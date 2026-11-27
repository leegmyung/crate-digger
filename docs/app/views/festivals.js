/**
 * 페스티벌 목록 #/festivals (정보 구조 v2 묶음 E) — 페스티벌 카드(종류 · 회차 연도 · 최근 라인업 규모 · 누적 팀 ·
 * 새 팀 비율 · 그 뒤 정답 팀 · 같은 집안 ⚠️) → 누르면 페스티벌 페이지 #/festival/<키> (views/festival_page.js).
 * 회차표 한 줄(editionRowHtml)은 페스티벌 페이지도 같이 쓴다.
 * 자료: festival_profiles.json
 */
import { loadFestivalProfiles } from '../db_venue.js';
import { escapeHtml, fmtInt, gradeBadgeHtml, naCell } from '../ui.js';

export function pctText(v) {
  return v === null || v === undefined ? '—' : `${Math.round(Number(v) * 100)}%`;
}

/** 회차표 한 줄: 회차 · 라인업 · 새 팀 · 첫 페스티벌 · 그 뒤 정답 */
export function editionRowHtml(year, e) {
  const winners = Array.isArray(e.later_winners) ? e.later_winners : [];
  const names = winners.slice(0, 4).map(w => `<a href="#/team/${encodeURIComponent(w.team_key)}">${escapeHtml(w.name)}</a> ${gradeBadgeHtml(w.grade)}`).join(' · ');
  return `
    <tr>
      <td class="mono" data-label="회차">${escapeHtml(year)}${e.upcoming ? ' <span class="venue-upcoming-pill">예정</span>' : ''}</td>
      <td class="num" data-label="라인업">${fmtInt(e.lineup)}팀</td>
      <td class="num" data-label="새 팀">${pctText(e.new_to_festival_share)}</td>
      <td class="num" data-label="첫 페스티벌">${pctText(e.first_festival_share)}</td>
      <td data-label="그 뒤 정답">${e.upcoming ? naCell('아직 열리지 않은 회차라 세지 않습니다', { label: '—' }) : `<span><strong>${fmtInt(e.later_winners_total || 0)}팀</strong>${names ? ` <span class="small">${names}</span>` : ''}${winners.length > 4 ? ` <span class="small muted">외 ${fmtInt(winners.length - 4)}</span>` : ''}</span>`}</td>
    </tr>`;
}

function cardHtml(key, f) {
  const eds = Object.entries(f.editions || {}).sort((a, b) => a[0].localeCompare(b[0]));
  const latest = eds[eds.length - 1]?.[1] || null;
  const years = eds.length ? (eds.length > 1 ? `${eds[0][0]}~${eds[eds.length - 1][0]}` : eds[0][0]) : '회차 없음';
  const winners = eds.reduce((n, [, e]) => n + (e.upcoming ? 0 : Number(e.later_winners_total) || 0), 0);
  const sameHouse = f.same_house?.is_outcome || (f.same_house?.outcome_programs || []).length;
  return `
    <li class="place-card">
      <a class="place-card-link" href="#/festival/${encodeURIComponent(key)}">
        <div class="place-card-head">
          <strong class="place-card-name">${escapeHtml(f.label || key)}</strong>
          <span class="place-badge">${f.kind === 'outcome' ? '정답 프로그램' : '신호'}</span>
        </div>
        <p class="small muted place-card-sub">${escapeHtml(years)} · 회차 ${fmtInt(eds.length)}개 · 누적 ${fmtInt(f.teams_total || 0)}팀</p>
        <div class="place-card-kpis small">
          <span>최근 라인업 <strong>${latest ? fmtInt(latest.lineup) : '—'}</strong>팀</span>
          <span>새 팀 <strong>${latest ? pctText(latest.new_to_festival_share) : '—'}</strong></span>
          <span>그 뒤 정답 <strong>${fmtInt(winners)}</strong>팀</span>
        </div>
        ${sameHouse ? '<p class="small place-card-warn">⚠️ 같은 집안 정답은 \'그 뒤 정답\'에서 뺌</p>' : ''}
      </a>
    </li>`;
}

/** @param {HTMLElement} host */
export async function renderFestivalsList(host) {
  const fp = await loadFestivalProfiles();
  if (!fp?.festivals) {
    host.innerHTML = `<section class="block">${naCell('페스티벌 프로필(festival_profiles.json)이 아직 없습니다', { block: true })}</section>`;
    return;
  }
  const items = Object.entries(fp.festivals)
    .sort((a, b) => (b[1].teams_total || 0) - (a[1].teams_total || 0));
  host.innerHTML = `
    <div class="vl-page-head">
      <div>
        <h1 class="vl-title">페스티벌</h1>
        <p class="small muted">${fmtInt(items.length)}곳 · 누적 출연 팀 많은 순${fp.as_of ? ` · 기준 ${escapeHtml(fp.as_of)}` : ''}</p>
      </div>
    </div>
    <ul class="place-cards">${items.map(([k, f]) => cardHtml(k, f)).join('')}</ul>
    <p class="small muted place-evidence">새 팀 = 이 페스티벌 앞선 회차(우리 데이터)에 없던 팀 · 그 뒤 정답 = 회차 날짜보다 뒤에 받은 센 정답(같은 집안 정답은 뺌) · 라인업은 우리가 모은 기록만이라 실제보다 적을 수 있음</p>`;
}
