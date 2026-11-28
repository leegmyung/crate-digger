// 앱 그림 공통 설정 — Chart.js 기본값 · 색 역할 · 축 · 범례 · 기준선/오차 막대 플러그인. 관계망(css/graph.css)과 같은 색 토큰(--viz-*).
// 원칙(docs/layout_rules.md '그림 규칙'): 값 축은 0부터 · 격자는 값 축 한 방향만 옅게 · 색은 의미(주인공/비교/기준)만
//   · 범례는 위 왼쪽, 계열 1개면 없음 · 말풍선은 표면색 + 테두리 · 막대 끝 4px 둥글게 · 어두운 테마는 같은 토큰을 다시 읽음.
// 순수 함수(readVizTokens 빼고)는 tests/js/chart_theme.test.mjs 가 검사한다.

/** 색 역할 — 그림에서 색은 이 의미로만 쓴다 */
export const VIZ_ROLES = ['focus', 'compare', 'compare2', 'neutral', 'weak', 'ref', 'gig', 'sel'];

const TOKEN_VARS = {
  focus: '--viz-focus', compare: '--viz-compare', compare2: '--viz-compare-2', neutral: '--viz-neutral', weak: '--viz-weak',
  ref: '--viz-ref', grid: '--viz-grid', axis: '--viz-axis', label: '--viz-label', text: '--viz-text',
  surface: '--viz-surface', tipLine: '--viz-tip-line', gig: '--viz-gig', sel: '--viz-sel',
};
const FALLBACK = {
  focus: '#b4501f', compare: '#929191', compare2: '#c6c6c6', neutral: '#a9a8a6', weak: '#dcdbd9', ref: '#121110',
  grid: 'rgba(18,17,16,0.08)', axis: '#666159', label: '#524e47', text: '#121110', surface: '#ffffff', tipLine: '#c9c4bb',
  gig: '#1b7a78', sel: '#2f5d8c',
};
const FONT = '"Pretendard", -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", sans-serif';
const VALUE_TICKS = 5;
const PNG_BUTTON_ROOM = 22;

/**
 * css 토큰을 캔버스가 읽는 rgb 문자열로 (color-mix 등도 풀림). 테마가 바뀌면 다시 부른다.
 * @returns {Record<string, string>}
 */
export function readVizTokens(doc = globalThis.document) {
  if (!doc?.body) return { ...FALLBACK };
  const probe = doc.createElement('span');
  probe.style.cssText = 'position:absolute;width:0;height:0;overflow:hidden;visibility:hidden;pointer-events:none';
  doc.body.appendChild(probe);
  const out = {};
  for (const [key, cssVar] of Object.entries(TOKEN_VARS)) {
    probe.style.color = '';
    probe.style.color = `var(${cssVar}, ${FALLBACK[key]})`;
    out[key] = getComputedStyle(probe).color || FALLBACK[key];
  }
  probe.remove();
  return out;
}

export function roleColor(role, t) {
  return VIZ_ROLES.includes(role) && t[role] ? t[role] : t.neutral;
}

/** Chart.defaults 에 덮을 값 */
export function chartDefaultsPatch(t) {
  return {
    color: t.label,
    borderColor: t.grid,
    font: { family: FONT, size: 12 },
    animation: false,
    layout: { padding: { top: PNG_BUTTON_ROOM } },   // 오른쪽 위 'PNG' 단추(chart_png.js) 자리
    plugins: {
      legend: {
        position: 'top',
        align: 'start',
        labels: { usePointStyle: true, pointStyle: 'rectRounded', boxWidth: 10, boxHeight: 10, padding: 14, color: t.text, font: { size: 12, weight: '600' } },
      },
      tooltip: {
        backgroundColor: t.surface,
        borderColor: t.tipLine,
        borderWidth: 1,
        titleColor: t.text,
        bodyColor: t.text,
        footerColor: t.label,
        titleFont: { size: 12.5, weight: '700' },
        bodyFont: { size: 12 },
        padding: 10,
        cornerRadius: 8,
        boxPadding: 4,
        usePointStyle: true,
        caretSize: 5,
      },
    },
    elements: {
      bar: { borderRadius: 4, borderSkipped: 'start' },
      line: { borderWidth: 2, tension: 0 },
      point: { radius: 0, hoverRadius: 4, hitRadius: 8 },
    },
    scale: {
      grid: { color: t.grid, drawTicks: false },
      border: { display: false },
      ticks: { color: t.axis, padding: 6, font: { size: 11.5 } },
    },
  };
}

