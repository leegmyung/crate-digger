import { appState, registerChart, setExportContext, syncHash } from '../state.js';
import {
  buildNextGigByTeam, groupUpcomingEvents, loadDashboardJson, loadSceneMap, queryCandidates,
  queryMonthlyNewcomerVenues, queryUpcomingGigs,
} from '../db.js';
import {
  avatarHtml, cssVar, ensureChartJs, ensureD3, escapeHtml, fmtInt, fmtNum, formatKoreanShortDate,
  formatNextGigText, plainWhyLine, renderActionBanner, renderTableCsvBtn, spotifyButtonHtml,
  triggerTableCsvExport, wireAvatarFallbacks, wireSpotifyButtons,
} from '../ui.js';
import { mountSceneNetworkBlock } from './graph.js';
import { renderVenueListPage, renderVenueViewSwitch, wireVenueViewSwitch } from './venues_list.js';
import { renderCitiesList } from './city.js';
import { renderCityPage } from './city_page.js';
import { renderFestivalsList } from './festivals.js';
import { renderFestivalPage } from './festival_page.js';

/**
 * 공연장 메뉴(정보 구조 v2 묶음 D): #/venues · #/venues/list = 공연장 목록(보기: 표·지도),
 * #/venues/network = 씬 보기(씬 네트워크 그림 + 이번 달 신인 많은 공연장 · 씬 묶음 · 다가오는 공연 달력).
 * 도시(#/cities·#/city/<이름>)·페스티벌(#/festivals·#/festival/<이름>)도 안쪽 경로는 venues 라 여기서 나눠 준다.
 */
