import { appState, getWatchlist, hasCustomWeights, navigateTo } from '../state.js';
import { getSnapshotDiff, queryCandidates, queryWatchlistEnriched } from '../db.js';
import {
  escapeHtml, fmtInt, fmtNum, renderActionBanner,
  renderEmptyState, scorePartsLine, watchButtonHtml,
  avatarHtml, spotifyButtonHtml, wireSpotifyButtons,
} from '../ui.js';

export async function renderTodayView(root) {
  const [candRows, watchEnriched] = await Promise.all([
    queryCandidates({ limit: 300 }),
    queryWatchlistEnriched(getWatchlist()),
  ]);

  const top5 = candRows.slice(0, 5);
  const diff = getSnapshotDiff(candRows);
  const watchActive = watchEnriched.filter(w => w.recent_7d > 0);
  const customW = hasCustomWeights();
  const isReconstructed = Boolean(
    diff.prevDate && (appState.snapshots.reconstructed || []).includes(diff.prevDate)
  );

  let showAllNew = false;
  let showAllRisers = false;

  const leadParts = [];
  if (top5.length) {
    leadParts.push(`지금 상위 1위는 <strong>${escapeHtml(top5[0].display_name)}</strong>(${fmtNum(top5[0].score, 2)}점)입니다.`);
  } else {
    leadParts.push('현재 필터 조건에 해당하는 후보 팀이 없습니다.');
  }
  if (diff.latestDate && diff.prevDate) {
    leadParts.push(
      `${diff.prevDate} → ${diff.latestDate} 신규 ${fmtInt(diff.newEntrants.length)}팀, 상승 ${fmtInt(diff.risers.length)}팀.`
    );
  }
  if (watchActive.length) {
    leadParts.push(`관심 팀 중 ${fmtInt(watchActive.length)}팀에 최근 7일 새 신호가 있습니다.`);
  }

  const todo = top5.length
    ? '상위 5팀 카드를 눌러 근거·선례를 보고, 추적할 팀은 관심 목록에 담으세요.'
    : '위쪽 필터에서 조건을 줄여 보거나 초기화해 전체 후보를 확인하세요.';

  const bannerHtml = renderActionBanner({
    title: '오늘 볼 것',
    lead: leadParts.join(' '),
    todo,
    buttonsHtml: `
      <a class="btn" href="#/candidates">전체 후보 (${fmtInt(candRows.length)})</a>
      <a class="btn" href="#/backtest">가중치 조정${customW ? ' (수정됨)' : ''}</a>
    `,
  });

  const top5Html = top5.length
    ? `<div class="grid-5">${top5.map((r, i) => {
        const hasVid = (appState.videosByTeam.get(r.team_key) || []).length > 0;
        return `
          <article class="pick-card">
            <div class="pick-top">
              <span class="pick-rank">#${i + 1}${r.primary_genre ? ` · ${escapeHtml(r.primary_genre)}` : ''}${hasVid ? ' · 영상' : ''}</span>
              <span class="pick-score">${fmtNum(r.score, 2)}</span>
            </div>
            <div class="pick-head">
              ${avatarHtml(r.team_key, r.display_name, 44)}
              <a class="pick-name" href="#/team/${encodeURIComponent(r.team_key)}">${escapeHtml(r.display_name || r.team_key)}</a>
            </div>
            <div class="pick-why">${escapeHtml(scorePartsLine(r))}</div>
            <div class="pick-foot">
              <a class="small muted" href="#/team/${encodeURIComponent(r.team_key)}">근거 보기</a>
              ${spotifyButtonHtml(r.team_key, true)}
              ${watchButtonHtml(r.team_key, r.display_name || r.team_key, true, true)}
            </div>
            <div data-player-slot></div>
          </article>
        `;
      }).join('')}</div>`
    : renderEmptyState({
        title: '조건에 맞는 상위 후보가 없습니다',
        message: '장르·갈래·기간 조건을 줄여 보거나 필터를 초기화해 보세요.',
        showReset: true,
      });

  const snapNoteParts = [];
  if (diff.latestDate && diff.prevDate) {
    snapNoteParts.push(`${diff.prevDate} → ${diff.latestDate}`);
    if (customW) snapNoteParts.push('기본 설정 기준');
    if (isReconstructed) snapNoteParts.push('지난주 점수는 그날까지 신호로 다시 계산한 값');
  }
  const snapNote = snapNoteParts.join(' · ');

  const watchListHtml = !watchEnriched.length
    ? '<p class="muted small" style="margin:0;">아직 담은 관심 팀이 없습니다. 팀에 마우스를 올려 <strong>관심 추가</strong>를 누르거나 상세 화면에서 담아 두세요.</p>'
    : watchActive.length
      ? `<ul class="mini-list">${watchActive.slice(0, 5).map(w => `
          <li>
            <div class="mini-list-main">
              <a href="#/team/${encodeURIComponent(w.team_key)}"><strong>${escapeHtml(w.display_name)}</strong></a>
              <div class="mini-list-sub">7일 신호 ${fmtInt(w.recent_7d)}건 · 최근 ${escapeHtml(w.last_seen || '-')}</div>
            </div>
            <a class="small muted" href="#/team/${encodeURIComponent(w.team_key)}">상세</a>
          </li>
        `).join('')}</ul>`
      : `<p class="muted small" style="margin:0;">관심 팀 ${fmtInt(watchEnriched.length)}팀 중 최근 7일 새 신호는 없습니다. <a href="#/watchlist">관심 목록 보기</a></p>`;

  function paint() {
    const visNew = showAllNew ? diff.newEntrants.slice(0, 20) : diff.newEntrants.slice(0, 5);
    const visRisers = showAllRisers ? diff.risers.slice(0, 20) : diff.risers.slice(0, 5);

    const newHtml = visNew.length
      ? `<ul class="mini-list">${visNew.map(t => `
          <li>
            <div class="mini-list-main">
              <a href="#/team/${encodeURIComponent(t.team_key)}"><strong>${escapeHtml(t.display_name)}</strong></a>
              <div class="mini-list-sub">신규 #${t.rank_now} · ${fmtNum(t.score_now, 2)}점${t.genre ? ` · ${escapeHtml(t.genre)}` : ''}</div>
            </div>
            ${watchButtonHtml(t.team_key, t.display_name, true, true)}
          </li>
        `).join('')}</ul>
        ${!showAllNew && diff.newEntrants.length > 5 ? `<div style="margin-top:8px;"><button type="button" class="btn btn-sm" id="btnMoreNew">${fmtInt(Math.min(20, diff.newEntrants.length) - 5)}팀 더 보기</button></div>` : ''}`
      : '<p class="muted small" style="margin:0;">새로 들어온 팀이 없습니다.</p>';

    const riserHtml = visRisers.length
      ? `<ul class="mini-list">${visRisers.map(t => {
          const deltaParts = [];
          if (t.rank_gain > 0) deltaParts.push(`+${t.rank_gain}계단`);
          if (t.score_gain > 0) deltaParts.push(`+${fmtNum(t.score_gain, 2)}점`);
          return `
            <li>
              <div class="mini-list-main">
                <a href="#/team/${encodeURIComponent(t.team_key)}"><strong>${escapeHtml(t.display_name)}</strong></a>
                <div class="mini-list-sub">#${t.rank_prev} → #${t.rank_now} (${deltaParts.join(', ')})</div>
              </div>
              ${watchButtonHtml(t.team_key, t.display_name, true, true)}
            </li>
          `;
        }).join('')}</ul>
        ${!showAllRisers && diff.risers.length > 5 ? `<div style="margin-top:8px;"><button type="button" class="btn btn-sm" id="btnMoreRisers">${fmtInt(Math.min(20, diff.risers.length) - 5)}팀 더 보기</button></div>` : ''}`
      : '<p class="muted small" style="margin:0;">순위·점수가 크게 오른 팀이 없습니다.</p>';

    root.innerHTML = `
      ${bannerHtml}
      <div class="block-head" style="border:none;margin-bottom:8px;padding:0;">
        <h2>지금 점수 상위 5팀</h2>
        <span class="block-meta">기준일 ${escapeHtml(appState.cfg.as_of)} · 첫 등장 ${appState.cfg.newcomer_years}년 이내</span>
      </div>
      ${top5Html}

      <div class="grid-3">
        <section class="block" style="margin-bottom:0;">
          <div class="block-head">
            <h3>이번 주 새로 후보에 들어온 팀</h3>
            <span class="block-meta">${fmtInt(diff.newEntrants.length)}</span>
          </div>
          ${newHtml}
          ${snapNote ? `<p class="muted small" style="margin:8px 0 0 0;">${escapeHtml(snapNote)}</p>` : ''}
        </section>

        <section class="block" style="margin-bottom:0;">
          <div class="block-head">
            <h3>점수·순위가 오른 팀</h3>
            <span class="block-meta">${fmtInt(diff.risers.length)}</span>
          </div>
          ${riserHtml}
          ${snapNote ? `<p class="muted small" style="margin:8px 0 0 0;">${escapeHtml(snapNote)}</p>` : ''}
        </section>

        <section class="block" style="margin-bottom:0;">
          <div class="block-head">
            <h3>최근 7일 새 신호가 들어온 관심 팀</h3>
            <span class="block-meta">${fmtInt(watchActive.length)} / ${fmtInt(watchEnriched.length)}</span>
          </div>
          ${watchListHtml}
        </section>
      </div>
    `;

    wireSpotifyButtons(root);
    root.querySelector('#btnMoreNew')?.addEventListener('click', () => { showAllNew = true; paint(); });
    root.querySelector('#btnMoreRisers')?.addEventListener('click', () => { showAllRisers = true; paint(); });
    root.querySelectorAll('[data-open-team]').forEach(el => {
      el.addEventListener('click', () => navigateTo('team', el.dataset.openTeam));
    });
  }

  paint();
}
