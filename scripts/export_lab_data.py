"""랩(docs/lab.html)용 데이터 내보내기: PostgreSQL → docs/lab/data/*.csv + meta.json

브라우저 안 DuckDB가 이 CSV를 읽어 사용자가 고른 설정(가중치·기준일·신인 기준 등)으로 SQL을 다시 돌린다.
팀 키는 core 뷰의 team_key(연결표 ref.artist_xref 우선, 없으면 괄호 별칭)를 그대로 쓴다.

실행:
    python3 scripts/load_pg.py && psql -d crate_digger -f sql/kr/00_core_views.sql   # 먼저 적재
    python3 scripts/export_lab_data.py                # → docs/lab/data/
"""
from __future__ import annotations

import calendar
import csv
import io
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Callable, Dict, List
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_dashboard_data import PROGRAM_NAMES, _has_xref_table, psql_csv  # noqa: E402
from csv_schema import OUTCOME_TIER  # noqa: E402
import genre as genre_mod  # noqa: E402
import genre_fill  # noqa: E402
import collect_itunes  # noqa: E402
import players as players_mod  # noqa: E402
import video_match  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "docs" / "lab" / "data"
SPOTIFY_MATCH = ROOT / "data" / "raw" / "state" / "spotify_match.json"
XREF_FILE = ROOT / "data" / "raw" / "state" / "artist_xref.json"
RAW_DIR = ROOT / "data" / "raw"
IMAGE_CACHE = ROOT / "data" / "raw" / "state" / "artist_images.json"
MUSICBRAINZ_FILE = ROOT / "data" / "raw" / "state" / "musicbrainz.json"   # collect_musicbrainz: 공식 링크
INDIEGO_SNS = ROOT / "data" / "raw" / "state" / "indiego_sns.json"   # collect_indiego_sns: 인디고가 자동으로 붙인 인스타(확신 mid)
INDISTREET_SNS = ROOT / "data" / "raw" / "state" / "indistreet_sns.json"   # collect_indistreet_sns: 팀이 직접 적은 공식 계정
YT_CHANNELS = ROOT / "data" / "raw" / "state" / "yt_channels.json"   # collect_yt_channels: 팀 공식 채널·아바타

SIGNAL_FIELDS = ["team_key", "branch", "source", "program", "stage_rank", "signal_date", "venue", "role"]
TEAM_FIELDS = ["team_key", "display_name", "first_seen", "first_release", "fan_count", "album_count",
               "profile_status", "primary_genre", "agency", "newcomer_check", "genre_confidence"]
# 신인 판정 확인 상태 (2026-11-27 사용자 결정: 후보에서 빼지 않고 표시만, 점수·검증엔 안 씀)
NEWCOMER_CHECK_DAYS = 90   # 출처 수집 시작 뒤 이 기간 안에 처음 본 팀은 그 전부터 활동했을 수 있다 (데이터 시작점에 잘림)
LINK_FIELDS = ["team_key", "platform", "url"]
IMAGE_FIELDS = ["team_key", "url", "source", "page_url"]   # page_url = 사진 출처 페이지(표시할 때 링크로 걸기)
IMAGE_CACHE_HOSTS = ("i.scdn.co",)
YT_AVATAR_HOSTS = ("yt3.ggpht.com", "yt3.googleusercontent.com")   # YouTube Data API channels.list 썸네일
SPOTIFY_ID_RE = re.compile(r"[A-Za-z0-9]{22}")
CHANNEL_ID_RE = re.compile(r"UC[A-Za-z0-9_-]{22}")
VIDEO_FIELDS = ["team_key", "video_id", "title", "channel_title", "published_at", "kind"]
VIDEO_KIND_ORDER = {"stage": 0, "official_live": 1, "official": 2, "search": 3}
VIDEOS_PER_TEAM = 6
VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}")
# 무대가 아닌 영상(인터뷰·셀캠·직캠·쇼츠·예고)은 어느 채널이든 뺀다
NOT_STAGE = re.compile(r"interview|인터뷰|셀캠|직캠|fancam|#shorts|선공개|예고|teaser|비하인드|behind", re.I)
# KBS Kpop 채널은 아이돌 예능 클립이 대부분 → 라이브 프로그램 클립만 남긴다
KBS_LIVE = re.compile(r"더 시즌즈|리무진서비스|the seasons", re.I)
# 플랫폼 번호 → 아티스트 페이지 주소 (번호만 있을 때). 전체 주소가 오면 이 도메인일 때만 그대로 쓴다.
URL_TEMPLATES = {
    "melon": ("https://www.melon.com/artist/detail.htm?artistId={}", r"\d+"),
    "genie": ("https://www.genie.co.kr/detail/artistInfo?xxnm={}", r"\d+"),
    "bugs": ("https://music.bugs.co.kr/artist/{}", r"\d+"),
    "spotify": ("https://open.spotify.com/artist/{}", r"[A-Za-z0-9]{22}"),
    "instagram": ("https://www.instagram.com/{}/", r"[A-Za-z0-9._]{1,30}"),
    "youtube": (None, None),
}
URL_HOSTS = {"melon": "www.melon.com", "genie": "www.genie.co.kr", "bugs": "music.bugs.co.kr",
             "spotify": "open.spotify.com", "instagram": "www.instagram.com", "youtube": "www.youtube.com"}
COLLAB_FIELDS = ["team_key", "partner_key", "partner_name", "release_date", "role", "partner_established"]
# '기성 파트너' 규칙 — 이미 자리 잡은 아티스트와의 협업은 업계가 그 신인을 알아봤다는 신호일 수 있다.
# 시점 누수 방지: 모든 비교는 '그 협업 발매일' 기준(그때 이미 기성이었나). 정답·유명 여부도 그 전에 알 수 있던 것만.
ESTABLISHED_YEARS = 5      # 파트너 첫 발매가 협업보다 5년 이상 앞서면 기성 (신인 기준 3년보다 넉넉히 — 확실한 선배만)
ESTABLISHED_ALBUMS = 15    # 앨범(싱글 포함) 15개 이상이면 기성 (신인 기준 10개를 확실히 넘는 수준)
OUTCOME_FIELDS = ["team_key", "program", "program_label", "tier", "result", "announced_date", "counted", "grade", "weight",
                  "same_house_sources", "same_house_scored"]
