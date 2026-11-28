/**
 * 4-3 공연장 전후 흐름 그림 — 왼쪽 = 이곳 '전에' 선 곳 → 가운데 = 이곳 → 오른쪽 = 이곳 '뒤에' 처음 선 곳.
 * 굵기 = 팀 수, 색 = 그 공연장이 이곳보다 큰 무대(up)·비슷한 무대(same)·작은 무대(down)·크기 모름(unknown).
 * 넓은 판(760)과 좁은 판(360) 두 장을 만들고 css(@container)가 칸 폭에 맞는 한 장만 보인다. 순수 함수(다른 모듈 안 부름).
 * 표본(처음 선 팀) 5팀 미만이면 그림 대신 문장, 20팀 미만이면 앞뒤 상위 3곳만.
 */

import { escapeHtml as esc } from '../util.js';

export const TIER_COLUMNS = [
  { key: 'S', label: 'S ~150명' },
  { key: 'M', label: 'M ~400명' },
  { key: 'L', label: 'L ~1,000명' },
  { key: 'XL', label: 'XL 1,000명+' },
  { key: '?', label: '크기 모름' },
];

const TIER_RANK = { S: 1, M: 2, L: 3, XL: 4 };
const REL_LABELS = { up: '이곳보다 큰 무대', same: '비슷한 무대', down: '더 작은 무대', unknown: '크기 모름' };
const REL_ORDER = ['up', 'same', 'down', 'unknown'];

const MIN_SAMPLE = 5;
const SMALL_SAMPLE = 20;
const TOP = 40;            // 위 제목 줄 자리
const BOTTOM_PAD = 30;     // 가운데 아래 '처음 선 팀' 줄 자리
const LABEL_SLOT = 36;     // 이름 2줄이 들어가는 최소 칸 높이
const SLOT_GAP = 6;
const MIN_BAR = 3;
const BAR_W = 10;
const CENTER_W = 18;

const SIZES = {
  wide: { width: 760, sideBudget: 250, maxBar: 48, leftX: 250, centerX: 371, rightX: 500, nameMax: 14, centerMax: 14, fs: 12.5 },
  compact: { width: 360, sideBudget: 220, maxBar: 40, leftX: 122, centerX: 171, rightX: 228, nameMax: 7, centerMax: 9, fs: 12 },
};

function short(name, max = 9) {
  const arr = Array.from(String(name));
  return arr.length > max ? `${arr.slice(0, max - 1).join('')}…` : arr.join('');
}

/** 그 공연장(tier)이 이곳(hereTier)보다 큰지·비슷한지·작은지 */
export function relTier(tier, hereTier) {
  const a = TIER_RANK[String(tier || '').toUpperCase()];
  const b = TIER_RANK[String(hereTier || '').toUpperCase()];
  if (!a || !b) return 'unknown';
  if (a > b) return 'up';
  if (a < b) return 'down';
  return 'same';
}

function tierText(tier) {
  const t = String(tier || '').toUpperCase();
  return TIER_RANK[t] ? t : '크기 모름';
}

function stackSide(list, scale, top) {
  let y = top;
  return list.map(([name, n]) => {
    const h = Math.max(MIN_BAR, n * scale);
    const slotH = Math.max(h, LABEL_SLOT);
    const node = { name, n, h, slotTop: y, slotH, y: y + (slotH - h) / 2 };
    y += slotH + SLOT_GAP;
    return node;
  });
}

function shiftSide(nodes, dy) {
  return nodes.map(n => ({ ...n, slotTop: n.slotTop + dy, y: n.y + dy }));
}

function sideHeight(nodes) {
  return nodes.length ? nodes[nodes.length - 1].slotTop + nodes[nodes.length - 1].slotH - nodes[0].slotTop : 0;
}

/**
 * 자리 잡기. before/after = [[공연장, 팀 수], ...] (많은 순), width = 760 | 360
 * @returns {{ width: number, height: number, scale: number, left: object[], right: object[], center: {x: number, y: number, w: number, h: number}, cols: object }}
 */
