"""점수 재검토 — 매주(월요일) 교차 검증을 다시 돌려 지금 기본 가중치와 비교하고, 바꿀 만하면 '제안'만 남긴다.

    .venv/bin/python scripts/score_review.py     # 몇 분 걸림 (가중치 후보 1만 개 × 기준일 6개)

- 교차 검증은 scripts/score_tune.py 의 tune() 을 그대로 쓰고, docs/score_tuning.md 도 같은 결과로 갱신한다(두 번 계산 안 함).
- 비교 대상: scripts/lab_sql.py DEFAULTS (앱·스냅샷이 쓰는 지금 기본값). 기본값은 절대 자동으로 바꾸지 않는다.
- 제안 ① 점수 변경: 교차 검증(고를 때 안 본 기준일) 평균 가중 AUC가 기본값보다 SCORE_MIN_GAIN 이상 높고,
  기준일 6개 중 MIN_WINS 개 이상에서 앞설 때.  ② 새 신호 반영: 기준일 전체로 고른 추천 가중치에서, 기본값은 0인데
  0보다 크게 골라진 특징이 있고, 추천 가중치의 평균 AUC가 기본값보다 SCORE_MIN_GAIN 이상 높을 때
  (예: 협업 데이터가 쌓여 w_collab 이 골라지면). 추천 가중치는 기준일 전체로 고르므로 아주 작은 차이로도 0 아닌 값이
  뽑힐 수 있어서, 의미 있는 차이가 날 때만 제안한다.
- 결과: docs/data/score_review.json (공개: 숫자·제안만). 일일 기록·진행 점검표가 이 파일을 읽는다.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lab_sql  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "data" / "score_review.json"
SCORE_MIN_GAIN = 0.01   # 평균 AUC 0.01 미만 차이는 정답 1~2팀 순서로도 생기는 흔들림 수준 → 그보다 커야 바꿀 만함
MIN_WINS = 4            # 기준일 6개 중 4개 이상에서 앞서야 한두 시점의 우연이 아니라고 봄
RULES = {"change": f"교차 검증 평균 가중 AUC가 기본값보다 {SCORE_MIN_GAIN} 이상 높고 기준일 {MIN_WINS}개 이상에서 앞서면 점수 변경 제안",
         "new_signal": "기준일 전체로 고른 추천 가중치에서 기본값 0인 특징이 0보다 크게 골라지면 새 신호 반영 제안",
         "note": "제안만 한다 — 기본값(scripts/lab_sql.py DEFAULTS) 변경은 사람이 결정"}


def default_weights(defaults: Dict[str, str], keys) -> Dict[str, float]:
    return {k: float(defaults.get(k, 0) or 0) for k in keys}


def _mean(vals: List[float]) -> Optional[float]:
    return sum(vals) / len(vals) if vals else None


def compare(res: dict, defaults: Dict[str, float], default_eval: Dict[str, dict], cutoffs: List[str]) -> dict:
    """교차 검증 결과(score_tune.tune) + 기본값 평가 → 비교 숫자와 제안."""
    names, evals, picks, table = res["names"], res["evals"], res["picks"], res["table"]
    per_cutoff, pick_aucs, def_aucs, wins = [], [], [], 0
    for c in cutoffs:
        idx = int(picks[c])
        e = evals[idx][c]
        a_pick, a_def = e.get("auc"), (default_eval.get(c) or {}).get("auc")
        per_cutoff.append({"cutoff": c, "n": e.get("n"), "pos": e.get("pos"), "picked": names[idx],
                           "auc_picked": a_pick, "auc_default": a_def})
        if a_pick is None or a_def is None:
            continue
        pick_aucs.append(a_pick)
        def_aucs.append(a_def)
        wins += a_pick > a_def
    best = max(table, key=lambda i: sum(v for v in table[i].values() if v is not None))
    recommended = names[int(best)]
    mean_pick, mean_def = _mean(pick_aucs), _mean(def_aucs)
    both = [c for c in cutoffs if table[best].get(c) is not None and (default_eval.get(c) or {}).get("auc") is not None]
    rec_mean = _mean([table[best][c] for c in both])
    def_all = _mean([default_eval[c]["auc"] for c in both])
    proposals = []
    if mean_pick is not None and mean_def is not None and mean_pick - mean_def >= SCORE_MIN_GAIN and wins >= MIN_WINS:
        proposals.append({"kind": "change", "text": "점수 가중치 변경 제안 (추천 가중치로)",
                          "reason": f"교차 검증 평균 가중 AUC {mean_pick:.3f} vs 기본값 {mean_def:.3f} (+{mean_pick - mean_def:.3f}), "
                                    f"우세 {wins}/{len(pick_aucs)}"})
    new = [k for k, v in recommended.items() if v > 0 and defaults.get(k, 0) == 0]
    if new and rec_mean is not None and def_all is not None and rec_mean - def_all >= SCORE_MIN_GAIN:
        proposals.append({"kind": "new_signal", "text": "새 신호 반영 제안: " + ", ".join(f"{k}={recommended[k]:g}" for k in new),
                          "reason": f"기준일 전체로 고른 추천 가중치(평균 AUC {rec_mean:.3f})가 기본값({def_all:.3f})보다 "
                                    f"+{rec_mean - def_all:.3f}, 기본값 0인 특징이 0보다 크게 골라짐"})
    return {"per_cutoff": per_cutoff, "mean_pick": mean_pick, "mean_default": mean_def, "wins": wins,
            "compared": len(pick_aucs), "recommended": recommended, "recommended_mean": rec_mean,
            "default_mean_all": def_all, "defaults": defaults, "proposals": proposals}


def build_report(cmp: dict, today: str, prev: Optional[dict]) -> dict:
    key = lambda items: sorted((p["kind"], p["text"]) for p in items)   # noqa: E731
    changed_on = today
    if prev and key(prev.get("proposals", [])) == key(cmp["proposals"]):
        changed_on = prev.get("proposals_changed_on") or today
    return {"generated_at": datetime.now().astimezone().isoformat(timespec="seconds"), "run_date": today,
            "rules": RULES, "proposals_changed_on": changed_on, **cmp}


def _load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def main() -> int:
    import score_tune as st

    started = time.time()
    res = st.tune()
    st.main(res)                                    # docs/score_tuning.md 같은 결과로 갱신
    defaults = default_weights(lab_sql.DEFAULTS, st.GRID)
    cmp = compare(res, defaults, st.evaluate(res["data"], defaults), st.CUTOFFS)
    report = build_report(cmp, date.today().isoformat(), _load(OUT))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    mins = (time.time() - started) / 60
    print(f"✅ 점수 재검토 ({mins:.1f}분): 교차 검증 평균 {cmp['mean_pick']:.3f} vs 기본값 {cmp['mean_default']:.3f}, "
          f"우세 {cmp['wins']}/{cmp['compared']}, 제안 {len(cmp['proposals'])}건 → {OUT.relative_to(ROOT)}")
    for p in cmp["proposals"]:
        print(f"  - {p['text']} · {p['reason']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
