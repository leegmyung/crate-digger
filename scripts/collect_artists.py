"""아티스트 메타데이터 수집기 (멜론 아티스트 페이지) → data/raw/raw_artist_profile_<날짜>_melon.csv

    python3 scripts/collect_artists.py            # 발매 수집에서 새로 본 멜론 아티스트만
    python3 scripts/collect_artists.py --limit 50

- 대상: data/raw/raw_kr_release_*_melon*.csv 의 artist_source_id 중 아직 프로필을 안 받은 아티스트.
  이미 받은 번호는 data/raw/state/artist_profile_seen.json.
- 읽는 것: 데뷔일·데뷔곡, 첫 발매일(앨범 목록의 가장 오래된 날짜 — 데뷔일이 비어 있는 팀이 많아서), 활동유형,
  소속사, 장르, 국적, 팬 수, 앨범 수, 유튜브 채널 주소(3단계 유튜브 지표용).
  1.5단계 신인 판별(첫 발매 2년 이내 & 발매 5개 이하)과 2단계 이름 맞추기(동명 팀 구분)의 기준 자료.
- 멜론은 robots.txt가 막아서 aside 브라우저로 읽는다. 페이지가 뜰 때까지만 기다린다.
- 다른 플랫폼에서만 보인 팀은 2단계 이름 맞추기에서 멜론 번호를 찾은 뒤 이어서 받는다.
- 형식: docs/csv_spec.md / scripts/csv_schema.py raw_artist_profile
"""
import argparse
import csv
import glob
import html
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from collect_gigs import parse_repl_output
from melon_names import ATTEMPTS as ATTEMPTS_STATE  # {이름: 마지막 검색 날짜} — 명단(melon_names.py)과 같은 파일
from melon_names import MATCHES as MATCH_STATE
from melon_names import due_for_search             # 검색할 이름 고르기: 처음 보는 이름 + 못 찾고 RETRY_DAYS 지난 이름
from csv_schema import TABLES
from normalize import artist_key

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
STATE = RAW_DIR / "state" / "artist_profile_seen.json"
KST = timezone(timedelta(hours=9))
COLUMNS = [f.name for f in TABLES["raw_artist_profile"]["fields"]]
ARTIST_URL = "https://www.melon.com/artist/detail.htm?artistId={id}"
ALBUM_URL = "https://www.melon.com/artist/album.htm?artistId={id}"
BATCH = 10
DEFAULT_LIMIT = 200
SAVE_EVERY = 20             # 프로필 이만큼 받을 때마다 저장·상태 갱신 (긴 수집이 끊겨도 받은 만큼 남게)
MAX_PROFILES_PER_RUN = 1000  # 프로필 페이지 읽기 상한 — 사용자 지시(2026-11-27)로 하루 100팀 한도를 없애고 밀린 것을 한 번에 받음
REPL_TIMEOUT_SEC = 300
PAGE_WAIT_MS = 2500

TAG = re.compile(r"<[^>]+>")
DL_LABELS = ["데뷔", "활동년대", "유형", "장르", "소속사명", "소속그룹", "국적", "SNS", "본명", "생일", "멤버",
             "아티스트명", "팬맺기", "YouTube", "페이스북", "트위터", "인스타그램"]
YOUTUBE = re.compile(r"https?://(?:www\.)?youtube\.com/[^\s|,]+")


def clean(text):
    return re.sub(r"\s+", " ", html.unescape(TAG.sub(" ", text or ""))).strip()


def _date(text):
    m = re.search(r"(\d{4})(?:[.\-](\d{2}))?(?:[.\-](\d{2}))?", text or "")
    return "-".join(p for p in m.groups() if p) if m else ""


def _after(label, texts, stops):
    """'장르 인디음악, 발라드 소속사명 …' 같은 상세 칸에서 label 다음 값을 꺼낸다.
    칸(dl)마다 따로 보고, '음악장르'처럼 다른 낱말 안의 label은 무시한다 (멤버 목록이 섞이지 않게)."""
    pattern = re.compile(rf"(?<![가-힣]){label}\s+(.*?)(?=\s+(?:{'|'.join(stops)})(?:\s|$)|$)")
    for text in texts:
        m = pattern.search(text or "")
        if m:
            return m.group(1).strip()
    return ""


