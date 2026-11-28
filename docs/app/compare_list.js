/**
 * 팀 나란히 비교 — '비교에 담기' 목록 (Chartmetric '비교'처럼, 최대 4팀).
 * 규칙 함수는 순수(tests/js/compare_list.test.mjs), 저장은 브라우저(localStorage, 막히면 이 탭 메모리).
 */

export const COMPARE_MAX = 4;
const KEY = 'gr_compare_v1';
export const COMPARE_STORAGE_KEY = KEY;   // key_aliases.js 가 팀 키 바뀜을 옮길 때도 씀
let memory = [];

/**
 * 주소의 teams 값('a,b,c') → 팀 키 배열 (빈칸·중복 빼고 최대 4팀). 각 칸은 이미 decode 된 값이어야 함.
 * @param {string|null} raw
 * @returns {string[]}
 */
export function parseCompareKeys(raw) {
  const out = [];
  for (const k of String(raw || '').split(',').map(s => s.trim())) {
    if (k && !out.includes(k)) out.push(k);
    if (out.length >= COMPARE_MAX) break;
  }
  return out;
}

/**
 * 담기·빼기 (원래 배열은 그대로 두고 새 배열).
 * @param {string[]} list
 * @param {string} key
 * @returns {{ list: string[], added: boolean, full: boolean }}
 */
export function toggleCompareKey(list, key) {
  const cur = [...(list || [])];
  if (!key) return { list: cur, added: false, full: false };
  if (cur.includes(key)) return { list: cur.filter(k => k !== key), added: false, full: false };
  if (cur.length >= COMPARE_MAX) return { list: cur, added: false, full: true };
  return { list: [...cur, key], added: true, full: false };
}

/** 비교 화면 주소. 팀 키는 하나씩 인코딩(키 안 쉼표도 %2C 로). */
export function compareHash(keys) {
  const ks = (keys || []).filter(Boolean);
  return ks.length ? `#/compare?teams=${ks.map(encodeURIComponent).join(',')}` : '#/compare';
}

/** 주소 쿼리의 teams 원문(인코딩된 채) → 팀 키 배열. URLSearchParams 는 %2C 를 쉼표로 풀어 버리므로 원문을 먼저 나눈 뒤 칸마다 푼다. */
export function compareKeysFromQuery(queryPart) {
  const m = String(queryPart || '').match(/(?:^|&)teams=([^&]*)/);
  if (!m) return [];
  const out = [];
  for (const seg of m[1].split(',')) {
    let k = '';
    try { k = decodeURIComponent(seg.replace(/\+/g, ' ')).trim(); } catch (_) { k = ''; }
    if (k && !out.includes(k)) out.push(k);
    if (out.length >= COMPARE_MAX) break;
  }
  return out;
}

export function getCompareList() {
  try {
    const raw = window.localStorage.getItem(KEY);
    if (raw) {
      const arr = JSON.parse(raw);
      if (Array.isArray(arr)) memory = arr.filter(k => typeof k === 'string' && k).slice(0, COMPARE_MAX);
    }
  } catch (_) { /* 저장소가 막힘 → 메모리 값 */ }
  return [...memory];
}

export function setCompareList(list) {
  memory = (list || []).slice(0, COMPARE_MAX);
  try {
    window.localStorage.setItem(KEY, JSON.stringify(memory));
  } catch (_) { /* 이 탭 안에서만 기억 */ }
  window.dispatchEvent(new CustomEvent('app:compare-changed', { detail: [...memory] }));
  return [...memory];
}
