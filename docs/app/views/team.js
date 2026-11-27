import { appState, navigateTo, setExportContext } from '../state.js';
import { getTeamExternalLinks, queryTeamDetail } from '../db.js';
import {
  avatarHtml, avatarSourceOf, escapeHtml, fmtInt, fmtNum, formatSignalDate,
  PROFILE_LABELS, renderActionBanner, renderScoreBar,
  SOURCE_LABELS, spotifyButtonHtml, spotifyUrlOf, summarizeWhyTeam,
  watchButtonHtml, wireAvatarFallbacks, wireSpotifyButtons,
} from '../ui.js';

/**
 * 듣기·보기는 스포티파이·유튜브 두 가지만 (사용자 결정 2026-11-27).
 * - 스포티파이: '▶ 듣기'를 누르면 이 자리에서 공식 임베드 플레이어(미리 듣기, 로그인 시 전곡)
 * - 유튜브: 공식 채널이 있으면 채널로, 없으면 아래 '최근 무대' 영상으로 이동
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

function renderVideosSection(videos, showAll) {
  if (!videos || !videos.length) return '';
  const visible = showAll ? videos : videos.slice(0, 3);
  const moreCount = videos.length - visible.length;

  return `
    <section class="block" id="teamVideosBlock">
      <div class="block-head">
        <h2>최근 무대</h2>
        <span class="block-meta">${fmtInt(videos.length)}개</span>
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
    </section>
  `;
}

export async function renderTeamView(root, teamKey) {
  if (!teamKey) {
    root.innerHTML = renderActionBanner({
      title: '팀 상세',
      lead: '선택된 팀이 없습니다.',
      todo: '위쪽 팀 검색 창에서 팀 이름을 입력하거나 후보 탐색에서 팀을 선택하세요.',
      buttonsHtml: '<a class="btn" href="#/candidates">후보 탐색으로</a>',
    });
    return;
  }

  const data = await queryTeamDetail(teamKey);
  const { profile, scored, timeline, outcomes, precedents, related, links, videos } = data;

  if (!profile && !scored && !timeline.length) {
    root.innerHTML = renderActionBanner({
      title: `팀을 찾을 수 없음: ${teamKey}`,
      lead: '현재 데이터에 해당 팀 키가 없습니다.',
      todo: '위쪽 팀 검색 창에서 정확한 팀 이름을 선택해 주세요.',
      buttonsHtml: '<a class="btn" href="#/candidates">후보 탐색으로</a>',
    });
    return;
  }

  const displayName = scored?.display_name || profile?.display_name || teamKey;
  const extLinks = getTeamExternalLinks(teamKey, displayName);
  const whyLines = summarizeWhyTeam(data);
  const snapNow = appState.snapshots.latest.get(teamKey);

  // Build concise 1-line summary (omit empty fields)
  const metaParts = [];
  if (profile?.primary_genre) metaParts.push(profile.primary_genre);
  if (profile?.agency) metaParts.push(`소속 ${profile.agency}`);
  if (profile?.first_seen) metaParts.push(`첫 등장 ${profile.first_seen}`);
  if (scored) {
    const rankTxt = snapNow ? ` (기본 순위 #${snapNow.rank})` : '';
    metaParts.push(`${fmtNum(scored.score, 2)}점${rankTxt}`);
  }

  // Merge outcomes + signals into single timeline
  const mergedTimeline = [];
  for (const o of outcomes) {
    const tierKo = o.tier === 'final' ? '최종' : '중간';
    mergedTimeline.push({
      sortDate: o.announced_date || '',
      dateDisp: o.announced_date || '-',
      branch: '정답',
      isOutcome: true,
      text: `${o.program_label || o.program} [${tierKo}]${o.counted ? '' : ' (집계 제외)'}`,
    });
  }
  for (const s of timeline) {
    const name = s.program_label || SOURCE_LABELS[s.program] || SOURCE_LABELS[s.source] || s.source || '';
    const detail = s.venue ? `${name} — ${s.venue}` : name;
    mergedTimeline.push({
      sortDate: s.signal_date || '',
      dateDisp: formatSignalDate(s.signal_date, s.branch),
      branch: s.branch || '',
      isOutcome: false,
      text: detail,
    });
  }
  mergedTimeline.sort((a, b) => (b.sortDate > a.sortDate ? 1 : b.sortDate < a.sortDate ? -1 : 0));

  const stageRelated = related.filter(r => r.relation === '같은 무대');
  const agencyRelated = related.filter(r => r.relation === '같은 소속사');
  const hasRelated = related.length > 0;

  let activeSubTab = 'why';
  let showAllVideos = false;
  let showAllPrec = false;
  let showAllTimeline = false;
  let showAllStageRel = false;

  // Non-empty profile facts only (never list '수집 전' rows)
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

  function renderSubPanel() {
    if (activeSubTab === 'why') {
      const scoreItems = scored ? [
        ['갈래 수 (' + fmtInt(scored.n_branch) + '개)', scored.pts_branch],
        ['선정 최고 단계 (' + fmtInt(scored.best_stage) + ')', scored.pts_stage],
        ['서로 다른 공연장 (' + fmtInt(scored.venues) + '곳)', scored.pts_venues],
        ['최근 6개월 활동 (' + fmtInt(scored.recent180) + '건)', scored.pts_recent],
        ['이미 상 받은 팀과 같은 무대', scored.pts_winner],
        ['큐레이션 매체 (' + fmtInt(scored.outlets) + '곳)', scored.pts_outlets],
        ['선정 팀과 같은 무대', scored.pts_peer],
        ['DMZ 출연', scored.pts_dmz],
        ['최근 1년 공연 (' + fmtInt(scored.gigs_1y) + '일)', scored.pts_gigs],
      ].filter(([, v]) => Number(v) > 0) : [];

      const visiblePrec = showAllPrec ? precedents : precedents.slice(0, 3);
      const morePrec = precedents.length - visiblePrec.length;

      return `
        <section class="block">
          <div class="block-head">
            <h2>요약</h2>
            <span class="block-meta">기준일 ${escapeHtml(appState.cfg.as_of)}</span>
          </div>
          <ol class="why-list">
            ${whyLines.map(line => `<li>${escapeHtml(line)}</li>`).join('')}
          </ol>
        </section>

        <div class="${profileFacts.length ? 'grid-2' : ''}">
          <section class="block" style="${profileFacts.length ? 'margin-bottom:0;' : ''}">
            <div class="block-head">
              <h3>점수 구성</h3>
              ${scored ? `<span class="block-meta">합계 ${fmtNum(scored.score, 2)}점</span>` : ''}
            </div>
            ${scored ? `
              <div style="margin-bottom:10px;">${renderScoreBar(scored, Math.max(10, Number(scored.score) || 1))}</div>
              <dl class="kv-list">
                ${scoreItems.map(([k, v]) => `<dt>${escapeHtml(k)}</dt><dd>+${fmtNum(v, 2)}</dd>`).join('')}
              </dl>
            ` : '<p class="muted small" style="margin:0;">현재 필터·기간 조건 안의 점수가 없습니다.</p>'}
          </section>

          ${profileFacts.length ? `
            <section class="block" style="margin-bottom:0;">
              <div class="block-head"><h3>아티스트 정보</h3></div>
              <dl class="kv-list">
                ${profileFacts.map(([k, v]) => `<dt>${escapeHtml(k)}</dt><dd>${escapeHtml(v)}</dd>`).join('')}
              </dl>
            </section>
          ` : ''}
        </div>

        <section class="block" style="margin-top:16px;">
          <div class="block-head">
            <h2>비슷한 길을 밟은 과거 수상 팀</h2>
            <span class="block-meta">${fmtInt(precedents.length)}팀</span>
          </div>
          ${visiblePrec.length ? `
            <div class="table-wrap">
              <table class="data-table">
                <thead>
                  <tr>
                    <th>과거 수상 팀</th>
                    <th>첫 정답</th>
                    <th class="nowrap">발표일</th>
                    <th>겹친 경로</th>
                    <th class="num nowrap">소요 (개월)</th>
                  </tr>
                </thead>
                <tbody>
                  ${visiblePrec.map(p => `
                    <tr>
                      <td><a href="#/team/${encodeURIComponent(p.past_team)}"><strong>${escapeHtml(p.display_name || p.past_team)}</strong></a></td>
                      <td>${escapeHtml(p.outcome_label || '-')}</td>
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
              <summary>ⓘ 선례 해석 주의</summary>
              <div class="info-fold-body">선례는 정답 전에 같은 선정·공연장·매체를 거쳤다는 참고 경로일 뿐이며, 수상을 예측하지 않습니다.</div>
            </details>
          ` : '<p class="muted small" style="margin:0;">겹치는 경로를 가진 과거 수상 팀 선례가 아직 없습니다.</p>'}
        </section>
      `;
    }

    if (activeSubTab === 'activity') {
      const visibleTl = showAllTimeline ? mergedTimeline : mergedTimeline.slice(0, 10);
      const moreTl = mergedTimeline.length - visibleTl.length;
      return `
        <section class="block">
          <div class="block-head">
            <h2>신호 · 정답 타임라인</h2>
            <span class="block-meta">전체 ${fmtInt(mergedTimeline.length)}건</span>
          </div>
          ${visibleTl.length ? `
            <ul class="timeline-list">
              ${visibleTl.map(m => `
                <li>
                  <span class="timeline-date">${escapeHtml(m.dateDisp)}</span>
                  <span class="timeline-branch ${m.isOutcome ? 'timeline-outcome' : ''}">${escapeHtml(m.branch)}</span>
                  <span>${escapeHtml(m.text)}</span>
                </li>
              `).join('')}
            </ul>
            ${moreTl > 0 ? `<div class="more-row" style="margin-top:8px;"><span>최근 ${fmtInt(visibleTl.length)} / ${fmtInt(mergedTimeline.length)}건</span><button type="button" class="btn btn-sm" id="btnMoreTimeline">${fmtInt(moreTl)}건 더 보기</button></div>` : ''}
          ` : '<p class="muted small" style="margin:0;">기록된 신호가 없습니다.</p>'}
        </section>

        ${extLinks.length ? `
          <section class="block">
            <div class="block-head">
              <h3>관련 기사 · 출처 링크</h3>
              <span class="block-meta">${fmtInt(extLinks.length)}건</span>
            </div>
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
          </section>
        ` : ''}
      `;
    }

    // activeSubTab === 'related'
    const visibleStage = showAllStageRel ? stageRelated : stageRelated.slice(0, 5);
    const moreStage = stageRelated.length - visibleStage.length;
    return `
      ${stageRelated.length ? `
        <section class="block">
          <div class="block-head">
            <h2>같은 무대에 함께 선 팀</h2>
            <span class="block-meta">${fmtInt(stageRelated.length)}팀</span>
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
                    <td class="muted">${escapeHtml(r.detail || '-')}</td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          </div>
          ${moreStage > 0 ? `<div class="more-row"><span>상위 ${fmtInt(visibleStage.length)} / ${fmtInt(stageRelated.length)}팀</span><button type="button" class="btn btn-sm" id="btnMoreStageRel">${fmtInt(moreStage)}팀 더 보기</button></div>` : ''}
        </section>
      ` : ''}

      ${agencyRelated.length ? `
        <section class="block">
          <div class="block-head">
            <h2>같은 소속사 팀</h2>
            <span class="block-meta">${escapeHtml(agencyRelated[0]?.detail || '')} · ${fmtInt(agencyRelated.length)}팀</span>
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
        </section>
      ` : ''}
    `;
  }

  // Register team timeline CSV with unified export dropdown
  setExportContext({
    csvLabel: `${displayName} 활동 기록 CSV 내려받기 (${fmtInt(mergedTimeline.length)}건)`,
    csvFilename: `crate_digger_team_${teamKey.replace(/[^a-zA-Z0-9가-힣_-]+/g, '_')}_${appState.dataEnd || 'export'}.csv`,
    csvHeaders: ['date', 'branch', 'detail'],
    csvRows: mergedTimeline.map(m => [m.dateDisp, m.branch, m.text]),
  });

  const backLabels = {
    today: '이번 주 브리핑',
    candidates: '후보 목록',
    venues: '공연장·씬',
    watchlist: '관심 목록',
    verify: '점수 신뢰도·검증',
    quality: '데이터 수집·품질',
  };
  const backRoute = appState.prevRoute && backLabels[appState.prevRoute] ? appState.prevRoute : 'today';
  const backLabel = backLabels[backRoute] || '이번 주 브리핑';

  const imgSrc = avatarSourceOf(teamKey);
  const spUrl = spotifyUrlOf(teamKey);
  const genre = scored?.primary_genre || profile?.primary_genre || '';
  const photoCreditHtml = imgSrc === 'spotify'
    ? (spUrl
        ? `<a class="avatar-credit" href="${escapeHtml(spUrl)}" target="_blank" rel="noopener noreferrer">사진 · Spotify ↗</a>`
        : '<span class="avatar-credit">사진 · Spotify</span>')
    : imgSrc === 'youtube'
      ? '<span class="avatar-credit">사진 · YouTube</span>'
      : '';

  function paint() {
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
            <h1 class="action-banner-title">${escapeHtml(displayName)}</h1>
            <p class="team-subline">${escapeHtml(metaParts.join(' · ') || '기록된 신호 ' + fmtInt(mergedTimeline.length) + '건')}</p>
          </div>
        </div>
        <div class="action-banner-btns">
          ${renderListenButtons(teamKey, displayName, links, videos.length > 0)}
          ${watchButtonHtml(teamKey, displayName, false)}
        </div>
      </div>
      <div class="player-slot" id="teamPlayerSlot" data-player-slot></div>

      ${renderVideosSection(videos, showAllVideos)}

      <div class="sub-tabs" role="tablist" aria-label="팀 상세 탭">
        <button type="button" class="sub-tab-btn ${activeSubTab === 'why' ? 'active' : ''}" role="tab" aria-selected="${activeSubTab === 'why'}" data-subtab="why">왜 후보인가</button>
        <button type="button" class="sub-tab-btn ${activeSubTab === 'activity' ? 'active' : ''}" role="tab" aria-selected="${activeSubTab === 'activity'}" data-subtab="activity">활동 기록 (${fmtInt(mergedTimeline.length)})</button>
        ${hasRelated ? `<button type="button" class="sub-tab-btn ${activeSubTab === 'related' ? 'active' : ''}" role="tab" aria-selected="${activeSubTab === 'related'}" data-subtab="related">관련 팀 (${fmtInt(related.length)})</button>` : ''}
      </div>

      <div id="teamSubPanel">${renderSubPanel()}</div>
    `;

    wireAvatarFallbacks(root);
    wireSpotifyButtons(root, root.querySelector('#teamPlayerSlot'));

    root.querySelector('#btnTeamBack')?.addEventListener('click', () => {
      navigateTo(backRoute, '');
    });

    root.querySelector('[data-scroll-videos]')?.addEventListener('click', (e) => {
      e.preventDefault();
      root.querySelector('#teamVideosBlock')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });

    // Wire inline lazy YouTube embed swap on click
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

    root.querySelector('#btnMoreVideos')?.addEventListener('click', () => { showAllVideos = true; paint(); });

    // Wire sub-tabs
    root.querySelectorAll('[data-subtab]').forEach(btn => {
      btn.addEventListener('click', () => {
        activeSubTab = btn.dataset.subtab;
        paint();
      });
    });

    // Wire show-more buttons inside sub-tabs
    root.querySelector('#btnMorePrec')?.addEventListener('click', () => { showAllPrec = true; paint(); });
    root.querySelector('#btnMoreTimeline')?.addEventListener('click', () => { showAllTimeline = true; paint(); });
    root.querySelector('#btnMoreStageRel')?.addEventListener('click', () => { showAllStageRel = true; paint(); });
  }

  paint();
}
