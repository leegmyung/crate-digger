// 화면 점검(docs/ui_review_2026-11-28.md)에서 바로 고친 것 — 사진·▶ 빠진 목록, 영어 꼬리표, 말풍선 없는 숫자 (node --test)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { venueTeamRowHtml } from '../../docs/app/views/venue_tables.js';
import { homeChartRowHtml } from '../../docs/app/home_chart_rows.js';
import { formatRankDeltaHtml } from '../../docs/app/components/cand_filters.js';
import { INFO_TIPS } from '../../docs/app/components/infotip.js';

const hasAvatar = html => /class="avatar[ "]/.test(html);
const hasPlay = html => /data-play-(team|slot)="/.test(html);

test('공연장 출연 팀 줄: 사진 + ▶(또는 영상 표를 받으면 채울 자리)', () => {
  const html = venueTeamRowHtml({ team_key: 'a', display_name: '팀A', primary_genre: '록·밴드', gigs: 3, first_here: '2024-01-01', last_here: '2024-02-01' });
  assert.ok(hasAvatar(html), html);
  assert.ok(hasPlay(html), html);
  assert.match(html, /href="#\/team\/a"/);
});

test('홈 차트 맛보기 줄: 사진 + ▶ + 관심 추가', () => {
  const html = homeChartRowHtml(0, { team_key: 'b', name: '팀B', genre: '포크·싱어송라이터', metric: '언급 2곳' });
  assert.ok(hasAvatar(html), html);
  assert.ok(hasPlay(html), html);
  assert.match(html, /data-watch-key="b"/);
  assert.match(html, /home-chart-rank mono">1</);
});

test('새로 진입은 영어 NEW 대신 "새로"', () => {
  const html = formatRankDeltaHtml({ rank: 12, week_label: 'NEW', week_date: '2026-11-21' }, 12);
  assert.match(html, />새로</);
  assert.doesNotMatch(html, />NEW</);
});

test('공연장 머리 숫자 말풍선: 정답 전에 선 팀 · 최근 12개월 공연', () => {
  assert.match(INFO_TIPS.venue_pre_outcome.what, /정답/);
  assert.match(INFO_TIPS.venue_nights_12m.what, /공연/);
});
