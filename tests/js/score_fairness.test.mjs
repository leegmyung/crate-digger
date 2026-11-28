// 점수 신뢰도 '같은 기준 판' 한 줄 (docs/score_leak_audit_2026-11-28.md, docs/data/score_leak_audit.json) — node --test
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { fairnessLine } from '../../docs/app/score_fairness.js';

const AUDIT = {
  base: { auc_v2: 0.8271, auc_cv: 0.8093 },
  D_untargeted_debut: { auc_v2: 0.7881, auc_cv: 0.7831 },
};

test('같은 기준 판과 지금 판을 나란히, 차이 이유 한 줄', () => {
  const line = fairnessLine(AUDIT);
  assert.match(line, /같은 기준 판 0\.788 \(교차 검증 0\.783\)/);
  assert.match(line, /지금 판 0\.827 \(교차 검증 0\.809\)/);
  assert.match(line, /정답 팀 위주로 받은 멜론 프로필/);
});

test('교차 검증 값이 없으면 v2만', () => {
  const line = fairnessLine({ base: { auc_v2: 0.8271 }, D_untargeted_debut: { auc_v2: 0.7881 } });
  assert.match(line, /같은 기준 판 0\.788 · 지금 판 0\.827/);
});

test('결과가 없거나 깨졌으면 빈 문자열', () => {
  assert.equal(fairnessLine(null), '');
  assert.equal(fairnessLine({}), '');
  assert.equal(fairnessLine({ base: { auc_v2: 'x' }, D_untargeted_debut: { auc_v2: 0.78 } }), '');
});
