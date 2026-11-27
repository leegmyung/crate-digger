"""이름 정규화 키 — 플랫폼마다 다른 표기를 같은 팀·같은 앨범으로 묶기 위한 1차 기준.

- artist_key: 이름 끝 괄호 속 별칭(영문 표기 등)을 빼고 ('(여자)아이들'처럼 앞 괄호는 이름의 일부로 둠), 공백·기호를 지우고, 소문자로.
  "오존(O3ohn)" → "오존", "스트레인지 프룻" = "스트레인지프룻"
- title_key: feat. 표기만 빼고(버전 표기는 남김) 공백·기호를 지우고 소문자로.
- platforms_seen: (artist_key, title_key)마다 몇 개 플랫폼에 올라왔는지.
- split_artist_cell: 한 칸에 쉼표로 이어 쓴 여러 팀 → 팀별 이름 (이름 자체에 쉼표가 있는 팀은 그대로, 문장·레이블 조각은 버림).

정식 이름 맞추기(동명 팀 구분, 한/영 표기 연결)는 2단계 검수에서 한다. 여기 키는 그 출발점이다.
(scripts/build_reco.py 의 artist_key 는 예전 추천 실험용 SQL 규칙이라 따로 둔다.)
"""
import re
from collections import defaultdict

TRAILING_ALIAS = re.compile(r"\s*[\(\[\{（【][^\)\]\}）】]*[\)\]\}）】]\s*$")   # 끝에 붙은 별칭만
FEAT = re.compile(r"\s*[\(\[]\s*(?:feat|ft|with)\.?\s[^\)\]]*[\)\]]", re.I)
NOT_WORD = re.compile(r"[^0-9a-z가-힣ㄱ-ㅎㅏ-ㅣ一-龥ぁ-んァ-ン]+")


def _squash(text):
    return NOT_WORD.sub("", (text or "").lower())


def artist_key(name):
    name = (name or "").strip()
    without_alias = _squash(TRAILING_ALIAS.sub("", name))
    return without_alias or _squash(name)


# 이름 자체에 쉼표가 들어 있는 팀 (나누면 안 됨) — 비교는 소문자로
COMMA_NAMES = frozenset(n.lower() for n in (
    "Tyler, The Creator", "Mandy, Indiana", "Black Country, New Road", "Earth, Wind & Fire",
    "Crosby, Stills, Nash & Young", "Emerson, Lake & Palmer", "Peter, Paul and Mary", "Moon, Night & Starts"))
LABEL_PIECE = re.compile(r"(?:레코즈|레코드|레이블|엔터테인먼트|records?|label|entertainment)$", re.I)
HANGUL = re.compile(r"[가-힣]")
SPLIT_MAX_LEN = 40              # 조각이 이보다 길면 이름이 아니라 문장


def _split_outside_parens(text, sep=","):
    parts, depth, cur = [], 0, ""
    for ch in text:
        if ch in "([（":
            depth += 1
        elif ch in ")]）":
            depth -= 1
        if ch == sep and depth <= 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    return [p.strip() for p in parts if p.strip()]


def _name_like(piece):
    """이름 조각으로 볼 만한가: 너무 길지 않고, 한글 문장(띄어쓰기 3번 이상)이 아니고, 레이블 이름이 아님."""
    return (len(piece) <= SPLIT_MAX_LEN and not (HANGUL.search(piece) and piece.count(" ") >= 3)
            and not LABEL_PIECE.search(piece))


def split_artist_cell(text):
    """'SUMIN, Slom' → ['SUMIN', 'Slom'] · 'Tyler, The Creator' → 그대로 · 괄호 안 쉼표는 나누지 않음.
    나눈 조각 중 문장('데미지 없이도 끌어올린 타격감')·레이블('ScreaM Records')은 버린다. 빈 칸 → []."""
    text = (text or "").strip()
    if not text:
        return []
    if text.lower() in COMMA_NAMES:
        return [text]
    pieces = _split_outside_parens(text, ",")
    if len(pieces) <= 1:
        return [text]
    return [p for p in pieces if _name_like(p)]


def title_key(title):
    return _squash(FEAT.sub("", title or ""))


def platforms_seen(rows):
    """행 목록 → {(artist_key, title_key): [플랫폼, ...]} (정렬, 중복 없음)."""
    seen = defaultdict(set)
    for r in rows:
        a = r.get("artist_key") or artist_key(r.get("artist_text", ""))
        t = r.get("title_key") or title_key(r.get("title", ""))
        if a and t:
            seen[(a, t)].add(r.get("source", ""))
    return {k: sorted(v) for k, v in seen.items()}
