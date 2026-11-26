"""이름 정규화 키 — 플랫폼마다 다른 표기를 같은 팀·같은 앨범으로 묶기 위한 1차 기준.

- artist_key: 이름 끝 괄호 속 별칭(영문 표기 등)을 빼고 ('(여자)아이들'처럼 앞 괄호는 이름의 일부로 둠), 공백·기호를 지우고, 소문자로.
  "오존(O3ohn)" → "오존", "스트레인지 프룻" = "스트레인지프룻"
- title_key: feat. 표기만 빼고(버전 표기는 남김) 공백·기호를 지우고 소문자로.
- platforms_seen: (artist_key, title_key)마다 몇 개 플랫폼에 올라왔는지.

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
