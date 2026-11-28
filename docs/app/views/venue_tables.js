/**
 * 4-2 공연장 상세 '출연 팀' 표 + '공연' 표 — 정렬 · CSV 내려받기 · 375px 에선 카드형 줄.
 * 출연 팀: 후보 점수(순위) · 발굴 단계 · 정답 여부 · 이 무대 첫 출연일 · 공연 수
 * 공연: 날짜 · 출연진 · 출처(인디스트릿·상상마당·인디고·인스타 등)
 */
import {
  avatarHtml, escapeHtml, fmtInt, fmtNum, gradeBadgeHtml, naCell, playButtonHtml, renderTableCsvBtn, SOURCE_LABELS,
  STAGE_META, stageBadgeHtml, triggerTableCsvExport, updateSortHeaders, wireAvatarFallbacks,
} from '../ui.js';

const TEAMS_FIRST = 20;
const SHOWS_FIRST = 15;

function teamSortValue(r, col) {
  switch (col) {
    case 'name': return r.display_name;
    case 'first_here': return r.first_here || '';
    case 'last_here': return r.last_here || '';
    case 'score': return r.score ?? -1;
    case 'stage': return r.stage ?? -1;
    case 'grade': return { S: 3, A: 2, B: 1 }[r.grade] || 0;
    default: return r.gigs;
  }
}

function sortBy(rows, col, dir, valueFn) {
  const mult = dir === 'asc' ? 1 : -1;
  return [...rows].sort((a, b) => {
    const va = valueFn(a, col);
    const vb = valueFn(b, col);
    if (va === vb) return (b.gigs || 0) - (a.gigs || 0);
    return (typeof va === 'string' ? va.localeCompare(vb) : va - vb) * mult;
  });
}

function outcomeCell(r) {
  if (!r.grade) return naCell('수상·선정 정답 기록이 없습니다', { label: '없음' });
  const after = r.first_outcome && r.first_here && r.first_outcome > r.first_here;
  return `<span class="venue-team-outcome">${gradeBadgeHtml(r.grade)}<span class="small muted">${escapeHtml(r.first_outcome || '')}${after ? ' · 이 무대 뒤' : ''}</span></span>`;
}