def parse_melon_artist(page):
    page = page or {}
    info, dl = page.get("info", ""), page.get("dl", []) or []
    pairs = {clean(k): v for k, v in re.findall(r"<dt>(.*?)</dt>\s*<dd[^>]*>(.*?)</dd>", info, re.S)}
    name = re.search(r'class="title_atist">(?:<strong[^>]*>.*?</strong>)?(.*?)</p>', info, re.S)
    debut = re.search(r'class="songname12">(.*?)</span>', pairs.get("데뷔", ""), re.S)
    genre = _after("장르", dl, DL_LABELS)
    albums = re.search(r"앨범\s*\(\s*(\d+)\s*\)", page.get("albums", "") or "")
    return {
        "artist_text": clean(name.group(1)) if name else "",
        "debut_date": _date(clean(pairs.get("데뷔", ""))),
        "debut_title": clean(debut.group(1)) if debut else "",
        "activity_type": clean(pairs.get("활동유형", "")),
        "agency_text": clean(pairs.get("소속사", "")) or _after("소속사명", dl, DL_LABELS),
        "genre": "|".join(g.strip() for g in genre.split(",") if g.strip()),
        "nationality": (_after("국적", dl, DL_LABELS).split() or [""])[0],
        "fan_count": re.sub(r"\D", "", page.get("fan", "") or ""),
        "album_count": albums.group(1) if albums else "",
        "first_release_date": min((d for d in map(_date, page.get("album_dates") or []) if d), default=""),
        "youtube_url": next((m.group(0) for t in dl if (m := YOUTUBE.search(t))), ""),
    }


def name_keys(name):
    """이름 키 + 끝 괄호 속 별칭 키. '피치트럭 하이재커스(Peach Truck Hijackers)' → 한글·영문 둘 다."""
    keys = {artist_key(name)}
    m = re.search(r"[\(\[]([^\)\]]+)[\)\]]\s*$", name or "")
    if m:
        keys.add(artist_key(m.group(1)))
    return {k for k in keys if k}


INVALID_IDS = {"0", "1"}   # 멜론 공용 번호('여러 아티스트' 등) — 실제 팀이 아님
MIN_MELON_ID = 1_000       # 이보다 작은 번호는 실제 아티스트 번호가 아님 (이름 속 숫자를 잘못 읽은 경우: 12BH→12)
_DETAIL_ID = re.compile(r"goArtistDetail\(['\"]?(\d+)")


def valid_melon_id(mid) -> bool:
    s = str(mid or "")
    return s.isdigit() and s not in INVALID_IDS and int(s) >= MIN_MELON_ID


def melon_id_from_href(href: str) -> str:
    """검색 결과 링크에서 아티스트 번호 — goArtistDetail('번호') 안의 숫자만 (앞쪽 searchLog 의 이름 속 숫자 무시)."""
    m = _DETAIL_ID.search(href or "")
    return m.group(1) if m and valid_melon_id(m.group(1)) else ""


def match_candidate(name, candidates):
    """멜론 검색 결과 [[번호, 이름, 설명], ...] 중 이름 키가 같은 후보. 같은 키가 여럿이면 namesakes>1 (검수 대상)."""
    want = name_keys(name)
    hits = [c for c in candidates if valid_melon_id(c[0]) and name_keys(c[1]) & want]
    if not hits:
        return None
    return {"id": hits[0][0], "name": hits[0][1], "desc": hits[0][2] if len(hits[0]) > 2 else "", "namesakes": len(hits)}


def targets(release_rows, seen):
    ids = [r.get("artist_source_id", "") for r in release_rows if r.get("source") == "melon"]
    return [i for i in dict.fromkeys(ids) if i and i not in seen]


def to_row(artist_id, profile, collected_at):
    if not profile.get("artist_text"):
        return None
    return dict(profile, collected_at=collected_at, source="melon", collector="aside", artist_source_id=artist_id,
                url=ARTIST_URL.format(id=artist_id), artist_key=artist_key(profile["artist_text"]))


def write_csv(rows, out_dir, day):
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"raw_artist_profile_{day}_melon.csv"
    if path.exists():  # 원본은 고치지 않는다
        path = out_dir / f"raw_artist_profile_{day}_melon_{datetime.now(KST):%H%M%S}.csv"
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _js(ids):
    return f"""await (async () => {{
  const out = {{}};
  for (const id of {json.dumps(ids)}) {{
    try {{
      let t = await openTab({json.dumps(ARTIST_URL)}.replace('{{id}}', id)); await sleep({PAGE_WAIT_MS});
      const p = await t.evaluate(() => ({{
        info: document.querySelector('.wrap_atist_info')?.outerHTML || '',
        fan: document.querySelector('#d_like_count')?.innerText || '',
        dl: [...document.querySelectorAll('dl')].map(d => d.innerText.replace(/\\s+/g, ' ')).slice(0, 12)
      }}));
      await closeTab(t);
      t = await openTab({json.dumps(ALBUM_URL)}.replace('{{id}}', id)); await sleep({PAGE_WAIT_MS});
      p.albums = (await t.evaluate(() => (document.body.innerText.match(/앨범\\s*\\(\\s*\\d+\\s*\\)/) || [''])[0]));
      const dates = () => t.evaluate(() => [...document.querySelectorAll('.cnt_view')].map(e => e.innerText.trim()));
      p.album_dates = await dates();
      const more = await t.evaluate(() => {{ const b = document.querySelector('.paginate a.btn_last'); if (b && !b.classList.contains('disabled')) {{ b.click(); return true; }} return false; }});
      if (more) {{ await sleep({PAGE_WAIT_MS}); p.album_dates = p.album_dates.concat(await dates()); }}
      await closeTab(t);
      out[id] = p;
    }} catch (e) {{ out[id] = {{}}; }}
  }}
  console.log('RESULT ' + JSON.stringify(out));
}})();"""


