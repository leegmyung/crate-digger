"""1.5단계 신인 판별 → data/raw/derived/newcomer_<기준일>.csv

    python3 scripts/newcomer.py                     # 기준일 = 오늘 (한국 시간)
    python3 scripts/newcomer.py --as-of 2025-01-01  # 백테스트용 기준일

신인 규칙 (PROJECT.md 5장): 첫 발매 2년 이내 & 발매 5개 이하, 또는 발매 없이 공연(·선정)만 있는 팀.
백테스트 결과에 따라 바뀔 수 있어 기준값은 MAX_YEARS / MAX_ALBUMS 상수와 함수 인자로 둔다.

- 대상: 후보 테이블(발매·공연·선정·매체) 어디든 나온 팀 전부. normalize.artist_key로 묶는다.
- 기준 자료: 멜론 아티스트 프로필(raw_artist_profile). 멜론 발매 행의 아티스트 번호로 먼저 찾고,
  없으면 이름 키(끝 괄호 별칭 포함)로 찾는다.
- 첫 발매일 = debut_date·first_release_date 중 더 이른 날. 연·월만 있으면 그 기간의 첫날로 읽는다
  (timing.outcome_date — 연차를 길게 보는 쪽이라 '신인'을 부풀리지 않는다).
- 프로필이 없으면 우리가 모은 발매 기록 중 가장 이른 발매일을 '약한 추정'으로 쓴다. 우리 수집 기간이 짧아서
  최근 발매만 보이므로 신인이라고 단정하지 않고 unknown. 다만 2년보다 오래된 발매가 있거나
  발매가 기준보다 많으면 '적어도 그만큼'이라는 증거라 established.
- 한계: album_count는 '수집한 날' 값이라 과거 기준일로 돌리면 실제보다 많을 수 있다.
"""
import argparse
import csv
import glob
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from collect_artists import name_keys
from normalize import artist_key, title_key
from timing import outcome_date

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
KST = timezone(timedelta(hours=9))

MAX_YEARS = 3       # 첫 발매 후 몇 년까지 신인 (2026-11-26 백테스트 근거로 2→3, 사용자 결정)
MAX_ALBUMS = 10     # 발매(앨범·싱글 포함) 몇 개까지 신인 (5→10: 멜론 앨범 수엔 싱글이 다 들어감)
# 이미 다 아는 팀(인디로 시작한 혁오·잔나비 등)은 후보에서 뺀다 (2026-11-27 사용자 지시)
FAME_FANS = 10000   # 멜론 팬 이 수 이상이면 '유명(제외)'
FAME_YEARS = 5      # 첫 발매 후 이 해 수를 넘고
FAME_YEARS_MIN_FANS = 1000   # 팬도 이만큼 이상이면 '유명(제외)'. 팬이 적으면 동명의 옛 팀일 수 있어 빼지 않음
DAYS_PER_YEAR = 365.25

TABLES = {          # 후보 테이블 이름 → 파일 패턴
    "release": "raw_kr_release_*.csv",
    "gig": "raw_kr_gig_*.csv",
    "selection": "raw_kr_selection_*.csv",
    "press": "raw_press_*.csv",
}
PROFILE_PATTERN = "raw_artist_profile_*.csv"
STATUSES = ("newcomer", "established", "unknown")
OUT_COLUMNS = ["artist_key", "artist_text", "status", "reason", "years_since_first", "albums", "sources"]
REASON_NO_RELEASE = "발매 기록 없음·공연/선정만"
ACTIVITY_DATE = {"gig": "gig_date", "selection": "announced_at"}   # 발매 없는 팀의 활동 연차 근거


def _rows(raw_dir, pattern):
    out = []
    for f in sorted(glob.glob(str(Path(raw_dir) / pattern))):
        with open(f, encoding="utf-8-sig") as fh:
            out.extend(csv.DictReader(fh))
    return out


def _years(first_iso, as_of):
    """첫 발매일부터 기준일까지 몇 년. 기준일 뒤에 첫 발매면 0."""
    days = (date.fromisoformat(as_of) - date.fromisoformat(first_iso)).days
    return max(days, 0) / DAYS_PER_YEAR


