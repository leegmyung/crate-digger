"""유튜브 채널 검색으로 팀 공식 채널 찾기 → data/raw/state/yt_search.json (비공개 상태)

    python3 scripts/yt_channel_search.py                  # 하루 최대 20번 검색 (2,000단위 + 확인 몇 단위)
    python3 scripts/yt_channel_search.py --max-searches 5

- 대상: 오늘 후보 상위 300(coverage_targets) 중 바로 듣기도 유튜브 링크도 없는 팀. 짧은 이름·흔한 낱말은 동명 위험이라 안 찾음.
  한 번 찾은 팀(찾았든 못 찾았든)은 RECHECK_DAYS 동안 다시 찾지 않는다.
- search.list(type=channel, 100단위)는 비싸서 하루 max_searches(기본 20)번까지만.
- 고르기(보수적, 2026-11-28 시험 10팀 정답지 = tests/test_yt_channel_search.py):
  채널 이름을 조각(괄호 안·한글/영문 덩어리, 'official'·'- Topic' 뗌)으로 나눠 팀 이름·별칭(연결표 영문 표기)과 키가 같으면 후보.
  공식(Topic 아닌) 후보가 하나면 그것. 여럿이면 최신 영상 5개 제목에 팀 이름이나 음악 낱말(MV·Live·Session…)이 있는
  채널이 딱 하나일 때만. 공식 후보가 없고 유튜브 자동 'Topic' 채널이 딱 하나이면서 그 채널 최신 영상 제목이 우리 발매 기록
  (raw_kr_release) 제목과 겹치면 그것(topic=true, verified=true). Topic 은 동명 위험이 커서(2026-11-28 '허재혁 - Topic') 겹침 필수.
- 결과는 collect_yt_channels 가 '채널 주소 후보'(출처 yt_search)로 받아 아바타·최신 영상을 받는다.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect_musicbrainz  # noqa: E402
import collect_videos as cv  # noqa: E402
import coverage_targets  # noqa: E402
from normalize import artist_key  # noqa: E402
from preview_match import name_keys, titles_overlap  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = ROOT / "data" / "raw" / "state" / "yt_search.json"
XREF_FILE = ROOT / "data" / "raw" / "state" / "artist_xref.json"
DATA_DIR = ROOT / "docs" / "lab" / "data"
COST_SEARCH = 100
DEFAULT_MAX_SEARCHES = 20
MAX_RANK = 300
RECHECK_DAYS = 90
SEARCH_RESULTS = 5
VERIFY_LATEST = 5
TOPIC_SUFFIX = re.compile(r"\s*-\s*topic\s*$", re.I)
NOISE_WORDS = re.compile(r"\b(?:official|offical|channel|youtube)\b|오피셜|공식|채널", re.I)
PARENS = re.compile(r"[\(\[（【]([^\)\]）】]*)[\)\]）】]")
SCRIPT_RUN = re.compile(r"[가-힣ㄱ-ㅎㅏ-ㅣ][가-힣ㄱ-ㅎㅏ-ㅣ0-9\s]*|[A-Za-z][A-Za-z0-9\s.&'!-]*")
MUSIC_WORDS = re.compile(r"\bm/?v\b|music video|official (?:audio|video)|\blive\b|session|라이브|세션|lyric|visuali[sz]er", re.I)


def channel_name_keys(title: str) -> Tuple[Set[str], bool]:
    """채널 이름 → (이름 키 조각 집합, Topic 채널인지). 조각: 전체·괄호 밖·괄호 안·한글 덩어리·영문 덩어리."""
    topic = bool(TOPIC_SUFFIX.search(title or ""))
    base = NOISE_WORDS.sub(" ", TOPIC_SUFFIX.sub("", title or ""))
    pieces = [base, PARENS.sub(" ", base)] + PARENS.findall(base)
    pieces += [m.group(0) for p in list(pieces) for m in SCRIPT_RUN.finditer(p)]
    return {k for k in (artist_key(p) for p in pieces) if k}, topic


def _music_like(titles: List[str], keys: Set[str]) -> bool:
    return any(MUSIC_WORDS.search(t) or any(k in artist_key(t) for k in keys if len(k) >= 3) for t in titles)


def choose_channel(names: List[str], results: List[dict], latest_titles: Callable[[str], List[str]],
                   our_titles: Iterable[str] = ()) -> Optional[dict]:
    """검색 결과 [{id, title}] → {id, title, topic[, verified]} 또는 None (규칙은 모듈 설명).
    Topic 채널은 동명 위험이 커서 우리 발매 기록 제목(our_titles)이 그 채널 최신 영상 제목과 겹칠 때만 (verified=True)."""
    want = name_keys(names)
    official, topic = [], []
    for r in results:
        keys, is_topic = channel_name_keys(r.get("title") or "")
        if keys & want:
            (topic if is_topic else official).append(r)
    if len(official) > 1:
        official = [r for r in official if _music_like(latest_titles(r["id"]), want)]
    if len(official) == 1:
        return {"id": official[0]["id"], "title": official[0]["title"], "topic": False}
    ours = list(our_titles)
    if not official and len(topic) == 1 and ours and titles_overlap(ours, latest_titles(topic[0]["id"])):
        return {"id": topic[0]["id"], "title": topic[0]["title"], "topic": True, "verified": True}
    return None


def _fresh(entry: Optional[dict], today: date) -> bool:
    try:
        return today - date.fromisoformat((entry or {}).get("checked") or "") < timedelta(days=RECHECK_DAYS)
    except ValueError:
        return False


def _latest_titles(client) -> Callable[[str], List[str]]:
    def fetch(channel_id: str) -> List[str]:
        uploads = "UU" + channel_id[2:]                     # 업로드 목록 = 채널 번호의 UC → UU (요청 0)
        try:
            body = client.get("playlistItems", {"part": "snippet", "playlistId": uploads,
                                                "maxResults": VERIFY_LATEST}, cv.COST_LIST)
        except cv.YouTubeError:
            return []
        return [(i.get("snippet") or {}).get("title") or "" for i in body.get("items") or []]
    return fetch


MAX_EN_TERMS = 1      # 한글 이름으로 못 찾으면 영문 활동명(en_names.py)으로 한 번 더 (하루 상한 안에서)


def _search(client, term: str) -> List[dict]:
    body = client.get("search", {"part": "snippet", "type": "channel", "q": term, "regionCode": "KR",
                                 "relevanceLanguage": "ko", "maxResults": SEARCH_RESULTS}, COST_SEARCH)
    return [{"id": (i.get("snippet") or {}).get("channelId") or "", "title": (i.get("snippet") or {}).get("channelTitle") or ""}
            for i in body.get("items") or []]


def _entry(picked: Optional[dict], today: date, terms: List[str]) -> dict:
    entry = {"checked": today.isoformat(), "channel_id": picked["id"] if picked else "", "terms": terms}
    if picked:
        entry.update(title=picked["title"], topic=picked["topic"])
        if picked.get("verified"):
            entry["verified"] = True
    return entry


def _terms(name: str, en: List[str], prev: Optional[dict], today: date) -> List[str]:
    """이번에 찾을 검색어(동명 위험이 적은 이름만). RECHECK_DAYS 안이면 못 찾은 팀의 아직 안 써 본 검색어만."""
    terms = ([name] if collect_musicbrainz.searchable(name) else [])
    terms += [e for e in en if e != name and collect_musicbrainz.searchable(e)][:MAX_EN_TERMS]
    if not _fresh(prev, today):
        return terms
    if (prev or {}).get("channel_id"):
        return []
    tried = (prev or {}).get("terms") or [name]
    return [t for t in terms if t not in tried]


def run(targets: List[dict], aliases: Dict[str, List[str]], state: Dict[str, dict], client, today: date,
        max_searches: int = DEFAULT_MAX_SEARCHES, max_rank: int = MAX_RANK, skip: Set[str] = frozenset(),
        releases: Optional[Dict[str, List[str]]] = None, en_names: Optional[Dict[str, List[str]]] = None) -> Dict[str, dict]:
    out, searched, en_names = dict(state), 0, en_names or {}
    for t in targets:
        key, name, rank = t.get("team_key") or "", t.get("display_name") or "", t.get("rank")
        if not key or not rank or rank > max_rank or key in skip:
            continue
        en = en_names.get(key, [])
        prev = out.get(key)
        todo = _terms(name, en, prev, today)
        if not todo:
            continue
        names = [name] + [a for a in aliases.get(key, []) if a != name] + en
        tried = list((prev or {}).get("terms") or []) if _fresh(prev, today) else []
        picked = None
        for term in todo:
            if searched >= max_searches or not client.quota.can(COST_SEARCH):
                break
            try:
                results = _search(client, term)
            except cv.QuotaExceeded:
                break
            searched += 1
            tried.append(term)
            try:
                picked = choose_channel(names, [r for r in results if r["id"]], _latest_titles(client),
                                        (releases or {}).get(key, []))
            except cv.QuotaExceeded:
                picked = None
            if picked:
                break
        if tried and tried != list((prev or {}).get("terms") or []):
            out[key] = _entry(picked, today, tried)
        if searched >= max_searches:
            break
    return out


def _csv(path: Path) -> List[dict]:
    try:
        with open(path, encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except OSError:
        return []


def _aliases(path: Path = XREF_FILE) -> Dict[str, List[str]]:
    try:
        return {a["artist_key"]: list(a.get("aliases") or []) for a in json.loads(path.read_text(encoding="utf-8"))}
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="유튜브 채널 검색으로 팀 공식 채널 찾기 (하루 상한)")
    ap.add_argument("--max-searches", type=int, default=DEFAULT_MAX_SEARCHES)
    args = ap.parse_args(argv)
    targets = coverage_targets.load_targets()
    if not targets:
        print("⏭ 대상 목록이 없어요 (먼저 .venv/bin/python scripts/coverage_targets.py)")
        return 0
    skip = {r["team_key"] for r in _csv(DATA_DIR / "players.csv")}
    skip |= {r["team_key"] for r in _csv(DATA_DIR / "links.csv") if r.get("platform") == "youtube"}
    env = cv.load_env(cv.ENV_FILE)
    budget = args.max_searches * (COST_SEARCH + 3 * cv.COST_LIST)
    try:
        client = cv.YouTubeClient(env.get("YOUTUBE_API_KEY"), quota=cv.Quota(budget))
    except cv.YouTubeError as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1
    state = cv.load_state(STATE_FILE)
    before = len(state)
    import collect_itunes                                   # 발매 기록 제목 (Topic 채널 확인용)
    import en_names as en_mod                               # 영문 활동명 (검색 전용, scripts/en_names.py)
    en_state = en_mod.load()
    state = run(targets, _aliases(), state, client, date.today(), max_searches=args.max_searches, skip=skip,
                releases=collect_itunes._releases(), en_names={k: en_mod.names_for(en_state, k) for k in en_state})
    cv.save_state(STATE_FILE, state)
    found = sum(1 for v in state.values() if v.get("channel_id"))
    print(f"✅ 유튜브 채널 검색: 이번 {len(state) - before}팀 · 누적 {len(state)}팀 중 채널 찾음 {found} · 사용 {client.quota.used}/{budget}단위")
    return 0


if __name__ == "__main__":
    sys.exit(main())
