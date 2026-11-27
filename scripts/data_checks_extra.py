"""매일 데이터 검사 — 2026-11-28에 생긴 데이터 쪽 (scripts/data_checks.py 에서 나눔, 출력은 같은 점검표에 이어서).

본인 음반 첫 발매(PostgreSQL)·공연장 좌표·체급 보유율·공연장 목록 짝·앱 보조 데이터 8개·알림 날짜·중복·팀 표 새 칸 분포.
data_checks.run_all / pg_checks 가 이 모듈을 불러 쓴다 (이 모듈은 data_checks 의 Check·도우미를 쓴다).
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path
from typing import Callable, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))
from data_checks import (GIG_FUTURE_MAX_DAYS, Check, _days, _examples, _level, _pct,  # noqa: E402
                         _read_json, _rows)

# ---------- 기준값 ----------
OWN_RELEASE_WARN = 0.50      # 멜론 프로필 중 본인 음반 첫 발매 보유율이 50% 밑이면 경고 (2026-11-28 수집 시작, 7일마다 다시 받으며 채워짐)
OWN_RELEASE_GAP_DAYS = 365 * 3   # 본인 음반 첫 발매가 전체 첫 발매보다 3년 넘게 늦으면 '크게 다름' (참여·소속 음반이 앞당긴 팀)
VENUE_GEO_WARN, VENUE_GEO_FAIL = 0.85, 0.60     # 공연 밤 기준 공연장 좌표 보유율
VENUE_TIER_WARN, VENUE_TIER_FAIL = 0.70, 0.40   # 공연 밤 기준 공연장 체급 보유율
VENUE_MASTER_WARN = 0.10     # 공연장 목록(config/venues_kr.json)과 짝 못 찾은 공연 밤 비율
UNKNOWN_VENUES = {"공연장 미정"}   # 공연장을 모르는 자리표시 — 보유율 계산에서 뺀다
EXTRAS = ("city_profiles.json", "event_stars.csv", "festival_profiles.json", "lineup_roles.csv",
          "team_cities.csv", "venue_ladder.json", "venue_profiles.json", "venue_tiers.csv")   # 앱 보조 데이터 8개 (meta.extras)
ALERT_FUTURE_OK = {"new_gig", "new_selection", "big_venue_first", "peer_winner", "blank_first_mention", "stage_up"}
NEWCOMER_CHECKS = {"verified", "unverified", "first_seen"}
GENRE_CONFIDENCES = {"", "profile", "press", "inferred", "inferred_low"}


# ---------- 파일 검사 ----------

def _gig_nights(signals: List[dict]) -> Counter:
    """공연장별 공연 밤 수 (같은 날 같은 공연장은 한 밤, '공연장 미정'·빈칸 제외)."""
    nights = {(s.get("venue"), s.get("signal_date")) for s in signals
              if s.get("branch") == "공연" and s.get("venue") and s.get("venue") not in UNKNOWN_VENUES}
    return Counter(v for v, _ in nights)


def check_venue_coverage(signals: List[dict], profiles: Dict[str, dict]) -> Check:
    name = "공연장 좌표·체급 보유율 (공연 밤 기준)"
    rule = (f"좌표 {int(VENUE_GEO_WARN * 100)}% 밑 경고·{int(VENUE_GEO_FAIL * 100)}% 밑 실패, "
            f"체급 {int(VENUE_TIER_WARN * 100)}% 밑 경고·{int(VENUE_TIER_FAIL * 100)}% 밑 실패 ('공연장 미정' 제외)")
    fix = "공연 많은 공연장부터 config/venue_capacity.json(체급)·좌표 캐시를 채운다 — 아래 값의 '빠진 곳'부터"
    nights = _gig_nights(signals)
    total = sum(nights.values())
    if not total:
        return Check("venue_coverage", name, rule, "공연 기록 없음", "skip", fix)
    geo = sum(n for v, n in nights.items() if (profiles.get(v) or {}).get("lat") is not None)
    tier = sum(n for v, n in nights.items() if (profiles.get(v) or {}).get("tier"))
    worst = max(("pass", "warn", "fail").index(_level(geo / total, VENUE_GEO_WARN, VENUE_GEO_FAIL, False)),
                ("pass", "warn", "fail").index(_level(tier / total, VENUE_TIER_WARN, VENUE_TIER_FAIL, False)))
    no_tier = sorted((v for v in nights if not (profiles.get(v) or {}).get("tier")), key=lambda v: -nights[v])
    value = (f"좌표 {geo:,}/{total:,} ({_pct(geo, total)}) · 체급 {tier:,}/{total:,} ({_pct(tier, total)})"
             + (" — 체급 빠진 곳(밤 많은 순): " + _examples(f"{v} {nights[v]}" for v in no_tier) if no_tier else ""))
    return Check("venue_coverage", name, rule, value, ("pass", "warn", "fail")[worst], fix)


def check_venue_master(signals: List[dict], match: Callable[[List[str]], dict]) -> Check:
    name = "공연장 목록(venues_kr) 짝 못 찾은 곳"
    rule = f"짝 없는 공연장의 공연 밤이 {int(VENUE_MASTER_WARN * 100)}% 넘으면 경고 ('공연장 미정' 제외)"
    fix = "config/venues_kr.json에 공연장(aliases 포함)을 추가하거나, 인스타 계정명(@…)이면 공연장 연결표에 대표 이름으로 묶는다"
    nights = _gig_nights(signals)
    total = sum(nights.values())
    if not total:
        return Check("venue_master", name, rule, "공연 기록 없음", "skip", fix)
    found = match(sorted(nights))
    missing = sorted((v for v in nights if v not in found), key=lambda v: (-nights[v], v))
    lost = sum(nights[v] for v in missing)
    value = f"{len(missing)}곳 · 공연 밤 {lost:,}/{total:,} ({_pct(lost, total)})"
    if missing:
        value += " — " + _examples(f"{v} {nights[v]}" for v in missing)
    return Check("venue_master", name, rule, value, "warn" if lost / total > VENUE_MASTER_WARN else "pass", fix)


def check_extras(meta: dict, lab_dir: Path) -> Check:
    name = f"앱 보조 데이터 {len(EXTRAS)}개"
    rule = "meta.json extras 목록에 다 있고, 파일이 있고 비어 있지 않아야 함 — 하나라도 빠지면 실패"
    fix = "daily_run.sh의 앱 보조 데이터 묶음(build_app_extras.sh)이 실패했는지 records/daily_run.log 확인 후 다시 돌린다"
    listed = {str(x).split(".")[0] for x in meta.get("extras") or []}
    rows = meta.get("extras_rows") or {}
    problems = []
    for f in EXTRAS:
        path = lab_dir / f
        if f.split(".")[0] not in listed:
            problems.append(f"{f} 목록에 없음")
        elif not path.exists() or path.stat().st_size == 0:
            problems.append(f"{f} 파일 없음·빔")
        elif f in rows and not rows[f]:
            problems.append(f"{f} 0행")
    value = "모두 있음" + (f" (갱신 {str(meta.get('extras_updated_at', ''))[:16].replace('T', ' ')})"
                         if meta.get("extras_updated_at") else "") if not problems else "; ".join(problems)
    return Check("extras", name, rule, value, "fail" if problems else "pass", fix)


def check_alerts(doc: dict) -> Check:
    name = "알림 날짜·중복"
    rule = (f"공연·선정 기반 알림 말고는 미래 날짜면 경고, 어떤 알림도 {GIG_FUTURE_MAX_DAYS}일 넘게 뒤면 경고, "
            "같은 종류·팀·날짜가 두 번이면 경고")
    fix = ("미래 날짜는 build_alerts.py의 날짜 고르기, 중복은 공연장 표기 차이('대구 제임스레코드'/'제임스레코드' 등)를 "
           "config/venue_aliases.json에 묶는다")
    alerts = (doc or {}).get("alerts")
    if not alerts:
        return Check("alerts", name, rule, "알림 파일 없음", "skip", fix)
    as_of = str(doc.get("as_of") or "")[:10]
    odd = Counter(a.get("type") for a in alerts if as_of and str(a.get("date", "")) > as_of
                  and (a.get("type") not in ALERT_FUTURE_OK or (_days(as_of, a["date"]) or 0) > GIG_FUTURE_MAX_DAYS))
    keys = Counter((a.get("type"), a.get("team_key"), a.get("date")) for a in alerts)
    dups = [k for k, n in keys.items() if n > 1]
    value = f"알림 {len(alerts)}건 · 이상한 미래 날짜 {sum(odd.values())}건 · 중복 {len(dups)}건"
    if odd:
        value += " — 미래: " + ", ".join(f"{t} {n}" for t, n in odd.most_common())
    if dups:
        value += " — 중복: " + _examples(f"{t} {k} {d}" for t, k, d in sorted(dups))
    return Check("alerts", name, rule, value, "warn" if odd or dups else "pass", fix)


def check_team_labels(teams: List[dict]) -> Check:
    name = "팀 표 신인 확인·장르 확신도 분포"
    rule = "newcomer_check·genre_confidence 칸에 정해진 값만 — 모르는 값이 있으면 경고 (분포는 참고)"
    fix = "export_lab_data.py의 newcomer_check·genre_confidence 값 목록과 data_checks.py NEWCOMER_CHECKS·GENRE_CONFIDENCES를 맞춘다"
    nc = Counter(t.get("newcomer_check") or "" for t in teams)
    gc = Counter(t.get("genre_confidence") or "" for t in teams)
    bad = sorted({k for k in nc if k not in NEWCOMER_CHECKS} | {k for k in gc if k not in GENRE_CONFIDENCES})
    fmt = lambda c: " · ".join(f"{k or '(빈칸)'} {n:,}" for k, n in c.most_common())
    value = f"newcomer_check: {fmt(nc)} / genre_confidence: {fmt(gc)}" + (f" — 모르는 값: {', '.join(k or '(빈칸)' for k in bad)}" if bad else "")
    return Check("team_labels", name, rule, value, "warn" if bad else "pass", fix)


def _venue_matcher(root: Path) -> Callable[[List[str]], dict]:
    """우리 공연장 이름 → config/venues_kr.json 짝 (venues_kr.match_our_venues 와 같은 규칙). 목록이 없으면 빈 짝."""
    master = (_read_json(root / "config" / "venues_kr.json").get("venues") or [])
    if not master:
        return lambda names: {}
    import venues_kr
    return lambda names: venues_kr.match_our_venues(master, names)


def extra_checks(root: Path, lab: Path, meta: dict, tables: Dict[str, List[dict]]) -> List[Check]:
    """data_checks.run_all 이 기존 검사 뒤에 붙이는 순서 그대로."""
    venues = (_read_json(lab / "venue_profiles.json").get("venues") or {})
    return [
        check_extras(meta, lab),
        check_team_labels(tables["teams"]),
        check_alerts(_read_json(root / "docs" / "data" / "alerts.json")),
        check_venue_coverage(tables["signals"], venues if isinstance(venues, dict) else {}),
        check_venue_master(tables["signals"], _venue_matcher(root)),
    ]


# ---------- PostgreSQL (읽기만) ----------

OWN_RELEASE_SQL = f"""-- dc:own_release
        WITH latest AS (SELECT DISTINCT ON (artist_source_id) * FROM raw.raw_artist_profile
                        WHERE source = 'melon' ORDER BY artist_source_id, collected_at DESC)
        SELECT count(*) AS n, count(first_release_start) AS has_all, count(first_release_own_start) AS has_own,
               count(*) FILTER (WHERE first_release_own_start - first_release_start > {OWN_RELEASE_GAP_DAYS}) AS diff3y,
               count(*) FILTER (WHERE first_release_own_start < first_release_start) AS own_earlier
        FROM latest"""


def _pg_own_release(text: str) -> Check:
    r = {k: int(v or 0) for k, v in _rows(text)[0].items()}
    ratio = r["has_own"] / max(r["n"], 1)
    value = (f"본인 음반 첫 발매 {r['has_own']}/{r['n']} ({_pct(r['has_own'], r['n'])}) · 전체 첫 발매 {r['has_all']} · "
             f"본인 음반이 {OWN_RELEASE_GAP_DAYS // 365}년 넘게 늦은 프로필 {r['diff3y']}개 · 본인이 더 이른 오류 {r['own_earlier']}개")
    return Check("pg_own_release", "멜론 본인 음반 첫 발매(first_release_own)",
                 f"최신 멜론 프로필 중 보유율 {int(OWN_RELEASE_WARN * 100)}% 밑이면 경고, 본인 음반이 전체보다 이르면(계산 오류) 경고",
                 value, "warn" if ratio < OWN_RELEASE_WARN or r["own_earlier"] else "pass",
                 "collect_artists.py --refresh가 7일마다 다시 받아 채움 — '늦은 프로필'은 참여·소속 음반 때문에 첫 발매가 "
                 "앞당겨졌던 팀(뷰가 본인 음반 기준으로 바로잡음)")


PG_EXTRA = {"pg_own_release": (OWN_RELEASE_SQL, _pg_own_release)}   # data_checks.pg_checks 가 기존 쿼리 뒤에 돌림
