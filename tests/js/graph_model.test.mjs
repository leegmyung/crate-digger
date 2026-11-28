// 관계망 그림의 순수 계산(크기·굵기·라벨 고르기·필터·소속사 묶기) 검사 — docs/app/views/graph_model.js
import test from 'node:test';
import assert from 'node:assert/strict';
import {
  REL_KINDS, relationKindOf, importanceOf, nodeRadiusFor, edgeWidthFor, labelBudget,
  estimateLabelWidth, pickVisibleLabels, filterGraph, buildAdjacency, rowToGraphParts,
  shortLabel, labelFontSize, kindOrder, labelPriority,
} from '../../docs/app/views/graph_model.js';

test('관계 종류: same_agency 는 소속사(agency) 갈래로 묶인다', () => {
  assert.equal(relationKindOf('same_agency'), 'agency');
  assert.equal(relationKindOf('co_stage'), 'co_stage');
  assert.equal(relationKindOf('모르는것'), 'other');
  assert.deepEqual(REL_KINDS.map(k => k.key), ['co_stage', 'agency', 'venue', 'outcome', 'program', 'outlet', 'scene']);
});

test('중요도: 순위가 높은 팀일수록 크고, 정답 등급 S > A > B', () => {
  const top = importanceOf({ node_type: 'team' }, { rank: 1, score: 11 });
  const mid = importanceOf({ node_type: 'team' }, { rank: 300, score: 2 });
  const none = importanceOf({ node_type: 'team' }, null);
  assert.ok(top > mid && mid > none, `${top} > ${mid} > ${none}`);
  assert.ok(top <= 1 && none >= 0);
  const s = importanceOf({ node_type: 'outcome', grade: 'S' });
  const a = importanceOf({ node_type: 'outcome', grade: 'A' });
  const b = importanceOf({ node_type: 'outcome', grade: 'b' });
  assert.ok(s > a && a > b);
  assert.equal(importanceOf({ node_type: 'ego' }), 1);
});

test('노드 크기: 중심 팀이 가장 크고, 중요한 팀이 덜 중요한 팀보다 크다', () => {
  const ego = nodeRadiusFor({ node_type: 'ego', importance: 1 });
  const big = nodeRadiusFor({ node_type: 'team', importance: 0.9 });
  const small = nodeRadiusFor({ node_type: 'team', importance: 0.05 });
  const venue = nodeRadiusFor({ node_type: 'venue', importance: 0.2 });
  assert.ok(ego > big && big > small, `${ego} > ${big} > ${small}`);
  assert.ok(small >= 8, '가장 작은 팀도 누를 수 있는 크기');
  assert.ok(venue < big);
});

test('선 굵기: 같은 무대 횟수가 많을수록 굵고 상한이 있다', () => {
  const one = edgeWidthFor({ relation: 'co_stage', weight: 1 });
  const six = edgeWidthFor({ relation: 'co_stage', weight: 6 });
  const huge = edgeWidthFor({ relation: 'co_stage', weight: 400 });
  assert.ok(six > one);
  assert.ok(huge <= 7);
  assert.ok(edgeWidthFor({ relation: 'same_agency', weight: 9 }) <= 1.6, '소속사 선은 횟수와 무관');
});

test('라벨 수: 멀리서 보면 적게, 가까이 보면 다 보인다', () => {
  assert.ok(labelBudget(0.5, 200) < labelBudget(1, 200));
  assert.ok(labelBudget(1, 200) < labelBudget(1.8, 200));
  assert.equal(labelBudget(3, 200), 200);
  assert.equal(labelBudget(0.5, 3), 3, '노드보다 많이 고르지 않음');
});

test('라벨 글자 크기: 확대해도 화면에서 너무 커지지 않는다', () => {
  const at1 = labelFontSize(11, 1);
  const at3 = labelFontSize(11, 3);
  assert.equal(at1, 11);
  assert.ok(at3 * 3 < 11 * 3, '확대 배율만큼 커지지 않음');
  assert.ok(at3 * 3 > 11, '그래도 조금은 커짐');
});

test('라벨 폭 추정: 한글은 영문보다 넓다', () => {
  assert.ok(estimateLabelWidth('가나다', 12) > estimateLabelWidth('abc', 12));
  assert.equal(estimateLabelWidth('', 12), 0);
});

