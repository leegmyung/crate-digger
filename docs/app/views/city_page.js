/**
 * 도시 페이지 #/city/<이름> (정보 구조 v2 묶음 E) — 요약 숫자 5 · 이 도시에서 뜨는 후보 · 월별 공연 · 대표 공연장 ·
 * 최근 3개월 첫 무대 신인 · 다가오는 공연 · 지방 → 서울 흐름 · 나중에 상 받은 팀.
 * 자료: city_profiles.json · team_cities.csv · venue_profiles.json(공연장 → 도시). 청취자(스트리밍 지역) 자료는 없다.
 */
import { appState } from '../state.js';
import {
  ensureTeamCitiesLoaded, fetchJson, loadVenueProfiles, queryCandidates, queryUpcomingGigs,
} from '../db.js';
import { loadCityProfiles, queryCityFirstStageTeams } from '../db_venue.js';
import {
  avatarHtml, escapeHtml, fmtInt, fmtNum, formatNextGigText, gradeBadgeHtml, INFO_TIPS, infoTip, naCell, playButtonHtml,
} from '../ui.js';
import { isInstaAccountName } from '../components/venue_info.js';
import { aggregateBySido, mountRegionMap, sidoOfCity, sumRecentMonths } from '../components/region_map.js';

const RECENT_DAYS = 90;
const UPCOMING_DAYS = 30;
const MONTHS_SHOWN = 24;
export const LOW_COVERAGE_NIGHTS = 100; // 공연 날짜가 이보다 적으면 '우리 기록 적음'
const LIST_MAX = 12;

function teamLink(key, name) {
  return `<a href="#/team/${encodeURIComponent(key)}">${escapeHtml(name || key)}</a>`;
}

/** 목록 한 줄의 팀: 사진 · 이름 · ▶ (공연 줄처럼 팀이 여럿 붙는 곳은 teamLink 만) */
function teamItem(key, name) {
  return `<span class="team-cell-inline">${avatarHtml(key, name || key, 22, { shape: 'circle' })}${teamLink(key, name)}${playButtonHtml(key, name || key, { variant: 'icon' })}</span>`;
}

function listOrEmpty(items, emptyText, render) {
  if (!items.length) return `<p class="small muted" style="margin:0;">${escapeHtml(emptyText)}</p>`;
  const shown = items.slice(0, LIST_MAX);
  const more = items.length - shown.length;
  return `<ul class="city-list">${shown.map(render).join('')}</ul>${more > 0 ? `<p class="small muted">외 ${fmtInt(more)}건</p>` : ''}`;
}

/** 기준 달까지 최근 n달 'YYYY-MM' */
export function recentMonths(asOf, n) {
  const [y, m] = String(asOf).split('-').map(Number);
  return Array.from({ length: n }, (_, i) => new Date(Date.UTC(y, m - 1 - (n - 1 - i), 1)).toISOString().slice(0, 7));
}

/** 월별 공연 날짜 막대 (city_profiles monthly) */
export function cityMonthBarsHtml(monthly, asOf, n = MONTHS_SHOWN, minScale = 8) {
  const months = recentMonths(asOf, n);
  const vals = months.map(ym => Number(monthly?.[ym]) || 0);
  const max = Math.max(minScale, ...vals);
  return `<div class="place-months" role="img" aria-label="최근 ${n}개월 월별 공연 날짜 ${vals.join(', ')}">
    ${vals.map((v, i) => `<span class="place-month" style="height:${Math.max(v ? 8 : 3, (v / max) * 100).toFixed(0)}%" title="${months[i]} ${v}일"></span>`).join('')}
  </div>`;
}

let krMapPromise = null;
/** 시·도 경계(docs/app/data/kr_sido.json, Natural Earth) — 한 번만 받는다. 없으면 null */
export function loadKrMap() {
  if (!krMapPromise) {
    krMapPromise = fetchJson('app/data/kr_sido.json', true)
      .then(d => (Array.isArray(d?.regions) && d.regions.length ? d : null))
      .catch(() => null);
  }
  return krMapPromise;
}

/** venue_profiles → 지도 점 자료 [{ name, city, lat, lon, tier, nights12 }] */
export function mapVenues(vp, asOf) {
  return Object.entries(vp?.venues || {}).map(([name, v]) => ({
    name,
    city: v?.city || '',
    lat: v?.lat,
    lon: v?.lon,
    tier: v?.tier || '',
    nights12: v?.discovery?.nights_12m ?? sumRecentMonths(v?.monthly, asOf, 12),
  }));
}

/**
 * 시·도 지도 붙이기 (도시 목록·도시 페이지 같이 씀). 경계 자료가 없으면 안내 문구만.
 * @returns {ReturnType<typeof mountRegionMap>|null}
 */
