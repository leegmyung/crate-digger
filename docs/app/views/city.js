/**
 * 4-5 도시 탭 — 도시 고르기 → 이 도시에서 최근 3개월 첫 무대를 연 신인 · 이 도시가 활동 도시인 후보 ·
 * 다가오는 공연 · 지방 → 서울 흐름 · 자주 쓰인 공연장 · 나중에 상 받은 팀.
 * 자료: city_profiles.json · team_cities.csv · venue_profiles.json(공연장 → 도시). 청취자(스트리밍 지역) 자료는 없다.
 */
import { appState, syncHash } from '../state.js';
import {
  ensureTeamCitiesLoaded, loadVenueProfiles, queryCandidates, queryUpcomingGigs,
} from '../db.js';
import { loadCityProfiles, queryCityFirstStageTeams } from '../db_venue.js';
import { escapeHtml, fmtInt, fmtNum, formatNextGigText, gradeBadgeHtml, naCell } from '../ui.js';

const RECENT_DAYS = 90;
const UPCOMING_DAYS = 30;
const LOW_COVERAGE_NIGHTS = 100; // 공연 날짜가 이보다 적으면 '우리 기록 적음'
const LIST_MAX = 12;

function teamLink(key, name) {
  return `<a href="#/team/${encodeURIComponent(key)}">${escapeHtml(name || key)}</a>`;
}

function listOrEmpty(items, emptyText, render) {
  if (!items.length) return `<p class="small muted" style="margin:0;">${escapeHtml(emptyText)}</p>`;
  const shown = items.slice(0, LIST_MAX);
  const more = items.length - shown.length;
  return `<ul class="city-list">${shown.map(render).join('')}</ul>${more > 0 ? `<p class="small muted">외 ${fmtInt(more)}건</p>` : ''}`;
}

function flowHtml(cp, city) {
  const f = cp.seoul_flow || {};
  if (city === '서울') {
    return `<p>지방에서 첫 무대를 연 <strong>${fmtInt(f.local_start || 0)}팀</strong> 중 <strong>${fmtInt(f.reached_seoul || 0)}팀</strong>이 서울 무대에 올랐고, 걸린 기간 중앙값은 <strong>${f.median_months ?? '—'}개월</strong>입니다.</p>`;
  }
  const c = f.by_first_city?.[city];
  if (!c) return naCell('이 도시에서 첫 무대를 연 팀의 서울 이동 기록이 없습니다', { block: true });
  const pct = c.teams ? Math.round((c.reached / c.teams) * 100) : 0;
  return `<p>${escapeHtml(city)}에서 첫 무대를 연 <strong>${fmtInt(c.teams)}팀</strong> 중 <strong>${fmtInt(c.reached)}팀(${pct}%)</strong>이 서울 무대에 올랐습니다${c.median_months !== null && c.median_months !== undefined ? ` · 걸린 기간 중앙값 <strong>${fmtNum(c.median_months, 1)}개월</strong>` : ''}.</p>`;
}

