import { appState, navigateTo, setExportContext } from '../state.js';
import {
  ensureTeamCitiesLoaded, getTeamExternalLinks, loadAlertsJson, loadDashboardJson, loadSceneMap,
  loadSourceRoles, queryDiscoveryStages, queryRankChange, queryTeamDetail,
} from '../db.js';
import {
  alertKindChipHtml, avatarHtml, avatarSourceOf, dormantBadgeHtml, ensureD3,
  escapeHtml, fmtInt, fmtNum, formatAlertEvidenceText, formatNextGigText,
  formatSignalDate, gradeBadgeHtml, INFO_TIPS, infoTip,
  isDormantTeam, isLoweredOutcomeResult, isWeakGenreConfidence, lookupSourceRoleMeta,
  newcomerUnverifiedBadgeHtml, PROFILE_LABELS,
  renderActionBanner, renderCompactGradeSummary, renderEmptyState,
  renderNoRecordLine, renderScoreBar,
  renderTableCsvBtn, roleBadgeHtml, SOURCE_LABELS, spotifyButtonHtml,
  spotifyUrlOf, summarizeWhyTeam, TERMS, triggerTableCsvExport,
  watchButtonHtml, wireAvatarFallbacks,
  routeBackLabel,
} from '../ui.js';
import { mountTeamGraphBlock } from './graph.js';
import { compareButtonHtml, renderKeyStatsHtml, renderTeamFactsHtml } from './team_head.js';
import { activeTeamTab, renderTeamTabsHtml, teamPanelHtml, wireTeamTabs } from './team_tabs.js';
import {
  queryScenePeerWinners, renderChangeRowHtml, renderTeamStatusBarsHtml, wireChangeRow,
} from './team_pulse.js';
import { renderScoreBodyHtml, wireScoreBlock } from './team_score.js';
import { renderEventLogHtml } from './team_events.js';
import { renderGigBlockHtml } from './team_gigs.js';
import { queryPeerCompare } from '../db_peer.js';
import {
  loadEventStars, loadLineupRoles, loadVenueMeta, queryTeamGigActs,
} from '../db_team_extras.js';

/**
 * 듣기·보기는 스포티파이·유튜브 두 가지만 (사용자 결정 2026-11-27).
 * - 스포티파이: '▶ 듣기'를 누르면 이 자리에서 공식 임베드 플레이어(미리 듣기, 로그인 시 전곡)
 * - 유튜브: 공식 채널이 있으면 채널로, 없으면 아래 '영상' 블록으로 이동
 */
function renderListenButtons(teamKey, displayName, linksMap, hasVideos) {
  const parts = [spotifyButtonHtml(teamKey, false, { teamName: displayName })];
  const yt = linksMap && linksMap.get('youtube');
  if (yt && yt.startsWith('https://www.youtube.com/')) {
    parts.push(`<a class="btn" href="${escapeHtml(yt)}" target="_blank" rel="noopener noreferrer">유튜브 채널</a>`);
  } else if (hasVideos) {
    parts.push('<a class="btn" href="#teamVideosBlock" data-scroll-videos>무대 영상</a>');
  }
  return parts.filter(Boolean).join('');
}

function resolveSignalName(s) {
  const progLabel = s.program_label && s.program_label !== s.program ? s.program_label : '';
  const code = s.branch === '선정·지원' && s.program ? s.program : s.source;
  let base = progLabel
    || SOURCE_LABELS[s.program]
    || SOURCE_LABELS[s.source]
    || s.program_label
    || s.source
    || '';
  if (code === 'instagram' && base === '인스타그램') {
    if (s.branch === '공연') base = '인스타그램 (공연장 라인업)';
    else if (s.branch === '큐레이션') base = '인스타그램 (매거진)';
  }
  return base;
}

function renderVideosInnerHtml(videos, showAll) {
  if (!videos || !videos.length) return '';
  const visible = showAll ? videos : videos.slice(0, 3);
  const moreCount = videos.length - visible.length;

  return `
    <div class="block-head">
      <h2>영상</h2>
      <span class="block-meta">최근 무대 ${fmtInt(videos.length)}개 · 누르면 바로 재생</span>
    </div>
    <div class="video-grid">
      ${visible.map(v => {
        const subParts = [];
        if (v.channel_title) subParts.push(escapeHtml(v.channel_title));
        if (v.published_at) subParts.push(escapeHtml(String(v.published_at).slice(0, 10)));
        const searchNote = v.kind === 'search'
          ? '<span class="video-search-tag" title="유튜브 검색 결과로 공식 영상이 아닐 수 있습니다">검색 결과</span>'
          : '';
        return `
          <article class="video-card">
            <button type="button" class="video-frame" data-video-id="${escapeHtml(v.video_id)}" aria-label="${escapeHtml(v.title || '영상 재생')}">
              <img src="https://i.ytimg.com/vi/${encodeURIComponent(v.video_id)}/mqdefault.jpg"
                   alt="${escapeHtml(v.title || '무대 영상')}" loading="lazy">
              <span class="video-play-label">재생</span>
            </button>
            <div class="video-meta">
              <div class="video-title">${escapeHtml(v.title || v.video_id)}</div>
              <div class="video-sub">${subParts.join(' · ')}${searchNote ? (subParts.length ? ' · ' : '') + searchNote : ''}</div>
            </div>
          </article>
        `;
      }).join('')}
    </div>
    ${moreCount > 0 ? `<div style="margin-top:8px;"><button type="button" class="btn btn-sm" id="btnMoreVideos">영상 ${fmtInt(moreCount)}개 더 보기</button></div>` : ''}
  `;
}

