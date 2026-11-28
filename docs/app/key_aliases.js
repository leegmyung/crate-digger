/**
 * 팀 대표 키가 바뀐 뒤(연결표 다시 적재: thevolunteers → 더발룬티어스) 저장된 관심 팀·비교 담기·옛 주소를 새 키로.
 * 표: docs/lab/data/key_aliases.csv (scripts/key_aliases.py, 매일 21시). 앱이 열 때 한 번 옮기고, 주소는 바뀔 때마다 고친다.
 * 규칙 함수는 순수(tests/js/key_aliases.test.mjs).
 */
import { COMPARE_STORAGE_KEY } from './compare_list.js';
import { WATCH_KEY } from './state.js';

/**
 * @param {string|null} text 'old_key,new_key' CSV
 * @returns {Map<string,string>}
 */
export function parseAliasCsv(text) {
  const map = new Map();
  const lines = String(text || '').split(/\r?\n/).slice(1);
  for (const line of lines) {
    const i = line.indexOf(',');
    if (i <= 0) continue;
    const oldKey = line.slice(0, i).trim();
    const newKey = line.slice(i + 1).trim();
    if (oldKey && newKey && oldKey !== newKey) map.set(oldKey, newKey);
  }
  return map;
}

/**
 * @param {string[]} keys
 * @param {Map<string,string>} map
 * @returns {string[]} 바꾼 키, 겹치면 앞의 것만
 */
export function remapKeyList(keys, map) {
  const out = [];
  for (const k of keys || []) {
    const nk = map.get(k) || k;
    if (nk && !out.includes(nk)) out.push(nk);
  }
  return out;
}

/**
 * @param {Array<{team_key:string}>} items 관심 팀 목록
 * @param {Map<string,string>} map
 * @returns {Array<object>} 키만 바꾼 새 목록 (겹치면 앞의 것)
 */
export function remapWatchItems(items, map) {
  const seen = new Set();
  const out = [];
  for (const it of items || []) {
    const key = map.get(it.team_key) || it.team_key;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push({ ...it, team_key: key });
  }
  return out;
}

function decodeSeg(seg) {
  try { return decodeURIComponent(seg); } catch (_) { return seg; }
}

/**
 * '#/team/<옛키>/<탭>' · '#/compare?teams=a,b' 의 옛 키를 새 키로. 바뀔 게 없으면 같은 글자.
 * @param {string} hash
 * @param {Map<string,string>} map
 * @returns {string}
 */
export function remapHash(hash, map) {
  const h = String(hash || '');
  if (!map?.size) return h;
  const team = h.match(/^#\/team\/([^/?]+)(.*)$/);
  if (team) {
    const nk = map.get(decodeSeg(team[1]));
    return nk ? `#/team/${encodeURIComponent(nk)}${team[2]}` : h;
  }
  const cmp = h.match(/^(#\/compare\?(?:.*&)?teams=)([^&]*)(.*)$/);
  if (cmp) {
    const keys = cmp[2].split(',').map(decodeSeg);
    if (!keys.some(k => map.has(k))) return h;
    return `${cmp[1]}${remapKeyList(keys, map).map(encodeURIComponent).join(',')}${cmp[3]}`;
  }
  return h;
}

function moveJson(storage, key, fn) {
  const raw = storage.getItem(key);
  if (!raw) return false;
  const before = JSON.parse(raw);
  if (!Array.isArray(before)) return false;
  const after = fn(before);
  if (JSON.stringify(after) === JSON.stringify(before)) return false;
  storage.setItem(key, JSON.stringify(after));
  return true;
}

/**
 * 저장된 관심 팀·비교 담기를 새 키로 옮긴다. 저장소가 막혀 있으면 아무것도 안 함.
 * @param {Map<string,string>} map
 * @param {{getItem:Function,setItem:Function}} [storage]
 * @returns {{watch:number, compare:number}} 옮긴 저장값 수(0·1)
 */
export function applyKeyAliases(map, storage = globalThis.localStorage) {
  const res = { watch: 0, compare: 0 };
  if (!map?.size || !storage) return res;
  try {
    res.watch = moveJson(storage, WATCH_KEY, list => remapWatchItems(list.filter(i => i && typeof i.team_key === 'string'), map)) ? 1 : 0;
    res.compare = moveJson(storage, COMPARE_STORAGE_KEY, list => remapKeyList(list.filter(k => typeof k === 'string'), map)) ? 1 : 0;
  } catch (_) {
    return { watch: 0, compare: 0 };
  }
  return res;
}
