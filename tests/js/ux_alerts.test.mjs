// 알림 기본 보기 = 중요한 것만 (docs/ux_simplify_2026-11-28.md ⑤) — node --test
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { isImportantAlert } from '../../docs/app/views/today_alerts.js';

test('새 공연(300건)·이미 뜬 팀의 새 정답은 기본 보기에서 빼고, 발굴 신호만', () => {
  for (const type of ['stage_up', 'new_selection', 'blank_first_mention', 'big_venue_first', 'peer_winner', 'rank_jump', 'spike']) {
    assert.equal(isImportantAlert({ type }), true, type);
  }
  assert.equal(isImportantAlert({ type: 'new_gig' }), false);
  assert.equal(isImportantAlert({ type: 'new_outcome' }), false);
  assert.equal(isImportantAlert({}), false);
});
