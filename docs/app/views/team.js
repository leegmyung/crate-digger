import {
  appState, getPreferredPlatform, setPreferredPlatform,
} from '../state.js';
import { getTeamExternalLinks, queryTeamDetail } from '../db.js';
import {
  escapeHtml, fmtInt, fmtNum, formatSignalDate,
  PROFILE_LABELS, renderActionBanner, renderScoreBar,
  SOURCE_LABELS, summarizeWhyTeam, watchButtonHtml,
} from '../ui.js';

const PLATFORMS = [
  { id: 'melon', label: '멜론', verb: '에서 듣기', searchUrl: q => `https://www.melon.com/search/total/index.htm?q=${encodeURIComponent(q)}` },
  { id: 'genie', label: '지니', verb: '에서 듣기', searchUrl: q => `https://www.genie.co.kr/search/searchMain?query=${encodeURIComponent(q)}` },
  { id: 'bugs', label: '벅스', verb: '에서 듣기', searchUrl: q => `https://music.bugs.co.kr/search/integrated?q=${encodeURIComponent(q)}` },
  { id: 'spotify', label: '스포티파이', verb: '에서 듣기', searchUrl: q => `https://open.spotify.com/search/${encodeURIComponent(q)}` },
  { id: 'youtube', label: '유튜브', verb: '에서 보기', searchUrl: q => `https://www.youtube.com/results?search_query=${encodeURIComponent(q)}` },
  { id: 'instagram', label: '인스타그램', verb: ' 보기', searchUrl: null }, // 링크 없으면 숨김
];

function buildPlatformEntries(displayName, linksMap) {
  const entries = [];
  for (const p of PLATFORMS) {
    const official = linksMap && linksMap.get(p.id);
    if (official && official.startsWith('https://')) {
      entries.push({ ...p, url: official, isOfficial: true });
    } else if (p.searchUrl) {
      entries.push({ ...p, url: p.searchUrl(displayName), isOfficial: false });
    }
  }
  return entries;
}

function renderPlatformDropdown(displayName, linksMap) {
  const entries = buildPlatformEntries(displayName, linksMap);
  if (!entries.length) return '';
  const prefId = getPreferredPlatform();
  // Prefer user's last chosen platform if available; fallback to first official or Melon
  let primary = entries.find(e => e.id === prefId);
  if (!primary) primary = entries.find(e => e.isOfficial) || entries[0];

  return `
    <div class="platform-menu-wrap" id="platformMenuWrap">
      <a class="btn btn-primary platform-main-btn" id="platformMainLink"
         href="${escapeHtml(primary.url)}" target="_blank" rel="noopener noreferrer"
         data-plat-id="${escapeHtml(primary.id)}">
        ${escapeHtml(primary.label)}${escapeHtml(primary.verb)}
      </a>
      <button type="button" class="btn btn-primary platform-caret-btn" id="platformCaretBtn"
              aria-haspopup="menu" aria-expanded="false" aria-label="다른 플랫폼 선택">▾</button>
      <div class="platform-drop" id="platformDrop" role="menu">
        ${entries.map(e => `
          <a class="platform-opt ${e.isOfficial ? '' : 'is-search'}" role="menuitem"
             href="${escapeHtml(e.url)}" target="_blank" rel="noopener noreferrer"
             data-plat-id="${escapeHtml(e.id)}" data-plat-label="${escapeHtml(e.label + e.verb)}">
            <span>${escapeHtml(e.label)}</span>
            <span class="platform-opt-tag">${e.isOfficial ? '공식 페이지' : '검색으로 찾기'}</span>
          </a>
        `).join('')}
      </div>
    </div>
  `;
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
                    <td><a href="#/team/${encodeURIComponent(r.related_team)}"><strong>${escapeHtml(r.display_name || r.related_team)}</strong></a></td>
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
                <div class="mini-list-main">
                  <a href="#/team/${encodeURIComponent(r.related_team)}"><strong>${escapeHtml(r.display_name || r.related_team)}</strong></a>
                </div>
                <span class="small muted">${escapeHtml(r.detail || '')}</span>
              </li>
            `).join('')}
          </ul>
        </section>
      ` : ''}
    `;
  }

  function paint() {
    root.innerHTML = `
      <div class="action-banner">
        <div>
          <h1 class="action-banner-title">${escapeHtml(displayName)}</h1>
          <p class="team-subline">${escapeHtml(metaParts.join(' · ') || '기록된 신호 ' + fmtInt(mergedTimeline.length) + '건')}</p>
        </div>
        <div class="action-banner-btns">
          ${renderPlatformDropdown(displayName, links)}
          ${watchButtonHtml(teamKey, displayName, false)}
        </div>
      </div>

      ${renderVideosSection(videos, showAllVideos)}

      <div class="sub-tabs" role="tablist" aria-label="팀 상세 탭">
        <button type="button" class="sub-tab-btn ${activeSubTab === 'why' ? 'active' : ''}" role="tab" aria-selected="${activeSubTab === 'why'}" data-subtab="why">왜 후보인가</button>
        <button type="button" class="sub-tab-btn ${activeSubTab === 'activity' ? 'active' : ''}" role="tab" aria-selected="${activeSubTab === 'activity'}" data-subtab="activity">활동 기록 (${fmtInt(mergedTimeline.length)})</button>
        ${hasRelated ? `<button type="button" class="sub-tab-btn ${activeSubTab === 'related' ? 'active' : ''}" role="tab" aria-selected="${activeSubTab === 'related'}" data-subtab="related">관련 팀 (${fmtInt(related.length)})</button>` : ''}
      </div>

      <div id="teamSubPanel">${renderSubPanel()}</div>
    `;

    // Wire platform hover/tap + keyboard dropdown
    const menuWrap = root.querySelector('#platformMenuWrap');
    const caretBtn = root.querySelector('#platformCaretBtn');
    const mainLink = root.querySelector('#platformMainLink');
    const drop = root.querySelector('#platformDrop');

    if (menuWrap && caretBtn && drop) {
      const setOpen = (on) => {
        menuWrap.classList.toggle('open', on);
        caretBtn.setAttribute('aria-expanded', on ? 'true' : 'false');
      };
      caretBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        setOpen(!menuWrap.classList.contains('open'));
      });
      caretBtn.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') { setOpen(false); }
        else if (e.key === 'ArrowDown' || e.key === 'Enter') {
          setOpen(true);
          drop.querySelector('.platform-opt')?.focus();
        }
      });
      drop.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
          setOpen(false);
          caretBtn.focus();
        }
      });
      drop.querySelectorAll('.platform-opt').forEach(opt => {
        opt.addEventListener('click', () => {
          const pid = opt.dataset.platId;
          setPreferredPlatform(pid);
          if (mainLink) {
            mainLink.href = opt.href;
            mainLink.dataset.platId = pid;
            mainLink.textContent = opt.dataset.platLabel;
          }
          setOpen(false);
        });
      });
      document.addEventListener('click', (e) => {
        if (!menuWrap.contains(e.target)) setOpen(false);
      }, { once: false });
    }

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
