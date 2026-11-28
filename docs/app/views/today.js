/**
 * 정보 구조 v2 '홈' (#/home) — 판단할 것만 간결하게 (상세는 각 메뉴로 연결)
 * 1. 이번 주 한 줄 (알림 핵심 건수 + 기준일)
 * 2. [처음이면] 할 일 3장 (관심 팀 추가 · 필터 저장 · 공연장 구독 — 완료 시 자동 숨김)
 * 3. 알림 요약 (별 많은 순 5줄 + 모두 보기 → #/alerts)
 * 4. 내 저장 필터에 새로 들어온 팀 (#/mine?tab=filters) + 구독 공연장 소식 (#/mine?tab=venues)
 * 5. 차트 맛보기: 떠오르는 5 (#/charts/rising) | 갓 데뷔 5 (#/charts/debut)
 * 6. 이번 주 다가오는 공연 (관심 팀 · 구독 공연장 먼저)
 * 7. 근거 줄 (데이터 갱신 시각 · 수집 이상 배너(조용할 때 숨김) · 검증 성적 → #/verify)
 */
import {
  appState, getWatchlist, hasCustomWeights, setExportContext,
} from '../state.js';
import {
  buildNextGigByTeam, getSnapshotDiff, groupUpcomingEvents,
  loadAlertsJson, loadScoreTuningSummary, queryCandidates, queryDebutCandidates, queryRisingPreset,
  queryUpcomingGigs, queryWeeklyDigestExtras,
} from '../db.js';
import { loadEventStars } from '../db_team_extras.js';
import { listVenueSubs } from '../venue_subs.js';
import {
  avatarHtml, buildWeeklySummaryText, escapeHtml, fmtInt, fmtNum,
  formatKoreanShortDate, formatNextGigText, spotifyButtonHtml,
  watchButtonHtml, wireAvatarFallbacks, wireSpotifyButtons,
} from '../ui.js';
import { alertsCarryStars, renderHomeAlertsSummaryHtml } from './today_alerts.js';
import { fillSavedCard, renderSavedCardShellHtml } from './today_saved.js';
import { renderVenueSubsHtml } from './venue_subs_view.js';
import { renderOnboardingStripHtml } from '../components/onboarding_cards.js';
import { renderEvidenceFooterHtml } from './mine.js';
import { homeChartRowHtml } from '../home_chart_rows.js';

const HEADLINE_ALERT_TYPES = [
  ['new_outcome', '새 정답'],
  ['new_selection', '새 선정·지원'],
  ['blank_first_mention', '백지 신인 첫 언급'],
  ['stage_up', '단계 상승'],
];

function buildWeeklyOneLineHtml(alertsData, diff) {
  const counts = alertsData?.counts_found || alertsData?.counts_shown || {};
  const parts = [];
  for (const [key, fallbackLabel] of HEADLINE_ALERT_TYPES) {
    const n = Number(counts[key]) || 0;
    if (n > 0) {
      const label = alertsData?.types?.[key] || fallbackLabel;
      parts.push(`<span>${escapeHtml(label)} <strong>${fmtInt(n)}</strong></span>`);
    }
  }
  if (!parts.length && diff.newEntrants.length > 0) {
    parts.push(`<span>새 후보 <strong>${fmtInt(diff.newEntrants.length)}</strong>팀</span>`);
  }
  if (!parts.length) {
    return '<span class="muted">이번 주 집계된 주요 변동 알림이 없습니다.</span>';
  }
  return parts.join('<span class="home-dot" aria-hidden="true">·</span>');
}

function buildSnapshotSublineHtml(diff, extras) {
  const bits = [];
  if (diff.newEntrants.length > 0) bits.push(`새 후보 ${fmtInt(diff.newEntrants.length)}팀`);
  const topRiser = diff.risers[0];
  if (topRiser) {
    bits.push(
      `최대 상승 <a class="inline-team-link" href="#/team/${encodeURIComponent(topRiser.team_key)}"><strong>${escapeHtml(topRiser.display_name)}</strong></a> (#${topRiser.rank_prev}→#${topRiser.rank_now})`
    );
  }
  if (extras?.signalStats?.total > 0) {
    bits.push(`최근 7일 새 신호 ${fmtInt(extras.signalStats.total)}건`);
  }
  return bits.join(' · ');
}

