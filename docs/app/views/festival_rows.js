/**
 * 페스티벌 회차표 한 줄·종류 꼬리표·비율 글자 — 목록(festivals.js)과 페스티벌 페이지(festival_page.js)가 같이 씀.
 * 브라우저 전용 모듈(DuckDB)을 불러오지 않아 node 테스트로 검사한다 (tests/js/festival_rows.test.mjs).
 */
import { escapeHtml, fmtInt, gradeBadgeHtml, naCell } from '../ui.js';

export function pctText(v) {
  return v === null || v === undefined ? '—' : `${Math.round(Number(v) * 100)}%`;
}

/** 페스티벌 종류 꼬리표: 정답 표(수상·선정) · 공식 라인업 표(config/festival_lineups.json) · 신호 */
export function festivalKindLabel(kind) {
  if (kind === 'outcome') return '수상·선정 프로그램';
  if (kind === 'lineup') return '공식 라인업';
  return '신호(라인업)';
}

/** 회차표 한 줄: 회차 · 라인업(국내 팀, 공식 전체 수) · 새 팀 · 첫 페스티벌 · 그 뒤 정답 */
export function editionRowHtml(year, e) {
  const winners = Array.isArray(e.later_winners) ? e.later_winners : [];
  const names = winners.slice(0, 4).map(w => `<a href="#/team/${encodeURIComponent(w.team_key)}">${escapeHtml(w.name)}</a> ${gradeBadgeHtml(w.grade)}`).join(' · ');
  return `
    <tr>
      <td class="mono" data-label="회차">${escapeHtml(year)}${e.upcoming ? ' <span class="venue-upcoming-pill">예정</span>' : ''}</td>
      <td class="num" data-label="라인업">${fmtInt(e.lineup)}팀${e.official_lineup ? ` <span class="small muted num-suffix is-wide" title="공식 라인업 전체(해외 팀 포함) — 라인업 칸은 그중 국내 팀">/ 공식 ${fmtInt(e.official_lineup)}</span>` : ' <span class="num-suffix is-wide" aria-hidden="true"></span>'}</td>
      <td class="num" data-label="새 팀">${pctText(e.new_to_festival_share)}</td>
      <td class="num" data-label="첫 페스티벌">${pctText(e.first_festival_share)}</td>
      <td data-label="그 뒤 수상·선정">${e.upcoming ? naCell('아직 열리지 않은 회차라 세지 않습니다', { label: '—' }) : `<span><strong>${fmtInt(e.later_winners_total || 0)}팀</strong>${names ? ` <span class="small">${names}</span>` : ''}${winners.length > 4 ? ` <span class="small muted">외 ${fmtInt(winners.length - 4)}</span>` : ''}</span>`}</td>
    </tr>`;
}

function _dayRange(dates) {
  if (!Array.isArray(dates) || !dates.length) return '';
  const md = d => String(d).slice(5).replace('-', '/');
  return dates.length > 1 ? `${md(dates[0])}~${md(dates[dates.length - 1])}` : md(dates[0]);
}

/**
 * 날짜·장소만 있는 페스티벌 표 (페스티벌라이프 목록 — 라인업은 포스터 그림이라 팀이 없음).
 * 줄 = 페스티벌 · 회차 연도(누르면 근거 글) · 최근 회차 날짜 · 장소. 라인업 페스티벌과 연결되면 이름이 그 페이지로.
 * @param {{name: string, festival: string|null, editions: Object<string, {dates: string[], venue: string, url: string}>}[]} rows
 */
export function catalogTableHtml(rows) {
  if (!Array.isArray(rows) || !rows.length) return '';
  const body = rows.map((r) => {
    const eds = Object.entries(r.editions || {}).sort((a, b) => a[0].localeCompare(b[0]));
    const [lastYear, last] = eds[eds.length - 1] || ['', {}];
    const name = r.festival
      ? `<a href="#/festival/${encodeURIComponent(r.festival)}"><strong>${escapeHtml(r.name)}</strong></a>`
      : `<strong>${escapeHtml(r.name)}</strong>`;
    const years = eds.map(([y, e]) => (e.url
      ? `<a class="fest-cat-year" href="${escapeHtml(e.url)}" target="_blank" rel="noopener noreferrer" title="${escapeHtml(_dayRange(e.dates) || y)} · 근거 글(페스티벌라이프)">${escapeHtml(y)}</a>`
      : escapeHtml(y))).join(' ');
    return `
    <tr>
      <td class="col-name" data-label="페스티벌">${name}</td>
      <td data-label="회차">${years}</td>
      <td class="mono col-fit" data-label="최근 날짜">${escapeHtml(lastYear)} ${escapeHtml(_dayRange(last.dates))}</td>
      <td data-label="장소">${escapeHtml(last.venue || '—')}</td>
    </tr>`;
  }).join('');
  return `
    <div class="table-wrap">
      <table class="data-table stack-table fest-catalog-table">
        <thead><tr><th>페스티벌</th><th>회차 (누르면 근거 글)</th><th class="col-fit">최근 날짜</th><th>장소</th></tr></thead>
        <tbody>${body}</tbody>
      </table>
    </div>`;
}
