/**
 * 도시 목록 #/cities (정보 구조 v2 묶음 E) — 도시 카드(공연장 수 · 공연 날짜 · 첫 무대 신인 · 우리 기록 많음/적음 ·
 * 최근 12개월 월별 막대) → 누르면 도시 페이지 #/city/<이름> (views/city_page.js).
 * 맨 위: 시·도 지도(components/region_map.js — 색 농도·숫자·말풍선, 누르면 확대돼 공연장 점) + 옆에 시·도 표.
 * 자료: city_profiles.json · venue_profiles.json(좌표) · app/data/kr_sido.json(경계). 청취자(스트리밍 지역) 자료는 없다.
 */
import { appState } from '../state.js';
import { loadVenueProfiles } from '../db.js';
import { loadCityProfiles } from '../db_venue.js';
import { escapeHtml, fmtInt, fmtNum, naCell } from '../ui.js';
import { aggregateBySido, sidoTableHtml } from '../components/region_map.js';
import {
  cityMonthBarsHtml, loadKrMap, LOW_COVERAGE_NIGHTS, mountCityRegionMap,
} from './city_page.js';

let mapMetric = 'venues'; // 고른 색 기준을 다시 들어와도 기억

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
        <p class="small muted place-card-sub">${escapeHtml(flowTxt)}${c.later_winners_total ? ` · 나중에 상 받은 팀 ${fmtInt(c.later_winners_total)}팀` : ''}</p>
      </a>
    </li>`;
}

/** @param {HTMLElement} host */
export async function renderCitiesList(host) {
  const [cp, vp, geo] = await Promise.all([loadCityProfiles(), loadVenueProfiles(), loadKrMap()]);
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
    <section class="block rm-wrap" aria-label="시·도 지도">
      <div class="rm-wrap-map" id="citiesRegionMap"></div>
      <div class="rm-wrap-table" id="citiesSidoTable"></div>
    </section>
    ${f.local_start ? `<p class="place-lead">지방에서 첫 무대를 연 <strong>${fmtInt(f.local_start)}팀</strong> 중 <strong>${fmtInt(f.reached_seoul || 0)}팀</strong>이 서울 무대에 올랐습니다(걸린 기간 중앙값 ${f.median_months !== null && f.median_months !== undefined ? `${fmtNum(f.median_months, 1)}개월` : '—'}).</p>` : ''}
    <ul class="place-cards">${cities.map(([n, c]) => cardHtml(n, c, asOf, f)).join('')}</ul>
    <p class="small muted place-evidence">기록 많음/적음 = 공연 날짜 ${fmtInt(LOW_COVERAGE_NIGHTS)}일 기준 · 도시 = 우리가 정리한 공연장 목록의 도시 · 수집 상태는 <a href="#/verify/quality">검증 › 데이터 품질</a></p>`;
  wireRegionMap(host, { geo, cp, vp, asOf });
}

/** 지도 + 시·도 표: 단추를 바꾸면 표 정렬도, 표 줄을 누르면 지도가 확대 */
function wireRegionMap(host, { geo, cp, vp, asOf }) {
  const tableEl = host.querySelector('#citiesSidoTable');
  const { bySido } = aggregateBySido(cp.cities, asOf);
  const drawTable = (sido = null) => {
    if (!tableEl || !geo) return;
    tableEl.innerHTML = sidoTableHtml({ geo, bySido, metric: mapMetric });
    tableEl.querySelectorAll('[data-sido-row]').forEach(b => b.closest('tr').classList.toggle('is-on', b.dataset.sidoRow === sido));
  };
  const map = mountCityRegionMap(host.querySelector('#citiesRegionMap'), {
    geo, cp, vp, asOf, metric: mapMetric,
    onMetric: m => { mapMetric = m; drawTable(map?.sido || null); },
    onZoom: sido => drawTable(sido),
  });
  drawTable();
  tableEl?.addEventListener('click', e => {
    const b = e.target.closest('[data-sido-row]');
    if (!b || !map) return;
    map.zoomTo(b.dataset.sidoRow);
    host.querySelector('#citiesRegionMap')?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  });
}
