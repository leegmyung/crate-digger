// 월별 막대 그림 규칙 (docs/layout_rules.md 7절, docs/app/viz_bars.js) — 값 축 0부터 · 최근 달만 주인공 색 · 단위 붙은 말풍선 (node --test)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { barPct, monthBarsHtml, niceMax } from '../../docs/app/viz_bars.js';

const MONTHS = ['2026-08', '2026-09', '2026-10', '2026-11'];
const heights = html => [...html.matchAll(/style="height:([\d.]+)%"/g)].map(m => Number(m[1]));

test('눈금 꼭대기: 1·2·5 × 10의 거듭제곱으로 올림', () => {
  assert.equal(niceMax(0), 1);
  assert.equal(niceMax(7), 10);
  assert.equal(niceMax(18), 20);
  assert.equal(niceMax(23), 50);
  assert.equal(niceMax(120), 200);
});

test('막대 길이 = 값 (0은 0, 작은 값도 비례 — 최소 높이로 부풀리지 않음)', () => {
  assert.equal(barPct(0, 10), 0);
  assert.equal(barPct(10, 10), 100);
  assert.equal(barPct(1, 20), 5);
  assert.equal(barPct(-3, 10), 0);
  assert.equal(barPct(5, 0), 0);
});

test('작은 그림(스파크라인): 최근 달만 is-latest, 0인 달은 is-zero, 말풍선에 단위', () => {
  const html = monthBarsHtml({ months: MONTHS, vals: [4, 0, 8, 2], wrapCls: 'vl-months', barCls: 'vl-month', scaleMin: 8 });
  assert.deepEqual(heights(html), [50, 0, 100, 25]);
  assert.equal((html.match(/is-latest/g) || []).length, 1);
  assert.match(html, /vl-month viz-mbar is-latest" style="height:25%" title="2026-11 · 2일"/);
  assert.match(html, /vl-month viz-mbar is-zero"/);
  assert.match(html, /role="img" aria-label="최근 4개월 월별 공연 날짜 4, 0, 8, 2일"/);
  assert.doesNotMatch(html, /viz-maxis/);    // 작은 그림엔 눈금 없음
});

test('큰 그림: 0과 꼭대기 눈금(단위 붙음)·달 이름표(처음·끝·1월)', () => {
  const months = ['2025-11', '2025-12', '2026-01', '2026-02', '2026-03'];
  const html = monthBarsHtml({ months, vals: [3, 18, 5, 0, 9], wrapCls: 'place-months', barCls: 'place-month', axis: true });
  assert.match(html, /viz-maxis/);
  assert.match(html, />20일</);          // 18 → 눈금 20
  assert.match(html, />0</);
  assert.deepEqual(heights(html), [15, 90, 25, 0, 45]);
  const labels = [...html.matchAll(/class="viz-mx">([^<]+)</g)].map(m => m[1]);
  assert.deepEqual(labels, ['25.11', '26.1', '26.3']);
});

test('값이 모두 0이어도 그림이 깨지지 않음', () => {
  const html = monthBarsHtml({ months: MONTHS, vals: [0, 0, 0, 0], axis: true });
  assert.deepEqual(heights(html), [0, 0, 0, 0]);
  assert.match(html, />1일</);
});

test('달 이름표가 붙어 겹치지 않게: 처음·끝 가까이의 1월은 뺌 (24개월이면 3칸 이상 떨어져야)', () => {
  const months = Array.from({ length: 24 }, (_, i) => new Date(Date.UTC(2024, 11 + i, 1)).toISOString().slice(0, 7)); // 2024-12 ~ 2026-11
  const html = monthBarsHtml({ months, vals: months.map(() => 1), axis: true });
  const labels = [...html.matchAll(/class="viz-mx">([^<]+)</g)].map(m => m[1]);
  assert.deepEqual(labels, ['24.12', '26.1', '26.11']);   // 25.1 은 24.12 바로 옆이라 뺌
});

test('큰 그림 구조: 눈금 칸이 막대 칸과 같은 줄(높이가 같이 늘고 줄어듦), 이름표는 그 아래 줄', () => {
  const html = monthBarsHtml({ months: MONTHS, vals: [1, 2, 3, 4], axis: true });
  const order = ['viz-maxis', 'viz-mbars', 'viz-mgap', 'viz-mxs'].map(c => html.indexOf(c));
  assert.ok(order.every(i => i > 0), JSON.stringify(order));
  assert.deepEqual(order, [...order].sort((a, b) => a - b));
});
