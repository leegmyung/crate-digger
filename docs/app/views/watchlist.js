import {
  appState, exportWatchlistCsv, getWatchlist, toggleWatch,
} from '../state.js';
import { queryWatchlistEnriched } from '../db.js';
import {
  clampDateDisplay, escapeHtml, fmtInt, fmtNum, renderActionBanner,
} from '../ui.js';

export async function renderWatchlistView(root) {
  const raw = getWatchlist();
  const rows = await queryWatchlistEnriched(raw);
  const recentActive = rows.filter(r => r.recent_7d > 0).length;

  const bannerHtml = renderActionBanner({
    title: '관심 목록',
    lead: rows.length
      ? `현재 <strong>${fmtInt(rows.length)}팀</strong>을 추적 중이며, 최근 7일 새 신호가 들어온 팀은 <strong>${fmtInt(recentActive)}팀</strong>입니다.`
      : '아직 관심 목록에 담은 팀이 없습니다.',
    todo: rows.length
      ? '새 신호가 들어온 팀을 눌러 타임라인을 확인하거나 CSV로 내려받아 공유하세요.'
      : '오늘 볼 것 또는 후보 탐색 화면에서 관심 추가 버튼을 눌러 팀을 모아 보세요.',
    buttonsHtml: `
      ${rows.length ? '<button type="button" class="btn btn-primary" id="btnExportWatch">CSV 내려받기</button>' : ''}
      <a class="btn" href="#/today">오늘 볼 것으로</a>
    `,
  });

  if (!rows.length) {
    root.innerHTML = `
      ${bannerHtml}
      <div class="block">
        <p class="muted" style="margin:0;">관심 목록은 이 브라우저(localStorage)에 저장됩니다. 후보 카드나 후보 탐색 표에서 <strong>관심 추가</strong>를 누르면 여기에 모입니다.</p>
      </div>
    `;
    return;
  }

  const snapLabel = appState.snapshots.latestDate && appState.snapshots.prevDate
    ? `${appState.snapshots.prevDate} → ${appState.snapshots.latestDate}`
    : '';

  root.innerHTML = `
    ${bannerHtml}
    <div class="block" style="padding:0;overflow:hidden;">
      <div class="table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>팀</th>
              <th class="num">현재 점수</th>
              <th class="num nowrap">스냅샷 순위 변화 ${snapLabel ? `(${escapeHtml(snapLabel)})` : ''}</th>
              <th class="num nowrap">최근 7일 신호</th>
              <th class="nowrap">최근 신호일</th>
              <th class="nowrap">담은 날</th>
              <th class="nowrap">관리</th>
            </tr>
          </thead>
          <tbody>
            ${rows.map(r => {
              let deltaStr = '-';
              if (r.is_new_in_snap) deltaStr = `신규 #${r.rank_now}`;
              else if (r.rank_now !== null && r.rank_delta !== null) {
                const sign = r.rank_delta > 0 ? `+${r.rank_delta}` : `${r.rank_delta}`;
                deltaStr = `#${r.rank_now} (${r.rank_delta === 0 ? '유지' : sign})`;
              } else if (r.rank_now !== null) {
                deltaStr = `#${r.rank_now}`;
              }
              return `
                <tr>
                  <td>
                    <a href="#/team/${encodeURIComponent(r.team_key)}"><strong>${escapeHtml(r.display_name)}</strong></a>
                    ${r.primary_genre ? `<div class="muted small">${escapeHtml(r.primary_genre)}</div>` : ''}
                  </td>
                  <td class="num"><strong>${r.score !== null ? fmtNum(r.score, 2) : '-'}</strong></td>
                  <td class="num nowrap">${escapeHtml(deltaStr)}</td>
                  <td class="num">${r.recent_7d > 0 ? `<strong>${fmtInt(r.recent_7d)}건</strong>` : '0건'}</td>
                  <td class="nowrap mono muted">${escapeHtml(clampDateDisplay(r.last_seen))}</td>
                  <td class="nowrap mono muted">${escapeHtml(r.added_at || '-')}</td>
                  <td class="nowrap">
                    <a class="btn btn-sm" href="#/team/${encodeURIComponent(r.team_key)}">상세</a>
                    <button type="button" class="btn btn-sm" data-remove-watch="${escapeHtml(r.team_key)}">제거</button>
                  </td>
                </tr>
              `;
            }).join('')}
          </tbody>
        </table>
      </div>
    </div>
  `;

  root.querySelector('#btnExportWatch')?.addEventListener('click', () => exportWatchlistCsv(rows));
  root.querySelectorAll('[data-remove-watch]').forEach(btn => {
    btn.addEventListener('click', () => {
      toggleWatch(btn.dataset.removeWatch);
      renderWatchlistView(root);
    });
  });
}