function renderRisingPreviewHtml(rows) {
  const top = (rows || []).slice(0, 5);
  if (!top.length) {
    return '<p class="small muted" style="margin:0;">최근 30일 상승 조건에 맞는 팀이 아직 없습니다.</p>';
  }
  return `
    <ol class="home-chart-list">
      ${top.map((r, idx) => {
        const name = r.display_name || r.team_key;
        const metricBits = [];
        if (r.recent_n > 0) metricBits.push(`30일 ${fmtInt(r.recent_n)}건`);
        if (r.growth !== null && r.growth !== undefined && Number.isFinite(r.growth)) {
          metricBits.push(`${r.growth.toFixed(1)}배`);
        } else if (r.prev_n === 0 && r.recent_n > 0) {
          metricBits.push('신규 급증');
        }
        return homeChartRowHtml(idx, { team_key: r.team_key, name, genre: r.primary_genre, metric: metricBits.join(' · ') });
      }).join('')}
    </ol>
  `;
}

function renderDebutPreviewHtml(debutData) {
  const mentioned = Array.isArray(debutData?.mentioned) ? debutData.mentioned : [];
  const unmentioned = Array.isArray(debutData?.unmentioned) ? debutData.unmentioned : [];
  const top = [...mentioned, ...unmentioned].slice(0, 5);
  if (!top.length) {
    return '<p class="small muted" style="margin:0;">최근 12개월 첫 발매 신인 기록이 아직 없습니다.</p>';
  }
  return `
    <ol class="home-chart-list">
      ${top.map((t, idx) => {
        const name = t.display_name || t.team_key;
        const mCnt = Array.isArray(t.mentions) ? t.mentions.length : 0;
        const metric = mCnt > 0
          ? `언급 ${fmtInt(mCnt)}곳`
          : (t.first_release ? `발매 ${String(t.first_release).slice(0, 10)}` : '언급 전');
        return homeChartRowHtml(idx, { team_key: t.team_key, name, genre: t.primary_genre, metric });
      }).join('')}
    </ol>
  `;
}

// 사건 별점(event_stars.csv, 약 2.4MB)은 알림 요약의 별 표시에만 쓰므로 화면을 막지 않고 뒤에서 받는다 (속도 점검 2026-11-28)
let homeEventStars;           // undefined = 아직, null = 없음, Map = 받음

