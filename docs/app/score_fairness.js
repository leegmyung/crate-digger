/**
 * 점수 신뢰도 '같은 기준 판' 한 줄 — docs/score_leak_audit_2026-11-28.md (결과 docs/data/score_leak_audit.json).
 * 과거 검증의 신인 판정이 '정답 팀 위주로 받은 멜론 프로필' 첫 발매일을 써서, 모든 팀에 같은 기준(팀을 고르지 않은
 * 발매 원본)으로 맞춘 판(D)보다 AUC가 약 0.04 높다. 점수 정의는 그대로 두고 두 숫자를 나란히 보여 준다.
 */

function num(v) {
  return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

function pair(v2, cv) {
  return cv === null ? v2.toFixed(3) : `${v2.toFixed(3)} (교차 검증 ${cv.toFixed(3)})`;
}

/**
 * 홈 근거 줄용 짧은 한 줄 — '점수 성적 AUC 0.827 · 같은 기준 0.788 (교차 검증 0.783)'.
 * @param {object|null} audit score_leak_audit.json
 * @returns {string}
 */
export function fairnessShort(audit) {
  const baseV2 = num(audit?.base?.auc_v2);
  const fairV2 = num(audit?.D_untargeted_debut?.auc_v2);
  if (baseV2 === null || fairV2 === null) return '';
  const fairCv = num(audit?.D_untargeted_debut?.auc_cv);
  return `점수 성적 AUC ${baseV2.toFixed(3)} · 같은 기준 ${pair(fairV2, fairCv)}`;
}

/**
 * @param {object|null} audit score_leak_audit.json
 * @returns {string} 화면 한 줄 (값이 없으면 '')
 */
export function fairnessLine(audit) {
  const base = audit?.base;
  const fair = audit?.D_untargeted_debut;
  const baseV2 = num(base?.auc_v2);
  const fairV2 = num(fair?.auc_v2);
  if (baseV2 === null || fairV2 === null) return '';
  const baseCv = num(base?.auc_cv);
  const fairCv = num(fair?.auc_cv);
  const both = baseCv !== null && fairCv !== null;
  return `같은 기준 판 ${pair(fairV2, both ? fairCv : null)} · 지금 판 ${pair(baseV2, both ? baseCv : null)}`
    + ' — 지금 판은 신인 확인을 정답 팀 위주로 받은 멜론 프로필로 해서 나이 많은 정답 팀만 빠져 높게 나옵니다.';
}
