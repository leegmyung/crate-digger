"""공연 수집기 (인디고·인디스트릿) → data/raw/raw_kr_gig_<날짜>_<소스>.csv

    python3 scripts/collect_gigs.py                  # 두 곳 모두, 오늘부터 7일
    python3 scripts/collect_gigs.py --site indiego --days 3
    python3 scripts/collect_gigs.py --venue-history regional   # 인디고 공연장별 지난 공연 (서울 밖, 일반 HTTP)
    python3 scripts/collect_gigs.py --venue-history all        # 인디고 공연장 전체

공연장별 지난 공연(--venue-history): config/venues_kr.json 의 인디고 공연장 페이지에 실린 공연 목록(번호·날짜)을 읽고,
아직 안 받은 지난 공연만 공연 페이지의 구조화 데이터(JSON-LD)로 읽는다. 인디고 robots.txt 는 /api/ 만 막고 나머지를
허용하므로 aside 없이 일반 요청으로 읽는다. → raw_kr_gig_<날짜>_indiego_history.csv (source=indiego, collector=script)

aside 브라우저(aside repl)로 목록 → 상세 페이지를 천천히 읽는다 (상세 사이 2초 쉼, 하루 1번).
상세 페이지의 구조화 데이터(JSON-LD MusicEvent)와 아티스트 링크에서 출연 팀을 뽑는다.
출연 팀이 없는 공연(DJ 파티 등)은 건너뛴다. 형식: docs/csv_spec.md
"""
import argparse
import csv
import json
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from csv_schema import TABLES

ROOT = Path(__file__).resolve().parent.parent
KST = timezone(timedelta(hours=9))
COLUMNS = [f.name for f in TABLES["raw_kr_gig"]["fields"]]
BATCH_SIZE = 12
DETAIL_DELAY_MS = 0   # 일부러 쉬지 않음 (2026-11-26 사용자 지시). 페이지 로딩 대기는 따로 있음
REPL_TIMEOUT_SEC = 150
MAX_GIGS_PER_SITE = 200
RETRY_WAIT_SEC = 20

SITES = {
    "indiego": {"list_urls": ["https://www.indiego.co.kr/events"], "scrolls": 8},
    "indistreet": {"list_urls": ["https://indistreet.com/weekly", "https://indistreet.com/weekly?week=1"], "scrolls": 0},
}

LIST_JS = """
await (async () => {
  const out = [];
  for (const u of %(urls)s) {
    const t = await openTab(u); await sleep(3000);
    for (let i = 0; i < %(scrolls)d; i++) { await t.evaluate(() => window.scrollTo(0, document.body.scrollHeight)); await sleep(1500); }
    const items = await t.evaluate((pat) => [...document.querySelectorAll('a[href*="' + pat + '"]')].map(a => {
      let el = a, text = '';
      for (let k = 0; k < 5 && el; k++, el = el.parentElement) { if (/\d{4}년/.test(el.innerText || '')) { text = el.innerText; break; } }
      return { url: a.href, text: (text || a.innerText || '').replace(/\s+/g, ' ').slice(0, 200) };
    }), %(pattern)s);
    out.push(...items); await closeTab(t);
  }
  console.log('RESULT ' + JSON.stringify(out));
})();
"""

DETAIL_JS = """
await (async () => {
  const out = [];
  for (const u of %(urls)s) {
    let t;
    try {
      t = await openTab(u); await sleep(2500);
      const d = await t.evaluate(() => {
        const lds = [...document.querySelectorAll('script[type="application/ld+json"]')]
          .map(s => { try { return JSON.parse(s.textContent); } catch (e) { return null; } }).filter(Boolean);
        const ev = lds.flat().find(x => x && x['@type'] === 'MusicEvent') || {};
        const loc = ev.location || {};
        const perf = [].concat(ev.performer || []).map(p => ({ name: (p.name || '').trim(), url: p.url || '' }));
        const anchors = [...document.querySelectorAll('a[href*="/artists/"]')]
          .map(a => ({ name: a.innerText.replace(/\\s+/g, ' ').trim(), url: a.href })).filter(p => p.name);
        return { url: location.href, name: ev.name || document.title, startDate: ev.startDate || '',
                 venue: loc.name || '', address: (loc.address && (loc.address.streetAddress || loc.address.addressLocality)) || '',
                 performers: perf.length ? perf : anchors };
      });
      out.push(d);
    } catch (e) { out.push({ url: u, error: String(e) }); }
    if (t) await closeTab(t);
    await sleep(%(delay)d);
  }
  console.log('RESULT ' + JSON.stringify(out));
})();
"""


