"""인디스트릿 지난 공연 채우기 → data/raw/raw_kr_gig_<오늘>_indistreet_history.csv

    .venv/bin/python scripts/collect_gigs_history.py --since 2024-01-01            # 어제까지
    .venv/bin/python scripts/collect_gigs_history.py --since 2024-01-01 --until 2024-06-30 --max-weeks 20

길: 주간 목록(indistreet.com/weekly?week=-N, 이번 주=0)을 한 주씩 거꾸로 열어 공연 주소를 모으고,
공연 상세의 구조화 데이터(JSON-LD MusicEvent)를 같은 탭 안에서 fetch로 읽는다 (탭을 매번 새로 열지 않아 빠름).
주간 목록에 섞여 나오는 기획공연(/programs/ 페스티벌) 페이지는 탭으로 열어 라인업(날짜별 출연 팀)을 읽는다.
페스티벌 행은 제목 앞에 [페스티벌], 주소 뒤에 #날짜를 붙인다.

인디스트릿 robots.txt가 봇을 일부 막아서 aside 브라우저(aside repl)로만 읽는다.
끊겨도 data/raw/state/gigs_history_seen.json 에 끝난 주·공연·기획공연이 남아 다음 실행이 이어 간다.
형식은 매일 수집기(collect_gigs.py)와 같다. 단 시작 시각은 한국 시간으로 바꿔 적는다
(사이트 JSON-LD 시각이 UTC(Z)라서).
"""
import argparse
import csv
import json
import re
import subprocess
import sys
import time
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from collect_gigs import COLUMNS, KST, _source_id, parse_repl_output, to_rows

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://indistreet.com"
SITE = "indistreet"
STATE_PATH = ROOT / "data" / "raw" / "state" / "gigs_history_seen.json"
STATE_KEYS = ("weeks_done", "gigs_done", "programs_done")
WEEKS_PER_LIST_CALL = 8
GIGS_PER_DETAIL_CALL = 40
REPL_TIMEOUT_SEC = 180
RETRY_WAIT_SEC = 20
LANG_PREFIX = re.compile(r"^/(?:ko|en|ja|zh-CN|zh-TW)(?=/)")

# 주간 목록 HTML은 서버가 다 그려서 주므로 fetch만으로 공연·기획공연 링크가 다 나온다 (렌더 결과와 개수 같음 확인)
LIST_JS = """
await (async () => {
  const t = await openTab(%(first)s); await sleep(2500);
  const out = await t.evaluate(async (weeks) => {
    const res = [];
    for (const w of weeks) {
      try {
        const html = await (await fetch('/weekly?week=' + w)).text();
        const doc = new DOMParser().parseFromString(html, 'text/html');
        const hrefs = (sel) => [...new Set([...doc.querySelectorAll(sel)].map(a => a.getAttribute('href')))];
        res.push({ week: w, title: doc.title, gigs: hrefs('a[href*="/gigs/"]'), programs: hrefs('a[href*="/programs/"]') });
      } catch (e) { res.push({ week: w, error: String(e) }); }
    }
    return res;
  }, %(weeks)s);
  await closeTab(t);
  console.log('RESULT ' + JSON.stringify(out));
})();
"""

DETAIL_JS = """
await (async () => {
  const t = await openTab('https://indistreet.com/weekly'); await sleep(2500);
  const out = await t.evaluate(async (urls) => {
    const res = [];
    for (const u of urls) {
      try {
        const read = async (url) => {
          const r = await fetch(url); const doc = new DOMParser().parseFromString(await r.text(), 'text/html');
          const lds = [...doc.querySelectorAll('script[type="application/ld+json"]')]
            .map(s => { try { return JSON.parse(s.textContent); } catch (e) { return null; } }).filter(Boolean);
          return { r, doc, ev: lds.flat().find(x => x && x['@type'] === 'MusicEvent') || {} };
        };
        let { r, doc, ev } = await read(u);
        // 제목에 '・' 같은 글자가 든 주소는 사이트가 '찾을 수 없음'을 낸다 → 끝의 공연 번호만으로 다시 연다
        const id = (u.match(/-([a-z0-9]{24})$/) || [])[1];
        if (!ev.startDate && id) ({ r, doc, ev } = await read('/gigs/' + id));
        const loc = ev.location || {};
        const perf = [].concat(ev.performer || []).map(p => ({ name: (p.name || '').trim(), url: p.url || '' }));
        const anchors = [...doc.querySelectorAll('a[href*="/artists/"]')]
          .map(a => ({ name: a.textContent.replace(/\\s+/g, ' ').trim(), url: a.getAttribute('href') })).filter(p => p.name);
        res.push({ url: r.url || u, status: r.status, notFound: !ev.startDate && /찾을 수 없/.test(doc.title), name: ev.name || doc.title, startDate: ev.startDate || '',
                   venue: loc.name || '', address: (loc.address && (loc.address.streetAddress || loc.address.addressLocality)) || '',
                   performers: perf.length ? perf : anchors });
      } catch (e) { res.push({ url: u, error: String(e) }); }
    }
    return res;
  }, %(urls)s);
  await closeTab(t);
  console.log('RESULT ' + JSON.stringify(out));
})();
"""

