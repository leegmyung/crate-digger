// e2e 화면 점검 경로 목록 검사 — tests/e2e/routes.mjs (route_check.mjs 가 읽는다)
import test from 'node:test';
import assert from 'node:assert/strict';
import { ROUTES, WIDTHS, THEMES, routeLabel, routeHash, cellCount } from '../e2e/routes.mjs';

test('씬 네트워크·공연장 흐름 탭·도시 확대 지도가 점검 경로에 있다', () => {
  const hashes = ROUTES.map(routeHash);
  assert.ok(hashes.includes('venues/network'), '씬 네트워크');
  assert.ok(hashes.some(h => /^venue\/.+\/flow$/.test(h)), '공연장 흐름 탭');
  const zoom = ROUTES.find(r => typeof r === 'object' && routeHash(r) === 'cities' && r.act);
  assert.ok(zoom, '도시 확대 지도는 시·도를 눌러 확대하는 동작을 같이 가진다');
  assert.match(zoom.act, /data-sido-row|data-sido/);
  assert.match(routeLabel(zoom), /확대/);
});

test('예전 경로 17개는 그대로 남는다', () => {
  const hashes = ROUTES.map(routeHash);
  for (const h of ['home', 'discover', 'charts', 'venues', 'cities', 'festivals', 'alerts', 'mine', 'verify/backtest', 'verify/sql']) {
    assert.ok(hashes.includes(h), h);
  }
  assert.ok(hashes.some(h => h.startsWith('team/')));
  assert.ok(hashes.some(h => h.startsWith('compare?')));
});

test('칸 수 = 경로 × 폭 3 × 테마 2 = 120', () => {
  assert.deepEqual(WIDTHS, [1280, 1920, 375]);
  assert.deepEqual(THEMES, ['light', 'dark']);
  assert.equal(ROUTES.length, 20);
  assert.equal(cellCount(), 120);
});

test('이름표: 문자열 경로는 한글 그대로, 동작 경로는 붙인 이름', () => {
  assert.equal(routeLabel(`team/${encodeURIComponent('포져군단')}`), 'team/포져군단');
  assert.equal(routeLabel({ route: 'cities', label: 'cities(확대)', act: 'x' }), 'cities(확대)');
});
