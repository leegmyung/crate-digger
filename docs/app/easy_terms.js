/**
 * 쉬운 말 바꾸기 (docs/ux_simplify_2026-11-28.md ⑥) — 자료 파일(alerts.json 등)에서 오는 글자에 남은 안쪽 용어를 화면에서 바꾼다.
 * 자료 파일은 매일 21시 스크립트가 새로 만들기 때문에, 앱이 읽을 때 한 번 바꾼다(자료 값·종류 코드는 그대로).
 * 순수 함수 (tests/js/ux_terms.test.mjs).
 */

// 긴 말부터 바꾼다(짧은 말이 먼저 바뀌어 긴 말을 깨뜨리지 않게)
const REPLACEMENTS = [
  [/선정·중간 정답/g, '선정·수상 후보'],
  [/여러 갈래/g, '여러 곳에서 보임'],
  [/(\d+)개 갈래/g, '신호 $1종류'],
  [/백지 신인/g, '언급 전 신인'],
  [/백지/g, '언급 전'],
  [/맥락 매체/g, '큰 매거진'],
  [/발굴 매체/g, '신인 소개 매체'],
  [/같은 집안/g, '같은 주최'],
  [/센 정답/g, '수상·선정'],
  [/정답/g, '수상·선정'],
  [/갈래/g, '신호 종류'],
  [/체급/g, '공연장 크기'],
];

/** @param {unknown} text @returns {string} */
export function easyText(text) {
  if (text === null || text === undefined) return '';
  let s = String(text);
  for (const [re, to] of REPLACEMENTS) s = s.replace(re, to);
  return s;
}

/** 알림 종류 코드 → 쉬운 이름 (앱 이름이 자료 파일 이름보다 먼저) */
export const EASY_ALERT_TYPE_LABELS = Object.freeze({
  new_outcome: '새 수상·선정',
  new_selection: '새 선정·지원',
  blank_first_mention: '언급 전 신인 첫 언급',
  stage_up: '단계 상승',
  big_venue_first: '큰 공연장 첫 출연',
  peer_winner: '같은 무대 수상 팀',
  rank_jump: '순위 급상승',
  spike: '언급 급증',
  new_gig: '새 공연',
});

/**
 * @param {string} type
 * @param {Record<string,string>} [dataTypes] alerts.json 의 types
 */
export function easyAlertTypeLabel(type, dataTypes = {}) {
  const t = String(type || '');
  return EASY_ALERT_TYPE_LABELS[t] || easyText(dataTypes?.[t] || t);
}
