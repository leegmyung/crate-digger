"""인스타 음악 매거진 일일 수집기 → data/raw/raw_press_<날짜>_instagram.csv

    python3 scripts/collect_insta.py            # 오늘 확인할 계정만 (메인 매일, 보조 며칠마다)
    python3 scripts/collect_insta.py --all      # 전부

- 계정 목록: config/insta_accounts.json
- aside 브라우저(aside repl)로 로그인 없이 프로필 → 새 게시물 캡션(og:description)을 읽는다.
  페이지가 뜰 때까지만 기다리고 일부러 쉬지는 않는다(사용자 지시). 로그인·팔로우·좋아요는 하지 않는다.
- 캡션에 태그된 @계정마다 1행. 이름은 '이름(@계정)' 형태일 때만 쓰고 아니면 계정 이름을 쓴다.
- @태그가 없는 캡션은 data/raw/review/insta_unparsed_<날짜>.json 에 모아 2단계에서 검수한다.
- 이미 본 게시물과 마지막 확인일은 data/raw/state/insta_state.json (비공개)
"""
import argparse
import csv
import json
import re
import subprocess
import sys
import time
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from collect_gigs import run_repl
from csv_schema import TABLES

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "insta_accounts.json"
RAW_DIR = ROOT / "data" / "raw"
STATE = RAW_DIR / "state" / "insta_state.json"
KST = timezone(timedelta(hours=9))
COLUMNS = [f.name for f in TABLES["raw_press"]["fields"]]
MAX_NEW_POSTS = 6
MAX_POST_AGE_DAYS = 14
SEEN_KEEP = 100
MAX_ACCOUNTS_PER_RUN = 260   # 한 번에 볼 계정 상한 (계정당 10~20초 → 1시간 안팎, 인스타 차단 위험 관리)
CHECKPOINT_EVERY = 20       # 이만큼 계정을 볼 때마다 행·상태 저장 (2026-11-26 수집이 도중에 멈춰 그날 본 계정이 모두 사라진 일 대비)
ACCOUNT_PAUSE_SEC = 0   # 일부러 쉬지 않음 (사용자 지시). 로그인 요구 화면으로 막히면 다시 늘린다

MONTHS = {m: i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August",
     "September", "October", "November", "December"], start=1)}
OG_RE = re.compile(r'^(?:.*? - )?(\S+) (?:on|-) ([A-Z][a-z]+) (\d{1,2}), (\d{4}): "?(.*?)"?\s*$', re.S)
HANDLE_RE = re.compile(r"@([A-Za-z0-9._]{1,30})")
NAMED_RE = re.compile(r"([^\s()@]+)\s*\(\s*@([A-Za-z0-9._]{1,30})\s*\)")
SPONSORED_RE = re.compile(r"#제작지원|#협찬|#광고(?![가-힣])|유료\s*광고|paid partnership|#sponsored|#ad\b|협찬을 받|제작 지원을 받", re.I)

PROFILE_JS = """
await (async () => {
  const t = await openTab('https://www.instagram.com/%(handle)s/'); await sleep(3500);
  const prof = await t.evaluate(() => ({
    meta: document.querySelector('meta[name="description"]')?.content || '',
    gone: /isn't available|페이지를 사용할 수 없습니다/.test(document.body.innerText),
    links: [...new Set([...document.querySelectorAll('a[href*="/p/"],a[href*="/reel/"]')].map(a => a.getAttribute('href')))]
  }));
  const seen = new Set(%(seen)s);
  const fresh = prof.links.filter(h => !seen.has(h.split('/').filter(Boolean).pop())).slice(0, %(max_new)d);
  const posts = [];
  for (const h of fresh) {
    await t.goto('https://www.instagram.com' + h); await sleep(2500);
    const og = await t.evaluate(() => document.querySelector('meta[property="og:description"]')?.content || '');
    posts.push({ url: 'https://www.instagram.com' + h, og });
  }
  await closeTab(t);
  console.log('RESULT ' + JSON.stringify({ meta: prof.meta, gone: prof.gone || !prof.meta, posts }));
})();
"""


