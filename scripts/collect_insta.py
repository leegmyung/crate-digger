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
HISTORY_DAYS = 365          # 첫 방문·--history: 프로필에 보이는 게시물을 이만큼 옛날 것까지 남긴다
HISTORY_POSTS = 12          # 첫 방문·--history: 로그인 없이 프로필에 보이는 게시물 수(약 12개)만큼 읽는다
SEEN_KEEP = 100
MAX_ACCOUNTS_PER_RUN = 260   # 한 번에 볼 계정 상한 (계정당 10~20초 → 1시간 안팎, 인스타 차단 위험 관리)
ZERO_STREAK_STEP = 3        # 이만큼 연속으로 0행(팀을 하나도 못 찾음)이면 주기를 2배로 (6회면 4배 …)
MAX_EVERY_DAYS = 28         # 늘어나는 주기의 상한
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


# 라인업 공지 계정 — 글이 평론 픽이 아니라 '누가 어디서 공연한다'는 공지라 '공연'으로 센다 (is_pick=0, venue_lineup).
# venue = 공연장, promoter = 기획·파티 크루·에이전시, label = 레이블·배급사, event = 페스티벌·행사.
# 공연장이 아닌 계정은 공연장 칸('@계정')이 어느 공연장인지 알려 주지 않는다 (scripts/venues_kr.py 가 '공연장 미상'으로 따로 셈).
LINEUP_ROLES = ("venue_showcase", "promoter_showcase", "label_showcase", "event_showcase")


def to_rows(account, post, collected_at, role="magazine"):
    """게시물 1개 → (행 목록, 검수 대기 항목 또는 None)

    role 이 LINEUP_ROLES(공연장·기획·레이블·행사 계정)면 글이 평론 픽이 아니라 라인업 공지라서
    is_pick=0, pick_label=venue_lineup 으로 남긴다. 갈래 겹침에서 '공연'으로 센다 (이중 가점 방지).
    """
    parsed = parse_og(post.get("og", ""))
    found = mentions(parsed["caption"], own_handle=account)
    if not parsed["date"] or not found:
        return [], {"account": account, "url": post.get("url", ""), "date": parsed["date"], "caption": parsed["caption"][:1500]}
    venue = role in LINEUP_ROLES
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