export function flowLayout({ before = [], after = [], width = 760 }) {
  const cfg = width < 500 ? SIZES.compact : SIZES.wide;
  const sumL = before.reduce((a, x) => a + x[1], 0);
  const sumR = after.reduce((a, x) => a + x[1], 0);
  const maxN = Math.max(1, ...before.map(x => x[1]), ...after.map(x => x[1]));
  const scale = Math.min(cfg.sideBudget / Math.max(1, sumL, sumR), cfg.maxBar / maxN);
  let left = stackSide(before, scale, TOP);
  let right = stackSide(after, scale, TOP);
  const centerH = Math.max(12, Math.max(sumL, sumR) * scale);
  const colH = Math.max(sideHeight(left), sideHeight(right), centerH);
  left = shiftSide(left, (colH - sideHeight(left)) / 2);
  right = shiftSide(right, (colH - sideHeight(right)) / 2);
  return {
    width: cfg.width,
    height: TOP + colH + BOTTOM_PAD,
    scale,
    left,
    right,
    center: { x: cfg.centerX, y: TOP + (colH - centerH) / 2, w: CENTER_W, h: centerH },
    cols: cfg,
  };
}

/** 띠 하나: (x0, y0~y0+h0) 에서 (x1, y1~y1+h1) 까지 부드럽게 */
function ribbon(x0, y0, h0, x1, y1, h1) {
  const xm = ((x0 + x1) / 2).toFixed(1);
  const f = v => v.toFixed(1);
  return `M${f(x0)} ${f(y0)}C${xm} ${f(y0)} ${xm} ${f(y1)} ${f(x1)} ${f(y1)}L${f(x1)} ${f(y1 + h1)}C${xm} ${f(y1 + h1)} ${xm} ${f(y0 + h0)} ${f(x0)} ${f(y0 + h0)}Z`;
}

function sideItems(nodes, side, L, hereTier, tierOf) {
  const { cols, center, scale } = L;
  const total = nodes.reduce((a, n) => a + n.n * scale, 0);
  let cy = center.y + (center.h - total) / 2;
  return nodes.map((node) => {
    const rel = relTier(tierOf.get(node.name), hereTier);
    const thick = node.n * scale;
    const isLeft = side === 'left';
    const barX = isLeft ? cols.leftX : cols.rightX;
    const path = isLeft
      ? ribbon(barX + BAR_W, node.y + (node.h - thick) / 2, thick, center.x, cy, thick)
      : ribbon(center.x + center.w, cy, thick, barX, node.y + (node.h - thick) / 2, thick);
    cy += thick;
    const mid = node.slotTop + node.slotH / 2;
    const tx = isLeft ? barX - 9 : barX + BAR_W + 9;
    const anchor = isLeft ? 'end' : 'start';
    const tip = `${node.name} — ${isLeft ? '이곳 전에' : '이곳 뒤에'} ${node.n}팀 · ${tierText(tierOf.get(node.name))}`;
    return { rel, html: `
      <a class="vfl-item is-${rel}" data-vfl="${esc(node.name)}" href="#/venue/${encodeURIComponent(node.name)}"><title>${esc(tip)}</title>
        <path class="vfl-ribbon" d="${path}"></path>
        <rect class="vfl-bar" x="${barX}" y="${node.y.toFixed(1)}" width="${BAR_W}" height="${node.h.toFixed(1)}" rx="2.5"></rect>
        <text class="vfl-name" x="${tx}" y="${(mid - 2).toFixed(1)}" text-anchor="${anchor}" font-size="${cols.fs}">${esc(short(node.name, cols.nameMax))}</text>
        <text class="vfl-sub" x="${tx}" y="${(mid + 12).toFixed(1)}" text-anchor="${anchor}">${node.n}팀 · ${esc(tierText(tierOf.get(node.name)))}</text>
      </a>` };
  });
}

