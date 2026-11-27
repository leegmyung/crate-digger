import { appState, getWatchlist, hasCustomWeights, navigateTo } from '../state.js';
import { getSnapshotDiff, queryCandidates, queryWatchlistEnriched } from '../db.js';
import {
  escapeHtml, fmtInt, fmtNum, renderActionBanner,
  scorePartsLine, watchButtonHtml,
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

  const leadParts = [];
  if (top5.length) {
    leadParts.push(`지금 상위 1위는 <strong>${escapeHtml(top5[0].display_name)}</strong>(${fmtNum(top5[0].score, 2)}점)입니다.`);
  } else {
    leadParts.push('현재 필터 조건에 해당하는 후보 팀이 없습니다.');
  }
  if (diff.latestDate && diff.prevDate) {
    leadParts.push(
      `${diff.prevDate} → ${diff.latestDate} 사이 신규 진입 ${fmtInt(diff.newEntrants.length)}팀, 순위·점수 상승 ${fmtInt(diff.risers.length)}팀입니다.`
    );
  }
  if (watchActive.length) {
    leadParts.push(`관심 팀 중 ${fmtInt(watchActive.length)}팀에 최근 7일 새 신호가 들어왔습니다.`);
  }

  const todo = top5.length
    ? '상위 5팀 카드를 눌러 근거·과거 선례를 확인하고, 추적할 팀은 관심 목록에 담아 두세요.'
    : '위쪽 선택 창에서 장르·기간·갈래 조건을 넓혀 보세요.';

  const bannerHtml = renderActionBanner({
    title: '오늘 볼 것',
    lead: leadParts.join(' '),
    todo,
    buttonsHtml: `
      <a class="btn" href="#/candidates">전체 후보 (${fmtInt(candRows.length)}팀)</a>
      <a class="btn" href="#/backtest">점수 가중치 조정${customW ? ' (변경됨)' : ''}</a>
    `,
  });

  const top5Html = top5.length
    ? `<div class="grid-5">${top5.map((r, i) => `
        <article class="pick-card">
          <div class="pick-top">
            <span class="pick-rank">#${i + 1}${r.primary_genre ? ` · ${escapeHtml(r.primary_genre)}` : ''}</span>
            <span class="pick-score">${fmtNum(r.score, 2)}점</span>
          </div>
          <a class="pick-name" href="#/team/${encodeURIComponent(r.team_key)}">${escapeHtml(r.display_name || r.team_key)}</a>
          <div class="pick-why">${escapeHtml(scorePartsLine(r))}</div>
          <div class="pick-actions">
            ${watchButtonHtml(r.team_key, r.display_name || r.team_key, true)}
            <a class="btn btn-sm" href="#/team/${encodeURIComponent(r.team_key)}">팀 상세</a>
          </div>
        </article>
      `).join('')}</div>`
    : '<div class="notice">조건에 맞는 상위 후보가 없습니다. 필터를 초기화해 보세요.</div>';

  const snapLabel = diff.latestDate && diff.prevDate
    ? `${diff.prevDate} → ${diff.latestDate} 비교 (기본 가중치 상위 300팀)`
    : '비교 스냅샷 없음';

  const newListHtml = diff.newEntrants.length
    ? `<ul class="mini-list">${diff.newEntrants.slice(0, 8).map(t => `
        <li>
          <div class="mini-list-main">
            <a href="#/team/${encodeURIComponent(t.team_key)}"><strong>${escapeHtml(t.display_name)}</strong></a>
            <div class="mini-list-sub">신규 #${t.rank_now} · ${fmtNum(t.score_now, 2)}점${t.genre ? ` · ${escapeHtml(t.genre)}` : ''}</div>
          </div>
          ${watchButtonHtml(t.team_key, t.display_name, true)}
        </li>
      `).join('')}</ul>`
    : '<p class="muted small" style="margin:0;">비교 기간 내 새로 들어온 팀이 없습니다.</p>';

  const riserListHtml = diff.risers.length
    ? `<ul class="mini-list">${diff.risers.slice(0, 8).map(t => {
        const deltaParts = [];
        if (t.rank_gain > 0) deltaParts.push(`순위 +${t.rank_gain}`);
        if (t.score_gain > 0) deltaParts.push(`점수 +${fmtNum(t.score_gain, 2)}`);
        return `
          <li>
            <div class="mini-list-main">
              <a href="#/team/${encodeURIComponent(t.team_key)}"><strong>${escapeHtml(t.display_name)}</strong></a>
              <div class="mini-list-sub">#${t.rank_prev} → #${t.rank_now} (${deltaParts.join(', ')}) · ${fmtNum(t.score_now, 2)}점</div>
            </div>
            ${watchButtonHtml(t.team_key, t.display_name, true)}
          </li>
        `;
      }).join('')}</ul>`
    : '<p class="muted small" style="margin:0;">비교 기간 내 순위·점수가 크게 오른 팀이 없습니다.</p>';

  const watchListHtml = !watchEnriched.length
    ? '<p class="muted small" style="margin:0;">아직 담은 관심 팀이 없습니다. 위 카드나 후보 표에서 <strong>관심 추가</strong>를 눌러 추적할 팀을 모아 두세요.</p>'
    : watchActive.length
      ? `<ul class="mini-list">${watchActive.slice(0, 8).map(w => `
          <li>
            <div class="mini-list-main">
              <a href="#/team/${encodeURIComponent(w.team_key)}"><strong>${escapeHtml(w.display_name)}</strong></a>
              <div class="mini-list-sub">최근 7일 신호 ${fmtInt(w.recent_7d)}건 · 최근 ${escapeHtml(w.last_seen || '-')} · ${w.score !== null ? `${fmtNum(w.score, 2)}점` : '-'}</div>
            </div>
            <a class="btn btn-sm" href="#/team/${encodeURIComponent(w.team_key)}">보기</a>
          </li>
        `).join('')}</ul>`
      : `<p class="muted small" style="margin:0;">관심 팀 ${fmtInt(watchEnriched.length)}팀 중 최근 7일 안에 새로 들어온 신호는 없습니다. <a href="#/watchlist">관심 목록 전체 보기</a></p>`;

  root.innerHTML = `
    ${bannerHtml}
    ${customW ? '<div class="notice">점수 검증 화면에서 바꾼 사용자 가중치가 상위 5팀 점수에 반영되어 있습니다. (신규·상승 비교는 기본 가중치 스냅샷 기준)</div>' : ''}
    <div class="block-head" style="border:none;margin-bottom:8px;padding:0;">
      <h2>지금 점수 상위 5팀</h2>
      <span class="block-meta">기준일 ${escapeHtml(appState.cfg.as_of)} · 첫 등장 ${appState.cfg.newcomer_years}년 이내</span>
    </div>
    ${top5Html}

    <div class="grid-3">
      <section class="block" style="margin-bottom:0;">
        <div class="block-head">
          <h3>이번 주 새로 후보에 들어온 팀</h3>
          <span class="block-meta">${fmtInt(diff.newEntrants.length)}팀</span>
        </div>
        ${newListHtml}
        <p class="muted small" style="margin:8px 0 0 0;">${escapeHtml(snapLabel)}</p>
      </section>

      <section class="block" style="margin-bottom:0;">
        <div class="block-head">
          <h3>점수·순위가 오른 팀</h3>
          <span class="block-meta">${fmtInt(diff.risers.length)}팀</span>
        </div>
        ${riserListHtml}
        <p class="muted small" style="margin:8px 0 0 0;">${escapeHtml(snapLabel)}</p>
      </section>

      <section class="block" style="margin-bottom:0;">
        <div class="block-head">
          <h3>최근 7일 새 신호가 들어온 관심 팀</h3>
          <span class="block-meta">${fmtInt(watchActive.length)} / ${fmtInt(watchEnriched.length)}팀</span>
        </div>
        ${watchListHtml}
      </section>
    </div>
  `;

  // Wire card link clicks gracefully (anchor hrefs already handle hash navigation,
  // ensure any programmatic navigation stays consistent)
  root.querySelectorAll('[data-open-team]').forEach(el => {
    el.addEventListener('click', () => navigateTo('team', el.dataset.openTeam));
  });
}
