/**
 * 5-1 저장 필터 — '내 목록' 한 칸(mine_store.js)에 저장. 막혀 있으면(사생활 보호 창 등) 이 탭 안에서만 기억한다.
 * 한 항목: { id, name, hash, spec, created }  — hash 는 후보 목록 주소, spec 은 components/saved_match.js 규격.
 */
import { appState, cloneDefaults, parseHash, resetViewFilters } from './state.js';
import { readMineSection, writeMineSection } from './mine_store.js';

export const SAVED_MAX = 10;
// 저장은 '내 목록' 한 칸(mine_store.js 의 filters) — 옛 키 cd_saved_filters_v1 은 처음 읽을 때 옮겨짐

function validItem(it) {
  return it && typeof it === 'object' && typeof it.id === 'string' && typeof it.name === 'string'
    && typeof it.hash === 'string' && (it.hash.startsWith('#/candidates') || it.hash.startsWith('#/discover'))
    && it.spec && typeof it.spec === 'object';
}

export function listSavedFilters() {
  return readMineSection('filters').filter(validItem).slice(0, SAVED_MAX);
}

/** @returns {boolean} 브라우저에 저장됐으면 true (막혔으면 이 탭에서만 기억) */
function persist(list) {
  return writeMineSection('filters', list.slice(0, SAVED_MAX));
}

/** @returns {{ ok: boolean, persisted: boolean, item?: object, reason?: string }} */
export function addSavedFilter({ name, hash, spec }) {
  const list = listSavedFilters();
  if (list.length >= SAVED_MAX) return { ok: false, persisted: false, reason: `저장 필터는 ${SAVED_MAX}개까지입니다` };
  const item = {
    id: `f${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`,
    name: String(name || '').trim() || '이름 없는 필터',
    hash,
    spec,
    created: new Date().toISOString().slice(0, 10),
  };
  const persisted = persist([...list, item]);
  return { ok: true, persisted, item };
}

export function renameSavedFilter(id, name) {
  const clean = String(name || '').trim();
  if (!clean) return false;
  return persist(listSavedFilters().map(it => (it.id === id ? { ...it, name: clean } : it)));
}

export function removeSavedFilter(id) {
  return persist(listSavedFilters().filter(it => it.id !== id));
}

/** 저장 필터 적용: 기본값으로 되돌린 뒤 저장한 주소를 연다(주소에 없는 조건이 남지 않게) */
export function applySavedFilter(item) {
  if (!validItem(item)) return;
  appState.cfg = cloneDefaults();
  appState.cfg.as_of = appState.dataEnd;
  resetViewFilters();
  if (window.location.hash === item.hash) {
    parseHash();
    window.dispatchEvent(new CustomEvent('app:route'));
  } else {
    window.location.hash = item.hash;
  }
}
