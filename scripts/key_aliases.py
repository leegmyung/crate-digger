"""팀 대표 키가 바뀐 뒤 옛 키 → 새 키 표 → docs/lab/data/key_aliases.csv (+ 지난 점수 스냅샷 키를 새 키로)

이름 묶기 연결표(artist_xref.py)를 다시 적재하면 정답 팀 대표 키가 바뀔 수 있다(thevolunteers → 더발룬티어스).
그러면 앱에 저장된 관심 팀·비교 담기·옛 주소(#/team/옛키)와, 지난주 순위 비교(▲▼, 스냅샷 키 기준)가 깨진다.
  - 옛 키: 바로 전에 커밋된 팀 표(git <rev>:docs/lab/data/teams.csv) + 지난 스냅샷 + 지난번 key_aliases.csv
  - 새 키: 지금 팀 표 — 옛 키(안 되면 옛 표시 이름)를 연결표로 풀어 지금 팀 표에 있는 키가 나오면 짝
  - 앱(docs/app/key_aliases.js)이 열 때 이 표로 저장값·주소를 옮기고, 지난 스냅샷은 여기서 새 키로 바꿔 쓴다
    (두 옛 키가 한 새 키로 합쳐지면 순위가 더 좋은 줄을 남김).

실행 (매일 21시, 랩 내보내기 뒤·점수 스냅샷 앞): .venv/bin/python scripts/key_aliases.py [--since-rev HEAD]
"""
from __future__ import annotations

import argparse
import csv
import glob
import io
import subprocess
import sys
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Sequence, Set, Tuple

ROOT = Path(__file__).resolve().parent.parent
LAB_DIR = ROOT / "docs" / "lab" / "data"
OUT = LAB_DIR / "key_aliases.csv"
TEAMS_REL = "docs/lab/data/teams.csv"


def build_aliases(old: Mapping[str, str], current: Set[str], resolve: Callable[[str], str]) -> Dict[str, str]:
    """old = {옛 키: 옛 표시 이름}. 지금 팀 표에 없는 옛 키만, 키(안 되면 이름)를 풀어 지금 키가 나오면 짝."""
    out: Dict[str, str] = {}
    for key, name in old.items():
        if not key or key in current:
            continue
        for probe in (key, name):
            new = resolve(probe) if probe else ""
            if new and new != key and new in current:
                out[key] = new
                break
    return out


def merge_aliases(existing: Mapping[str, str], new: Mapping[str, str], current: Set[str]) -> Dict[str, str]:
    """지난 표 + 새 짝. 대상이 다시 바뀌었으면 따라가고(a1→a2→a3), 대상이 지금 없거나 옛 키가 다시 지금 키면 버린다."""
    table = {**existing, **new}
    out: Dict[str, str] = {}
    for old in table:
        if old in current:
            continue
        target, seen = table[old], {old}
        while target not in current and target in table and target not in seen:
            seen.add(target)
            target = table[target]
        if target in current:
            out[old] = target
    return out


def remap_snapshot_rows(rows: Sequence[Mapping], aliases: Mapping[str, str]) -> Tuple[List[dict], bool]:
    """스냅샷 줄의 팀 키를 새 키로. 같은 새 키가 둘이면 순위가 더 좋은(작은) 줄. 원래 줄은 안 바꿈."""
    if not any(r.get("team_key") in aliases for r in rows):
        return [dict(r) for r in rows], False
    best: Dict[str, dict] = {}
    order: List[str] = []
    for r in rows:
        key = aliases.get(r["team_key"], r["team_key"])
        row = dict(r, team_key=key)
        cur = best.get(key)
        if cur is None:
            order.append(key)
            best[key] = row
        elif float(row.get("rank") or 1e9) < float(cur.get("rank") or 1e9):
            best[key] = row
    return [best[k] for k in order], True


def read_aliases(path: Path = OUT) -> Dict[str, str]:
    try:
        with open(path, encoding="utf-8") as fh:
            return {r["old_key"]: r["new_key"] for r in csv.DictReader(fh) if r.get("old_key") and r.get("new_key")}
    except OSError:
        return {}


def write_aliases(aliases: Mapping[str, str], path: Path = OUT) -> None:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["old_key", "new_key"])
        for old in sorted(aliases):
            w.writerow([old, aliases[old]])


# ---------- 파일 ----------

def _teams_at(rev: str) -> Dict[str, str]:
    """git rev 의 팀 표 {키: 표시 이름}. 못 읽으면 {}."""
    r = subprocess.run(["git", "show", f"{rev}:{TEAMS_REL}"], cwd=ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        return {}
    return {row["team_key"]: row.get("display_name") or "" for row in csv.DictReader(io.StringIO(r.stdout))}


def _snapshot_files() -> List[Path]:
    return [Path(p) for p in sorted(glob.glob(str(LAB_DIR / "snapshots" / "*.csv")))]


def _read_rows(path: Path) -> Tuple[List[str], List[dict]]:
    with open(path, encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        return list(reader.fieldnames or []), list(reader)


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="옛 팀 키 → 새 키 표")
    ap.add_argument("--since-rev", default="HEAD", help="옛 팀 표를 읽을 git 커밋 (기본: 마지막 커밋)")
    args = ap.parse_args(argv)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import artist_xref
    index = artist_xref.load_xref()
    resolve = lambda s: artist_xref.canonical_key(s, index)   # noqa: E731
    with open(LAB_DIR / "teams.csv", encoding="utf-8") as fh:
        current = {r["team_key"] for r in csv.DictReader(fh)}
    old = _teams_at(args.since_rev)
    for path in _snapshot_files():
        for r in _read_rows(path)[1]:
            old.setdefault(r["team_key"], "")
    existing = read_aliases()
    aliases = merge_aliases(existing, build_aliases(old, current, resolve), current)
    write_aliases(aliases)
    fixed = 0
    for path in _snapshot_files():
        fields, rows = _read_rows(path)
        new_rows, changed = remap_snapshot_rows(rows, aliases)
        if changed:
            with open(path, "w", encoding="utf-8", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=fields)
                w.writeheader()
                w.writerows(new_rows)
            fixed += 1
    print(f"✅ 옛 키 → 새 키 {len(aliases):,}개 (새로 {len(set(aliases) - set(existing)):,}) → {OUT.relative_to(ROOT)} · "
          f"스냅샷 {fixed}개 키 갱신")
    return 0


if __name__ == "__main__":
    sys.exit(main())
