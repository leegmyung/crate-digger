/**
 * 정보 구조 v2 '내 목록' (#/mine?tab=watch|venues|filters)
 * - 관심 팀 (표|보드, 상태 변경, 최근 7일 주간 요약, CSV)
 * - 구독 공연장 (venue_subs_view.js 재사용 + 빈 상태)
 * - 저장한 필터 (mine.js — 조건 요약, 이름 변경·삭제, 발굴에서 열기, 지난 7일 새로 맞은 팀)
 */
import {
  appState, getWatchlist, getWatchlistViewMode, setExportContext,
  setWatchlistViewMode, setWatchStatus, syncHash, toggleWatch, WATCH_STATUSES,
} from '../state.js';
import {
  ensureVideosLoaded, loadAlertsJson, queryDiscoveryStages, queryUpcomingGigs, queryWatchlistEnriched,
} from '../db.js';
import { watchSummary, watchSummaryLine } from '../watch_summary.js';
import { loadEventStars } from '../db_team_extras.js';
import { listSavedFilters } from '../saved_filters.js';
import { listVenueSubs } from '../venue_subs.js';
import { alertsCarryStars, renderWatchWeeklySummaryHtml } from './today_alerts.js';
import {
  fillMineFiltersMatches, normalizeMineTab, renderEvidenceFooterHtml,
  renderMineFiltersPanelHtml, renderMineTabsHtml, renderMineVenuesPanelHtml,
  wireMineFiltersPanel, wireMineVenuesPanel,
} from './mine.js';
import {
  avatarHtml, clampDateDisplay, escapeHtml, fmtInt, fmtNum, naCell, STAGE_META,
  renderActionBanner, renderEmptyState, renderNoRecordLine, renderTableCsvBtn,
  spotifyButtonHtml, triggerTableCsvExport, wireAvatarFallbacks,
  wireSpotifyButtons, youtubeQuickInfo,
} from '../ui.js';

const UPCOMING_DAYS = 30;

/** 내 목록 분석 카드 — 단계 분포 막대 · 최근 움직임 · 다가오는 공연 · 장르 (watch_summary.js) */
function renderWatchAnalysisHtml(sum) {
  if (!sum.total) return '';
  const seg = (n) => `${Math.max(2, Math.round((n / sum.total) * 100))}%`;
  const bar = [
    ...sum.stages.map(s => `<span class="wa-seg wa-seg-s${s.stage}" style="width:${seg(s.n)}" title="${escapeHtml(`${s.label} ${s.n}팀`)}"></span>`),
    sum.noStage ? `<span class="wa-seg wa-seg-none" style="width:${seg(sum.noStage)}" title="${escapeHtml(`단계 계산 안 됨 ${sum.noStage}팀`)}"></span>` : '',
  ].join('');
  const legend = [
    ...sum.stages.map(s => `<span class="wa-leg"><i class="wa-dot wa-seg-s${s.stage}"></i>${escapeHtml(s.label)} ${fmtInt(s.n)}</span>`),
    sum.noStage ? `<span class="wa-leg"><i class="wa-dot wa-seg-none"></i>계산 안 됨 ${fmtInt(sum.noStage)}</span>` : '',
  ].join('');
  const gigs = sum.nextGigs.length
    ? `<ul class="wa-gigs">${sum.nextGigs.map(g => `<li><span class="mono small">${escapeHtml(g.date.slice(5))}</span> <a href="#/team/${encodeURIComponent(g.team_key)}/gigs">${escapeHtml(g.name)}</a> <span class="small muted">${escapeHtml(g.venue)}</span></li>`).join('')}</ul>
       ${sum.upcomingTotal > sum.nextGigs.length ? `<p class="small muted">외 ${fmtInt(sum.upcomingTotal - sum.nextGigs.length)}회</p>` : ''}`
    : '<p class="small muted">잡힌 공연 없음</p>';
  return `
    <section class="block watch-analysis" aria-label="내 목록 분석">
      <div class="block-head"><h2>목록 분석</h2><span class="small muted">${escapeHtml(watchSummaryLine(sum, UPCOMING_DAYS))}</span></div>
      <div class="wa-grid">
        <div class="wa-cell">
          <h3>발굴 단계</h3>
          <div class="wa-bar" role="img" aria-label="${escapeHtml(sum.stages.map(s => `${s.label} ${s.n}팀`).join(', '))}">${bar}</div>
          <div class="wa-legend">${legend}</div>
        </div>
        <div class="wa-cell">
          <h3>최근 움직임</h3>
          <div class="wa-nums">
            <span><strong>${fmtInt(sum.active7d)}</strong><small>7일 새 신호</small></span>
            <span class="is-up"><strong>▲${fmtInt(sum.rankUp)}</strong><small>순위 오름</small></span>
            <span class="is-down"><strong>▼${fmtInt(sum.rankDown)}</strong><small>순위 내림</small></span>
          </div>
        </div>
        <div class="wa-cell">
          <h3>다가오는 공연 (${UPCOMING_DAYS}일)</h3>
          ${gigs}
        </div>
        <div class="wa-cell">
          <h3>장르</h3>
          ${sum.topGenres.length ? `<p class="small">${sum.topGenres.map(g => `${escapeHtml(g.genre)} ${fmtInt(g.n)}`).join(' · ')}</p>` : '<p class="small muted">장르 모름</p>'}
        </div>
      </div>
    </section>`;
}