export async function renderVenuesView(root) {
  const asOf = appState.cfg.as_of || appState.dataEnd || '2026-11-27';
  // 묶음 E: 도시 목록 #/cities → 도시 페이지 #/city/<이름>, 페스티벌 목록 #/festivals → #/festival/<이름>
  if (appState.venuesTab === 'city') {
    if (appState.venuesCity) await renderCityPage(root, appState.venuesCity);
    else await renderCitiesList(root);
    return;
  }
  if (appState.venuesTab === 'festival') {
    if (appState.festivalName) await renderFestivalPage(root, appState.festivalName);
    else await renderFestivalsList(root);
    return;
  }
  // 팀 상세의 '속한 씬' 링크는 씬 묶음을 펼쳐 보여 줘야 하므로 씬 보기로
  if (appState.focusSceneId !== undefined && appState.focusSceneId !== null) {
    appState.venuesTab = 'network';
    syncHash(true);
  }
  if (appState.venuesTab !== 'network') {
    await renderVenueListPage(root);
    return;
  }
  const [candRows, upcomingRaw, sceneMap] = await Promise.all([
    queryCandidates({ limit: 300 }),
    queryUpcomingGigs({ asOf }),
    loadSceneMap(),
    ensureD3().catch(() => null),
    loadDashboardJson().catch(() => null),
  ]);
  const monthly = await queryMonthlyNewcomerVenues(candRows, asOf);
  const sceneCommunities = sceneMap?.communities || [];

  const candRankMap = new Map();
  candRows.forEach((r, idx) => {
    candRankMap.set(r.team_key, {
      rank: idx + 1,
      score: r.score,
      display_name: r.display_name || r.team_key,
      primary_genre: r.primary_genre || '',
    });
  });
  const nextGigByTeam = buildNextGigByTeam(upcomingRaw);
  const allUpcomingEvents = groupUpcomingEvents(upcomingRaw, candRankMap);
  const candUpcomingEvents = allUpcomingEvents.filter(ev => ev.hasCandidate);

  let allTimeVenues = appState.dashboardJson?.sections?.top_venues || [];
  const topMonthV = monthly.venues[0];

  const venuesCsvSpec = monthly.venues.length ? {
    filename: `crate_digger_venues_${monthly.ym || appState.dataEnd || 'export'}.csv`,
    headers: ['순위', '공연장', '후보 팀', '전체 팀', '이달 무대', '후보 비율(%)', '주요 후보'],
    rows: monthly.venues.map((v, idx) => [
      idx + 1,
      v.venue,
      v.candidateCount,
      v.totalTeams,
      v.monthGigs,
      v.candidateRatio.toFixed(1),
      v.candidates.slice(0, 5).map(c => `${c.display_name}(#${c.rank})`).join(' / '),
    ]),
  } : null;

  setExportContext({
    csvLabel: venuesCsvSpec
      ? `${monthly.monthLabel} 공연장 CSV 내려받기 (${fmtInt(monthly.venues.length)}곳)`
      : '',
    csvFilename: venuesCsvSpec?.filename || '',
    csvHeaders: venuesCsvSpec?.headers || [],
    csvRows: venuesCsvSpec?.rows || [],
  });

  const bannerHtml = renderActionBanner({
    title: '이번 달',
    lead: topMonthV
      ? `${escapeHtml(monthly.monthLabel)} 신인 후보가 가장 많이 선 공연장은 <a class="inline-venue-link" href="#/venue/${encodeURIComponent(topMonthV.venue)}"><strong>${escapeHtml(topMonthV.venue)}</strong></a>(후보 ${fmtInt(topMonthV.candidateCount)}팀 · 전체 ${fmtInt(topMonthV.totalTeams)}팀)이며, 예정된 후보 무대는 <strong>${fmtInt(candUpcomingEvents.length)}건</strong>입니다.`
      : `${escapeHtml(monthly.monthLabel)} 기준 조건에 맞는 신인 후보 출연 공연장이 아직 없습니다.`,
  });

  let venueLimit = 8;
  let expandedVenue = '';
  let sceneLimit = 10;
  let expandedSceneId = null;
  if (appState.focusSceneId !== undefined && appState.focusSceneId !== null) {
    const targetId = Number(appState.focusSceneId);
    const idx = sceneCommunities.findIndex(c => Number(c.id) === targetId);
    if (idx >= 0) {
      expandedSceneId = targetId;
      if (idx + 1 > sceneLimit) sceneLimit = Math.ceil((idx + 1) / 10) * 10;
    }
    appState.focusSceneId = null;
  }
  let calMode = appState.venuesCalMode === 'all' ? 'all' : 'cand';
  let calLimit = 8;
  let chartRendered = false;
  let sceneGraphHandle = null;

  function renderVenueRow(v, idx) {
    const isOpen = expandedVenue === v.venue;
    const previewCands = v.candidates.slice(0, 4);
    const bodyCands = v.candidates.slice(0, 10);
    const extraCands = v.candidates.length - bodyCands.length;
    const venueHref = `#/venue/${encodeURIComponent(v.venue)}`;

    return `
      <li class="venue-acc-item ${isOpen ? 'is-open' : ''}">
        <div class="venue-acc-head" data-toggle-venue="${escapeHtml(v.venue)}" role="button" tabindex="0" aria-expanded="${isOpen ? 'true' : 'false'}">
          <div class="venue-acc-left">
            <span class="venue-rank">#${idx + 1}</span>
            <div class="venue-acc-title-col">
              <a class="venue-name venue-name-link" href="${venueHref}">${escapeHtml(v.venue)}</a>
              <span class="small muted">전체 출연 ${fmtInt(v.totalTeams)}팀 · 후보 비중 ${v.candidateRatio.toFixed(0)}%</span>
            </div>
          </div>
          <div class="venue-acc-right">
            <div class="avatar-stack" aria-hidden="true">
              ${previewCands.map(c => avatarHtml(c.team_key, c.display_name, 26, { shape: 'circle', genre: c.primary_genre })).join('')}
            </div>
            <span class="badge-new">후보 ${fmtInt(v.candidateCount)}팀</span>
            <span class="venue-acc-caret" aria-hidden="true">▸</span>
          </div>
        </div>
        ${isOpen ? `
          <div class="venue-acc-body">
            <div class="venue-cand-list">
              ${bodyCands.map(c => {
                const ng = nextGigByTeam.get(c.team_key);
                const dateBadge = ng
                  ? `<span class="next-gig-chip">다음 ${escapeHtml(formatNextGigText(ng))}</span>`
                  : `<span class="small muted mono">${escapeHtml(formatKoreanShortDate(c.lastGigDate))} 출연</span>`;
                return `
                  <div class="venue-cand-row">
                    <a class="row-team-cell venue-cand-main" href="#/team/${encodeURIComponent(c.team_key)}">
                      ${avatarHtml(c.team_key, c.display_name, 28, { shape: 'circle', genre: c.primary_genre })}
                      <div class="row-team-text">
                        <div class="row-team-name">
                          <strong>${escapeHtml(c.display_name || c.team_key)}</strong>
                          <span class="rank-pill">#${c.rank}</span>
                          <span class="small muted mono">${fmtNum(c.score, 1)}점</span>
                        </div>
                        <div class="small muted">${escapeHtml(plainWhyLine(c))}</div>
                      </div>
                    </a>
                    <div class="venue-cand-right">
                      ${dateBadge}
                      ${spotifyButtonHtml(c.team_key, true, { iconOnly: true, teamName: c.display_name || c.team_key, slotId: 'venueExpandedPlayerSlot' })}
                    </div>
                  </div>
                `;
              }).join('')}
            </div>
            <div class="player-slot" id="venueExpandedPlayerSlot" data-player-slot></div>
            <div class="venue-acc-foot">
              ${extraCands > 0 ? `<span class="small muted">외 후보 ${fmtInt(extraCands)}팀이 이번 달 이 무대에 섰습니다.</span>` : '<span></span>'}
              <a class="btn btn-sm" href="${venueHref}">공연장 상세 보기 →</a>
            </div>
          </div>
        ` : ''}
      </li>
    `;
  }

  function renderCalendarSection() {
    const sourceEvents = calMode === 'cand' ? candUpcomingEvents : allUpcomingEvents;
    const visEvents = sourceEvents.slice(0, calLimit);
    const remEvents = sourceEvents.length - visEvents.length;

    // Group visible events by date
    const byDate = new Map();
    for (const ev of visEvents) {
      if (!byDate.has(ev.signal_date)) byDate.set(ev.signal_date, []);
      byDate.get(ev.signal_date).push(ev);
    }

    const dayGroupsHtml = visEvents.length
      ? [...byDate.entries()].map(([dateStr, evs]) => `
          <div class="cal-day-group">
            <div class="cal-day-head">
              <strong>${escapeHtml(formatKoreanShortDate(dateStr))}</strong>
              <span class="small muted mono">${escapeHtml(dateStr)} · ${fmtInt(evs.length)}개 공연장</span>
            </div>
            <ul class="upcoming-list">
              ${evs.map(ev => {
                const primaryTeams = ev.candidateTeams.length ? ev.candidateTeams : ev.otherTeams.slice(0, 4);
                const extraOther = ev.candidateTeams.length
                  ? ev.otherTeams
                  : ev.otherTeams.slice(4);
                const otherNames = extraOther.slice(0, 3).map(t => t.display_name);
                const otherMore = extraOther.length - otherNames.length;
                const multiCand = ev.candidateTeams.length >= 2;
                const isNamedVenue = ev.venue && ev.venue !== '공연장 미정';
                return `
                  <li class="upcoming-row cal-event-row">
                    <div class="upcoming-when">
                      ${isNamedVenue
                        ? `<a class="upcoming-venue inline-venue-link" href="#/venue/${encodeURIComponent(ev.venue)}">${escapeHtml(ev.venue)}</a>`
                        : `<span class="upcoming-venue">${escapeHtml(ev.venue)}</span>`}
                      ${multiCand ? `<span class="cobill-badge">후보 ${ev.candidateTeams.length}팀 함께 서는 무대</span>` : ''}
                    </div>
                    <div class="upcoming-teams-wrap">
                      <div class="upcoming-teams">
                        ${primaryTeams.map(t => `
                          <div class="upcoming-team-chip">
                            <a class="upcoming-team-link" href="#/team/${encodeURIComponent(t.team_key)}">
                              ${avatarHtml(t.team_key, t.display_name, 28, { shape: 'circle', genre: t.primary_genre })}
                              <strong>${escapeHtml(t.display_name)}</strong>
                              ${t.rank ? `<span class="rank-pill">#${t.rank}</span>` : ''}
                            </a>
                            ${spotifyButtonHtml(t.team_key, true, { iconOnly: true, teamName: t.display_name, slotId: 'venueCalPlayerSlot' })}
                          </div>
                        `).join('')}
                      </div>
                      ${extraOther.length > 0 ? `<div class="cobill-note"><span class="cobill-lbl">함께 서는 팀</span> ${escapeHtml(otherNames.join(', '))}${otherMore > 0 ? ` 외 ${fmtInt(otherMore)}팀` : ''}</div>` : ''}
                    </div>
                  </li>
                `;
              }).join('')}
            </ul>
          </div>
        `).join('')
      : '<p class="muted small" style="margin:0;">예정된 공연 데이터가 없습니다.</p>';

    return `
      <section class="block" id="upcomingCalendarBlock">
        <div class="block-head">
          <div>
            <h2>다가오는 공연 달력</h2>
            <span class="block-meta">기준일 ${escapeHtml(asOf)} 이후 예정 공연 · 날짜·공연장별 묶음</span>
          </div>
          <div class="chip-group" role="group" aria-label="달력 범위">
            <button type="button" class="chip-btn ${calMode === 'cand' ? 'active' : ''}" data-cal-mode="cand" aria-pressed="${calMode === 'cand'}">후보 출연 ${fmtInt(candUpcomingEvents.length)}</button>
            <button type="button" class="chip-btn ${calMode === 'all' ? 'active' : ''}" data-cal-mode="all" aria-pressed="${calMode === 'all'}">전체 공연 ${fmtInt(allUpcomingEvents.length)}</button>
          </div>
        </div>
        ${dayGroupsHtml}
        <div class="player-slot" id="venueCalPlayerSlot" data-player-slot></div>
        ${remEvents > 0
          ? `<div class="more-row" style="margin-top:10px;">
               <span>${fmtInt(visEvents.length)} / ${fmtInt(sourceEvents.length)}개 무대</span>
               <button type="button" class="btn btn-sm" id="btnMoreCal">${fmtInt(Math.min(12, remEvents))}건 더 보기</button>
             </div>`
          : (calLimit > 8 && sourceEvents.length > 8
              ? `<div class="more-row" style="margin-top:10px;">
                   <span>전체 ${fmtInt(sourceEvents.length)}개 무대 표시 중</span>
                   <button type="button" class="btn btn-sm" id="btnLessCal">접기</button>
                 </div>`
              : '')}
      </section>
    `;
  }

  async function renderCumulativeChart() {
    if (chartRendered || !allTimeVenues.length) return;
    const cv = root.querySelector('#venuesChart');
    if (!cv) return;
    chartRendered = true;
    const ChartCtor = await ensureChartJs().catch(() => null);
    if (!ChartCtor || !cv.isConnected) {
      chartRendered = false;
      return;
    }
    const inkMuted = cssVar('--ink-muted');
    const lineColor = cssVar('--line');
    registerChart(new ChartCtor(cv.getContext('2d'), {
      type: 'bar',
      data: {
        labels: allTimeVenues.map(v => v.venue),
        datasets: [
          { label: '출연 팀', data: allTimeVenues.map(v => Number(v.teams) || 0), backgroundColor: cssVar('--bar-gigs'), borderRadius: 2 },
          { label: '후보 팀', data: allTimeVenues.map(v => Number(v.candidate_teams) || 0), backgroundColor: cssVar('--bar-score'), borderRadius: 2 },
        ],
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        plugins: {
          legend: { position: 'top', align: 'start', labels: { color: inkMuted, boxWidth: 12, font: { size: 12 } } },
        },
        scales: {
          x: { beginAtZero: true, ticks: { color: inkMuted }, grid: { color: lineColor } },
          y: { ticks: { color: inkMuted, font: { size: 11.5 } }, grid: { display: false } },
        },
      },
    }));
  }

  const validTeamKeys = appState.teamIndex?.length
    ? new Set(appState.teamIndex.map(t => t.team_key))
    : null;

  function renderSceneRow(c) {
    const isOpen = expandedSceneId === Number(c.id);
    const topVenues = (c.top_venues || []).slice(0, 3);
    const venuesTitle = topVenues.length
      ? topVenues.map(v => v.venue).join(' · ')
      : `씬 묶음 ${c.id}`;
    const venuesCountsHtml = topVenues.length
      ? topVenues.map(v => `<a class="inline-venue-link" href="#/venue/${encodeURIComponent(v.venue)}">${escapeHtml(v.venue)}</a> ${fmtInt(v.events)}`).join(' · ')
      : '';
    const topCands = (c.top_candidates || [])
      .filter(t => !validTeamKeys || validTeamKeys.has(t.team_key))
      .slice(0, 5);
    const hubs = (c.hubs || [])
      .filter(h => !validTeamKeys || validTeamKeys.has(h.team_key))
      .slice(0, 5);
    const previewTeams = topCands.length ? topCands.slice(0, 5) : hubs.slice(0, 3);

    return `
      <li class="venue-acc-item scene-acc-item ${isOpen ? 'is-open' : ''}" data-scene-id="${c.id}">
        <button type="button" class="venue-acc-head scene-acc-head" data-toggle-scene="${c.id}" aria-expanded="${isOpen ? 'true' : 'false'}">
          <div class="venue-acc-left">
            <span class="venue-rank scene-id-tag">묶음 ${fmtInt(c.id)}</span>
            <div class="venue-acc-title-col">
              <strong class="venue-name">${escapeHtml(venuesTitle)}</strong>
              <span class="small muted">${fmtInt(c.size)}팀${topCands.length ? ` · 상위 후보 ${fmtInt(topCands.length)}팀` : ''}</span>
            </div>
          </div>
          <div class="venue-acc-right">
            ${previewTeams.length ? `
              <div class="avatar-stack" aria-hidden="true">
                ${previewTeams.map(t => avatarHtml(t.team_key, t.name || t.team_key, 26, { shape: 'circle' })).join('')}
              </div>
            ` : ''}
            <span class="venue-acc-caret" aria-hidden="true">▸</span>
          </div>
        </button>
        ${isOpen ? `
          <div class="venue-acc-body scene-acc-body">
            ${venuesCountsHtml ? `<p class="small muted scene-venues-meta">대표 공연장 (최근 1년 공연 수): ${venuesCountsHtml}</p>` : ''}
            <div class="scene-detail-grid">
              <div class="scene-detail-col">
                <h3 class="scene-detail-head">상위 후보</h3>
                ${topCands.length ? `
                  <ul class="scene-team-list">
                    ${topCands.map(t => `
                      <li>
                        <a class="scene-team-link" href="#/team/${encodeURIComponent(t.team_key)}">
                          ${avatarHtml(t.team_key, t.name || t.team_key, 24, { shape: 'circle' })}
                          <strong>${escapeHtml(t.name || t.team_key)}</strong>
                          ${t.rank ? `<span class="rank-pill">#${fmtInt(t.rank)}</span>` : ''}
                        </a>
                        ${t.score !== null && t.score !== undefined ? `<span class="small muted mono">${fmtNum(t.score, 2)}점</span>` : ''}
                      </li>
                    `).join('')}
                  </ul>
                ` : '<p class="small muted" style="margin:0;">현재 점수 순위권 후보 없음</p>'}
              </div>
              <div class="scene-detail-col">
                <h3 class="scene-detail-head">허브 팀</h3>
                ${hubs.length ? `
                  <ul class="scene-team-list">
                    ${hubs.map(h => `
                      <li>
                        <a class="scene-team-link" href="#/team/${encodeURIComponent(h.team_key)}">
                          ${avatarHtml(h.team_key, h.name || h.team_key, 24, { shape: 'circle' })}
                          <strong>${escapeHtml(h.name || h.team_key)}</strong>
                        </a>
                        <span class="small muted mono">연결 ${fmtInt(h.links)}</span>
                      </li>
                    `).join('')}
                  </ul>
                ` : '<p class="small muted" style="margin:0;">허브 팀 정보 없음</p>'}
              </div>
            </div>
          </div>
        ` : ''}
      </li>
    `;
  }

  function renderSceneSection() {
    if (!sceneCommunities.length) return '';
    const vis = sceneCommunities.slice(0, sceneLimit);
    const rem = sceneCommunities.length - vis.length;
    const winFrom = sceneMap?.raw?.window?.from || '';
    const winTo = sceneMap?.raw?.window?.to || '';
    const metaSub = winFrom && winTo
      ? `${winFrom} ~ ${winTo} 같은 무대 기준 · 묶음을 누르면 상위 후보와 허브 팀이 펼쳐집니다`
      : '최근 1년 같은 무대 기준 · 묶음을 누르면 상위 후보와 허브 팀이 펼쳐집니다';

    return `
      <section class="block" id="sceneCommunitiesBlock">
        <div class="block-head">
          <div>
            <h2>씬 묶음</h2>
            <span class="block-meta">${escapeHtml(metaSub)}</span>
          </div>
          <span class="block-meta">${fmtInt(sceneCommunities.length)}개 묶음 · ${fmtInt(sceneMap?.raw?.n_teams || 0)}팀</span>
        </div>
        <ul class="venue-acc-list" id="sceneAccList">
          ${vis.map(c => renderSceneRow(c)).join('')}
        </ul>
        ${rem > 0
          ? `<div class="more-row" style="margin-top:10px;">
               <span>상위 ${fmtInt(vis.length)} / ${fmtInt(sceneCommunities.length)}개 묶음</span>
               <button type="button" class="btn btn-sm" id="btnMoreScenes">${fmtInt(Math.min(10, rem))}개 더 보기</button>
             </div>`
          : (sceneLimit > 10 && sceneCommunities.length > 10
              ? `<div class="more-row" style="margin-top:10px;">
                   <span>전체 ${fmtInt(sceneCommunities.length)}개 묶음 표시 중</span>
                   <button type="button" class="btn btn-sm" id="btnLessScenes">접기</button>
                 </div>`
              : '')}
      </section>
    `;
  }

  // 씬 보기 틀: 제목·보기 전환 + 씬 네트워크 그림(한 번만 그림) + 아래 묶음들(paint 가 다시 그림)
  root.innerHTML = `
    <div class="vl-page-head">
      <div>
        <h1 class="vl-title">공연장 · 씬</h1>
        <p class="small muted">같은 무대에 함께 선 팀·공연장의 연결 — 이번 달 신인이 많이 선 곳 · 씬 묶음 · 다가오는 공연</p>
      </div>
      ${renderVenueViewSwitch('scene')}
    </div>
    ${bannerHtml}
    <div id="sceneNetworkHost"></div>
    <div id="venueSceneSections"></div>
  `;
  wireVenueViewSwitch(root);
  const graphHost = root.querySelector('#sceneNetworkHost');
  if (graphHost) {
    sceneGraphHandle = mountSceneNetworkBlock(graphHost, {
      initialGenre: appState.cfg.genre || '',
      initialLimit: appState.sceneNetLimit || 150,
      nextGigByTeam,
    });
  }

  function paint() {
    chartRendered = false;
    const sectionsHost = root.querySelector('#venueSceneSections');
    if (!sectionsHost) return;

    const visVenues = monthly.venues.slice(0, venueLimit);
    const remVenues = monthly.venues.length - visVenues.length;

    sectionsHost.innerHTML = `
      <section class="block" id="monthlyVenuesBlock">
        <div class="block-head">
          <div>
            <h2>이번 달 신인이 많이 선 공연장 TOP</h2>
            <span class="block-meta">${escapeHtml(monthly.monthLabel)} 기준 · 공연장을 누르면 출연한 상위 후보가 펼쳐집니다</span>
          </div>
          <div class="block-head-actions">
            <span class="block-meta">${fmtInt(monthly.venues.length)}곳</span>
            ${venuesCsvSpec ? renderTableCsvBtn('btnVenuesCsv', 'CSV 내려받기') : ''}
          </div>
        </div>
        ${visVenues.length
          ? `<ul class="venue-acc-list" id="venueAccList">${visVenues.map((v, i) => renderVenueRow(v, i)).join('')}</ul>`
          : '<p class="muted small" style="margin:0;">이번 달 후보 출연 공연장이 없습니다.</p>'}
        ${remVenues > 0
          ? `<div class="more-row" style="margin-top:10px;">
               <span>상위 ${fmtInt(visVenues.length)} / ${fmtInt(monthly.venues.length)}곳</span>
               <button type="button" class="btn btn-sm" id="btnMoreVenues">${fmtInt(Math.min(10, remVenues))}곳 더 보기</button>
             </div>`
          : ''}
      </section>

      ${renderSceneSection()}

      ${renderCalendarSection()}

      ${allTimeVenues.length ? `
        <details class="block venue-cum-fold" id="venueCumFold">
          <summary class="venue-cum-summary">
            <strong>누적 공연장 통계 차트 (전체 기간 상위 ${fmtInt(allTimeVenues.length)}곳)</strong>
            <span class="small muted">펼쳐 보기</span>
          </summary>
          <div style="margin-top:14px;">
            <div class="chart-box chart-box-tall"><canvas id="venuesChart"></canvas></div>
          </div>
        </details>
      ` : ''}

      <p class="photo-credit">아티스트 사진 출처: Spotify</p>
    `;

    wireAvatarFallbacks(root);
    wireSpotifyButtons(root);

    root.querySelectorAll('[data-toggle-venue]').forEach(btn => {
      const toggle = () => {
        const v = btn.dataset.toggleVenue;
        expandedVenue = (expandedVenue === v) ? '' : v;
        paint();
      };
      btn.addEventListener('click', (e) => {
        if (e.target.closest('a')) return;
        toggle();
      });
      btn.addEventListener('keydown', (e) => {
        if (e.target.closest('a')) return;
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          toggle();
        }
      });
    });

    root.querySelector('#btnMoreVenues')?.addEventListener('click', () => {
      venueLimit += 10;
      paint();
    });

    root.querySelectorAll('[data-toggle-scene]').forEach(btn => {
      btn.addEventListener('click', () => {
        const sid = Number(btn.dataset.toggleScene);
        expandedSceneId = (expandedSceneId === sid) ? null : sid;
        paint();
      });
    });

    root.querySelector('#btnMoreScenes')?.addEventListener('click', () => {
      sceneLimit += 10;
      paint();
    });

    root.querySelector('#btnLessScenes')?.addEventListener('click', () => {
      sceneLimit = 10;
      paint();
    });

    root.querySelector('#btnVenuesCsv')?.addEventListener('click', () => {
      if (venuesCsvSpec) triggerTableCsvExport(venuesCsvSpec);
    });

    root.querySelectorAll('[data-cal-mode]').forEach(btn => {
      btn.addEventListener('click', () => {
        calMode = btn.dataset.calMode === 'all' ? 'all' : 'cand';
        appState.venuesCalMode = calMode;
        calLimit = 8;
        syncHash(true);
        paint();
      });
    });

    root.querySelector('#btnMoreCal')?.addEventListener('click', () => {
      calLimit += 12;
      paint();
    });
    root.querySelector('#btnLessCal')?.addEventListener('click', () => {
      calLimit = 8;
      paint();
    });

    const cumFold = root.querySelector('#venueCumFold');
    if (cumFold) {
      cumFold.addEventListener('toggle', () => {
        if (cumFold.open) renderCumulativeChart();
      });
    }
  }

  paint();
  if (expandedSceneId !== null) {
    root.querySelector(`[data-scene-id="${expandedSceneId}"]`)?.scrollIntoView({ block: 'center' });
  }
}
