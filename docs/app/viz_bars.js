/**
 * 월별 막대 (작은 HTML 그림) — 그림 규칙(docs/layout_rules.md 7절)을 도시·공연장 목록 막대에 같이 쓴다.
 * - 값 축은 0부터: 막대 길이 = 값. 0인 달은 막대 없음(바닥선만), 작은 값을 최소 높이로 부풀리지 않는다.
 * - 색은 의미만: 지난달들 = 중립(--viz-neutral), 가장 최근 달 = 주인공(--viz-focus). 색은 CSS(.viz-mbar).
 * - 말풍선(title)에는 단위. 큰 그림(axis)은 0·꼭대기 눈금과 달 이름표(처음·끝·1월), 작은 그림은 스파크라인(눈금 없음).
 * 순수 함수 (tests/js/viz_bars.test.mjs).
 */

const NICE_STEPS = [1, 2, 5, 10];

/** 눈금 꼭대기: v 이상인 1·2·5 × 10^k (0 이하면 1) */
export function niceMax(v) {
  const x = Number(v);
  if (!Number.isFinite(x) || x <= 0) return 1;
  const p = 10 ** Math.floor(Math.log10(x));
  return NICE_STEPS.map(s => s * p).find(n => n >= x) || 10 * p;
}

/** 막대 높이(%) — 0·음수·눈금 0이면 0, 그 밖엔 값에 비례(소수 한 자리) */
export function barPct(v, max) {
  const x = Number(v);
  const m = Number(max);
  if (!Number.isFinite(x) || !Number.isFinite(m) || x <= 0 || m <= 0) return 0;
  return Math.round(Math.min(100, (x / m) * 100) * 10) / 10;
}

function monthLabel(ym) {
  const [y, m] = String(ym).split('-');
  return `${String(y).slice(2)}.${Number(m)}`;
}

/** 달 이름표 자리: 처음 · 끝 · 1월 — 처음·끝·앞 이름표와 너무 붙은 1월은 빼서 글자가 겹치지 않게 */
function labelIndexes(months) {
  const last = months.length - 1;
  if (last < 0) return [];
  const minGap = Math.max(2, Math.ceil(months.length / 8));
  const out = [0];
  months.forEach((ym, i) => {
    if (i <= 0 || i >= last || !String(ym).endsWith('-01')) return;
    if (i - out[out.length - 1] >= minGap && last - i >= minGap) out.push(i);
  });
  if (last > 0) out.push(last);
  return out;
}

function xLabelHtml(months, i) {
  const last = months.length - 1;
  const pos = i === 0 ? 'left:0' : i === last ? 'left:100%;transform:translateX(-100%)' : `left:${(((i + 0.5) / months.length) * 100).toFixed(1)}%`;
  return `<span style="${pos}" class="viz-mx">${monthLabel(months[i])}</span>`;
}

/**
 * @param {{ months: string[], vals: number[], unit?: string, label?: string, wrapCls?: string, barCls?: string,
 *           scaleMin?: number, axis?: boolean }} o
 *   scaleMin: 눈금 꼭대기 최소값(한 달 1~2회뿐인 곳이 꽉 찬 막대로 보이지 않게) · axis: 큰 그림(눈금·달 이름표)
 * @returns {string}
 */
export function monthBarsHtml({
  months, vals, unit = '일', label = '월별 공연 날짜', wrapCls = '', barCls = '', scaleMin = 0, axis = false,
}) {
  const nums = (vals || []).map(v => Math.max(0, Number(v) || 0));
  const peak = Math.max(Number(scaleMin) || 0, ...nums, 0);
  const top = axis ? niceMax(peak) : (peak || 1);
  const last = nums.length - 1;
  const bars = nums.map((v, i) => {
    const cls = [barCls, 'viz-mbar', i === last ? 'is-latest' : '', v <= 0 ? 'is-zero' : ''].filter(Boolean).join(' ');
    return `<span class="${cls}" style="height:${barPct(v, top)}%" title="${months[i]} · ${v}${unit}"></span>`;
  }).join('');
  const plot = `<div class="${[wrapCls, 'viz-mbars'].filter(Boolean).join(' ')}" role="img" aria-label="최근 ${nums.length}개월 ${label} ${nums.join(', ')}${unit}">${bars}</div>`;
  if (!axis) return plot;
  // 2줄 격자: [눈금 | 막대] / [빈칸 | 달 이름표] — 눈금 칸 높이가 막대 칸을 따라감(좁은 화면에서 막대가 낮아져도 0이 바닥선에)
  return `
    <div class="viz-mchart">
      <div class="viz-maxis" aria-hidden="true"><span class="viz-my">${top}${unit}</span><span class="viz-my">0</span></div>
      ${plot}
      <span class="viz-mgap" aria-hidden="true"></span>
      <div class="viz-mxs" aria-hidden="true">${labelIndexes(months).map(i => xLabelHtml(months, i)).join('')}</div>
    </div>`;
}