function statusSelectHtml(teamKey, curStatus) {
  return `
    <select class="select status-pill-select status-${escapeHtml(curStatus)}" data-watch-status="${escapeHtml(teamKey)}" aria-label="관심 상태">
      ${WATCH_STATUSES.map(s => `<option value="${s.id}" ${s.id === curStatus ? 'selected' : ''}>${escapeHtml(s.label)}</option>`).join('')}
    </select>
  `;
}

function renderDeltaStr(r) {
  if (r.is_new_in_snap) return `신규 #${r.rank_now}`;
  if (r.rank_now !== null && r.rank_delta !== null) {
    const sign = r.rank_delta > 0 ? `+${r.rank_delta}` : `${r.rank_delta}`;
    return `#${r.rank_now} (${r.rank_delta === 0 ? '유지' : sign})`;
  }
  if (r.rank_now !== null) return `#${r.rank_now}`;
  return '—';
}

function renderListenQuick(r, mode, slotId) {
  const sp = spotifyButtonHtml(r.team_key, true, {
    iconOnly: true,
    mode,
    slotId,
    teamName: r.display_name,
  });
  if (sp) return sp;
  const yt = youtubeQuickInfo(r.team_key);
  if (yt && yt.kind === 'channel') {
    return `<a class="btn btn-icon btn-yt-mini" href="${escapeHtml(yt.url)}" target="_blank" rel="noopener noreferrer" title="유튜브 공식 채널">YT</a>`;
  }
  if (yt && yt.kind === 'video') {
    return `<a class="btn btn-icon btn-yt-mini" href="#/team/${encodeURIComponent(r.team_key)}" title="최근 무대 영상">영상</a>`;
  }
  return '';
}

