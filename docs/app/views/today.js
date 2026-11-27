import {
  appState, getWatchlist, hasCustomWeights, navigateTo, setExportContext,
} from '../state.js';
import {
  buildNextGigByTeam, getSnapshotDiff, groupUpcomingEvents,
  loadAlertsJson, queryCandidates, queryDebutCandidates, queryUpcomingGigs,
  queryWatchlistEnriched, queryWeeklyDigestExtras,
} from '../db.js';
import {
  avatarHtml, buildWeeklySummaryText,
  escapeHtml, fmtInt, fmtNum,
  formatKoreanShortDate, formatNextGigText,
  getWatchlistAlerts, INFO_TIPS, infoTip, plainWhyLine, renderEmptyState,
  spotifyButtonHtml, watchButtonHtml, wireAvatarFallbacks, wireSpotifyButtons,
  youtubeQuickInfo,
} from '../ui.js';
import { renderAlertsCardHtml, renderSpikeSentencesHtml } from './today_alerts.js';
import { fillSavedCard, renderSavedCardShellHtml } from './today_saved.js';
import { loadEventStars } from '../db_team_extras.js';

function renderCardListenAction(r) {
  const sp = spotifyButtonHtml(r.team_key, true, {
    teamName: r.display_name || r.team_key,
    slotId: 'todayTopPlayerSlot',
  });
  if (sp) return sp;

  const yt = youtubeQuickInfo(r.team_key);
  if (yt && yt.kind === 'channel') {
    return `<a class="btn btn-sm" href="${escapeHtml(yt.url)}" target="_blank" rel="noopener noreferrer">유튜브 채널</a>`;
  }
  if (yt && yt.kind === 'video') {
    return `<a class="btn btn-sm" href="#/team/${encodeURIComponent(r.team_key)}">▶ 영상 ${fmtInt(yt.count)}</a>`;
  }
  return `<a class="btn btn-sm" href="#/team/${encodeURIComponent(r.team_key)}">상세 보기</a>`;
}