function deepAssign(target, patch) {
  for (const [k, v] of Object.entries(patch)) {
    if (v && typeof v === 'object' && !Array.isArray(v)) {
      if (!target[k] || typeof target[k] !== 'object') target[k] = {};
      deepAssign(target[k], v);
    } else {
      target[k] = v;
    }
  }
  return target;
}

/** Chart.js 를 받은 뒤·테마가 바뀐 뒤 부른다 */
export function applyChartDefaults(Chart, t = readVizTokens()) {
  if (!Chart?.defaults) return;
  deepAssign(Chart.defaults, chartDefaultsPatch(t));
}

/**
 * 축 한 벌. 값 축 = 0부터·눈금 5개 안팎·옅은 격자, 범주 축 = 격자 없음·이름은 조금 진하게.
 * @param {object} t 토큰
 * @param {{ horizontal?: boolean, valueFmt?: (v: number) => string, suggestedMax?: number, max?: number, maxCategoryTicks?: number, precision?: number }} [o]
 */
export function vizScales(t, o = {}) {
  const value = {
    beginAtZero: true,
    grid: { color: t.grid, drawTicks: false },
    border: { display: false },
    ticks: { color: t.axis, maxTicksLimit: VALUE_TICKS, padding: 6, font: { size: 11.5 } },
  };
  if (o.valueFmt) value.ticks.callback = o.valueFmt;
  if (o.precision !== undefined) value.ticks.precision = o.precision;
  if (o.suggestedMax !== undefined) value.suggestedMax = o.suggestedMax;
  if (o.max !== undefined) value.max = o.max;
  const category = {
    grid: { display: false },
    border: { display: true, color: t.grid },
    ticks: { color: t.label, font: { size: 12 }, padding: 6 },
  };
  if (o.maxCategoryTicks) category.ticks.maxTicksLimit = o.maxCategoryTicks;
  if (o.allCategories) category.ticks.autoSkip = false;
  return o.horizontal ? { x: value, y: category } : { x: category, y: value };
}

/** 막대 데이터 한 벌 (색 = 역할) */
export function vizBar(label, data, role, t, extra = {}) {
  return {
    label,
    data,
    backgroundColor: roleColor(role, t),
    borderRadius: 4,
    borderSkipped: 'start',
    maxBarThickness: 32,
    categoryPercentage: 0.72,
    barPercentage: 0.86,
    ...extra,
  };
}

/** 범례: 계열 1개면 숨김(제목이 이름), 2개 이상이면 위 왼쪽 */
export function vizLegend(t, seriesCount) {
  if (seriesCount < 2) return { display: false };
  const { legend } = chartDefaultsPatch(t).plugins;
  return { ...legend, display: true };
}

/** 가로 기준선 글자 자리: 기본 = 선 바로 위 오른쪽 끝(맨 위면 선 아래로), outside = 그림 칸 오른쪽 밖(막대와 안 겹침) */
export function baselineLabelSpot(area, y, { outside = false } = {}) {
  if (outside) return { x: area.right + 6, y: y + 4, align: 'left' };
  const above = y - 6;
  return { x: area.right - 4, y: above < area.top + 12 ? y + 14 : above, align: 'right' };
}

/** 기준선 글자를 그림 칸 밖에 둘 때 오른쪽에 비워 둘 폭 */
export const BASELINE_OUTSIDE_PAD = 112;

function haloText(ctx, text, x, y, color, halo) {
  ctx.lineJoin = 'round';
  ctx.lineWidth = 4;
  ctx.strokeStyle = halo;
  ctx.strokeText(text, x, y);
  ctx.fillStyle = color;
  ctx.fillText(text, x, y);
}