# 기획공연 라인업은 나중에 채워지는 부분이 있어 fetch로는 일부만 보인다 → 탭으로 열어 다 그려진 뒤 읽는다
PROGRAM_JS = """
await (async () => {
  const out = [];
  for (const u of %(urls)s) {
    let t;
    try {
      t = await openTab(u); await sleep(3500);
      const d = await t.evaluate(async () => {
        const html = await (await fetch(location.href)).text();
        const isos = [...new Set(html.match(/20\\d\\d-\\d\\d-\\d\\d(?=T)/g) || [])];
        const sec = document.querySelector('section[aria-label="라인업"]');
        const blocks = sec ? [...sec.querySelectorAll(':scope > div > div')] : [];
        const days = blocks.map(b => {
          const txt = b.innerText || '';
          const label = (txt.match(/DAY\\s*\\d+/) || [''])[0].replace(/\\s+/g, ' ');
          const md = txt.match(/(\\d{1,2})\\.\\s*(\\d{1,2})\\./);
          let dt = '';
          if (md) {
            const mmdd = String(md[1]).padStart(2, '0') + '-' + String(md[2]).padStart(2, '0');
            dt = isos.find(x => x.slice(5) === mmdd) || ('????-' + mmdd);
          }
          const count = +((txt.match(/(\\d+)\\s*팀/) || [0, 0])[1]);
          const artists = [...b.querySelectorAll('a[href*="/artists/"]')]
            .map(a => ({ name: a.innerText.replace(/\\s+/g, ' ').trim(), url: a.getAttribute('href') })).filter(p => p.name);
          return { label, date: dt, count, artists };
        });
        const h1 = document.querySelector('h1');
        return { url: location.href, title: (h1 && h1.innerText.trim()) || document.title, days };
      });
      out.push(d);
    } catch (e) { out.push({ url: u, error: String(e) }); }
    if (t) await closeTab(t);
  }
  console.log('RESULT ' + JSON.stringify(out));
})();
"""


# ---------- 순수 함수 (테스트 대상) ----------

def _monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def week_offset(day: str, today: str) -> int:
    """day가 속한 주가 이번 주(today가 속한 주)에서 몇 주 전인지. 이번 주=0, 지난주=-1."""
    d, t = date.fromisoformat(day), date.fromisoformat(today)
    return (_monday(d) - _monday(t)).days // 7


def weeks_between(since: str, until: str, today: str) -> list:
    """[(주 번호, 그 주 월요일)] 오래된 주부터."""
    start, end = _monday(date.fromisoformat(since)), _monday(date.fromisoformat(until))
    out, cur = [], start
    while cur <= end:
        out.append((week_offset(cur.isoformat(), today), cur.isoformat()))
        cur += timedelta(days=7)
    return out


def week_fully_inside(monday: str, since: str, until: str) -> bool:
    """그 주 7일이 모두 범위 안이면 True — 경계 주는 '끝난 주'로 적지 않는다."""
    sunday = (date.fromisoformat(monday) + timedelta(days=6)).isoformat()
    return since <= monday and sunday <= until


def to_kst(start: str) -> str:
    """'2024-01-08T11:00:00.000Z' 같은 UTC 시각을 한국 시간 ISO로. 다른 형식은 그대로 둔다."""
    m = re.match(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?)(?:\.\d+)?Z$", start or "")
    if not m:
        return start or ""
    utc = datetime.fromisoformat(m.group(1)).replace(tzinfo=timezone.utc)
    return utc.astimezone(KST).isoformat()


def abs_url(href: str) -> str:
    """상대 주소를 절대 주소로, /ko/ 같은 언어 앞자리는 뗀다 (같은 공연이 두 주소로 갈라지지 않게)."""
    if not href:
        return ""
    parsed = urllib.parse.urlparse(urllib.parse.urljoin(BASE + "/", href))
    path = LANG_PREFIX.sub("", parsed.path)
    return f"{parsed.scheme}://{parsed.netloc}{path}"


def gig_rows(detail: dict, collected_at: str) -> list:
    fixed = dict(detail, url=abs_url(detail["url"]), startDate=to_kst(detail.get("startDate", "")),
                 performers=[dict(p, url=abs_url(p.get("url", ""))) for p in detail.get("performers", [])])
    return to_rows(SITE, fixed, collected_at)