export async function renderWatchlistView(root) {
  let rows = [];
  let alertsData = null;
  let eventStarsMap = null;
  let summary = null;

  async function loadAll() {
    const raw = getWatchlist();
    // 별점 파일(event_stars.csv)은 alerts.json 이 별점을 직접 담아 오지 않을 때만 받는다
    const alertsP = loadAlertsJson().catch(() => null);
    const [enriched, alerts, stars] = await Promise.all([
      queryWatchlistEnriched(raw),
      alertsP,
      alertsP.then(a => (alertsCarryStars(a) ? null : loadEventStars().catch(() => null))),
      ensureVideosLoaded().catch(() => null), // '영상' 버튼(스포티파이·유튜브 채널 없는 팀)용
    ]);
    rows = enriched;
    alertsData = alerts;
    eventStarsMap = stars;
    summary = null;
    if (rows.length) {
      const asOf = appState.cfg.as_of || appState.dataEnd;
      const [stageData, upcoming] = await Promise.all([
        queryDiscoveryStages({ as_of: asOf }).catch(() => null),
        queryUpcomingGigs({ asOf, days: UPCOMING_DAYS }).catch(() => []),
      ]);
      summary = watchSummary({
        teams: rows,
        stageByTeam: new Map((stageData?.rows || []).map(s => [s.team_key, s.stage])),
        stageLabels: Object.fromEntries(Object.entries(STAGE_META).map(([k, v]) => [k, v.label])),
        upcoming,
      });
    }
  }

  await loadAll();

  const statusMap = Object.fromEntries(WATCH_STATUSES.map(s => [s.id, s.label]));
  let activeTab = normalizeMineTab(appState.mineTab);
  appState.mineTab = activeTab;

  let viewMode = (appState.watchModeParam === 'board' || appState.watchModeParam === 'table')
    ? appState.watchModeParam
    : getWatchlistViewMode();
  appState.watchModeParam = viewMode;
  setWatchlistViewMode(viewMode);

  const filterUi = { renamingId: '', notice: '' };

  const buildWatchCsvSpec = () => ({
    filename: `crate_digger_watchlist_${appState.dataEnd || 'export'}.csv`,
    headers: ['팀', '장르', '상태', '현재 점수', '순위 변화', '최근 7일', '최근 신호일'],
    rows: rows.map(r => [
      r.display_name || r.team_key,
      r.primary_genre || '',
      statusMap[r.status] || '지켜보는 중',
      r.score !== null && r.score !== undefined ? fmtNum(r.score, 2) : '—',
      renderDeltaStr(r),
      `${r.recent_7d ?? 0}건`,
      clampDateDisplay(r.last_seen),
    ]),
  });

  const syncWatchExport = () => {
    const spec = buildWatchCsvSpec();
    setExportContext({
      csvLabel: activeTab === 'watch' && rows.length ? `관심 팀 CSV 내려받기 (${fmtInt(rows.length)}팀)` : '',
      csvFilename: spec.filename,
      csvHeaders: spec.headers,
      csvRows: spec.rows,
    });
    return spec;
  };

  const snapLabel = appState.snapshots.latestDate && appState.snapshots.prevDate
    ? `${appState.snapshots.prevDate} → ${appState.snapshots.latestDate}`
    : '';

  function buildWatchPanelHtml() {
    if (!rows.length) {
      return renderEmptyState({
        title: '관심 팀이 비어 있습니다',
        message: '홈·발굴·팀 페이지에서 ☆ 관심 추가를 누르면 최근 7일 새 신호와 순위 변동을 한곳에 모아 봅니다.',
        showReset: false,
        actionLabel: '발굴에서 팀 고르기',
        actionHref: '#/discover',
      });
    }

    const weeklySummaryHtml = renderWatchWeeklySummaryHtml(
      alertsData,
      new Set(rows.map(r => r.team_key)),
      eventStarsMap,
    );
    const hasAnyImg = rows.some(r => appState.imagesByTeam.has(r.team_key));

    const contentHtml = viewMode === 'board'
      ? `
        <div class="watch-board">
          ${WATCH_STATUSES.map(col => {
            const colRows = rows.filter(r => (r.status || 'watching') === col.id);
            const otherStatuses = WATCH_STATUSES.filter(s => s.id !== col.id);
            return `
              <section class="watch-col">
                <div class="watch-col-head">
                  <h3>${escapeHtml(col.label)}</h3>
                  <span class="block-meta">${fmtInt(colRows.length)}</span>
                </div>
                <div class="watch-col-cards">
                  ${colRows.length ? colRows.map(r => `
                    <article class="watch-card">
                      <div class="watch-card-top">
                        <a class="row-team-cell" href="#/team/${encodeURIComponent(r.team_key)}">
                          ${avatarHtml(r.team_key, r.display_name, 36, { shape: 'rounded', genre: r.primary_genre })}
                          <div class="row-team-text">
                            <strong>${escapeHtml(r.display_name)}</strong>
                            <div class="small muted">${r.score !== null && r.score !== undefined ? `${fmtNum(r.score, 2)}점` : naCell('현재 점수 후보군에 포함되지 않았습니다')}${r.primary_genre ? ` · ${escapeHtml(r.primary_genre)}` : ''}</div>
                          </div>
                        </a>
                        ${renderListenQuick(r, '', 'watchBoardPlayerSlot')}
                      </div>
                      <div class="watch-card-meta">
                        ${r.recent_7d > 0 ? `<span class="badge-new">7일 +${fmtInt(r.recent_7d)}건</span>` : '<span class="small muted">7일 0건</span>'}
                        <span class="small muted mono">${r.rank_now !== null ? escapeHtml(renderDeltaStr(r)) : naCell('상위 300 스냅샷 밖입니다')}</span>
                      </div>
                      <div class="watch-card-foot">
                        <div class="watch-move-btns">
                          ${otherStatuses.map(ns => `<button type="button" class="btn btn-sm" data-move-key="${escapeHtml(r.team_key)}" data-move-status="${ns.id}">${escapeHtml(ns.label)}</button>`).join('')}
                        </div>
                        <button type="button" class="btn btn-sm" data-remove-watch="${escapeHtml(r.team_key)}">제거</button>
                      </div>
                    </article>
                  `).join('') : renderNoRecordLine(`${col.label} 상태의 관심 팀이 아직 없습니다`)}
                </div>
              </section>
            `;
          }).join('')}
        </div>
        <div class="player-slot" id="watchBoardPlayerSlot" data-player-slot></div>
      `
      : `
        <div class="block" style="padding:0;overflow:hidden;">
          <div class="table-bar">
            <div class="table-bar-left">
              <strong>관심 팀 (${fmtInt(rows.length)}팀)</strong>
            </div>
            <div class="table-bar-right">
              ${renderTableCsvBtn('btnWatchCsv', 'CSV 내려받기')}
            </div>
          </div>
          <div class="table-wrap table-sticky">
            <table class="data-table">
              <thead>
                <tr>
                  <th>팀</th>
                  <th class="nowrap">듣기</th>
                  <th class="nowrap">상태</th>
                  <th class="num">현재 점수</th>
                  <th class="num nowrap">순위 변화 ${snapLabel ? `(${escapeHtml(snapLabel)})` : ''}</th>
                  <th class="num nowrap">최근 7일</th>
                  <th class="nowrap">최근 신호일</th>
                  <th class="nowrap">관리</th>
                </tr>
              </thead>
              <tbody>
                ${rows.map(r => `
                  <tr>
                    <td>
                      <a class="row-team-cell" href="#/team/${encodeURIComponent(r.team_key)}">
                        ${avatarHtml(r.team_key, r.display_name, 28, { shape: 'circle', genre: r.primary_genre })}
                        <div class="row-team-text">
                          <strong class="cell-truncate" title="${escapeHtml(r.display_name)}">${escapeHtml(r.display_name)}</strong>
                          ${r.primary_genre ? `<div class="muted small row-team-sub cell-truncate" title="${escapeHtml(r.primary_genre)}">${escapeHtml(r.primary_genre)}</div>` : ''}
                        </div>
                      </a>
                    </td>
                    <td class="nowrap">${renderListenQuick(r, 'table-row', '')}</td>
                    <td class="nowrap">${statusSelectHtml(r.team_key, r.status || 'watching')}</td>
                    <td class="num">${r.score !== null && r.score !== undefined ? `<strong>${fmtNum(r.score, 2)}</strong>` : naCell('현재 점수 후보군에 포함되지 않았습니다')}</td>
                    <td class="num nowrap">${r.rank_now !== null ? escapeHtml(renderDeltaStr(r)) : naCell('상위 300 스냅샷 밖입니다')}</td>
                    <td class="num">${r.recent_7d > 0 ? `<span class="badge-new">${fmtInt(r.recent_7d)}건</span>` : '<span class="muted">0건</span>'}</td>
                    <td class="nowrap mono muted">${r.last_seen ? escapeHtml(clampDateDisplay(r.last_seen)) : naCell('수집된 신호 기록이 없습니다')}</td>
                    <td class="nowrap">
                      <button type="button" class="btn btn-sm" data-remove-watch="${escapeHtml(r.team_key)}">제거</button>
                    </td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          </div>
        </div>
      `;

    return `
      ${summary ? renderWatchAnalysisHtml(summary) : ''}
      ${weeklySummaryHtml}
      ${contentHtml}
      ${hasAnyImg ? '<p class="photo-credit">아티스트 사진 출처: Spotify</p>' : ''}
    `;
  }

  function paint() {
    syncWatchExport();
    const recentActive = rows.filter(r => r.recent_7d > 0).length;
    const venueCount = listVenueSubs().length;
    const filterCount = listSavedFilters().length;

    let leadHtml = '';
    let buttonsHtml = '';
    if (activeTab === 'watch') {
      leadHtml = rows.length
        ? `관심 팀 <strong>${fmtInt(rows.length)}팀</strong> 중 최근 7일 새 신호가 들어온 팀은 <strong>${fmtInt(recentActive)}팀</strong>입니다.`
        : '관심 팀·구독 공연장·저장한 필터를 한곳에 모아 관리합니다.';
      buttonsHtml = rows.length
        ? `<div class="view-mode-switch" role="group" aria-label="보기 방식">
            <button type="button" class="btn btn-sm ${viewMode === 'table' ? 'btn-active' : ''}" data-wmode="table">표</button>
            <button type="button" class="btn btn-sm ${viewMode === 'board' ? 'btn-active' : ''}" data-wmode="board">보드</button>
           </div>`
        : '<a class="btn btn-sm" href="#/alerts">알림 센터 →</a>';
    } else if (activeTab === 'venues') {
      leadHtml = venueCount
        ? `구독 중인 공연장 <strong>${fmtInt(venueCount)}곳</strong>의 신인·새 공연 소식을 모아 봅니다.`
        : '관심 공연장을 구독해 두면 새 공연과 첫 무대 신인 소식을 받아 봅니다.';
      buttonsHtml = '<a class="btn btn-sm" href="#/venues">공연장 목록 →</a>';
    } else {
      leadHtml = filterCount
        ? `저장한 필터 <strong>${fmtInt(filterCount)}개</strong> — 매주 기준일 대비 새로 맞는 팀을 계산합니다.`
        : '발굴 조건을 저장해 두면 매주 조건에 새로 들어온 팀을 자동으로 확인합니다.';
      buttonsHtml = '<a class="btn btn-sm" href="#/discover">발굴 열기 →</a>';
    }

    const headHtml = renderActionBanner({
      title: '내 목록',
      lead: leadHtml,
      buttonsHtml,
    });

    const tabsHtml = renderMineTabsHtml(activeTab, {
      watchCount: rows.length,
      venueCount,
      filterCount,
    });

    let bodyHtml = '';
    if (activeTab === 'watch') {
      bodyHtml = buildWatchPanelHtml();
    } else if (activeTab === 'venues') {
      bodyHtml = renderMineVenuesPanelHtml(alertsData);
    } else {
      bodyHtml = renderMineFiltersPanelHtml(filterUi);
    }

    root.innerHTML = `
      <div class="mine-page" id="minePageRoot">
        ${headHtml}
        ${tabsHtml}
        <div class="mine-panel" role="tabpanel">
          ${bodyHtml}
        </div>
        ${renderEvidenceFooterHtml()}
      </div>
    `;

    // Tab switching
    root.querySelectorAll('[data-mine-tab]').forEach(btn => {
      btn.addEventListener('click', () => {
        const next = normalizeMineTab(btn.dataset.mineTab);
        if (activeTab === next) return;
        activeTab = next;
        appState.mineTab = activeTab;
        syncHash(true);
        paint();
      });
    });

    if (activeTab === 'watch') {
      wireAvatarFallbacks(root);
      wireSpotifyButtons(root);

      root.querySelector('#btnWatchCsv')?.addEventListener('click', () => {
        triggerTableCsvExport(syncWatchExport());
      });

      root.querySelectorAll('[data-wmode]').forEach(btn => {
        btn.addEventListener('click', () => {
          viewMode = btn.dataset.wmode;
          appState.watchModeParam = viewMode;
          setWatchlistViewMode(viewMode);
          syncHash(true);
          paint();
        });
      });

      root.querySelectorAll('[data-watch-status]').forEach(sel => {
        sel.addEventListener('change', () => {
          const key = sel.dataset.watchStatus;
          const nextStatus = sel.value;
          setWatchStatus(key, nextStatus);
          const item = rows.find(r => r.team_key === key);
          if (item) item.status = nextStatus;
          syncWatchExport();
          paint();
        });
      });

      root.querySelectorAll('[data-move-key]').forEach(btn => {
        btn.addEventListener('click', () => {
          const key = btn.dataset.moveKey;
          const nextStatus = btn.dataset.moveStatus;
          setWatchStatus(key, nextStatus);
          const item = rows.find(r => r.team_key === key);
          if (item) item.status = nextStatus;
          syncWatchExport();
          paint();
        });
      });

      root.querySelectorAll('[data-remove-watch]').forEach(btn => {
        btn.addEventListener('click', async () => {
          toggleWatch(btn.dataset.removeWatch);
          await loadAll();
          paint();
        });
      });
    } else if (activeTab === 'venues') {
      wireMineVenuesPanel(root, () => paint());
    } else {
      wireMineFiltersPanel(root, filterUi, () => paint());
      fillMineFiltersMatches(root);
    }
  }

  paint();

  const onExternalChange = async () => {
    const host = root.querySelector('#minePageRoot');
    if (!host || !host.isConnected) {
      window.removeEventListener('app:watchlist', onExternalChange);
      window.removeEventListener('app:venue-subs', onExternalChange);
      return;
    }
    await loadAll();
    if (!host.isConnected) return;
    paint();
  };
  window.addEventListener('app:watchlist', onExternalChange);
  window.addEventListener('app:venue-subs', onExternalChange);
}