def _int_or_none(text):
    text = (text or "").strip()
    return int(text) if text.isdigit() else None


def _decide(years, albums, max_years, max_albums):
    """(status, 이유 조각). years·albums가 None이면 그 기준은 모름."""
    if years is not None and years > max_years:
        return "established", f"첫 발매 {years:.1f}년 전 (> {max_years}년)"
    if albums is not None and albums > max_albums:
        return "established", f"앨범 {albums}개 (> {max_albums}개)"
    if years is None and albums is None:
        return "unknown", "첫 발매일·앨범 수 모름"
    if years is None:
        return "unknown", f"첫 발매일 모름 (앨범 {albums}개)"
    if albums is None:
        return "unknown", f"첫 발매 {years:.1f}년 전, 앨범 수 모름"
    return "newcomer", f"첫 발매 {years:.1f}년 전 & 앨범 {albums}개"


def _result(status, reason, years, albums):
    return {"status": status, "reason": reason,
            "years_since_first": round(years, 1) if years is not None else None, "albums": albums}


def judge(profile_row, as_of, max_years=MAX_YEARS, max_albums=MAX_ALBUMS):
    """멜론 프로필 1행 → {status, reason, years_since_first, albums}."""
    dates = [outcome_date(profile_row.get(c) or "") for c in ("debut_date", "first_release_date")]
    dates = [d for d in dates if d]
    years = _years(min(dates), as_of) if dates else None
    albums = _int_or_none(profile_row.get("album_count"))
    fans = _int_or_none(profile_row.get("fan_count"))
    if fans is not None and fans >= FAME_FANS:
        return _result("famous", f"멜론 프로필: 팬 {fans:,}명 (유명 팀 기준 {FAME_FANS:,}명 이상)", years, albums)
    if years is not None and years > FAME_YEARS and fans is not None and fans >= FAME_YEARS_MIN_FANS:
        return _result("famous", f"멜론 프로필: 첫 발매 후 {years}년·팬 {fans:,}명 (유명 팀 기준 {FAME_YEARS}년 초과 & 팬 {FAME_YEARS_MIN_FANS:,}명 이상)", years, albums)
    status, why = _decide(years, albums, max_years, max_albums)
    return _result(status, f"멜론 프로필: {why}", years, albums)


def judge_from_releases(release_rows, as_of, max_years=MAX_YEARS, max_albums=MAX_ALBUMS):
    """프로필 없는 팀: 우리가 모은 발매 기록으로 약하게 추정. 신인은 단정하지 않는다."""
    dated = [(outcome_date(r.get("released_at") or ""), r) for r in release_rows]
    dated = [(d, r) for d, r in dated if d and d <= as_of]
    if not dated:
        return None
    years = _years(min(d for d, _ in dated), as_of)
    albums = len({r.get("title_key") or title_key(r.get("title", "")) or r.get("release_url", "") for _, r in dated})
    status, why = _decide(years, albums, max_years, max_albums)
    if status != "established":
        status = "unknown"
    return _result(status, f"프로필 없음, 우리 발매 기록으로 약한 추정: {why} — 프로필 필요", years, albums)


def _latest_profiles(profiles):
    """같은 (source, 번호)를 여러 번 받았으면 가장 최근 수집만."""
    latest = {}
    for p in sorted(profiles, key=lambda p: p.get("collected_at", "")):
        latest[(p.get("source", ""), p.get("artist_source_id", ""))] = p
    return list(latest.values())


def _gather(raw_dir):
    """artist_key → {texts, sources, releases, melon_ids}."""
    artists = defaultdict(lambda: {"texts": [], "sources": [], "releases": [], "melon_ids": [], "activity": []})
    for table, pattern in TABLES.items():
        for r in _rows(raw_dir, pattern):
            key = r.get("artist_key") or artist_key(r.get("artist_text", ""))
            if not key:
                continue
            a = artists[key]
            a["texts"].append(r.get("artist_text", ""))
            if table not in a["sources"]:
                a["sources"].append(table)
            if table in ACTIVITY_DATE:
                a["activity"].append(r.get(ACTIVITY_DATE[table]) or "")
            if table == "release":
                a["releases"].append(r)
                if r.get("source") == "melon" and r.get("artist_source_id"):
                    a["melon_ids"].append(r["artist_source_id"])
    return artists