export async function renderTodayView(root) {
  const asOf = appState.cfg.as_of || appState.dataEnd || '2026-11-27';
  const [candRows, watchEnriched, upcomingRaw, debutData, alertsData, eventStarsMap] = await Promise.all([
    queryCandidates({ limit: 300 }),
    queryWatchlistEnriched(getWatchlist()),
    queryUpcomingGigs({ asOf, days: 14 }),
    queryDebutCandidates({ as_of: asOf }).catch(() => null),
    loadAlertsJson().catch(() => null),
    loadEventStars(),
  ]);
  const extras = await queryWeeklyDigestExtras(candRows);

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
  const watchActive = watchEnriched.filter(w => w.recent_7d > 0);
  const customW = hasCustomWeights();
  const health = appState.dataHealth;
  const isReconstructed = Boolean(
    diff.prevDate && (appState.snapshots.reconstructed || []).includes(diff.prevDate)
  );

  // Register unified export context (weekly digest text + top 100 candidates CSV)
  const digestText = buildWeeklySummaryText({
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
  let showAllNew = false;
  let showAllRisers = false;
  let showAllWatchAlerts = false;
  const expandedAlertTypes = new Set();

  // Build plain-Korean weekly briefing narrative
  const topRiser = diff.risers[0];
  const brSummary = Object.entries(extras.signalStats.byBranch || {})
    .filter(([, n]) => n > 0)
    .slice(0, 3)
    .map(([b, n]) => `${b} ${fmtInt(n)}`)
    .join(' · ');

  const sentence1Parts = [];
  if (diff.newEntrants.length > 0 || topRiser) {
    const newTxt = `이번 주 새로 들어온 후보는 <strong>${fmtInt(diff.newEntrants.length)}팀</strong>`;
    if (topRiser) {
      const gainParts = [];
      if (topRiser.rank_gain > 0) gainParts.push(`+${fmtInt(topRiser.rank_gain)}계단`);
      if (topRiser.score_gain > 0) gainParts.push(`+${fmtNum(topRiser.score_gain, 2)}점`);
      sentence1Parts.push(
        `${newTxt}이고, 가장 크게 오른 팀은 <a class="inline-team-link" href="#/team/${encodeURIComponent(topRiser.team_key)}"><strong>${escapeHtml(topRiser.display_name)}</strong></a>(#${topRiser.rank_prev}→#${topRiser.rank_now}${gainParts.length ? `, ${gainParts.join(' · ')}` : ''})입니다.`
      );
    } else {
      sentence1Parts.push(`${newTxt}입니다.`);
    }
  } else if (top5.length) {
    sentence1Parts.push(`현재 신인 후보 1위는 <a class="inline-team-link" href="#/team/${encodeURIComponent(top5[0].team_key)}"><strong>${escapeHtml(top5[0].display_name)}</strong></a>(${fmtNum(top5[0].score, 2)}점)입니다.`);
  } else {
    sentence1Parts.push('현재 조건에 맞는 후보 팀이 없습니다.');
  }

  const sentence2Parts = [];
  if (extras.signalStats.total > 0) {
    sentence2Parts.push(`최근 7일간 새 신호 <strong>${fmtInt(extras.signalStats.total)}건</strong>${brSummary ? `(${brSummary})` : ''}`);
  }
  if (upcomingCandEvents.length > 0) {
    sentence2Parts.push(`2주 내 볼 수 있는 후보 공연 <strong>${fmtInt(upcomingCandEvents.length)}건</strong>(${fmtInt(upcomingCandTeamSet.size)}팀)이 잡혔고`);
  } else if (extras.newVideos7d > 0) {
    sentence2Parts.push(`새 무대 영상 <strong>${fmtInt(extras.newVideos7d)}개</strong>가 잡혔고`);
  }
  const healthTxt = health.ok
    ? (health.totalSources > 0 ? `데이터 수집은 정상(${health.okSources}/${health.totalSources} 출처)입니다.` : '데이터 수집은 정상입니다.')
    : `<a href="#/quality"><strong>${escapeHtml(health.summaryLabel)}</strong></a> 상태입니다.`;
  const sentence2 = sentence2Parts.length ? `${sentence2Parts.join('과 ')}, ${healthTxt}` : healthTxt;

  const periodPill = diff.prevDate && diff.latestDate
    ? `${diff.prevDate} → ${diff.latestDate}`
    : `기준 ${appState.dataEnd}`;

  const heroHtml = `
    <section class="briefing-hero" aria-label="주간 브리핑 요약">
      <div class="briefing-hero-head">
        <div>
          <div class="briefing-kicker">
            <span class="briefing-date-pill">${escapeHtml(periodPill)}</span>
            ${customW ? '<span class="briefing-tag">사용자 가중치 적용 중</span>' : ''}
          </div>
          <h1 class="briefing-title">이번 주 브리핑</h1>
        </div>
        <div class="briefing-hero-actions">
          <a class="btn" href="#/candidates">전체 후보 보기 (${fmtInt(candRows.length)})</a>
        </div>
      </div>
      <p class="briefing-narrative">${sentence1Parts.join(' ')} ${sentence2}</p>
      <div class="briefing-kpis">
        <div class="kpi-chip">
          <span class="kpi-chip-lbl">새 후보</span>
          <strong class="kpi-chip-val">${fmtInt(diff.newEntrants.length)}팀</strong>
        </div>
        <div class="kpi-chip">
          <span class="kpi-chip-lbl">순위·점수 상승</span>
          <strong class="kpi-chip-val">${fmtInt(diff.risers.length)}팀</strong>
        </div>
        <a class="kpi-chip" href="#/venues">
          <span class="kpi-chip-lbl">2주 내 후보 공연</span>
          <strong class="kpi-chip-val">${fmtInt(upcomingCandEvents.length)}건</strong>
        </a>
        <div class="kpi-chip">
          <span class="kpi-chip-lbl">최근 7일 새 신호</span>
          <strong class="kpi-chip-val">${fmtInt(extras.signalStats.total)}건</strong>
        </div>
        ${watchActive.length > 0 ? `
          <a class="kpi-chip kpi-chip-accent" href="#/watchlist">
            <span class="kpi-chip-lbl">관심 팀 새 신호</span>
            <strong class="kpi-chip-val">${fmtInt(watchActive.length)}팀</strong>
          </a>
        ` : ''}
      </div>
    </section>
  `;

  const hasAnyTop5Img = top5.some(r => appState.imagesByTeam.has(r.team_key));
  const top5Html = top5.length
    ? `<div class="grid-5">${top5.map((r, i) => {
        const ng = nextGigByTeam.get(r.team_key);
        return `
          <article class="pick-card">
            <div class="pick-top">
              <span class="pick-rank">#${i + 1}${r.primary_genre ? ` · ${escapeHtml(r.primary_genre)}` : ''}</span>
              <span class="pick-score" title="종합 점수">${fmtNum(r.score, 2)}</span>
            </div>
            <a class="pick-head" href="#/team/${encodeURIComponent(r.team_key)}">
              ${avatarHtml(r.team_key, r.display_name, 48, { shape: 'rounded', genre: r.primary_genre })}
              <span class="pick-name">${escapeHtml(r.display_name || r.team_key)}</span>
            </a>
            <p class="pick-why">${escapeHtml(plainWhyLine(r))}</p>
            ${ng ? `<div class="pick-next-gig">다음 공연 ${escapeHtml(formatNextGigText(ng))}</div>` : ''}
            <div class="pick-foot">
              ${renderCardListenAction(r)}
              ${watchButtonHtml(r.team_key, r.display_name || r.team_key, true, true)}
            </div>
          </article>
        `;
      }).join('')}</div>
      <div class="player-slot" id="todayTopPlayerSlot" data-player-slot></div>
      ${hasAnyTop5Img ? '<p class="photo-credit">아티스트 사진 출처: Spotify</p>' : ''}`
    : renderEmptyState({
        title: '조건에 맞는 상위 후보가 없습니다',
        message: '후보 목록에서 조건을 줄여 보거나 초기화해 전체 후보를 확인해 보세요.',
        showReset: true,
      });

  const snapNoteParts = [];
  if (diff.latestDate && diff.prevDate) {
    snapNoteParts.push(`${diff.prevDate} → ${diff.latestDate}`);
    if (customW) snapNoteParts.push('기본 점수 기준');
    if (isReconstructed) snapNoteParts.push(`${diff.prevDate} 점수는 당시 신호 기준 재계산`);
  }
  const snapNote = snapNoteParts.join(' · ');

  const recentVideosHtml = extras.recentStageVideos.length
    ? `
      <section class="block">
        <div class="block-head">
          <h2>최근 올라온 무대 영상</h2>
          <span class="block-meta">상위 후보 최근 영상 · 누르면 바로 재생</span>
        </div>
        <div class="recent-videos-grid">
          ${extras.recentStageVideos.map(v => {
            const thumb = `https://i.ytimg.com/vi/${v.video_id}/hqdefault.jpg`;
            return `
              <article class="video-card">
                <button type="button" class="video-frame" data-video-id="${escapeHtml(v.video_id)}" aria-label="${escapeHtml(v.display_name)} 영상 재생">
                  <img src="${thumb}" alt="${escapeHtml(v.title || v.display_name)}" loading="lazy" decoding="async">
                  <span class="video-play-btn" aria-hidden="true"></span>
                </button>
                <div class="video-card-body">
                  <div class="video-card-team">
                    <a href="#/team/${encodeURIComponent(v.team_key)}"><strong>${escapeHtml(v.display_name)}</strong></a>
                    <span class="small muted">#${v.rank}${v.published_at ? ` · ${escapeHtml(String(v.published_at).slice(0, 10))}` : ''}</span>
                  </div>
                  <div class="video-title" title="${escapeHtml(v.title)}">${escapeHtml(v.title || '무대 영상')}</div>
                </div>
              </article>
            `;
          }).join('')}
        </div>
      </section>
    `
    : '';

  // Conditional watchlist block: COMPLETELY HIDDEN when watchlist is empty ("할 일을 만들지 않기")
  const watchBlockHtml = watchEnriched.length > 0
    ? `
      <section class="block">
        <div class="block-head">
          <h2>관심 팀 최근 7일 소식</h2>
          <a class="small muted" href="#/watchlist">관심 목록 전체 (${fmtInt(watchEnriched.length)}) →</a>
        </div>
        ${watchActive.length
          ? `<ul class="mini-list">${watchActive.slice(0, 5).map(w => `
              <li>
                <div class="mini-list-row">
                  ${avatarHtml(w.team_key, w.display_name, 28, { shape: 'circle', genre: w.primary_genre })}
                  <div class="mini-list-main">
                    <a href="#/team/${encodeURIComponent(w.team_key)}"><strong>${escapeHtml(w.display_name)}</strong></a>
                    <div class="mini-list-sub">최근 7일 새 신호 <strong>${fmtInt(w.recent_7d)}건</strong> · 마지막 기록 ${escapeHtml(w.last_seen || '-')}</div>
                  </div>
                </div>
                <div class="mini-list-actions">
                  ${spotifyButtonHtml(w.team_key, true, { iconOnly: true, teamName: w.display_name, slotId: 'todayWatchPlayerSlot' })}
                  <a class="small muted" href="#/team/${encodeURIComponent(w.team_key)}">상세</a>
                </div>
              </li>
            `).join('')}</ul>
            <div class="player-slot" id="todayWatchPlayerSlot" data-player-slot></div>`
          : `<p class="muted small" style="margin:0;">담아 둔 ${fmtInt(watchEnriched.length)}팀 중 최근 7일 새 신호는 없습니다.</p>`}
      </section>
    `
    : '';

  function paint() {
    const visUpcoming = upcomingCandEvents.slice(0, upcomingLimit);
    const remUpcoming = upcomingCandEvents.length - visUpcoming.length;

    const upcomingHtml = upcomingCandEvents.length
      ? `
        <section class="block" id="todayUpcomingBlock">
          <div class="block-head">
            <div>
              <h2>이번 주·다음 주 볼 수 있는 후보 공연</h2>
              <span class="block-meta">후보 ${fmtInt(upcomingCandTeamSet.size)}팀 · ${fmtInt(upcomingCandEvents.length)}개 무대 (같은 날·같은 공연장 묶음)</span>
            </div>
            <a class="small muted" href="#/venues">공연장·달력 보기 →</a>
          </div>
          <ul class="upcoming-list">
            ${visUpcoming.map(ev => {
              const dtLabel = formatKoreanShortDate(ev.signal_date);
              const multiCand = ev.candidateTeams.length >= 2;
              const otherNames = ev.otherTeams.slice(0, 3).map(t => t.display_name);
              const otherMore = ev.otherTeams.length - otherNames.length;
              const coBillHtml = ev.otherTeams.length > 0
                ? `<div class="cobill-note"><span class="cobill-lbl">함께 서는 팀</span> ${escapeHtml(otherNames.join(', '))}${otherMore > 0 ? ` 외 ${fmtInt(otherMore)}팀` : ''}</div>`
                : '';
              return `
                <li class="upcoming-row">
                  <div class="upcoming-when">
                    <span class="upcoming-date">${escapeHtml(dtLabel)}</span>
                    <span class="upcoming-venue">${escapeHtml(ev.venue)}</span>
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
                 <span>${fmtInt(visUpcoming.length)} / ${fmtInt(upcomingCandEvents.length)}개 무대</span>
                 <button type="button" class="btn btn-sm" id="btnMoreUpcoming">${fmtInt(Math.min(10, remUpcoming))}건 더 보기</button>
               </div>`
            : (upcomingLimit > 5 && upcomingCandEvents.length > 5
                ? `<div class="more-row" style="margin-top:10px;">
                     <span>전체 ${fmtInt(upcomingCandEvents.length)}개 무대 표시 중</span>
                     <button type="button" class="btn btn-sm" id="btnLessUpcoming">접기</button>
                   </div>`
                : '')}
        </section>
      `
      : '';

    const visNew = showAllNew ? diff.newEntrants.slice(0, 20) : diff.newEntrants.slice(0, 5);
    const visRisers = showAllRisers ? diff.risers.slice(0, 20) : diff.risers.slice(0, 5);

    const newHtml = visNew.length
      ? `<ul class="mini-list">${visNew.map(t => `
          <li>
            <div class="mini-list-row">
              ${avatarHtml(t.team_key, t.display_name, 28, { shape: 'circle', genre: t.genre })}
              <div class="mini-list-main">
                <a href="#/team/${encodeURIComponent(t.team_key)}"><strong>${escapeHtml(t.display_name)}</strong></a>
                <div class="mini-list-sub">신규 #${t.rank_now} · ${fmtNum(t.score_now, 2)}점${t.genre ? ` · ${escapeHtml(t.genre)}` : ''}</div>
              </div>
            </div>
            <div class="mini-list-actions">
              ${spotifyButtonHtml(t.team_key, true, { iconOnly: true, teamName: t.display_name, slotId: 'todayNewPlayerSlot' })}
              ${watchButtonHtml(t.team_key, t.display_name, true, true)}
            </div>
          </li>
        `).join('')}</ul>
        <div class="player-slot" id="todayNewPlayerSlot" data-player-slot></div>
        ${!showAllNew && diff.newEntrants.length > 5 ? `<div style="margin-top:10px;"><button type="button" class="btn btn-sm" id="btnMoreNew">${fmtInt(Math.min(20, diff.newEntrants.length) - 5)}팀 더 보기</button></div>` : ''}`
      : '<p class="muted small" style="margin:0;">이번 주 새로 들어온 팀이 없습니다.</p>';

    const riserHtml = visRisers.length
      ? `<ul class="mini-list">${visRisers.map(t => {
          const deltaParts = [];
          if (t.rank_gain > 0) deltaParts.push(`+${t.rank_gain}계단`);
          if (t.score_gain > 0) deltaParts.push(`+${fmtNum(t.score_gain, 2)}점`);
          return `
            <li>
              <div class="mini-list-row">
                ${avatarHtml(t.team_key, t.display_name, 28, { shape: 'circle', genre: t.genre })}
                <div class="mini-list-main">
                  <a href="#/team/${encodeURIComponent(t.team_key)}"><strong>${escapeHtml(t.display_name)}</strong></a>
                  <div class="mini-list-sub">#${t.rank_prev} → #${t.rank_now} (${deltaParts.join(', ')})</div>
                </div>
              </div>
              <div class="mini-list-actions">
                ${spotifyButtonHtml(t.team_key, true, { iconOnly: true, teamName: t.display_name, slotId: 'todayRiserPlayerSlot' })}
                ${watchButtonHtml(t.team_key, t.display_name, true, true)}
              </div>
            </li>
          `;
        }).join('')}</ul>
        <div class="player-slot" id="todayRiserPlayerSlot" data-player-slot></div>
        ${!showAllRisers && diff.risers.length > 5 ? `<div style="margin-top:10px;"><button type="button" class="btn btn-sm" id="btnMoreRisers">${fmtInt(Math.min(20, diff.risers.length) - 5)}팀 더 보기</button></div>` : ''}`
      : '<p class="muted small" style="margin:0;">순위·점수가 크게 오른 팀이 없습니다.</p>';

    const debutTotal = debutData?.total || 0;
    const debutMent = debutData?.mentioned?.length || 0;
    const debutUnm = debutData?.unmentioned?.length || 0;
    const sceneCommCount = appState.sceneMap?.communities?.length || Number(appState.meta?.scene_communities) || 0;

    const exploreStripHtml = `
      <section class="today-explore-strip" aria-label="신인 · 씬 탐색 바로가기">
        <a class="today-explore-card" href="#/candidates/debut">
          <div class="today-explore-top">
            <strong>갓 데뷔 신인</strong>
            ${debutTotal > 0 ? `<span class="today-explore-count">${fmtInt(debutTotal)}팀</span>` : ''}
          </div>
          <p class="today-explore-desc">
            ${debutTotal > 0
              ? `최근 12개월 첫 발매 · 언급 있음 ${fmtInt(debutMent)} · 아직 언급 없음 ${fmtInt(debutUnm)}`
              : '최근 12개월 내 첫 발매한 백지 신인 모아 보기'}
          </p>
          <span class="today-explore-cta">갓 데뷔 보기 →</span>
        </a>
        <a class="today-explore-card" href="#/venues/network">
          <div class="today-explore-top">
            <strong>씬 네트워크</strong>
            ${sceneCommCount > 0 ? `<span class="today-explore-count">묶음 ${fmtInt(sceneCommCount)}개</span>` : ''}
          </div>
          <p class="today-explore-desc">같은 무대에 함께 선 후보·수상 팀 연결 지도 탐색</p>
          <span class="today-explore-cta">씬 네트워크 열기 →</span>
        </a>
      </section>
    `;

    // 5-3 알림 카드(종류별 묶음·별점/중요도 순·근거 펼침·보인/찾은 수) · 5-4 이상치 문장(spike)
    const watchAlertsAll = getWatchlistAlerts(alertsData, getWatchlist());
    function buildAlertsBlockHtml() {
      return renderAlertsCardHtml(alertsData, {
        watchAlerts: watchAlertsAll,
        showAllWatch: showAllWatchAlerts,
        eventStarsMap,
        expandedTypes: expandedAlertTypes,
      });
    }
    const spikeAlerts = (alertsData?.alerts || []).filter(a => a.type === 'spike');
    const spikeBlockHtml = spikeAlerts.length ? `
      <section class="block today-spike-block" aria-label="평소와 다른 움직임">
        <div class="block-head">
          <h2>평소와 다른 움직임</h2>
          <span class="block-meta">최근 1주 언급 vs 지난 12주 · ${fmtInt(spikeAlerts.length)}팀</span>
        </div>
        ${renderSpikeSentencesHtml(spikeAlerts)}
      </section>` : '';

    const alertsBlockHtml = buildAlertsBlockHtml();

    root.innerHTML = `
      ${heroHtml}

      <div id="todayAlertsHost">${alertsBlockHtml}</div>

      ${spikeBlockHtml}

      ${renderSavedCardShellHtml()}

      <section class="today-section">
        <div class="block-head" style="border:none;margin-bottom:10px;padding:0;">
          <h2>이번 주 먼저 볼 5팀${infoTip('종합 점수', INFO_TIPS.score)}</h2>
          <a class="small muted" href="#/candidates">후보 전체 보기 →</a>
        </div>
        ${top5Html}
      </section>

      ${exploreStripHtml}

      ${upcomingHtml}

      <div class="grid-2" style="margin-bottom:20px;">
        <section class="block" style="margin-bottom:0;">
          <div class="block-head">
            <h3>새로 후보에 들어온 팀</h3>
            <span class="block-meta">${fmtInt(diff.newEntrants.length)}팀</span>
          </div>
          ${newHtml}
          ${snapNote ? `<p class="muted small" style="margin:10px 0 0 0;">${escapeHtml(snapNote)}</p>` : ''}
        </section>

        <section class="block" style="margin-bottom:0;">
          <div class="block-head">
            <h3>순위·점수가 크게 오른 팀</h3>
            <span class="block-meta">${fmtInt(diff.risers.length)}팀</span>
          </div>
          ${riserHtml}
          ${snapNote ? `<p class="muted small" style="margin:10px 0 0 0;">${escapeHtml(snapNote)}</p>` : ''}
        </section>
      </div>

      ${recentVideosHtml}
      ${watchBlockHtml}
    `;

    wireAvatarFallbacks(root);
    wireSpotifyButtons(root);

    // Inline click-to-play YouTube thumbnails (zero iframes on initial load)
    root.querySelectorAll('.video-frame[data-video-id]').forEach(btn => {
      btn.addEventListener('click', () => {
        const vid = btn.dataset.videoId;
        if (!/^[A-Za-z0-9_-]{11}$/.test(vid)) return;
        const wrap = document.createElement('div');
        wrap.className = 'video-frame';
        wrap.innerHTML = `<iframe src="https://www.youtube-nocookie.com/embed/${vid}?autoplay=1" allow="autoplay; encrypted-media; picture-in-picture" allowfullscreen title="무대 영상"></iframe>`;
        btn.replaceWith(wrap);
      });
    });

    root.querySelector('#btnMoreWatchAlerts')?.addEventListener('click', () => { showAllWatchAlerts = true; paint(); });
    root.querySelectorAll('[data-alert-more]').forEach(btn => {
      btn.addEventListener('click', () => { expandedAlertTypes.add(btn.dataset.alertMore); paint(); });
    });
    fillSavedCard(root);
    root.querySelector('#btnMoreUpcoming')?.addEventListener('click', () => { upcomingLimit += 10; paint(); });
    root.querySelector('#btnLessUpcoming')?.addEventListener('click', () => { upcomingLimit = 5; paint(); });
    root.querySelector('#btnMoreNew')?.addEventListener('click', () => { showAllNew = true; paint(); });
    root.querySelector('#btnMoreRisers')?.addEventListener('click', () => { showAllRisers = true; paint(); });
    root.querySelectorAll('[data-open-team]').forEach(el => {
      el.addEventListener('click', () => navigateTo('team', el.dataset.openTeam));
    });
  }

  paint();

  // Live-update alerts highlight if user stars/unstars a team directly on #/today
  const onWatchChange = () => {
    const host = root.querySelector('#todayAlertsHost');
    if (!host || !host.isConnected) {
      window.removeEventListener('app:watchlist', onWatchChange);
      return;
    }
    paint();
  };
  window.addEventListener('app:watchlist', onWatchChange);
}
