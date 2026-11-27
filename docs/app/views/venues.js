import { appState, registerChart, setExportContext } from '../state.js';
import {
  buildNextGigByTeam, groupUpcomingEvents, queryCandidates,
  queryMonthlyNewcomerVenues, queryUpcomingGigs,
} from '../db.js';
import {
  avatarHtml, cssVar, escapeHtml, fmtInt, fmtNum, formatKoreanShortDate,
  formatNextGigText, plainWhyLine, renderActionBanner, spotifyButtonHtml,
  wireAvatarFallbacks, wireSpotifyButtons,
} from '../ui.js';

export async function renderVenuesView(root) {
  const asOf = appState.cfg.as_of || appState.dataEnd || '2026-11-27';
  const [candRows, upcomingRaw] = await Promise.all([
    queryCandidates({ limit: 300 }),
    queryUpcomingGigs({ asOf }),
  ]);
  const monthly = await queryMonthlyNewcomerVenues(candRows, asOf);

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

  const dj = appState.dashboardJson;
  const allTimeVenues = dj?.sections?.top_venues || [];
  const topMonthV = monthly.venues[0];

  setExportContext({
    csvLabel: monthly.venues.length
      ? `${monthly.monthLabel} 공연장·씬 CSV 내려받기 (${fmtInt(monthly.venues.length)}곳)`
      : '',
    csvFilename: `crate_digger_venues_${monthly.ym || appState.dataEnd || 'export'}.csv`,
    csvHeaders: ['rank', 'venue', 'candidate_teams', 'total_teams', 'month_gigs', 'candidate_ratio_pct', 'top_candidates'],
    csvRows: monthly.venues.map((v, idx) => [
      idx + 1,
      v.venue,
      v.candidateCount,
      v.totalTeams,
      v.monthGigs,
      v.candidateRatio.toFixed(1),
      v.candidates.slice(0, 5).map(c => `${c.display_name}(#${c.rank})`).join(' / '),
    ]),
  });

  const bannerHtml = renderActionBanner({
    title: '공연장·씬',
    lead: topMonthV
      ? `${escapeHtml(monthly.monthLabel)} 신인 후보가 가장 많이 선 공연장은 <strong>${escapeHtml(topMonthV.venue)}</strong>(후보 ${fmtInt(topMonthV.candidateCount)}팀 · 전체 ${fmtInt(topMonthV.totalTeams)}팀)이며, 예정된 후보 무대는 <strong>${fmtInt(candUpcomingEvents.length)}건</strong>입니다.`
      : '이번 달 공연장 요약 데이터를 불러오는 중입니다.',
  });

  let venueLimit = 8;
  let expandedVenue = '';
  let calMode = 'cand'; // 'cand' | 'all'
  let calLimit = 8;
  let chartRendered = false;

  function renderVenueRow(v, idx) {
    const isOpen = expandedVenue === v.venue;
    const previewCands = v.candidates.slice(0, 4);
    const bodyCands = v.candidates.slice(0, 10);
    const extraCands = v.candidates.length - bodyCands.length;

    return `
      <li class="venue-acc-item ${isOpen ? 'is-open' : ''}">
        <button type="button" class="venue-acc-head" data-toggle-venue="${escapeHtml(v.venue)}" aria-expanded="${isOpen ? 'true' : 'false'}">
          <div class="venue-acc-left">
            <span class="venue-rank">#${idx + 1}</span>
            <div class="venue-acc-title-col">
              <strong class="venue-name">${escapeHtml(v.venue)}</strong>
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
        </button>
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
            ${extraCands > 0 ? `<p class="small muted" style="margin:8px 0 0 0;">외 후보 ${fmtInt(extraCands)}팀이 이번 달 이 무대에 섰습니다.</p>` : ''}
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
                return `
                  <li class="upcoming-row cal-event-row">
                    <div class="upcoming-when">
                      <span class="upcoming-venue">${escapeHtml(ev.venue)}</span>
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

  function renderCumulativeChart() {
    if (chartRendered || !window.Chart || !allTimeVenues.length) return;
    const cv = root.querySelector('#venuesChart');
    if (!cv) return;
    chartRendered = true;
    const inkMuted = cssVar('--ink-muted');
    const lineColor = cssVar('--line');
    registerChart(new window.Chart(cv.getContext('2d'), {
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

  function paint() {
    chartRendered = false;
    const visVenues = monthly.venues.slice(0, venueLimit);
    const remVenues = monthly.venues.length - visVenues.length;

    root.innerHTML = `
      ${bannerHtml}

      <section class="block" id="monthlyVenuesBlock">
        <div class="block-head">
          <div>
            <h2>이번 달 신인이 많이 선 공연장 TOP</h2>
            <span class="block-meta">${escapeHtml(monthly.monthLabel)} 기준 · 공연장을 누르면 출연한 상위 후보가 펼쳐집니다</span>
          </div>
          <span class="block-meta">${fmtInt(monthly.venues.length)}곳</span>
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
      btn.addEventListener('click', () => {
        const v = btn.dataset.toggleVenue;
        expandedVenue = (expandedVenue === v) ? '' : v;
        paint();
      });
    });

    root.querySelector('#btnMoreVenues')?.addEventListener('click', () => {
      venueLimit += 10;
      paint();
    });

    root.querySelectorAll('[data-cal-mode]').forEach(btn => {
      btn.addEventListener('click', () => {
        calMode = btn.dataset.calMode;
        calLimit = 8;
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
}
