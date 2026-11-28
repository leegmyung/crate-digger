// 씬 네트워크 순수 계산·HTML 검사 — docs/app/views/graph_scene_model.js · graph_scene_panel.js
import test from 'node:test';
import assert from 'node:assert/strict';
import {
  sceneRadius, roleOf, isHiddenNode, roleCounts, sceneFocusSet, matchTeams, sceneLabelPriority,
} from '../../docs/app/views/graph_scene_model.js';
import {
  sceneChipsHtml, scenePanelHtml, sceneTooltipHtml, searchMenuHtml,
} from '../../docs/app/views/graph_scene_panel.js';

const winner = { id: 'w', team_key: 'w', display_name: '산하', score: 9, had_outcome: true, outcome_grade: 'A', degree: 4, communityId: 1, colorSlot: 0 };
const cand = { id: 'c', team_key: 'c', display_name: '나이테', score: 3, had_outcome: false, cand_rank: 12, degree: 2, communityId: 1, colorSlot: 0 };
const other = { id: 'o', team_key: 'o', display_name: 'Ozz', score: 1, had_outcome: false, degree: 0, communityId: null, colorSlot: -1 };

test('크기: 점수가 높을수록 크고, 범위 안에 든다', () => {
  assert.ok(sceneRadius(9, 1, 9) > sceneRadius(3, 1, 9));
  assert.ok(sceneRadius(1, 1, 9) >= 5);
  assert.ok(sceneRadius(9, 1, 9) <= 17);
  assert.ok(Number.isFinite(sceneRadius(5, 5, 5)), '모두 같은 점수여도 숫자');
});

test('역할: 수상·선정 팀은 winner, 나머지는 cand · 숨김·개수', () => {
  assert.equal(roleOf(winner), 'winner');
  assert.equal(roleOf(cand), 'cand');
  assert.equal(isHiddenNode(winner, new Set(['winner'])), true);
  assert.equal(isHiddenNode(cand, new Set(['winner'])), false);
  const counts = roleCounts([winner, cand, other]);
  assert.equal(counts.get('winner'), 1);
  assert.equal(counts.get('cand'), 2);
});

test('강조: 올린 팀 > 고른 팀 > 고른 묶음 순, 숨긴 팀은 빠짐', () => {
  const adj = new Map([['w', [{ neighbor: cand }, { neighbor: other }]], ['c', [{ neighbor: winner }]], ['o', [{ neighbor: winner }]]]);
  const nodes = [winner, cand, other];
  const byId = new Map(nodes.map(n => [n.id, n]));
  const hov = sceneFocusSet({ hoveredId: 'w', selectedId: 'c', activeCommId: null, nodes, adjMap: adj, nodeById: byId, hiddenRoles: new Set() });
  assert.equal(hov.focusId, 'w');
  assert.deepEqual([...hov.set].sort(), ['c', 'o', 'w']);
  const hidden = sceneFocusSet({ hoveredId: 'w', selectedId: null, activeCommId: null, nodes, adjMap: adj, nodeById: byId, hiddenRoles: new Set(['cand']) });
  assert.deepEqual([...hidden.set], ['w']);
  const comm = sceneFocusSet({ hoveredId: null, selectedId: null, activeCommId: 1, nodes, adjMap: adj, nodeById: byId, hiddenRoles: new Set() });
  assert.equal(comm.focusId, null);
  assert.deepEqual([...comm.set].sort(), ['c', 'w']);
  assert.equal(sceneFocusSet({ hoveredId: null, selectedId: null, activeCommId: null, nodes, adjMap: adj, nodeById: byId, hiddenRoles: new Set() }), null);
});

test('검색: 앞글자 일치 먼저, 그다음 점수 순, 개수 제한', () => {
  const list = [
    { ...cand, id: 'a', display_name: '가나다', score: 1, team_key: 'a' },
    { ...cand, id: 'b', display_name: '다나가', score: 9, team_key: 'b' },
    { ...cand, id: 'c2', display_name: '나무', score: 5, team_key: 'c2' },
  ];
  assert.deepEqual(matchTeams(list, '나').map(n => n.id), ['c2', 'b', 'a']);
  assert.deepEqual(matchTeams(list, '가', 1).map(n => n.id), ['a']);
  assert.deepEqual(matchTeams(list, '   '), []);
});

test('라벨 우선순위: 수상 팀·점수 높은 팀이 먼저', () => {
  assert.ok(sceneLabelPriority(winner) > sceneLabelPriority(cand));
  assert.ok(sceneLabelPriority(cand) > sceneLabelPriority(other));
});

test('칩: 묶음 칩(고르면 aria-pressed) + 역할 칩(숨기면 is-off)', () => {
  const html = sceneChipsHtml({
    communities: [{ id: 4, count: 21, colorSlot: 0, topVenues: ['Club FF'] }],
    colorOf: () => '#123456',
    activeCommId: 4,
    counts: new Map([['cand', 120], ['winner', 22]]),
    hiddenRoles: new Set(['cand']),
  });
  assert.match(html, /data-sn-comm="4"[^>]*aria-pressed="true"/);
  assert.match(html, /--c:#123456/);
  assert.match(html, /Club FF/);
  assert.match(html, /rg-chip sn-role is-off" data-sn-role="cand" aria-pressed="false"/);
  assert.match(html, /data-sn-role="winner" aria-pressed="true"/);
});

test('패널: 팀을 고르면 점수·묶음·같은 무대 목록·팀 페이지 링크', () => {
  const html = scenePanelHtml({
    mode: 'team',
    node: winner,
    neighbors: [{ neighbor: cand, weight: 3 }],
    colorOf: () => '#abcdef',
    nextGig: null,
  });
  assert.match(html, /산하/);
  assert.match(html, /A등급/);
  assert.match(html, /href="#\/team\/w"/);
  assert.match(html, /data-sn-jump="c"/);
  assert.match(html, /같은 무대 3번/);
  assert.match(html, /data-sn-close/);
});

test('패널: 아무것도 안 고르면 요약 + 큰 묶음 + 점수 높은 팀 + 읽는 법', () => {
  const html = scenePanelHtml({
    mode: 'summary',
    stats: { genre: '', teams: 150, cand: 128, winners: 22, links: 538 },
    communities: [{ id: 4, count: 21, colorSlot: 0, topVenues: ['Club FF'] }],
    topTeams: [winner, cand],
    colorOf: () => '#000',
  });
  assert.match(html, /150팀/);
  assert.match(html, /data-sn-comm-pick="4"/);
  assert.match(html, /data-sn-jump="w"/);
  assert.match(html, /읽는 법/);
  assert.doesNotMatch(html, /data-sn-close/);
});

test('패널: 묶음을 고르면 대표 공연장 링크와 그 묶음 팀', () => {
  const html = scenePanelHtml({
    mode: 'community',
    community: { id: 4, count: 2, colorSlot: 0, topVenues: ['Club FF', '롤링홀'] },
    members: [winner, cand],
    colorOf: () => '#000',
  });
  assert.match(html, /씬 묶음 4/);
  assert.match(html, /href="#\/venue\/Club%20FF"/);
  assert.match(html, /data-sn-jump="c"/);
  assert.match(html, /data-sn-close/);
});

test('말풍선·검색 목록: 이름 HTML 은 글자로', () => {
  const evil = { ...cand, display_name: '<b>x</b>' };
  assert.doesNotMatch(sceneTooltipHtml(evil), /<b>x/);
  assert.doesNotMatch(searchMenuHtml([evil], 10, () => '#000'), /<b>x/);
  assert.match(searchMenuHtml([], 10, () => '#000'), /10팀/);
});
