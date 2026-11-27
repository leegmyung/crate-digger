/**
 * 4-3 공연장 전후 흐름 그림 — 가로축 = 체급 4칸 + '체급 모름'. 순수 함수(다른 모듈 안 부름).
 * 위쪽 호 = 이 공연장 '전에' 선 곳(--ink-muted), 아래쪽 호 = '뒤에' 간 곳(--accent), 굵기 = 팀 수.
 * 표본(처음 선 팀) 5팀 미만이면 그림 대신 문장, 20팀 미만이면 앞뒤 상위 3곳만.
 */

export const TIER_COLUMNS = [
  { key: 'S', label: 'S ~150명' },
  { key: 'M', label: 'M ~400명' },
  { key: 'L', label: 'L ~1,000명' },
  { key: 'XL', label: 'XL 1,000명+' },
  { key: '?', label: '체급 모름' },
];

const MIN_SAMPLE = 5;
const SMALL_SAMPLE = 20;
const W = 760;
const H = 340;
const PAD_X = 90;          // 첫·끝 칸 띠가 그림 밖으로 나가지 않게
const TOP_Y = 84;          // 위 이름표 3줄 자리
const BOTTOM_Y = H - 92;   // 아래 이름표 3줄 + 체급 이름 자리
const MID_Y = (TOP_Y + BOTTOM_Y) / 2;
const BAND = 0.86;         // 한 칸 안에서 점을 펼치는 너비(칸 간격 대비)
const LABEL_ROWS = 3;      // 이름표를 3줄로 엇갈려 겹치지 않게
const LABEL_STEP = 14;

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
}

function short(name, max = 9) {
  const arr = Array.from(String(name));
  return arr.length > max ? `${arr.slice(0, max - 1).join('')}…` : arr.join('');
}

function colIndex(tier) {
  const i = TIER_COLUMNS.findIndex(c => c.key === tier);
  return i >= 0 ? i : TIER_COLUMNS.length - 1;
}

function colX(i) {
  const step = (W - PAD_X * 2) / (TIER_COLUMNS.length - 1);
  return PAD_X + step * i;
}

/** 같은 칸에 여러 곳이면 좌우로 펼친다 */
function placeNodes(items, tierOf, y) {
  const byCol = new Map();
  for (const [name, n] of items) {
    const ci = colIndex(tierOf.get(name));
    if (!byCol.has(ci)) byCol.set(ci, []);
    byCol.get(ci).push({ name, n, ci });
  }
  const step = (W - PAD_X * 2) / (TIER_COLUMNS.length - 1);
  const band = step * BAND;
  const out = [];
  for (const [ci, list] of byCol) {
    list.forEach((it, k) => {
      const offset = list.length === 1 ? 0 : -band / 2 + (k * band) / (list.length - 1);
      out.push({ ...it, x: colX(ci) + offset, y, row: k % LABEL_ROWS, tierKey: TIER_COLUMNS[ci].key });
    });
  }
  return out;
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

/**
 * @param {{ venue: string, tier: string, before: Array<[string, number]>, after: Array<[string, number]>,
 *           sample: number|null, tierOf: Map<string, string> }} p
 * @returns {{ kind: 'svg'|'sentence', html: string }}
 */
export function buildVenueFlow({ venue, tier, before = [], after = [], sample = null, tierOf = new Map() }) {
  const b = (before || []).filter(x => Array.isArray(x) && x[0]);
  const a = (after || []).filter(x => Array.isArray(x) && x[0]);
  if ((sample !== null && sample < MIN_SAMPLE) || (!b.length && !a.length)) {
    return { kind: 'sentence', html: sentence(venue, b, a, sample) };
  }
  const take = sample !== null && sample < SMALL_SAMPLE ? 3 : 6;
  const bTop = b.slice(0, take);
  const aTop = a.slice(0, take);
  const maxN = Math.max(1, ...bTop.map(x => x[1]), ...aTop.map(x => x[1]));
  const cx = colX(colIndex(tier));
  const width = n => (1.5 + (n / maxN) * 7).toFixed(1);

  const arc = (node, cls) => {
    const ctrlY = node.y < MID_Y ? TOP_Y - 10 : BOTTOM_Y + 10;
    return `<path class="vf-arc ${cls}" d="M${node.x.toFixed(1)} ${node.y} Q${((node.x + cx) / 2).toFixed(1)} ${ctrlY} ${cx.toFixed(1)} ${MID_Y}" stroke-width="${width(node.n)}"><title>${esc(node.name)} ${node.n}팀</title></path>`;
  };
  const label = (node, above) => `
    <g class="vf-node" data-vf-tier="${node.tierKey}">
      <circle cx="${node.x.toFixed(1)}" cy="${node.y}" r="4"></circle>
      <text x="${node.x.toFixed(1)}" y="${above ? node.y - 10 - node.row * LABEL_STEP : node.y + 18 + node.row * LABEL_STEP}" text-anchor="middle">${esc(short(node.name, 6))} ${node.n}</text>
    </g>`;

  const bNodes = placeNodes(bTop, tierOf, TOP_Y);
  const aNodes = placeNodes(aTop, tierOf, BOTTOM_Y);
  const axis = TIER_COLUMNS.map((c, i) => `
    <line class="vf-col" x1="${colX(i)}" y1="${TOP_Y}" x2="${colX(i)}" y2="${BOTTOM_Y}"></line>
    <text class="vf-col-label" x="${colX(i)}" y="${H - 4}" text-anchor="middle">${esc(c.label)}</text>`).join('');

  const svg = `
    <svg class="vf-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(venue)} 전후 공연장 흐름: 위는 전에 선 곳, 아래는 뒤에 간 곳, 가로는 체급">
      ${axis}
      ${bNodes.map(n => arc(n, 'vf-before')).join('')}
      ${aNodes.map(n => arc(n, 'vf-after')).join('')}
      ${bNodes.map(n => label(n, true)).join('')}
      ${aNodes.map(n => label(n, false)).join('')}
      <g class="vf-here"><circle cx="${cx.toFixed(1)}" cy="${MID_Y}" r="8"></circle>
        <text x="${cx.toFixed(1)}" y="${MID_Y + 4}" dx="14">${esc(short(venue, 12))}</text></g>
    </svg>`;
  return { kind: 'svg', html: svg };
}
