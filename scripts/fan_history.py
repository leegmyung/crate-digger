"""멜론 팬 수 기록 쌓기 → data/raw/state/fan_history.json (비공개) + docs/fan_history.md (숫자 요약만)

    .venv/bin/python scripts/fan_history.py          # 매일 실행 (같은 파일을 다시 읽어도 결과는 같음)

왜: 유명 팀 제외는 '지금' 멜론 팬 수로 정해져 과거 기준일 백테스트에 쓰면 미래 정보가 된다(docs/rule_leakage.md).
팬 수를 날짜별로 쌓아 두면, 나중에 '기준일 당시 알던 팬 수'(fans_at)로 유명 판정을 할 수 있다.
- 입력: data/raw/raw_artist_profile_<날짜>_melon*.csv (수집 시각 날짜 = 기록 날짜, 같은 날 여러 번이면 마지막 값)
- 키: 멜론 아티스트 번호 (팀 이름 키 artist_key 도 같이 남김)
- 공개 문서에는 팀 이름 없이 숫자 요약만 쓴다.
"""
from __future__ import annotations

import csv
import json
import sys
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
STATE = RAW_DIR / "state" / "fan_history.json"
OUT = ROOT / "docs" / "fan_history.md"
PATTERN = "raw_artist_profile_*_melon*.csv"


def _fans(text: str) -> Optional[int]:
    t = (text or "").replace(",", "").strip()
    return int(t) if t.isdigit() else None


