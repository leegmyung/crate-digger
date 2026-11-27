import {
  appState, getWatchlist, getWatchlistViewMode, setExportContext,
  setWatchlistViewMode, setWatchStatus, syncHash, toggleWatch, WATCH_STATUSES,
} from '../state.js';
import { loadAlertsJson, queryWatchlistEnriched } from '../db.js';
import { loadEventStars } from '../db_team_extras.js';
import { renderWatchWeeklySummaryHtml } from './today_alerts.js';
import { renderVenueSubsHtml, wireVenueSubs } from './venue_subs_view.js';
import {
  avatarHtml, clampDateDisplay, escapeHtml, fmtInt, fmtNum, naCell,
  renderActionBanner, renderEmptyState, renderNoRecordLine, renderTableCsvBtn,
  spotifyButtonHtml, triggerTableCsvExport, wireAvatarFallbacks,
  wireSpotifyButtons, youtubeQuickInfo,
} from '../ui.js';

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
  const raw = getWatchlist();
  const [rows, alertsData, eventStarsMap] = await Promise.all([
    queryWatchlistEnriched(raw),
    loadAlertsJson().catch(() => null),
    loadEventStars(),
  ]);
  // 5-4 관심 팀 주간 요약 (alerts.json 재사용)
  const weeklySummaryHtml = rows.length
    ? renderWatchWeeklySummaryHtml(alertsData, new Set(rows.map(r => r.team_key)), eventStarsMap)
    : '';
  const recentActive = rows.filter(r => r.recent_7d > 0).length;
  const statusMap = Object.fromEntries(WATCH_STATUSES.map(s => [s.id, s.label]));

  let viewMode = (appState.watchModeParam === 'board' || appState.watchModeParam === 'table')
    ? appState.watchModeParam
    : getWatchlistViewMode();
  appState.watchModeParam = viewMode;
  setWatchlistViewMode(viewMode);

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
      csvLabel: rows.length ? `관심 목록 CSV 내려받기 (${fmtInt(rows.length)}팀)` : '',
      csvFilename: spec.filename,
      csvHeaders: spec.headers,
      csvRows: spec.rows,
    });
    return spec;
  };
  syncWatchExport();

  const bannerHtml = renderActionBanner({
    title: '관심 목록',
    lead: rows.length
      ? `담아 둔 <strong>${fmtInt(rows.length)}팀</strong> 중 최근 7일 새 신호가 들어온 팀은 <strong>${fmtInt(recentActive)}팀</strong>입니다.`
      : '관심 목록은 선택 사항입니다. 추적하고 싶은 팀이 생길 때만 담아 두세요.',
    buttonsHtml: rows.length
      ? `<div class="view-mode-switch" role="group" aria-label="보기 방식">
          <button type="button" class="btn btn-sm ${viewMode === 'table' ? 'btn-active' : ''}" data-wmode="table">표</button>
          <button type="button" class="btn btn-sm ${viewMode === 'board' ? 'btn-active' : ''}" data-wmode="board">보드</button>
         </div>`
      : '<a class="btn" href="#/today">이번 주 브리핑 보기</a>',
  });

  if (!rows.length) {
    root.innerHTML = `
      ${bannerHtml}
      ${renderEmptyState({
        message: '관심 목록이 비어 있습니다. 브리핑·후보 목록·팀 상세에서 ☆ 관심 추가를 누르면 최근 7일 새 신호와 순위 변동을 한곳에 모아 봅니다.',
        showReset: false,
        actionLabel: '후보 목록에서 고르기',
        actionHref: '#/candidates',
      })}
      ${renderVenueSubsHtml(alertsData, { editable: true })}
    `;
    wireVenueSubs(root, () => renderWatchlistView(root));
    return;
  }

  const snapLabel = appState.snapshots.latestDate && appState.snapshots.prevDate
    ? `${appState.snapshots.prevDate} → ${appState.snapshots.latestDate}`
    : '';
  const hasAnyImg = rows.some(r => appState.imagesByTeam.has(r.team_key));

  function paint() {
    const modeBtns = `
      <div class="view-mode-switch" role="group" aria-label="보기 방식">
        <button type="button" class="btn btn-sm ${viewMode === 'table' ? 'btn-active' : ''}" data-wmode="table">표</button>
        <button type="button" class="btn btn-sm ${viewMode === 'board' ? 'btn-active' : ''}" data-wmode="board">보드</button>
      </div>
    `;

    const headHtml = renderActionBanner({
      title: '관심 목록',
      lead: `담아 둔 <strong>${fmtInt(rows.length)}팀</strong> 중 최근 7일 새 신호가 들어온 팀은 <strong>${fmtInt(recentActive)}팀</strong>입니다.`,
      buttonsHtml: modeBtns,
    });

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

    root.innerHTML = `
      ${headHtml}
      ${weeklySummaryHtml}
      ${renderVenueSubsHtml(alertsData, { editable: true })}
      ${contentHtml}
      ${hasAnyImg ? '<p class="photo-credit">아티스트 사진 출처: Spotify</p>' : ''}
    `;

    wireAvatarFallbacks(root);
    wireSpotifyButtons(root);
    wireVenueSubs(root, () => renderWatchlistView(root));

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
      btn.addEventListener('click', () => {
        toggleWatch(btn.dataset.removeWatch);
        renderWatchlistView(root);
      });
    });
  }

  paint();
}
