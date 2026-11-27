"""팀 신원 점검 → docs/identity_audit.md (계산만, 연결표·DB는 바꾸지 않음)

경쟁 서비스(Chartmetric·Viberate)는 플랫폼 번호로 아티스트를 묶는데, 우리 연결표(scripts/artist_xref.py)는 이름 중심이다.
1. 진단: 팀(대표 키)별 멜론 번호·스포티파이 번호·인스타 계정 보유율(전체·후보 상위 300·정답 팀),
   한 팀에 번호 여러 개 / 한 번호에 팀 여러 개 충돌, 근거가 이름뿐인 팀 비율, 이름으로 묶은 팀을 번호가 확인하는지.
2. '번호 먼저' 시뮬레이션: 번호가 같으면 이름이 달라도 같은 팀(공용·차단 번호 제외), 번호가 다르면 이름이 같아도
   다른 팀 의심 — 지금 연결표에 적용하면 몇 팀이 합쳐지고 갈라지는지.
입력은 artist_xref 와 같다(collect_inputs·load_curation, 읽기만). 결과 연결표 data/raw/state/artist_xref.json 을 읽는다.

실행: .venv/bin/python scripts/identity_audit.py
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import artist_xref as ax  # noqa: E402

ROOT = ax.ROOT
OUT = ROOT / "docs" / "identity_audit.md"
LAB_DATA = ROOT / "docs" / "lab" / "data"
REPO_URL = "https://github.com/leegmyung/crate-digger"
PLATFORMS = ax.PLATFORMS                      # ("melon", "spotify")
CONF_RANK = ax.CONF_RANK                      # high 3 · mid 2 · low 1
LINKED_IG = ("high", "mid")                   # 다른 소스와 이어진 인스타 계정만 '보유'로 셈
TOP_N = 300
EXAMPLES = 10

Record = Dict[str, str]


# ---------- 입력 다듬기 ----------

def usable_records(platform_ids: Iterable[Record], curation: dict) -> List[Record]:
    """플랫폼 번호 기록 중 쓸 수 있는 것: 사람이 고정한 번호를 더하고(artist_xref._pin_platform_ids), 공용 번호(0·1)와
    다른 아티스트로 확인된 번호(not)는 뺀다 — artist_xref.blocked_profile_rows 와 같은 목록."""
    pinned = ax._pin_platform_ids(list(platform_ids), curation.get("platform_ids", []))
    blocked = {(src, sid) for src, sid, _ in ax.blocked_profile_rows(curation)}
    return [r for r in pinned if (r["platform"], str(r["id"])) not in blocked and ax._usable_id(r["platform"], r["id"])]


def map_records(records: Iterable[Record], artists: Sequence[dict]) -> Tuple[List[dict], int]:
    """기록의 이름 → 연결표 대표 키(team)와 그 이름 자체의 키(variant). 연결표에 없는 이름은 센 수만 돌려준다."""
    index = ax.index_from_artists(list(artists))
    known = set(index["artists"])
    mapped, unmapped = [], 0
    for r in records:
        team = ax.canonical_key(r["name"], index)
        if team not in known:
            unmapped += 1
            continue
        variant = ax.artist_key(ax.parse_name(ax.clean(r["name"]))[0]) or team
        mapped.append({**r, "id": str(r["id"]), "team": team, "variant": variant})
    return mapped, unmapped


def _at_least(rows: Iterable[dict], min_conf: str) -> List[dict]:
    floor = CONF_RANK[min_conf]
    return [r for r in rows if CONF_RANK.get(r.get("confidence", "mid"), 2) >= floor]


# ---------- 진단 ----------

def id_conflicts(mapped: Iterable[dict], min_conf: str = "low") -> dict:
    """multi_id_teams[platform] = {팀: 번호들} (2개 이상) · multi_team_ids[(platform, 번호)] = 팀들 (2팀 이상)."""
    team_ids: Dict[str, Dict[str, Set[str]]] = {p: defaultdict(set) for p in PLATFORMS}
    id_teams: Dict[Tuple[str, str], Set[str]] = defaultdict(set)
    for r in _at_least(mapped, min_conf):
        team_ids[r["platform"]][r["team"]].add(r["id"])
        id_teams[(r["platform"], r["id"])].add(r["team"])
    return {"multi_id_teams": {p: {t: ids for t, ids in team_ids[p].items() if len(ids) > 1} for p in PLATFORMS},
            "multi_team_ids": {k: v for k, v in id_teams.items() if len(v) > 1}}


def id_confirmed_merges(artists: Sequence[dict], mapped: Iterable[dict]) -> Dict[str, int]:
    """이름으로 묶인 팀(키 2개 이상)마다: 서로 다른 표기 둘 이상이 같은 번호 → confirmed, 같은 플랫폼에서 표기마다 번호가 다름
    → contradicted, 그 밖(번호가 표기 하나에만 있거나 없음) → no_id."""
    by_team: Dict[str, Dict[Tuple[str, str], Set[str]]] = defaultdict(lambda: defaultdict(set))
    for r in mapped:
        by_team[r["team"]][(r["platform"], r["id"])].add(r["variant"])
    out = Counter({"confirmed": 0, "contradicted": 0, "no_id": 0})
    for a in artists:
        if len(a.get("keys", [])) < 2:
            continue
        ids = by_team.get(a["artist_key"], {})
        per_platform = Counter(p for p, _ in ids)      # 같은 플랫폼 안에서만 번호를 견준다(멜론 번호 ≠ 스포티파이 번호는 비교 불가)
        if any(len(v) >= 2 for v in ids.values()):
            out["confirmed"] += 1
        elif any(n >= 2 for n in per_platform.values()):
            out["contradicted"] += 1
        else:
            out["no_id"] += 1
    return dict(out)


def _linked_handles(a: dict) -> List[str]:
    return [i["handle"].lower() for i in a.get("instagram") or [] if i.get("confidence") in LINKED_IG]


def ig_conflicts(artists: Sequence[dict]) -> dict:
    """인스타(high·mid): 한 계정에 팀 여러 개 / 한 팀에 계정 여러 개."""
    handle_teams: Dict[str, Set[str]] = defaultdict(set)
    multi_handle = {}
    for a in artists:
        hs = set(_linked_handles(a))
        for h in hs:
            handle_teams[h].add(a["artist_key"])
        if len(hs) > 1:
            multi_handle[a["artist_key"]] = hs
    return {"multi_team_handles": {h: t for h, t in handle_teams.items() if len(t) > 1}, "multi_handle_teams": multi_handle}


def holding(artists: Sequence[dict], keys: Optional[Set[str]] = None) -> dict:
    """번호·인스타 보유 팀 수. keys 를 주면 그 팀들만(연결표에 없는 키는 missing)."""
    by_key = {a["artist_key"]: a for a in artists}
    rows = list(artists) if keys is None else [by_key[k] for k in keys if k in by_key]
    has = {p: sum(1 for a in rows if a.get(f"{p}_id")) for p in PLATFORMS}
    ig = sum(1 for a in rows if _linked_handles(a))
    any_id = sum(1 for a in rows if any(a.get(f"{p}_id") for p in PLATFORMS) or _linked_handles(a))
    return {"teams": len(rows), **has, "instagram": ig, "any_id": any_id, "name_only": len(rows) - any_id,
            "missing": 0 if keys is None else len(keys) - len(rows)}


# ---------- '번호 먼저' 시뮬레이션 ----------

def simulate(mapped: Iterable[dict], min_conf: str = "high") -> dict:
    """번호가 같은 팀은 하나로(합치기), 같은 플랫폼 번호가 2개 이상인 팀은 번호 수만큼(가르기)."""
    rows = _at_least(mapped, min_conf)
    groups = ax._Groups()
    by_id: Dict[Tuple[str, str], List[str]] = defaultdict(list)
    for r in rows:
        groups.find(r["team"])
        by_id[(r["platform"], r["id"])].append(r["team"])
    for teams in by_id.values():
        for t in teams[1:]:
            groups.union(teams[0], t)
    members: Dict[str, Set[str]] = defaultdict(set)
    for t in list(groups.parent):
        members[groups.find(t)].add(t)
    merge_groups = sorted((m for m in members.values() if len(m) > 1), key=lambda m: (-len(m), sorted(m)))
    split: Dict[str, Dict[str, Set[str]]] = defaultdict(dict)
    for p, team_ids in id_conflicts(rows)["multi_id_teams"].items():
        for t, ids in team_ids.items():
            split[t][p] = ids
    return {"merge_groups": merge_groups, "teams_absorbed": sum(len(m) - 1 for m in merge_groups),
            "split_teams": dict(split),
            "teams_added": sum(max(len(ids) for ids in per.values()) - 1 for per in split.values())}


# ---------- 문서 ----------

def _pct(a: int, b: int) -> str:
    return "—" if not b else f"{100 * a / b:.1f}%"


def holding_table(artists: Sequence[dict], groups: Dict[str, Optional[Set[str]]]) -> List[str]:
    out = ["| 묶음 | 팀 | 멜론 번호 | 스포티파이 번호 | 인스타(연결 high·mid) | 하나라도 있음 | **근거가 이름뿐** | 연결표에 없음 |",
           "|---|---|---|---|---|---|---|---|"]
    for name, keys in groups.items():
        h = holding(artists, keys)
        n = h["teams"]
        out.append(f"| {name} | {n:,} | {h['melon']:,} ({_pct(h['melon'], n)}) | {h['spotify']:,} ({_pct(h['spotify'], n)}) | "
                   f"{h['instagram']:,} ({_pct(h['instagram'], n)}) | {h['any_id']:,} ({_pct(h['any_id'], n)}) | "
                   f"**{h['name_only']:,} ({_pct(h['name_only'], n)})** | {h['missing']:,} |")
    return out


def short_name(name: str) -> str:
    """끝 괄호를 모두 뗀 이름 — 선정 명단의 '활동명 (영문) (본명)'에서 본명이 공개 문서에 나오지 않게."""
    name = ax.clean(name)
    while (m := ax.TRAILING_PAREN.match(name)) and m.group(1).strip():
        name = m.group(1).strip()
    return name


def _names(keys: Iterable[str], display: Dict[str, str]) -> str:
    return " + ".join(short_name(display.get(k, k)) for k in sorted(keys))


def paren_only_groups(merge_groups: Iterable[Set[str]], display: Dict[str, str]) -> int:
    """합쳐질 묶음 중 끝 괄호(영문 표기·본명)만 떼면 이름이 같아지는 묶음 수 — 이름 규칙의 빈틈."""
    return sum(1 for g in merge_groups if len({ax.artist_key(short_name(display.get(k, k))) for k in g}) == 1)


def _flag(keys: Iterable[str], groups: Dict[str, Optional[Set[str]]]) -> str:
    tags = [name for name, g in groups.items() if g is not None and any(k in g for k in keys)]
    return ", ".join(tags) or "—"


def sim_section(sim_by_conf: Dict[str, dict], display: Dict[str, str], groups: Dict[str, Optional[Set[str]]],
                impact: Dict[str, int]) -> List[str]:
    out = ["| 쓰는 번호 | 합쳐지는 묶음 | 줄어드는 팀 수 | 갈라지는 팀 | 늘어나는 팀 수 | 후보 상위 300·정답 팀이 걸린 건 |",
           "|---|---|---|---|---|---|"]
    for conf, sim in sim_by_conf.items():
        touched = [g for g in sim["merge_groups"]] + [{t} for t in sim["split_teams"]]
        hot = sum(1 for g in touched if _flag(g, groups) != "—")
        label = "확신 high만" if conf == "high" else "high + mid(검색 동명이인 있음)"
        out.append(f"| {label} | {len(sim['merge_groups'])} | {sim['teams_absorbed']} | {len(sim['split_teams'])} | "
                   f"{sim['teams_added']} | {hot} |")
    sim = sim_by_conf.get("mid") or next(iter(sim_by_conf.values()))
    paren = paren_only_groups(sim["merge_groups"], display)
    out += ["", f"- 합쳐질 묶음 {len(sim['merge_groups'])}개 중 **{paren}개는 끝 괄호(영문 표기·본명)만 떼면 이름이 같은 경우**입니다 "
            "(선정 명단의 '활동명 (영문) (본명)' 꼴). 지금 이름 규칙은 같은 문자끼리의 괄호를 소속·설명으로 보고 떼지 않아서 못 묶습니다 "
            "('예지(있지)'처럼 괄호가 소속 그룹인 경우를 잘못 합치지 않으려는 규칙). 번호가 같을 때만 묶으면 두 위험을 다 피합니다."]
    out += ["", f"**합쳐질 묶음 예시** (high + mid, 신호가 많은 순 {EXAMPLES}개):", "",
            "| 묶일 팀들 (지금 대표 이름, 괄호 뗌) | 번호 확신 | 신호 줄 수 | 걸린 묶음 |", "|---|---|---|---|"]
    high_groups = [g for g in sim_by_conf.get("high", {}).get("merge_groups", [])]
    for g in sorted(sim["merge_groups"], key=lambda g: (-sum(impact.get(k, 0) for k in g), sorted(g)))[:EXAMPLES]:
        conf = "high" if any(g <= h for h in high_groups) else "mid"
        out.append(f"| {_names(g, display)} | {conf} | {sum(impact.get(k, 0) for k in g):,} | {_flag(g, groups)} |")
    out += ["", f"**갈라질 팀 예시** (같은 플랫폼 번호가 2개 이상, 신호가 많은 순 {EXAMPLES}개):", "",
            "| 팀 | 번호 수 (플랫폼별) | 신호 줄 수 | 걸린 묶음 |", "|---|---|---|---|"]
    for t, per in sorted(sim["split_teams"].items(), key=lambda kv: (-impact.get(kv[0], 0), kv[0]))[:EXAMPLES]:
        ids = ", ".join(f"{p} {len(v)}개" for p, v in sorted(per.items()))
        out.append(f"| {short_name(display.get(t, t))} | {ids} | {impact.get(t, 0):,} | {_flag([t], groups)} |")
    return out


def render(artists: Sequence[dict], mapped: Sequence[dict], unmapped: int,
           groups: Dict[str, Optional[Set[str]]], impact: Dict[str, int]) -> List[str]:
    display = {a["artist_key"]: a.get("display_name", a["artist_key"]) for a in artists}
    total = holding(artists)
    c_all, c_high = id_conflicts(mapped), id_conflicts(mapped, "high")
    ig = ig_conflicts(artists)
    merges = id_confirmed_merges(artists, mapped)
    n_merged = sum(merges.values())
    sims = {"high": simulate(mapped, "high"), "mid": simulate(mapped, "mid")}
    multi_id = {p: len(c_all["multi_id_teams"][p]) for p in PLATFORMS}
    multi_id_high = {p: len(c_high["multi_id_teams"][p]) for p in PLATFORMS}
    multi_team = Counter(p for p, _ in c_all["multi_team_ids"])
    multi_team_high = Counter(p for p, _ in c_high["multi_team_ids"])
    lines = [
        "# 팀 신원 점검 — 이름 중심 연결표를 '번호 먼저'로 바꾸면", "",
        "_자동 생성: `.venv/bin/python scripts/identity_audit.py` (계산만 — 연결표·DB는 바꾸지 않음) · "
        "[경쟁 서비스 조사](research_2026-11-27_competitor_logic.md) 보강 ③_", "",
        "**왜**: Chartmetric은 스포티파이·애플·인스타 계정 번호를 하나의 아티스트로 묶고, Viberate는 사람이 검수하며 사용자 오류 신고를 받습니다. "
        "우리 [연결표](artist_xref.md)는 **이름**(한글·영문 병기, 인스타 프로필 이름)으로 팀을 묶고 번호는 '붙여 두기'만 합니다. "
        "동명 팀이 섞이면 백테스트 숫자 자체가 흔들리므로, 번호를 얼마나 갖고 있고 번호를 먼저 쓰면 무엇이 바뀌는지 잽니다.", "",
        "## 요약", "",
        f"- **근거가 이름뿐인 팀이 {_pct(total['name_only'], total['teams'])}** ({total['name_only']:,} / {total['teams']:,}팀) — "
        "멜론·스포티파이 번호도, 다른 소스와 이어진 인스타 계정도 없습니다. 후보 상위·정답 팀은 아래 표처럼 훨씬 낫습니다.",
        f"- 번호 충돌: 한 팀에 번호 여러 개 멜론 {multi_id['melon']}·스포티파이 {multi_id['spotify']}팀"
        f"(확신 high만 {multi_id_high['melon']}·{multi_id_high['spotify']}), "
        f"한 번호에 팀 여러 개 멜론 {multi_team['melon']}·스포티파이 {multi_team['spotify']}건"
        f"(high만 {multi_team_high['melon']}·{multi_team_high['spotify']}). 인스타 한 계정에 팀 여러 개 {len(ig['multi_team_handles'])}건.",
        f"- '번호 먼저'로 바꾸면(high + mid 번호): **{sims['mid']['teams_absorbed']}팀이 줄고**(묶음 {len(sims['mid']['merge_groups'])}개), "
        f"**{sims['mid']['teams_added']}팀이 늘어납니다**(갈라질 팀 {len(sims['mid']['split_teams'])}). "
        f"확신 high 번호만 쓰면 줄어듦 {sims['high']['teams_absorbed']} · 늘어남 {sims['high']['teams_added']}.",
        f"- 이름으로 묶은 팀 {n_merged:,}개 중 번호가 확인해 준 묶음 {merges['confirmed']} · 번호가 어긋난 묶음 {merges['contradicted']} · "
        f"번호로 확인할 수 없는 묶음 {merges['no_id']} — **이름 묶음 대부분은 번호로 검증되지 않은 상태**입니다.",
        "- 제안: 확신 high 번호는 '합치기'에 바로 쓰고(같은 번호 = 같은 팀, 공용·차단 번호 제외), mid 번호 합치기와 모든 '가르기'는 "
        "자동으로 하지 말고 사람 확인 목록에 올립니다(아래 3절). 앱에는 GitHub 이슈로 가는 '정보가 틀려요' 링크를 둡니다(4절).", "",
        "## 1. 진단 — 보유율", "",
        *holding_table(artists, groups), "",
        "- 팀 = 연결표의 대표 키. **후보 상위 300** = 앱 기본 설정(점수 v2, 데이터 끝 날짜 기준, 이미 정답 받은 팀 제외) 상위 300팀. "
        "**정답 팀** = 센 정답(counted)을 받은 팀.",
        "- 인스타는 다른 소스(공연·선정·발매 등)의 팀 이름과 이어진 계정(확신 high·mid)만 셉니다. 인스타에만 있는 이름(low)은 신원 근거로 안 봅니다.",
        "- 번호는 연결표가 팀마다 고른 하나(`melon_id`·`spotify_id`)만 봅니다. 멜론 프로필은 상위 후보·정답 팀 위주로 모아서 "
        "후보·정답 팀의 보유율이 전체보다 높습니다.", "",
        "## 2. 진단 — 충돌과 이름 묶음", "",
        "| 충돌 | 모든 번호 | 확신 high 번호만 |", "|---|---|---|",
        *[f"| 한 팀에 {p} 번호 2개 이상 | {multi_id[p]} | {multi_id_high[p]} |" for p in PLATFORMS],
        *[f"| 한 {p} 번호에 팀 2개 이상 | {multi_team[p]} | {multi_team_high[p]} |" for p in PLATFORMS],
        f"| 인스타 한 계정에 팀 2개 이상 (high·mid) | {len(ig['multi_team_handles'])} | — |",
        f"| 한 팀에 인스타 계정 2개 이상 (high·mid) | {len(ig['multi_handle_teams'])} | — |", "",
        f"- 플랫폼 번호 기록 {len(mapped) + unmapped:,}건(공용·차단 번호를 뺀 뒤) 중 {unmapped:,}건은 이름이 연결표의 어느 팀과도 맞지 않아 뺐습니다.",
        "- '한 팀에 번호 여러 개' = 동명 팀이 한 팀으로 섞였을 가능성. '한 번호에 팀 여러 개' = 같은 팀이 다른 이름으로 갈라졌을 가능성.",
        f"- 이름으로 묶인 팀(대표 키 아래 이름 키가 2개 이상) {n_merged:,}개: 서로 다른 표기 둘 이상이 같은 번호 → 확인 {merges['confirmed']} · "
        f"표기마다 다른 번호 → 어긋남 {merges['contradicted']} · 번호가 표기 하나에만 있거나 없음 → 확인 불가 {merges['no_id']}.", "",
        "## 3. '번호 먼저' 묶기 — 시뮬레이션 (적재 안 함)", "",
        "규칙: ① 같은 플랫폼 번호가 붙은 팀들은 이름이 달라도 한 팀으로 합친다 ② 한 팀에 같은 플랫폼 번호가 2개 이상이면 번호 수만큼 다른 팀으로 본다. "
        "공용 번호(멜론 0·1)·사람이 '다른 아티스트'로 확인한 번호(`config/artist_aliases.json` platform_ids.not)·1,000 미만 멜론 번호는 처음부터 뺍니다. "
        "'high'는 검색 결과에 같은 이름이 한 명뿐이었거나 프로필·발매 원본에서 온 번호, 'mid'는 동명이인이 있던 검색 결과입니다.", "",
        *sim_section(sims, display, groups, impact), "",
        "### 규칙 제안 (적용은 코디네이터·사용자 판단)", "",
        "1. **합치기는 번호 우선**: 확신 high 번호가 같으면 이름이 달라도 같은 팀으로 묶는다(artist_xref 의 별칭 간선에 '번호 근거' 간선 추가, 확신 high). "
        "mid 번호(동명이인 검색)는 합치기 근거로 쓰지 않고 확인 목록에만 올린다.",
        "2. **가르기는 사람 확인**: 한 팀에 번호가 2개 이상이면 자동으로 나누지 않고 지금처럼 `multiple_platform_ids` 확인 목록에 올리되, "
        "가중치를 올리고(후보 상위 300·정답 팀이면 맨 위) 확인 결과는 `config/artist_aliases.json`의 `distinct`(다른 팀)·`platform_ids`(맞는 번호·not)로 남긴다. "
        "검색 동명이인 때문에 생긴 가짜 충돌이 섞여 있어 자동 가르기는 오히려 맞는 팀을 쪼갤 수 있다.",
        "3. **대표 키는 그대로**: 팀 키를 번호로 바꾸면 기존 문서·앱 주소·관심 목록이 깨진다. 키는 이름 그대로 두고, 번호는 '같은 팀 판정' 근거로만 쓴다.",
        "4. **번호 보유율을 매일 지표로**: 후보 상위 300의 '근거가 이름뿐' 비율을 매일 데이터 검사(`scripts/data_checks.py`)에 넣고, "
        "멜론 보강 명단(`scripts/melon_names.py`)이 이 팀들을 먼저 찾게 한다.", "",
        "## 4. 앱 '오류 신고' 칸 제안 (Viberate·Songstats 방식을 공개 저장소에 맞게)", "",
        "Viberate는 사용자 제보를 큐레이터가 승인/거절하고, Songstats는 '숫자가 틀렸다' 양식(프로필·플랫폼 주소·지표·기대값)을 둡니다. "
        "우리 앱은 서버 없는 정적 페이지라 **GitHub 이슈**가 가장 단순합니다.", "",
        f"- **어디에**: 팀 상세 머리(단계 배지 옆)에 작은 링크 '정보가 틀려요'. 누르면 `{REPO_URL}/issues/new?template=identity.yml"
        "&title=[신원] 팀이름&labels=identity` 처럼 팀 이름·대표 키·화면 주소를 미리 채운 새 이슈 화면이 열린다.",
        "- **양식 칸** (`.github/ISSUE_TEMPLATE/identity.yml`, 이슈 양식): 종류(다른 팀이 섞임 / 같은 팀이 갈라짐 / 번호가 틀림 / 인스타 계정이 틀림 / 팀이 아님), "
        "대표 키(자동), 근거 링크(멜론·스포티파이·인스타 공개 주소), 설명. **개인 연락처·이메일을 적지 말라**는 안내를 맨 위에.",
        "- **처리**: 코디네이터가 근거를 확인해 `config/artist_aliases.json`(aliases·distinct·platform_ids·non_artist_handles)에 이유·근거·확인 날짜와 함께 "
        "적고 이슈를 닫는다 → 다음 날 연결표·점수에 반영. 거절은 이유를 이슈에 남긴다(Viberate의 '거절 사유 안내').",
        "- **주의**: 공개 저장소라 이슈도 공개된다. GitHub 계정이 있어야 신고할 수 있다(장벽이자 스팸 방지). 신고 수가 적어도 '고칠 길이 있다'는 신뢰를 준다.", "",
        "## 5. 한계", "",
        "- 플랫폼 번호는 이름 검색으로 찾은 것이 많아(정답 팀·상위 후보 위주), 검색이 틀리면 번호도 틀립니다. 'high'도 검색 결과 동명이인이 없었다는 뜻일 뿐입니다.",
        "- 멜론 번호와 스포티파이 번호를 서로 잇는 자료가 없어 '두 플랫폼 번호가 같은 사람인가'는 확인할 수 없습니다.",
        "- 이 점검은 지금 연결표 파일을 읽어 계산합니다. 매일 실행이 연결표를 다시 만들면 숫자가 조금 바뀝니다.", "",
    ]
    return lines


# ---------- 실행 ----------

def lab_groups(data_dir: Path = LAB_DATA, top_n: int = TOP_N) -> Tuple[Dict[str, Optional[Set[str]]], Dict[str, int]]:
    """(묶음 이름 → 팀 키 집합, 팀별 신호 줄 수). 후보 상위 N은 앱 기본 설정(lab_sql.DEFAULTS)으로 계산."""
    import lab_sql

    meta = json.loads((data_dir / "meta.json").read_text(encoding="utf-8"))
    con = lab_sql.connect(data_dir)
    top = lab_sql.query(con, "candidates.sql", as_of=f"'{meta['data_end']}'", limit=str(top_n))
    with open(data_dir / "outcomes.csv", encoding="utf-8", newline="") as f:
        winners = {r["team_key"] for r in csv.DictReader(f) if r.get("counted") == "true"}
    with open(data_dir / "signals.csv", encoding="utf-8", newline="") as f:
        impact = Counter(r["team_key"] for r in csv.DictReader(f))
    groups = {"전체": None, f"후보 상위 {top_n}": {r["team_key"] for r in top}, "정답 팀": winners}
    return groups, dict(impact)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="팀 신원 점검 (계산만)")
    ap.add_argument("--xref", type=Path, default=ax.DEFAULT_XREF)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)
    try:
        artists = json.loads(args.xref.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"❌ 연결표를 읽지 못함 ({args.xref.name}): {e} — 먼저 scripts/artist_xref.py 를 실행하세요", file=sys.stderr)
        return 1
    _, _, _, platform_ids = ax.collect_inputs()
    mapped, unmapped = map_records(usable_records(platform_ids, ax.load_curation()), artists)
    groups, impact = lab_groups()
    lines = render(artists, mapped, unmapped, groups, impact)
    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"✅ → {args.out.relative_to(ROOT) if args.out.is_relative_to(ROOT) else args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