SCORED_ROLES = ("discovery", "context")   # 점수에 들어가는 출처 역할
ROLES_FILE = ROOT / "config" / "source_roles.json"
DEBUT_OVERRIDES_FILE = ROOT / "config" / "debut_overrides.json"   # 사람이 확인한 데뷔일 (근거 필수)
GENRE_OVERRIDES_FILE = ROOT / "config" / "genre_overrides.json"   # 사람이 확인한 장르 갈래 (근거 필수)
DEFAULT_GRADE = ("B", 1)
GRADE_LADDER = [("S", 3), ("A", 2), ("B", 1)]   # 후보(nominee 등)는 한 칸 아래, B 아래는 없음
STATUS_PRIORITY = "CASE st.status WHEN 'famous' THEN 4 WHEN 'established' THEN 3 WHEN 'newcomer' THEN 2 ELSE 1 END"

Run = Callable[[str], str]


SIG_CTE = """WITH sig AS (
        SELECT * FROM core.v_signal          -- team_key = 연결표(ref.artist_xref) 또는 별칭으로 묶은 대표 키
        WHERE artist_key IS NOT NULL AND artist_key <> '' AND signal_date IS NOT NULL
    )"""


def queries(use_xref: bool) -> Dict[str, str]:
    display = ("(SELECT MIN(display_name) FROM ref.artist_xref x WHERE x.artist_key = t.team_key)"
               if use_xref else "NULL")
    return {
        "signals": f"""-- lab:signals
            {SIG_CTE}
            SELECT DISTINCT team_key, branch, source, COALESCE(program, '') AS program,
                   stage_rank, signal_date,
                   CASE WHEN branch = '공연' THEN COALESCE(venue, detail, '') ELSE '' END AS venue   -- 공연장 대표 이름 (ref.venue_xref)
            FROM sig ORDER BY team_key, signal_date""",
        "teams": f"""-- lab:teams
            {SIG_CTE},
            t AS (
                SELECT team_key, MIN(artist_text) AS any_name,
                       MIN(signal_date) FILTER (WHERE signal_date <= CURRENT_DATE) AS first_seen,
                       string_agg(DISTINCT source, '|') FILTER (WHERE branch = '큐레이션') AS press_sources,
                       string_agg(DISTINCT program, '|') FILTER (WHERE branch = '선정·지원') AS sel_programs
                FROM sig GROUP BY team_key
            ),
            prof AS (
                SELECT st.team_key,
                       MIN(st.first_release) AS first_release, MAX(st.fan_count) AS fan_count,
                       MAX(st.album_count) AS album_count,
                       (SELECT MIN(NULLIF(rp.agency_text, '')) FROM raw.raw_artist_profile rp
                        LEFT JOIN core.v_team_map tm2 ON tm2.variant_key = rp.artist_key
                        WHERE COALESCE(tm2.team_key, rp.artist_key) = st.team_key) AS agency,
                       (ARRAY_AGG(st.status ORDER BY {STATUS_PRIORITY} DESC))[1] AS profile_status
                FROM core.v_artist_status st
                GROUP BY 1
            ),
            genres AS (
                SELECT COALESCE(tm.team_key, g.artist_key) AS team_key,
                       string_agg(DISTINCT g.genre, '|') AS raw_genres
                FROM (SELECT artist_key, genre FROM raw.raw_artist_profile
                      UNION SELECT artist_key, genre FROM raw.raw_kr_release) g
                LEFT JOIN core.v_team_map tm ON tm.variant_key = g.artist_key
                WHERE COALESCE(g.genre, '') <> ''
                GROUP BY 1
            )
            SELECT t.team_key, COALESCE({display}, t.any_name) AS display_name, t.first_seen,
                   p.first_release, p.fan_count, p.album_count, p.profile_status, p.agency,
                   g.raw_genres, t.press_sources, t.sel_programs
            FROM t
            LEFT JOIN prof p ON p.team_key = t.team_key
            LEFT JOIN genres g ON g.team_key = t.team_key
            ORDER BY t.team_key""",
        "links": """-- lab:links
            WITH refs AS (
                SELECT artist_key, source AS platform, url AS ref FROM raw.raw_artist_profile
                WHERE source IN ('melon', 'spotify', 'instagram') AND COALESCE(url, '') <> ''
                UNION
                SELECT artist_key, 'youtube', youtube_url FROM raw.raw_artist_profile WHERE COALESCE(youtube_url, '') <> ''
                UNION
                SELECT artist_key, source, artist_source_id FROM raw.raw_kr_release
                WHERE source IN ('melon', 'genie', 'bugs') AND COALESCE(artist_source_id, '') <> ''
                  AND artist_source_id NOT LIKE '%,%'             -- 여러 아티스트 합작은 건너뜀
            )
            SELECT DISTINCT COALESCE(tm.team_key, r.artist_key) AS team_key, r.platform, r.ref
            FROM refs r LEFT JOIN core.v_team_map tm ON tm.variant_key = r.artist_key
            WHERE r.artist_key IS NOT NULL AND r.artist_key <> ''""",
        # 매체 리뷰 장르(음악취향Y·overtone·VISLA): 새 원본의 genre 칸 — 칸이 없는 옛 적재본에서도 돌게 to_jsonb 로 읽는다.
        # 이미 받은 글의 장르는 data/raw/reference/press_genres.csv(collect_webzines --genre-backfill)에서 주소로 보탠다.
        "press_genres": """-- lab:press_genres
            SELECT DISTINCT COALESCE(tm.team_key, p.artist_key) AS team_key, p.url,
                   COALESCE(to_jsonb(p) ->> 'genre', '') AS genre
            FROM raw.raw_press p LEFT JOIN core.v_team_map tm ON tm.variant_key = p.artist_key
            WHERE p.source IN ('musicy', 'overtone', 'visla') AND COALESCE(p.artist_key, '') <> ''
              AND COALESCE(p.is_sponsored, '0') <> '1'
            ORDER BY 1, 2""",
        "outcomes": """-- lab:outcomes
            SELECT DISTINCT team_key, program, tier, COALESCE(result, '') AS result,
                   announced_start AS announced_date, counted
            FROM core.v_outcome
            WHERE artist_key IS NOT NULL AND artist_key <> '' AND announced_start IS NOT NULL
            ORDER BY team_key, announced_date""",
    }