def judge_without_release(activity_dates, as_of, max_years=MAX_YEARS):
    """발매 기록도 프로필도 없고 공연·선정만 있는 팀. 첫 활동이 기준보다 오래됐으면 신인이 아니다
    (예: 20년 전 유재하 본선 팀 — 발매가 안 보이는 건 우리 발매 수집이 최근 것뿐이라서)."""
    dates = [d for d in (outcome_date(t) for t in activity_dates) if d and d <= as_of]
    years = _years(min(dates), as_of) if dates else None
    if years is not None and years > max_years:
        return _result("established", f"발매 기록 없음, 첫 활동(공연·선정) {years:.1f}년 전 (> {max_years}년)", years, None)
    return _result("newcomer", REASON_NO_RELEASE, years, None)


def _find_profile(key, info, by_id, by_key):
    for mid in info["melon_ids"]:
        if mid in by_id:
            return by_id[mid], ""
    hits = by_key.get(key, [])
    note = f" (이름이 같은 프로필 {len(hits)}개 — 검수 필요)" if len(hits) > 1 else ""
    return (hits[0], note) if hits else (None, "")


def judge_all(raw_dir, as_of, max_years=MAX_YEARS, max_albums=MAX_ALBUMS):
    """후보 테이블에 나온 모든 팀의 신인 판별 행 목록 (artist_key 순)."""
    melon = [p for p in _latest_profiles(_rows(raw_dir, PROFILE_PATTERN)) if p.get("source") == "melon"]
    by_id = {p["artist_source_id"]: p for p in melon if p.get("artist_source_id")}
    by_key = defaultdict(list)
    for p in melon:
        for k in name_keys(p.get("artist_text", "")) | ({p["artist_key"]} if p.get("artist_key") else set()):
            by_key[k].append(p)

    out = []
    for key, info in sorted(_gather(raw_dir).items()):
        profile, note = _find_profile(key, info, by_id, by_key)
        if profile:
            res = judge(profile, as_of, max_years, max_albums)
            res["reason"] += note
            text = profile.get("artist_text") or info["texts"][0]
        else:
            res = judge_from_releases(info["releases"], as_of, max_years, max_albums)
            if res is None and ({"gig", "selection"} & set(info["sources"])):
                res = judge_without_release(info["activity"], as_of, max_years)
            elif res is None:
                res = _result("unknown", "발매·공연·선정 기록 없음·매체 언급만", None, None)
            text = info["texts"][0]
        out.append(dict(res, artist_key=key, artist_text=text, sources="|".join(info["sources"])))
    return out


def counts(rows):
    """(상태별 수, 테이블별 {상태: 수})."""
    by_status = Counter(r["status"] for r in rows)
    by_table = defaultdict(Counter)
    for r in rows:
        for t in r["sources"].split("|"):
            by_table[t][r["status"]] += 1
    return by_status, by_table


def write_csv(rows, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=OUT_COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({c: "" if r.get(c) is None else r.get(c) for c in OUT_COLUMNS})


def _valid_date(text):
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        raise argparse.ArgumentTypeError(f"날짜는 YYYY-MM-DD 형식이어야 해요: {text}")


def main(argv):
    ap = argparse.ArgumentParser(description="1.5단계 신인 판별")
    ap.add_argument("--as-of", type=_valid_date, default=datetime.now(KST).date().isoformat())
    args = ap.parse_args(argv)
    rows = judge_all(RAW_DIR, args.as_of)
    out = RAW_DIR / "derived" / f"newcomer_{args.as_of}.csv"
    write_csv(rows, out)
    by_status, by_table = counts(rows)
    print(f"기준일 {args.as_of} · 팀 {len(rows)}")
    print("상태별: " + " · ".join(f"{s} {by_status.get(s, 0)}" for s in STATUSES))
    for t in TABLES:
        c = by_table.get(t, Counter())
        print(f"  {t:<9} 팀 {sum(c.values()):>4} — " + " · ".join(f"{s} {c.get(s, 0)}" for s in STATUSES))
    print(f"→ {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
