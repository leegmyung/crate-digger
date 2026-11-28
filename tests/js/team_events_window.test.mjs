// 팀 사건 전후 28일 작은 표 — 칸 안 막대 (docs/app/views/team_events.js windowTableHtml)
// 전 = 비교 회색, 후 = 늘었을 때만 주인공 색(is-up), 막대 길이 = 그 줄 큰 값 기준(0부터)
import test from 'node:test';
import assert from 'node:assert/strict';
import { windowTableHtml } from '../../docs/app/views/team_events.js';

const base = { kind: 'selection', after_days: 28 };

test('늘어난 줄은 후 막대가 is-up, 줄어든·같은 줄은 아님', () => {
  const html = windowTableHtml({ ...base, gigs_before: 2, gigs_after: 4, mentions_before: 1, mentions_after: 0 });
  const rows = html.split('<tr>').filter(r => r.includes('scope="row"'));
  assert.match(rows[0], /ew-bar is-after is-up/);
  assert.doesNotMatch(rows[1], /is-up/);
});

test('막대 길이: 그 줄의 큰 값이 100%, 0 이면 0%', () => {
  const html = windowTableHtml({ ...base, gigs_before: 2, gigs_after: 4, mentions_before: 0, mentions_after: 0 });
  assert.match(html, /is-before"[^>]*--w:50%/);
  assert.match(html, /is-after is-up"[^>]*--w:100%/);
  assert.match(html, /--w:0%/);
});

test('값이 없으면 — 이고 막대도 없음, 대상 아닌 사건은 표 없음', () => {
  const html = windowTableHtml({ ...base, gigs_before: 3, gigs_after: 3, mentions_before: null, mentions_after: null });
  const mention = html.split('<tr>').find(r => r.includes('언급'));
  assert.match(mention, /—/);
  assert.doesNotMatch(mention, /ew-bar/);
  assert.equal(windowTableHtml({ kind: 'release', gigs_before: 1, gigs_after: 2 }), '');
});
