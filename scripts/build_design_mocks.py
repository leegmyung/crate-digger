"""디자인 시안(docs/design/mock_a·b·c.html)에 실제 상위 10팀 데이터를 넣는다.

- 순위: docs/lab/data/snapshots 의 가장 최근 CSV 상위 10팀 (앱 '후보'와 같은 점수 v2).
- 점수 구성·백분위: candidates.sql 을 파이썬 DuckDB로 돌려(scripts/lab_sql.py) 같은 날 기준으로 계산.
  백분위 = '지금 후보 풀(정답 아직 없는 팀)' 안에서 그 항목 점수의 위치(0~100).
- 각 HTML의 <script id="mock-data" type="application/json"> ... </script> 칸만 바꾼다(화면 코드는 그대로).

실행: .venv/bin/python scripts/build_design_mocks.py   (duckdb 필요)
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "docs" / "lab" / "data"
SNAP_DIR = DATA_DIR / "snapshots"
DESIGN_DIR = ROOT / "docs" / "design"
MOCK_FILES = ("mock_a.html", "mock_b.html", "mock_c.html", "index.html")   # index는 기준일·빠진 팀 안내용
TOP_N = 10
EVENTS_PER_TEAM = 5

SOURCE_LABELS = {
    "indistreet": "인디스트릿", "hiphople": "힙합엘이", "trackzero": "멜론 트랙제로", "izm": "이즘",
    "visla": "VISLA", "musicy": "음악취향Y", "sangsangmadang": "상상마당", "overtone": "overtone",
    "indiego": "인디고", "dmz": "DMZ 피스트레인", "rhythmer": "리드머", "routenote": "루트노트",
    "instagram": "인스타그램", "bugs": "벅스", "genie": "지니", "melon": "멜론", "flo": "FLO",
    "sejong": "세종", "gbsound": "경북 사운드", "poclanos": "포크라노스", "weiv": "weiv",
    "busanrock": "부산록페", "yjh": "yjh",
}
STATUS_LABELS = {"newcomer": "신인", "established": "활동 중", "unknown": "프로필 없음"}

# 점수 v2에서 쓰는 항목만 (가중치 0인 항목은 화면에 안 씀). 순서 = 화면 순서.
COMPONENTS = (
    ("branch", "갈래 겹침", "공연·발매·선정·큐레이션 중 몇 갈래에서 보였나"),
    ("stage", "선정 단계", "선정·지원 프로그램에서 오른 가장 높은 단계"),
    ("venues", "공연장 다양성", "서로 다른 공연장 수"),
    ("winner", "수상 팀과 같은 무대", "이미 상을 받은 팀과 같은 공연에 섰나"),
    ("outlets", "발굴 매거진", "발굴형 매체(검증된 곳) 소개 수"),
    ("context", "맥락 매거진", "맥락 매체 소개 수 (약하게 반영)"),
)
FACT_KEYS = ("n_branch", "best_stage", "venues", "gigs_1y", "recent180", "outlets", "context_outlets", "peer_winner")


def percentile(value: float, pool: Sequence[float]) -> int:
    """풀 안에서 value의 위치(0~100). 0 이하는 0. 같은 값은 절반만 아래로 센다(중간 순위)."""
    if value <= 0 or not pool:
        return 0
    below = sum(1 for x in pool if x < value)
    same = sum(1 for x in pool if x == value)
    return max(0, min(100, round(100 * (below + same / 2) / len(pool))))


def event_label(row: Dict[str, str], programs: Dict[str, str]) -> str:
    """신호 한 줄을 사람이 읽는 이름으로: 프로그램 이름 > 프로그램 칸 > 출처 이름(+공연장)."""
    program = (row.get("program") or "").strip()
    if program:
        return programs.get(program, program)
    label = SOURCE_LABELS.get(row.get("source", ""), row.get("source", ""))
    venue = (row.get("venue") or "").strip()
    return f"{label} · {venue}" if venue else label


def recent_events(rows: Iterable[Dict[str, str]], team_key: str, as_of: str,
                  programs: Dict[str, str], n: int = EVENTS_PER_TEAM) -> List[Dict[str, str]]:
    """기준일까지의 최근 신호 n개(최신순). 기준일보다 뒤(예정된 일정)는 뺀다."""
    mine = [r for r in rows if r.get("team_key") == team_key and r.get("signal_date") and r["signal_date"] <= as_of]
    mine.sort(key=lambda r: r["signal_date"], reverse=True)
    return [{"date": r["signal_date"], "branch": r.get("branch", ""), "label": event_label(r, programs)}
            for r in mine[:n]]


def summary_clauses(facts: Dict[str, int]) -> List[str]:
    """점수 근거를 짧은 구절 목록으로 (있는 신호만)."""
    clauses: List[str] = []
    gigs, venues = facts.get("gigs_1y", 0), facts.get("venues", 0)
    if gigs and venues:
        clauses.append(f"최근 1년 공연 {gigs}회 · 공연장 {venues}곳")
    elif gigs:
        clauses.append(f"최근 1년 공연 {gigs}회")
    elif venues:
        clauses.append(f"공연장 {venues}곳")
    if facts.get("best_stage"):
        clauses.append(f"선정·지원 {facts['best_stage']}단계")
    if facts.get("peer_winner"):
        clauses.append("수상 팀과 같은 무대")
    if facts.get("outlets"):
        clauses.append(f"발굴 매거진 {facts['outlets']}곳")
    if facts.get("context_outlets"):
        clauses.append(f"맥락 매거진 {facts['context_outlets']}곳")
    return clauses


def topic_particle(name: str) -> str:
    """이름 뒤 은/는. 마지막 글자가 한글이 아니면 '은(는)'."""
    last = name.strip()[-1:] if name.strip() else ""
    if not ("가" <= last <= "힣"):
        return "은(는)"
    return "은" if (ord(last) - 0xAC00) % 28 else "는"


_DATA_RE = re.compile(r'(<script id="mock-data" type="application/json">)(.*?)(</script>)', re.S)


def inject_data(html: str, payload: dict) -> str:
    """HTML의 데이터 칸만 payload(JSON)로 바꾼다. '</'는 '<\\/'로 바꿔 스크립트가 일찍 닫히지 않게."""
    if not _DATA_RE.search(html):
        raise ValueError('데이터 칸 <script id="mock-data" type="application/json"> 이 없음')
    body = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    return _DATA_RE.sub(lambda m: m.group(1) + body + m.group(3), html, count=1)


def read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def latest_snapshot_path() -> Path:
    files = sorted(p for p in SNAP_DIR.glob("*.csv") if re.fullmatch(r"\d{4}-\d{2}-\d{2}\.csv", p.name))
    if not files:
        raise FileNotFoundError(f"스냅샷 CSV가 없음: {SNAP_DIR}")
    return files[-1]


def latest_snapshot() -> List[Dict[str, str]]:
    return sorted(read_csv(latest_snapshot_path()), key=lambda r: int(r["rank"]))


def pick_top(snapshot: List[Dict[str, str]], candidates: Dict[str, dict],
             n: int) -> "tuple[List[Dict[str, str]], List[Dict[str, str]]]":
    """스냅샷 순서대로 n팀. 지금 규칙에서 후보가 아닌 팀(스냅샷 뒤 프로필 갱신 등)은 건너뛰고 dropped로 돌려준다.
    점수는 지금 계산값으로 바꿔 넣는다(점수 구성 합과 맞게)."""
    picked: List[Dict[str, str]] = []
    dropped: List[Dict[str, str]] = []
    for row in snapshot:
        if len(picked) == n:
            break
        cand = candidates.get(row["team_key"])
        if cand is None:
            dropped.append(row)
            continue
        picked.append({**row, "score": str(cand["score"])})
    return picked, dropped


def _num(value) -> float:
    return float(value) if value not in (None, "") else 0.0


def _raw_text(key: str, facts: Dict[str, int]) -> str:
    return {
        "branch": f"{facts['n_branch']}갈래",
        "stage": f"{facts['best_stage']}단계" if facts["best_stage"] else "없음",
        "venues": f"{facts['venues']}곳",
        "winner": "있음" if facts["peer_winner"] else "없음",
        "outlets": f"{facts['outlets']}곳",
        "context": f"{facts['context_outlets']}곳",
    }[key]


def _team_entry(rank: int, snap_row: Dict[str, str], row: dict, team: Dict[str, str], image: str,
                pools: Dict[str, List[float]], events: List[Dict[str, str]]) -> dict:
    facts = {k: int(_num(row.get(k))) for k in FACT_KEYS}
    name = team.get("display_name") or row.get("display_name") or snap_row["team_key"]
    score = _num(snap_row["score"])
    parts = []
    for key, _, _ in COMPONENTS:
        pts = round(_num(row.get(f"pts_{key}")), 2)
        parts.append({"key": key, "pts": pts, "pct": percentile(pts, pools[key]), "raw": _raw_text(key, facts)})
    return {
        "rank": rank, "key": snap_row["team_key"], "name": name, "particle": topic_particle(name),
        "score": score, "score_pct": percentile(score, pools["score"]),
        "genre": team.get("primary_genre") or "", "status": STATUS_LABELS.get(team.get("profile_status", ""), ""),
        "first_seen": team.get("first_seen") or "", "first_release": team.get("first_release") or "",
        "last_seen": str(row.get("last_seen") or ""), "agency": team.get("agency") or "",
        "image": image, "facts": facts, "parts": parts, "clauses": summary_clauses(facts), "events": events,
    }


def build_payload() -> dict:
    sys.path.insert(0, str(ROOT / "scripts"))
    import lab_sql

    as_of = latest_snapshot_path().stem
    con = lab_sql.connect()
    rows = lab_sql.query(con, "candidates.sql", as_of=f"'{as_of}'", only_no_outcome="false", limit="100000")
    pool = [r for r in rows if not r["had_outcome"]]
    by_key = {r["team_key"]: r for r in pool}
    pools = {key: [_num(r.get(f"pts_{key}")) for r in pool] for key, _, _ in COMPONENTS}
    pools["score"] = [_num(r.get("score")) for r in pool]
    snap, dropped = pick_top(latest_snapshot(), by_key, TOP_N)

    teams = {r["team_key"]: r for r in read_csv(DATA_DIR / "teams.csv")}
    images: Dict[str, str] = {}
    for r in read_csv(DATA_DIR / "images.csv"):
        images.setdefault(r["team_key"], r["url"])
    programs = {r["program"]: r["label"] for r in read_csv(DATA_DIR / "programs.csv")}
    signals = read_csv(DATA_DIR / "signals.csv")

    entries = [
        _team_entry(i, s, by_key[s["team_key"]], teams.get(s["team_key"], {}),
                    images.get(s["team_key"], ""), pools,
                    recent_events(signals, s["team_key"], as_of, programs))
        for i, s in enumerate(snap, start=1)
    ]
    return {
        "as_of": as_of, "pool_size": len(pool),
        "dropped": [{"key": d["team_key"], "name": teams.get(d["team_key"], {}).get("display_name") or d["team_key"],
                     "snapshot_rank": int(d["rank"])} for d in dropped],
        "components": [{"key": k, "label": label, "desc": desc, "weight": float(lab_sql.DEFAULTS[f"w_{k}"])}
                       for k, label, desc in COMPONENTS],
        "teams": entries,
    }


def main() -> int:
    payload = build_payload()
    for name in MOCK_FILES:
        path = DESIGN_DIR / name
        path.write_text(inject_data(path.read_text(encoding="utf-8"), payload), encoding="utf-8")
        print(f"{path.relative_to(ROOT)}: {len(payload['teams'])}팀 · 기준일 {payload['as_of']} · 후보 풀 {payload['pool_size']}팀")
    return 0


if __name__ == "__main__":
    sys.exit(main())