def program_rows(program: dict, collected_at: str, since: str, until: str) -> list:
    """페스티벌 라인업 → 날짜 × 출연 팀 1행. 기간 밖이거나 날짜를 모르는 날은 뺀다."""
    url = abs_url(program["url"])
    slug = _source_id(SITE, url, "programs")
    rows = []
    for day in program.get("days", []):
        d = day.get("date", "")
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", d) or not since <= d <= until:
            continue
        title = f"[페스티벌] {program.get('title', '').strip()} {day.get('label', '')}".strip()
        base = {"collected_at": collected_at, "source": SITE, "collector": "aside", "source_id": f"{slug}#{d}",
                "gig_date": d, "gig_time": "", "title": title, "venue_text": "", "gig_url": f"{url}#{d}"}
        seen = set()
        for p in day.get("artists", []):
            name = (p.get("name") or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            a_url = abs_url(p.get("url") or "")
            rows.append(dict(base, artist_text=name, artist_url=a_url,
                             artist_source_id=_source_id(SITE, a_url, "artists") if a_url else ""))
    return rows


def load_state(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}
    return {k: list(data.get(k, [])) for k in STATE_KEYS}


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=0), encoding="utf-8")
    tmp.replace(path)


def mark(state: dict, key: str, items: list) -> dict:
    """원본은 두고, key 목록에 items를 (중복 없이) 더한 새 상태를 돌려준다."""
    have = set(state[key])
    added = [x for x in dict.fromkeys(items) if x not in have]
    return dict(state, **{key: state[key] + added})


class CsvAppender:
    """한 번 실행 = 파일 하나. 주마다 행을 덧붙이고 바로 디스크에 쓴다 (중간에 끊겨도 남게)."""

    def __init__(self, out_dir: Path, day: str):
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"raw_kr_gig_{day}_{SITE}_history.csv"
        if path.exists():  # 원본은 고치지 않는다
            path = out_dir / f"raw_kr_gig_{day}_{SITE}_history_{datetime.now(KST):%H%M%S}.csv"
        self.path = path
        self.count = 0
        self._fh = open(path, "w", encoding="utf-8", newline="")
        self._writer = csv.DictWriter(self._fh, fieldnames=COLUMNS)
        self._writer.writeheader()

    def write(self, rows: list) -> None:
        self._writer.writerows(rows)
        self._fh.flush()
        self.count += len(rows)

    def close(self) -> None:
        self._fh.close()


# ---------- aside 호출 ----------

def run_repl(code: str):
    proc = subprocess.run(["aside", "repl", "--json", code], capture_output=True, text=True, timeout=REPL_TIMEOUT_SEC)
    return parse_repl_output(proc.stdout)


def run_with_retry(code: str, what: str):
    for attempt in (1, 2):
        try:
            return run_repl(code)
        except (RuntimeError, subprocess.TimeoutExpired) as e:
            print(f"  ⚠️ {what} 실패 ({attempt}번째): {e}", file=sys.stderr)
            if attempt == 1:
                time.sleep(RETRY_WAIT_SEC)
    return None


def list_weeks(offsets: list):
    first = f"{BASE}/weekly?week={offsets[0]}"
    return run_with_retry(LIST_JS % {"first": json.dumps(first), "weeks": json.dumps(offsets)}, f"주간 목록 {offsets}")


# ---------- 실행 ----------

def _process_gigs(urls, state, writer, stats, since, until):
    for i in range(0, len(urls), GIGS_PER_DETAIL_CALL):
        batch = urls[i:i + GIGS_PER_DETAIL_CALL]
        details = run_with_retry(DETAIL_JS % {"urls": json.dumps(batch)}, f"상세 {len(batch)}건")
        if details is None:
            stats["failed"] += len(batch)
            continue
        now = datetime.now(KST).replace(microsecond=0).isoformat()
        done = []
        for want, d in zip(batch, details):
            if d.get("notFound"):   # 사이트에서 지워진 공연: 다시 봐도 소용없으니 끝난 것으로 친다
                stats["not_found"] += 1
                done.append(want)
                continue
            if d.get("error") or d.get("status", 200) != 200 or not d.get("startDate"):
                stats["failed"] += 1
                continue
            day = to_kst(d["startDate"])[:10]
            if not since <= day <= until:   # 범위 밖은 '끝남'으로 적지 않는다 (더 이른 --since 되짚기 때 다시 받게)
                continue
            done.append(want)
            rows = gig_rows(d, now)
            stats["gigs"] += 1
            stats["no_performer"] += 0 if rows else 1
            writer.write(rows)
        state = mark(state, "gigs_done", done)
        save_state(STATE_PATH, state)
    return state


