"""유튜브 '최근 무대 영상' 수집기 → data/raw/raw_video_<날짜>.csv

    python3 scripts/collect_videos.py                 # 무대 채널 훑기 + 팀 공식 채널 + 상위 후보 검색
    python3 scripts/collect_videos.py --search-n 10   # 검색 팀 수 줄이기
    python3 scripts/collect_videos.py --no-search     # 검색(100단위씩 드는 비싼 요청) 빼고
    python3 scripts/collect_videos.py --backfill --budget 3000   # 무대 채널 과거 업로드를 2021-01-01까지 (이어받기)

- 왜: 신인 팀이 라이브 세션 채널(딩고·it's Live·스페이스 공감 등)에 나왔는지, 최근 무대 영상이 있는지는
  '무대에서 검증되기 시작했다'는 신호가 된다.
- 공식 YouTube Data API v3만 쓴다 (youtube.com 페이지는 robots.txt가 /results 등을 막아서 긁지 않는다).
  열쇠는 .env 또는 환경변수의 YOUTUBE_API_KEY. 값은 출력하지도 파일에 쓰지도 않는다.
- 하루 한도 10,000단위: channels.list·playlistItems.list = 1, search.list = 100.
  한 번 실행에 --budget(기본 5,000)까지만 쓰고, 넘을 것 같으면 그때까지 결과를 저장하고 멈춘다 → 다음 날 이어서.
- 하는 일
  1) 무대 채널(config/video_channels.json)의 업로드 목록을 최신부터 넘기며, 지난번에 본 영상(첫 실행은 400일 전)까지만 본다.
     제목에 팀 이름이 '낱말 그대로' 들어 있으면 kind=stage.
  2) 팀 공식 채널(docs/lab/data/links.csv의 youtube 줄)의 최신 영상 10개. 제목에 live·라이브·session·세션·무대가 있으면
     kind=official_live, 아니면 official. 채널 주소 → 업로드 목록 ID는 한 번 찾으면 상태 파일에 저장.
  3) 최신 점수 스냅샷(docs/lab/data/snapshots/<날짜>.csv) 상위 팀 중 7일 안에 검색 안 한 40팀을
     "<이름> 라이브"로 검색(최근 400일, 한국, 5개). 제목에 그 팀 이름이 있을 때만 kind=search.
- 이름 맞추기는 보수적으로: 잘못 붙는 것이 놓치는 것보다 나쁘다.
  한 글자·숫자만인 이름, 영문 2글자 이하, 흔한 낱말(STOPLIST)은 쓰지 않는다. 같은 이름의 팀이 둘 이상이면 버린다.
  두 글자 한글·세 글자 영문 이름은 제목 맨 앞이나 '-', '|', '(' 같은 구분 기호 옆에 있을 때만 인정한다.
- 상태: data/raw/state/videos_state.json (채널별 마지막 영상 시각, 주소→업로드 목록, 팀별 마지막 검색일)
"""
import argparse
import csv
import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
STATE_FILE = RAW_DIR / "state" / "videos_state.json"
ENV_FILE = ROOT / ".env"
CHANNELS_FILE = ROOT / "config" / "video_channels.json"
LAB_DATA = ROOT / "docs" / "lab" / "data"
KST = timezone(timedelta(hours=9))

API = "https://www.googleapis.com/youtube/v3/"
HTTP_TIMEOUT_SEC = 20
DEFAULT_BUDGET = 5000
COST_LIST = 1
COST_SEARCH = 100
FIRST_RUN_DAYS = 400
SEARCH_DAYS = 400
SEARCH_REPEAT_DAYS = 7
SEARCH_N = 40
SEARCH_RESULTS = 5
OFFICIAL_LATEST = 10
PAGE_SIZE = 50
DEFAULT_MAX_PAGES = 40
MAX_NAME_TOKENS = 6

COLUMNS = ["collected_at", "team_key", "display_name", "video_id", "title", "channel_title", "channel_id",
           "published_at", "kind", "source_channel_handle"]
VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
LIVE_WORDS = re.compile(r"\blive\b|\bsession\b|라이브|세션|무대", re.I)
TRAILING_ALIAS = re.compile(r"^(.*?)\s*[\(\[（]([^\)\]）]+)[\)\]）]\s*$")
TOKEN = re.compile(r"[0-9a-z가-힣ㄱ-ㅎㅏ-ㅣ一-鿿ぁ-んァ-ヶー]+")
HANGUL_ONLY = re.compile(r"^[가-힣]+$")
LATIN_ONLY = re.compile(r"^[a-z]+$")
LEADING_TAGS = re.compile(r"^\s*(?:[\[【(（<][^\]】)）>]*[\]】)）>]\s*)*$")
# '(원곡: 팀)', 'Original by 팀', 'cover by 팀' 처럼 원곡자·만든 사람으로만 나온 부분은 지우고 맞춘다
CREDIT_ONLY = re.compile(r"(?:원곡|original(?:\s*(?:by|artist))?|cover(?:ed)?\s*by|prod\.?\s*by)\s*[:：.]?[^)\]|/]*", re.I)
# 아이돌 멤버 직캠은 멤버 이름이 다른 팀 이름과 겹쳐 잘못 붙기 쉬워 무대 채널 훑기에서 뺀다
FANCAM = re.compile(r"직캠|fancam|facecam", re.I)
SEP_BEFORE = set("-–—|:/")   # 가운데의 [ ( 뒤는 작품·프로그램 이름일 때가 많아 뺀다
SEP_AFTER = set("-–—|:/(（[【'\"‘’“”「『<")

# 제목에 흔히 나오는 낱말이라 팀 이름으로 쓰면 잘못 붙는 것들 (팀 이름 쪽에서 제외)
STOPLIST = {
    # 방송·채널·영상 용어 (제목 앞머리 [태그]로 자주 나옴)
    "하이라이트", "highlight", "티저", "teaser", "세로", "fullcam", "inside", "스포트라이트", "spotlight",
    "헬로루키", "잇츠라이브", "리무진서비스", "고막남친", "뮤직뱅크", "musicbank", "공감라이브",
    "화이트", "white", "블랙", "black", "레드", "red", "블루", "blue", "핑크", "pink", "골드", "gold",
    "라이브", "세션", "무대", "밴드", "노래", "공연", "직캠", "난장", "공감", "딩고", "스케치북", "온스테이지", "시즌즈",
    "live", "session", "stage", "band", "music", "official", "video", "audio", "clip", "full", "cover", "kpop",
    "onstage", "dingo", "sketchbook", "tinydesk", "mv", "ost", "kbs", "ebs", "mbc", "sbs", "mnet", "nhk", "ktv",
    # 흔한 한국어 낱말 (팀 이름과 겹침)
    "사랑", "바보", "바다", "하늘", "이제", "모든", "어떤", "언제", "있지", "확인", "소리", "소년", "시간", "지구", "영원",
    "영화", "태양", "우리", "오늘", "하루", "그대", "다섯", "서른", "공원", "근처", "단독", "이런", "비밀", "요정",
    "지옥", "천둥", "고요", "낭만", "여백", "여운", "물결", "흔적", "투명", "온도", "동화", "부활", "새해", "시골",
    "식구", "자매", "취미", "피난", "항해", "한결", "흑백", "직시", "체감", "목적", "매듭", "무덤", "반말", "방백",
    "불씨", "거품", "구름", "모래", "소금", "양파", "치즈", "곱창", "꼬막", "키위", "모과", "녹두", "레고", "버그",
    "카드", "코드", "링크", "메타", "무드", "원더", "그린", "크림", "피크", "오프", "이브", "아이", "마크", "노선",
    "대동", "진보", "진화", "정오", "초승", "하지", "세기", "세로", "단지", "달력", "다방", "이유", "이월", "민주",
    "사색", "사심", "사양", "산보", "서리", "선명", "성에", "소통", "소실", "암호", "염력", "예상", "오열", "온돌",
    "온화", "우기", "우물", "유령", "유랑", "유아", "유자", "재판", "정국", "진격", "청백", "청록", "커서", "포효",
    "한해", "해무", "화목", "환원", "회랑", "흐를", "희미", "끌림", "느린", "느림", "맑은", "짙은", "날선", "달다",
    "쓰다", "말고", "물들", "홀린", "아늑", "오붓", "든든", "담담", "거미", "광야", "교정", "극야", "기원", "나날",
    "낙원", "녹음", "누에", "뉴런", "도끼", "동녘", "마치", "매미", "면도", "모음", "목적", "몽돌", "물결", "미소",
    "반도", "백합", "보리", "부활", "사가", "산새", "서정", "선망", "소담", "소요", "솔잎", "수호", "시소", "심단",
    "앗싸", "어흥", "여울", "연정", "영롱", "오존", "울림", "원형", "유수", "은하", "이삭", "일렁", "잔향", "잔영",
    "적재", "지주", "천둥", "청하", "초하", "치기", "키키", "태양", "피아", "한음", "해파", "호수", "홍시", "화원",
    "효정", "흑백", "희로", "다다", "나나", "미미", "비비", "디디", "지지", "더더", "문문", "용용", "양양", "월월",
    "위위", "윤윤", "넘넘", "핍핍", "수수", "씽씽", "차차", "논논", "든든", "뉘뉘", "낙낙", "교교", "구구",
    # 흔한 영어 낱말
    "the", "one", "air", "add", "ear", "eve", "man", "los", "toe", "dim", "dear", "what", "every", "enjoy", "envy",
    "sorry", "surf", "flow", "fog", "lamp", "laugh", "speed", "tank", "unity", "upper", "wood", "patch", "pale",
    "rave", "ray", "trace", "verge", "veil", "wiki", "cyan", "dots", "haven", "mania", "mike", "nyc", "bike",
    "brick", "chasm", "crane", "geese", "otter", "poppy", "pulp", "squid", "scrim", "slant", "sole", "mood", "room",
    "root", "loud", "low", "blur", "lilac", "pine", "pony", "puff", "puffy", "saga", "spin", "uni", "pam", "par",
    "dan", "ado", "amy", "ali", "eve", "ora", "roi", "rue", "sen", "tak", "khc", "cero", "flick", "leech", "limbs",
    "wack", "wade", "wisp", "zulu", "aries", "haim", "nina", "noah", "ethan", "chloe", "rosie", "robyn", "sammy",
    "shane", "isaac", "mina", "zoey", "kang", "jinho", "sunho", "yujin", "bela", "alma", "gaku", "kirin", "noi",
    "voi", "nib", "nuh", "gud", "kaz", "kik", "nas", "yon", "zinn", "baths", "beaks", "dorks", "elves", "fleet",
    "knob", "pores", "suede", "twice", "bada", "hana", "sora", "yama", "yuka", "yuzu", "saya", "huka", "maga",
}


