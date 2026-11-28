// 관계망 옆 패널·말풍선·필터 칩 HTML 검사 — docs/app/views/graph_panel.js
import test from 'node:test';
import assert from 'node:assert/strict';
import {
  describeLink, filterChipsHtml, neighborsOf, panelHtml, tooltipHtml,
} from '../../docs/app/views/graph_panel.js';

const ego = { id: 'team:ego', node_type: 'ego', node_key: 'ego', label: '포져군단', importance: 1 };
const venue = { id: 'venue:ff', node_type: 'venue', node_key: 'Club FF', label: 'Club FF', detail: '13회 공연', last_date: '2026-11-14', importance: 0.5 };
const team = { id: 'team:t', node_type: 'team', node_key: 't', label: '산하', importance: 0.3, last_date: '2026-10-31' };

test('선 설명: 같은 무대·공연 횟수, 소속사는 이름만', () => {
  assert.equal(describeLink({ relation: 'co_stage', weight: 6 }), '같은 무대 6번');
  assert.equal(describeLink({ relation: 'venue', weight: 13 }), '공연 13번');
  assert.equal(describeLink({ relation: 'same_agency', weight: 1 }), '소속사');
  assert.equal(describeLink({ relation: 'co_stage', relations: ['co_stage', 'same_agency'], weight: 2 }), '같은 무대 2번 · 소속사');
});

test('이웃 목록: 같은 무대가 공연장보다 먼저, 같은 종류는 횟수 큰 순', () => {
  const t2 = { ...team, id: 'team:t2', label: '나' };
  const links = [
    { source: 'team:ego', target: 'venue:ff', relation: 'venue', weight: 13 },
    { source: { id: 'team:ego' }, target: { id: 'team:t' }, relation: 'co_stage', weight: 2 },
    { source: 'team:t2', target: 'team:ego', relation: 'co_stage', weight: 5 },
  ];
  const byId = new Map([ego, venue, team, t2].map(n => [n.id, n]));
  assert.deepEqual(neighborsOf('team:ego', links, byId).map(x => x.node.id), ['team:t2', 'team:t', 'venue:ff']);
});

test('필터 칩: 있는 종류만, 숨긴 종류는 is-off · aria-pressed=false', () => {
  const html = filterChipsHtml(new Map([['co_stage', 3], ['venue', 2]]), new Set(['venue']));
  assert.match(html, /data-rg-kind="co_stage"[^>]*aria-pressed="true"/);
  assert.match(html, /rg-chip k-venue is-off" data-rg-kind="venue" aria-pressed="false"/);
  assert.doesNotMatch(html, /data-rg-kind="outlet"/);
});

test('패널: 공연장은 "○○이 여기서 13번 공연" + 공연장 페이지 링크 + 펼치기', () => {
  const html = panelHtml({
    node: venue, egoNode: ego, linkToEgo: { relation: 'venue', weight: 13 }, neighbors: [], isSelected: true, expandState: '',
  });
  assert.match(html, /<b>포져군단<\/b>이 여기서 13번 공연/);
  assert.match(html, /href="#\/venue\/Club%20FF"/);
  assert.match(html, /data-rg-expand="venue:ff"/);
  assert.match(html, /data-rg-close/);
  assert.doesNotMatch(html, /읽는 법/, '고른 뒤에는 읽는 법을 숨김');
});

test('패널: 아무것도 안 고르면 중심 팀 요약 + 읽는 법, 닫기·펼치기 단추 없음', () => {
  const html = panelHtml({ node: ego, egoNode: ego, linkToEgo: null, neighbors: [], isSelected: false, expandState: '' });
  assert.match(html, /읽는 법/);
  assert.doesNotMatch(html, /data-rg-close/);
  assert.doesNotMatch(html, /data-rg-expand/);
  assert.doesNotMatch(html, /팀 페이지/);
});

test('패널: 팀은 "○○과 같은 무대 N번" + 팀 페이지 링크, 펼치는 중이면 단추 잠김', () => {
  const html = panelHtml({
    node: team, egoNode: { ...ego, label: '산이' }, linkToEgo: { relation: 'co_stage', weight: 3, detail: 'A · B' },
    neighbors: [], isSelected: true, expandState: 'loading',
  });
  assert.match(html, /<b>산이<\/b>와 같은 무대 3번/);
  assert.match(html, /href="#\/team\/t"/);
  assert.match(html, /불러오는 중…<\/button>/);
  assert.match(html, /data-rg-expand="team:t" disabled/);
});

test('이름의 HTML 은 글자로 나온다 (말풍선·패널)', () => {
  const evil = { ...team, label: '<img src=x onerror=1>' };
  assert.doesNotMatch(tooltipHtml(evil, null), /<img/);
  assert.doesNotMatch(panelHtml({ node: evil, egoNode: ego, linkToEgo: null, neighbors: [], isSelected: true, expandState: '' }), /<img src=x/);
});