/** 출연 팀 표 한 줄 — 사진·▶ 바로 듣기 포함 (다른 팀 목록과 같은 모양, docs/ui_review_2026-11-28.md) */
export function venueTeamRowHtml(r) {
  const name = r.display_name || r.team_key;
  return `
    <tr>
      <td data-label="팀"><span class="team-cell-inline">${avatarHtml(r.team_key, name, 28, { shape: 'circle', genre: r.primary_genre })}<a href="#/team/${encodeURIComponent(r.team_key)}"><strong>${escapeHtml(name)}</strong></a>${playButtonHtml(r.team_key, name, { variant: 'icon' })}</span>${r.primary_genre ? ` <span class="small muted">${escapeHtml(r.primary_genre)}</span>` : ''}</td>
      <td class="num" data-label="공연 수">${fmtInt(r.gigs)}회${r.upcoming ? ` <span class="small muted">+예정 ${fmtInt(r.upcoming)}</span>` : ''}</td>
      <td class="mono nowrap" data-label="첫 출연">${escapeHtml(r.first_here || '—')}</td>
      <td class="mono nowrap" data-label="마지막">${escapeHtml(r.last_here || '—')}</td>
      <td class="num" data-label="후보 점수">${r.score !== null && r.score !== undefined ? `${fmtNum(r.score, 2)} <span class="small muted">#${fmtInt(r.rank)}</span>` : naCell('지금 후보 상위 300팀 밖입니다', { label: '—' })}</td>
      <td data-label="발굴 단계">${r.stage !== null && r.stage !== undefined ? stageBadgeHtml(r.stage, { short: true }) : naCell('발굴 단계를 계산하지 않은 팀입니다', { label: '—' })}</td>
      <td data-label="정답">${outcomeCell(r)}</td>
    </tr>`;
}

function sourceLabels(teams) {
  return [...new Set(teams.map(t => t.source).filter(Boolean))].map(s => SOURCE_LABELS[s] || s).join(' · ');
}

function showRowHtml(g) {
  return `
    <tr class="${g.isUpcoming ? 'is-upcoming' : ''}">
      <td class="mono nowrap" data-label="날짜">${escapeHtml(g.date)}${g.isUpcoming ? ' <span class="venue-upcoming-pill">예정</span>' : ''}</td>
      <td data-label="출연진">${g.teams.map(t => `<a class="venue-show-team-link" href="#/team/${encodeURIComponent(t.team_key)}">${escapeHtml(t.display_name)}</a>`).join(' · ')} <span class="small muted">(${fmtInt(g.teams.length)}팀)</span></td>
      <td data-label="출처">${escapeHtml(sourceLabels(g.teams) || '—')}</td>
    </tr>`;
}

/**
 * @param {HTMLElement} root 공연장 화면
 * @param {{ venue: string, asOf: string, teams: object[], showGroups: object[],
 *           candByKey: Map<string,{score:number, rank:number}>, stageByTeam: Map<string, number> }} ctx
 */
export function mountVenueTables(root, ctx) {
  const teams = ctx.teams.map(t => ({
    ...t,
    score: ctx.candByKey.get(t.team_key)?.score ?? null,
    rank: ctx.candByKey.get(t.team_key)?.rank ?? null,
    stage: ctx.stageByTeam.has(t.team_key) ? ctx.stageByTeam.get(t.team_key) : null,
  }));
  const safeName = ctx.venue.replace(/[^a-zA-Z0-9가-힣_-]+/g, '_');
  let teamSort = { col: 'gigs', dir: 'desc' };
  let teamLimit = TEAMS_FIRST;
  let showDir = 'desc';
  let showLimit = SHOWS_FIRST;

  const teamsCsv = () => ({
    filename: `crate_digger_venue_teams_${safeName}_${ctx.asOf}.csv`,
    headers: ['팀', '공연 수', '예정', '첫 출연', '마지막', '후보 점수', '후보 순위', '발굴 단계', '정답 등급', '첫 정답일'],
    rows: sortBy(teams, teamSort.col, teamSort.dir, teamSortValue).map(r => [
      r.display_name, r.gigs, r.upcoming, r.first_here, r.last_here,
      r.score ?? '', r.rank ?? '', r.stage !== null ? (STAGE_META[r.stage]?.label || r.stage) : '', r.grade, r.first_outcome,
    ]),
  });
  const showsCsv = () => ({
    filename: `crate_digger_venue_shows_${safeName}_${ctx.asOf}.csv`,
    headers: ['날짜', '예정', '출연 팀 수', '출연진', '출처'],
    rows: ctx.showGroups.map(g => [g.date, g.isUpcoming ? '예정' : '', g.teams.length, g.teams.map(t => t.display_name).join(' / '), sourceLabels(g.teams)]),
  });

  function paintTeams() {
    const el = root.querySelector('#venueTeamsBlock');
    if (!el) return;
    const sorted = sortBy(teams, teamSort.col, teamSort.dir, teamSortValue);
    const shown = sorted.slice(0, teamLimit);
    const th = (col, label, cls = '') => `<th class="sortable ${cls}" data-vt-sort="${col}" tabindex="0">${label}</th>`;
    el.innerHTML = `
      <div class="block-head">
        <div><h2>출연 팀</h2><span class="block-meta">이 무대에 선 ${fmtInt(teams.length)}팀 · 머리줄을 누르면 정렬</span></div>
        ${teams.length ? `<div class="block-head-actions">${renderTableCsvBtn('btnVenueTeamsCsv', 'CSV 내려받기')}</div>` : ''}
      </div>
      ${teams.length ? `
        <div class="table-wrap">
          <table class="data-table stack-table venue-teams-table" id="venueTeamsTable">
            <thead><tr>${th('name', '팀')}${th('gigs', '공연 수', 'num')}${th('first_here', '첫 출연')}${th('last_here', '마지막')}${th('score', '후보 점수', 'num')}${th('stage', '발굴 단계')}${th('grade', '정답')}</tr></thead>
            <tbody>${shown.map(venueTeamRowHtml).join('')}</tbody>
          </table>
        </div>
        ${sorted.length > shown.length ? `<div class="more-row"><span>${fmtInt(shown.length)} / ${fmtInt(sorted.length)}팀</span><button type="button" class="btn btn-sm" data-vt-more="1">20팀 더 보기</button></div>` : ''}
      ` : '<p class="muted small" style="margin:0;">이 공연장의 출연 기록이 없습니다.</p>'}`;
    updateSortHeaders(el.querySelector('#venueTeamsTable'), teamSort.col, teamSort.dir, 'vtSort');
    wireAvatarFallbacks(el);
  }

  function paintShows() {
    const el = root.querySelector('#venueRecentShowsBlock');
    if (!el) return;
    const sorted = [...ctx.showGroups].sort((a, b) => (showDir === 'asc' ? a.date.localeCompare(b.date) : b.date.localeCompare(a.date)));
    const shown = sorted.slice(0, showLimit);
    el.innerHTML = `
      <div class="block-head">
        <div><h2>공연</h2><span class="block-meta">${ctx.totalNights && ctx.totalNights > sorted.length ? `최근 ${fmtInt(sorted.length)}일 표시 (전체 ${fmtInt(ctx.totalNights)}일 중 — 오래된 기록은 CSV에도 빠짐)` : `공연 날짜 ${fmtInt(sorted.length)}일`} · 팀 이름을 누르면 팀 상세로</span></div>
        ${sorted.length ? `<div class="block-head-actions">${renderTableCsvBtn('btnVenueShowsCsv', 'CSV 내려받기')}</div>` : ''}
      </div>
      ${sorted.length ? `
        <div class="table-wrap">
          <table class="data-table stack-table venue-shows-table" id="venueShowsTable">
            <thead><tr><th class="sortable" data-vs-sort="date" tabindex="0">날짜</th><th>출연진</th><th>출처</th></tr></thead>
            <tbody>${shown.map(showRowHtml).join('')}</tbody>
          </table>
        </div>
        ${sorted.length > shown.length ? `<div class="more-row"><span>${fmtInt(shown.length)} / ${fmtInt(sorted.length)}일</span><button type="button" class="btn btn-sm" data-vs-more="1">20일 더 보기</button></div>` : ''}
      ` : '<p class="muted small" style="margin:0;">현재 데이터에 이 공연장의 공연 기록이 없습니다.</p>'}`;
    updateSortHeaders(el.querySelector('#venueShowsTable'), 'date', showDir, 'vsSort');
  }

  const onTeams = (e) => {
    const th = e.target.closest('[data-vt-sort]');
    if (th) {
      const col = th.dataset.vtSort;
      teamSort = teamSort.col === col
        ? { col, dir: teamSort.dir === 'desc' ? 'asc' : 'desc' }
        : { col, dir: col === 'name' || col === 'first_here' ? 'asc' : 'desc' };
      paintTeams();
      root.querySelector(`[data-vt-sort="${col}"]`)?.focus();
      return;
    }
    if (e.target.closest('[data-vt-more]')) { teamLimit += 20; paintTeams(); return; }
    if (e.target.closest('#btnVenueTeamsCsv')) triggerTableCsvExport(teamsCsv());
  };
  const onShows = (e) => {
    if (e.target.closest('[data-vs-sort]')) {
      showDir = showDir === 'desc' ? 'asc' : 'desc';
      paintShows();
      root.querySelector('[data-vs-sort]')?.focus();
      return;
    }
    if (e.target.closest('[data-vs-more]')) { showLimit += 20; paintShows(); return; }
    if (e.target.closest('#btnVenueShowsCsv')) triggerTableCsvExport(showsCsv());
  };
  const keyToClick = handler => (e) => {
    if ((e.key === 'Enter' || e.key === ' ') && e.target.matches('th.sortable')) {
      e.preventDefault();
      handler(e);
    }
  };
  const teamsEl = root.querySelector('#venueTeamsBlock');
  const showsEl = root.querySelector('#venueRecentShowsBlock');
  teamsEl?.addEventListener('click', onTeams);
  teamsEl?.addEventListener('keydown', keyToClick(onTeams));
  showsEl?.addEventListener('click', onShows);
  showsEl?.addEventListener('keydown', keyToClick(onShows));
  paintTeams();
  paintShows();
  return { teamsCsv, showsCsv };
}
