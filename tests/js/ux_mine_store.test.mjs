// '담기' 하나로 (docs/ux_simplify_2026-11-28.md ⑦) — 관심 팀·저장 필터·구독 공연장을 한 저장 칸(cd_mine_v1)으로.
// 옛 저장값 3개(crate_digger_watchlist_v1 · cd_saved_filters_v1 · cd_venue_subs_v1)는 처음 읽을 때 그대로 옮겨진다. (node --test)
import { test, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import {
  LEGACY_MINE_KEYS, MINE_KEY, buildMineFromLegacy, readMineSection, resetMineMemory, writeMineSection,
} from '../../docs/app/mine_store.js';
import { applyKeyAliases } from '../../docs/app/key_aliases.js';

function memStorage(init = {}) {
  const m = new Map(Object.entries(init));
  return { map: m, getItem: k => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)) };
}

const TEAM = { team_key: 'pcr', display_name: 'PCR', added_at: '2026-11-01', status: 'listened' };
const FILTER = { id: 'f1', name: '부산 록', hash: '#/discover?genre=록', spec: { cfg: { genre: '록' } }, created: '2026-11-20' };

beforeEach(() => resetMineMemory());

test('옛 저장값 3개 → 한 칸으로 옮김 (옛 칸은 지우지 않음)', () => {
  const s = memStorage({
    [LEGACY_MINE_KEYS.teams]: JSON.stringify([TEAM]),
    [LEGACY_MINE_KEYS.filters]: JSON.stringify([FILTER]),
    [LEGACY_MINE_KEYS.venues]: JSON.stringify(['Club FF', '롤링홀']),
  });
  assert.deepEqual(readMineSection('teams', s), [TEAM]);
  assert.deepEqual(readMineSection('filters', s), [FILTER]);
  assert.deepEqual(readMineSection('venues', s), ['Club FF', '롤링홀']);
  const saved = JSON.parse(s.getItem(MINE_KEY));
  assert.equal(saved.v, 1);
  assert.deepEqual(saved.teams, [TEAM]);
  assert.ok(s.getItem(LEGACY_MINE_KEYS.teams), '옛 칸은 그대로 (예전 화면으로 돌아가도 읽힘)');
});

test('새 칸이 있으면 새 칸을 믿고 옛 칸은 다시 읽지 않음', () => {
  const s = memStorage({
    [MINE_KEY]: JSON.stringify({ v: 1, teams: [], venues: ['Club FF'], filters: [] }),
    [LEGACY_MINE_KEYS.teams]: JSON.stringify([TEAM]),
  });
  assert.deepEqual(readMineSection('teams', s), []);
  assert.deepEqual(readMineSection('venues', s), ['Club FF']);
});

test('깨진 옛 값·배열 아닌 값은 빈 목록으로', () => {
  const s = memStorage({ [LEGACY_MINE_KEYS.teams]: '{깨짐', [LEGACY_MINE_KEYS.venues]: '"문자열"' });
  assert.deepEqual(buildMineFromLegacy(k => s.getItem(k)), { v: 1, teams: [], venues: [], filters: [] });
  assert.deepEqual(readMineSection('teams', s), []);
  assert.equal(s.getItem(MINE_KEY), null, '옮길 것이 없으면 새 칸을 만들지 않음');
});

test('쓰기: 한 칸만 바꾸고 나머지는 그대로', () => {
  const s = memStorage({ [LEGACY_MINE_KEYS.venues]: JSON.stringify(['Club FF']) });
  assert.equal(writeMineSection('teams', [TEAM], s), true);
  const saved = JSON.parse(s.getItem(MINE_KEY));
  assert.deepEqual(saved.teams, [TEAM]);
  assert.deepEqual(saved.venues, ['Club FF']);
});

test('저장소가 막히면 이 탭 메모리로 (쓰기 false, 읽기는 메모리 값)', () => {
  const blocked = { getItem: () => { throw new Error('막힘'); }, setItem: () => { throw new Error('막힘'); } };
  assert.deepEqual(readMineSection('teams', blocked), []);
  assert.equal(writeMineSection('teams', [TEAM], blocked), false);
  assert.deepEqual(readMineSection('teams', blocked), [TEAM]);
});

test('모르는 칸 이름은 빈 목록·쓰기 거절', () => {
  const s = memStorage();
  assert.deepEqual(readMineSection('nope', s), []);
  assert.equal(writeMineSection('nope', [1], s), false);
});

test('팀 키 바뀜(key_aliases)이 새 칸의 관심 팀도 옮김', () => {
  const s = memStorage({ [MINE_KEY]: JSON.stringify({ v: 1, teams: [{ team_key: 'sole', display_name: 'SOLE' }], venues: [], filters: [] }) });
  const n = applyKeyAliases(new Map([['sole', '쏠']]), s);
  assert.equal(n.watch, 1);
  assert.equal(JSON.parse(s.getItem(MINE_KEY)).teams[0].team_key, '쏠');
  assert.deepEqual(applyKeyAliases(new Map([['sole', '쏠']]), s), { watch: 0, compare: 0 });
});
