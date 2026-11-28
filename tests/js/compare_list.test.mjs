// 팀 나란히 비교 — 담기 목록 규칙 (node --test)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  COMPARE_MAX, compareHash, compareKeysFromQuery, parseCompareKeys, toggleCompareKey,
} from '../../docs/app/compare_list.js';

test('주소의 teams 값 읽기: 빈칸·중복 빼고 최대 4팀', () => {
  assert.equal(COMPARE_MAX, 4);
  assert.deepEqual(parseCompareKeys('a,b,,a, c'), ['a', 'b', 'c']);
  assert.deepEqual(parseCompareKeys('a,b,c,d,e'), ['a', 'b', 'c', 'd']);
  assert.deepEqual(parseCompareKeys(''), []);
  assert.deepEqual(parseCompareKeys(null), []);
});

test('담기·빼기는 새 배열을 돌려주고 원래 배열은 그대로', () => {
  const base = ['a', 'b'];
  const added = toggleCompareKey(base, 'c');
  assert.deepEqual(added, { list: ['a', 'b', 'c'], added: true, full: false });
  assert.deepEqual(base, ['a', 'b']);
  assert.deepEqual(toggleCompareKey(base, 'a'), { list: ['b'], added: false, full: false });
});

test('4팀이 차 있으면 더 담지 않고 full', () => {
  assert.deepEqual(toggleCompareKey(['a', 'b', 'c', 'd'], 'e'), { list: ['a', 'b', 'c', 'd'], added: false, full: true });
  assert.deepEqual(toggleCompareKey(['a'], ''), { list: ['a'], added: false, full: false });
});

test('비교 주소: 팀 이름은 한 칸씩 인코딩, 쉼표로 이어 붙임', () => {
  assert.equal(compareHash(['포져군단', 'a,b']), `#/compare?teams=${encodeURIComponent('포져군단')},${encodeURIComponent('a,b')}`);
  assert.equal(compareHash([]), '#/compare');
});

test('주소 쿼리 → 팀 키: 칸마다 풀어서 키 안의 쉼표도 지킴', () => {
  const q = compareHash(['포져군단', 'a,b', '포져군단']).split('?')[1] + '&as_of=2026-11-28';
  assert.deepEqual(compareKeysFromQuery(q), ['포져군단', 'a,b']);
  assert.deepEqual(compareKeysFromQuery('x=1'), []);
  assert.deepEqual(compareKeysFromQuery('teams=%E0%A4%A,ok'), ['ok']);
});