class QuotaExceeded(RuntimeError):
    """예산(또는 API 하루 한도)에 닿음. rows에 그때까지 찾은 행을 싣는다."""

    def __init__(self, message="", rows=None):
        super().__init__(message)
        self.rows = rows or []


class YouTubeError(RuntimeError):
    def __init__(self, message="", status=None, reason=""):
        super().__init__(message)
        self.status = status
        self.reason = reason


# ---------- 설정 ----------

def load_env(path, environ=None):
    """.env 의 KEY=VALUE 를 읽는다. 이미 환경변수에 있으면 그쪽이 우선."""
    environ = os.environ if environ is None else environ
    values = {}
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return {**values, **{k: v for k, v in environ.items() if k in values or k.startswith("YOUTUBE_")}}


def load_state(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(path, state):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


# ---------- 예산·HTTP ----------

class Quota:
    def __init__(self, budget):
        self.budget = budget
        self.used = 0

    def can(self, cost):
        return self.used + cost <= self.budget

    def spend(self, cost):
        if not self.can(cost):
            raise QuotaExceeded(f"예산 {self.budget}단위에 닿음 (사용 {self.used})")
        self.used += cost


def urllib_http(url):
    try:
        with urllib.request.urlopen(url, timeout=HTTP_TIMEOUT_SEC) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except json.JSONDecodeError:
            return e.code, {}
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return 0, {"error": {"message": type(e).__name__}}


def _error_reason(body):
    errors = (body.get("error") or {}).get("errors") or [{}]
    return errors[0].get("reason", "")


class YouTubeClient:
    def __init__(self, api_key, http=urllib_http, quota=None):
        if not api_key:
            raise YouTubeError("YOUTUBE_API_KEY 가 없습니다 (.env 확인)")
        self._key = api_key
        self._http = http
        self.quota = quota or Quota(DEFAULT_BUDGET)

    def get(self, endpoint, params, cost):
        self.quota.spend(cost)
        url = API + endpoint + "?" + urllib.parse.urlencode({**params, "key": self._key})
        status, body = self._http(url)
        if status == 200:
            return body
        reason = _error_reason(body)
        if status == 403 and reason in ("quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded"):
            raise QuotaExceeded(f"API 하루 한도 초과 ({reason})")
        raise YouTubeError(f"{endpoint} 실패 (HTTP {status} {reason})", status, reason)   # 주소에 열쇠가 있어 주소는 안 적는다


# ---------- 주소·이름 ----------

def parse_youtube_url(url):
    """유튜브 채널 주소 → ('handle','@x') / ('id','UC..') / ('custom',이름) / ('user',이름), 아니면 None."""
    parsed = urllib.parse.urlparse((url or "").strip())
    host = parsed.netloc.lower()
    if not (host == "youtube.com" or host.endswith(".youtube.com")):
        return None
    parts = [urllib.parse.unquote(p) for p in parsed.path.split("/") if p]
    if not parts:
        return None
    first = parts[0]
    if first.startswith("@") and len(first) > 1:
        return ("handle", first)
    if first == "channel" and len(parts) > 1 and re.fullmatch(r"UC[A-Za-z0-9_-]{22}", parts[1]):
        return ("id", parts[1])
    if first == "c" and len(parts) > 1:
        return ("custom", parts[1])
    if first == "user" and len(parts) > 1:
        return ("user", parts[1])
    if first in ("watch", "shorts", "playlist", "embed", "live", "results", "feed") or len(parts) > 2:
        return None
    return ("custom", first)


def valid_video_id(video_id):
    return bool(VIDEO_ID.match(video_id or ""))


def split_names(display_name):
    """'사뮈 (Samui)' → ['사뮈', 'Samui']"""
    name = (display_name or "").strip()
    m = TRAILING_ALIAS.match(name)
    names = [m.group(1), m.group(2)] if m and m.group(1).strip() else [name]
    return [n.strip() for n in names if n.strip()]


def _tokens(text):
    return tuple(TOKEN.findall((text or "").lower()))


def name_rule(tokens):
    """이름 낱말 묶음 → None(쓰지 않음) / 'short'(구분 기호 옆에서만) / 'ok'."""
    joined = "".join(tokens)
    if not joined or joined.isdigit() or len(joined) < 2:
        return None
    if joined in STOPLIST or " ".join(tokens) in STOPLIST:
        return None
    if LATIN_ONLY.match(joined):
        if len(joined) < 3:
            return None
        return "short" if len(joined) == 3 else "ok"
    if HANGUL_ONLY.match(joined) and len(joined) == 2:
        return "short"
    return "ok"


def _credit_position(text, start, end):
    """짧은 이름이 '팀 이름 자리'에 있는지: 제목 맨 앞(앞머리 [태그] 제외)이거나 구분 기호 옆."""
    prefix = text[:start]
    if LEADING_TAGS.match(prefix):
        return True
    before = prefix.rstrip()[-1:]
    after = text[end:].lstrip()[:1]
    return before in SEP_BEFORE or after in SEP_AFTER or after == ""


class TitleMatcher:
    def __init__(self, teams):
        """teams: [(team_key, display_name), ...]"""
        self.display = {}
        owners = {}
        for key, display in teams:
            self.display.setdefault(key, display)
            for name in split_names(display):
                toks = _tokens(name)
                rule = name_rule(toks)
                if rule and len(toks) <= MAX_NAME_TOKENS:
                    owners.setdefault(toks, {}).setdefault(key, rule)
        # 같은 이름을 가진 팀이 둘 이상이면 어느 팀인지 알 수 없으니 버린다
        self.names = {toks: next(iter(o.items())) for toks, o in owners.items() if len(o) == 1}
        self.by_team = {}
        for toks, (key, _) in self.names.items():
            self.by_team.setdefault(key, []).append(toks)

    def searchable(self, team_key):
        return bool(self.by_team.get(team_key))

    def query_name(self, team_key):
        """검색어용 이름: 쓸 수 있는 이름 중 표시 이름에 먼저 나오는 것."""
        for name in split_names(self.display.get(team_key, "")):
            if _tokens(name) in self.names:
                return name
        return None

    def match(self, title, only=None):
        text = CREDIT_ONLY.sub(" ", html.unescape(title or "").lower())
        spans = [(m.group(0), m.start(), m.end()) for m in TOKEN.finditer(text)]
        words = [s[0] for s in spans]
        found = []
        for i in range(len(words)):
            for size in range(min(MAX_NAME_TOKENS, len(words) - i), 0, -1):
                hit = self.names.get(tuple(words[i:i + size]))
                if not hit:
                    continue
                key, rule = hit
                if only is not None and key != only:
                    continue
                if rule == "short" and not _credit_position(text, spans[i][1], spans[i + size - 1][2]):
                    continue
                found.append((i, i + size, key))
        # 겹치면 긴 이름 우선
        chosen, used = [], set()
        for start, stop, key in sorted(found, key=lambda f: (f[0] - f[1], f[0])):
            if used.isdisjoint(range(start, stop)):
                used.update(range(start, stop))
                chosen.append((start, key))
        result = []
        for _, key in sorted(chosen):
            item = (key, self.display[key])
            if item not in result:
                result.append(item)
        return result


# ---------- 행 만들기·저장 ----------

def make_row(now, team_key, display_name, video_id, title, channel_title, channel_id, published_at, kind, handle):
    return {"collected_at": now.isoformat(timespec="seconds"), "team_key": team_key, "display_name": display_name,
            "video_id": video_id, "title": html.unescape(title or ""), "channel_title": channel_title or "",
            "channel_id": channel_id or "", "published_at": published_at or "", "kind": kind,
            "source_channel_handle": handle or ""}


def dedupe(rows):
    seen, out = set(), []
    for r in rows:
        k = (r["team_key"], r["video_id"])
        if k in seen or not valid_video_id(r["video_id"]):
            continue
        seen.add(k)
        out.append(r)
    return out


def write_rows(path, rows):
    """같은 날 파일이 있으면 합쳐서 (team_key, video_id)로 중복을 뺀다. 먼저 있던 행이 남는다."""
    path = Path(path)
    existing = []
    if path.exists():
        with open(path, encoding="utf-8", newline="") as fh:
            existing = list(csv.DictReader(fh))
    merged = dedupe(existing + list(rows))
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(merged)
    return merged


def _iso_utc(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _item_video(item):
    sn, cd = item.get("snippet") or {}, item.get("contentDetails") or {}
    vid = cd.get("videoId") or (sn.get("resourceId") or {}).get("videoId", "")
    published = cd.get("videoPublishedAt", "")   # 비공개·삭제 영상은 비어 있다
    return vid, sn.get("title", ""), published, sn


# ---------- 1) 무대 채널 훑기 ----------

def sweep_channel(client, channel, matcher, state, now):
    handle = channel["handle"]
    mark = state.setdefault("channels", {}).setdefault(handle, {})
    cutoff = mark.get("last_published") or _iso_utc(now - timedelta(days=FIRST_RUN_DAYS))
    newest = mark.get("last_published", "")
    rows, token = [], None
    for _ in range(channel.get("max_pages", DEFAULT_MAX_PAGES)):
        params = {"part": "snippet,contentDetails", "playlistId": channel["uploads"], "maxResults": PAGE_SIZE}
        if token:
            params["pageToken"] = token
        try:
            body = client.get("playlistItems", params, COST_LIST)
        except QuotaExceeded as e:
            raise QuotaExceeded(str(e), rows) from None
        reached_old = False
        for item in body.get("items", []):
            vid, title, published, sn = _item_video(item)
            if not published or not valid_video_id(vid):
                continue
            if published <= cutoff:
                reached_old = True
                continue
            newest = max(newest, published)
            if FANCAM.search(title):
                continue
            for key, display in matcher.match(title):
                rows.append(make_row(now, key, display, vid, title, sn.get("channelTitle") or channel.get("name"),
                                     sn.get("channelId") or channel.get("channel_id"), published, "stage", handle))
        token = body.get("nextPageToken")
        if reached_old or not token:
            break
    mark["last_published"] = newest or mark.get("last_published", "")
    mark["swept_at"] = now.isoformat(timespec="seconds")
    return rows


# ---------- 1-b) 과거 업로드 백필 (--backfill) ----------

BACKFILL_UNTIL = "2021-01-01"


def backfill_channel(client, channel, matcher, state, now, until=BACKFILL_UNTIL):
    """업로드 목록을 최신→과거로 넘기며 until 날짜까지 무대 영상을 모은다 (50개당 1단위).
    채널마다 '다음 쪽 위치(page_token)'를 state['backfill'][handle]에 저장해, 예산에 닿으면 다음 실행에 이어받는다.
    매일 훑기 표시(state['channels'])는 건드리지 않는다. until 보다 오래된 영상을 만나면 그 채널은 끝(done)."""
    handle = channel["handle"]
    mark = state.setdefault("backfill", {}).setdefault(handle, {})
    if mark.get("done"):
        return []
    cutoff = f"{until}T00:00:00Z"
    token = mark.get("page_token") or None
    rows = []
    while True:
        params = {"part": "snippet,contentDetails", "playlistId": channel["uploads"], "maxResults": PAGE_SIZE}
        if token:
            params["pageToken"] = token
        try:
            body = client.get("playlistItems", params, COST_LIST)
        except QuotaExceeded as e:
            raise QuotaExceeded(str(e), rows) from None
        reached_old = False
        for item in body.get("items", []):
            vid, title, published, sn = _item_video(item)
            if not published or not valid_video_id(vid):
                continue
            mark["oldest_seen"] = min(mark.get("oldest_seen") or published, published)
            if published < cutoff:
                reached_old = True
                continue
            if FANCAM.search(title):
                continue
            for key, display in matcher.match(title):
                rows.append(make_row(now, key, display, vid, title, sn.get("channelTitle") or channel.get("name"),
                                     sn.get("channelId") or channel.get("channel_id"), published, "stage", handle))
        token = body.get("nextPageToken")
        mark["pages"] = mark.get("pages", 0) + 1
        mark["page_token"] = token or ""
        mark["backfilled_at"] = now.isoformat(timespec="seconds")
        if reached_old or not token:
            mark["done"] = True
            mark["page_token"] = ""
            return rows


def backfill_order(channels):
    """업로드가 아주 많은 채널(max_pages 를 크게 잡은 KBS 등, 대부분 아이돌 무대)은 뒤로 — 인디 채널부터 끝낸다."""
    return sorted(channels, key=lambda c: c.get("max_pages", DEFAULT_MAX_PAGES) > DEFAULT_MAX_PAGES)


def backfill(client, matcher, channels, state, now, until, save):
    """모든 무대 채널을 차례로 백필. 예산에 닿으면 그때까지 저장하고 멈춘다. (행 목록, 멈췄는지)."""
    rows, stopped = [], False
    for ch in backfill_order(channels):
        try:
            rows += backfill_channel(client, ch, matcher, state, now, until)
        except QuotaExceeded as e:
            rows += e.rows
            stopped = True
            save()
            break
        except YouTubeError as e:   # 오래된 쪽 위치가 만료되면 다음 실행은 처음부터 (비용이 작음)
            print(f"⚠️ 백필 실패: {ch.get('name')} ({e}) — 다음 실행에서 처음부터 다시")
            state.setdefault("backfill", {}).setdefault(ch["handle"], {})["page_token"] = ""
        save()
    return rows, stopped


# ---------- 2) 팀 공식 채널 ----------

def _lookup_uploads(client, params):
    body = client.get("channels", {"part": "contentDetails", **params}, COST_LIST)
    items = body.get("items") or []
    return items[0]["contentDetails"]["relatedPlaylists"]["uploads"] if items else ""


def resolve_uploads(client, url, state):
    cache = state.setdefault("resolved", {})
    if url in cache:
        return cache[url]
    parsed = parse_youtube_url(url)
    uploads = ""
    if parsed:
        kind, value = parsed
        if kind == "id":
            uploads = "UU" + value[2:]   # 업로드 목록 ID는 채널 ID의 UC를 UU로 바꾼 것 (요청 0단위)
        elif kind == "handle":
            uploads = _lookup_uploads(client, {"forHandle": value})
        elif kind == "user":
            uploads = _lookup_uploads(client, {"forUsername": value})
        else:
            uploads = _lookup_uploads(client, {"forHandle": "@" + value}) or \
                _lookup_uploads(client, {"forUsername": value})
    cache[url] = uploads   # 못 찾은 것도 ""로 저장해 매일 비용을 쓰지 않는다
    return uploads


def official_videos(client, team_key, display_name, url, state, now):
    uploads = resolve_uploads(client, url, state)
    if not uploads:
        return []
    try:
        body = client.get("playlistItems", {"part": "snippet,contentDetails", "playlistId": uploads,
                                            "maxResults": OFFICIAL_LATEST}, COST_LIST)
    except YouTubeError as e:
        if e.status == 404 and e.reason == "playlistNotFound":
            state.setdefault("resolved", {})[url] = ""   # 업로드 목록이 없는 채널 → 다음부터 건너뜀
        raise
    handle = (parse_youtube_url(url) or ("", ""))[1]
    rows = []
    for item in body.get("items", []):
        vid, title, published, sn = _item_video(item)
        if not published or not valid_video_id(vid):
            continue
        kind = "official_live" if LIVE_WORDS.search(title) else "official"
        rows.append(make_row(now, team_key, display_name, vid, title, sn.get("channelTitle"),
                             sn.get("channelId"), published, kind, handle))
    return rows


# ---------- 3) 후보 검색 ----------

def pick_search_teams(ranked_keys, state, today, n, matcher):
    searched = state.get("searched", {})
    picked = []
    for key in ranked_keys:
        last = searched.get(key)
        if last and (today - date.fromisoformat(last)).days < SEARCH_REPEAT_DAYS:
            continue
        if not matcher.searchable(key) or key in picked:
            continue
        picked.append(key)
        if len(picked) >= n:
            break
    return picked


def run_search(client, matcher, ranked_keys, state, now, n=SEARCH_N):
    today = now.date()
    after = _iso_utc(now - timedelta(days=SEARCH_DAYS))
    rows = []
    for key in pick_search_teams(ranked_keys, state, today, n, matcher):
        if not client.quota.can(COST_SEARCH):
            break
        params = {"part": "snippet", "q": f"{matcher.query_name(key)} 라이브", "type": "video",
                  "order": "relevance", "publishedAfter": after, "regionCode": "KR", "maxResults": SEARCH_RESULTS}
        try:
            body = client.get("search", params, COST_SEARCH)
        except QuotaExceeded:
            break
        except YouTubeError as e:
            print(f"⚠️ 검색 실패: {key} ({e})")
            continue
        state.setdefault("searched", {})[key] = today.isoformat()
        for item in body.get("items", []):
            vid = (item.get("id") or {}).get("videoId", "")
            sn = item.get("snippet") or {}
            for k, display in matcher.match(sn.get("title", ""), only=key):
                rows.append(make_row(now, k, display, vid, sn.get("title"), sn.get("channelTitle"),
                                     sn.get("channelId"), sn.get("publishedAt"), "search", ""))
    return rows


# ---------- 입력 파일 ----------

def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def load_teams(path):
    return [(r["team_key"], r["display_name"]) for r in read_csv(path) if r.get("team_key")]


def load_ranked(snap_dir):
    snaps = sorted(p for p in Path(snap_dir).glob("*.csv") if re.fullmatch(r"\d{4}-\d{2}-\d{2}\.csv", p.name))
    if not snaps:
        return []
    rows = read_csv(snaps[-1])
    rows.sort(key=lambda r: int(r.get("rank") or 10 ** 9))
    return [r["team_key"] for r in rows]


# ---------- 실행 ----------

def collect(client, matcher, channels, links, ranked, state, now, search_n, save):
    """세 단계를 차례로. 예산에 닿으면 남은 단계는 건너뛴다. (행 목록, 멈췄는지) 를 돌려준다."""
    rows, stopped = [], False
    for ch in channels:
        try:
            rows += sweep_channel(client, ch, matcher, state, now)
        except QuotaExceeded as e:
            rows += e.rows
            stopped = True
            break
        except YouTubeError as e:
            print(f"⚠️ 채널 훑기 실패: {ch.get('name')} ({e})")
    save()
    if not stopped:
        for team_key, url in links:
            try:
                rows += official_videos(client, team_key, matcher.display.get(team_key, team_key), url, state, now)
            except QuotaExceeded:
                stopped = True
                break
            except YouTubeError as e:
                print(f"⚠️ 공식 채널 실패: {team_key} ({e})")
        save()
    if not stopped and search_n > 0:
        rows += run_search(client, matcher, ranked, state, now, n=search_n)
        stopped = not client.quota.can(COST_SEARCH)
        save()
    return rows, stopped


def summarize(rows, used, budget, stopped):
    kinds = Counter(r["kind"] for r in rows)
    teams = {r["team_key"] for r in rows}
    print(f"사용한 단위: {used} / 예산 {budget}" + (" (예산에 닿아 멈춤 → 내일 이어서)" if stopped else ""))
    for kind in ("stage", "official_live", "official", "search"):
        print(f"  {kind}: {kinds.get(kind, 0)}개")
    print(f"영상이 1개 이상 있는 팀: {len(teams)}팀")


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="유튜브 최근 무대 영상 수집 (YouTube Data API v3)")
    ap.add_argument("--budget", type=int, default=DEFAULT_BUDGET, help="이번 실행에 쓸 최대 단위 (기본 5000)")
    ap.add_argument("--search-n", type=int, default=SEARCH_N, help="검색할 상위 후보 팀 수 (기본 40)")
    ap.add_argument("--no-search", action="store_true", help="검색 단계 건너뛰기")
    ap.add_argument("--backfill", action="store_true",
                    help="과거 업로드 백필만: 무대 채널 업로드 목록을 --until 날짜까지 (50개당 1단위, 예산에 닿으면 다음 실행에 이어받기)")
    ap.add_argument("--until", default=BACKFILL_UNTIL, help=f"백필할 가장 오래된 날짜 (기본 {BACKFILL_UNTIL})")
    args = ap.parse_args(argv)
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", args.until):
        ap.error("--until 은 YYYY-MM-DD 형식")
    return args


def run_backfill(client, matcher, channels, state, now, until):
    rows, stopped = backfill(client, matcher, channels, state, now, until, lambda: save_state(STATE_FILE, state))
    out = RAW_DIR / f"raw_video_{now.date().isoformat()}.csv"
    written = write_rows(out, rows)
    marks = state.get("backfill", {})
    done = sum(1 for c in channels if marks.get(c["handle"], {}).get("done"))
    print(f"저장: {out.relative_to(ROOT)} (백필 {len(dedupe(rows))}줄, 파일 전체 {len(written)}줄)")
    print(f"사용한 단위: {client.quota.used} / 예산 {client.quota.budget}" + (" (예산에 닿아 멈춤 → 다음 실행에 이어서)" if stopped else ""))
    print(f"백필 끝난 채널 {done}/{len(channels)}: " + ", ".join(
        f"{c.get('name')} {'완료' if marks.get(c['handle'], {}).get('done') else '진행 중'}"
        f"(가장 오래된 {marks.get(c['handle'], {}).get('oldest_seen', '-')[:10]})" for c in backfill_order(channels)))
    return 0


def main(argv=None):
    args = parse_args(argv)

    env = load_env(ENV_FILE)
    try:
        client = YouTubeClient(env.get("YOUTUBE_API_KEY"), quota=Quota(args.budget))
    except YouTubeError as e:
        print(f"❌ {e}")
        return 1
    now = datetime.now(KST)
    matcher = TitleMatcher(load_teams(LAB_DATA / "teams.csv"))
    config = json.loads(CHANNELS_FILE.read_text(encoding="utf-8"))
    channels = [c for c in config["channels"] if c.get("uploads")]
    links = [(r["team_key"], r["url"]) for r in read_csv(LAB_DATA / "links.csv") if r.get("platform") == "youtube"]
    ranked = load_ranked(LAB_DATA / "snapshots")
    state = load_state(STATE_FILE)
    if args.backfill:
        return run_backfill(client, matcher, channels, state, now, args.until)

    rows, stopped = collect(client, matcher, channels, links, ranked, state, now,
                            0 if args.no_search else args.search_n, lambda: save_state(STATE_FILE, state))
    out = RAW_DIR / f"raw_video_{now.date().isoformat()}.csv"
    written = write_rows(out, rows)
    new_rows = dedupe(rows)
    print(f"저장: {out.relative_to(ROOT)} (이번 실행 {len(new_rows)}줄, 파일 전체 {len(written)}줄)")
    summarize(new_rows, client.quota.used, args.budget, stopped)
    return 0


if __name__ == "__main__":
    sys.exit(main())
