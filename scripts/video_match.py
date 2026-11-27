"""영상 제목 ↔ 팀 이름 대조 규칙 — 수집(collect_videos)과 내보내기(export_lab_data) 가 같은 규칙을 쓴다.

- 이름 맞추기는 보수적으로: 잘못 붙는 것이 놓치는 것보다 나쁘다.
- 흔한 낱말: 코드의 기본 목록(STOPLIST) + config/video_common_words.json 의 수동 목록(common). allow 는 거기서 빼 준다.
  빈도로 뽑은 자동 후보(auto_common: 여러 번 나오는데 거의 늘 문장 가운데 나오는 긴 이름)는 보고만 하고 바로 쓰지 않는다
  — 처음 돌려 보니 '아디오스오디오 Adios Audio /' 처럼 진짜 팀도 섞여서, 사람이 보고 common 으로 옮긴다.
  보기: python3 scripts/video_match.py  (거르기 전후 줄 수·많이 걸러진 팀·자동 후보와 예시 제목)
- 짧은 이름(한글 2자 이하·영문 3자 이하)은 낱말 전체가 같고, '팀 이름 자리'에 있을 때만 인정:
  제목 맨 앞(앞머리 [태그] 제외)이나 구분 기호 뒤에 있으면서 뒤도 구분 기호·괄호·제목 끝이거나, [팀명] 처럼 괄호로 감싼 형식.
  팀 공식 채널 영상(kind=official·official_live)은 채널 자체가 근거라 제목 검사를 하지 않는다.
- 원본 raw_video 파일은 그대로 두고, 내보낼 때 filter_rows 로 다시 걸러낸다 (규칙을 바꿔도 다시 수집할 필요 없음).
"""
import csv
import html
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMMON_FILE = ROOT / "config" / "video_common_words.json"
RAW_DIR = ROOT / "data" / "raw"
OFFICIAL_KINDS = {"official", "official_live"}
AUTO_MIN_HITS = 10            # 자동 후보: 이만큼 이상 나온 이름 중
AUTO_MAX_ARTIST_SHARE = 0.1   # '팀 이름 자리'에 나온 비율이 이 이하이면 흔한 낱말 후보

TRAILING_ALIAS = re.compile(r"^(.*?)\s*[\(\[（]([^\)\]）]+)[\)\]）]\s*$")
TOKEN = re.compile(r"[0-9a-z가-힣ㄱ-ㅎㅏ-ㅣ一-鿿ぁ-んァ-ヶー]+")
HANGUL_ONLY = re.compile(r"^[가-힣]+$")
LATIN_ONLY = re.compile(r"^[a-z]+$")
LEADING_TAGS = re.compile(r"^\s*(?:[\[【(（<][^\]】)）>]*[\]】)）>]\s*)*$")
# '(원곡: 팀)', 'Original by 팀', 'cover by 팀' 처럼 원곡자·만든 사람으로만 나온 부분은 지우고 맞춘다
CREDIT_ONLY = re.compile(r"(?:원곡|original(?:\s*(?:by|artist))?|cover(?:ed)?\s*by|prod\.?\s*by)\s*[:：.]?[^)\]|/]*", re.I)
SEP_BEFORE = set("-–—|:;/ㅣ│,&×")   # 가운데의 [ ( 뒤는 작품·프로그램 이름일 때가 많아 뺀다
SEP_AFTER = set("-–—|:;/ㅣ│,&×(（[【'\"‘’“”「『<")
OPEN_BRACKETS, CLOSE_BRACKETS = set("[【"), set("]】")
# 자동 후보 계산 때만 쓰는 너그러운 자리: 날짜(6자리) 뒤·# 뒤·괄호 속, 한글 이름 바로 뒤 영문 별칭
LOOSE_BEFORE = SEP_BEFORE | set("#(（[【")
LOOSE_AFTER = SEP_AFTER | set("#@)）]】")
DATE_BEFORE = re.compile(r"(?:^|\s)\d{6}\s*$")
LATIN_NEXT = re.compile(r"\s*[a-z]")

# 제목에 흔히 나오는 낱말이라 팀 이름으로 쓰면 잘못 붙는 것들 (팀 이름 쪽에서 제외)
STOPLIST = frozenset({
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
})


