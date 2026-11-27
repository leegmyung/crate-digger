/**
 * 1-5: 공용 막대 3종 (항목 막대 · 동료 비교 막대 · 상태 막대)
 * - 색은 var(--accent), var(--line), var(--na-bg), var(--na-ink)만 사용
 * - 값이 없으면 --na-bg 회색 막대 + '자료 없음'으로 0과 '모름'을 명확히 구분
 */

function esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function clampPct(n) {
  if (!Number.isFinite(n)) return 0;
  return Math.max(0, Math.min(100, n));
}

function defaultFormatNum(n) {
  const num = Number(n);
  if (!Number.isFinite(num)) return '자료 없음';
  return Number.isInteger(num) ? num.toLocaleString('ko-KR') : num.toFixed(1);
}

/**
 * ① 항목 막대 (이름 · 막대 · 값)
 * @param {string} label
 * @param {number|null|undefined} value
 * @param {number} max
 * @param {{ unit?: string, formatValue?: (v:number)=>string, infoTipHtml?: string, naReason?: string }} [opts]
 */
export function itemBar(label, value, max = 100, opts = {}) {
  const isMissing = value === null || value === undefined || value === '' || !Number.isFinite(Number(value));
  const tipHtml = opts.infoTipHtml || '';
  if (isMissing) {
    const reasonAttr = opts.naReason ? ` data-na-reason="${esc(opts.naReason)}" tabindex="0"` : '';
    return `
      <div class="cd-item-bar is-na">
        <span class="cd-item-bar-lbl">${esc(label)}${tipHtml}</span>
        <div class="cd-item-bar-track is-na" role="img" aria-label="${esc(label)}: 자료 없음"></div>
        <span class="cd-item-bar-val is-na"${reasonAttr}>자료 없음</span>
      </div>
    `;
  }
  const num = Number(value);
  const denom = Number(max) > 0 ? Number(max) : Math.max(1, num);
  const pct = num > 0 ? Math.max(3, clampPct((num / denom) * 100)) : 0;
  const valStr = typeof opts.formatValue === 'function'
    ? opts.formatValue(num)
    : `${defaultFormatNum(num)}${opts.unit ? opts.unit : ''}`;

  return `
    <div class="cd-item-bar">
      <span class="cd-item-bar-lbl">${esc(label)}${tipHtml}</span>
      <div class="cd-item-bar-track" role="img" aria-label="${esc(label)} ${esc(valStr)}">
        <span class="cd-item-bar-fill" style="width:${pct.toFixed(1)}%"></span>
      </div>
      <span class="cd-item-bar-val">${esc(valStr)}</span>
    </div>
  `;
}

/**
 * 항목 막대 여러 줄 묶음
 * @param {Array<{ label: string, value: number|null, max?: number, unit?: string, formatValue?: Function, infoTipHtml?: string, naReason?: string }>} items
 * @param {{ max?: number }} [opts]
 */
export function itemBarList(items = [], opts = {}) {
  const validVals = items.map(it => Number(it?.value)).filter(v => Number.isFinite(v) && v > 0);
  const sharedMax = opts.max ?? (validVals.length ? Math.max(...validVals) : 1);
  return `<div class="cd-item-bar-list">${items.map(it => itemBar(it.label, it.value, it.max ?? sharedMax, it)).join('')}</div>`;
}

/**
 * ② 동료 비교 막대 (회색 막대 + 중앙값 눈금 + 내 위치 점 + 글자 등급)
 * @param {{
 *   label?: string,
 *   value?: number|null,
 *   min?: number,
 *   median?: number,
 *   max?: number,
 *   pct?: number|null,
 *   grade?: string,
 *   groupLabel?: string,
 *   formatValue?: (v:number)=>string,
 *   infoTipHtml?: string,
 *   naReason?: string
 * }} spec
 */