def parse_og(og):
    m = OG_RE.match((og or "").strip())
    if not m or m.group(2) not in MONTHS:
        return {"date": "", "caption": (og or "").strip()}
    day = date(int(m.group(4)), MONTHS[m.group(2)], int(m.group(3)))
    return {"date": day.isoformat(), "caption": m.group(5).strip()}


NOT_A_NAME = re.compile(r"^[\d,.:~\-/]+(원|명|시|분|일|월)?$")   # 가격·시간·날짜는 이름이 아님


def mentions(caption, own_handle):
    pairs = [(name, h.rstrip(".")) for name, h in NAMED_RE.findall(caption or "") if not NOT_A_NAME.match(name)]
    uses = Counter(name for name, _ in pairs)
    named = {h: name for name, h in pairs if uses[name] == 1}   # 한 이름이 여러 계정에 붙으면 계정 이름을 쓴다
    out, seen = [], set()
    for raw in HANDLE_RE.findall(caption or ""):
        handle = raw.rstrip(".")
        if not handle or handle.lower() == own_handle.lower() or handle in seen:
            continue
        seen.add(handle)
        out.append((named.get(handle, handle), "@" + handle))
    return out


def is_sponsored(caption):
    return bool(SPONSORED_RE.search(caption or ""))


def to_rows(account, post, collected_at, role="magazine"):
    """게시물 1개 → (행 목록, 검수 대기 항목 또는 None)

    role="venue_showcase"(공연장·기획 계정)의 글은 평론 픽이 아니라 라인업 공지라서
    is_pick=0, pick_label=venue_lineup 으로 남긴다. 갈래 겹침에서 '공연'으로 센다 (이중 가점 방지).
    """
    parsed = parse_og(post.get("og", ""))
    found = mentions(parsed["caption"], own_handle=account)
    if not parsed["date"] or not found:
        return [], {"account": account, "url": post.get("url", ""), "date": parsed["date"], "caption": parsed["caption"][:1500]}
    venue = role == "venue_showcase"
    base = {
        "collected_at": collected_at, "source": "instagram", "collector": "aside",
        "outlet": "@" + account, "published_at": parsed["date"],
        "title": re.sub(r"\s+", " ", parsed["caption"])[:80], "url": post["url"],
        "release_title": "", "is_pick": "0" if venue else "1", "pick_label": "venue_lineup" if venue else "",
        "is_sponsored": "1" if is_sponsored(parsed["caption"]) else "0",
    }
    return [dict(base, artist_text=name, artist_handle=handle) for name, handle in found], None


def collectable_accounts(accounts):
    """수집할 계정: 팀 본인 계정(role=artist)은 뺀다 — 그 글을 매체 큐레이션으로 세면 다른 팀에 가짜 신호가 생김."""
    return [a for a in accounts if a.get("role") != "artist"]


def due_accounts(accounts, last_checked, today, limit=None):
    """볼 때가 된 계정. limit이 있으면 가장 오래 밀린 계정부터 limit개 (처음 보는 계정이 맨 앞)."""
    t = date.fromisoformat(today)

    def overdue(a):
        last = last_checked.get(a["handle"])
        every = int(a.get("every_days", 1))
        return 10 ** 6 if not last else (t - date.fromisoformat(last)).days - every

    due = [a for a in accounts if overdue(a) >= 0]
    if limit is None:
        return due
    return sorted(due, key=lambda a: -overdue(a))[:limit]


def stagger(accounts, last_checked, today):
    """처음 보는 계정의 '지난 확인일'을 주기 안에서 나눠 배정 → 새 계정이 한날 한꺼번에 몰리지 않게.
    every_days=N인 i번째 새 계정은 오늘부터 i % N일 뒤에 처음 확인된다."""
    t = date.fromisoformat(today)
    out = dict(last_checked)
    count: dict = {}
    for a in accounts:
        if a["handle"] in out:
            continue
        every = max(1, int(a.get("every_days", 1)))
        i = count.get(every, 0)
        count[every] = i + 1
        out[a["handle"]] = (t - timedelta(days=every - i % every)).isoformat()
    return out


