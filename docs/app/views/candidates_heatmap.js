/**
 * 2-5: 후보 목록 '색 지도' 보기 — 행 = 팀, 열 = 신호 8개, 칸 = 1~5단계 진하기(--ramp-*), 값 없음 = 회색.
 * 등급: 같은 발굴 단계(장르를 알면 +장르) 이웃 안 백분위(docs/lab/sql/peer_compare.sql)를
 *       components/heat_scale.js 의 경계(상위 10/30/70/90%)로 1~5 로 바꾼다.
 *       이웃 비교에 없는 열(최근 언급·지역 수)이나 이웃 비교에 없는 팀은 '지금 표 안' 백분위를 쓴다.
 */
import { heatLevel, percentRanks } from '../components/heat_scale.js';
import {
  avatarHtml, escapeHtml, fmtInt, INFO_TIPS, infoTip, naCell, playButtonHtml,
} from '../ui.js';

const yesNo = v => (Number(v) > 0 ? '있음' : '없음');

/** 열 정의: raw = 칸에 쓰는 원래 값(없으면 null), peerPct = peer_compare.sql 백분위 칸 */
export const HEAT_COLUMNS = [
  { key: 'branch', label: '신호 갈래', unit: '개', raw: r => r.n_branch, peerPct: 'branch_pct' },
  { key: 'stage', label: '선정 단계', unit: '', raw: r => r.best_stage, peerPct: 'stage_pct' },
  { key: 'venues', label: '최근 2년 공연장 수', unit: '곳', raw: r => r.venues, peerPct: 'venues_pct' },
  { key: 'outlets', label: '발굴 매체', unit: '곳', raw: r => r.outlets, peerPct: 'outlets_pct' },
  { key: 'winner', label: '수상 팀과 같은 무대', unit: '', raw: r => r.peer_winner, peerPct: 'winner_pct', fmt: yesNo },
  { key: 'gigs', label: '1년 공연', unit: '회', raw: r => r.gigs_1y, peerPct: 'gigs_pct' },
  { key: 'recent', label: '최근 90일 언급', unit: '건', raw: r => r.stage_info?.recent_n },
  { key: 'cities', label: '활동 지역 수', unit: '곳', raw: (r, ctx) => ctx.cities.get(r.team_key)?.cities },
];

const VALID_KEYS = new Set(['rank', ...HEAT_COLUMNS.map(c => c.key)]);