def _fill_year(program: dict, year: str) -> dict:
    """라인업 날짜에 연도를 못 찾았으면('????-09-05') 목록에서 본 주의 연도로 채운다."""
    days = [dict(d, date=d.get("date", "").replace("????", year)) for d in program.get("days", [])]
    return dict(program, days=days)


def _process_programs(urls, state, writer, stats, since, until, year):
    if not urls:
        return state
    progs = run_with_retry(PROGRAM_JS % {"urls": json.dumps(urls)}, f"기획공연 {len(urls)}건")
    if progs is None:
        return state
    now = datetime.now(KST).replace(microsecond=0).isoformat()
    done = []
    for want, p in zip(urls, progs):
        if p.get("error"):
            continue
        done.append(want)
        rows = program_rows(_fill_year(p, year), now, since, until)
        if rows:
            listed = sum(d.get("count", 0) for d in p.get("days", []))
            stats["festivals"].append(f"{p.get('title', '')} ({len(rows)}행, 라인업 표기 {listed}팀)")
            writer.write(rows)
    state = mark(state, "programs_done", done)
    save_state(STATE_PATH, state)
    return state


def collect(since: str, until: str, out_dir: Path, max_weeks: int):
    today = datetime.now(KST).date().isoformat()
    state = load_state(STATE_PATH)
    todo = [w for w in weeks_between(since, until, today) if w[1] not in set(state["weeks_done"])][:max_weeks]
    stats = {"weeks": 0, "gigs": 0, "no_performer": 0, "failed": 0, "not_found": 0, "festivals": []}
    writer = CsvAppender(out_dir, today)
    try:
        for i in range(0, len(todo), WEEKS_PER_LIST_CALL):
            chunk = todo[i:i + WEEKS_PER_LIST_CALL]
            listed = list_weeks([w for w, _ in chunk])
            if listed is None:
                stats["failed_weeks"] = stats.get("failed_weeks", 0) + len(chunk)
                continue
            for (offset, monday), wk in zip(chunk, listed):
                if wk.get("error"):
                    continue
                gigs_done, progs_done = set(state["gigs_done"]), set(state["programs_done"])
                gigs = [u for u in dict.fromkeys(abs_url(h) for h in wk["gigs"]) if u not in gigs_done]
                progs = [u for u in dict.fromkeys(abs_url(h) for h in wk["programs"]) if u not in progs_done]
                before_failed = stats["failed"]
                state = _process_gigs(gigs, state, writer, stats, since, until)
                state = _process_programs(progs, state, writer, stats, since, until, monday[:4])
                if stats["failed"] == before_failed and week_fully_inside(monday, since, until):
                    # 실패가 있거나 범위 경계에 걸친 주는 다음 실행에서 다시 본다
                    state = mark(state, "weeks_done", [monday])
                    save_state(STATE_PATH, state)
                stats["weeks"] += 1
                print(f"  {monday} (week={offset}): 공연 {len(wk['gigs'])}건, 기획공연 {len(wk['programs'])}건"
                      f" → 누적 {writer.count}행", file=sys.stderr)
    finally:
        writer.close()
    if writer.count == 0:
        writer.path.unlink()
        return None, 0, stats
    return writer.path, writer.count, stats


def main(argv):
    ap = argparse.ArgumentParser(description="인디스트릿 지난 공연 채우기 (aside 브라우저)")
    ap.add_argument("--since", default="2024-01-01", help="이 날짜부터 (YYYY-MM-DD)")
    ap.add_argument("--until", default=None, help="이 날짜까지 (기본: 어제)")
    ap.add_argument("--max-weeks", type=int, default=1000, help="이번 실행에서 볼 최대 주 수 (나눠 돌리기용)")
    ap.add_argument("--out", default=str(ROOT / "data" / "raw"))
    args = ap.parse_args(argv)
    yesterday = (datetime.now(KST).date() - timedelta(days=1)).isoformat()
    until = args.until or yesterday
    for v in (args.since, until):
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", v):
            ap.error("날짜는 YYYY-MM-DD 로 주세요")
    if args.since > until:
        ap.error("--since 가 --until 보다 늦어요")
    try:
        path, n_rows, st = collect(args.since, until, Path(args.out), args.max_weeks)
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"❌ 수집 실패: {e}", file=sys.stderr)
        return 1
    print(f"✅ indistreet 지난 공연: {st['weeks']}주, 공연 {st['gigs']}건 → {n_rows}행"
          f" (출연 팀 없음 {st['no_performer']}, 사이트에 없음 {st['not_found']}, 실패 {st['failed']}, 목록 실패 주 {st.get('failed_weeks', 0)})"
          + (f" → {path}" if path else ""))
    for f in st["festivals"]:
        print(f"   페스티벌: {f}")
    return 0 if st["failed"] == 0 and not st.get("failed_weeks") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
