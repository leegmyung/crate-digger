// 내 목록 분석 — 관심 팀 묶음의 단계 분포 · 최근 움직임 · 다가오는 공연 요약 (node --test)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { watchSummary, watchSummaryLine } from '../../docs/app/watch_summary.js';

const teams = [
  { team_key: 'a', display_name: '에이', recent_7d: 2, rank_delta: 3, primary_genre: '록·밴드' },
  { team_key: 'b', display_name: '비', recent_7d: 0, rank_delta: -2, primary_genre: '록·밴드' },
  { team_key: 'c', display_name: '씨', recent_7d: 1, rank_delta: 0, is_new_in_snap: true, primary_genre: '힙합' },
  { team_key: 'd', display_name: '디', recent_7d: 0, rank_delta: null, primary_genre: '' },
];
const stageByTeam = new Map([['a', 2], ['b', 2], ['c', 0]]);
const labels = { 0: '백지', 1: '첫 신호', 2: '여러 갈래', 3: '선정', 4: '졸업' };
const upcoming = [
  { signal_date: '2026-12-05', team_key: 'a', display_name: '에이', venue: '클럽1' },
  { signal_date: '2026-12-01', team_key: 'b', display_name: '비', venue: '클럽2' },
  { signal_date: '2026-12-01', team_key: 'b', display_name: '비', venue: '클럽2' },   // 같은 공연 두 줄 → 한 번
  { signal_date: '2026-12-09', team_key: 'zz', display_name: '남', venue: '클럽3' },  // 관심 팀 아님
  { signal_date: '2026-12-10', team_key: 'a', display_name: '에이', venue: '클럽4' },
];

test('단계 분포: 순서대로, 없는 단계는 빼고, 계산 안 된 팀은 따로', () => {
  const s = watchSummary({ teams, stageByTeam, stageLabels: labels, upcoming });
  assert.deepEqual(s.stages, [{ stage: 0, label: '백지', n: 1 }, { stage: 2, label: '여러 갈래', n: 2 }]);
  assert.equal(s.noStage, 1);
  assert.equal(s.total, 4);
});

test('최근 움직임: 7일 신호 있는 팀·순위 오른/내린 팀·새로 300위 안', () => {
  const s = watchSummary({ teams, stageByTeam, stageLabels: labels, upcoming });
  assert.equal(s.active7d, 2);
  assert.equal(s.rankUp, 1);
  assert.equal(s.rankDown, 1);
  assert.equal(s.newInSnap, 1);
  assert.deepEqual(s.topGenres, [{ genre: '록·밴드', n: 2 }, { genre: '힙합', n: 1 }]);
});

test('다가오는 공연: 관심 팀만, 같은 공연은 한 번, 날짜순 앞 3개', () => {
  const s = watchSummary({ teams, stageByTeam, stageLabels: labels, upcoming });
  assert.equal(s.upcomingTotal, 3);
  assert.equal(s.upcomingTeams, 2);
  assert.deepEqual(s.nextGigs.map(g => [g.date, g.team_key, g.venue]),
    [['2026-12-01', 'b', '클럽2'], ['2026-12-05', 'a', '클럽1'], ['2026-12-10', 'a', '클럽4']]);
});

test('한 줄 요약', () => {
  const s = watchSummary({ teams, stageByTeam, stageLabels: labels, upcoming });
  assert.equal(watchSummaryLine(s, 30),
    '관심 4팀 — 최근 7일 움직인 팀 2 · 순위 오른 팀 1 · 내린 팀 1 · 새로 300위 안 1 · 앞으로 30일 공연 2팀 3회');
  assert.equal(watchSummaryLine(watchSummary({ teams: [], stageByTeam, upcoming: [] }), 30), '');
});