def parse_repl_output(stdout):
    """aside repl --json 출력에서 'RESULT {json}' 줄을 찾아 돌려준다."""
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"aside 출력 해석 실패: {stdout[:200]}") from e
    texts = [c.get("text", "") for c in data.get("run", {}).get("content", []) if isinstance(c, dict)]
    for text in texts:
        for line in text.split("\n"):   # splitlines()는 캡션 속 U+2028도 줄바꿈으로 봐서 결과를 자른다
            if line.startswith("RESULT "):
                try:
                    return json.loads(line[len("RESULT "):])
                except json.JSONDecodeError as e:
                    raise RuntimeError(f"aside 결과가 잘렸거나 깨짐: {e}") from e
    raise RuntimeError(f"aside 결과 없음: {data.get('run', {}).get('error')}")


def run_repl(code):
    proc = subprocess.run(["aside", "repl", "--json", code], capture_output=True, text=True, timeout=REPL_TIMEOUT_SEC)
    return parse_repl_output(proc.stdout)


def _tail_id(url, segment):
    path = urllib.parse.unquote(urllib.parse.urlparse(url).path)
    m = re.search(rf"/{segment}/([^/]+)", path)
    return m.group(1) if m else ""


def _source_id(site, url, segment):
    slug = _tail_id(url, segment)
    if site == "indiego":
        m = re.match(r"(\d+)", slug)
        return m.group(1) if m else slug
    return slug


def in_window(start_date, first_day, last_day):
    day = (start_date or "")[:10]
    return bool(re.match(r"^\d{4}-\d{2}-\d{2}$", day)) and first_day <= day <= last_day


def _to_kst(start):
    """'2026-11-26T11:00:00.000Z'처럼 UTC로 온 시각을 한국 시간으로. 이미 +09:00이거나 날짜만 있으면 그대로."""
    m = re.match(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?)(?:\.\d+)?Z$", start or "")
    if not m:
        return start or ""
    return datetime.fromisoformat(m.group(1)).replace(tzinfo=timezone.utc).astimezone(KST).isoformat()


