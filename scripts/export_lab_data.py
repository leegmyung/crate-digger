"""랩(docs/lab.html)용 데이터 내보내기: PostgreSQL → docs/lab/data/*.csv + meta.json

브라우저 안 DuckDB가 이 CSV를 읽어 사용자가 고른 설정(가중치·기준일·신인 기준 등)으로 SQL을 다시 돌린다.
팀 키는 core 뷰의 team_key(연결표 ref.artist_xref 우선, 없으면 괄호 별칭)를 그대로 쓴다.

실행:
    python3 scripts/load_pg.py && psql -d crate_digger -f sql/kr/00_core_views.sql   # 먼저 적재
    python3 scripts/export_lab_data.py                # → docs/lab/data/
"""
from __future__ import annotations

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
from build_dashboard_data import PROGRAM_NAMES, _has_xref_table, _infer_genres, psql_csv  # noqa: E402
from csv_schema import OUTCOME_TIER  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "docs" / "lab" / "data"
SPOTIFY_MATCH = ROOT / "data" / "raw" / "state" / "spotify_match.json"
XREF_FILE = ROOT / "data" / "raw" / "state" / "artist_xref.json"

SIGNAL_FIELDS = ["team_key", "branch", "source", "program", "stage_rank", "signal_date", "venue"]
TEAM_FIELDS = ["team_key", "display_name", "first_seen", "first_release", "fan_count", "album_count",
               "profile_status", "primary_genre", "agency"]
LINK_FIELDS = ["team_key", "platform", "url"]
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
OUTCOME_FIELDS = ["team_key", "program", "program_label", "tier", "announced_date", "counted"]
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
        "outcomes": """-- lab:outcomes
            SELECT DISTINCT team_key, program, tier, announced_start AS announced_date, counted
            FROM core.v_outcome
            WHERE artist_key IS NOT NULL AND artist_key <> '' AND announced_start IS NOT NULL
            ORDER BY team_key, announced_date""",
    }


def _records(text: str) -> List[dict]:
    return list(csv.DictReader(io.StringIO(text)))


def team_rows(rows: List[dict]) -> List[dict]:
    """도우미 열(raw_genres 등)로 대표 장르를 정하고, 프로필 없는 팀은 unknown으로."""
    out = []
    for r in rows:
        genres = _infer_genres(r.get("raw_genres"), r.get("press_sources"), r.get("sel_programs"))
        row = {k: r.get(k) or "" for k in TEAM_FIELDS}
        row["profile_status"] = row["profile_status"] or "unknown"
        row["primary_genre"] = genres[0] if genres else ""
        out.append(row)
    return out


def outcome_rows(rows: List[dict]) -> List[dict]:
    return [{**{k: r.get(k) or "" for k in OUTCOME_FIELDS},
             "program_label": PROGRAM_NAMES.get(r["program"], r["program"]),
             "counted": "true" if str(r.get("counted", "")).lower() in ("t", "true", "1") else "false"}
            for r in rows]


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


def _extra_refs() -> List[dict]:
    """PostgreSQL 밖의 연결: 스포티파이 이름 매칭, 연결표의 인스타 계정. 파일이 없으면 빈 목록."""
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
    return refs


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
           extra_refs: Callable[[], List[dict]] | None = _extra_refs) -> dict:
    use_xref = _has_xref_table(run)
    q = queries(use_xref)
    signals = _records(run(q["signals"]))
    teams = team_rows(_records(run(q["teams"])))
    outcomes = outcome_rows(_records(run(q["outcomes"])))
    programs = program_rows(signals, outcomes)
    links = link_rows(_records(run(q["links"])) + (extra_refs() if extra_refs else []))

    out_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(out_dir / "signals.csv", SIGNAL_FIELDS, signals)
    _write_csv(out_dir / "teams.csv", TEAM_FIELDS, teams)
    _write_csv(out_dir / "outcomes.csv", OUTCOME_FIELDS, outcomes)
    _write_csv(out_dir / "programs.csv", ["program", "label", "kind"], programs)
    _write_csv(out_dir / "links.csv", LINK_FIELDS, links)
    meta = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "data_end": today or date.today().isoformat(),
        "uses_artist_xref": use_xref,
        "rows": {"signals": len(signals), "teams": len(teams), "outcomes": len(outcomes),
                 "programs": len(programs), "links": len(links)},
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