function svgFor(kind, { venue, tier, before, after, sample, tierOf }) {
  const L = flowLayout({ before, after, width: SIZES[kind].width });
  const { cols, center } = L;
  const items = [...sideItems(L.left, 'left', L, tier, tierOf), ...sideItems(L.right, 'right', L, tier, tierOf)];
  const isWide = kind === 'wide';
  const titleL = isWide ? '← 이곳 전에 선 곳' : '전에 선 곳';
  const titleR = isWide ? '이곳 뒤에 처음 선 곳 →' : '뒤에 간 곳';
  const cx = center.x + center.w / 2;
  const sampleTxt = sample !== null && sample !== undefined ? `처음 선 팀 ${sample}팀 · ${tierText(tier)}` : tierText(tier);
  const cls = isWide ? 'vf-svg vfl-svg is-wide' : 'vfl-svg is-compact';
  const aria = `${venue} 전후 공연장 흐름: 왼쪽은 이곳 전에 선 곳, 오른쪽은 이곳 뒤에 처음 선 곳, 굵기는 팀 수, 색은 이곳보다 큰 무대인지`;
  const svg = `
    <svg class="${cls}" viewBox="0 0 ${L.width} ${L.height.toFixed(0)}" role="img" aria-label="${esc(aria)}"${isWide ? '' : ' aria-hidden="true"'}>
      <text class="vfl-col-title" x="${cols.leftX + BAR_W}" y="18" text-anchor="end">${titleL}</text>
      <text class="vfl-col-title" x="${cols.rightX}" y="18" text-anchor="start">${titleR}</text>
      ${items.map(x => x.html).join('')}
      <g class="vfl-here">
        <rect x="${center.x}" y="${center.y.toFixed(1)}" width="${center.w}" height="${center.h.toFixed(1)}" rx="4"></rect>
        <text class="vfl-here-name" x="${cx}" y="${(center.y - 8).toFixed(1)}" text-anchor="middle">${esc(short(venue, cols.centerMax))}</text>
        <text class="vfl-here-sub" x="${cx}" y="${(L.height - 9).toFixed(1)}" text-anchor="middle">${esc(sampleTxt)}</text>
      </g>
    </svg>`;
  return { svg, rels: new Set(items.map(x => x.rel)) };
}

function sentence(venue, before, after, sample) {
  const fmt = list => list.slice(0, 3).map(([v, n]) => `${esc(v)}(${n}팀)`).join(', ');
  const parts = [];
  if (before.length) parts.push(`이곳 전에는 ${fmt(before)}`);
  if (after.length) parts.push(`이곳 뒤에는 ${fmt(after)}`);
  const body = parts.length ? `${parts.join(', ')}에 많이 섰습니다.` : '앞뒤로 함께 집계된 공연장이 없습니다.';
  const note = sample !== null && sample < MIN_SAMPLE ? ` (처음 선 팀 ${sample}팀뿐이라 그림 대신 문장으로)` : '';
  return `<p class="vf-sentence">${esc(venue)} — ${body}${note}</p>`;
}

function legendHtml(rels) {
  const keys = REL_ORDER.filter(r => rels.has(r))
    .map(r => `<span class="vfl-key is-${r}"><i aria-hidden="true"></i>${REL_LABELS[r]}</span>`).join('');
  return `<div class="vfl-legend">${keys}<span class="vfl-key-w"><i aria-hidden="true"></i>굵기 = 팀 수</span><span class="vfl-key-tip">공연장을 누르면 그 공연장 페이지</span></div>`;
}

/**
 * @param {{ venue: string, tier: string, before: Array<[string, number]>, after: Array<[string, number]>,
 *           sample: number|null, tierOf: Map<string, string> }} p
 * @returns {{ kind: 'svg'|'sentence', html: string }}
 */
export function buildVenueFlow({ venue, tier, before = [], after = [], sample = null, tierOf = new Map() }) {
  const clean = list => (list || []).filter(x => Array.isArray(x) && x[0]).map(([v, n]) => [String(v), Math.max(0, Number(n) || 0)]);
  const b = clean(before);
  const a = clean(after);
  if ((sample !== null && sample < MIN_SAMPLE) || (!b.length && !a.length)) {
    return { kind: 'sentence', html: sentence(venue, b, a, sample) };
  }
  const take = sample !== null && sample < SMALL_SAMPLE ? 3 : 6;
  const input = { venue, tier: String(tier || '').toUpperCase(), before: b.slice(0, take), after: a.slice(0, take), sample, tierOf };
  const wide = svgFor('wide', input);
  const compact = svgFor('compact', input);
  return { kind: 'svg', html: `<div class="vfl">${legendHtml(wide.rels)}<div class="vfl-stage">${wide.svg}${compact.svg}</div></div>` };
}