def to_rows(site, detail, collected_at):
    start = _to_kst(detail.get("startDate", ""))
    m = re.match(r"^(\d{4}-\d{2}-\d{2})(?:T(\d{2}:\d{2}))?", start)
    if not m:
        return []
    venue = detail.get("venue", "").strip()
    address = detail.get("address", "").strip()
    base = {
        "collected_at": collected_at, "source": site, "collector": "aside",
        "source_id": _source_id(site, detail["url"], "events" if site == "indiego" else "gigs"),
        "gig_date": m.group(1), "gig_time": m.group(2) or "",
        "title": detail.get("name", "").strip(),
        "venue_text": f"{venue} ({address})" if venue and address else venue or address,
        "gig_url": detail["url"],
    }
    rows, seen = [], set()
    for p in detail.get("performers", []):
        name = (p.get("name") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        url = p.get("url") or ""
        rows.append(dict(base, artist_text=name, artist_source_id=_source_id(site, url, "artists") if url else "",
                         artist_url=url))
    return rows


def write_csv(rows, out_dir, site, day):
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"raw_kr_gig_{day}_{site}.csv"
    if path.exists():  # 원본은 고치지 않는다
        path = out_dir / f"raw_kr_gig_{day}_{site}_{datetime.now(KST):%H%M%S}.csv"
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def list_date(text):
    """목록 카드 글자의 '2026년 11월 26일'을 2026-11-26으로. 없으면 빈 문자열."""
    m = re.search(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일", text or "")
    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else ""


def filter_listed(items, first_day, last_day):
    """상세를 열기 전에 날짜로 거른다. 인디스트릿은 주소에, 인디고는 카드 글자에 날짜가 있다.
    날짜를 못 찾은 공연은 남겨 두고 상세에서 다시 확인한다."""
    urls, seen = [], set()
    for it in items:
        url = it["url"]
        if url in seen:
            continue
        seen.add(url)
        day = _tail_id(url, "gigs")[:10] if "/gigs/" in url else list_date(it.get("text", ""))
        if not day or in_window(day, first_day, last_day):
            urls.append(url)
    return urls


def list_gig_urls(site, first_day, last_day):
    cfg = SITES[site]
    pattern = "/events/" if site == "indiego" else "/gigs/"
    items = run_repl(LIST_JS % {"urls": json.dumps(cfg["list_urls"]), "scrolls": cfg["scrolls"], "pattern": json.dumps(pattern)})
    return filter_listed(items, first_day, last_day)[:MAX_GIGS_PER_SITE]


def _details_with_retry(site, batch):
    """상세 묶음을 읽는다. aside 응답이 없거나 시간이 넘으면 잠시 쉬고 한 번 더 시도한다."""
    code = DETAIL_JS % {"urls": json.dumps(batch), "delay": DETAIL_DELAY_MS}
    for attempt in (1, 2):
        try:
            return run_repl(code)
        except (RuntimeError, subprocess.TimeoutExpired) as e:
            print(f"  ⚠️ {site} 상세 묶음 실패 ({len(batch)}건, {attempt}번째): {e}", file=sys.stderr)
            if attempt == 1:
                time.sleep(RETRY_WAIT_SEC)
    return None


def collect_site(site, days, out_dir):
    now = datetime.now(KST).replace(microsecond=0)
    first_day, last_day = f"{now:%Y-%m-%d}", f"{now + timedelta(days=days):%Y-%m-%d}"
    urls = list_gig_urls(site, first_day, last_day)
    rows, stats = [], {"listed": len(urls), "in_window": 0, "no_performer": 0, "failed": 0}
    for i in range(0, len(urls), BATCH_SIZE):
        batch = urls[i:i + BATCH_SIZE]
        details = _details_with_retry(site, batch)
        if details is None:
            stats["failed"] += len(batch)
            continue
        for d in details:
            if d.get("error"):
                stats["failed"] += 1
                continue
            if not in_window(d.get("startDate", ""), first_day, last_day):
                continue
            stats["in_window"] += 1
            new_rows = to_rows(site, d, now.isoformat())
            stats["no_performer"] += 0 if new_rows else 1
            rows.extend(new_rows)
        print(f"  {site}: {min(i + BATCH_SIZE, len(urls))}/{len(urls)} 확인", file=sys.stderr)
    path = write_csv(rows, out_dir, site, first_day) if rows else None
    return path, len(rows), stats


# ---------- 인디고 공연장별 지난 공연 (일반 HTTP) ----------

INDIEGO = "https://www.indiego.co.kr"
VENUES_KR = ROOT / "config" / "venues_kr.json"
HTTP_DELAY_SEC = 0.3
USER_AGENT = "Mozilla/5.0 (compatible; gigle-research-script)"
VENUE_EVENT = re.compile(r'public_id\\?":(\d+)[^{}]*?start_date\\?":\\?"(\d{4}-\d{2}-\d{2})')
LD_JSON = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)


def http_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", "replace")


def venue_events(html):
    """인디고 공연장 페이지 → [{public_id, start_date}] (페이지에 실린 공연 순서대로, 공연장 자신의 번호는 날짜가 없어 빠짐)."""
    out, seen = [], set()
    for pid, day in VENUE_EVENT.findall(html or ""):
        if pid not in seen:
            seen.add(pid)
            out.append({"public_id": int(pid), "start_date": day})
    return out


def parse_event_page(html, url):
    """인디고 공연 페이지의 JSON-LD MusicEvent → aside 상세(DETAIL_JS)와 같은 모양. 없으면 None."""
    for raw in LD_JSON.findall(html or ""):
        try:
            data = json.loads(raw)
        except ValueError:
            continue
        for ev in data if isinstance(data, list) else [data]:
            if not isinstance(ev, dict) or ev.get("@type") != "MusicEvent":
                continue
            loc = ev.get("location") or {}
            addr = loc.get("address") or {}
            perf = [{"name": (p.get("name") or "").strip(), "url": p.get("url") or ""}
                    for p in ([ev["performer"]] if isinstance(ev.get("performer"), dict) else ev.get("performer") or [])]
            return {"url": ev.get("url") or url, "name": ev.get("name", ""), "startDate": ev.get("startDate", ""),
                    "venue": loc.get("name", ""),
                    "address": addr.get("streetAddress") or addr.get("addressLocality") or "" if isinstance(addr, dict) else str(addr),
                    "performers": [p for p in perf if p["name"]]}
    return None


def history_targets(cfg, scope):
    """config/venues_kr.json → [(공연장 이름, 인디고 공연장 주소)]. scope: regional = 서울 밖만, all = 전부."""
    return [(v["name"], v["indiego_url"]) for v in cfg.get("venues", [])
            if v.get("indiego_url") and (scope == "all" or v.get("city") not in ("", "서울"))]


def seen_indiego_ids(raw_dir):
    """이미 받은 인디고 공연 번호 (raw_kr_gig_*indiego*.csv 의 source_id)."""
    ids = set()
    for path in sorted(Path(raw_dir).glob("raw_kr_gig_*indiego*.csv")):
        with open(path, encoding="utf-8", newline="") as fh:
            ids.update(r["source_id"] for r in csv.DictReader(fh) if r.get("source") == "indiego" and r.get("source_id"))
    return ids


def collect_venue_history(targets, out_dir, today, seen, fetch=http_get, delay=HTTP_DELAY_SEC):
    """공연장마다 지난 공연(오늘 이전, 아직 안 받은 것)만 공연 페이지로 읽어 한 파일에 쓴다."""
    collected_at = datetime.now(KST).replace(microsecond=0).isoformat()
    rows, done = [], set(seen)
    st = {"venues": 0, "failed_venues": 0, "events_past": 0, "skipped_seen": 0, "fetched": 0, "failed": 0,
          "no_performer": 0}
    for name, url in targets:
        try:
            events = venue_events(fetch(url))
        except (OSError, ValueError) as e:
            st["failed_venues"] += 1
            print(f"  ⚠️ 공연장 페이지 실패 {name}: {e}", file=sys.stderr)
            continue
        st["venues"] += 1
        for ev in events:
            pid = str(ev["public_id"])
            if ev["start_date"] >= today:
                continue
            st["events_past"] += 1
            if pid in done:
                st["skipped_seen"] += 1
                continue
            done.add(pid)
            try:
                detail = parse_event_page(fetch(f"{INDIEGO}/events/{pid}"), f"{INDIEGO}/events/{pid}")
            except (OSError, ValueError):
                detail = None
            st["fetched"] += 1
            if detail is None:
                st["failed"] += 1
                continue
            new = [dict(r, collector="script", collected_at=collected_at) for r in to_rows("indiego", detail, collected_at)]
            st["no_performer"] += 0 if new else 1
            rows.extend(new)
            time.sleep(delay)
    path = write_csv(rows, Path(out_dir), "indiego_history", today) if rows else None
    return path, rows, st


def run_venue_history(scope, out_dir):
    cfg = json.loads(VENUES_KR.read_text(encoding="utf-8"))
    today = f"{datetime.now(KST):%Y-%m-%d}"
    path, rows, st = collect_venue_history(history_targets(cfg, scope), out_dir, today, seen_indiego_ids(out_dir))
    print(f"✅ 인디고 공연장별 지난 공연({scope}): 공연장 {st['venues']}곳(실패 {st['failed_venues']}) · 지난 공연 "
          f"{st['events_past']}건 중 이미 받음 {st['skipped_seen']} · 새로 읽음 {st['fetched']} → {len(rows)}행"
          f" (출연 팀 없음 {st['no_performer']}, 실패 {st['failed']})" + (f" → {path}" if path else ""))
    return 0


def main(argv):
    ap = argparse.ArgumentParser(description="인디고·인디스트릿 공연 수집 (aside 브라우저)")
    ap.add_argument("--site", choices=["indiego", "indistreet", "all"], default="all")
    ap.add_argument("--days", type=int, default=7, help="오늘부터 며칠 뒤 공연까지 (기본 7)")
    ap.add_argument("--out", default=str(ROOT / "data" / "raw"))
    ap.add_argument("--venue-history", choices=["regional", "all"],
                    help="인디고 공연장 페이지로 지난 공연 되짚기 (regional = 서울 밖 공연장만)")
    args = ap.parse_args(argv)
    if args.venue_history:
        return run_venue_history(args.venue_history, Path(args.out))
    if not 0 <= args.days <= 14:
        ap.error("--days 는 0~14 사이로 주세요")
    sites = ["indiego", "indistreet"] if args.site == "all" else [args.site]
    exit_code = 0
    for site in sites:
        try:
            path, n_rows, st = collect_site(site, args.days, Path(args.out))
        except (RuntimeError, subprocess.TimeoutExpired, FileNotFoundError) as e:
            print(f"❌ {site} 수집 실패: {e}", file=sys.stderr)
            exit_code = 1
            continue
        print(f"✅ {site}: 목록 {st['listed']}건 중 기간 내 공연 {st['in_window']}건 → {n_rows}행"
              f" (출연 팀 없음 {st['no_performer']}, 실패 {st['failed']})" + (f" → {path}" if path else ""))
    return exit_code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
