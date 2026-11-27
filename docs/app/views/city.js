/**
 * 도시 목록 #/cities (정보 구조 v2 묶음 E) — 도시 카드(공연장 수 · 공연 날짜 · 첫 무대 신인 · 우리 기록 많음/적음 ·
 * 최근 12개월 월별 막대) → 누르면 도시 페이지 #/city/<이름> (views/city_page.js).
 * 자료: city_profiles.json. 청취자(스트리밍 지역) 자료는 없다.
 */
import { appState } from '../state.js';
import { loadCityProfiles } from '../db_venue.js';
import { escapeHtml, fmtInt, fmtNum, naCell } from '../ui.js';
import { cityMonthBarsHtml, LOW_COVERAGE_NIGHTS } from './city_page.js';

function cardHtml(name, c, asOf, flow) {
  const low = (c.nights || 0) < LOW_COVERAGE_NIGHTS;
  const f = flow?.by_first_city?.[name];
  const flowTxt = name === '서울'
    ? '지방에서 올라오는 도착지'
    : (f && f.teams ? `첫 무대 ${fmtInt(f.teams)}팀 중 ${fmtInt(f.reached)}팀 서울로` : '서울 이동 기록 없음');
  return `
    <li class="place-card">
      <a class="place-card-link" href="#/city/${encodeURIComponent(name)}">
        <div class="place-card-head">
          <strong class="place-card-name">${escapeHtml(name)}</strong>
          <span class="place-badge${low ? ' is-low' : ''}">${low ? '기록 적음' : '기록 많음'}</span>
        </div>
        ${cityMonthBarsHtml(c.monthly, asOf, 12, 20)}
        <div class="place-card-kpis small">
          <span>공연장 <strong>${fmtInt(c.venues_with_gigs || 0)}</strong>곳</span>
          <span>공연 <strong>${fmtInt(c.nights || 0)}</strong>일</span>
          <span>첫 무대 신인 <strong>${fmtInt(c.first_stage_teams_1y || 0)}</strong>팀<span class="muted">/1년</span></span>
        </div>
        <p class="small muted place-card-sub">${escapeHtml(flowTxt)}${c.later_winners_total ? ` · 나중 정답 ${fmtInt(c.later_winners_total)}팀` : ''}</p>
      </a>
    </li>`;
}

/** @param {HTMLElement} host */
export async function renderCitiesList(host) {
  const cp = await loadCityProfiles();
  if (!cp?.cities) {
    host.innerHTML = `<section class="block">${naCell('도시 프로필(city_profiles.json)이 아직 없습니다', { block: true })}</section>`;
    return;
  }
  const asOf = cp.as_of || appState.dataEnd || '2026-11-28';
  const cities = Object.entries(cp.cities).sort((a, b) => (b[1].nights || 0) - (a[1].nights || 0));
  const f = cp.seoul_flow || {};
  host.innerHTML = `
    <div class="vl-page-head">
      <div>
        <h1 class="vl-title">도시</h1>
        <p class="small muted">${fmtInt(cities.length)}곳 · 공연 날짜 많은 순 · 기준 ${escapeHtml(asOf)} · 청취자(스트리밍 지역) 자료는 없어 공연 기록만으로 봅니다</p>
      </div>
    </div>
    ${f.local_start ? `<p class="place-lead">지방에서 첫 무대를 연 <strong>${fmtInt(f.local_start)}팀</strong> 중 <strong>${fmtInt(f.reached_seoul || 0)}팀</strong>이 서울 무대에 올랐습니다(걸린 기간 중앙값 ${f.median_months !== null && f.median_months !== undefined ? `${fmtNum(f.median_months, 1)}개월` : '—'}).</p>` : ''}
    <ul class="place-cards">${cities.map(([n, c]) => cardHtml(n, c, asOf, f)).join('')}</ul>
    <p class="small muted place-evidence">기록 많음/적음 = 공연 날짜 ${fmtInt(LOW_COVERAGE_NIGHTS)}일 기준 · 도시 = 공연장 마스터 목록(config/venues_kr.json) · 수집 상태는 <a href="#/verify/quality">검증 › 데이터 품질</a></p>`;
}