SEARCH_URL = "https://www.melon.com/search/artist/index.htm?q="


def _search_js(names):
    return f"""await (async () => {{
  const out = {{}};
  for (const n of {json.dumps(names, ensure_ascii=False)}) {{
    try {{
      const t = await openTab({json.dumps(SEARCH_URL)} + encodeURIComponent(n)); await sleep({PAGE_WAIT_MS});
      out[n] = await t.evaluate(() => {{
        const seen = new Set(); const res = [];
        for (const a of document.querySelectorAll('a[href*="goArtistDetail"]')) {{
          const mm = (a.getAttribute('href') || '').match(/goArtistDetail\\(['"]?(\\d+)/); const id = mm && Number(mm[1]) >= {MIN_MELON_ID} ? mm[1] : ''; const name = a.innerText.trim();
          if (!id || !name || seen.has(id)) continue; seen.add(id);
          const box = a.closest('li, div'); res.push([id, name, box ? box.innerText.replace(/\\s+/g, ' ').slice(0, 160) : '']);
        }}
        return res.slice(0, 8);
      }});
      await closeTab(t);
    }} catch (e) {{ out[n] = []; }}
  }}
  console.log('RESULT ' + JSON.stringify(out));
}})();"""


def _run_batch(js):
    proc = subprocess.run(["aside", "repl", "--json", js], capture_output=True, text=True, timeout=REPL_TIMEOUT_SEC)
    return parse_repl_output(proc.stdout)


def search_artists(names):
    """→ (검색 결과, 실패한 이름). 묶음 하나가 실패해도(aside가 바쁠 때 등) 나머지는 계속한다."""
    out, failed = {}, []
    for i in range(0, len(names), BATCH):
        batch = names[i:i + BATCH]
        try:
            out.update(_run_batch(_search_js(batch)))
        except (RuntimeError, subprocess.TimeoutExpired) as e:
            failed.extend(batch)
            print(f"  ⚠️ 검색 묶음 실패 ({len(batch)}팀, 다음 실행 때 다시): {str(e)[:80]}", file=sys.stderr)
    return out, failed


def fetch_profiles(ids):
    out = {}
    for i in range(0, len(ids), BATCH):
        try:
            out.update(_run_batch(_js(ids[i:i + BATCH])))
        except (RuntimeError, subprocess.TimeoutExpired) as e:   # 못 받은 팀은 seen에 안 들어가 다음에 다시
            print(f"  ⚠️ 프로필 묶음 실패: {str(e)[:80]}", file=sys.stderr)
    return out


def _release_rows():
    rows = []
    for f in sorted(glob.glob(str(RAW_DIR / "raw_kr_release_*_melon*.csv"))):
        with open(f, encoding="utf-8") as fh:
            rows.extend(csv.DictReader(fh))
    return rows


def collect(limit):
    try:
        seen = json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        seen = []
    ids = targets(_release_rows(), set(seen))[:limit]
    if not ids:
        return None, 0, 0
    now = datetime.now(KST).replace(microsecond=0)
    pages = fetch_profiles(ids)
    rows = [r for r in (to_row(i, parse_melon_artist(pages.get(i, {})), now.isoformat()) for i in ids) if r]
    path = write_csv(rows, RAW_DIR, f"{now:%Y-%m-%d}") if rows else None
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(seen + [r["artist_source_id"] for r in rows]), encoding="utf-8")  # 못 읽은 팀은 다음에 다시
    return path, len(ids), len(rows)