def tokens(text):
    return tuple(TOKEN.findall((text or "").lower()))


def joined(toks):
    return "".join(toks)


def split_names(display_name):
    """'사뮈 (Samui)' → ['사뮈', 'Samui']"""
    name = (display_name or "").strip()
    m = TRAILING_ALIAS.match(name)
    names = [m.group(1), m.group(2)] if m and m.group(1).strip() else [name]
    return [n.strip() for n in names if n.strip()]


def load_common(path=COMMON_FILE):
    """(흔한 낱말 집합, 허용 집합). 모두 소문자·띄어쓰기 없는 꼴. 파일이 없거나 깨지면 기본 목록만."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    allow = frozenset(joined(tokens(w)) for w in data.get("allow", []) if tokens(w))
    common = {joined(tokens(w)) for w in STOPLIST} | {joined(tokens(w)) for w in data.get("common", []) if tokens(w)}
    return frozenset(common - allow), allow


def is_short(toks):
    """한글 2자 이하·영문 3자 이하 이름."""
    j = joined(toks)
    return bool((HANGUL_ONLY.match(j) and len(j) <= 2) or (LATIN_ONLY.match(j) and len(j) <= 3))


def name_rule(toks, common=STOPLIST):
    """이름 낱말 묶음 → None(쓰지 않음) / 'short'(팀 이름 자리에서만) / 'ok'."""
    j = joined(toks)
    if not j or j.isdigit() or len(j) < 2:
        return None
    if j in common or " ".join(toks) in common:
        return None
    if LATIN_ONLY.match(j) and len(j) < 3:
        return None
    return "short" if is_short(toks) else "ok"


COLLAB_BEFORE = re.compile(r"\sx\s*$")    # 'A X B' 함께 무대 (제목은 소문자로 맞춘 뒤)
COLLAB_AFTER = re.compile(r"\s*x\s")
WORD_AT_END = re.compile(TOKEN.pattern + "$")


def _left_ok(prefix):
    """이름 앞이 '팀 이름 자리'인지: 맨 앞(태그 제외)·구분 기호 뒤·'X' 뒤·맨 앞 이름 바로 뒤 괄호 속 별칭."""
    before = prefix.rstrip()[-1:]
    if LEADING_TAGS.match(prefix) or (before != "" and before in SEP_BEFORE) or COLLAB_BEFORE.search(prefix):
        return True
    if prefix.endswith(("(", "（")):
        head = prefix[:-1].rstrip()                 # 'neu(노이' 와 'neu (노이' 둘 다
        m = WORD_AT_END.search(head)
        return bool(m) and _left_ok(head[:m.start()])
    return False


def artist_position(text, start, end):
    """text[start:end] 가 '팀 이름 자리'인지: [팀명] 형식이거나, 앞(맨 앞·구분 기호·X·별칭 괄호)과 뒤(구분 기호·괄호·X·제목 끝)가 모두 맞을 때."""
    before = text[:start].rstrip()[-1:]
    after = text[end:].lstrip()[:1]
    if before in OPEN_BRACKETS and after in CLOSE_BRACKETS and before:
        return True
    right = after == "" or after in SEP_AFTER or after in ")）" or bool(COLLAB_AFTER.match(text[end:]))
    return right and _left_ok(text[:start])


def loose_position(text, start, end, toks):
    """긴 이름용 너그러운 '팀 이름 자리' (자동 후보 계산에만)."""
    prefix = text[:start]
    before = prefix.rstrip()[-1:]
    after = text[end:].lstrip()[:1]
    left = bool(LEADING_TAGS.match(prefix)) or (before != "" and before in LOOSE_BEFORE) or bool(DATE_BEFORE.search(prefix))
    alias_next = bool(HANGUL_ONLY.match(joined(toks))) and bool(LATIN_NEXT.match(text[end:]))
    right = after == "" or after in LOOSE_AFTER or alias_next
    return left and right


def title_spans(title):
    """제목 → (지운 뒤 소문자 글, [(낱말, 시작, 끝)])."""
    text = CREDIT_ONLY.sub(" ", html.unescape(title or "").lower())
    return text, [(m.group(0), m.start(), m.end()) for m in TOKEN.finditer(text)]


def _occurrences(spans, toks):
    words = [s[0] for s in spans]
    n = len(toks)
    for i in range(len(words) - n + 1):
        if tuple(words[i:i + n]) == toks:
            yield spans[i][1], spans[i + n - 1][2]


def keep_row(row, common, allow, auto=frozenset()):
    """수집해 둔 영상 줄을 지금 규칙으로 다시 검사 — 팀 이름 중 하나라도 규칙대로 제목에 있으면 남긴다."""
    if row.get("kind") in OFFICIAL_KINDS:
        return True
    display = row.get("display_name")
    if not display:
        return True                      # 이름을 모르면 검사할 수 없으니 그대로 (옛 형식 줄)
    blocked = (common | auto) - allow
    text, spans = title_spans(row.get("title"))
    for name in split_names(display):
        toks = tokens(name)
        if name_rule(toks, blocked) is None:
            continue
        for start, end in _occurrences(spans, toks):
            if not is_short(toks) or artist_position(text, start, end):
                return True
    return False


def auto_common(rows, min_hits=AUTO_MIN_HITS, max_artist_share=AUTO_MAX_ARTIST_SHARE, allow=frozenset()):
    """빈도 기반 흔한 낱말 후보: 긴 이름 중 min_hits 번 이상 나왔는데 '팀 이름 자리' 비율이 max_artist_share 이하인 것."""
    hits, artist = Counter(), Counter()
    for r in rows:
        if r.get("kind") in OFFICIAL_KINDS or not r.get("display_name"):
            continue
        text, spans = title_spans(r.get("title"))
        for name in split_names(r["display_name"]):
            toks = tokens(name)
            if name_rule(toks, frozenset()) is None or is_short(toks):
                continue
            occ = list(_occurrences(spans, toks))
            if not occ:
                continue
            hits[joined(toks)] += 1
            if any(artist_position(text, s, e) or loose_position(text, s, e, toks) for s, e in occ):
                artist[joined(toks)] += 1
    return frozenset(k for k, n in hits.items()
                     if n >= min_hits and artist[k] / n <= max_artist_share and k not in allow)


def filter_rows(rows, common=None, allow=None, auto=frozenset()):
    """영상 줄 거르기 → (남은 줄, 보고 {before, after, auto_candidates, dropped_by_team}).
    auto 는 따로 넘길 때만 적용. 자동 후보는 이미 흔한 낱말 목록에 있는 것을 빼고 보고만 한다."""
    if common is None or allow is None:
        file_common, file_allow = load_common()
        common = file_common if common is None else common
        allow = file_allow if allow is None else allow
    candidates = sorted(auto_common(rows, allow=allow) - common)
    kept, dropped = [], Counter()
    for r in rows:
        if keep_row(r, common, allow, auto):
            kept.append(r)
        else:
            dropped[r.get("team_key") or ""] += 1
    return kept, {"before": len(rows), "after": len(kept), "auto_candidates": candidates, "dropped_by_team": dropped}


def read_raw(raw_dir=RAW_DIR):
    rows = []
    for path in sorted(Path(raw_dir).glob("raw_video_2*.csv")):     # raw_video_stats_* 는 영상 목록이 아님
        with open(path, encoding="utf-8") as f:
            rows.extend(csv.DictReader(f))
    return rows


def main():
    rows = read_raw()
    kept, report = filter_rows(rows)
    print(f"영상 줄: 거르기 전 {report['before']:,} → 후 {report['after']:,} (뺀 줄 {report['before'] - report['after']:,})")
    print("많이 걸러진 팀: " + ", ".join(f"{k} {n}" for k, n in report["dropped_by_team"].most_common(20)))
    if report["auto_candidates"]:
        print("흔한 낱말 자동 후보 (보고 config/video_common_words.json 의 common 또는 allow 로 옮기기):")
        for name in report["auto_candidates"]:
            titles = [r["title"] for r in rows if name in {joined(tokens(n)) for n in split_names(r.get("display_name"))}]
            print(f"  {name} ({len(titles)}줄) 예: " + " / ".join(t[:50] for t in titles[:2]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
