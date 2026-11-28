// 팀 대표 키가 바뀐 뒤 저장된 관심 팀·비교 담기·옛 주소를 새 키로 (docs/app/key_aliases.js, node --test)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  applyKeyAliases, parseAliasCsv, remapHash, remapKeyList, remapWatchItems,
} from '../../docs/app/key_aliases.js';

const MAP = parseAliasCsv('old_key,new_key\nthevolunteers,더발룬티어스\nsole,쏠\n강형호,pitta\n\n');

test('CSV 읽기', () => {
  assert.equal(MAP.size, 3);
  assert.equal(MAP.get('sole'), '쏠');
  assert.equal(parseAliasCsv('').size, 0);
  assert.equal(parseAliasCsv(null).size, 0);
});

test('키 목록: 바꾸고 겹치면 하나만, 순서 유지', () => {
  assert.deepEqual(remapKeyList(['sole', 'pcr', '쏠', 'thevolunteers'], MAP), ['쏠', 'pcr', '더발룬티어스']);
});

test('관심 팀: 키만 바꾸고 이름·상태·추가일은 그대로, 겹치면 앞의 것', () => {
  const items = [{ team_key: 'sole', display_name: 'SOLE', status: 'contacted', added_at: '2026-11-20' },
                 { team_key: '쏠', display_name: '쏠', status: 'watching', added_at: '2026-11-27' },
                 { team_key: 'pcr', display_name: 'PCR', status: 'watching', added_at: '' }];
  const out = remapWatchItems(items, MAP);
  assert.deepEqual(out.map(i => [i.team_key, i.status]), [['쏠', 'contacted'], ['pcr', 'watching']]);
  assert.equal(items[0].team_key, 'sole');   // 원래 것은 그대로
});

test('주소: #/team/옛키/탭 · 비교 주소', () => {
  assert.equal(remapHash('#/team/thevolunteers/score', MAP), `#/team/${encodeURIComponent('더발룬티어스')}/score`);
  assert.equal(remapHash(`#/team/${encodeURIComponent('강형호')}`, MAP), '#/team/pitta');
  assert.equal(remapHash('#/compare?teams=sole,pcr', MAP), `#/compare?teams=${encodeURIComponent('쏠')},pcr`);
  assert.equal(remapHash('#/team/pcr/overview', MAP), '#/team/pcr/overview');   // 그대로면 같은 글자
  assert.equal(remapHash('#/home', MAP), '#/home');
});

test('저장소 옮기기: 관심 팀·비교 담기, 바뀐 수 돌려줌', () => {
  const store = new Map([
    ['crate_digger_watchlist_v1', JSON.stringify([{ team_key: 'sole', display_name: 'SOLE', status: 'watching' }])],
    ['gr_compare_v1', JSON.stringify(['thevolunteers', 'pcr'])],
  ]);
  const storage = { getItem: k => store.get(k) ?? null, setItem: (k, v) => store.set(k, v) };
  const n = applyKeyAliases(MAP, storage);
  assert.deepEqual(n, { watch: 1, compare: 1 });
  assert.equal(JSON.parse(store.get('crate_digger_watchlist_v1'))[0].team_key, '쏠');
  assert.deepEqual(JSON.parse(store.get('gr_compare_v1')), ['더발룬티어스', 'pcr']);
  assert.deepEqual(applyKeyAliases(MAP, storage), { watch: 0, compare: 0 });    // 두 번째는 할 일 없음
  assert.deepEqual(applyKeyAliases(MAP, { getItem: () => { throw new Error('막힘'); }, setItem() {} }), { watch: 0, compare: 0 });
});