/** @param {HTMLElement} host */
export async function renderCityTab(host) {
  const asOf = appState.dataEnd || appState.cfg.as_of || '2026-11-28';
  const [cp, vp, candRows, upcomingRaw] = await Promise.all([
    loadCityProfiles(),
    loadVenueProfiles(),
    queryCandidates({ limit: 300 }).catch(() => []),
    queryUpcomingGigs({ asOf, days: UPCOMING_DAYS }).catch(() => []),
    ensureTeamCitiesLoaded().catch(() => null),
  ]);
  if (!cp?.cities) {
    host.innerHTML = `<section class="block">${naCell('도시 프로필(city_profiles.json)이 아직 없습니다', { block: true })}</section>`;
    return;
  }
  const cities = Object.entries(cp.cities).sort((a, b) => (b[1].nights || 0) - (a[1].nights || 0)).map(([name]) => name);
  const venueCity = new Map(Object.entries(vp?.venues || {}).filter(([, v]) => v?.city).map(([n, v]) => [n, String(v.city)]));
  if (!cities.includes(appState.venuesCity)) appState.venuesCity = cities[0] || '';

  const paint = async () => {
    const city = appState.venuesCity;
    const c = cp.cities[city] || {};
    const low = (c.nights || 0) < LOW_COVERAGE_NIGHTS;
    const homeCands = candRows
      .map((r, i) => ({ ...r, rank: i + 1 }))
      .filter(r => appState.teamCitiesByTeam.get(r.team_key)?.home_city === city);
    const upcoming = upcomingRaw.filter(g => venueCity.get(g.venue) === city);
    const byGig = new Map();
    for (const g of upcoming) {
      const k = `${g.signal_date}|${g.venue}`;
      if (!byGig.has(k)) byGig.set(k, { signal_date: g.signal_date, venue: g.venue, teams: [] });
      byGig.get(k).teams.push(g);
    }
    host.innerHTML = `
      <section class="block city-block">
        <div class="city-picker" role="group" aria-label="도시 고르기">
          ${cities.map(n => `<button type="button" class="cf-preset-btn${n === city ? ' is-active' : ''}" data-city="${escapeHtml(n)}" aria-pressed="${n === city}">${escapeHtml(n)} <span class="cf-preset-cnt">${fmtInt(cp.cities[n].nights || 0)}</span></button>`).join('')}
        </div>
        <p class="small muted city-note">숫자 = 기록된 공연 날짜 수 · 청취자(스트리밍 지역) 자료는 없어 공연 기록만으로 봅니다${cp.as_of ? ` · 기준 ${escapeHtml(cp.as_of)}` : ''}</p>
        <div class="city-kpis">
          <div class="venue-kpi-card"><span class="venue-kpi-lbl">공연장</span><strong class="venue-kpi-val mono">${fmtInt(c.venues_with_gigs || 0)}곳</strong><span class="venue-kpi-sub">명부 ${fmtInt(c.venues_master || 0)}곳 중 기록 있음</span></div>
          <div class="venue-kpi-card"><span class="venue-kpi-lbl">공연 날짜</span><strong class="venue-kpi-val mono">${fmtInt(c.nights || 0)}일</strong><span class="venue-kpi-sub">예정 ${fmtInt(c.upcoming_nights || 0)}일</span></div>
          <div class="venue-kpi-card"><span class="venue-kpi-lbl">최근 1년 출연</span><strong class="venue-kpi-val mono">${fmtInt(c.teams_1y || 0)}팀</strong><span class="venue-kpi-sub">첫 무대 ${fmtInt(c.first_stage_teams_1y || 0)}팀</span></div>
          <div class="venue-kpi-card"><span class="venue-kpi-lbl">나중에 상 받은 팀</span><strong class="venue-kpi-val mono">${fmtInt(c.later_winners_total || 0)}팀</strong><span class="venue-kpi-sub">정답 전에 이 도시에서 공연</span></div>
        </div>
        ${low ? '<p class="city-low-coverage">⚠️ 우리 기록 적음 — 이 도시는 수집된 공연이 적어 아래 목록이 실제보다 비어 보일 수 있습니다.</p>' : ''}
      </section>
      <div class="city-grid">
        <section class="block"><div class="block-head"><h3>최근 3개월 이 도시에서 첫 무대를 연 신인</h3><span class="block-meta" id="cityFirstMeta">계산 중…</span></div><div id="cityFirstBody"><p class="small muted">계산 중…</p></div></section>
        <section class="block"><div class="block-head"><h3>이 도시가 활동 도시인 후보</h3><span class="block-meta">후보 상위 300 중 ${fmtInt(homeCands.length)}팀</span></div>
          ${listOrEmpty(homeCands, appState.teamCitiesByTeam.size ? '이 도시를 활동 도시로 둔 후보가 없습니다.' : '팀별 활동 도시 자료(team_cities.csv)가 아직 없습니다.', r => `<li>${teamLink(r.team_key, r.display_name)} <span class="small muted">#${fmtInt(r.rank)} · ${fmtNum(r.score, 2)}점</span></li>`)}
        </section>
        <section class="block"><div class="block-head"><h3>다가오는 공연 (${UPCOMING_DAYS}일)</h3><span class="block-meta">${fmtInt(byGig.size)}건</span></div>
          ${listOrEmpty([...byGig.values()].sort((a, b) => a.signal_date.localeCompare(b.signal_date)), '30일 안에 잡힌 공연 기록이 없습니다.', g => `<li><span class="mono small">${escapeHtml(formatNextGigText(g))}</span> — ${g.teams.slice(0, 4).map(t => teamLink(t.team_key, t.display_name)).join(' · ')}${g.teams.length > 4 ? ` <span class="small muted">외 ${fmtInt(g.teams.length - 4)}</span>` : ''}</li>`)}
        </section>
        <section class="block"><div class="block-head"><h3>지방 → 서울 흐름</h3></div>${flowHtml(cp, city)}</section>
        <section class="block"><div class="block-head"><h3>자주 쓰인 공연장</h3></div>
          ${listOrEmpty(c.top_venues || [], '공연장 기록이 없습니다.', ([v, n]) => `<li><a class="inline-venue-link" href="#/venue/${encodeURIComponent(v)}">${escapeHtml(v)}</a> <span class="small muted">${fmtInt(n)}일</span></li>`)}
        </section>
        <section class="block"><div class="block-head"><h3>여기서 공연한 뒤 상 받은 팀</h3><span class="block-meta">${fmtInt(c.later_winners_total || 0)}팀</span></div>
          ${listOrEmpty(c.later_winners || [], '기록이 없습니다.', w => `<li>${teamLink(w.team_key, w.name)} ${gradeBadgeHtml(w.grade)} <span class="small muted">${escapeHtml(w.outcome || '')} · ${fmtInt(w.lead_months)}개월 전 이 도시</span></li>`)}
        </section>
      </div>`;
    const first = await queryCityFirstStageTeams(city, venueCity, asOf, RECENT_DAYS);
    if (!host.isConnected || appState.venuesCity !== city) return;
    const body = host.querySelector('#cityFirstBody');
    const meta = host.querySelector('#cityFirstMeta');
    if (meta) meta.textContent = `${fmtInt(first.length)}팀`;
    if (body) {
      body.innerHTML = listOrEmpty(first, venueCity.size ? '최근 3개월 이 도시에서 첫 무대를 연 팀이 없습니다.' : '공연장 → 도시 자료가 없어 계산하지 못했습니다.', t => `<li>${teamLink(t.team_key, t.display_name)} <span class="small muted">${escapeHtml(t.first_date)} · ${escapeHtml(t.first_venue)}</span></li>`);
    }
  };

  host.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-city]');
    if (!btn || btn.dataset.city === appState.venuesCity) return;
    appState.venuesCity = btn.dataset.city;
    syncHash(true);
    paint();
  });
  paint();
}