def _records(text: str) -> List[dict]:
    return list(csv.DictReader(io.StringIO(text)))


def _is_iso_date(text) -> bool:
    try:
        return isinstance(text, str) and bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", text)) and bool(date.fromisoformat(text))
    except ValueError:
        return False


def _check_override(e, kind: str, buckets: dict) -> List[str]:
    """덮어쓰기 항목 하나의 문제 목록 (비면 통과). 모든 항목에 이유·근거 링크·확인 날짜 필수."""
    if not isinstance(e, dict):
        return ["항목이 객체가 아님"]
    problems = [why for ok, why in (
        (isinstance(e.get("reason"), str) and e["reason"].strip(), "reason(이유)이 비어 있음"),
        (isinstance(e.get("evidence"), list) and any(isinstance(x, str) and x.strip() for x in e["evidence"]),
         "evidence(근거 링크)가 비어 있음"),
        (_is_iso_date(e.get("checked")), "checked(확인 날짜 YYYY-MM-DD)가 없음"),
    ) if not ok]
    if kind == "debut" and not _is_iso_date(e.get("debut")):
        problems.append("debut(데뷔 날짜 YYYY-MM-DD)가 올바르지 않음")
    if kind == "genre" and e.get("genre") not in buckets:
        problems.append(f"genre는 장르 지도 갈래 키 중 하나 ({'/'.join(buckets)})")
    return problems


