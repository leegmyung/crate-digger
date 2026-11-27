"""Tableau 추출 데이터 → docs/tableau/*.csv (긴 형식, 공개: 팀 이름·공개 출처 숫자만)

    .venv/bin/python scripts/export_tableau.py

Tableau 계정 없이도 바로 올릴 수 있게, 앱과 같은 계산(docs/lab/sql/*.sql, scripts/lab_sql.py DuckDB)으로 4개 파일을 만든다.
시트·차트 설계와 계산 필드는 docs/tableau/README.md. 기준일·성적표 기간은 주간 엑셀(export_excel.py)과 같은 값을 쓴다.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lab_sql  # noqa: E402
from export_excel import BACKTEST_CUTOFFS, CANDIDATE_POOL, PTS_COLS, ROLE_KO, SCORECARD_SINCE  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "docs" / "tableau"
COMPONENT_KO = {"pts_branch": "갈래 수", "pts_stage": "선정 단계", "pts_peer": "선정 팀과 같은 무대", "pts_dmz": "DMZ 출연",
                "pts_gigs": "1년 공연 일수", "pts_outlets": "발굴 매거진", "pts_recent": "최근 180일 활동",
                "pts_venues": "공연장 다양성", "pts_winner": "수상 팀과 같은 무대", "pts_context": "맥락 매거진"}
FILES: Dict[str, List[str]] = {
    "candidate_score_parts.csv": ["as_of", "rank", "team_key", "team_name", "genre", "profile_status", "score",
                                  "component", "points"],
    "signal_timeline.csv": ["team_key", "team_name", "rank", "signal_date", "branch", "source", "program", "venue", "role"],
    "source_scorecard.csv": ["src", "branch", "role", "role_ko", "since_date", "teams", "hits", "rate", "lift",
                             "base_rate", "below_baseline", "winners_seen", "first_to_see", "only_source",
                             "median_lead_months"],
    "backtest.csv": ["cutoff", "k", "method", "hits", "hit_rate", "random_expected", "lift", "pool_n", "pool_hits"],
}


def score_long(cands: List[dict], as_of: str) -> List[dict]:
    """후보 1팀 = 점수 구성 10줄 (Tableau 누적 막대용)."""
    out = []
    for i, c in enumerate(cands, 1):
        for col in PTS_COLS:
            out.append({"as_of": as_of, "rank": i, "team_key": c["team_key"], "team_name": c.get("display_name") or c["team_key"],
                        "genre": c.get("primary_genre") or "", "profile_status": c.get("profile_status") or "",
                        "score": float(c.get("score") or 0), "component": COMPONENT_KO[col], "points": float(c.get(col) or 0)})
    return out


def _iso(v):
    return v.isoformat() if hasattr(v, "isoformat") else ("" if v is None else v)


def _write(path: Path, fields: List[str], rows: List[dict]) -> int:
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows({k: _iso(r.get(k)) for k in fields} for r in rows)
    return len(rows)


def export(data_dir: Path = lab_sql.DATA_DIR, out_dir: Path = OUT_DIR, cutoffs=BACKTEST_CUTOFFS) -> Dict[str, int]:
    import json

    meta_path = data_dir / "meta.json"
    as_of = json.loads(meta_path.read_text(encoding="utf-8")).get("data_end") if meta_path.exists() else None
    con = lab_sql.connect(data_dir)
    as_of = as_of or str(con.execute("SELECT MAX(signal_date) FROM signals WHERE signal_date <= CURRENT_DATE").fetchone()[0])
    cands = lab_sql.query(con, "candidates.sql", as_of=f"'{as_of}'", limit=str(CANDIDATE_POOL))
    rank = {c["team_key"]: i for i, c in enumerate(cands, 1)}
    names = {c["team_key"]: c.get("display_name") or c["team_key"] for c in cands}
    timeline: List[dict] = []                     # 후보(상위 300) 팀의 기준일까지 신호
    cur = con.execute("SELECT team_key, signal_date, branch, source, program, venue, role FROM signals "
                      f"WHERE signal_date <= DATE '{as_of}' ORDER BY team_key, signal_date")
    cols = [d[0] for d in cur.description]
    for row in cur.fetchall():
        r = dict(zip(cols, row))
        if r["team_key"] in rank:
            timeline.append({**r, "team_name": names[r["team_key"]], "rank": rank[r["team_key"]]})
    cut_sql = ",".join(f"(DATE '{c}')" for c in cutoffs)
    scorecard = []
    for r in lab_sql.query(con, "source_scorecard.sql", cutoffs=cut_sql, since=f"'{SCORECARD_SINCE}'"):
        lift = r.get("lift")
        scorecard.append({**r, "branch": r["src"].split(":", 1)[0], "role_ko": ROLE_KO.get(r.get("role") or "", ""),
                          "below_baseline": "true" if lift is not None and float(lift) < 1 else "false"})
    backtest = [row for c in cutoffs for row in lab_sql.query(con, "backtest.sql", cutoff=f"'{c}'")]
    out_dir.mkdir(parents=True, exist_ok=True)
    data = {"candidate_score_parts.csv": score_long(cands, as_of), "signal_timeline.csv": timeline,
            "source_scorecard.csv": scorecard, "backtest.csv": backtest}
    return {name: _write(out_dir / name, FILES[name], rows) for name, rows in data.items()}


def main() -> int:
    try:
        counts = export()
    except ImportError as e:
        print(f"❌ {e} — .venv/bin/python 으로 실행 (duckdb 필요)", file=sys.stderr)
        return 1
    print(f"✅ Tableau 추출 → {OUT_DIR.relative_to(ROOT)} {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