function renderMonthlyBarsHtml(timeline, endDateStr) {
  const [ey, em] = String(endDateStr || '2026-11-27').split('-').map(Number);
  const monthBuckets = [];
  const bucketMap = new Map();
  if (Number.isFinite(ey) && Number.isFinite(em)) {
    for (let offset = 11; offset >= 0; offset--) {
      const d = new Date(Date.UTC(ey, em - 1 - offset, 1));
      const y = d.getUTCFullYear();
      const mo = d.getUTCMonth() + 1;
      const ym = `${y}-${String(mo).padStart(2, '0')}`;
      const item = { ym, shortLabel: `${mo}월`, gig: 0, sel: 0, other: 0, total: 0 };
      monthBuckets.push(item);
      bucketMap.set(ym, item);
    }
  }
  for (const s of timeline) {
    if (s.role === 'excluded') continue;
    const dt = String(s.signal_date || '').slice(0, 10);
    if (!dt || dt > endDateStr) continue;
    const b = bucketMap.get(dt.slice(0, 7));
    if (!b) continue;
    if (s.branch === '공연') b.gig += 1;
    else if (s.branch === '선정·지원') b.sel += 1;
    else b.other += 1;
    b.total += 1;
  }
  const total12m = monthBuckets.reduce((acc, m) => acc + m.total, 0);
  const max12m = Math.max(1, ...monthBuckets.map(m => m.total));

  const lastNonExclDate = timeline
    .filter(s => s.role !== 'excluded' && s.signal_date && String(s.signal_date).slice(0, 10) <= endDateStr)
    .map(s => String(s.signal_date).slice(0, 7))
    .sort()
    .pop() || '';

  return `
    <div class="team-activity-bars">
      <div class="team-activity-bars-head">
        <span class="small muted">최근 12개월 활동 흐름 (${escapeHtml(monthBuckets[0]?.ym || '')} ~ ${escapeHtml(monthBuckets[monthBuckets.length - 1]?.ym || '')} · 총 ${fmtInt(total12m)}건)</span>
        <div class="monthly-legend" aria-label="갈래 범례">
          <span class="monthly-leg-item"><i class="monthly-dot is-gig"></i>공연</span>
          <span class="monthly-leg-item"><i class="monthly-dot is-sel"></i>선정·지원</span>
          <span class="monthly-leg-item"><i class="monthly-dot is-other"></i>발매·큐레이션</span>
        </div>
      </div>
      ${total12m > 0 ? `
        <div class="monthly-bars-grid" role="img" aria-label="최근 12개월 갈래별 활동 막대 그래프">
          ${monthBuckets.map(m => {
            const barPct = m.total > 0 ? Math.max(8, Math.round((m.total / max12m) * 100)) : 0;
            const gigPct = m.total > 0 ? (m.gig / m.total) * 100 : 0;
            const selPct = m.total > 0 ? (m.sel / m.total) * 100 : 0;
            const otherPct = m.total > 0 ? (m.other / m.total) * 100 : 0;
            const parts = [];
            if (m.gig) parts.push(`공연 ${m.gig}`);
            if (m.sel) parts.push(`선정·지원 ${m.sel}`);
            if (m.other) parts.push(`발매·큐레이션 ${m.other}`);
            const tip = parts.length ? `${m.ym}: ${parts.join(' · ')}` : `${m.ym}: 기록 없음`;
            return `
              <div class="monthly-bar-col" title="${escapeHtml(tip)}">
                <span class="monthly-bar-cnt">${m.total > 0 ? fmtInt(m.total) : ''}</span>
                <div class="monthly-bar-track">
                  ${m.total > 0 ? `
                    <div class="monthly-bar-stack" style="height:${barPct}%">
                      ${m.other ? `<span class="monthly-seg is-other" style="height:${otherPct.toFixed(1)}%"></span>` : ''}
                      ${m.sel ? `<span class="monthly-seg is-sel" style="height:${selPct.toFixed(1)}%"></span>` : ''}
                      ${m.gig ? `<span class="monthly-seg is-gig" style="height:${gigPct.toFixed(1)}%"></span>` : ''}
                    </div>
                  ` : '<div class="monthly-bar-zero"></div>'}
                </div>
                <span class="monthly-bar-lbl">${escapeHtml(m.shortLabel)}</span>
              </div>
            `;
          }).join('')}
        </div>
      ` : renderNoRecordLine(lastNonExclDate ? `최근 12개월 활동 없음 · 마지막 활동 ${lastNonExclDate}` : '최근 12개월 내 기록된 활동 없음')}
    </div>
  `;
}

// 사건 별점(event_stars.csv, 약 2.4MB)은 화면을 막지 않고 뒤에서 받는다 — 받은 뒤엔 다음 팀부터 바로 씀 (속도 점검 2026-11-28)
let eventStarsCache;          // undefined = 아직, null = 파일 없음, Map = 받음

