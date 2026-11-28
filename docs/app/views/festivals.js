/**
 * 페스티벌 목록 #/festivals (정보 구조 v2 묶음 E) — 페스티벌 카드(종류 · 회차 연도 · 최근 라인업 규모 · 누적 팀 ·
 * 새 팀 비율 · 그 뒤 정답 팀 · 같은 집안 ⚠️) → 누르면 페스티벌 페이지 #/festival/<키> (views/festival_page.js).
 * 회차표 한 줄(editionRowHtml)은 페스티벌 페이지도 같이 쓴다.
 * 자료: festival_profiles.json
 */
import { loadFestivalProfiles } from '../db_venue.js';
import { escapeHtml, fmtInt, naCell } from '../ui.js';
import { catalogTableHtml, festivalKindLabel, pctText } from './festival_rows.js';

export { editionRowHtml, festivalKindLabel, pctText } from './festival_rows.js';

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
          <span class="place-badge">${festivalKindLabel(f.kind)}</span>
        </div>
        <p class="small muted place-card-sub">${escapeHtml(years)} · 회차 ${fmtInt(eds.length)}개 · 누적 ${fmtInt(f.teams_total || 0)}팀</p>
        <div class="place-card-kpis small">
          <span>최근 라인업 <strong>${latest ? fmtInt(latest.lineup) : '—'}</strong>팀</span>
          <span>새 팀 <strong>${latest ? pctText(latest.new_to_festival_share) : '—'}</strong></span>
          <span>그 뒤 수상·선정 <strong>${fmtInt(winners)}</strong>팀</span>
        </div>
        ${sameHouse ? '<p class="small place-card-warn">⚠️ 같은 주최 수상·선정은 \'그 뒤 수상·선정\'에서 뺌</p>' : ''}
      </a>
    </li>`;
}

/** 날짜·장소만 있는 페스티벌 (페스티벌라이프 목록) — 라인업 팀이 있는 페스티벌과 연결된 줄도 같이 */
function catalogSectionHtml(catalog) {
  const rows = Array.isArray(catalog) ? catalog : [];
  if (!rows.length) return '';
  const only = rows.filter(r => !r.festival).length;
  return `
    <section class="block fest-catalog">
      <div class="block-head"><h2>날짜·장소만 있는 페스티벌</h2><span class="block-meta">${fmtInt(rows.length)}곳 (라인업 팀 없는 곳 ${fmtInt(only)}) · 2021~2026</span></div>
      <p class="small muted">페스티벌라이프 '국내 페스티벌' 글에서 모은 일정·장소예요. 라인업은 포스터 그림이라 팀은 아직 없어요 — 회차 연도를 누르면 근거 글이 열려요.</p>
      ${catalogTableHtml(rows)}
    </section>`;
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
    ${catalogSectionHtml(fp.catalog)}
    <p class="small muted place-evidence">새 팀 = 이 페스티벌 앞선 회차(우리 데이터)에 없던 팀 · 그 뒤 수상·선정 = 회차 날짜보다 뒤에 받은 큰 수상·선정(같은 주최 수상·선정은 뺌) · 라인업은 우리가 모은 기록만이라 실제보다 적을 수 있음</p>`;
}