def _load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def collect_from_outcomes(limit, names=None, today=None):
    """팀 이름 목록 → 멜론 검색으로 번호 찾기 → 프로필. names가 없으면 정답(raw_outcome) 팀 (백테스트용).
    후보 팀의 유명도(팬 수·연차) 판별에도 쓴다 (--names-file).
    짝 맞춘 결과(동명 팀 수 포함)는 data/raw/state/outcome_melon_match.json 에 남겨 2단계 검수에서 확인한다.
    검색할 때마다 data/raw/state/melon_match_attempts.json 에 {이름: 마지막 시도 날짜}를 남기고, 못 찾은 이름(null)은
    melon_names.RETRY_DAYS(30일) 지나면 다시 검색한다 (멜론에 새로 등록됐을 수 있음). 검색 자체가 실패하면 시도로 안 침."""
    if names is None:
        names = []
        for f in sorted(glob.glob(str(RAW_DIR / "raw_outcome_*.csv"))):
            with open(f, encoding="utf-8") as fh:
                names.extend(r["artist_text"] for r in csv.DictReader(fh))
    today = today or f"{datetime.now(KST):%Y-%m-%d}"
    matches = _load_json(MATCH_STATE, {})
    attempts = _load_json(ATTEMPTS_STATE, {})
    for n, m in matches.items():          # 날짜 기록 전의 '못 찾음'은 오늘로만 적고 30일 뒤부터 재시도 (한꺼번에 몰리지 않게)
        if m is None and n not in attempts:
            attempts[n] = today
    todo = [n for n in dict.fromkeys(names) if n and due_for_search(n, matches, attempts, today)][:limit]
    # 1차: 괄호 앞 이름으로, 2차: 못 찾은 팀은 괄호 속 별칭으로 검색 ('피치트럭 하이재커스(Peach Truck Hijackers)')
    first = {n: re.sub(r"\s*[\(\[][^\)\]]*[\)\]]\s*$", "", n) or n for n in todo}
    found, failed = search_artists(sorted(set(first.values()))) if todo else ({}, [])
    failed = set(failed)
    for n in todo:
        if first[n] not in failed:               # 검색이 실패한 이름은 '못 찾음'으로 남기지 않음 → 다음에 다시
            matches[n] = match_candidate(n, found.get(first[n], []))
            attempts[n] = today
    alias = {n: m.group(1) for n in todo if n in matches and not matches[n]
             and (m := re.search(r"[\(\[]([^\)\]]+)[\)\]]\s*$", n))}
    found2, failed2 = search_artists(sorted(set(alias.values()))) if alias else ({}, [])
    for n, a in alias.items():
        if a not in failed2:
            matches[n] = match_candidate(n, found2.get(a, []))
    MATCH_STATE.parent.mkdir(parents=True, exist_ok=True)
    MATCH_STATE.write_text(json.dumps(matches, ensure_ascii=False, indent=1), encoding="utf-8")
    ATTEMPTS_STATE.write_text(json.dumps(attempts, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    try:
        seen = set(json.loads(STATE.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        seen = set()
    listed = [matches.get(n) for n in dict.fromkeys(names)]     # 명단 순서가 먼저 (0순위 = 후보 점검 b 팀)
    ids = [m["id"] for m in [*listed, *matches.values()] if m and m["id"] not in seen and valid_melon_id(m["id"])]
    ids = list(dict.fromkeys(ids))[:MAX_PROFILES_PER_RUN]   # 한 번 실행이 너무 길어지지 않게 (남은 팀은 다음 실행에)
    if not ids:
        return None, len(todo), 0
    path, total = None, 0
    for k in range(0, len(ids), SAVE_EVERY):
        chunk = ids[k:k + SAVE_EVERY]
        now = datetime.now(KST).replace(microsecond=0)
        pages = fetch_profiles(chunk)
        rows = [r for r in (to_row(i, parse_melon_artist(pages.get(i, {})), now.isoformat()) for i in chunk) if r]
        if rows:
            path = write_csv(rows, RAW_DIR, f"{now:%Y-%m-%d}")
            seen |= {r["artist_source_id"] for r in rows}
            STATE.write_text(json.dumps(sorted(seen)), encoding="utf-8")
            total += len(rows)
    return path, len(todo), total


def main(argv):
    ap = argparse.ArgumentParser(description="멜론 아티스트 메타데이터 수집 (aside 브라우저)")
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    ap.add_argument("--from-outcomes", action="store_true", help="정답 명단 팀을 멜론에서 찾아 프로필 받기 (백테스트용)")
    ap.add_argument("--names-file", help="한 줄에 팀 이름 하나 — 멜론에서 찾아 프로필 받기 (후보 팀 유명도 판별용)")
    args = ap.parse_args(argv)
    try:
        if args.names_file:
            names = [n.strip() for n in Path(args.names_file).read_text(encoding="utf-8").splitlines() if n.strip()]
            path, n_ids, n_rows = collect_from_outcomes(args.limit, names)
        else:
            path, n_ids, n_rows = (collect_from_outcomes if args.from_outcomes else collect)(args.limit)
    except (RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        print(f"⚠️ 아티스트 프로필 수집 실패: {e}")
        return 1
    print(f"✅ 아티스트 프로필: 대상 {n_ids}명 → {n_rows}행" + (f" → {path}" if path else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
