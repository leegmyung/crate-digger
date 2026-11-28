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

// 옛 정답을 오늘 되짚어 넣은 것(past_outcome, scripts/build_alerts.py) — 새 소식처럼 보이지 않게
import { renderHomeAlertsSummaryHtml } from '../../docs/app/views/today_alerts.js';
import { easyAlertTypeLabel } from '../../docs/app/easy_terms.js';

test('과거 수상·선정 기록 추가: 기본 보기·홈 알림 요약에서 빠짐, 이름은 쉬운 말', () => {
  assert.equal(isImportantAlert({ type: 'past_outcome' }), false);
  const data = {
    as_of: '2026-11-28', types: {},
    alerts: [
      { type: 'past_outcome', team_key: 'cott', name: 'cott', date: '2021-05-01', found_on: '2026-11-28', text: 'CJ 튠업 (S등급)', stars: 5, importance: 5, evidence: [] },
      { type: 'stage_up', team_key: 'a', name: '에이', date: '2026-11-27', found_on: '2026-11-28', text: '첫 신호 → 여러 곳에서 보임', stars: 3, importance: 50, evidence: [] },
    ],
  };
  const html = renderHomeAlertsSummaryHtml(data, {});
  assert.doesNotMatch(html, /cott/);
  assert.match(html, /에이/);
  assert.equal(easyAlertTypeLabel('past_outcome', {}), '과거 수상·선정 기록 추가');
});