export async function renderTeamView(root, teamKey) {
  if (!teamKey) {
    root.innerHTML = renderEmptyState({
      message: '선택된 팀이 없습니다. 위 검색창에서 찾거나 발굴·차트에서 팀을 골라 주세요.',
      showReset: false,
      actionLabel: '발굴에서 고르기',
      actionHref: '#/discover',
    });
    return;
  }

  const asOf = appState.cfg.as_of || appState.dataEnd || '2026-11-27';
  const [data, sceneMap, sourceRoles, stageData, alertsData, rankChangeData, sceneWinners,
    peerStage, eventStarsMap, lineupMap, venueMeta, gigActs] = await Promise.all([
    queryTeamDetail(teamKey),
    loadSceneMap(),
    loadSourceRoles(),
    queryDiscoveryStages({ as_of: asOf }),
    loadAlertsJson().catch(() => null),
    queryRankChange({ as_of: asOf }).catch(() => null),
    queryScenePeerWinners(teamKey, asOf),
    queryPeerCompare({ as_of: asOf, team_key: teamKey, scope: 'stage' }),
    Promise.resolve(eventStarsCache === undefined ? null : eventStarsCache),
    loadLineupRoles(),
    loadVenueMeta(),
    queryTeamGigActs(teamKey),
    ensureTeamCitiesLoaded().catch(() => null),
    loadDashboardJson().catch(() => null),
    ensureD3().catch(() => null),
  ]);
  const { profile, scored, timeline, outcomes, precedents, related, links, videos } = data;
  const sceneComm = sceneMap?.teamToCommunity?.get(teamKey) || null;

  if (!profile && !scored && !timeline.length) {
    root.innerHTML = renderEmptyState({
      message: `'${teamKey}' 팀의 기록을 찾지 못했습니다. 위 검색창에서 다른 이름으로 찾거나 발굴·차트를 확인해 주세요.`,
      showReset: false,
      actionLabel: '발굴에서 고르기',
      actionHref: '#/discover',
    });
    return;
  }

  let stageInfo = stageData?.byTeam?.get(teamKey) || null;
  if (!stageInfo) {
    const wideStage = await queryDiscoveryStages({ as_of: asOf, newcomer_years: 50 }).catch(() => null);
    stageInfo = wideStage?.byTeam?.get(teamKey) || null;
  }

  const displayName = scored?.display_name || profile?.display_name || teamKey;
  const extLinks = getTeamExternalLinks(teamKey, displayName);
  const whyLines = summarizeWhyTeam(data);

  // Concise 1-line identity subline (omit empty fields)
  const metaParts = [];
  if (profile?.agency) metaParts.push(`소속 ${profile.agency}`);
  if (profile?.first_seen) metaParts.push(`첫 등장 ${profile.first_seen}`);
  if (scored) {
    metaParts.push(`${fmtNum(scored.score, 2)}점`);
  }

  // Merge outcomes + signals into single chronological timeline
  const mergedTimeline = [];
  for (const o of outcomes) {
    const tierKo = o.tier === 'final' ? '최종' : '중간';
    const isNominee = isLoweredOutcomeResult(o.result, sourceRoles);
    mergedTimeline.push({
      sortDate: o.announced_date || '',
      dateDisp: o.announced_date || '-',
      branch: TERMS.outcome,
      isOutcome: true,
      grade: o.grade || '',
      weight: o.weight,
      isNominee,
      role: '',
      roleReason: '',
      isDimmed: false,
      text: `${o.program_label || o.program} [${tierKo}]${o.counted ? '' : ' (집계 제외)'}`,
    });
  }
  for (const s of timeline) {
    const name = resolveSignalName(s);
    const cleanVenue = (s.venue && String(s.venue).trim() && String(s.venue).trim() !== '공연장 미정')
      ? String(s.venue).trim()
      : '';
    const detail = s.venue ? `${name} — ${s.venue}` : name;
    const roleMeta = lookupSourceRoleMeta(sourceRoles, s.branch, s.source, s.program);
    const role = s.role || roleMeta?.role || 'pending';
    const roleReason = roleMeta?.reason || '';
    mergedTimeline.push({
      sortDate: s.signal_date || '',
      dateDisp: formatSignalDate(s.signal_date, s.branch),
      branch: s.branch || '',
      isOutcome: false,
      grade: '',
      role,
      roleReason,
      isDimmed: role === 'excluded' || role === 'pending',
      baseName: name,
      venue: cleanVenue,
      text: detail,
    });
  }
  mergedTimeline.sort((a, b) => (b.sortDate > a.sortDate ? 1 : b.sortDate < a.sortDate ? -1 : 0));

  const stageRelated = related.filter(r => r.relation === '같은 무대');
  const agencyRelated = related.filter(r => r.relation === '같은 소속사');

  // Non-empty profile facts only (inline compact strip inside 요약)
  const profileFacts = [];
  if (profile?.agency) profileFacts.push(['소속사', profile.agency]);
  if (profile?.primary_genre) profileFacts.push(['장르', profile.primary_genre]);
  if (profile?.first_release) profileFacts.push(['첫 발매일', profile.first_release]);
  if (profile?.fan_count !== null && profile?.fan_count !== undefined && profile?.fan_count !== '') {
    profileFacts.push(['멜론 팬', `${fmtInt(profile.fan_count)}명`]);
  }
  if (profile?.album_count !== null && profile?.album_count !== undefined && profile?.album_count !== '') {
    profileFacts.push(['앨범', `${fmtInt(profile.album_count)}장`]);
  }
  if (profile?.profile_status && profile.profile_status !== 'unknown') {
    profileFacts.push(['분류', PROFILE_LABELS[profile.profile_status] || profile.profile_status]);
  }

  // 3-4 점수 근거: 항목 막대 + 동료 비교(같은 발굴 단계 기본, 장르 이웃은 profile·press 장르 팀만)
  const genreConf = appState.genreConfidenceByTeam?.get(teamKey) || profile?.genre_confidence || '';
  const genreForPeer = String(scored?.primary_genre || profile?.primary_genre || '').trim();
  const scoreCtx = {
    teamKey,
    scored,
    peer: peerStage?.byTeam?.get(teamKey) || null,
    peerError: peerStage?.error || '',
    genreOk: Boolean(genreForPeer && genreForPeer !== '미분류' && !isWeakGenreConfidence(genreConf)),   // 추정·리뷰 장르는 이웃 비교 제외
    timeline,
    asOf,
    nameOf: resolveSignalName,
  };

  // Register team timeline CSV with unified export dropdown
  const teamTlCsvSpec = mergedTimeline.length ? {
    filename: `crate_digger_team_${teamKey.replace(/[^a-zA-Z0-9가-힣_-]+/g, '_')}_${appState.dataEnd || 'export'}.csv`,
    headers: ['날짜', '갈래', '역할/등급', '내용'],
    rows: mergedTimeline.map(m => [m.dateDisp, m.branch, m.isOutcome ? (m.grade || '') : (m.role || ''), m.text]),
  } : null;

  setExportContext({
    csvLabel: teamTlCsvSpec ? `${displayName} 활동 기록 CSV 내려받기 (${fmtInt(mergedTimeline.length)}건)` : '',
    csvFilename: teamTlCsvSpec?.filename || '',
    csvHeaders: teamTlCsvSpec?.headers || [],
    csvRows: teamTlCsvSpec?.rows || [],
  });

  // 이전 화면 이름(메뉴 이름) — 모르면 홈
  const backRoute = appState.prevRoute && routeBackLabel(appState.prevRoute) && appState.prevRoute !== 'team' ? appState.prevRoute : 'today';
  const backLabel = routeBackLabel(backRoute) || '홈';

  const imgSrc = avatarSourceOf(teamKey);
  const spUrl = spotifyUrlOf(teamKey);
  const genre = scored?.primary_genre || profile?.primary_genre || '';
  const photoCreditHtml = imgSrc === 'spotify'
    ? (spUrl
        ? `<a class="avatar-credit" href="${escapeHtml(spUrl)}" target="_blank" rel="noopener noreferrer">사진 · Spotify ↗</a>`
        : '<span class="avatar-credit">사진 · Spotify</span>')
    : '';

  const upcomingDedup = new Map();
  for (const s of timeline) {
    if (s.branch !== '공연') continue;
    const dt = String(s.signal_date || '').slice(0, 10);
    if (!dt || dt < asOf) continue;
    const v = String(s.venue || '').trim() || '공연장 미정';
    const key = `${dt}::${v}`;
    if (!upcomingDedup.has(key)) upcomingDedup.set(key, { signal_date: dt, venue: v });
  }
  const upcomingList = [...upcomingDedup.values()].sort((a, b) => a.signal_date.localeCompare(b.signal_date));
  const nextGig = upcomingList[0] || null;
  const nextGigVenueOk = Boolean(nextGig && nextGig.venue && nextGig.venue !== '공연장 미정');
  const nextGigHtml = nextGig
    ? `<p class="team-next-gig">${nextGigVenueOk
        ? `<a class="next-gig-pill next-gig-pill-link" href="#/venue/${encodeURIComponent(nextGig.venue)}">다음 공연 ${escapeHtml(formatNextGigText(nextGig))}${upcomingList.length > 1 ? ` 외 ${upcomingList.length - 1}건` : ''}</a>`
        : `<span class="next-gig-pill">다음 공연 ${escapeHtml(formatNextGigText(nextGig))}${upcomingList.length > 1 ? ` 외 ${upcomingList.length - 1}건` : ''}</span>`}</p>`
    : '';

  const sceneVenuesHtml = sceneComm && Array.isArray(sceneComm.top_venues) && sceneComm.top_venues.length
    ? sceneComm.top_venues.slice(0, 3).map(v => `<a class="inline-venue-link" href="#/venue/${encodeURIComponent(v.venue)}">${escapeHtml(v.venue)}</a>`).join(' · ')
    : '';
  const sceneLineHtml = sceneComm
    ? `<p class="team-scene-line">속한 씬: <a href="#/venues" class="inline-team-link" data-jump-scene="${sceneComm.id}"><strong>묶음 ${fmtInt(sceneComm.id)}</strong></a>${sceneVenuesHtml ? ` <span class="muted">(${sceneVenuesHtml})</span>` : ''}</p>`
    : '';

  const outcomesLineHtml = outcomes.length
    ? `<div class="team-outcomes-line" aria-label="${escapeHtml(TERMS.outcome)} 기록">
        <span class="team-outcomes-lbl">${escapeHtml(TERMS.outcome)}</span>
        ${outcomes.slice(0, 4).map(o => {
          const isNominee = isLoweredOutcomeResult(o.result, sourceRoles);
          const progLabel = o.program_label || o.program || '';
          const yr = o.announced_date ? String(o.announced_date).slice(0, 4) : '';
          return `<span class="team-outcome-chip">${gradeBadgeHtml(o.grade, { weight: o.weight, isNominee })}<span>${escapeHtml(progLabel)}${yr ? ` (${escapeHtml(yr)})` : ''}</span></span>`;
        }).join('')}
        ${outcomes.length > 4 ? `<span class="small muted">외 ${fmtInt(outcomes.length - 4)}건</span>` : ''}
      </div>`
    : '';


  const teamAlerts = alertsData?.byTeam?.get(teamKey) || [];
  const teamAlertsLineHtml = teamAlerts.length
    ? `<div class="team-alerts-line" aria-label="이 팀 최근 알림">
        <span class="team-alerts-lbl">최근 알림</span>
        ${teamAlerts.slice(0, 3).map(a => {
          const evTxt = formatAlertEvidenceText(a);
          const tip = [evTxt ? `근거: ${evTxt}` : '', a.found_on ? `발견일: ${a.found_on}` : ''].filter(Boolean).join(' · ');
          return `<span class="team-alert-chip"${tip ? ` title="${escapeHtml(tip)}"` : ''}>${alertKindChipHtml(a, alertsData?.types)}<span>${escapeHtml(a.text)}</span>${a.date ? `<span class="mono muted">${escapeHtml(a.date)}</span>` : ''}</span>`;
        }).join('')}
        ${teamAlerts.length > 3 ? `<span class="small muted">외 ${fmtInt(teamAlerts.length - 3)}건</span>` : ''}
      </div>`
    : '';

  let isDormant = isDormantTeam(scored);
  if (timeline.length > 0 && asOf) {
    const asOfMs = Date.parse(`${asOf}T00:00:00Z`);
    if (Number.isFinite(asOfMs)) {
      const cut180 = new Date(asOfMs - 180 * 86400000).toISOString().slice(0, 10);
      const cut365 = new Date(asOfMs - 365 * 86400000).toISOString().slice(0, 10);
      const nonExcl = timeline.filter(s => s.role !== 'excluded');
      const hasGig1y = nonExcl.some(s => s.branch === '공연' && (s.is_upcoming || (s.signal_date && s.signal_date >= cut365 && s.signal_date <= asOf)));
      if (scored) {
        if (hasGig1y) isDormant = false;
      } else {
        const hasRec180 = nonExcl.some(s => s.signal_date && s.signal_date >= cut180 && s.signal_date <= asOf);
        isDormant = !hasRec180 && !hasGig1y;
      }
    }
  }

  const monthlyBarsHtml = renderMonthlyBarsHtml(timeline, asOf);
  const hasNonDiscovery = mergedTimeline.some(m => !m.isOutcome && m.role !== 'discovery');
  const hasUnscored = mergedTimeline.some(m => !m.isOutcome && (m.role === 'pending' || m.role === 'excluded'));

  let showAllVideos = false;
  let showAllPrec = false;
  let showAllTimeline = false;
  let showAllEvents = false;
  let teamEvents = eventStarsMap ? (eventStarsMap.get(teamKey) || []) : null;
  let showAllStageRel = false;

  // Section 1: 요약
  const summarySectionHtml = `
    <section class="block" id="teamSummaryBlock">
      <div class="block-head">
        <h2>요약</h2>
        <span class="block-meta">기준일 ${escapeHtml(asOf)}</span>
      </div>
      <ol class="why-list">
        ${whyLines.map(line => `<li>${escapeHtml(line)}</li>`).join('')}
      </ol>
      ${profileFacts.length ? `
        <dl class="team-profile-strip" aria-label="아티스트 기본 정보">
          ${profileFacts.map(([k, v]) => `
            <div class="team-profile-chip">
              <dt>${escapeHtml(k)}</dt>
              <dd>${escapeHtml(v)}</dd>
            </div>
          `).join('')}
        </dl>
      ` : ''}
    </section>
  `;

  // Section 2: 점수 근거
  const scoreSectionHtml = `
    <section class="block" id="teamScoreBlock">
      <div class="block-head">
        <h2>점수 근거${infoTip('점수 근거', INFO_TIPS.score_breakdown)}</h2>
        ${scored ? `<span class="block-meta">합계 ${fmtNum(scored.score, 2)}점</span>` : ''}
      </div>
      ${scored ? `
        <div style="margin-bottom:10px;">${renderScoreBar(scored, Math.max(10, Number(scored.score) || 1))}</div>
        <div id="teamScoreBody">${renderScoreBodyHtml(scoreCtx)}</div>
      ` : renderNoRecordLine('현재 필터·기간 조건 안의 점수가 없습니다')}
      <p class="score-role-note">
        점수에는 발굴 출처만, 맥락 매체는 약하게 반영합니다. 검증 대기·제외 출처는 아래 활동 기록에서 참고용으로만 보여 줍니다.
        <a href="#/verify/scorecard">출처 성적표 보기 ↗</a>
      </p>
    </section>
  `;

  // Section 3b: folded related teams list right under 관계망
  function renderRelatedFoldInner() {
    if (!related.length) return '';
    const visibleStage = showAllStageRel ? stageRelated : stageRelated.slice(0, 6);
    const moreStage = stageRelated.length - visibleStage.length;
    return `
      ${stageRelated.length ? `
        <div class="team-rel-sub">
          <div class="team-rel-sub-head">
            <strong>같은 무대에 함께 선 팀</strong>
            <span class="small muted">${fmtInt(stageRelated.length)}팀</span>
          </div>
          <div class="table-wrap">
            <table class="data-table">
              <thead>
                <tr>
                  <th>팀</th>
                  <th class="num nowrap">함께 선 횟수</th>
                  <th class="nowrap">최근 날짜</th>
                  <th>공연장</th>
                </tr>
              </thead>
              <tbody>
                ${visibleStage.map(r => `
                  <tr>
                    <td>
                      <a class="row-team-cell" href="#/team/${encodeURIComponent(r.related_team)}">
                        ${avatarHtml(r.related_team, r.display_name || r.related_team, 24, { shape: 'circle' })}
                        <strong>${escapeHtml(r.display_name || r.related_team)}</strong>
                      </a>
                    </td>
                    <td class="num">${fmtInt(r.shared_count)}</td>
                    <td class="nowrap mono muted">${escapeHtml(r.last_date || '-')}</td>
                    <td class="muted">${r.detail
                      ? String(r.detail).split(' · ').filter(Boolean).map(v => {
                          const vn = v.trim();
                          return (vn && vn !== '공연장 미정')
                            ? `<a class="inline-venue-link" href="#/venue/${encodeURIComponent(vn)}">${escapeHtml(vn)}</a>`
                            : escapeHtml(vn);
                        }).join(' · ')
                      : '-'}</td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          </div>
          ${moreStage > 0 ? `<div class="more-row"><span>상위 ${fmtInt(visibleStage.length)} / ${fmtInt(stageRelated.length)}팀</span><button type="button" class="btn btn-sm" id="btnMoreStageRel">${fmtInt(moreStage)}팀 더 보기</button></div>` : ''}
        </div>
      ` : ''}
      ${agencyRelated.length ? `
        <div class="team-rel-sub" style="${stageRelated.length ? 'margin-top:14px;' : ''}">
          <div class="team-rel-sub-head">
            <strong>같은 소속사 팀</strong>
            <span class="small muted">${escapeHtml(agencyRelated[0]?.detail || '')} · ${fmtInt(agencyRelated.length)}팀</span>
          </div>
          <ul class="mini-list">
            ${agencyRelated.map(r => `
              <li>
                <div class="mini-list-row">
                  ${avatarHtml(r.related_team, r.display_name || r.related_team, 24, { shape: 'circle' })}
                  <div class="mini-list-main">
                    <a href="#/team/${encodeURIComponent(r.related_team)}"><strong>${escapeHtml(r.display_name || r.related_team)}</strong></a>
                  </div>
                </div>
                <span class="small muted">${escapeHtml(r.detail || '')}</span>
              </li>
            `).join('')}
          </ul>
        </div>
      ` : ''}
    `;
  }

  // Section 4: 활동 기록
  function renderActivityInner() {
    const visibleTl = showAllTimeline ? mergedTimeline : mergedTimeline.slice(0, 8);
    const moreTl = mergedTimeline.length - visibleTl.length;
    const legendText = hasUnscored
      ? `표시: <strong>발굴</strong> 점수 반영 · <strong>맥락</strong> 약하게 반영 · <strong>${escapeHtml(TERMS.unscored)}</strong> 점수에 안 쓰는 출처(검증 대기·제외, 흐리게 표시)`
      : '표시: <strong>발굴</strong> 점수 반영 · <strong>맥락</strong> 약하게 반영';

    return `
      <div class="block-head">
        <div>
          <h2>${teamEvents ? '사건 기록' : '활동 기록'}</h2>
          <span class="block-meta">전체 활동 ${fmtInt(mergedTimeline.length)}건</span>
        </div>
        ${teamTlCsvSpec ? `<div class="block-head-actions">${renderTableCsvBtn('btnTeamTlCsv', 'CSV 내려받기')}</div>` : ''}
      </div>
      ${monthlyBarsHtml}
      ${renderEventLogHtml(teamEvents, asOf, showAllEvents)}
      ${teamEvents ? '<h3 class="timeline-all-title">전체 활동 기록</h3>' : ''}
      ${hasNonDiscovery ? `<p class="timeline-role-legend">${legendText}</p>` : ''}
      ${visibleTl.length ? `
        <ul class="timeline-list">
          ${visibleTl.map(m => `
            <li class="${m.isDimmed ? 'is-dimmed' : ''}">
              <span class="timeline-date">${escapeHtml(m.dateDisp)}</span>
              <span class="timeline-branch ${m.isOutcome ? 'timeline-outcome' : ''}">${escapeHtml(m.branch)}</span>
              <span class="timeline-detail">
                ${m.isOutcome
                  ? gradeBadgeHtml(m.grade, { weight: m.weight, isNominee: m.isNominee })
                  : roleBadgeHtml(m.role, { context: 'timeline', title: m.roleReason })}
                <span>${m.venue
                  ? `${escapeHtml(m.baseName || '')} — <a class="inline-venue-link" href="#/venue/${encodeURIComponent(m.venue)}">${escapeHtml(m.venue)}</a>`
                  : escapeHtml(m.text)}</span>
              </span>
            </li>
          `).join('')}
        </ul>
        ${moreTl > 0 ? `<div class="more-row" style="margin-top:8px;"><span>최근 ${fmtInt(visibleTl.length)} / ${fmtInt(mergedTimeline.length)}건</span><button type="button" class="btn btn-sm" id="btnMoreTimeline">${fmtInt(moreTl)}건 더 보기</button></div>` : ''}
      ` : renderNoRecordLine('기록된 활동 신호가 없습니다')}
      ${extLinks.length ? `
        <details class="info-fold" style="margin:12px 0 0 0;">
          <summary>관련 기사 · 출처 링크 (${fmtInt(extLinks.length)}건)</summary>
          <div class="info-fold-body">
            <ul class="mini-list">
              ${extLinks.map(l => `
                <li>
                  <div class="mini-list-main">
                    <a href="${escapeHtml(l.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(l.title)}</a>
                    <div class="mini-list-sub">${escapeHtml(l.source)}${l.date ? ` · ${escapeHtml(l.date)}` : ''}</div>
                  </div>
                </li>
              `).join('')}
            </ul>
          </div>
        </details>
      ` : ''}
    `;
  }

  // Section 5: 비슷한 과거 수상 팀
  function renderPrecedentsInner() {
    const visiblePrec = showAllPrec ? precedents : precedents.slice(0, 3);
    const morePrec = precedents.length - visiblePrec.length;
    return `
      <div class="block-head">
        <h2>비슷한 과거 수상 팀</h2>
        <span class="block-meta">${fmtInt(precedents.length)}팀</span>
      </div>
      ${visiblePrec.length ? `
        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>과거 수상 팀</th>
                <th>첫 ${escapeHtml(TERMS.outcome)}</th>
                <th class="nowrap">발표일</th>
                <th>겹친 경로</th>
                <th class="num nowrap">소요 (개월)</th>
              </tr>
            </thead>
            <tbody>
              ${visiblePrec.map(p => `
                <tr>
                  <td><a href="#/team/${encodeURIComponent(p.past_team)}"><strong>${escapeHtml(p.display_name || p.past_team)}</strong></a></td>
                  <td><span class="outcome-label-wrap">${gradeBadgeHtml(p.outcome_grade)}<span>${escapeHtml(p.outcome_label || '-')}</span></span></td>
                  <td class="nowrap mono muted">${escapeHtml(p.outcome_date || '-')}</td>
                  <td>${escapeHtml(p.shared_list || '-')}</td>
                  <td class="num">${p.months_signal_to_outcome !== null && p.months_signal_to_outcome !== undefined ? fmtInt(p.months_signal_to_outcome) : '-'}</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
        ${morePrec > 0 ? `<div class="more-row"><span>${fmtInt(visiblePrec.length)} / ${fmtInt(precedents.length)}팀 표시</span><button type="button" class="btn btn-sm" id="btnMorePrec">${fmtInt(morePrec)}팀 더 보기</button></div>` : ''}
        <details class="info-fold" style="margin:8px 0 0 0;">
          <summary>ⓘ 선례 · 등급 해석</summary>
          <div class="info-fold-body">선례는 수상·선정 전에 같은 선정·공연장·매체를 거쳤다는 참고 경로일 뿐이며, 수상을 예측하지 않습니다.${(() => { const s = renderCompactGradeSummary({ sourceRoles }); return s ? ` ${s}` : ''; })()}</div>
        </details>
      ` : renderNoRecordLine('겹치는 경로를 가진 과거 수상 팀 선례 없음')}
    `;
  }

  const reportUrl =
    'https://github.com/leegmyung/crate-digger/issues/new?template=identity.yml'
    + `&title=${encodeURIComponent(`[팀 정보] ${displayName}`)}`
    + `&team=${encodeURIComponent(displayName)}`
    + `&team_key=${encodeURIComponent(teamKey)}`
    + `&page=${encodeURIComponent(window.location.href)}`;

  // 3-1 머리 띠 사실 줄 · 3-2/3-3 상태·변화 · 쪽 안 목차
  const rcRow = rankChangeData?.byTeam?.get(teamKey) || null;
  const teamFactsHtml = renderTeamFactsHtml({
    teamKey,
    stageInfo,
    rc: rcRow,
    homeCity: appState.teamCitiesByTeam.get(teamKey)?.home_city || rcRow?.home_city || '',
    hasCityData: appState.teamCitiesByTeam.size > 0,
    firstRelease: profile?.first_release || appState.firstReleaseByTeam.get(teamKey) || stageInfo?.first_release || '',
    genre,
  });
  const pulseCtx = { timeline, asOf, rc: rcRow };
  const activeTab = activeTeamTab();
  const tabsHtml = renderTeamTabsHtml(teamKey, activeTab, { videos: videos.length || 0 });

  // 정보 구조 v2: 고정 머리 + 탭 7개 (개요·점수·사건·공연·관계·영상·선례) — docs/app_structure_v2.md 2-3
  root.innerHTML = `
    <div class="team-back-bar">
      <button type="button" class="btn btn-sm" id="btnTeamBack">← ${escapeHtml(backLabel)}</button>
    </div>
    <div class="action-banner">
      <div class="team-head">
        <div class="team-avatar-col">
          ${avatarHtml(teamKey, displayName, 72, { shape: 'rounded', genre })}
          ${photoCreditHtml}
        </div>
        <div>
          <div class="team-title-row">
            <h1 class="action-banner-title">${escapeHtml(displayName)}</h1>
            ${dormantBadgeHtml(isDormant)}
            ${newcomerUnverifiedBadgeHtml(teamKey, profile)}
          </div>
          <p class="team-subline">${escapeHtml(metaParts.join(' · ') || '기록된 활동 ' + fmtInt(mergedTimeline.length) + '건')}</p>
          ${teamFactsHtml}
          ${teamAlertsLineHtml}
          ${sceneLineHtml}
          ${outcomesLineHtml}
          ${nextGigHtml}
        </div>
      </div>
      <div class="action-banner-btns">
        ${renderListenButtons(teamKey, displayName, links, videos.length > 0)}
        ${watchButtonHtml(teamKey, displayName, false)}
        ${compareButtonHtml(genre)}
      </div>
    </div>
    ${renderKeyStatsHtml({ scored, rc: rcRow, videos, links, displayName })}

    ${tabsHtml}

    ${teamPanelHtml('overview', activeTab, `
      <section class="block team-pulse" id="teamPulseBlock" aria-label="상태와 변화">
        ${renderTeamStatusBarsHtml({ stageInfo, scored, timeline, sceneWinners, asOf })}
        ${renderChangeRowHtml(pulseCtx)}
      </section>
      ${summarySectionHtml}
    `)}

    ${teamPanelHtml('score', activeTab, scoreSectionHtml)}

    ${teamPanelHtml('events', activeTab, '<section class="block" id="teamActivityBlock"></section>')}

    ${teamPanelHtml('gigs', activeTab, `<section class="block" id="teamGigsBlock">${renderGigBlockHtml({
      teamKey, asOf, gigActs, venueMeta, lineupMap,
      teamCity: appState.teamCitiesByTeam.get(teamKey) || null,
      upcomingList,
    })}</section>`)}

    ${teamPanelHtml('network', activeTab, `
      <div id="teamGraphSection" class="team-graph-section">
        <div id="teamGraphHost" class="team-graph-host"></div>
        ${related.length ? `
          <details class="info-fold team-related-fold" id="teamRelatedFold">
            <summary>같은 무대 · 같은 소속사 목록 표로 보기 (${fmtInt(related.length)}팀)</summary>
            <div class="info-fold-body" id="teamRelatedBody"></div>
          </details>
        ` : ''}
      </div>
    `)}

    ${teamPanelHtml('videos', activeTab, videos.length
      ? '<section class="block" id="teamVideosBlock"></section>'
      : '<section class="block"><h2>영상</h2><p class="muted">아직 연결된 무대 영상이 없어요.</p></section>')}

    ${teamPanelHtml('precedents', activeTab, '<section class="block" id="teamPrecedentsBlock"></section>')}

    <div class="team-report-bar">
      <a class="team-report-link" href="${escapeHtml(reportUrl)}" target="_blank" rel="noopener noreferrer" title="공개 저장소 이슈로 접수돼요 — 개인 연락처는 적지 마세요">정보가 틀려요 ↗</a>
    </div>
  `;

  wireAvatarFallbacks(root);
  wireChangeRow(root, pulseCtx);
  wireScoreBlock(root, scoreCtx);

  function paintRelatedBody() {
    const body = root.querySelector('#teamRelatedBody');
    if (!body) return;
    body.innerHTML = renderRelatedFoldInner();
    wireAvatarFallbacks(body);
    body.querySelector('#btnMoreStageRel')?.addEventListener('click', () => {
      showAllStageRel = true;
      paintRelatedBody();
    });
  }

  function paintActivity() {
    const el = root.querySelector('#teamActivityBlock');
    if (!el) return;
    el.innerHTML = renderActivityInner();
    el.querySelector('#btnTeamTlCsv')?.addEventListener('click', () => {
      if (teamTlCsvSpec) triggerTableCsvExport(teamTlCsvSpec);
    });
    el.querySelector('#btnMoreTimeline')?.addEventListener('click', () => {
      showAllTimeline = true;
      paintActivity();
    });
    el.querySelector('[data-event-more]')?.addEventListener('click', () => {
      showAllEvents = true;
      paintActivity();
    });
  }

  function paintPrecedents() {
    const el = root.querySelector('#teamPrecedentsBlock');
    if (!el) return;
    el.innerHTML = renderPrecedentsInner();
    el.querySelector('#btnMorePrec')?.addEventListener('click', () => {
      showAllPrec = true;
      paintPrecedents();
    });
  }

  function paintVideos() {
    const el = root.querySelector('#teamVideosBlock');
    if (!el) return;
    el.innerHTML = renderVideosInnerHtml(videos, showAllVideos);
    el.querySelectorAll('.video-frame[data-video-id]').forEach(btn => {
      btn.addEventListener('click', () => {
        const vid = btn.dataset.videoId;
        if (!/^[A-Za-z0-9_-]{11}$/.test(vid)) return;
        const wrap = document.createElement('div');
        wrap.className = 'video-frame';
        wrap.innerHTML = `<iframe src="https://www.youtube-nocookie.com/embed/${vid}?autoplay=1" allow="autoplay; encrypted-media; picture-in-picture" allowfullscreen title="무대 영상"></iframe>`;
        btn.replaceWith(wrap);
      });
    });
    el.querySelector('#btnMoreVideos')?.addEventListener('click', () => {
      showAllVideos = true;
      paintVideos();
    });
  }

  paintRelatedBody();
  paintActivity();
  if (eventStarsCache === undefined) {
    loadEventStars().then(m => {
      eventStarsCache = m || null;
      if (!m || !root.isConnected || appState.routeParam !== teamKey) return;
      teamEvents = m.get(teamKey) || [];
      paintActivity();
    }).catch(() => { eventStarsCache = null; });
  }
  paintPrecedents();
  paintVideos();

  // 관계망 그림은 '관계' 탭이 처음 보일 때 그린다 (숨은 칸에서 그리면 크기가 0이 됨)
  const tabs = wireTeamTabs(root, (tab) => {
    if (tab !== 'network') return;
    const graphHost = root.querySelector('#teamGraphHost');
    if (graphHost) {
      mountTeamGraphBlock(graphHost, {
        teamKey,
        displayName,
        primaryGenre: genre,
      });
    }
  });

  root.querySelector('#btnTeamBack')?.addEventListener('click', () => {
    navigateTo(backRoute, backRoute === 'venue' ? (appState.prevParam || '') : '');
  });

  root.querySelector('[data-jump-scene]')?.addEventListener('click', (e) => {
    e.preventDefault();
    appState.focusSceneId = Number(e.currentTarget.dataset.jumpScene);
    navigateTo('venues', '');
  });

  root.querySelector('[data-scroll-videos]')?.addEventListener('click', (e) => {
    e.preventDefault();
    tabs.show('videos');
    root.querySelector('#teamTabs')?.scrollIntoView({ block: 'start' });
  });
}
