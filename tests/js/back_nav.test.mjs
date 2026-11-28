// 상세 화면 '← 온 곳으로' 단추 (docs/ux_simplify_2026-11-28.md ⑨) — node --test
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { backTarget } from '../../docs/app/back_nav.js';

const LABEL = { today: '홈', candidates: '발굴', charts: '차트', venues: '공연장', venue: '공연장 페이지', team: '팀 페이지', alerts: '알림' };
const label = r => LABEL[r] || null;

test('앱 안에서 온 화면이면 그 이름 + 브라우저 뒤로 가기(필터·주소 그대로)', () => {
  assert.deepEqual(backTarget({ prevRoute: 'candidates', selfRoute: 'team', fallbackRoute: 'candidates', label }),
    { route: 'candidates', param: '', label: '발굴', useHistory: true });
  assert.deepEqual(backTarget({ prevRoute: 'venue', prevParam: 'Club FF', selfRoute: 'team', fallbackRoute: 'candidates', label }),
    { route: 'venue', param: 'Club FF', label: '공연장 페이지', useHistory: true });
});

test('주소로 바로 열었거나 같은 종류 화면에서 왔으면 기본 화면으로 이동', () => {
  assert.deepEqual(backTarget({ prevRoute: null, selfRoute: 'team', fallbackRoute: 'candidates', label }),
    { route: 'candidates', param: '', label: '발굴', useHistory: false });
  assert.deepEqual(backTarget({ prevRoute: 'team', prevParam: 'x', selfRoute: 'team', fallbackRoute: 'candidates', label }),
    { route: 'candidates', param: '', label: '발굴', useHistory: false });
  assert.deepEqual(backTarget({ prevRoute: 'unknown', selfRoute: 'venue', fallbackRoute: 'venues', label }),
    { route: 'venues', param: '', label: '공연장', useHistory: false });
});
