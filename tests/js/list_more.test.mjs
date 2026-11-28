// 긴 목록은 처음 20줄 + '더 보기' (docs/ux_simplify_2026-11-28.md ⑧) — node --test
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { LIST_FIRST, moreLabel } from '../../docs/app/list_more.js';

test('처음 20줄, 남은 수를 단추에', () => {
  assert.equal(LIST_FIRST, 20);
  assert.equal(moreLabel(50, 20), '30팀 더 보기');
  assert.equal(moreLabel(20, 20), '');
  assert.equal(moreLabel(12, 20), '');
});
