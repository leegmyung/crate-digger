"""장르 빈칸 채우기 + 확신도(genre_confidence) — docs/genre_fill.md.

팀 표(teams.csv)의 대표 장르가 93% 빈칸이라 장르 안 비교·필터가 무너진다(경쟁 서비스 Viberate 도 장르 오분류가 비교를 망침).
확신도 순서대로 채운다:
  profile  = 멜론 프로필·발매 장르, 사람이 확인한 장르(config/genre_overrides.json)
  press    = 오탐이 적은 출처 힌트(build_dashboard_data._infer_genres: 리드머 → 힙합, 밴드 디스커버리 → 록·밴드)
  inferred = 빈칸에만, 아래 순서로 처음 결정되는 것
             ① 같은 무대 다수결: 같은 날·같은 공연장에 선 팀들의 장르 — 2표 이상, 60% 이상
             ② 공연장 성향: 그 팀이 선 공연장들의 장르 분포(투표자 5팀 이상인 공연장만, 공연장마다 같은 무게) — 70% 이상
             ③ 약한 출처 힌트: 힙합엘 기사 → '힙합·R&B'(넓은 묶음 — 힙합만 47%, 힙합·R&B 합치면 78%),
                유재하 경연 본선 → 포크·싱어송라이터 (65%)
  review   = 위로도 못 정한 팀의 매체 리뷰 장르(음악취향Y '장르'·overtone 'Genre'·VISLA 장르 태그). 맞는 비율 53%(멜론 장르
             중 하나와 76%)로 같은 무대 다수결(69%)보다 낮아 press 가 아님(2026-11-28 결정). 리뷰 장르가 같은 무대 1표와 같으면 inferred.
  inferred_low = 위로도 못 정한 팀 중 같은 무대에 장르 아는 팀이 딱 1팀뿐일 때 그 장르 (확신 낮음)
우선순위: profile > press > inferred > review > inferred_low. review·inferred·inferred_low 는 앱 필터·표시에만('추정' 꼬리표),
비교·분석(peer_compare·genre_bias·장르별 성적표)에서는 '미분류'로 센다.
투표는 profile·press 팀만 한다 — 추정한 장르로 다시 추정하지 않는다(순환 방지, 한 번만 계산).
정답(검증용) 정보는 쓰지 않는다: 공연 신호와 신호 출처만 보고, 정답 프로그램(csv_schema.OUTCOME_TIER)은 힌트에서 뺀다.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Dict, Iterable, List, Mapping, Sequence, Set, Tuple

import csv_schema
import genre as genre_mod
from build_dashboard_data import _infer_genres, _split_lower

PROFILE, PRESS, INFERRED, REVIEW, INFERRED_LOW = "profile", "press", "inferred", "review", "inferred_low"
ANALYSIS_LEVELS = ("", PROFILE, PRESS)   # 비교·분석(peer_compare·genre_bias)이 쓰는 확신도 — 나머지(추정·리뷰)는 '미분류'로
VOTER_LEVELS = (PROFILE, PRESS)
MIN_VOTES = 2            # 같은 무대 다수결: 최소 표 수
MIN_SHARE = 0.6          # 같은 무대 다수결: 1등 장르 비율 하한
VENUE_MIN_SHARE = 0.7    # 공연장 성향: 1등 장르 비율 하한 (60%면 맞는 비율 51% — '모두 록' 기준선 46%와 비슷해서 올림)
VENUE_MIN_VOTERS = 5     # 공연장 성향을 믿을 최소 투표자(장르 아는 팀) 수
NO_VENUE = ("", "공연장 미정")
# 약한 출처 힌트 (신호 출처만, 순서 = 우선순위). 값 = 장르 지도 갈래 키 또는 넓은 묶음 이름.
# 멜론 장르가 있는 팀으로 잰 맞는 비율: 힙합엘 힙합 47%·힙합/R&B 78% → 넓은 묶음, 유재하 본선 포크 65% — docs/genre_fill.md
HIPHOP_RNB = "힙합·R&B"                               # 넓은 묶음: 힙합 또는 R&B·소울 (어느 쪽인지 모름)
BROAD_MEMBERS = {HIPHOP_RNB: ("hiphop", "rnb")}      # 넓은 묶음 → 들어 있는 갈래 키 (맞는 비율 셀 때)
WEAK_PRESS = {"hiphople": HIPHOP_RNB}
WEAK_PROGRAMS = {"yoojaeha_finalist": "folk"}

Gig = Tuple[str, str]   # (날짜, 공연장)


def _labels() -> Dict[str, str]:
    return {k: b["label"] for k, b in genre_mod.load_config()["buckets"].items()}


def base_genre(raw_genres, press_sources="", sel_programs="") -> Tuple[str, str]:
    """(대표 장르, 확신도) — 플랫폼 장르가 있으면 profile, 확실한 출처 힌트만 있으면 press, 없으면 ('', '')."""
    labels = _labels()
    raw = [labels[b] for b in genre_mod.buckets_of(str(raw_genres or "")) if b in labels]
    if raw:
        return raw[0], PROFILE
    hinted = _infer_genres("", press_sources, sel_programs)
    return (hinted[0], PRESS) if hinted else ("", "")


def review_genres(rows: Iterable[Mapping]) -> Dict[str, str]:
    """도우미 열 press_genres(매체 리뷰 장르 '|' 구분)가 있는 팀 행 → {팀: 첫 갈래 이름}. 갈래로 못 묶는 글자는 뺀다."""
    labels = _labels()
    out = {}
    for r in rows:
        got = [labels[b] for b in genre_mod.buckets_of(str(r.get("press_genres") or "")) if b in labels]
        if got:
            out[str(r.get("team_key"))] = got[0]
    return out


def weak_hints(rows: Iterable[Mapping]) -> Dict[str, str]:
    """도우미 열(press_sources·sel_programs)이 있는 팀 행 → {팀: 약한 힌트 장르}. 정답 프로그램은 힌트가 아니다."""
    labels = _labels()
    order = [*WEAK_PRESS.values(), *WEAK_PROGRAMS.values()]
    out = {}
    for r in rows:
        press = _split_lower(r.get("press_sources"))
        progs = [p for p in _split_lower(r.get("sel_programs")) if p not in csv_schema.OUTCOME_TIER]
        found = [WEAK_PRESS[s] for s in press if s in WEAK_PRESS] + [WEAK_PROGRAMS[p] for p in progs if p in WEAK_PROGRAMS]
        best = min(found, key=order.index) if found else ""
        if best in labels or best in BROAD_MEMBERS:
            out[str(r.get("team_key"))] = labels.get(best, best)
    return out


class _Votes:
    """공연 신호에서 같은 무대·공연장 투표 재료를 한 번 만들어 둔다."""

    def __init__(self, teams: Sequence[Mapping], signals: Iterable[Mapping]):
        self.voters = {str(t["team_key"]): str(t["primary_genre"]) for t in teams
                       if t.get("primary_genre") and t.get("genre_confidence") in VOTER_LEVELS}
        self.nights: Dict[Gig, Set[str]] = defaultdict(set)
        self.team_gigs: Dict[str, Set[Gig]] = defaultdict(set)
        for s in signals:
            venue = str(s.get("venue") or "").strip()
            if s.get("branch") != "공연" or s.get("role") == "excluded" or venue in NO_VENUE:
                continue
            gig = (str(s.get("signal_date") or ""), venue)
            self.nights[gig].add(str(s["team_key"]))
            self.team_gigs[str(s["team_key"])].add(gig)
        venue_teams: Dict[str, Set[str]] = defaultdict(set)
        for (_, venue), ts in self.nights.items():
            venue_teams[venue] |= ts
        self.venue_genres = {v: Counter(self.voters[k] for k in ts if k in self.voters) for v, ts in venue_teams.items()}

    def _neighbor_votes(self, key: str) -> Counter:
        co = {o for gig in self.team_gigs.get(key, ()) for o in self.nights[gig] if o != key and o in self.voters}
        return Counter(self.voters[o] for o in co)

    def neighbor(self, key: str) -> str:
        """같은 날·같은 공연장에 선 다른 투표자들의 장르 (한 팀은 한 표)."""
        votes = self._neighbor_votes(key)
        if not votes:
            return ""
        top, n = votes.most_common(1)[0]
        return top if n >= MIN_VOTES and n / sum(votes.values()) >= MIN_SHARE else ""

    def single_vote(self, key: str) -> str:
        """같은 무대에 장르 아는 팀이 딱 1팀뿐이면 그 장르 (확신 낮음)."""
        votes = self._neighbor_votes(key)
        return next(iter(votes)) if sum(votes.values()) == 1 else ""

    def venue(self, key: str) -> str:
        """그 팀이 선 공연장들의 장르 분포를 공연장마다 같은 무게로 합친 1등 (자기 표는 뺌)."""
        total: Counter = Counter()
        for venue in {v for _, v in self.team_gigs.get(key, ())}:
            dist = Counter(self.venue_genres.get(venue, {}))
            if key in self.voters:
                dist[self.voters[key]] -= 1
            n = sum(dist.values())
            if n >= VENUE_MIN_VOTERS:
                for genre, c in dist.items():
                    total[genre] += c / n
        if not total:
            return ""
        top, score = total.most_common(1)[0]
        return top if score / sum(total.values()) >= VENUE_MIN_SHARE else ""

    def infer(self, key: str, hints: Mapping[str, str], reviews: Mapping[str, str] = None) -> Tuple[str, str]:
        """(장르, 방법) — 방법 = neighbor · venue · hint · review_agree(리뷰 = 같은 무대 1표) · review · single, 못 정하면 ('', '')."""
        reviews = reviews or {}
        for method, fn in (("neighbor", self.neighbor), ("venue", self.venue), ("hint", lambda k: hints.get(k, ""))):
            guess = fn(key)
            if guess:
                return guess, method
        single, review = self.single_vote(key), reviews.get(key, "")
        if review:
            return review, ("review_agree" if review == single else "review")
        return (single, "single") if single else ("", "")


def _members(guess: str) -> Set[str]:
    """추정 장르가 뜻하는 대표 장르 이름들 (넓은 묶음이면 여러 개)."""
    labels = _labels()
    return {labels[k] for k in BROAD_MEMBERS[guess] if k in labels} if guess in BROAD_MEMBERS else {guess}


METHOD_LEVEL = {"neighbor": INFERRED, "venue": INFERRED, "hint": INFERRED, "review_agree": INFERRED,
                "review": REVIEW, "single": INFERRED_LOW}


def fill_genres(teams: Sequence[Mapping], signals: Iterable[Mapping], hints: Mapping[str, str],
                reviews: Mapping[str, str] = None) -> List[dict]:
    """빈칸 팀에 추정·리뷰 장르를 채운 새 목록. 장르가 있는 팀·입력 목록은 바꾸지 않는다."""
    votes = _Votes(teams, signals)
    out = []
    for t in teams:
        row = dict(t)
        if not row.get("primary_genre"):
            guess, method = votes.infer(str(row["team_key"]), hints, reviews)
            row["primary_genre"], row["genre_confidence"] = guess, (METHOD_LEVEL[method] if guess else "")
        out.append(row)
    return out


def evaluate(teams: Sequence[Mapping], signals: Iterable[Mapping], hints: Mapping[str, str],
             reviews: Mapping[str, str] = None) -> Dict[str, Dict[str, int]]:
    """profile 팀의 장르를 가리고 추정해 맞는 비율을 잰다(자기 표는 빠짐) → {방법: {n, correct}, 'all': …}."""
    votes = _Votes(teams, signals)
    rep = {m: {"n": 0, "correct": 0} for m in ("neighbor", "venue", "hint", "review_agree", "review", "single", "all")}
    for t in teams:
        if t.get("genre_confidence") != PROFILE or not t.get("primary_genre"):
            continue
        guess, method = votes.infer(str(t["team_key"]), hints, reviews)
        if not guess:
            continue
        hit = int(t["primary_genre"] in _members(guess))
        for m in (method, "all"):
            rep[m]["n"] += 1
            rep[m]["correct"] += hit
    return rep
