// 화면 바꿀 때 '불러오는 중' 뼈대 판단 + 공연장 크기 표 — docs/app/render_guard.js · docs/app/venue_tiers.js
// 버그(2026-11-28): 느린 망에서 #/venues 가 영영 빈 화면 — 화면이 먼저 그린 틀(#venueListHost)을 90ms 뒤 뼈대가 덮어 써서,
// 나중에 받은 목록이 떨어져 나간 칸에 그려짐.
import test from 'node:test';
import assert from 'node:assert/strict';
import { skeletonAllowed } from '../../docs/app/render_guard.js';
import { parseVenueTierRows, venueTierValuesSql } from '../../docs/app/venue_tiers.js';

const old = { id: 'old-view' };

test('뼈대: 화면이 아직 아무것도 안 그렸으면 그린다', () => {
  assert.equal(skeletonAllowed({ pending: '3', seq: 3, current: 3, startNode: old, firstNode: old }), true);
  assert.equal(skeletonAllowed({ pending: '1', seq: 1, current: 1, startNode: null, firstNode: null }), true, '첫 부팅 빈 칸');
});

test('뼈대: 화면이 이미 자기 틀을 그렸으면 덮지 않는다', () => {
  assert.equal(skeletonAllowed({ pending: '3', seq: 3, current: 3, startNode: old, firstNode: { id: 'host' } }), false);
  assert.equal(skeletonAllowed({ pending: '1', seq: 1, current: 1, startNode: null, firstNode: { id: 'host' } }), false);
});

test('뼈대: 더 새 화면 그리기가 시작됐거나 이미 끝났으면 안 그린다', () => {
  assert.equal(skeletonAllowed({ pending: '4', seq: 3, current: 4, startNode: old, firstNode: old }), false);
  assert.equal(skeletonAllowed({ pending: undefined, seq: 3, current: 3, startNode: old, firstNode: old }), false);
});

test('공연장 크기 표: S·M·L·XL 만, 이름 앞뒤 공백 정리, 소문자도', () => {
  const m = parseVenueTierRows([
    { venue: ' A.O.R ', tier: 's' }, { venue: '롤링홀', tier: 'L' }, { venue: '이상한곳', tier: 'Q' }, { venue: '', tier: 'M' },
  ]);
  assert.deepEqual([...m.entries()], [['A.O.R', 'S'], ['롤링홀', 'L']]);
  assert.equal(parseVenueTierRows(null).size, 0);
});

test('공연장 크기 표 → INSERT 값: 작은따옴표를 이스케이프', () => {
  const sql = venueTierValuesSql(new Map([["Club 'FF'", 'M'], ['롤링홀', 'L']]));
  assert.equal(sql, "('Club ''FF''', 'M'), ('롤링홀', 'L')");
  assert.equal(venueTierValuesSql(new Map()), '');
});