export function mountCityRegionMap(el, { geo, cp, vp, asOf, initial = null, highlightCity = null, metric, onMetric, onZoom }) {
  if (!el) return null;
  if (!geo) {
    el.innerHTML = naCell('시·도 경계 자료(app/data/kr_sido.json)를 불러오지 못했습니다', { block: true });
    return null;
  }
  const { bySido } = aggregateBySido(cp?.cities || {}, asOf);
  return mountRegionMap(el, {
    geo, bySido, venues: mapVenues(vp, asOf), initial, highlightCity, metric, onMetric, onZoom,
  });
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

function kpi(label, value, sub) {
  const desc = (INFO_TIPS.city_summary.bands || []).find(([k]) => k === label)?.[1] || '';
  const tip = desc ? infoTip(label, { what: desc, period: INFO_TIPS.city_summary.period, compare: INFO_TIPS.city_summary.compare }, { compact: true }) : '';
  return `<div class="venue-kpi-card"><span class="venue-kpi-lbl">${escapeHtml(label)}${tip}</span><strong class="venue-kpi-val mono">${value}</strong><span class="venue-kpi-sub">${sub}</span></div>`;
}

/**
 * @param {HTMLElement} host
 * @param {string} city
 */
export async function renderCityPage(host, city) {
  const asOf = appState.dataEnd || appState.cfg.as_of || '2026-11-28';
  const [cp, vp, candRows, upcomingRaw, , geo] = await Promise.all([
    loadCityProfiles(),
    loadVenueProfiles(),
    queryCandidates({ limit: 300 }).catch(() => []),
    queryUpcomingGigs({ asOf, days: UPCOMING_DAYS }).catch(() => []),
    ensureTeamCitiesLoaded().catch(() => null),
    loadKrMap(),
  ]);
  const back = '<div class="team-topbar"><a class="btn btn-sm" href="#/cities">← 도시 목록</a></div>';
  if (!cp?.cities) {
    host.innerHTML = `${back}<section class="block">${naCell('도시 프로필(city_profiles.json)이 아직 없습니다', { block: true })}</section>`;
    return;
  }
  const c = cp.cities[city];
  if (!c) {
    host.innerHTML = `${back}<section class="block"><h1 class="place-title">${escapeHtml(city)}</h1>
      <p class="muted">이 도시는 우리 공연 기록에 없습니다. <a href="#/cities">도시 목록</a>에서 골라 주세요.</p></section>`;
    return;
  }
  // '@계정'(인스타 기획·레이블 계정 표기)은 공연장이 아니라 '첫 무대' 계산에서 뺀다
  const venueCity = new Map(Object.entries(vp?.venues || {})
    .filter(([n, v]) => v?.city && !isInstaAccountName(n))
    .map(([n, v]) => [n, String(v.city)]));
  const low = (c.nights || 0) < LOW_COVERAGE_NIGHTS;
  const homeCands = candRows
    .map((r, i) => ({ ...r, rank: i + 1 }))
    .filter(r => appState.teamCitiesByTeam.get(r.team_key)?.home_city === city);
  const byGig = new Map();
  for (const g of upcomingRaw.filter(x => venueCity.get(x.venue) === city)) {
    const k = `${g.signal_date}|${g.venue}`;
    if (!byGig.has(k)) byGig.set(k, { signal_date: g.signal_date, venue: g.venue, teams: [] });
    byGig.get(k).teams.push(g);
  }

  host.innerHTML = `
    ${back}
    <section class="place-head">
      <div class="place-head-row">
        <h1 class="place-title">${escapeHtml(city)}</h1>
        <span class="place-badge${low ? ' is-low' : ''}">${low ? '우리 기록 적음' : '우리 기록 많음'}</span>
      </div>
      <p class="small muted">청취자(스트리밍 지역) 자료는 없어 공연 기록만으로 봅니다${cp.as_of ? ` · 기준 ${escapeHtml(cp.as_of)}` : ''}</p>
      <div class="city-kpis">
        ${kpi('공연장', `${fmtInt(c.venues_with_gigs || 0)}곳`, `명부 ${fmtInt(c.venues_master || 0)}곳 중 기록 있음`)}
        ${kpi('공연 날짜', `${fmtInt(c.nights || 0)}일`, `예정 ${fmtInt(c.upcoming_nights || 0)}일`)}
        ${kpi('최근 1년 출연', `${fmtInt(c.teams_1y || 0)}팀`, '이 도시 무대에 선 팀')}
        ${kpi('첫 무대 신인', `${fmtInt(c.first_stage_teams_1y || 0)}팀`, `최근 1년 · 누적 ${fmtInt(c.first_stage_teams || 0)}팀`)}
        ${kpi('나중에 상 받은 팀', `${fmtInt(c.later_winners_total || 0)}팀`, '정답 전에 이 도시에서 공연')}
      </div>
      ${low ? '<p class="city-low-coverage">⚠️ 우리 기록 적음 — 이 도시는 수집된 공연이 적어 아래 목록이 실제보다 비어 보일 수 있습니다.</p>' : ''}
    </section>
    <section class="block">
      <div class="block-head"><h2>지도</h2><span class="block-meta">${sidoOfCity(city) ? `${escapeHtml(sidoOfCity(city))} 공연장 · 진한 점 = ${escapeHtml(city)}` : '전국'} · 점을 누르면 공연장 페이지</span></div>
      <div id="cityRegionMap"></div>
    </section>
    <section class="block">
      <div class="block-head"><h2>월별 공연</h2><span class="block-meta">최근 ${MONTHS_SHOWN}개월 · 공연 날짜 수(같은 날·같은 공연장 = 1)</span></div>
      ${cityMonthBarsHtml(c.monthly, asOf)}
    </section>
    <div class="city-grid">
      <section class="block"><div class="block-head"><h3>이 도시에서 뜨는 후보</h3><span class="block-meta">최근 3년 이 도시에서 공연한 팀 중 점수 상위</span></div>
        ${listOrEmpty(c.top_candidates || [], '기록이 없습니다.', r => `<li>${teamItem(r.team_key, r.name)} <span class="small muted">#${fmtInt(r.rank)} · ${fmtNum(r.score, 2)}점 · 마지막 ${escapeHtml(r.last_here || '')}</span></li>`)}
      </section>
      <section class="block"><div class="block-head"><h3>이 도시가 활동 도시인 후보</h3><span class="block-meta">후보 상위 300 중 ${fmtInt(homeCands.length)}팀</span></div>
        ${listOrEmpty(homeCands, appState.teamCitiesByTeam.size ? '이 도시를 활동 도시로 둔 후보가 없습니다.' : '팀별 활동 도시 자료(team_cities.csv)가 아직 없습니다.', r => `<li>${teamItem(r.team_key, r.display_name)} <span class="small muted">#${fmtInt(r.rank)} · ${fmtNum(r.score, 2)}점</span></li>`)}
      </section>
      <section class="block"><div class="block-head"><h3>최근 3개월 이 도시에서 첫 무대를 연 신인</h3><span class="block-meta" id="cityFirstMeta">계산 중…</span></div><div id="cityFirstBody"><p class="small muted">계산 중…</p></div></section>
      <section class="block"><div class="block-head"><h3>다가오는 공연 (${UPCOMING_DAYS}일)</h3><span class="block-meta">${fmtInt(byGig.size)}건</span></div>
        ${listOrEmpty([...byGig.values()].sort((a, b) => a.signal_date.localeCompare(b.signal_date)), '30일 안에 잡힌 공연 기록이 없습니다.', g => `<li><span class="mono small">${escapeHtml(formatNextGigText(g))}</span> — ${g.teams.slice(0, 4).map(t => `<span class="team-cell-inline">${avatarHtml(t.team_key, t.display_name, 18, { shape: 'circle' })}${teamLink(t.team_key, t.display_name)}</span>`).join(' · ')}${g.teams.length > 4 ? ` <span class="small muted">외 ${fmtInt(g.teams.length - 4)}</span>` : ''}</li>`)}
      </section>
      <section class="block"><div class="block-head"><h3>대표 공연장</h3><span class="block-meta">공연 날짜 많은 순</span></div>
        ${listOrEmpty(c.top_venues || [], '공연장 기록이 없습니다.', ([v, n]) => `<li><a class="inline-venue-link" href="#/venue/${encodeURIComponent(v)}">${escapeHtml(v)}</a> <span class="small muted">${fmtInt(n)}일</span></li>`)}
      </section>
      <section class="block"><div class="block-head"><h3>지방 → 서울 흐름</h3></div>${flowHtml(cp, city)}</section>
      <section class="block"><div class="block-head"><h3>여기서 공연한 뒤 상 받은 팀</h3><span class="block-meta">${fmtInt(c.later_winners_total || 0)}팀</span></div>
        ${listOrEmpty(c.later_winners || [], '기록이 없습니다.', w => `<li>${teamItem(w.team_key, w.name)} ${gradeBadgeHtml(w.grade)} <span class="small muted">${escapeHtml(w.outcome || '')} · ${fmtInt(w.lead_months)}개월 전 이 도시</span></li>`)}
      </section>
    </div>
    <p class="small muted place-evidence">근거: 도시 = 우리가 정리한 공연장 목록의 도시 · 첫 무대 = 우리 데이터에서 도시를 아는 첫 공연 · 수집 상태는 <a href="#/verify/quality">검증 › 데이터 품질</a></p>`;

  mountCityRegionMap(host.querySelector('#cityRegionMap'), {
    geo, cp, vp, asOf, initial: sidoOfCity(city), highlightCity: city,
  });

  const first = await queryCityFirstStageTeams(city, venueCity, asOf, RECENT_DAYS);
  if (!host.isConnected) return;
  const body = host.querySelector('#cityFirstBody');
  const meta = host.querySelector('#cityFirstMeta');
  if (meta) meta.textContent = `${fmtInt(first.length)}팀`;
  if (body) {
    body.innerHTML = listOrEmpty(first, venueCity.size ? '최근 3개월 이 도시에서 첫 무대를 연 팀이 없습니다.' : '공연장 → 도시 자료가 없어 계산하지 못했습니다.', t => `<li>${teamItem(t.team_key, t.display_name)} <span class="small muted">${escapeHtml(t.first_date)} · <a class="inline-venue-link" href="#/venue/${encodeURIComponent(t.first_venue)}">${escapeHtml(t.first_venue)}</a></span></li>`);
  }
}