/** 가로 기준선 (예: 무작위 기대) — options.plugins.horizontalBaseline = { value, label, color, bgColor, outside }
 *  outside 면 글자를 그림 칸 오른쪽 밖에 쓴다 → options.layout.padding.right = BASELINE_OUTSIDE_PAD 를 같이 준다 */
export const horizontalBaselinePlugin = {
  id: 'horizontalBaseline',
  afterDatasetsDraw(chart, _args, opts) {
    if (!opts || opts.value === null || opts.value === undefined) return;
    const { ctx, chartArea, scales } = chart;
    const y = scales.y.getPixelForValue(opts.value);
    if (y < chartArea.top || y > chartArea.bottom) return;
    ctx.save();
    ctx.strokeStyle = opts.color || FALLBACK.ref;
    ctx.lineWidth = 1.5;
    ctx.setLineDash([5, 4]);
    ctx.beginPath();
    ctx.moveTo(chartArea.left, y);
    ctx.lineTo(chartArea.right, y);
    ctx.stroke();
    ctx.setLineDash([]);
    if (opts.label) {
      const spot = baselineLabelSpot(chartArea, y, { outside: Boolean(opts.outside) });
      ctx.font = `600 11.5px ${FONT}`;
      ctx.textAlign = spot.align;
      haloText(ctx, opts.label, spot.x, spot.y, opts.color || FALLBACK.ref, opts.bgColor || FALLBACK.surface);
    }
    ctx.restore();
  },
};

/** 세로 기준선 + 신뢰구간 수염 — options.plugins.signalWhisker = { rows, baseline, baselineColor, whiskerColor, bgColor } */
export const signalWhiskerPlugin = {
  id: 'signalWhisker',
  afterDatasetsDraw(chart, _args, opts) {
    if (!opts) return;
    const { ctx, chartArea, scales } = chart;
    ctx.save();
    if (typeof opts.baseline === 'number') {
      const bx = scales.x.getPixelForValue(opts.baseline);
      if (bx >= chartArea.left && bx <= chartArea.right) {
        ctx.strokeStyle = opts.baselineColor || FALLBACK.ref;
        ctx.lineWidth = 1.5;
        ctx.setLineDash([4, 4]);
        ctx.beginPath();
        ctx.moveTo(bx, chartArea.top);
        ctx.lineTo(bx, chartArea.bottom);
        ctx.stroke();
        ctx.setLineDash([]);
        const lbl = `기준선 ${opts.baseline.toFixed(1)}%`;
        ctx.font = `600 11.5px ${FONT}`;
        const tw = ctx.measureText(lbl).width;
        ctx.textAlign = 'left';
        haloText(ctx, lbl, Math.min(chartArea.right - tw - 6, bx + 6), chartArea.top + 12, opts.baselineColor || FALLBACK.ref, opts.bgColor || FALLBACK.surface);
      }
    }
    const meta = chart.getDatasetMeta(0);
    const rows = opts.rows || [];
    ctx.strokeStyle = opts.whiskerColor || FALLBACK.label;
    ctx.lineWidth = 1.5;
    for (let i = 0; i < rows.length; i++) {
      const el = meta.data[i];
      if (!el) continue;
      const r = rows[i];
      const xLow = scales.x.getPixelForValue(Number(r.ci_low) || 0);
      const xHigh = scales.x.getPixelForValue(Number(r.ci_high) || 0);
      const y = el.y;
      ctx.globalAlpha = Number(r.teams) < 10 ? 0.45 : 0.9;
      ctx.beginPath();
      ctx.moveTo(xLow, y);
      ctx.lineTo(xHigh, y);
      ctx.moveTo(xLow, y - 4);
      ctx.lineTo(xLow, y + 4);
      ctx.moveTo(xHigh, y - 4);
      ctx.lineTo(xHigh, y + 4);
      ctx.stroke();
    }
    ctx.restore();
  },
};
