// 앱 그림 공통 설정 검사 — docs/app/chart_theme.js
// 원칙: 값 축은 0부터 · 격자는 값 축 한 방향만 옅게 · 색은 의미(주인공/비교/기준)만 · 범례는 위 왼쪽 · 말풍선은 표면색
import test from 'node:test';
import assert from 'node:assert/strict';
import {
  VIZ_ROLES, roleColor, chartDefaultsPatch, applyChartDefaults, vizScales, vizBar, vizLegend, baselineLabelSpot,
} from '../../docs/app/chart_theme.js';

const T = {
  focus: 'rgb(180, 80, 31)', compare: 'rgb(146, 145, 145)', compare2: 'rgb(198, 198, 198)', neutral: 'rgb(170, 170, 170)',
  weak: 'rgb(220, 220, 220)', ref: 'rgb(18, 17, 16)', grid: 'rgba(18, 17, 16, 0.08)', axis: 'rgb(102, 97, 89)',
  label: 'rgb(82, 78, 71)', text: 'rgb(18, 17, 16)', surface: 'rgb(255, 255, 255)', tipLine: 'rgb(201, 196, 187)',
  gig: 'rgb(27, 122, 120)', sel: 'rgb(47, 93, 140)',
};

test('색 역할: 주인공·비교·기준이 정해진 색, 모르는 역할은 중립', () => {
  assert.deepEqual(VIZ_ROLES, ['focus', 'compare', 'compare2', 'neutral', 'weak', 'ref', 'gig', 'sel']);
  assert.equal(roleColor('focus', T), T.focus);
  assert.equal(roleColor('compare2', T), T.compare2);
  assert.equal(roleColor('없는역할', T), T.neutral);
});

test('기본값: 말풍선은 표면색·테두리·둥근 모서리, 범례는 위 왼쪽 점 모양, 막대 4px 둥근 끝, 애니메이션 끔', () => {
  const p = chartDefaultsPatch(T);
  assert.equal(p.color, T.label);
  assert.equal(p.plugins.tooltip.backgroundColor, T.surface);
  assert.equal(p.plugins.tooltip.borderColor, T.tipLine);
  assert.equal(p.plugins.tooltip.titleColor, T.text);
  assert.ok(p.plugins.tooltip.cornerRadius >= 6);
  assert.equal(p.plugins.legend.position, 'top');
  assert.equal(p.plugins.legend.align, 'start');
  assert.equal(p.plugins.legend.labels.usePointStyle, true);
  assert.equal(p.elements.bar.borderRadius, 4);
  assert.equal(p.animation, false);
  assert.equal(p.scale.grid.color, T.grid);
  assert.equal(p.scale.border.display, false);
  assert.ok(p.layout.padding.top >= 20, '오른쪽 위 PNG 단추가 막대를 가리지 않게');
});

test('기본값 덮어쓰기: 깊게 합치고 원래 다른 칸은 남긴다', () => {
  const Chart = { defaults: { color: 'x', plugins: { tooltip: { mode: 'index' }, legend: {} }, elements: {}, scale: {}, keep: 1 } };
  applyChartDefaults(Chart, T);
  assert.equal(Chart.defaults.color, T.label);
  assert.equal(Chart.defaults.plugins.tooltip.mode, 'index', '원래 있던 설정 유지');
  assert.equal(Chart.defaults.plugins.tooltip.backgroundColor, T.surface);
  assert.equal(Chart.defaults.keep, 1);
  assert.doesNotThrow(() => applyChartDefaults(null, T));
});

test('축: 값 축은 0부터·눈금 5개 이하·격자 있음, 범주 축은 격자 없음 (세로·가로 막대 모두)', () => {
  const v = vizScales(T, { valueFmt: x => `${x}%` });
  assert.equal(v.y.beginAtZero, true);
  assert.ok(v.y.ticks.maxTicksLimit <= 6);
  assert.equal(v.y.ticks.callback(20), '20%');
  assert.notEqual(v.y.grid.display, false);
  assert.equal(v.x.grid.display, false);
  const h = vizScales(T, { horizontal: true, suggestedMax: 40 });
  assert.equal(h.x.beginAtZero, true);
  assert.equal(h.x.suggestedMax, 40);
  assert.equal(h.y.grid.display, false);
  assert.equal(h.y.ticks.color, T.label, '범주 이름은 조금 진하게');
  assert.equal(h.x.ticks.color, T.axis, '숫자 눈금은 옅게');
});

test('막대 데이터: 역할 색 + 둥근 끝, 덧붙인 설정이 이긴다', () => {
  const d = vizBar('점수', [1, 2], 'focus', T);
  assert.equal(d.backgroundColor, T.focus);
  assert.equal(d.borderRadius, 4);
  assert.equal(d.label, '점수');
  const d2 = vizBar('팀 수', [3], 'neutral', T, { backgroundColor: ['red'] });
  assert.deepEqual(d2.backgroundColor, ['red']);
});

test('범례: 계열이 1개면 숨김, 2개 이상이면 위 왼쪽', () => {
  assert.equal(vizLegend(T, 1).display, false);
  const l = vizLegend(T, 3);
  assert.equal(l.display, true);
  assert.equal(l.align, 'start');
  assert.equal(l.labels.color, T.text);
});

test('기준선 글자 자리: 선 바로 위 오른쪽, 그림 위 칸을 넘지 않음', () => {
  const area = { left: 40, right: 600, top: 10, bottom: 300 };
  const s = baselineLabelSpot(area, 250);
  assert.equal(s.align, 'right');
  assert.ok(s.x <= area.right && s.y < 250);
  const top = baselineLabelSpot(area, 12);
  assert.ok(top.y >= area.top + 10, '맨 위 선이면 아래로 내려 잘리지 않게');
  const out = baselineLabelSpot(area, 250, { outside: true });
  assert.equal(out.align, 'left');
  assert.ok(out.x > area.right, '막대와 겹치지 않게 그림 칸 오른쪽 밖');
});

test('축: 범주 이름을 하나도 건너뛰지 않게 할 수 있다', () => {
  const h = vizScales(T, { horizontal: true, allCategories: true });
  assert.equal(h.y.ticks.autoSkip, false);
});
