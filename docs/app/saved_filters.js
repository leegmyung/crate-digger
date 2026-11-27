/**
 * 5-1 저장 필터 — 브라우저 저장(localStorage). 막혀 있으면(사생활 보호 창 등) 이 탭 안에서만 기억한다.
 * 한 항목: { id, name, hash, spec, created }  — hash 는 후보 목록 주소, spec 은 components/saved_match.js 규격.
 */
import { appState, cloneDefaults, parseHash, resetViewFilters } from './state.js';

const KEY = 'cd_saved_filters_v1';
export const SAVED_MAX = 10;
let memory = [];
let writeBlocked = false; // 한 번이라도 쓰기가 막히면 이 탭에선 메모리 값을 믿는다(읽기만 되는 저장소 대비)

function validItem(it) {
  return it && typeof it === 'object' && typeof it.id === 'string' && typeof it.name === 'string'
    && typeof it.hash === 'string' && it.hash.startsWith('#/candidates') && it.spec && typeof it.spec === 'object';
}

export function listSavedFilters() {
  if (writeBlocked) return [...memory];
  try {
    const raw = window.localStorage.getItem(KEY);
    if (raw) {
      const arr = JSON.parse(raw);
      if (Array.isArray(arr)) {
        memory = arr.filter(validItem).slice(0, SAVED_MAX);
        return [...memory];
      }
    }
  } catch (_) {
    // 저장소가 막혔거나 깨짐 → 메모리 값 사용
  }
  return [...memory];
}

function persist(list) {
  memory = list.slice(0, SAVED_MAX);
  try {
    window.localStorage.setItem(KEY, JSON.stringify(memory));
    return true;
  } catch (_) {
    writeBlocked = true;
    return false; // 화면은 그대로 동작(이 탭 안에서만 기억)
  }
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