test('라벨 고르기: 겹치면 중요도 낮은 쪽을 숨기고, 고정 라벨은 늘 보인다', () => {
  const items = [
    { id: 'a', x: 100, y: 100, w: 60, h: 14, priority: 10 },
    { id: 'b', x: 110, y: 104, w: 60, h: 14, priority: 5 },   // a 와 겹침
    { id: 'c', x: 300, y: 100, w: 60, h: 14, priority: 1 },
    { id: 'p', x: 112, y: 100, w: 60, h: 14, priority: 0 },   // 고정
  ];
  const on = pickVisibleLabels(items, { budget: 10, pinned: new Set(['p']) });
  assert.ok(on.has('p'));
  assert.ok(on.has('c'));
  assert.ok(!on.has('b'));
  assert.ok(!on.has('a'), '고정 라벨과 겹치면 숨김');
  const limited = pickVisibleLabels(items, { budget: 1, pinned: new Set() });
  assert.deepEqual([...limited], ['a']);
});

test('필터: 숨긴 종류의 선과, 중심에서 끊긴 노드는 빠진다', () => {
  const nodes = [{ id: 'ego' }, { id: 't1' }, { id: 'v1' }, { id: 't2' }];
  const links = [
    { id: 'l1', source: 'ego', target: 't1', relation: 'co_stage' },
    { id: 'l2', source: 'ego', target: 'v1', relation: 'venue' },
    { id: 'l3', source: 'v1', target: 't2', relation: 'venue' },
  ];
  const all = filterGraph(nodes, links, new Set(), 'ego');
  assert.equal(all.nodes.length, 4);
  const noVenue = filterGraph(nodes, links, new Set(['venue']), 'ego');
  assert.deepEqual(noVenue.nodes.map(n => n.id).sort(), ['ego', 't1']);
  assert.deepEqual(noVenue.links.map(l => l.id), ['l1']);
  // d3 가 source/target 을 객체로 바꾼 뒤에도 같게 동작
  const objLinks = links.map(l => ({ ...l, source: { id: l.source }, target: { id: l.target } }));
  assert.equal(filterGraph(nodes, objLinks, new Set(['co_stage']), 'ego').nodes.length, 3);
});

test('이웃 표: 양쪽 방향으로 이어진다', () => {
  const adj = buildAdjacency([{ source: 'a', target: 'b' }, { source: { id: 'b' }, target: { id: 'c' } }]);
  assert.deepEqual([...adj.get('b')].sort(), ['a', 'c']);
  assert.deepEqual([...adj.get('a')], ['b']);
});

test('행 → 그림 조각: 같은 소속사 팀은 소속사 노드를 거쳐 이어진다', () => {
  const parent = { id: 'team:ego' };
  const parts = rowToGraphParts(parent, {
    node_id: 'team:x', node_type: 'team', node_key: 'x', label: 'X', relation: 'same_agency', weight: 1, detail: '붕가붕가레코드',
  });
  assert.deepEqual(parts.nodes.map(n => n.id), ['agency:붕가붕가레코드', 'team:x']);
  assert.equal(parts.nodes[0].node_type, 'agency');
  assert.deepEqual(parts.links.map(l => [l.source, l.target, l.relation]), [
    ['team:ego', 'agency:붕가붕가레코드', 'same_agency'],
    ['agency:붕가붕가레코드', 'team:x', 'same_agency'],
  ]);
});

test('행 → 그림 조각: 보통 관계는 노드 1개·선 1개, 소속사 이름이 없으면 바로 잇는다', () => {
  const parent = { id: 'team:ego' };
  const co = rowToGraphParts(parent, { node_id: 'team:y', node_type: 'team', relation: 'co_stage', weight: 4 });
  assert.equal(co.nodes.length, 1);
  assert.deepEqual(co.links.map(l => [l.source, l.target, l.weight]), [['team:ego', 'team:y', 4]]);
  const noAgency = rowToGraphParts(parent, { node_id: 'team:z', node_type: 'team', relation: 'same_agency', detail: '' });
  assert.deepEqual(noAgency.links.map(l => l.target), ['team:z']);
  assert.deepEqual(rowToGraphParts(parent, { node_id: 'team:ego' }), { nodes: [], links: [] }, '자기 자신은 무시');
  assert.deepEqual(rowToGraphParts(parent, null), { nodes: [], links: [] });
});

test('짧은 이름: 길면 말줄임', () => {
  assert.equal(shortLabel('가나다라마바사아자차', 5), '가나다라…');
  assert.equal(shortLabel(' 짧음 ', 5), '짧음');
});

test('관계 종류 순서·라벨 우선순위: 같은 무대가 먼저, 팀 라벨이 공연장보다 먼저', () => {
  assert.ok(kindOrder('co_stage') < kindOrder('venue'));
  assert.ok(kindOrder('same_agency') < kindOrder('scene'));
  assert.ok(kindOrder('???') > kindOrder('scene'));
  const team = labelPriority({ node_type: 'team', importance: 0.05, depth: 1 }, 1);
  const venue = labelPriority({ node_type: 'venue', importance: 0.4, depth: 1 }, 1);
  assert.ok(team > venue);
});