def write_csv(rows, out_dir, day):
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"raw_press_{day}_instagram.csv"
    if path.exists():  # 원본은 고치지 않는다
        path = out_dir / f"raw_press_{day}_instagram_{datetime.now(KST):%H%M%S}.csv"
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _post_id(url):
    return url.rstrip("/").split("/")[-1]


def _collect_account(handle, seen, collected_at, oldest, role="magazine"):
    res = run_repl(PROFILE_JS % {"handle": handle, "seen": json.dumps(seen), "max_new": MAX_NEW_POSTS})
    if res.get("gone"):
        return None
    rows, review, ids = [], [], []
    for post in res.get("posts", []):
        ids.append(_post_id(post["url"]))
        got, unparsed = to_rows(handle, post, collected_at, role)
        if got and got[0]["published_at"] >= oldest:   # 오래된 고정 게시물은 건너뜀
            rows.extend(got)
        if unparsed and (not unparsed["date"] or unparsed["date"] >= oldest):
            review.append(unparsed)
    return rows, review, ids


def collect(check_all=False):
    now = datetime.now(KST).replace(microsecond=0)
    today = f"{now:%Y-%m-%d}"
    oldest = (now - timedelta(days=MAX_POST_AGE_DAYS)).date().isoformat()
    accounts = collectable_accounts(_load_json(CONFIG, {}).get("accounts", []))
    state = _load_json(STATE, {"last_checked": {}, "seen": {}})
    if not check_all:
        state["last_checked"] = stagger(accounts, state["last_checked"], today)
    targets = accounts if check_all else due_accounts(accounts, state["last_checked"], today,
                                                      limit=MAX_ACCOUNTS_PER_RUN)
    pending, review, report = [], [], []
    written = {"path": None, "rows": 0}

    def flush():
        """모은 행을 파일로, 상태를 state 파일로 (중간 저장). 같은 날 두 번째부터는 시각 붙은 새 파일."""
        if pending:
            written["path"] = write_csv(pending, RAW_DIR, today)
            written["rows"] += len(pending)
            pending.clear()
        if review:
            rdir = RAW_DIR / "review"
            rdir.mkdir(parents=True, exist_ok=True)
            (rdir / f"insta_unparsed_{today}.json").write_text(json.dumps(review, ensure_ascii=False, indent=1), encoding="utf-8")
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")

    try:
        for n, a in enumerate(targets, 1):
            handle = a["handle"]
            seen = state["seen"].get(handle, [])
            try:
                result = _collect_account(handle, seen, now.isoformat(), oldest, a.get("role", "magazine"))
            except (RuntimeError, subprocess.TimeoutExpired, ValueError, KeyError) as e:   # 계정 하나 실패해도 계속
                report.append(f"⚠️ @{handle}: 읽기 실패 ({e})")
                continue
            if result is None:
                report.append(f"❌ @{handle}: 계정이 없거나 볼 수 없음 → config 확인 필요")
                continue
            got, unparsed, ids = result
            pending.extend(got)
            review.extend(unparsed)
            state["seen"][handle] = (seen + ids)[-SEEN_KEEP:]
            state["last_checked"][handle] = today
            report.append(f"✅ @{handle}: 새 게시물 {len(ids)}개 → {len(got)}행" + (f", 검수 대기 {len(unparsed)}" if unparsed else ""))
            if n % CHECKPOINT_EVERY == 0:
                flush()
            time.sleep(ACCOUNT_PAUSE_SEC)
    finally:
        flush()                                  # 끝났든 도중에 멈췄든 받은 만큼은 남긴다
    return written["path"], written["rows"], len(review), report


def main(argv):
    ap = argparse.ArgumentParser(description="인스타 음악 매거진 수집 (aside 브라우저, 로그인 없이)")
    ap.add_argument("--all", action="store_true", help="주기와 상관없이 모든 계정 확인")
    args = ap.parse_args(argv)
    path, n_rows, n_review, report = collect(args.all)
    print("\n".join(report))
    print(f"✅ 인스타: {n_rows}행" + (f" → {path}" if path else "") + (f" · 검수 대기 {n_review}건" if n_review else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
