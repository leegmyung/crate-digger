"""장르 처음 확인한 날 되짚기 → docs/lab/data/genre_seen.csv

'확인된 장르 = 사후 수집 편향'(docs/methods.md) 대책. 확인된 장르(teams.genre_confidence = profile·press)마다
  first_seen = 우리가 그 장르를 처음 본 날 (원본 파일의 collected_at, 상태 파일 data/raw/state/genre_first_seen.json)
  known_from = 그 장르 근거가 공개된 가장 이른 날 (발매 장르 = 발매일, 출처 힌트 = 그 신호 날짜, 멜론 프로필·사람 확인 =
               우리가 본 날 — 프로필 장르가 언제부터 있었는지는 알 수 없어 보수적으로)
을 남긴다. 기준일 시점 장르만 쓰는 판: first_seen < 기준일(가장 엄격, 우리가 그때 실제로 알았나) 또는
known_from < 기준일(그때 공개돼 있던 근거로 알 수 있었나).

근거 4가지 (genre_fill.py 의 profile·press 규칙과 같은 출처):
  profile = 멜론·스포티파이 프로필 장르(data/raw/raw_artist_profile_*.csv) + 상태 파일
          + 발매 장르(data/raw/raw_kr_release_*.csv) + 사람 확인(config/genre_overrides.json, checked 날짜)
  press   = 리드머 소개 → 힙합, 밴드 디스커버리 → 록·밴드 (build_dashboard_data.GENRE_HINT_*), 날짜는 docs/lab/data/signals.csv
원본 이름 → 팀 키는 artist_xref.canonical_key (data/raw/state/artist_xref.json, 팀 표와 같은 규칙).

실행:
  .venv/bin/python scripts/genre_seen.py                 # → docs/lab/data/genre_seen.csv + 기준일별 팀 수
  .venv/bin/python scripts/genre_seen.py --seed-state    # 지금 원본으로 상태 파일을 처음 채움(이미 있는 날짜는 더 이른 쪽 유지)
  .venv/bin/python scripts/genre_seen.py --pool          # 점수 후보군(기준일 6개)에서 행·정답 수까지 (duckdb 필요)
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Callable, Dict, Iterable, Iterator, List, Mapping, NamedTuple, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
STATE_PATH = RAW_DIR / "state" / "genre_first_seen.json"
LAB_DIR = ROOT / "docs" / "lab" / "data"
OUT = LAB_DIR / "genre_seen.csv"
OVERRIDES = ROOT / "config" / "genre_overrides.json"
CONFIRMED = ("profile", "press")
COLUMNS = ("team_key", "genre", "confidence", "first_seen", "first_seen_source", "known_from", "known_from_source", "match")
PRESS_RAW_GLOBS = ("raw_press_*_rhythmer*.csv", "raw_kr_selection_*_sangsangmadang*.csv")


class Evidence(NamedTuple):
    team_key: str
    labels: Tuple[str, ...]   # 장르 지도 갈래 이름 (teams.primary_genre 와 같은 말)
    seen: str                 # 우리가 본 날 YYYY-MM-DD
    known: str                # 근거가 공개된 날 YYYY-MM-DD (seen 보다 늦지 않음)
    source: str
    kind: str                 # profile | press


def _day(value) -> str:
    v = str(value or "").strip()[:10]
    return v if len(v) == 10 and v[4] == "-" and v[7] == "-" else ""


def _tags(field) -> List[str]:
    return [t.strip() for t in str(field or "").split("|") if t.strip()]


# ---------- 상태 파일 (collect_artists.py 가 부름) ----------

def merge_genre_seen(state: Mapping[str, dict], rows: Iterable[Mapping]) -> Tuple[Dict[str, dict], int]:
    """프로필 줄들로 상태 갱신 → (새 상태, 새로 본 태그 수). {멜론 번호: {artist_text, genres: {태그: 처음 본 날}}}.
    이미 있는 태그는 더 이른 날짜를 남긴다. 원래 state 는 바꾸지 않는다."""
    new = {k: {"artist_text": v.get("artist_text", ""), "genres": dict(v.get("genres") or {})} for k, v in state.items()}
    added = 0
    for r in rows:
        aid, day, tags = str(r.get("artist_source_id") or ""), _day(r.get("collected_at")), _tags(r.get("genre"))
        if not (aid and day and tags):
            continue
        entry = new.setdefault(aid, {"artist_text": r.get("artist_text", ""), "genres": {}})
        entry["artist_text"] = entry["artist_text"] or r.get("artist_text", "")
        for t in tags:
            old = entry["genres"].get(t)
            if old is None:
                added += 1
            if old is None or day < old:
                entry["genres"][t] = day
    return new, added


def state_rows(state: Mapping[str, dict]) -> Iterator[dict]:
    """상태 파일 → 프로필 줄 모양 (profile_evidence 에 넣을 수 있게)."""
    for v in state.values():
        for tag, day in (v.get("genres") or {}).items():
            yield {"artist_text": v.get("artist_text", ""), "genre": tag, "collected_at": day, "source": "state"}


# ---------- 근거 ----------

def _labels_of(field) -> Tuple[str, ...]:
    import genre as genre_mod
    cfg = genre_mod.load_config()["buckets"]
    return tuple(cfg[b]["label"] for b in genre_mod.buckets_of(str(field or "")) if b in cfg)


def profile_evidence(rows: Iterable[Mapping], key_of: Callable[[str], str]) -> Iterator[Evidence]:
    for r in rows:
        labels, day = _labels_of(r.get("genre")), _day(r.get("collected_at"))
        key = key_of(r.get("artist_text") or "")
        if labels and day and key:
            yield Evidence(key, labels, day, day, f"profile:{r.get('source') or 'unknown'}", "profile")


def release_evidence(rows: Iterable[Mapping], key_of: Callable[[str], str]) -> Iterator[Evidence]:
    for r in rows:
        labels, seen = _labels_of(r.get("genre")), _day(r.get("collected_at"))
        key = key_of(r.get("artist_text") or "")
        if not (labels and seen and key):
            continue
        released = _day(r.get("released_at"))
        known = released if released and released < seen else seen
        yield Evidence(key, labels, seen, known, f"release:{r.get('source') or 'unknown'}", "profile")


def _press_hints() -> Tuple[Dict[str, str], Dict[str, str]]:
    import genre as genre_mod
    from build_dashboard_data import GENRE_HINT_PRESS, GENRE_HINT_PROGRAMS
    cfg = genre_mod.load_config()["buckets"]
    lab = lambda m: {k: cfg[v]["label"] for k, v in m.items() if v in cfg}   # noqa: E731
    return lab(GENRE_HINT_PRESS), lab(GENRE_HINT_PROGRAMS)


def press_evidence(signals: Iterable[Mapping], collected: Mapping[str, str]) -> Iterator[Evidence]:
    """확실한 출처 힌트(press) 근거. known = 신호 날짜, seen = 그 팀 원본을 처음 받은 날(collected, 없으면 빈칸)."""
    by_source, by_program = _press_hints()
    for s in signals:
        src, prog = str(s.get("source") or "").lower(), str(s.get("program") or "").lower()
        label = by_source.get(src) if s.get("branch") == "큐레이션" else by_program.get(prog)
        day, key = _day(s.get("signal_date")), s.get("team_key") or ""
        if label and day and key:
            seen = collected.get(key, "")
            yield Evidence(key, (label,), seen, min(day, seen) if seen else day,
                           f"press:{prog if s.get('branch') != '큐레이션' else src}", "press")


def override_evidence(overrides: Mapping[str, dict]) -> Iterator[Evidence]:
    import genre as genre_mod
    cfg = genre_mod.load_config()["buckets"]
    for key, v in overrides.items():
        day, b = _day(v.get("checked")), v.get("genre")
        if day and b in cfg:
            yield Evidence(key, (cfg[b]["label"],), day, day, "override", "profile")


# ---------- 표 ----------

def _earliest(evs: Sequence[Evidence], attr: str) -> Tuple[str, str]:
    dated = [e for e in evs if getattr(e, attr)]
    if not dated:
        return "", ""
    best = min(dated, key=lambda e: (getattr(e, attr), e.source))
    return getattr(best, attr), best.source


def first_seen_table(teams: Iterable[Mapping], evidence: Iterable[Evidence]) -> List[dict]:
    """확인된 장르 팀마다 한 줄. 대표 장르와 같은 갈래의 근거(match=genre)를 쓰고, 없으면 같은 종류의 아무 장르 근거(any),
    그것도 없으면 빈칸(none). profile 팀은 profile 근거만, press 팀은 press 근거만 본다."""
    by_team: Dict[str, List[Evidence]] = defaultdict(list)
    for e in evidence:
        by_team[e.team_key].append(e)
    out = []
    for t in teams:
        conf, genre = t.get("genre_confidence") or "", (t.get("primary_genre") or "").strip()
        if conf not in CONFIRMED or genre in ("", "미분류"):
            continue
        same_kind = [e for e in by_team.get(t["team_key"], ()) if e.kind == conf]
        matched = [e for e in same_kind if genre in e.labels]
        use, match = (matched, "genre") if matched else ((same_kind, "any") if same_kind else ([], "none"))
        seen, seen_src = _earliest(use, "seen")
        known, known_src = _earliest(use, "known")
        out.append(dict(zip(COLUMNS, (t["team_key"], genre, conf, seen, seen_src, known, known_src, match))))
    return out


def point_in_time_counts(table: Sequence[Mapping], cutoffs: Sequence[str]) -> List[dict]:
    """기준일마다 '그때 이미 확인된' 팀 수 — 우리가 본 날 기준(by_first_seen) / 근거 공개일 기준(by_known_from)."""
    return [{"cutoff": c,
             "by_first_seen": sum(1 for r in table if r.get("first_seen") and r["first_seen"] < c),
             "by_known_from": sum(1 for r in table if r.get("known_from") and r["known_from"] < c),
             "total": len(table)} for c in cutoffs]


def pool_counts(table: Sequence[Mapping], pool: Mapping[str, Sequence[Mapping]]) -> List[dict]:
    """점수 후보군(기준일 → 줄들, is_hit)에서 지금 확인된 장르 / 그때 공개 근거로 알 수 있던 장르 / 그때 우리가 본 장르."""
    rows_by_key = {r["team_key"]: r for r in table}
    out = []
    for c, rows in pool.items():
        now = [r for r in rows if r["team_key"] in rows_by_key]
        known = [r for r in now if (rows_by_key[r["team_key"]].get("known_from") or "9") < c]
        seen = [r for r in now if (rows_by_key[r["team_key"]].get("first_seen") or "9") < c]
        out.append({"cutoff": c, "rows": len(rows), "hits": sum(int(r["is_hit"]) for r in rows),
                    "confirmed_now": len(now), "confirmed_now_hits": sum(int(r["is_hit"]) for r in now),
                    "known_then": len(known), "known_then_hits": sum(int(r["is_hit"]) for r in known),
                    "seen_then": len(seen)})
    return out


# ---------- 파일 ----------

def _read_csvs(patterns: Iterable[str]) -> List[dict]:
    rows: List[dict] = []
    for pat in patterns:
        for f in sorted(glob.glob(str(RAW_DIR / pat))):
            with open(f, encoding="utf-8") as fh:
                rows.extend(csv.DictReader(fh))
    return rows


def _load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _key_fn() -> Callable[[str], str]:
    import artist_xref
    index = artist_xref.load_xref()
    return lambda name: artist_xref.canonical_key(name, index) if name else ""


def _collected_by_team(key_of: Callable[[str], str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for r in _read_csvs(PRESS_RAW_GLOBS):
        key, day = key_of(r.get("artist_text") or ""), _day(r.get("collected_at"))
        if key and day and (key not in out or day < out[key]):
            out[key] = day
    return out


def collect_evidence() -> List[Evidence]:
    key_of = _key_fn()
    profiles = _read_csvs(("raw_artist_profile_*.csv",)) + list(state_rows(_load_json(STATE_PATH, {})))
    overrides = (_load_json(OVERRIDES, {}) or {}).get("teams") or {}
    with open(LAB_DIR / "signals.csv", encoding="utf-8") as fh:
        signals = list(csv.DictReader(fh))
    return [*profile_evidence(profiles, key_of), *release_evidence(_read_csvs(("raw_kr_release_*.csv",)), key_of),
            *press_evidence(signals, _collected_by_team(key_of)), *override_evidence(overrides)]


def seed_state(path: Path = STATE_PATH) -> int:
    """지금 원본 멜론 프로필로 상태 파일을 채운다. 새로 넣은 태그 수를 돌려준다."""
    rows = _read_csvs(("raw_artist_profile_*_melon*.csv",))
    new, added = merge_genre_seen(_load_json(path, {}), rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(new, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    return added


def write_table(table: Sequence[Mapping], out: Path = OUT) -> None:
    with open(out, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(sorted(table, key=lambda r: r["team_key"]))


def _pool() -> Dict[str, List[dict]]:
    import lab_sql
    import score_tune as st
    con = lab_sql.connect()
    return {c: st.features(con, c) for c in st.CUTOFFS}


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seed-state", action="store_true", help="원본 멜론 프로필로 상태 파일 채우기")
    ap.add_argument("--pool", action="store_true", help="점수 후보군(기준일 6개) 행·정답 수까지 (duckdb 필요)")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    if args.seed_state:
        print(f"상태 파일 {STATE_PATH.relative_to(ROOT)}: 새 태그 {seed_state():,}개")
    with open(LAB_DIR / "teams.csv", encoding="utf-8") as fh:
        teams = list(csv.DictReader(fh))
    table = first_seen_table(teams, collect_evidence())
    write_table(table, args.out)
    match = defaultdict(int)
    for r in table:
        match[r["match"]] += 1
    print(f"✅ {len(table):,}팀 → {args.out.relative_to(ROOT) if args.out.is_relative_to(ROOT) else args.out} "
          f"(근거: 같은 장르 {match['genre']:,} · 다른 장르 {match['any']:,} · 없음 {match['none']:,})")
    import score_tune as st
    for c in point_in_time_counts(table, st.CUTOFFS + ["2026-11-01"]):
        print(f"  {c['cutoff']}: 우리가 본 날 기준 {c['by_first_seen']:,}팀 · 공개 근거 기준 {c['by_known_from']:,}팀 / 지금 {c['total']:,}팀")
    if args.pool:
        for p in pool_counts(table, _pool()):
            print(f"  후보군 {p['cutoff']}: {p['rows']:,}행(정답 {p['hits']}) · 지금 확인 {p['confirmed_now']}(정답 {p['confirmed_now_hits']}) · "
                  f"그때 공개 근거 {p['known_then']}(정답 {p['known_then_hits']}) · 그때 본 것 {p['seen_then']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