def load_team_overrides(path: Path, kind: str) -> Dict[str, dict]:
    """사람이 확인한 팀별 덮어쓰기 (kind = 'debut' 데뷔일 / 'genre' 장르 갈래 키) → {팀 키: 항목}.
    파일이 없으면 빈 dict, 항목이 잘못됐으면 어느 팀의 무엇이 문제인지 알려 주고 멈춘다(근거 없는 덮어쓰기 금지)."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    teams = data.get("teams") if isinstance(data, dict) else None
    if not isinstance(teams, dict):
        raise ValueError(f"{path}: 'teams' 객체가 없음")
    buckets = genre_mod.load_config()["buckets"]
    problems = [f"{k}: {why}" for k, e in teams.items() for why in _check_override(e, kind, buckets)]
    if problems:
        raise ValueError(f"{path} 항목 오류 — " + " · ".join(problems))
    return teams


def press_genres_by_team(rows: List[dict], reference: Dict[str, str]) -> Dict[str, str]:
    """매체 리뷰 행(team_key·url·genre) → {팀: '장르|장르'}. 행의 genre 가 비면 참고 파일(주소 → 장르)로 보탠다."""
    out: Dict[str, List[str]] = {}
    for r in rows:
        g = (r.get("genre") or "").strip() or (reference.get(r.get("url") or "") or "").strip()
        if g and r.get("team_key"):
            got = out.setdefault(r["team_key"], [])
            if g not in got:
                got.append(g)
    return {k: "|".join(v) for k, v in out.items()}


def _press_genre_ref() -> Dict[str, str]:
    from collect_webzines import load_genre_reference
    return load_genre_reference()


def team_rows(rows: List[dict], roles: dict | None = None, debut_overrides: Dict[str, dict] | None = None,
              genre_overrides: Dict[str, dict] | None = None) -> List[dict]:
    """도우미 열(raw_genres 등)로 대표 장르를 정하고, 프로필 없는 팀은 unknown으로.
    candidate_rules.excluded_teams(팀이 아닌 이름·사람이 확인한 기성 팀)는 팀 표에서 빼서 후보군·백테스트에 안 들어가게 한다.
    debut_overrides(사람이 확인한 데뷔일)는 프로필 첫 발매일과 비교해 이른 쪽을 first_release로 — 데뷔는 과거 사실이라
    과거 기준일 검증에 써도 미래 정보가 새지 않는다. genre_overrides(사람이 확인한 갈래 키)는 자동 추정보다 먼저 쓴다."""
    excluded = ((roles or {}).get("candidate_rules") or {}).get("excluded_teams") or {}
    debut_overrides, genre_overrides = debut_overrides or {}, genre_overrides or {}
    labels = {k: b["label"] for k, b in genre_mod.load_config()["buckets"].items()}
    out = []
    for r in rows:
        key = r.get("team_key")
        if key in excluded:
            continue
        row = {k: r.get(k) or "" for k in TEAM_FIELDS}
        row["profile_status"] = row["profile_status"] or "unknown"
        # 대표 장르 + 확신도(profile 플랫폼 장르 / press 확실한 출처 힌트) — 빈칸 추정·리뷰 장르는 export()의 genre_fill
        row["primary_genre"], row["genre_confidence"] = genre_fill.base_genre(
            r.get("raw_genres"), r.get("press_sources"), r.get("sel_programs"))
        if key in debut_overrides:
            row["first_release"] = min(d for d in (row["first_release"], debut_overrides[key]["debut"]) if d)
        if key in genre_overrides:
            row["primary_genre"], row["genre_confidence"] = labels[genre_overrides[key]["genre"]], genre_fill.PROFILE
        out.append(row)
    return out


def with_newcomer_check(teams: List[dict], signals: List[dict], window_days: int = NEWCOMER_CHECK_DAYS) -> List[dict]:
    """팀마다 newcomer_check 를 붙인 새 목록 (입력은 바꾸지 않음):
    verified = 첫 발매일 있음(사람이 확인한 데뷔일 포함) · unverified = 첫 발매일 없고, 그 팀을 처음 본 출처의 수집 시작일
    (signals 에서 출처별 가장 이른 날) + window_days 안에 처음 봄 — 우리가 모으기 전부터 활동했을 수 있어 신인인지 확실치 않음 ·
    first_seen = 첫 발매일 없고 그 뒤에 처음 봄 (우리 데이터 첫 등장으로 신인 판정)."""
    start: Dict[str, str] = {}
    first: Dict[str, tuple] = {}            # 팀 → (첫 날짜, 그날 본 출처들)
    for r in signals:
        d, src, key = r.get("signal_date") or "", r.get("source") or "", r.get("team_key") or ""
        if not (d and src and key):
            continue
        if d < start.get(src, "9999"):
            start[src] = d
        day, srcs = first.get(key, ("9999", set()))
        if d < day:
            first[key] = (d, {src})
        elif d == day:
            first[key] = (day, srcs | {src})

    def check(t: dict) -> str:
        if t.get("first_release"):
            return "verified"
        day, srcs = first.get(t.get("team_key"), ("", set()))
        early = any((date.fromisoformat(day[:10]) - date.fromisoformat(start[s][:10])).days <= window_days for s in srcs)
        return "unverified" if day and early else "first_seen"

    return [{**t, "newcomer_check": check(t)} for t in teams]


def load_roles(path: Path = ROLES_FILE) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"default_role": "discovery", "signals": {}, "outcomes": {}}   # 분류표가 없으면 예전처럼 전부 사용


def signal_role(row: dict, roles: dict) -> str:
    """config/source_roles.json 기준 신호 역할. 선정·지원은 프로그램, 나머지는 출처로 찾는다."""
    branch = row.get("branch", "")
    name = row.get("program") if branch == "선정·지원" else row.get("source")
    entry = (roles.get("signals") or {}).get(f"{branch}:{name}") or {}
    return entry.get("role") or roles.get("default_role", "pending")


def _lower_grade(grade: str, weight) -> tuple:
    """등급 한 칸 낮추기 (S→A→B, B는 그대로)."""
    names = [g for g, _ in GRADE_LADDER]
    if grade not in names:
        return grade, weight
    return GRADE_LADDER[min(names.index(grade) + 1, len(names) - 1)]


def outcome_rows(rows: List[dict], roles: dict | None = None) -> List[dict]:
    """정답 행 + 등급. outcome_rules: lower_results(후보·최종 후보 등은 한 등급 아래), excluded_teams(정답에서 뺄 팀과 이유),
    excluded_rows(프로그램·발표 연도·팀이 모두 맞는 행만 뺌 — 원본 정답 파일에 잘못 들어간 행).
    같은 팀·같은 프로그램·같은 날짜가 후보와 수상으로 둘 다 있으면 가중치가 큰 행 하나만 남긴다."""
    roles = roles or {}
    grades = roles.get("outcomes") or {}
    rules = roles.get("outcome_rules") or {}
    lower = set(rules.get("lower_results") or [])
    excluded = rules.get("excluded_teams") or {}
    excluded_rows = {(e.get("program"), str(e.get("year")), t)
                     for e in rules.get("excluded_rows") or [] for t in e.get("teams") or []}
    best: Dict[tuple, dict] = {}
    for r in rows:
        if r.get("team_key") in excluded:
            continue
        if (r.get("program"), (r.get("announced_date") or "")[:4], r.get("team_key")) in excluded_rows:
            continue   # 그해 그 프로그램의 그 팀 행만 뺀다 (예: 본무대 정답에 섞인 신인 경연 팀)
        g = grades.get(r["program"]) or {}
        grade, weight = g.get("grade", DEFAULT_GRADE[0]), g.get("weight", DEFAULT_GRADE[1])
        if (r.get("result") or "") in lower:
            grade, weight = _lower_grade(grade, weight)
        row = {**{k: r.get(k) or "" for k in OUTCOME_FIELDS},
               "program_label": PROGRAM_NAMES.get(r["program"], r["program"]),
               "counted": "true" if str(r.get("counted", "")).lower() in ("t", "true", "1") else "false",
               "grade": grade, "weight": weight}
        key = (row["team_key"], row["program"], row["announced_date"])
        if key not in best or int(weight) > int(best[key]["weight"]):
            best[key] = row
    return list(best.values())


def _signal_key(row: dict) -> str:
    branch = row.get("branch", "")
    return f"{branch}:{row.get('program') if branch == '선정·지원' else row.get('source')}"


def same_house_flags(outcomes: List[dict], signals: List[dict], roles: dict | None = None) -> List[dict]:
    """'같은 집안' 표시: 정답 발표 전에 그 정답과 같은 집안 출처(config same_house, apply=true)에 나온 팀이면
    same_house_sources = 그 출처 키들(;로 이음) — 출처 성적표에서 그 출처의 적중으로 세지 않음.
    same_house_scored = 그중 점수에 쓰는 출처(discovery·context)가 있으면 true — 점수 백테스트에서도 적중으로 세지 않음."""
    roles = roles or {}
    pairs = [p for p in roles.get("same_house") or [] if p.get("apply")]
    by_program: Dict[str, set] = {}
    for p in pairs:
        for prog in p.get("outcomes", []):
            by_program.setdefault(prog, set()).update(p.get("sources", []))
    wanted = set().union(*by_program.values()) if by_program else set()
    first_seen: Dict[tuple, str] = {}
    for sg in signals:
        key = _signal_key(sg)
        if key in wanted:
            k = (sg["team_key"], key)
            first_seen[k] = min(first_seen.get(k, sg["signal_date"]), sg["signal_date"])
    sig_roles = roles.get("signals") or {}
    out = []
    for o in outcomes:
        srcs = sorted(src for src in by_program.get(o["program"], ())
                      if first_seen.get((o["team_key"], src), "9999") < o["announced_date"])
        scored = any((sig_roles.get(src) or {}).get("role") in SCORED_ROLES for src in srcs)
        out.append({**o, "same_house_sources": ";".join(srcs), "same_house_scored": "true" if scored else "false"})
    return out


def _link_url(platform: str, ref: str) -> str | None:
    """번호·계정명·주소 → 안전한 아티스트 페이지 주소. 모르는 플랫폼·다른 도메인·이상한 값은 None."""
    if platform not in URL_TEMPLATES or not ref:
        return None
    ref = ref.strip()
    if ref.startswith("http"):
        parsed = urlparse(ref)
        ok = parsed.scheme == "https" and parsed.netloc in (URL_HOSTS[platform], URL_HOSTS[platform].replace("www.", ""))
        return ref if ok else None
    template, pattern = URL_TEMPLATES[platform]
    value = ref.lstrip("@")
    if template is None or not re.fullmatch(pattern, value):
        return None
    return template.format(value)


def _norm_url(url: str) -> str:
    return url.rstrip("/").replace("://", "://www.", 1) if "://www." not in url else url.rstrip("/")


LINK_BLOCKLIST_FILE = ROOT / "config" / "link_blocklist.json"   # 사람이 틀리거나 애매하다고 본 연결 (docs/link_audit_2026-11-28.md)


def _load_blocklist() -> List[dict]:
    return json.loads(LINK_BLOCKLIST_FILE.read_text(encoding="utf-8")).get("blocked", []) if LINK_BLOCKLIST_FILE.exists() else []


def drop_blocked_links(refs: List[dict], blocked: List[dict] | None = None) -> List[dict]:
    """차단 목록(팀 키·플랫폼·계정 또는 주소)에 있는 연결을 뺀다. 계정·주소 어느 꼴로 적어도 같은 주소면 막는다.
    항목마다 reason·checked 가 없으면 멈춘다. blocked 를 안 주면 config/link_blocklist.json 을 읽는다(없으면 빈 목록)."""
    if blocked is None:
        blocked = _load_blocklist()

    def key(team: str, platform: str, ref: str):
        url = _link_url(platform, ref or "")
        return (team, platform, (_norm_url(url) if url else (ref or "").strip()).lower())

    bad = set()
    for e in blocked:
        if not all(e.get(f) for f in ("team_key", "platform", "ref", "reason", "checked")):
            raise ValueError(f"link_blocklist 항목에 team_key·platform·ref·reason·checked 가 모두 있어야 해요: {e}")
        bad.add(key(e["team_key"], e["platform"], e["ref"]))
    return [r for r in refs if key(r.get("team_key"), r.get("platform", ""), r.get("ref") or "") not in bad]


def drop_blocked_channels(channels: dict, blocked: List[dict] | None = None) -> dict:
    """collect_yt_channels 상태(팀 → 채널)에서 차단 목록의 유튜브 채널을 뺀다 → 막은 채널 아바타가 사진으로 안 나간다."""
    refs = [{"team_key": t, "platform": "youtube", "ref": f"https://www.youtube.com/channel/{(c or {}).get('channel_id') or ''}"}
            for t, c in channels.items()]
    keep = {r["team_key"] for r in drop_blocked_links(refs, blocked)}
    return {t: c for t, c in channels.items() if t in keep}


def drop_blocked_itunes(state: dict, blocked: List[dict] | None = None) -> dict:
    """collect_itunes 상태(팀 → iTunes 아티스트)에서 차단 목록(platform itunes, ref = 아티스트 번호 또는 주소)을 뺀다
    → 막은 아티스트의 미리듣기가 players.csv 에 안 나간다."""
    keep = {}
    for team, e in state.items():
        refs = [{"team_key": team, "platform": "itunes", "ref": str((e or {}).get(f) or "")} for f in ("artist_id", "artist_url")]
        if len(drop_blocked_links(refs, blocked)) == len(refs):
            keep[team] = e
    return keep


def drop_blocked_videos(rows: List[dict], blocked: List[dict] | None = None) -> List[dict]:
    """영상 원본 줄 중 차단 목록의 유튜브 채널(그 팀) 영상을 뺀다 → 막은 채널 영상이 videos.csv·players.csv 에 안 나간다."""
    blocked = _load_blocklist() if blocked is None else blocked
    if not blocked:
        return rows
    refs = [{"team_key": r.get("team_key"), "platform": "youtube", "ref": f"https://www.youtube.com/channel/{r.get('channel_id') or ''}",
             "_i": i} for i, r in enumerate(rows)]
    keep = {x["_i"] for x in drop_blocked_links(refs, blocked)}
    return [r for i, r in enumerate(rows) if i in keep]


def link_rows(refs: List[dict]) -> List[dict]:
    """(팀, 플랫폼, 번호/주소) → (팀, 플랫폼, 주소). 같은 주소는 하나만."""
    out, seen = [], set()
    for r in refs:
        url = _link_url(r.get("platform", ""), r.get("ref") or "")
        key = (r.get("team_key"), r.get("platform"), _norm_url(url) if url else None)
        if not url or not r.get("team_key") or key in seen:
            continue
        seen.add(key)
        out.append({"team_key": r["team_key"], "platform": r["platform"], "url": url})
    return out


def spotify_refs(matches: dict, key_of: Callable[[str], str]) -> List[dict]:
    """spotify_match.json(이름 → {id, namesakes}) 중 같은 이름이 하나뿐인 것만 팀에 붙인다(동명 오연결 방지)."""
    return [{"team_key": key_of(name), "platform": "spotify", "ref": m["id"]}
            for name, m in sorted(matches.items())
            if m and m.get("id") and int(m.get("namesakes") or 1) <= 1]


MUSICBRAINZ_PLATFORMS = ("youtube", "spotify", "instagram")


def musicbrainz_refs(state: dict) -> List[dict]:
    """collect_musicbrainz 상태 → 연결 (찾은 팀의 유튜브 채널 주소·스포티파이 번호·인스타 계정). 주소 검사는 link_rows 가 한다."""
    refs: List[dict] = []
    for team, entry in sorted(state.items()):
        urls = (entry or {}).get("urls") or {} if (entry or {}).get("mbid") else {}
        refs += [{"team_key": team, "platform": p, "ref": v} for p in MUSICBRAINZ_PLATFORMS for v in urls.get(p) or []]
    return refs


SAME_AS_YOUTUBE = re.compile(r"^https://(?:www\.)?youtube\.com/(channel/UC[\w-]{22}|@[\w.\-%]+|c/[\w.\-%]+|user/[\w.\-%]+)/?(?:\?.*)?$")
SAME_AS_SPOTIFY = re.compile(r"^https://open\.spotify\.com/(?:intl-[a-z-]+/)?artist/([A-Za-z0-9]{22})/?(?:\?.*)?$")


def _same_as_one(same_as: List[str], pattern: "re.Pattern[str]") -> str | None:
    """sameAs 중 pattern 에 맞는 값이 정확히 하나면 그 값(첫 묶음), 없거나 둘 이상이면 None (어느 쪽이 팀 것인지 모름)."""
    found = list(dict.fromkeys(m.group(1) for u in same_as if isinstance(u, str) and (m := pattern.match(u.strip()))))
    return found[0] if len(found) == 1 else None


def indistreet_sns_refs(state: dict, key_of: Callable[[str], str] = lambda n: n) -> List[dict]:
    """collect_indistreet_sns 상태 → 연결 (팀이 인디스트릿 페이지 sameAs 에 직접 적은 공식 채널).
    인스타 = 수집기가 고른 하나뿐인 계정, 유튜브 = 채널 주소(@이름·channel/UC…·c/…·user/…)가 하나뿐일 때,
    스포티파이 = 아티스트 주소가 하나뿐일 때 번호로. 영상·앨범·유튜브 뮤직 주소는 쓰지 않는다. 주소 검사는 link_rows 가 한다."""
    refs: List[dict] = []
    for name, entry in sorted(state.items()):
        if not isinstance(entry, dict):
            continue
        team = key_of(name)
        same_as = entry.get("same_as") or []
        if entry.get("instagram"):
            refs.append({"team_key": team, "platform": "instagram", "ref": entry["instagram"]})
        yt = _same_as_one(same_as, SAME_AS_YOUTUBE)
        if yt:
            refs.append({"team_key": team, "platform": "youtube", "ref": f"https://www.youtube.com/{yt}"})
        sp = _same_as_one(same_as, SAME_AS_SPOTIFY)
        if sp:
            refs.append({"team_key": team, "platform": "spotify", "ref": sp})
    return refs


def indiego_sns_refs(state: dict, have_instagram: set, key_of: Callable[[str], str] = lambda n: n) -> List[dict]:
    """collect_indiego_sns 상태 → 인스타 연결(확신 mid: 아는 계정과 92% 일치). 이미 인스타가 있는 팀에는 안 붙인다."""
    return [r for r in indistreet_sns_refs(state, key_of=key_of)
            if r["platform"] == "instagram" and r["team_key"] not in have_instagram]


def _extra_refs() -> List[dict]:
    """PostgreSQL 밖의 연결: 스포티파이 이름 매칭, 연결표의 인스타 계정, MusicBrainz 공식 링크. 파일이 없으면 빈 목록."""
    from artist_xref import canonical_key, load_xref

    index = load_xref()
    refs: List[dict] = []
    try:
        matches = json.loads(SPOTIFY_MATCH.read_text(encoding="utf-8"))
        refs += spotify_refs(matches, key_of=lambda n: canonical_key(n, index))
    except (OSError, ValueError):
        pass
    try:
        artists = json.loads(XREF_FILE.read_text(encoding="utf-8"))
        refs += [{"team_key": a["artist_key"], "platform": "instagram", "ref": h.get("handle", "")}
                 for a in artists for h in a.get("instagram") or []
                 if isinstance(h, dict) and h.get("confidence") in ("high", "mid")]   # 확신 낮은 계정은 안 붙임
    except (OSError, ValueError, TypeError, KeyError):
        pass
    refs += indistreet_sns_refs(_read_json_dict(INDISTREET_SNS), key_of=lambda n: canonical_key(n, index))
    refs += indiego_sns_refs(_read_json_dict(INDIEGO_SNS), {r["team_key"] for r in refs if r["platform"] == "instagram"},
                             key_of=lambda n: canonical_key(n, index))
    refs += musicbrainz_refs(_read_json_dict(MUSICBRAINZ_FILE))   # 맨 뒤: 같은 팀에 이미 있는 연결이 먼저 쓰인다
    return refs


def filtered_videos(raw: List[dict]) -> List[dict]:
    """수집한 유튜브 영상 → 거른 전체 목록 (팀·영상 번호마다 한 줄, 자르기 전).
    제목 ↔ 팀 이름은 video_match 규칙(흔한 낱말·짧은 이름)으로 다시 걸러낸다 — 원본 raw_video 는 그대로."""
    raw, _ = video_match.filter_rows(raw)
    best: Dict[tuple, dict] = {}
    for r in raw:
        vid, title, channel = r.get("video_id") or "", r.get("title") or "", r.get("channel_title") or ""
        if not VIDEO_ID.fullmatch(vid) or not r.get("team_key") or NOT_STAGE.search(title):
            continue
        if channel.startswith("KBS") and not KBS_LIVE.search(title):
            continue
        row = {k: r.get(k) or "" for k in VIDEO_FIELDS}
        row["published_at"] = row["published_at"][:10]
        best.setdefault((row["team_key"], vid), row)
    return list(best.values())


def video_rows(raw: List[dict], per_team: int = VIDEOS_PER_TEAM, filtered: List[dict] | None = None) -> List[dict]:
    """팀별 무대 영상(무대 > 공식 라이브 > 공식 > 검색, 같은 순위는 최신순, 팀당 최대 per_team)."""
    by_team: Dict[str, List[dict]] = {}
    for row in (filtered_videos(raw) if filtered is None else filtered):
        by_team.setdefault(row["team_key"], []).append(row)
    out = []
    for team in sorted(by_team):
        ranked = sorted(by_team[team], key=lambda v: v["published_at"], reverse=True)
        ranked.sort(key=lambda v: VIDEO_KIND_ORDER.get(v["kind"], 9))
        out.extend(ranked[:per_team])
    return out


def _safe_image(url: str, hosts: tuple) -> bool:
    p = urlparse(url or "")
    return p.scheme == "https" and p.netloc in hosts


def image_rows(cache: dict, yt_channels: dict | None = None) -> List[dict]:
    """팀별 사진 1장: 스포티파이 아티스트 사진(collect_artist_images) → 없으면 유튜브 공식 채널 아바타(collect_yt_channels).
    https + 허용 도메인만. page_url 은 출처 페이지(앱이 사진에 출처 링크를 걸 수 있게)."""
    picked: Dict[str, dict] = {}
    for team, v in cache.items():
        v = v or {}
        if _safe_image(v.get("url") or "", IMAGE_CACHE_HOSTS):
            sid = v.get("spotify_id") or ""
            page = f"https://open.spotify.com/artist/{sid}" if SPOTIFY_ID_RE.fullmatch(sid) else ""
            picked[team] = {"team_key": team, "url": v["url"], "source": v.get("source", ""), "page_url": page}
    for team, ch in (yt_channels or {}).items():
        ch = ch or {}
        cid = ch.get("channel_id") or ""
        if team in picked or not CHANNEL_ID_RE.fullmatch(cid) or not _safe_image(ch.get("avatar") or "", YT_AVATAR_HOSTS):
            continue
        picked[team] = {"team_key": team, "url": ch["avatar"], "source": "youtube",
                        "page_url": f"https://www.youtube.com/channel/{cid}"}
    return [picked[t] for t in sorted(picked)]


def _read_json_dict(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _image_cache() -> dict:
    return _read_json_dict(IMAGE_CACHE)


YT_KEEP_DAYS = 30   # YouTube API 정책: API 데이터는 30일 안에 새로 받거나 지운다


def fresh_channels(teams: dict, today: str, days: int = YT_KEEP_DAYS) -> dict:
    """확인(checked)한 지 days 일이 안 된 채널만 (오래된 아바타는 앱에 걸지 않는다)."""
    def fresh(v: dict) -> bool:
        try:
            return (date.fromisoformat(today) - date.fromisoformat((v or {}).get("checked") or "")).days <= days
        except ValueError:
            return False
    return {k: v for k, v in teams.items() if fresh(v)}


def _yt_channels() -> dict:
    return fresh_channels(_read_json_dict(YT_CHANNELS).get("teams") or {}, date.today().isoformat())


def _itunes_state() -> dict:
    return _read_json_dict(collect_itunes.STATE_FILE)


def _video_views() -> Dict[str, int]:
    return players_mod.latest_views(RAW_DIR)


def period_end_date(text: str, precision: str = "") -> str:
    """스포티파이 발매일 → YYYY-MM-DD. 일부만 알면 기간의 '마지막 날'(시점 누수 방지: 늦게 잡아 '미리 알았다'를 부풀리지 않음).
    '2024'(year) → 2024-12-31, '2024-02'(month) → 2024-02-29. 형식이 틀리면 ''."""
    parts = (text or "").strip().split("-")
    try:
        nums = [int(p) for p in parts]
        if len(nums) == 1:
            return date(nums[0], 12, 31).isoformat()
        if len(nums) == 2:
            return date(nums[0], nums[1], calendar.monthrange(nums[0], nums[1])[1]).isoformat()
        if len(nums) == 3:
            return date(*nums).isoformat()
    except (ValueError, calendar.IllegalMonthError):
        return ""
    return ""


def _years_before(earlier: str, later: str, years: int) -> bool:
    """earlier 가 later 보다 years 년 이상 앞서나 (2월 29일은 28일로)."""
    try:
        e, l = date.fromisoformat(earlier), date.fromisoformat(later)
    except ValueError:
        return False
    try:
        threshold = l.replace(year=l.year - years)
    except ValueError:
        threshold = l.replace(year=l.year - years, day=28)
    return e <= threshold


def _is_established(partner_key: str, profile: dict, released: str, famous: set, first_outcome: Dict[str, str]) -> bool:
    # 파트너 첫 발매도 보수적으로 늦게 · 본인 음반 기준(first_release_own)이 있으면 그것 (참여 음반이 연차를 앞당기지 않게)
    first = period_end_date(profile.get("first_release_own") or profile.get("first_release_date", ""))
    albums = int(profile["album_count"]) if str(profile.get("album_count") or "").isdigit() else 0
    won = first_outcome.get(partner_key)
    return bool((first and _years_before(first, released, ESTABLISHED_YEARS)) or albums >= ESTABLISHED_ALBUMS
                or partner_key in famous or (won and won < released))


def collab_rows(collabs: List[dict], partners: List[dict], teams: List[dict], outcomes: List[dict],
                key_of: Callable[[str], str] | None = None, xref_index: dict | None = None) -> List[dict]:
    """raw_collab(+partner) → collabs.csv 행. 팀·파트너 키는 아티스트 연결표의 canonical_key."""
    if key_of is None:
        from artist_xref import canonical_key, load_xref

        index = load_xref() if xref_index is None else xref_index
        key_of = lambda name: canonical_key(name, index)   # noqa: E731
    profiles = {p.get("partner_spotify_id", ""): p for p in partners}
    famous = {t["team_key"] for t in teams if t.get("profile_status") == "famous"}
    first_outcome: Dict[str, str] = {}
    for o in outcomes:
        if str(o.get("counted", "")).lower() == "true" and o.get("announced_date"):
            first_outcome[o["team_key"]] = min(first_outcome.get(o["team_key"], o["announced_date"]), o["announced_date"])
    out, seen = [], set()
    for c in collabs:
        team, partner = key_of(c.get("artist_name", "")), key_of(c.get("partner_name", ""))
        released = period_end_date(c.get("release_date", ""), c.get("release_date_precision", ""))
        if not team or not partner or team == partner or not released:
            continue
        est = _is_established(partner, profiles.get(c.get("partner_spotify_id", ""), {}), released, famous, first_outcome)
        row = {"team_key": team, "partner_key": partner, "partner_name": c.get("partner_name", ""),
               "release_date": released, "role": c.get("role", ""), "partner_established": "true" if est else "false"}
        sig = tuple(row.values())
        if sig not in seen:
            seen.add(sig)
            out.append(row)
    return out


def _raw_collabs(raw_dir: Path = RAW_DIR) -> tuple:
    """data/raw/raw_collab_*.csv(협업)와 raw_collab_partner_*.csv(파트너 프로필). 없으면 빈 목록."""
    collabs: List[dict] = []
    partners: List[dict] = []
    for path in sorted(raw_dir.glob("raw_collab_*.csv")):
        with open(path, encoding="utf-8") as f:
            (partners if path.name.startswith("raw_collab_partner_") else collabs).extend(csv.DictReader(f))
    return collabs, partners


CHANNEL_FILE_SUFFIX = "_channels.csv"   # collect_yt_channels 가 쓰는 공식 채널 영상 원본


def drop_unlinked_channel_videos(rows: List[dict], yt_teams: dict) -> List[dict]:
    """공식 채널 영상 원본(*_channels.csv) 줄은 그 팀에 지금도 그 채널이 붙어 있을 때만 (연결이 끊긴 채널 영상은 뺌)."""
    current = {(k, (v or {}).get("channel_id")) for k, v in (yt_teams or {}).items()}
    return [r for r in rows if not str(r.get("_file", "")).endswith(CHANNEL_FILE_SUFFIX)
            or (r.get("team_key"), r.get("channel_id")) in current]


def _raw_videos(raw_dir: Path = RAW_DIR) -> List[dict]:
    rows: List[dict] = []
    for path in sorted(raw_dir.glob("raw_video_*.csv")):
        with open(path, encoding="utf-8") as f:
            rows.extend({**r, "_file": path.name} for r in csv.DictReader(f))
    return drop_unlinked_channel_videos(rows, _read_json_dict(YT_CHANNELS).get("teams") or {})


def program_rows(signals: List[dict], outcomes: List[dict]) -> List[dict]:
    kinds: Dict[str, str] = {}
    for s in signals:
        if s.get("program") and s.get("branch") == "선정·지원":
            kinds.setdefault(s["program"], "signal")
    for o in outcomes:
        if o["program"] in OUTCOME_TIER or o["program"] not in kinds:
            kinds[o["program"]] = "outcome"
    return [{"program": p, "label": PROGRAM_NAMES.get(p, p), "kind": k} for p, k in sorted(kinds.items())]


def _write_csv(path: Path, fields: List[str], rows: List[dict]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def export(out_dir: Path = OUT_DIR, run: Run = psql_csv, today: str | None = None,
           extra_refs: Callable[[], List[dict]] | None = _extra_refs,
           raw_videos: Callable[[], List[dict]] | None = _raw_videos,
           image_cache: Callable[[], dict] | None = _image_cache,
           yt_channels: Callable[[], dict] | None = _yt_channels,
           video_views: Callable[[], Dict[str, int]] | None = _video_views,
           itunes_state: Callable[[], dict] | None = _itunes_state,
           raw_collabs: Callable[[], tuple] | None = _raw_collabs,
           press_genre_ref: Callable[[], Dict[str, str]] | None = _press_genre_ref) -> dict:
    use_xref = _has_xref_table(run)
    q = queries(use_xref)
    roles = load_roles()
    signals = [{**r, "role": signal_role(r, roles)} for r in _records(run(q["signals"]))]
    press = press_genres_by_team(_records(run(q["press_genres"])), press_genre_ref() if press_genre_ref else {})
    team_raw = [{**r, "press_genres": press.get(r.get("team_key") or "", "")} for r in _records(run(q["teams"]))]
    teams = team_rows(team_raw, roles,
                      debut_overrides=load_team_overrides(DEBUT_OVERRIDES_FILE, "debut"),
                      genre_overrides=load_team_overrides(GENRE_OVERRIDES_FILE, "genre"))
    teams = with_newcomer_check(teams, signals)
    # 장르 빈칸 추정(같은 무대 다수결 → 공연장 성향 → 약한 출처 힌트, 확신도 inferred) — 정답 정보 안 씀 (docs/genre_fill.md)
    # 매체 리뷰 장르는 review(추정과 inferred_low 사이, 비교·분석 제외 — 2026-11-28 결정, docs/genre_fill.md)
    teams = genre_fill.fill_genres(teams, signals, genre_fill.weak_hints(team_raw), genre_fill.review_genres(team_raw))
    outcomes = same_house_flags(outcome_rows(_records(run(q["outcomes"])), roles), signals, roles)
    programs = program_rows(signals, outcomes)
    links = link_rows(drop_blocked_links(_records(run(q["links"])) + (extra_refs() if extra_refs else [])))

    out_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(out_dir / "signals.csv", SIGNAL_FIELDS, signals)
    _write_csv(out_dir / "teams.csv", TEAM_FIELDS, teams)
    _write_csv(out_dir / "outcomes.csv", OUTCOME_FIELDS, outcomes)
    _write_csv(out_dir / "programs.csv", ["program", "label", "kind"], programs)
    # 앱이 역할 설명·근거를 보여 줄 수 있게 분류표 사본 (원본: config/source_roles.json)
    (out_dir / "source_roles.json").write_text(json.dumps(roles, ensure_ascii=False, indent=1), encoding="utf-8")
    _write_csv(out_dir / "links.csv", LINK_FIELDS, links)
    all_videos = filtered_videos(drop_blocked_videos(raw_videos())) if raw_videos else []
    videos = video_rows([], filtered=all_videos)
    _write_csv(out_dir / "videos.csv", VIDEO_FIELDS, videos)
    # 바로 듣기 표: 팀마다 스포티파이 1줄 + 대표 유튜브 영상 1줄 (규칙: scripts/players.py)
    players = players_mod.player_rows(links, all_videos, video_views() if video_views else {})
    # iTunes 30초 미리듣기 — 확인된(제목 겹침·첫 발매 연도) 것만 (규칙: scripts/collect_itunes.py)
    players = sorted(players + collect_itunes.player_rows(drop_blocked_itunes(itunes_state() if itunes_state else {})),
                     key=lambda r: (r["team_key"], ("spotify", "youtube", "itunes").index(r["kind"])))
    _write_csv(out_dir / "players.csv", players_mod.PLAYER_FIELDS, players)
    images = image_rows(image_cache() if image_cache else {}, drop_blocked_channels(yt_channels() if yt_channels else {}))
    _write_csv(out_dir / "images.csv", IMAGE_FIELDS, images)
    raw_c, raw_p = raw_collabs() if raw_collabs else ([], [])
    collabs = collab_rows(raw_c, raw_p, teams, outcomes) if raw_c else []
    _write_csv(out_dir / "collabs.csv", COLLAB_FIELDS, collabs)   # 데이터가 없으면 헤더만
    day = today or date.today().isoformat()
    try:   # 직전 '날짜'의 행 수 → 앱이 '어젯밤 새로 붙은 신호·영상 수'를 보여 줄 수 있게
        old = json.loads((out_dir / "meta.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        old = {}
    # 같은 날 다시 돌리면 어제 값을 그대로 둔다 (몇 시간 전 실행과 비교하지 않게)
    prev_rows = old.get("prev_rows", {}) if old.get("data_end") == day else (old.get("rows") or {})
    meta = {
        "prev_rows": prev_rows,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "data_end": day,
        "uses_artist_xref": use_xref,
        "rows": {"signals": len(signals), "teams": len(teams), "outcomes": len(outcomes),
                 "programs": len(programs), "links": len(links), "videos": len(videos), "images": len(images),
                 "players": len(players),
                 "collabs": len(collabs)},
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def main() -> int:
    try:
        meta = export()
    except RuntimeError as e:
        print(f"❌ PostgreSQL에서 읽지 못했어요 (먼저 load_pg.py와 00_core_views.sql을 실행): {e}", file=sys.stderr)
        return 1
    print(f"✅ 랩 데이터 → {OUT_DIR.relative_to(ROOT)} {meta['rows']} (연결표 사용: {meta['uses_artist_xref']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
