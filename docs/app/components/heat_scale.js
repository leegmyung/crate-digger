/**
 * 색 지도(2-5)·동료 비교용 1~5 등급 계산 — 다른 모듈을 부르지 않는 순수 함수만 둔다.
 * 등급 경계는 docs/lab/sql/peer_compare.sql 의 등급과 같다:
 *   상위 10%(백분위 ≥ 0.9) = 5 · 상위 30% = 4 · 상위 70% = 3 · 상위 90% = 2 · 나머지 = 1
 */

/** 백분위 하한 → 등급 (높은 등급부터 검사) */
export const HEAT_BOUNDS = [
  [0.9, 5],
  [0.7, 4],
  [0.3, 3],
  [0.1, 2],
];

/**
 * 0~1 백분위(클수록 좋음)를 1~5 등급으로. 값이 없으면 null(= 자료 없음, 0과 구분).
 * @param {number|string|null|undefined} pct
 * @returns {number|null}
 */
export function heatLevel(pct) {
  if (pct === null || pct === undefined || pct === '') return null;
  const v = Number(pct);
  if (!Number.isFinite(v)) return null;
  const hit = HEAT_BOUNDS.find(([lo]) => v >= lo);
  return hit ? hit[1] : 1;
}

/**
 * DuckDB PERCENT_RANK 와 같은 방식(동점은 낮은 쪽, (순위-1)/(n-1))으로 백분위를 만든다.
 * 빈 값(null·undefined·숫자 아님)은 계산에서 빼고 null 로 돌려준다. 원본 배열은 바꾸지 않는다.
 * @param {Array<number|null|undefined>} values
 * @returns {Array<number|null>}
 */
export function percentRanks(values) {
  const nums = values
    .map(v => (v === null || v === undefined || v === '' ? NaN : Number(v)))
    .map(v => (Number.isFinite(v) ? v : null));
  const sorted = nums.filter(v => v !== null).sort((a, b) => a - b);
  const n = sorted.length;
  const firstIdx = new Map();
  sorted.forEach((v, i) => {
    if (!firstIdx.has(v)) firstIdx.set(v, i);
  });
  return nums.map(v => {
    if (v === null) return null;
    return n <= 1 ? 0 : firstIdx.get(v) / (n - 1);
  });
}