function cleanRaw(v) {
  if (v === null || v === undefined || v === '') return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

/**
 * 표 목록(이미 필터·정렬된 후보 행)을 색 지도 행으로 바꾼다. 원본 행은 바꾸지 않는다.
 * @param {object[]} list
 * @param {{ peerByTeam: Map<string, object>, cities: Map<string, object> }} ctx
 */
export function buildHeatRows(list, ctx) {
  const rawByCol = HEAT_COLUMNS.map(col => list.map(r => cleanRaw(col.raw(r, ctx))));
  const listPctByCol = rawByCol.map(vals => percentRanks(vals));
  return list.map((r, i) => {
    const peer = ctx.peerByTeam.get(r.team_key) || null;
    const cells = HEAT_COLUMNS.map((col, ci) => {
      const raw = rawByCol[ci][i];
      if (raw === null) return { key: col.key, raw: null, level: null, basis: '' };
      const peerPct = col.peerPct && peer ? peer[col.peerPct] : null;
      const usePeer = peerPct !== null && peerPct !== undefined;
      const pct = usePeer ? peerPct : listPctByCol[ci][i];
      return { key: col.key, raw, pct, level: heatLevel(pct), basis: usePeer ? 'peer' : 'list' };
    });
    return {
      team_key: r.team_key,
      display_name: r.display_name || r.team_key,
      rank: i + 1,
      peer,
      cells,
    };
  });
}

/** 열 정렬: 등급 → 원래 값 순, 자료 없음은 방향과 상관없이 맨 뒤. 'rank' 는 표 순서. */
export function sortHeatRows(rows, sort) {
  const col = VALID_KEYS.has(sort?.col) ? sort.col : 'rank';
  const mult = sort?.dir === 'asc' ? 1 : -1;
  if (col === 'rank') {
    return [...rows].sort((a, b) => (a.rank - b.rank) * (sort?.dir === 'desc' ? -1 : 1));
  }
  const ci = HEAT_COLUMNS.findIndex(c => c.key === col);
  return [...rows].sort((a, b) => {
    const ca = a.cells[ci];
    const cb = b.cells[ci];
    if (ca.level === null && cb.level === null) return a.rank - b.rank;
    if (ca.level === null) return 1;
    if (cb.level === null) return -1;
    if (ca.level !== cb.level) return (ca.level - cb.level) * mult;
    if (ca.raw !== cb.raw) return (ca.raw - cb.raw) * mult;
    return a.rank - b.rank;
  });
}

function cellTitle(col, cell, peer) {
  const valTxt = col.fmt ? col.fmt(cell.raw) : `${fmtInt(cell.raw)}${col.unit}`;
  const topPct = Math.max(1, Math.round((1 - cell.pct) * 100));
  const where = cell.basis === 'peer' && peer
    ? `이웃(${peer.peer_scope} ${fmtInt(peer.peer_n)}팀) 안 상위 ${topPct}%`
    : `지금 표 안 상위 ${topPct}%`;
  return `${col.label}: ${valTxt} · ${where} · ${cell.level}단계`;
}

function renderCell(col, cell, peer) {
  if (cell.level === null) {
    const reason = col.key === 'cities'
      ? '팀별 활동 지역 자료가 아직 없습니다'
      : `${col.label} 기록이 없습니다`;
    return `<td class="heat-cell is-na">${naCell(reason)}</td>`;
  }
  const txt = col.fmt ? col.fmt(cell.raw) : fmtInt(cell.raw);
  const title = cellTitle(col, cell, peer);
  return `<td class="heat-cell lv${cell.level}" title="${escapeHtml(title)}" aria-label="${escapeHtml(title)}">${escapeHtml(txt)}</td>`;
}

function renderHead(allRows, sort) {
  const total = allRows.length;
  const ths = HEAT_COLUMNS.map((col, ci) => {
    const n = allRows.filter(r => r.cells[ci].level !== null).length;
    const active = sort.col === col.key;
    const ariaSort = active ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none';
    const arrow = active ? (sort.dir === 'asc' ? '▲' : '▼') : '';
    return `<th class="heat-th sortable" data-heat-sort="${col.key}" tabindex="0" aria-sort="${ariaSort}" scope="col">
      <span class="heat-th-lbl">${escapeHtml(col.label)}${arrow ? `<span class="heat-th-arrow" aria-hidden="true">${arrow}</span>` : ''}</span>
      <span class="th-coverage">${fmtInt(n)}/${fmtInt(total)}팀</span>
    </th>`;
  }).join('');
  const rankActive = sort.col === 'rank';
  const rankAria = rankActive ? (sort.dir === 'desc' ? 'descending' : 'ascending') : 'none';
  return `<thead><tr>
    <th class="heat-team-th sortable" data-heat-sort="rank" tabindex="0" aria-sort="${rankAria}" scope="col">팀 <span class="muted small">(순위)</span></th>
    ${ths}
  </tr></thead>`;
}

/**
 * @param {ReturnType<typeof buildHeatRows>} allRows 필터를 거친 전체 행(칸별 팀 수 계산용)
 * @param {{ sort: { col: string, dir: string }, limit: number, loading?: boolean, error?: string }} opts
 */
export function renderHeatmapHtml(allRows, { sort, limit, loading = false, error = '' }) {
  const status = loading
    ? '<span class="small muted">이웃 비교 계산 중…</span>'
    : (error ? '<span class="small muted">이웃 비교를 못 불러와 표 안 비교로 보여 줍니다</span>' : '');
  const legend = `
    <div class="heat-legend">
      <span class="heat-legend-lbl">진하기 = 같은 발굴 단계(장르를 알면 +장르) 이웃 안 위치${infoTip('색 지도 읽는 법', INFO_TIPS.heatmap, { compact: true })}</span>
      <span class="heat-scale" aria-label="1단계 낮음부터 5단계 높음">
        <span class="heat-scale-end">낮음</span>
        ${[1, 2, 3, 4, 5].map(l => `<span class="heat-chip lv${l}">${l}</span>`).join('')}
        <span class="heat-scale-end">높음</span>
      </span>
      <span class="heat-legend-na">${naCell('자료 없음은 0이 아니라 기록이 없다는 뜻입니다')} 자료 없음</span>
      ${status}
    </div>`;
  const sorted = sortHeatRows(allRows, sort).slice(0, limit);
  const body = sorted.map(r => `
    <tr class="clickable" tabindex="0" data-nav-row="1" data-team-key="${escapeHtml(r.team_key)}">
      <th scope="row" class="heat-team"><span class="heat-rank">${fmtInt(r.rank)}</span>${avatarHtml(r.team_key, r.display_name, 22, { shape: 'circle' })}<span class="heat-name" title="${escapeHtml(r.display_name)}">${escapeHtml(r.display_name)}</span>${playButtonHtml(r.team_key, r.display_name, { variant: 'icon' })}</th>
      ${HEAT_COLUMNS.map((col, ci) => renderCell(col, r.cells[ci], r.peer)).join('')}
    </tr>`).join('');
  return `${legend}
    <div class="table-wrap heat-wrap">
      <table class="heat-table" aria-label="후보 색 지도">
        ${renderHead(allRows, sort)}
        <tbody>${body}</tbody>
      </table>
    </div>`;
}

/** 다음 정렬 상태(같은 열 다시 누르면 방향 바꿈, 새 열은 높은 쪽부터·순위는 1위부터) */
export function nextHeatSort(cur, col) {
  if (!VALID_KEYS.has(col)) return cur;
  if (cur.col === col) return { col, dir: cur.dir === 'desc' ? 'asc' : 'desc' };
  return { col, dir: col === 'rank' ? 'asc' : 'desc' };
}
