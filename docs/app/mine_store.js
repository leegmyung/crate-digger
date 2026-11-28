/**
 * '내 목록' 한 칸 저장 (docs/ux_simplify_2026-11-28.md ⑦) — 관심 팀·구독 공연장·저장한 필터를 '담기' 하나로 모은다.
 * 브라우저 저장(localStorage) 키 하나 = { v: 1, teams: [], venues: [], filters: [] }.
 *
 * 옛 저장값 이전: 새 칸이 없으면 처음 읽을 때 옛 키 3개를 읽어 한 칸으로 옮긴다.
 * 옛 키는 지우지 않는다(예전 화면을 다시 열어도 그때까지 담은 것이 보이게). 새 칸이 생기면 새 칸만 믿는다.
 * 저장소가 막히면(사생활 보호 창 등) 이 탭 메모리에서만 기억한다.
 * 칸마다 항목 검사는 주인 모듈(state.js 관심 팀 · saved_filters.js · venue_subs.js)이 한다.
 */
export const MINE_KEY = 'cd_mine_v1';
export const LEGACY_MINE_KEYS = Object.freeze({
  teams: 'crate_digger_watchlist_v1',
  filters: 'cd_saved_filters_v1',
  venues: 'cd_venue_subs_v1',
});
const SECTIONS = ['teams', 'venues', 'filters'];

let memory = null;      // 마지막으로 읽거나 쓴 값
let blocked = false;    // 한 번이라도 쓰기가 막히면 이 탭에선 메모리 값을 믿는다

function emptyMine() {
  return { v: 1, teams: [], venues: [], filters: [] };
}

function parseArray(raw) {
  if (!raw) return [];
  try {
    const arr = JSON.parse(raw);
    return Array.isArray(arr) ? arr : [];
  } catch (_) {
    return [];
  }
}

function normalizeMine(obj) {
  const out = emptyMine();
  if (!obj || typeof obj !== 'object') return out;
  for (const s of SECTIONS) out[s] = Array.isArray(obj[s]) ? obj[s] : [];
  return out;
}

function cloneMine(m) {
  return { v: 1, teams: [...m.teams], venues: [...m.venues], filters: [...m.filters] };
}

function storageOf(storage) {
  if (storage) return storage;
  try {
    return globalThis.localStorage || null;
  } catch (_) {
    return null;
  }
}

/** 옛 키 3개 → 한 칸 (읽기 함수만 받아 순수하게) */
export function buildMineFromLegacy(getItem) {
  const out = emptyMine();
  for (const s of SECTIONS) {
    let raw = null;
    try {
      raw = getItem(LEGACY_MINE_KEYS[s]);
    } catch (_) {
      raw = null;
    }
    out[s] = parseArray(raw);
  }
  return out;
}

function loadMine(storage) {
  if (blocked && memory) return memory;
  const st = storageOf(storage);
  if (!st) return memory || (memory = emptyMine());
  try {
    const raw = st.getItem(MINE_KEY);
    if (raw) {
      memory = normalizeMine(JSON.parse(raw));
      return memory;
    }
    const migrated = buildMineFromLegacy(k => st.getItem(k));
    memory = migrated;
    if (SECTIONS.some(s => migrated[s].length)) {
      try {
        st.setItem(MINE_KEY, JSON.stringify(migrated));
      } catch (_) {
        blocked = true;
      }
    }
    return memory;
  } catch (_) {
    return memory || (memory = emptyMine());
  }
}

/** @param {'teams'|'venues'|'filters'} name */
export function readMineSection(name, storage) {
  if (!SECTIONS.includes(name)) return [];
  return [...loadMine(storage)[name]];
}

/** @returns {boolean} 브라우저에 저장됐으면 true (막혔으면 이 탭 메모리에만) */
export function writeMineSection(name, list, storage) {
  if (!SECTIONS.includes(name) || !Array.isArray(list)) return false;
  const next = { ...cloneMine(loadMine(storage)), [name]: [...list] };
  memory = next;
  const st = storageOf(storage);
  if (!st) {
    blocked = true;
    return false;
  }
  try {
    st.setItem(MINE_KEY, JSON.stringify(next));
    return true;
  } catch (_) {
    blocked = true;
    return false;
  }
}

/** 시험용: 메모리·막힘 상태를 처음으로 */
export function resetMineMemory() {
  memory = null;
  blocked = false;
}