def effective_every(account, zero_streak=0):
    """실제 확인 주기: 설정 주기 × 2^(연속 0행 ÷ ZERO_STREAK_STEP), 상한 MAX_EVERY_DAYS.
    라인업이 이미지로만 올라오거나 태그가 없는 계정을 매번 보지 않게 (행이 나오면 바로 원래 주기로)."""
    every = max(1, int(account.get("every_days", 1)))
    return min(MAX_EVERY_DAYS, every * 2 ** (int(zero_streak or 0) // ZERO_STREAK_STEP))


def update_streak(streaks, handle, n_rows):
    """읽기에 성공한 계정의 연속 0행 횟수 갱신 (새 dict)."""
    return {**streaks, handle: 0 if n_rows else int(streaks.get(handle, 0)) + 1}


def due_accounts(accounts, last_checked, today, limit=None, zero_streak=None):
    """볼 때가 된 계정. limit이 있으면 가장 오래 밀린 계정부터 limit개 (처음 보는 계정이 맨 앞).
    zero_streak 이 있으면 연속 0행 계정은 늘어난 주기(effective_every)로 본다."""
    t = date.fromisoformat(today)
    streaks = zero_streak or {}

    def overdue(a):
        last = last_checked.get(a["handle"])
        every = effective_every(a, streaks.get(a["handle"], 0))
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


def dedupe_rows(rows, written):
    """같은 (게시물 주소, 팀)은 한 번만 — 두 계정이 함께 올린 공동 게시물은 양쪽 계정에서 똑같이 읽힌다.
    written 은 이번 실행에서 이미 쓴 키 모음 (중간 저장 사이에도 유지, 이 함수가 채운다)."""
    out = []
    for r in rows:
        key = (r.get("url", ""), r.get("artist_text", ""))
        if key in written:
            continue
        written.add(key)
        out.append(r)
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


def oldest_for(seen, now, history=False):
    """남길 가장 오래된 게시일. 첫 방문(본 게시물 없음)·--history 는 HISTORY_DAYS, 평소엔 MAX_POST_AGE_DAYS.
    (예전엔 첫 방문에도 14일만 남기고 나머지를 '본 것'으로 적어, 옛 게시물을 영영 못 받았다.)"""
    days = HISTORY_DAYS if history or not seen else MAX_POST_AGE_DAYS
    return (now - timedelta(days=days)).date().isoformat()


def collected_post_ids(raw_dir):
    """이미 원본 CSV에 저장한 인스타 게시물 번호 — --history 가 이것만 건너뛰고 버려졌던 옛 게시물은 다시 읽게."""
    ids = set()
    for path in sorted(Path(raw_dir).glob("raw_press_*_instagram*.csv")):
        with open(path, encoding="utf-8", newline="") as fh:
            ids.update(_post_id(r["url"]) for r in csv.DictReader(fh) if r.get("url"))
    return ids


def _collect_account(handle, seen, collected_at, oldest, role="magazine", max_new=MAX_NEW_POSTS):
    res = run_repl(PROFILE_JS % {"handle": handle, "seen": json.dumps(seen), "max_new": max_new})
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


def collect(check_all=False, history=False, limit=None, offset=0):
    """history=True: 이미 한 번 본 계정의 옛 게시물(저장 안 한 것)을 HISTORY_DAYS 까지 다시 읽는 한 번짜리 되짚기.
    매일 주기(last_checked·zero_streak)는 바꾸지 않는다."""
    now = datetime.now(KST).replace(microsecond=0)
    today = f"{now:%Y-%m-%d}"
    accounts = collectable_accounts(_load_json(CONFIG, {}).get("accounts", []))
    state = _load_json(STATE, {"last_checked": {}, "seen": {}})
    state.setdefault("zero_streak", {})          # 계정별 연속 0행 횟수 (늘어난 주기 계산용)
    saved_ids = collected_post_ids(RAW_DIR) if history else set()
    if history:
        visited = [a for a in accounts if state["seen"].get(a["handle"])][offset:]   # offset: 끊긴 되짚기 이어 하기
        targets = visited[:limit]
    else:
        if not check_all:
            state["last_checked"] = stagger(accounts, state["last_checked"], today)
        targets = accounts if check_all else due_accounts(accounts, state["last_checked"], today,
                                                          limit=MAX_ACCOUNTS_PER_RUN, zero_streak=state["zero_streak"])
    pending, review, report = [], [], []
    written = {"path": None, "rows": 0}
    written_keys: set = set()

    def flush():
        """모은 행을 파일로, 상태를 state 파일로 (중간 저장). 같은 날 두 번째부터는 시각 붙은 새 파일."""
        rows_out = dedupe_rows(pending, written_keys)
        pending.clear()
        if rows_out:
            written["path"] = write_csv(rows_out, RAW_DIR, today)
            written["rows"] += len(rows_out)
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
            wide = history or not seen
            skip = sorted(saved_ids & set(seen)) if history else seen
            try:
                result = _collect_account(handle, skip, now.isoformat(), oldest_for(seen, now, history),
                                          a.get("role", "magazine"), max_new=HISTORY_POSTS if wide else MAX_NEW_POSTS)
            except (RuntimeError, subprocess.TimeoutExpired, ValueError, KeyError) as e:   # 계정 하나 실패해도 계속
                report.append(f"⚠️ @{handle}: 읽기 실패 ({e})")
                continue
            if result is None:
                report.append(f"❌ @{handle}: 계정이 없거나 볼 수 없음 → config 확인 필요")
                continue
            got, unparsed, ids = result
            pending.extend(got)
            review.extend(unparsed)
            state["seen"][handle] = (seen + [i for i in ids if i not in seen])[-SEEN_KEEP:]
            if not history:
                state["last_checked"][handle] = today
                state["zero_streak"] = update_streak(state["zero_streak"], handle, len(got))
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
    ap.add_argument("--history", action="store_true",
                    help=f"한 번짜리 되짚기: 이미 본 계정의 옛 게시물을 {HISTORY_DAYS}일 치까지 다시 읽기 (매일 주기는 그대로)")
    ap.add_argument("--limit", type=int, default=None, help="--history 로 볼 계정 수 상한")
    ap.add_argument("--offset", type=int, default=0, help="--history 를 앞의 N계정 건너뛰고 이어 하기 (끊겼을 때)")
    args = ap.parse_args(argv)
    path, n_rows, n_review, report = collect(args.all, args.history, args.limit, args.offset)
    print("\n".join(report))
    print(f"✅ 인스타: {n_rows}행" + (f" → {path}" if path else "") + (f" · 검수 대기 {n_review}건" if n_review else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
