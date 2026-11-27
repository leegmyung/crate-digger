"""점수 재검토(score_review): 매주 교차 검증 결과를 지금 기본값과 비교해 '점수 변경'·'새 신호 반영'을 제안만 한다."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import score_review as sr  # noqa: E402

CUTS = ["c1", "c2", "c3", "c4", "c5", "c6"]
BASE = {"w_branch": 1.0, "w_stage": 1.0, "w_collab": 0.0}


def fake_res(pick_aucs, picks_weights=None, all_best=None):
    """교차 검증 결과 흉내: 후보 가중치 0번(=picks)이 기준일마다 pick_aucs 의 AUC."""
    w0 = picks_weights or {"w_branch": 2.0, "w_stage": 1.0, "w_collab": 0.0}
    w1 = all_best or w0
    evals = {0: {c: {"auc": a, "n": 100, "pos": 5} for c, a in zip(CUTS, pick_aucs)},
             1: {c: {"auc": 0.9, "n": 100, "pos": 5} for c in CUTS}}   # 1번은 전체 합이 가장 큼 → 추천 가중치
    return {"names": {0: w0, 1: w1}, "evals": evals, "picks": {c: "0" for c in CUTS},
            "table": {"0": {c: a for c, a in zip(CUTS, pick_aucs)}, "1": {c: 0.9 for c in CUTS}}}


def default_eval(aucs):
    return {c: {"auc": a} for c, a in zip(CUTS, aucs)}


class CompareTest(unittest.TestCase):
    def test_change_proposed_when_gain_and_wins(self):
        out = sr.compare(fake_res([0.72] * 6), BASE, default_eval([0.70] * 6), CUTS)
        self.assertAlmostEqual(out["mean_pick"], 0.72)
        self.assertAlmostEqual(out["mean_default"], 0.70)
        self.assertEqual(out["wins"], 6)
        self.assertEqual([p["kind"] for p in out["proposals"]], ["change"])

    def test_no_change_when_gain_small_or_few_wins(self):
        small = sr.compare(fake_res([0.705] * 6), BASE, default_eval([0.70] * 6), CUTS)
        self.assertEqual(small["proposals"], [])
        few = sr.compare(fake_res([0.80, 0.80, 0.80, 0.60, 0.60, 0.60]), BASE, default_eval([0.70] * 6), CUTS)
        self.assertEqual(few["wins"], 3)
        self.assertEqual(few["proposals"], [])                      # 평균은 같고 우세 3/6 → 제안 없음

    def test_new_signal_when_recommended_weight_turns_positive(self):
        rec = {"w_branch": 1.0, "w_stage": 1.0, "w_collab": 0.5}
        out = sr.compare(fake_res([0.70] * 6, all_best=rec), BASE, default_eval([0.70] * 6), CUTS)
        kinds = [p["kind"] for p in out["proposals"]]
        self.assertEqual(kinds, ["new_signal"])
        self.assertIn("w_collab", out["proposals"][0]["text"])
        self.assertEqual(out["recommended"], rec)

    def test_new_signal_needs_real_gain_over_default(self):
        # 추천 가중치는 기준일 전체로 고르므로 기본값보다 아주 조금만 나아도 0 아닌 값이 뽑힐 수 있음 → 0.01 이상 나아야 제안
        rec = {"w_branch": 1.0, "w_stage": 1.0, "w_collab": 0.5}
        res = fake_res([0.70] * 6, all_best=rec)
        res["table"]["1"] = {c: 0.705 for c in CUTS}
        out = sr.compare(res, BASE, default_eval([0.70] * 6), CUTS)
        self.assertEqual(out["proposals"], [])
        self.assertAlmostEqual(out["recommended_mean"], 0.705)

    def test_missing_auc_cutoffs_skipped(self):
        res = fake_res([None, 0.72, 0.72, 0.72, 0.72, 0.72])
        out = sr.compare(res, BASE, default_eval([0.70] * 6), CUTS)
        self.assertEqual(out["compared"], 5)


class DefaultsTest(unittest.TestCase):
    def test_default_weights_from_lab_sql_strings(self):
        self.assertEqual(sr.default_weights({"w_branch": "1", "w_context": "0.5", "limit": "100"}, ["w_branch", "w_context", "w_collab"]),
                         {"w_branch": 1.0, "w_context": 0.5, "w_collab": 0.0})


class ReportTest(unittest.TestCase):
    def test_changed_on_kept_when_same(self):
        cmp1 = {"proposals": [{"kind": "change", "text": "x", "reason": "y"}], "mean_pick": 0.7, "mean_default": 0.69,
                "wins": 4, "compared": 6, "per_cutoff": [], "recommended": {}, "defaults": {}}
        first = sr.build_report(cmp1, "2026-11-30", prev=None)
        self.assertEqual(first["proposals_changed_on"], "2026-11-30")
        again = sr.build_report(cmp1, "2026-12-07", prev=first)
        self.assertEqual(again["proposals_changed_on"], "2026-11-30")
        self.assertEqual(again["run_date"], "2026-12-07")
        self.assertIn("rules", again)


class NoteAndStatusTest(unittest.TestCase):
    REP = {"run_date": "2026-11-30", "proposals_changed_on": "2026-11-30", "mean_pick": 0.72, "mean_default": 0.70,
           "wins": 5, "compared": 6, "proposals": [{"kind": "change", "text": "점수 가중치 변경 제안", "reason": "평균 +0.02"}]}

    def test_daily_note_section_only_on_run_day_with_proposals(self):
        import daily_note as dn
        lines = dn.score_review_section("2026-11-30", self.REP)
        self.assertIn("## 점수 재검토 제안 1건", lines)
        self.assertEqual(dn.score_review_section("2026-12-01", self.REP), [])
        self.assertEqual(dn.score_review_section("2026-11-30", {**self.REP, "proposals": []}), [])
        self.assertEqual(dn.score_review_section("2026-11-30", None), [])
        md = dn.render_note("2026-11-30", [], [], {}, score_review=self.REP)
        self.assertIn("점수 재검토 제안", md)

    def test_status_report_line(self):
        import build_status_report as bs
        self.assertIn("점수 재검토 2026-11-30", bs.score_review_line(self.REP))
        self.assertIn("1건", bs.score_review_line(self.REP))
        self.assertIn("아직", bs.score_review_line(None))


if __name__ == "__main__":
    unittest.main()
