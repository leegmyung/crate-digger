// 팀 머리 단순화 (docs/ux_simplify_2026-11-28.md ②) — 한 줄 이유를 맨 위로, 반복 숫자(단계·순위·점수)는 한 곳만 (node --test)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { renderTeamFactsHtml, teamWhyHtml } from '../../docs/app/views/team_head.js';
import { plainWhyLine } from '../../docs/app/ui.js';

const SCORED = { score: 7.58, venues: 7, pts_venues: 2.1, peer_winner: 1, pts_winner: 2, outlets: 1, pts_outlets: 1,
                 context_outlets: 3, pts_context: 1.5, n_branch: 2, pts_branch: 1 };

test('한 줄 이유: 💡 근거 + 후보 순위·점수 (점수·순위는 여기 한 번)', () => {
  const html = teamWhyHtml(SCORED, 1);
  assert.match(html, /💡/);
  assert.match(html, /최근 2년 공연장 7곳/);
  assert.match(html, /후보 1위 · 7\.58점/);
  assert.equal(teamWhyHtml(null, 1), '');
  assert.match(teamWhyHtml(SCORED, null), /7\.58점/);
});

test('사실 줄에서 단계 꼬리표·순위는 빼고(아래 상태 칸·숫자 칸에 있음) 지역·첫 발매·장르만', () => {
  const html = renderTeamFactsHtml({ teamKey: 'a', stageInfo: { stage: 2 }, rc: { rank: 1, week_change: 3 },
    homeCity: '서울', hasCityData: true, firstRelease: '2025-10-07', genre: '록·밴드' });
  assert.doesNotMatch(html, /순위|stage-badge|여러 곳/);
  assert.match(html, /서울/);
  assert.match(html, /2025/);
  assert.match(html, /록·밴드/);
});

test('이유 문장은 쉬운 말 (맥락 매체·갈래 대신)', () => {
  const s = plainWhyLine({ ...SCORED, venues: 0, pts_venues: 0, peer_winner: 0, outlets: 0 });
  assert.doesNotMatch(s, /맥락 매체|갈래/);
  assert.match(s, /큰 매거진 3곳/);
});