def collect(raw_dir: Path, history: Dict[str, dict]) -> Dict[str, dict]:
    """멜론 프로필 파일들을 읽어 {멜론 번호: {artist_key, name, points: [[날짜, 팬 수], …]}} — 기존 기록과 합친다."""
    latest: Dict[tuple, tuple] = {}            # (번호, 날짜) → (수집 시각, 팬 수, artist_key, 이름)
    for path in sorted(raw_dir.glob(PATTERN)):
        with open(path, encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                if (r.get("source") or "melon") != "melon":
                    continue
                fans, aid, at = _fans(r.get("fan_count")), (r.get("artist_source_id") or "").strip(), r.get("collected_at") or ""
                if fans is None or not aid or len(at) < 10:
                    continue
                key = (aid, at[:10])
                if key not in latest or at >= latest[key][0]:
                    latest[key] = (at, fans, r.get("artist_key") or "", r.get("artist_text") or "")
    new: Dict[str, dict] = {}
    for (aid, day), (_, fans, akey, name) in sorted(latest.items()):
        entry = new.setdefault(aid, {"artist_key": akey, "name": name, "points": []})
        entry["points"].append([day, fans])
    return merge(history, new)


def merge(old: Dict[str, dict], new: Dict[str, dict]) -> Dict[str, dict]:
    out = {k: {**v, "points": [list(p) for p in v.get("points", [])]} for k, v in old.items()}
    for aid, entry in new.items():
        cur = out.setdefault(aid, {"artist_key": entry.get("artist_key", ""), "name": entry.get("name", ""), "points": []})
        days = {d: f for d, f in cur["points"]}
        days.update({d: f for d, f in entry["points"]})
        cur["points"] = [[d, days[d]] for d in sorted(days)]
        cur["artist_key"] = entry.get("artist_key") or cur.get("artist_key", "")
        cur["name"] = entry.get("name") or cur.get("name", "")
    return out


def fans_at(points: Sequence[Sequence], when: date) -> Optional[int]:
    """그 날짜에 알 수 있던 팬 수 = 그 날짜 이전(같은 날 포함) 마지막 기록. 기록 전이면 None(모름)."""
    known = [f for d, f in points if d <= when.isoformat()]
    return known[-1] if known else None


def summarize(history: Dict[str, dict]) -> dict:
    pts = [v["points"] for v in history.values() if v.get("points")]
    days = sorted({d for p in pts for d, _ in p})
    multi = [p for p in pts if len(p) >= 2]
    changes = [(p[-1][1] - p[0][1]) for p in multi]
    pct = [(p[-1][1] - p[0][1]) / p[0][1] * 100 for p in multi if p[0][1]]
    fans_now = [p[-1][1] for p in pts]
    return {"artists": len(pts), "multi": len(multi), "dates": len(days),
            "first": days[0] if days else None, "last": days[-1] if days else None,
            "up": sum(c > 0 for c in changes), "down": sum(c < 0 for c in changes), "same": sum(c == 0 for c in changes),
            "pct_q": tuple(float(x) for x in np.percentile(pct, [25, 50, 75])) if pct else None,
            "fans_q": tuple(float(x) for x in np.percentile(fans_now, [25, 50, 75])) if fans_now else None,
            "over_10k": sum(f >= 10000 for f in fans_now), "over_1k": sum(f >= 1000 for f in fans_now)}


def build_doc(s: dict) -> List[str]:
    q = s["fans_q"]
    lines = ["# 멜론 팬 수 기록 (요약)", "",
             "_자동 생성: `.venv/bin/python scripts/fan_history.py` · 원본 기록은 `data/raw/state/fan_history.json`(비공개, 커밋 안 함)_", "",
             "**왜 쌓나**: 유명 팀 제외는 '지금' 팬 수로 정해져서, 과거 기준일 검증에는 쓰지 않는다([규칙 시점 점검](rule_leakage.md)). "
             "팬 수를 날짜별로 쌓아 두면 나중에 '기준일 당시 알던 팬 수'로 유명 판정을 할 수 있다(그때 `fame_known_from()`을 기록 시작일로 둔다).", "",
             "| 항목 | 값 |", "|---|---|",
             f"| 팬 수 기록이 있는 아티스트 | {s['artists']:,} |",
             f"| 기록 날짜 | {s['dates']}일 ({s['first'] or '—'} ~ {s['last'] or '—'}) |",
             f"| 두 날짜 이상 기록된 아티스트 (변화를 볼 수 있음) | {s['multi']:,} |",
             f"| 최근 팬 수 사분위 (25%·중앙값·75%) | " + ("—" if not q else f"{q[0]:,.0f} · {q[1]:,.0f} · {q[2]:,.0f}") + " |",
             f"| 팬 1만 이상 / 1천 이상 | {s['over_10k']:,} / {s['over_1k']:,} |"]
    if s["multi"]:
        pq = s["pct_q"]
        lines += [f"| 첫 기록 → 마지막 기록 변화: 늘어남 · 줄어듦 · 같음 | {s['up']} · {s['down']} · {s['same']} |",
                  f"| 변화율 사분위 (%) | " + ("—" if not pq else f"{pq[0]:+.1f} · {pq[1]:+.1f} · {pq[2]:+.1f}") + " |"]
    lines += ["", "**지금 한계**: 멜론 수집기(`collect_artists.py`)는 한 번 받은 아티스트를 다시 받지 않는다(`artist_profile_seen.json`). "
              "그래서 같은 아티스트의 팬 수가 날짜별로 쌓이려면 **관찰 목록(후보 상위·정답 팀)을 주기적으로 다시 받는 모드**가 필요하다. "
              + ("지금은 두 날짜 이상 기록된 아티스트가 없다." if not s["multi"] else ""), ""]
    return lines


def main() -> int:
    try:
        history = json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        history = {}
    history = collect(RAW_DIR, history)
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(history, ensure_ascii=False, indent=1), encoding="utf-8")
    s = summarize(history)
    OUT.write_text("\n".join(build_doc(s)) + "\n", encoding="utf-8")
    print(f"✅ 팬 수 기록 {s['artists']}명 · 날짜 {s['dates']}일 · 두 날짜 이상 {s['multi']}명 → {STATE.relative_to(ROOT)}, {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