export async function renderTodayView(root) {
  const asOf = appState.cfg.as_of || appState.dataEnd || '2026-11-28';
  const [candRows, upcomingRaw, risingRows, debutData, alertsData, eventStarsMap, tuningSummary] = await Promise.all([
    queryCandidates({ limit: 300 }),
    queryUpcomingGigs({ asOf, days: 14 }),
    queryRisingPreset({ as_of: asOf }).catch(() => []),
    queryDebutCandidates({ as_of: asOf }).catch(() => null),
    loadAlertsJson().catch(() => null),
    Promise.resolve(homeEventStars === undefined ? null : homeEventStars),
    loadScoreTuningSummary().catch(() => null),   // 근거 줄 '점수 성적' 한 줄 (같은 기준 판 나란히)
  ]);
  // 홈 화면엔 영상이 안 보이므로 영상 표(videos.csv)를 받지 않는다. 브리핑 글의 '새 무대 영상 수'는 복사할 때 채움(app.js digest)
  const extras = await queryWeeklyDigestExtras(candRows, { videos: false });

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
  const upcomingCandEvents = groupUpcomingEvents(upcomingRaw, candRankMap).filter(ev => ev.hasCandidate);
  const upcomingCandTeamSet = new Set();
  for (const ev of upcomingCandEvents) {
    for (const t of ev.candidateTeams) upcomingCandTeamSet.add(t.team_key);
  }

  const top5 = candRows.slice(0, 5);
  const diff = getSnapshotDiff(candRows);
  const customW = hasCustomWeights();
  const health = appState.dataHealth || { ok: true, totalSources: 0, okSources: 0, summaryLabel: '수집 정상' };

  // Register unified export context (weekly digest text + top 100 candidates CSV)
  const digestText = extras.newVideos7d == null ? null : buildWeeklySummaryText({
    dataEnd: appState.dataEnd,
    prevDate: diff.prevDate,
    latestDate: diff.latestDate,
    newEntrants: diff.newEntrants,
    risers: diff.risers,
    signalStats: extras.signalStats,
    newVideos7d: extras.newVideos7d,
    top5,
    health,
  });
  if (digestText == null) appState.weeklyDigestText = ''; // 예전 글이 남지 않게 — 복사할 때 새로 만듦
  setExportContext({
    digestText,
    csvLabel: '상위 후보 100팀 CSV 내려받기',
    csvFilename: `crate_digger_top100_${appState.dataEnd || 'export'}.csv`,
    csvHeaders: ['rank', 'team_key', 'display_name', 'genre', 'score', 'n_branch', 'venues', 'recent180', 'next_gig', 'first_seen', 'last_seen'],
    csvRows: candRows.slice(0, 100).map((r, i) => [
      i + 1,
      r.team_key,
      r.display_name || r.team_key,
      r.primary_genre || '',
      r.score ?? '',
      r.n_branch ?? 0,
      r.venues ?? 0,
      r.recent180 ?? 0,
      formatNextGigText(nextGigByTeam.get(r.team_key)),
      r.first_seen || '',
      r.last_seen || '',
    ]),
  });

  let upcomingLimit = 5;

  const periodLabel = alertsData?.snapshots?.before && alertsData?.as_of
    ? `${alertsData.snapshots.before} → ${alertsData.as_of}`
    : (diff.prevDate && diff.latestDate ? `${diff.prevDate} → ${diff.latestDate}` : `기준 ${asOf}`);

  const weeklyOneLineHtml = buildWeeklyOneLineHtml(alertsData, diff);
  const snapshotSublineHtml = buildSnapshotSublineHtml(diff, extras);
  const debutTotal = debutData?.total || 0;
  const debutMent = debutData?.mentioned?.length || 0;

  function paint() {
    const watchKeys = new Set(getWatchlist().map(w => w.team_key));
    const subVenues = new Set(listVenueSubs());

    // Prioritize upcoming events involving watched teams or subscribed venues
    const prioritizedUpcoming = upcomingCandEvents
      .map((ev, origIdx) => {
        const hasWatched = ev.candidateTeams.some(t => watchKeys.has(t.team_key))
          || ev.otherTeams.some(t => watchKeys.has(t.team_key));
        const isSubVenue = subVenues.has(String(ev.venue || '').trim());
        const priority = (hasWatched ? 2 : 0) + (isSubVenue ? 1 : 0);
        return { ev, origIdx, hasWatched, isSubVenue, priority };
      })
      .sort((a, b) => (b.priority > 0 ? 1 : 0) - (a.priority > 0 ? 1 : 0) || b.priority - a.priority || a.origIdx - b.origIdx);

    const visUpcoming = prioritizedUpcoming.slice(0, upcomingLimit);
    const remUpcoming = prioritizedUpcoming.length - visUpcoming.length;

    const headlineHtml = `
      <section class="home-headline" aria-label="이번 주 한 줄 요약">
        <div class="home-headline-top">
          <div class="home-headline-kicker">
            <h1 class="home-headline-title">이번 주 브리핑</h1>
            <span class="home-date-tag mono">${escapeHtml(periodLabel)}</span>
            ${customW ? '<span class="briefing-tag">사용자 가중치</span>' : ''}
          </div>
          <div class="home-headline-actions">
            <a class="btn btn-sm" href="#/alerts">알림 센터</a>
            <a class="btn btn-sm btn-primary" href="#/discover">발굴 열기</a>
          </div>
        </div>
        <p class="home-one-line">${weeklyOneLineHtml}</p>
        ${snapshotSublineHtml ? `<p class="home-sub-line small muted">${snapshotSublineHtml}</p>` : ''}
      </section>
    `;

    const alertsSummaryHtml = renderHomeAlertsSummaryHtml(alertsData, {
      eventStarsMap,
      watchKeys,
      subVenues,
      limit: 5,
    });
    // alerts.json 알림마다 stars 칸이 있으면 별점 파일을 받을 필요가 없다
    if (homeEventStars === undefined && !alertsCarryStars(alertsData)) {
      loadEventStars().then(m => {
        homeEventStars = m || null;
        const el = root.querySelector('#todayAlertsBlock');
        if (!m || !el || !root.isConnected) return;
        el.outerHTML = renderHomeAlertsSummaryHtml(alertsData, { eventStarsMap: m, watchKeys, subVenues, limit: 5 });
      }).catch(() => { homeEventStars = null; });
    }

    const venueSubsRaw = renderVenueSubsHtml(alertsData, { title: '구독 공연장 소식' });
    const venueSubsSectionHtml = venueSubsRaw
      ? `<div class="home-venue-subs-wrap">${venueSubsRaw}<div class="home-venue-subs-foot"><a class="home-more-link" href="#/mine?tab=venues">구독 공연장 관리 →</a></div></div>`
      : '';

    const chartsPreviewHtml = `
      <section class="home-charts-section" aria-label="차트 맛보기">
        <div class="home-charts-grid">
          <article class="block home-chart-card">
            <div class="block-head">
              <div>
                <h2>떠오르는 5</h2>
                <span class="block-meta">최근 30일 신호 증가 · 소형 무대 위주</span>
              </div>
              <a class="home-more-link" href="#/charts/rising">전체 보기 →</a>
            </div>
            ${renderRisingPreviewHtml(risingRows)}
          </article>

          <article class="block home-chart-card">
            <div class="block-head">
              <div>
                <h2>갓 데뷔 5</h2>
                <span class="block-meta">${debutTotal > 0 ? `최근 12개월 첫 발매 ${fmtInt(debutTotal)}팀 · 언급 ${fmtInt(debutMent)}팀` : '최근 12개월 첫 발매 백지 신인'}</span>
              </div>
              <a class="home-more-link" href="#/charts/debut">전체 보기 →</a>
            </div>
            ${renderDebutPreviewHtml(debutData)}
          </article>
        </div>

        <nav class="home-quick-links" aria-label="빠른 이동">
          <a class="home-quick-link" href="#/discover">발굴 · 전체 후보 (${fmtInt(candRows.length)}) →</a>
          <a class="home-quick-link" href="#/charts">차트 순위표 →</a>
          <a class="home-quick-link" href="#/venues">공연장 목록 →</a>
          <a class="home-quick-link" href="#/cities">도시별 씬 →</a>
          <a class="home-quick-link" href="#/festivals">페스티벌 →</a>
        </nav>
      </section>
    `;

    const upcomingHtml = prioritizedUpcoming.length
      ? `
        <section class="block" id="todayUpcomingBlock" aria-label="이번 주 다가오는 공연">
          <div class="block-head">
            <div>
              <h2>이번 주 다가오는 공연</h2>
              <span class="block-meta">관심 팀·구독 공연장 먼저 · 2주 내 후보 ${fmtInt(upcomingCandTeamSet.size)}팀 · ${fmtInt(prioritizedUpcoming.length)}개 무대</span>
            </div>
            <a class="home-more-link" href="#/venues">공연장·달력 보기 →</a>
          </div>
          <ul class="upcoming-list">
            ${visUpcoming.map(({ ev, hasWatched, isSubVenue }) => {
              const dtLabel = formatKoreanShortDate(ev.signal_date);
              const multiCand = ev.candidateTeams.length >= 2;
              const otherNames = ev.otherTeams.slice(0, 3).map(t => t.display_name);
              const otherMore = ev.otherTeams.length - otherNames.length;
              const coBillHtml = ev.otherTeams.length > 0
                ? `<div class="cobill-note"><span class="cobill-lbl">함께 서는 팀</span> ${escapeHtml(otherNames.join(', '))}${otherMore > 0 ? ` 외 ${fmtInt(otherMore)}팀` : ''}</div>`
                : '';
              const prioTags = [
                hasWatched ? '<span class="home-prio-tag">관심 팀</span>' : '',
                isSubVenue ? '<span class="home-prio-tag">구독 공연장</span>' : '',
              ].filter(Boolean).join('');
              return `
                <li class="upcoming-row${hasWatched || isSubVenue ? ' is-priority' : ''}">
                  <div class="upcoming-when">
                    <span class="upcoming-date">${escapeHtml(dtLabel)}</span>
                    <a class="upcoming-venue inline-venue-link" href="#/venue/${encodeURIComponent(ev.venue)}">${escapeHtml(ev.venue)}</a>
                    ${prioTags}
                    ${multiCand ? `<span class="cobill-badge">후보 ${ev.candidateTeams.length}팀 함께 서는 무대</span>` : ''}
                  </div>
                  <div class="upcoming-teams-wrap">
                    <div class="upcoming-teams">
                      ${ev.candidateTeams.map(t => `
                        <div class="upcoming-team-chip">
                          <a class="upcoming-team-link" href="#/team/${encodeURIComponent(t.team_key)}">
                            ${avatarHtml(t.team_key, t.display_name, 28, { shape: 'circle', genre: t.primary_genre })}
                            <strong>${escapeHtml(t.display_name)}</strong>
                            <span class="rank-pill">#${t.rank}</span>
                          </a>
                          ${spotifyButtonHtml(t.team_key, true, { iconOnly: true, teamName: t.display_name, slotId: 'todayUpcomingPlayerSlot' })}
                        </div>
                      `).join('')}
                    </div>
                    ${coBillHtml}
                  </div>
                </li>
              `;
            }).join('')}
          </ul>
          <div class="player-slot" id="todayUpcomingPlayerSlot" data-player-slot></div>
          ${remUpcoming > 0
            ? `<div class="more-row" style="margin-top:10px;">
                 <span>${fmtInt(visUpcoming.length)} / ${fmtInt(prioritizedUpcoming.length)}개 무대</span>
                 <button type="button" class="btn btn-sm" id="btnMoreUpcoming">${fmtInt(Math.min(10, remUpcoming))}건 더 보기</button>
               </div>`
            : (upcomingLimit > 5 && prioritizedUpcoming.length > 5
                ? `<div class="more-row" style="margin-top:10px;">
                     <span>전체 ${fmtInt(prioritizedUpcoming.length)}개 무대 표시 중</span>
                     <button type="button" class="btn btn-sm" id="btnLessUpcoming">접기</button>
                   </div>`
                : '')}
        </section>
      `
      : '';

    const healthWarnBannerHtml = !health.ok
      ? `
        <section class="home-health-warn" role="status" aria-label="데이터 수집 이상 안내">
          <strong>수집 점검 필요:</strong>
          <span>${escapeHtml(health.summaryLabel || '일부 출처 수집 상태를 확인해 주세요.')}</span>
          <a href="#/verify/quality">데이터 품질 보기 →</a>
        </section>
      `
      : '';

    root.innerHTML = `
      <div class="home-page" id="homePageRoot">
        ${headlineHtml}
        ${renderOnboardingStripHtml()}
        <div id="todayAlertsHost">${alertsSummaryHtml}</div>
        ${renderSavedCardShellHtml()}
        ${venueSubsSectionHtml}
        ${chartsPreviewHtml}
        ${upcomingHtml}
        ${healthWarnBannerHtml}
        ${renderEvidenceFooterHtml({ extraNote: tuningSummary?.fairShort || '' })}
      </div>
    `;

    wireAvatarFallbacks(root);
    wireSpotifyButtons(root);
    fillSavedCard(root);

    root.querySelector('#btnMoreUpcoming')?.addEventListener('click', () => { upcomingLimit += 10; paint(); });
    root.querySelector('#btnLessUpcoming')?.addEventListener('click', () => { upcomingLimit = 5; paint(); });
  }

  paint();

  // Live-update alerts summary, onboarding cards & priority upcoming gigs on watchlist / venue sub changes
  const onWatchChange = () => {
    const host = root.querySelector('#homePageRoot');
    if (!host || !host.isConnected) {
      window.removeEventListener('app:watchlist', onWatchChange);
      window.removeEventListener('app:venue-subs', onWatchChange);
      return;
    }
    paint();
  };
  window.addEventListener('app:watchlist', onWatchChange);
  window.addEventListener('app:venue-subs', onWatchChange);
}
