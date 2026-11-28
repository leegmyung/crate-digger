// 홈 '이번 주 볼 신인 5팀' (docs/ux_simplify_2026-11-28.md ①) — node --test
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { pickWeeklyTeams, weeklyPicksHtml } from '../../docs/app/home_picks.js';

const ROWS = [
  { team_key: 'a', display_name: 'A', score: 9, last_seen: '2026-10-01' },   // 점수 1위지만 최근 신호 없음
  { team_key: 'b', display_name: 'B', score: 8, last_seen: '2026-11-25' },
  { team_key: 'c', display_name: 'C', score: 7, last_seen: '2026-09-01' },   // 알림이 있음
  { team_key: 'd', display_name: 'D', score: 6, last_seen: '2026-11-20' },
  { team_key: 'e', display_name: 'E', score: 5, last_seen: '2026-11-27' },
];
const ALERTS = [{ type: 'stage_up', team_key: 'c' }, { type: 'new_gig', team_key: 'a' }];

test('점수 순으로 최근 14일 신호 또는 중요한 알림이 있는 팀 (새 공연 알림은 안 셈)', () => {
  const out = pickWeeklyTeams(ROWS, ALERTS, '2026-11-28', 3);
  assert.deepEqual(out.map(r => r.team_key), ['b', 'c', 'd']);
});

test('모자라면 점수 순으로 채움, 중복 없음', () => {
  const out = pickWeeklyTeams(ROWS, [], '2026-11-28', 5);
  assert.deepEqual(out.map(r => r.team_key), ['b', 'd', 'e', 'a', 'c']);
  assert.deepEqual(pickWeeklyTeams([], [], '2026-11-28', 5), []);
});

test('블록: 사진·▶·한 줄 이유·발굴로 가는 링크, 팀이 없으면 빈 글자', () => {
  const html = weeklyPicksHtml([{ team_key: 'b', display_name: 'B', score: 8, venues: 3, pts_venues: 1 }]);
  assert.match(html, /이번 주 볼 신인/);
  assert.match(html, /class="avatar[ "]/);
  assert.match(html, /data-play-(team|slot)="b"/);
  assert.match(html, /최근 2년 공연장 3곳/);
  assert.match(html, /href="#\/discover"/);
  assert.equal(weeklyPicksHtml([]), '');
});