export function peerBar(spec = {}) {
  const {
    label = '',
    value = null,
    min = 0,
    median = null,
    max = 100,
    pct = null,
    grade = '',
    groupLabel = '',
    formatValue = defaultFormatNum,
    infoTipHtml = '',
    naReason = '',
  } = spec;

  const hasPct = pct !== null && pct !== undefined && Number.isFinite(Number(pct));
  const hasVal = value !== null && value !== undefined && Number.isFinite(Number(value));
  const span = Number(max) - Number(min);
  const isMissing = !hasPct && (!hasVal || !Number.isFinite(span) || span <= 0);

  if (isMissing) {
    const reasonAttr = naReason ? ` data-na-reason="${esc(naReason)}" tabindex="0"` : '';
    return `
      <div class="cd-peer-bar is-na">
        ${(label || groupLabel) ? `
          <div class="cd-peer-bar-head">
            <span class="cd-peer-bar-lbl">${esc(label)}${infoTipHtml}</span>
            ${groupLabel ? `<span class="cd-peer-bar-group">${esc(groupLabel)}</span>` : ''}
          </div>
        ` : ''}
        <div class="cd-peer-bar-row">
          <div class="cd-peer-bar-track is-na" role="img" aria-label="${esc(label || '동료 비교')}: 자료 없음"></div>
          <span class="cd-peer-bar-grade is-na"${reasonAttr}>자료 없음</span>
        </div>
      </div>
    `;
  }

  const posPct = hasPct
    ? clampPct(Number(pct))
    : clampPct(((Number(value) - Number(min)) / span) * 100);

  const medPct = (median !== null && median !== undefined && Number.isFinite(Number(median)) && span > 0)
    ? clampPct(((Number(median) - Number(min)) / span) * 100)
    : 50;

  const valLabel = hasVal ? formatValue(Number(value)) : `상위 ${Math.max(1, Math.round(100 - posPct))}%`;
  const gradeText = grade || (posPct >= 80 ? '탁월' : posPct >= 60 ? '좋음' : posPct >= 35 ? '보통' : '아래');
  const isTopGrade = posPct >= 60;

  return `
    <div class="cd-peer-bar">
      ${(label || groupLabel) ? `
        <div class="cd-peer-bar-head">
          <span class="cd-peer-bar-lbl">${esc(label)}${infoTipHtml}</span>
          ${groupLabel ? `<span class="cd-peer-bar-group">${esc(groupLabel)}</span>` : ''}
        </div>
      ` : ''}
      <div class="cd-peer-bar-row">
        <div class="cd-peer-bar-track-wrap">
          <div class="cd-peer-bar-track" role="img" aria-label="${esc(label || '동료 비교')}: ${esc(valLabel)}, 등급 ${esc(gradeText)}">
            <span class="cd-peer-bar-median" style="left:${medPct.toFixed(1)}%" title="동료 중앙값${median !== null ? ` (${esc(formatValue(Number(median)))})` : ''}"></span>
            <span class="cd-peer-bar-dot" style="left:${posPct.toFixed(1)}%" title="현재 팀 (${esc(valLabel)})"></span>
          </div>
          <div class="cd-peer-bar-scale" aria-hidden="true">
            <span>${esc(formatValue(Number(min)))}</span>
            <span>중앙값${median !== null ? ` ${esc(formatValue(Number(median)))}` : ''}</span>
            <span>${esc(formatValue(Number(max)))}</span>
          </div>
        </div>
        <div class="cd-peer-bar-right">
          <span class="cd-peer-bar-grade${isTopGrade ? ' is-accent' : ''}">${esc(gradeText)}</span>
          <span class="cd-peer-bar-val">${esc(valLabel)}</span>
        </div>
      </div>
    </div>
  `;
}

/**
 * ③ 상태 막대 (제목 · 현재 상태 · 막대 · 양끝 이름)
 * @param {{
 *   title: string,
 *   stateLabel?: string|null,
 *   ratio?: number|null,
 *   lowLabel?: string,
 *   highLabel?: string,
 *   infoTipHtml?: string,
 *   naReason?: string
 * }} spec
 */
export function statusBar(spec = {}) {
  const {
    title = '',
    stateLabel = null,
    ratio = null,
    lowLabel = '',
    highLabel = '',
    infoTipHtml = '',
    naReason = '',
  } = spec;

  const isMissing = ratio === null || ratio === undefined || !Number.isFinite(Number(ratio)) || !stateLabel;
  if (isMissing) {
    const reasonAttr = naReason ? ` data-na-reason="${esc(naReason)}" tabindex="0"` : '';
    return `
      <div class="cd-status-bar is-na">
        <div class="cd-status-bar-head">
          <span class="cd-status-bar-title">${esc(title)}</span>
          ${infoTipHtml}
        </div>
        <div class="cd-status-bar-state is-na"${reasonAttr}>자료 없음</div>
        <div class="cd-status-bar-track is-na" role="img" aria-label="${esc(title)}: 자료 없음"></div>
        ${(lowLabel || highLabel) ? `
          <div class="cd-status-bar-ends">
            <span>${esc(lowLabel)}</span>
            <span>${esc(highLabel)}</span>
          </div>
        ` : ''}
      </div>
    `;
  }

  const raw = Number(ratio);
  const pct = clampPct(raw <= 1 ? raw * 100 : raw);

  return `
    <div class="cd-status-bar">
      <div class="cd-status-bar-head">
        <span class="cd-status-bar-title">${esc(title)}</span>
        ${infoTipHtml}
      </div>
      <div class="cd-status-bar-state">${esc(stateLabel)}</div>
      <div class="cd-status-bar-track" role="img" aria-label="${esc(title)}: ${esc(stateLabel)} (${Math.round(pct)}%)">
        <span class="cd-status-bar-fill" style="width:${pct.toFixed(1)}%"></span>
      </div>
      ${(lowLabel || highLabel) ? `
        <div class="cd-status-bar-ends">
          <span>${esc(lowLabel)}</span>
          <span>${esc(highLabel)}</span>
        </div>
      ` : ''}
    </div>
  `;
}
