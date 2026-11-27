import {
  ALL_BRANCHES, appState, getActiveFilterSummary, navigateTo,
  setExportContext, syncHash,
} from '../state.js';
import {
  buildNextGigByTeam, getSnapshotDiff, queryCandidates, queryDebutCandidates,
  queryDebutScorecard, queryTopPrecedent, queryUpcomingGigs,
} from '../db.js';
import {
  avatarHtml, escapeHtml, fmtInt, fmtNum, formatNextGigText, formatSourceKey,
  gradeBadgeHtml, plainWhyLine, renderActionBanner, renderEmptyState, scorePartsLine,
  spotifyButtonHtml, TERMS, watchButtonHtml, wireAvatarFallbacks, wireSpotifyButtons,
  youtubeQuickInfo,
} from '../ui.js';

const DEBUT_MIN_SAMPLE = 5;
const DEBUT_DOC_URL = 'https://github.com/leegmyung/crate-digger/blob/main/docs/debut_cohort.md';
const VALID_SORT_COLS = new Set(['score', 'display_name', 'next_gig_sort']);
const VALID_DEBUT_SORT_COLS = new Set(['score', 'first_release', 'display_name']);

function sortRows(rows, col, dir) {
  const safeCol = VALID_SORT_COLS.has(col) ? col : 'score';
  const mult = dir === 'asc' ? 1 : -1;
  return [...rows].sort((a, b) => {
    if (safeCol === 'next_gig_sort') {
      const da = a.next_gig?.signal_date || '9999-12-31';
      const db = b.next_gig?.signal_date || '9999-12-31';
      if (da !== db) return da.localeCompare(db) * mult;
      return (Number(b.score) || 0) - (Number(a.score) || 0);
    }
    const va = a[safeCol];
    const vb = b[safeCol];
    if (va === vb) return 0;
    if (va === null || va === undefined) return 1;
    if (vb === null || vb === undefined) return -1;
    if (typeof va === 'number' && typeof vb === 'number') return (va - vb) * mult;
    return String(va).localeCompare(String(vb), 'ko') * mult;
  });
}

function renderRowListenControl(r) {
  const sp = spotifyButtonHtml(r.team_key, true, {
    iconOnly: true,
    mode: 'table-row',
    teamName: r.display_name || r.team_key,
  });
  if (sp) return sp;

  const yt = youtubeQuickInfo(r.team_key);
  if (yt && yt.kind === 'channel') {
    return `<a class="btn btn-icon btn-yt-mini" href="${escapeHtml(yt.url)}" target="_blank" rel="noopener noreferrer" title="유튜브 공식 채널" aria-label="${escapeHtml(r.display_name || r.team_key)} 유튜브 공식 채널">YT</a>`;
  }
  if (yt && yt.kind === 'video') {
    return `<a class="btn btn-icon btn-yt-mini" href="#/team/${encodeURIComponent(r.team_key)}" title="최근 무대 영상 ${yt.count}개" aria-label="${escapeHtml(r.display_name || r.team_key)} 무대 영상">영상</a>`;
  }
  return '';
}

function renderCandTabsHtml(activeTab) {
  return `
    <div class="sub-tabs cand-sub-tabs" role="tablist" aria-label="후보 목록 보기 전환">
      <button type="button" class="sub-tab-btn ${activeTab === 'all' ? 'active' : ''}" role="tab" aria-selected="${activeTab === 'all' ? 'true' : 'false'}" data-cand-tab="all">전체 후보</button>
      <button type="button" class="sub-tab-btn ${activeTab === 'debut' ? 'active' : ''}" role="tab" aria-selected="${activeTab === 'debut' ? 'true' : 'false'}" data-cand-tab="debut">갓 데뷔</button>
    </div>
  `;
}

function wireCandTabs(root) {
  root.querySelectorAll('[data-cand-tab]').forEach(btn => {
    btn.addEventListener('click', () => {
      const next = btn.dataset.candTab;
      if (next === appState.candTab) return;
      appState.candTab = next;
      syncHash(true);
      window.dispatchEvent(new CustomEvent('app:route'));
    });
  });
}

function sortDebutRows(rows, col, dir) {
  const safeCol = VALID_DEBUT_SORT_COLS.has(col) ? col : 'score';
  const mult = dir === 'asc' ? 1 : -1;
  return [...rows].sort((a, b) => {
    if (safeCol === 'score') {
      const va = a.score !== null && a.score !== undefined ? Number(a.score) : -1;
      const vb = b.score !== null && b.score !== undefined ? Number(b.score) : -1;
      if (va !== vb) return (va - vb) * mult;
      return String(b.first_release || '').localeCompare(String(a.first_release || ''));
    }
    if (safeCol === 'first_release') {
      const cmp = String(a.first_release || '').localeCompare(String(b.first_release || '')) * mult;
      if (cmp !== 0) return cmp;
      return ((Number(b.score) || 0) - (Number(a.score) || 0));
    }
    return String(a.display_name || '').localeCompare(String(b.display_name || ''), 'ko') * mult;
  });
}

function renderDebutMentionChip(m, debutScorecard) {
  const info = formatSourceKey(m.src);
  const sc = debutScorecard?.bySrc?.get(m.src) || null;
  const days = m.days_to_mention !== null && m.days_to_mention !== undefined ? Number(m.days_to_mention) : null;
  const daysTxt = days !== null ? `+${fmtInt(days)}일` : '';

  let relHtml = '<span class="debut-mention-rel is-thin">표본 부족</span>';
  let tipParts = [
    `${info.label}${info.branch ? ` (${info.branch})` : ''}`,
    m.first_mention_date ? `첫 언급 ${m.first_mention_date}${daysTxt ? ` (${daysTxt})` : ''}` : '',
    m.mention_cnt > 1 ? `총 ${fmtInt(m.mention_cnt)}회` : '',
  ].filter(Boolean);

  if (sc) {
    const teams = Number(sc.teams) || 0;
    const hits = Number(sc.hits) || 0;
    const rate = sc.rate !== null && sc.rate !== undefined ? Number(sc.rate) : null;
    const lift = sc.lift !== null && sc.lift !== undefined ? Number(sc.lift) : null;
    const thin = teams < DEBUT_MIN_SAMPLE;
    const liftCls = !thin && lift !== null && lift >= 1.5 ? ' is-strong' : '';
    const metricTxt = `${rate !== null ? fmtNum(rate, 1) + '%' : '-'}${lift !== null ? ` · ${fmtNum(lift, 1)}배` : ''}`;
    relHtml = `<span class="debut-mention-rel${thin ? ' is-thin' : liftCls}">${escapeHtml(metricTxt)}${thin ? ' (표본 부족)' : ''}</span>`;
    const medTxt = sc.median_days !== null && sc.median_days !== undefined ? `, 중앙 ${fmtNum(sc.median_days, 0)}일` : '';
    tipParts.push(`데뷔 코호트 ${fmtInt(hits)}/${fmtInt(teams)}팀 (${metricTxt}${medTxt})${thin ? ' — 표본 부족' : ''}`);
  } else {
    tipParts.push('데뷔 코호트 기록 없음 (표본 부족)');
  }

  return `
    <span class="debut-mention-chip" title="${escapeHtml(tipParts.join(' · '))}">
      <span class="debut-mention-src">${escapeHtml(info.label)}</span>
      ${daysTxt ? `<span class="debut-mention-days mono">${escapeHtml(daysTxt)}</span>` : ''}
      ${relHtml}
    </span>
  `;
}

async function renderDebutCandidatesView(root) {
  const c = appState.cfg;
  const asOf = c.as_of || appState.dataEnd || '2026-11-27';
  const [debutData, debutScorecard] = await Promise.all([
    queryDebutCandidates({ as_of: asOf }),
    queryDebutScorecard({ horizonMonths: c.horizon_months || 24 }),
  ]);

  let debutSort = { col: 'score', dir: 'desc' };

  const bannerHtml = renderActionBanner({
    title: '후보 목록',
    lead: debutData.total
      ? `기준일(${escapeHtml(asOf)}) 전 12개월 내 첫 발매·사전 신호 없는 백지 신인 <strong>${fmtInt(debutData.total)}팀</strong>(언급 있음 ${fmtInt(debutData.mentioned.length)}팀 · 아직 언급 없음 ${fmtInt(debutData.unmentioned.length)}팀)입니다.`
      : `기준일(${escapeHtml(asOf)}) 전 12개월 내 조건에 맞는 백지 신인이 없습니다.`,
  });

  const genreOpts = ['<option value="">전체 장르</option>']
    .concat(appState.validGenres.map(g => `<option value="${escapeHtml(g)}" ${c.genre === g ? 'selected' : ''}>${escapeHtml(g)}</option>`))
    .join('');

  const cohortPillsHtml = debutScorecard.sourceRows.length
    ? debutScorecard.sourceRows.map(r => {
        const info = formatSourceKey(r.src);
        const teams = Number(r.teams) || 0;
        const hits = Number(r.hits) || 0;
        const thin = teams < DEBUT_MIN_SAMPLE;
        const rateTxt = r.rate !== null && r.rate !== undefined ? `${fmtNum(r.rate, 1)}%` : '-';
        const liftTxt = r.lift !== null && r.lift !== undefined ? `${fmtNum(r.lift, 1)}배` : '-';
        const medTxt = r.median_days !== null && r.median_days !== undefined ? ` · 중앙 ${fmtNum(r.median_days, 0)}일` : '';
        const tip = `${info.label}: 코호트 ${fmtInt(hits)}/${fmtInt(teams)}팀 (적중률 ${rateTxt}, 배수 ${liftTxt}${medTxt})`;
        return `<span class="debut-cohort-pill${thin ? ' is-thin' : ''}" title="${escapeHtml(tip)}"><strong>${escapeHtml(info.label)}</strong> <span class="mono">${escapeHtml(rateTxt)} · ${escapeHtml(liftTxt)}</span>${thin ? ' <span class="small">(표본 부족)</span>' : ''}</span>`;
      }).join('')
    : '<span class="muted small">데뷔 코호트 출처 데이터 없음</span>';

  const cohortMetaHtml = debutScorecard.cohortTeams > 0
    ? `데뷔 코호트 신뢰도 (${fmtInt(debutScorecard.mentionMonths)}개월 창 · ${fmtInt(debutScorecard.cohortTeams)}팀, 기준율 ${fmtNum(debutScorecard.baseRate, 1)}%):`
    : '데뷔 코호트 신뢰도:';

  const unm = debutScorecard.unmentioned;
  const unmOpportunityHtml = unm && debutScorecard.cohortTeams > 0
    ? `데뷔 코호트 검증 기준 첫 발매 뒤 ${fmtInt(debutScorecard.mentionMonths)}개월 안에 어느 출처에도 안 나온 백지 신인이 <strong>${fmtInt(debutScorecard.unmentionedPct)}%</strong>(${fmtInt(unm.teams)}/${fmtInt(debutScorecard.cohortTeams)}팀, 그중 ${escapeHtml(TERMS.outcome)} ${fmtInt(unm.hits)}팀)입니다 — 아직 언급이 없는 팀이 가장 큰 발굴 기회입니다.`
    : '아직 어느 출처에도 언급되지 않은 백지 신인은 선행 발굴 후보로 따로 모아 둡니다.';

  root.innerHTML = `
    ${bannerHtml}
    ${renderCandTabsHtml('debut')}

    <section class="inline-filter-bar" aria-label="갓 데뷔 필터">
      <div class="inline-filter-row">
        <input type="search" id="debutFilterInput" class="input cand-search-input" placeholder="팀 이름·장르·언급 출처 검색..." aria-label="갓 데뷔 표 안에서 검색">
        <select id="debutGenreSel" class="select" aria-label="장르 필터">${genreOpts}</select>
        <span class="small muted inline-filter-count" id="debutCountText"></span>
      </div>
      <details class="inline-more-filters">
        <summary>세부 기준 (${c.exclude_famous ? '유명 팀 제외' : '유명 팀 포함'} · ${c.only_no_outcome ? `${TERMS.priorOutcome} 제외` : `${TERMS.priorOutcome} 포함`})</summary>
        <div class="inline-more-body">
          <div class="inline-more-controls">
            <label class="f-check small">
              <input type="checkbox" id="debutExcludeFamous" ${c.exclude_famous ? 'checked' : ''}>
              <span>유명 팀 제외</span>
            </label>
            <label class="f-check small">
              <input type="checkbox" id="debutOnlyNoOutcome" ${c.only_no_outcome ? 'checked' : ''}>
              <span>${escapeHtml(TERMS.priorOutcome)} 팀 제외</span>
            </label>
          </div>
          <p class="small muted" style="margin:8px 0 0 0;">
            기준일(${escapeHtml(asOf)}) 전 12개월 안에 첫 발매가 있고 첫 발매 이전 신호가 0건인 팀만 모았습니다.
          </p>
        </div>
      </details>
    </section>

    <section class="debut-cohort-strip" id="debutCohortStrip" aria-label="데뷔 코호트 신뢰도 기준">
      <div class="debut-cohort-row">
        <span class="debut-cohort-label">${cohortMetaHtml}</span>
        <div class="debut-cohort-pills">${cohortPillsHtml}</div>
        <a class="debut-doc-link" href="${DEBUT_DOC_URL}" target="_blank" rel="noopener noreferrer">분석 문서 ↗</a>
      </div>
      <p class="debut-limit-note">한계: 첫 발매일은 멜론·스포티파이 프로필이 있는 팀에만 있어 전체 백지 신인의 일부만 보입니다.</p>
    </section>

    <div class="block" style="padding:0;overflow:hidden;">
      <div class="table-wrap">
        <table class="data-table debut-table" id="debutTable">
          <thead>
            <tr>
              <th class="num">#</th>
              <th class="sortable" data-debut-sort="display_name">팀</th>
              <th class="nowrap sortable" data-debut-sort="first_release">첫 발매일</th>
              <th>첫 발매 뒤 언급 출처 · 데뷔 신뢰도</th>
              <th class="num sortable" data-debut-sort="score">점수</th>
              <th class="nowrap">듣기</th>
              <th class="nowrap">관심</th>
            </tr>
          </thead>
          <tbody id="debutTbody"></tbody>
        </table>
      </div>
    </div>

    <details class="info-fold debut-unmentioned-fold" id="debutUnmentionedFold">
      <summary id="debutUnmSummary">아직 언급 없음 (${fmtInt(debutData.unmentioned.length)}팀)</summary>
      <div class="info-fold-body">
        <p class="debut-unm-note">${unmOpportunityHtml}</p>
        <div id="debutUnmBody"></div>
      </div>
    </details>

    <p class="photo-credit" id="debutPhotoCredit" hidden>아티스트 사진 출처: Spotify</p>
  `;

  wireCandTabs(root);

  function paintDebut() {
    const q = (root.querySelector('#debutFilterInput')?.value || '').trim().toLowerCase();
    const matchQuery = (t) => {
      if (!q) return true;
      if (String(t.display_name || '').toLowerCase().includes(q)) return true;
      if (String(t.team_key || '').toLowerCase().includes(q)) return true;
      if (String(t.primary_genre || '').toLowerCase().includes(q)) return true;
      if (String(t.first_release || '').toLowerCase().includes(q)) return true;
      return t.mentions.some(m => {
        const info = formatSourceKey(m.src);
        return info.label.toLowerCase().includes(q) || m.src.toLowerCase().includes(q);
      });
    };

    const filteredMentioned = sortDebutRows(debutData.mentioned.filter(matchQuery), debutSort.col, debutSort.dir);
    const filteredUnmentioned = debutData.unmentioned.filter(matchQuery);

    root.querySelector('#debutCountText').textContent = `언급 있음 ${fmtInt(filteredMentioned.length)}팀 · 미언급 ${fmtInt(filteredUnmentioned.length)}팀`;
    const unmSumEl = root.querySelector('#debutUnmSummary');
    if (unmSumEl) unmSumEl.textContent = `아직 언급 없음 (${fmtInt(filteredUnmentioned.length)}팀)`;

    root.querySelectorAll('th[data-debut-sort]').forEach(th => {
      const col = th.dataset.debutSort;
      const baseLabel = th.dataset.label || th.textContent.replace(/ [▲▼]$/, '');
      th.dataset.label = baseLabel;
      th.textContent = col === debutSort.col
        ? `${baseLabel} ${debutSort.dir === 'asc' ? '▲' : '▼'}`
        : baseLabel;
    });

    setExportContext({
      csvLabel: `갓 데뷔 백지 신인 CSV 내려받기 (${fmtInt(filteredMentioned.length + filteredUnmentioned.length)}팀)`,
      csvFilename: `crate_digger_debut_${asOf}.csv`,
      csvHeaders: ['team_key', 'display_name', 'genre', 'first_release', 'score', 'mentions'],
      csvRows: [...filteredMentioned, ...filteredUnmentioned].map(r => [
        r.team_key,
        r.display_name,
        r.primary_genre || '',
        r.first_release || '',
        r.score ?? '',
        r.mentions.map(m => `${formatSourceKey(m.src).label}(+${m.days_to_mention ?? '?'}일)`).join(' / '),
      ]),
    });

    const tbody = root.querySelector('#debutTbody');
    if (!filteredMentioned.length) {
      tbody.innerHTML = `<tr><td colspan="7" style="padding:0;border:none;">${renderEmptyState({
        title: '조건에 맞는 첫 발매 뒤 언급 팀이 없습니다',
        message: `검색어 또는 장르·${TERMS.priorOutcome} 제외 조건을 완화해 보세요.`,
        showReset: false,
      })}</td></tr>`;
    } else {
      tbody.innerHTML = filteredMentioned.map((r, idx) => {
        const subParts = [];
        if (r.primary_genre) subParts.push(escapeHtml(r.primary_genre));
        if (r.had_outcome) subParts.push(escapeHtml(TERMS.priorOutcome));
        const mentionsHtml = `<div class="debut-mention-list">${r.mentions.map(m => renderDebutMentionChip(m, debutScorecard)).join('')}</div>`;
        return `
          <tr class="clickable" tabindex="0" data-team-key="${escapeHtml(r.team_key)}">
            <td class="num muted">${idx + 1}</td>
            <td>
              <div class="row-team-cell">
                ${avatarHtml(r.team_key, r.display_name, 28, { shape: 'circle', genre: r.primary_genre })}
                <div class="row-team-text">
                  <div class="row-team-name">
                    <span class="cand-mobile-rank">#${idx + 1}</span>
                    <strong>${escapeHtml(r.display_name)}</strong>
                  </div>
                  ${subParts.length ? `<div class="muted small">${subParts.join(' · ')}</div>` : ''}
                  <div class="debut-mobile-meta">
                    <span class="mono muted small">첫 발매 ${escapeHtml(r.first_release || '-')}</span>
                    ${mentionsHtml}
                  </div>
                </div>
              </div>
            </td>
            <td class="nowrap mono muted debut-date-col">${escapeHtml(r.first_release || '-')}</td>
            <td class="debut-mentions-col">${mentionsHtml}</td>
            <td class="num"><strong>${r.score !== null ? fmtNum(r.score, 2) : '—'}</strong></td>
            <td class="nowrap cand-listen-col">${renderRowListenControl(r)}</td>
            <td class="nowrap">${watchButtonHtml(r.team_key, r.display_name, true, true)}</td>
          </tr>
        `;
      }).join('');
      wireAvatarFallbacks(tbody);
      wireSpotifyButtons(tbody);
    }

    const unmBody = root.querySelector('#debutUnmBody');
    if (filteredUnmentioned.length) {
      unmBody.innerHTML = `
        <ul class="debut-unmentioned-list">
          ${filteredUnmentioned.map(r => `
            <li>
              <a class="debut-unm-team" href="#/team/${encodeURIComponent(r.team_key)}">
                ${avatarHtml(r.team_key, r.display_name, 24, { shape: 'circle', genre: r.primary_genre })}
                <strong>${escapeHtml(r.display_name)}</strong>
                ${r.primary_genre ? `<span class="small muted">${escapeHtml(r.primary_genre)}</span>` : ''}
              </a>
              <span class="debut-unm-right">
                <span class="mono small muted">첫 발매 ${escapeHtml(r.first_release || '-')}</span>
                ${watchButtonHtml(r.team_key, r.display_name, true, true)}
              </span>
            </li>
          `).join('')}
        </ul>
      `;
      wireAvatarFallbacks(unmBody);
    } else {
      unmBody.innerHTML = `<p class="small muted" style="margin:6px 0 0 0;">현재 기준일(${escapeHtml(asOf)}) 프로필 보유 백지 신인 중 첫 발매 뒤 언급이 0건인 팀은 없습니다.</p>`;
    }

    const hasAnyImg = [...filteredMentioned, ...filteredUnmentioned].some(r => appState.imagesByTeam.has(r.team_key));
    root.querySelector('#debutPhotoCredit').hidden = !hasAnyImg;
  }

  paintDebut();

  root.querySelector('#debutFilterInput')?.addEventListener('input', () => paintDebut());

  const triggerRecompute = () => {
    syncHash(true);
    window.dispatchEvent(new CustomEvent('app:recompute'));
  };
  root.querySelector('#debutGenreSel')?.addEventListener('change', (e) => {
    appState.cfg.genre = e.target.value || '';
    triggerRecompute();
  });
  root.querySelector('#debutExcludeFamous')?.addEventListener('change', (e) => {
    appState.cfg.exclude_famous = e.target.checked;
    triggerRecompute();
  });
  root.querySelector('#debutOnlyNoOutcome')?.addEventListener('change', (e) => {
    appState.cfg.only_no_outcome = e.target.checked;
    triggerRecompute();
  });

  root.querySelectorAll('th[data-debut-sort]').forEach(th => {
    th.setAttribute('tabindex', '0');
    const onSort = () => {
      const col = th.dataset.debutSort;
      if (debutSort.col === col) {
        debutSort.dir = debutSort.dir === 'desc' ? 'asc' : 'desc';
      } else {
        debutSort.col = col;
        debutSort.dir = col === 'display_name' ? 'asc' : 'desc';
      }
      paintDebut();
    };
    th.addEventListener('click', onSort);
    th.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        onSort();
      }
    });
  });

  const tbodyEl = root.querySelector('#debutTbody');
  tbodyEl?.addEventListener('click', (e) => {
    if (e.target.closest('button') || e.target.closest('a')) return;
    const tr = e.target.closest('tr.clickable');
    if (tr && tr.dataset.teamKey) navigateTo('team', tr.dataset.teamKey);
  });
  tbodyEl?.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    if (e.target.closest('button') || e.target.closest('a')) return;
    const tr = e.target.closest('tr.clickable');
    if (tr && tr.dataset.teamKey) {
      e.preventDefault();
      navigateTo('team', tr.dataset.teamKey);
    }
  });
}

export async function renderCandidatesView(root) {
  if (appState.candTab === 'debut') {
    await renderDebutCandidatesView(root);
    return;
  }

  const asOf = appState.cfg.as_of || appState.dataEnd || '2026-11-27';
  const [rawRows, upcomingRaw] = await Promise.all([
    queryCandidates(),
    queryUpcomingGigs({ asOf }),
  ]);

  const c = appState.cfg;
  const nextGigByTeam = buildNextGigByTeam(upcomingRaw);
  const diff = getSnapshotDiff(rawRows);
  const newSet = new Set(diff.newEntrants.map(t => t.team_key));
  const riserMap = new Map(diff.risers.map(t => [t.team_key, t]));

  const rows = rawRows.map(r => {
    const ng = nextGigByTeam.get(r.team_key) || null;
    const riser = riserMap.get(r.team_key) || null;
    return {
      ...r,
      why_line: plainWhyLine(r),
      next_gig: ng,
      next_gig_text: ng ? formatNextGigText(ng) : '',
      is_new: newSet.has(r.team_key),
      riser,
    };
  });

  if (!VALID_SORT_COLS.has(appState.candSort.col)) {
    appState.candSort.col = 'score';
    appState.candSort.dir = 'desc';
  }

  const newCount = rows.filter(r => r.is_new).length;
  const riserCount = rows.filter(r => Boolean(r.riser)).length;
  const upcomingCount = rows.filter(r => Boolean(r.next_gig)).length;
  const filterSummary = getActiveFilterSummary(c);

  const rowByKey = new Map(rows.map(r => [r.team_key, r]));
  let moveFilter = ''; // '' | 'new' | 'riser' | 'upcoming'
  let visibleCount = 20;
  let expandedTeamKey = null;

  const topName = rows[0] ? `${rows[0].display_name} (${fmtNum(rows[0].score, 2)}점)` : '없음';
  const bannerHtml = renderActionBanner({
    title: '후보 목록',
    lead: rows.length
      ? `신인 후보 상위 <strong>${fmtInt(rows.length)}팀</strong> 중 1위는 <strong>${escapeHtml(topName)}</strong>이며, 예정 공연이 잡힌 팀은 <strong>${fmtInt(upcomingCount)}팀</strong>입니다.`
      : '현재 조건에 맞는 신인 후보가 없습니다.',
  });

  const genreOpts = ['<option value="">전체 장르</option>']
    .concat(appState.validGenres.map(g => `<option value="${escapeHtml(g)}" ${c.genre === g ? 'selected' : ''}>${escapeHtml(g)}</option>`))
    .join('');

  const branchChips = ALL_BRANCHES.map(b => {
    const active = c.branches.includes(b);
    return `<button type="button" class="chip-btn ${active ? 'active' : ''}" data-branch-chip="${escapeHtml(b)}" aria-pressed="${active ? 'true' : 'false'}">${escapeHtml(b)}</button>`;
  }).join('');

  root.innerHTML = `
    ${bannerHtml}
    ${renderCandTabsHtml('all')}

    <section class="inline-filter-bar" aria-label="후보 목록 필터">
      <div class="inline-filter-row">
        <input type="search" id="candFilterInput" class="input cand-search-input" placeholder="팀 이름·장르·이유 검색..." aria-label="표 안에서 팀 검색">

        <select id="candGenreSel" class="select" aria-label="장르 필터">${genreOpts}</select>

        <select id="candPeriodSel" class="select" aria-label="최근 활동 기간">
          <option value="0" ${Number(c.period_days) === 0 ? 'selected' : ''}>전체 기간 (3년)</option>
          <option value="30" ${Number(c.period_days) === 30 ? 'selected' : ''}>최근 30일</option>
          <option value="90" ${Number(c.period_days) === 90 ? 'selected' : ''}>최근 90일</option>
          <option value="180" ${Number(c.period_days) === 180 ? 'selected' : ''}>최근 180일</option>
          <option value="365" ${Number(c.period_days) === 365 ? 'selected' : ''}>최근 365일</option>
        </select>

        <div class="chip-group" role="group" aria-label="신호 갈래 선택">${branchChips}</div>

        <div class="chip-group chip-group-move" role="group" aria-label="이번 주 변동 필터">
          <button type="button" class="chip-btn" data-move-chip="new" aria-pressed="false">새로 들어옴${newCount ? ` ${fmtInt(newCount)}` : ''}</button>
          <button type="button" class="chip-btn" data-move-chip="riser" aria-pressed="false">상승${riserCount ? ` ${fmtInt(riserCount)}` : ''}</button>
          <button type="button" class="chip-btn" data-move-chip="upcoming" aria-pressed="false">예정 공연${upcomingCount ? ` ${fmtInt(upcomingCount)}` : ''}</button>
        </div>

        ${filterSummary.count > 0 ? '<button type="button" class="btn btn-sm" data-action="reset-filters">초기화</button>' : ''}

        <span class="small muted inline-filter-count" id="candCountText"></span>
      </div>

      <details class="inline-more-filters">
        <summary>세부 기준 · 안내 (${c.newcomer_years}년 이내 · ${c.exclude_famous ? '유명 팀 제외' : '유명 팀 포함'} · ${c.only_no_outcome ? `${TERMS.priorOutcome} 제외` : `${TERMS.priorOutcome} 포함`} · 상위 ${c.limit}팀)</summary>
        <div class="inline-more-body">
          <div class="inline-more-controls">
            <label class="f-item-inline small">
              <span>신인 기준(년)</span>
              <input type="number" id="candNewcomerInp" class="input input-num" min="1" max="15" value="${c.newcomer_years}">
            </label>
            <label class="f-check small">
              <input type="checkbox" id="candExcludeFamous" ${c.exclude_famous ? 'checked' : ''}>
              <span>유명 팀 제외</span>
            </label>
            <label class="f-check small">
              <input type="checkbox" id="candOnlyNoOutcome" ${c.only_no_outcome ? 'checked' : ''}>
              <span>${escapeHtml(TERMS.priorOutcome)} 팀 제외</span>
            </label>
            <label class="f-item-inline small">
              <span>조회 상한</span>
              <select id="candLimitSel" class="select" aria-label="조회 상한">
                <option value="50" ${c.limit === 50 ? 'selected' : ''}>50팀</option>
                <option value="100" ${c.limit === 100 ? 'selected' : ''}>100팀</option>
                <option value="200" ${c.limit === 200 ? 'selected' : ''}>200팀</option>
              </select>
            </label>
          </div>
          <p class="small muted" style="margin:8px 0 0 0;">
            '신인 추정'은 우리 데이터 첫 등장 후 <strong>${c.newcomer_years}년</strong> 이내 기준입니다. 팀을 누르면 상세 점수 근거와 무대 영상을 볼 수 있습니다.
          </p>
        </div>
      </details>
    </section>

    <div class="block" style="padding:0;overflow:hidden;">
      <div class="table-wrap">
        <table class="data-table cand-table" id="candTable">
          <thead>
            <tr>
              <th class="num">#</th>
              <th class="sortable" data-sort="display_name">팀</th>
              <th>주목 이유</th>
              <th class="nowrap sortable" data-sort="next_gig_sort">다음 공연</th>
              <th class="num sortable" data-sort="score">점수</th>
              <th class="nowrap">듣기</th>
              <th class="nowrap">관심</th>
            </tr>
          </thead>
          <tbody id="candTbody"></tbody>
        </table>
      </div>
      <div class="more-row" id="candMoreRow" hidden></div>
    </div>
    <p class="photo-credit" id="candPhotoCredit" hidden>아티스트 사진 출처: Spotify</p>
  `;

  function paintTable() {
    const q = (root.querySelector('#candFilterInput')?.value || '').trim().toLowerCase();
    let list = rows;
    if (moveFilter === 'new') list = list.filter(r => r.is_new);
    else if (moveFilter === 'riser') list = list.filter(r => Boolean(r.riser));
    else if (moveFilter === 'upcoming') list = list.filter(r => Boolean(r.next_gig));

    if (q) {
      list = list.filter(r =>
        String(r.display_name || '').toLowerCase().includes(q) ||
        String(r.team_key || '').toLowerCase().includes(q) ||
        String(r.primary_genre || '').toLowerCase().includes(q) ||
        String(r.why_line || '').toLowerCase().includes(q) ||
        String(r.next_gig_text || '').toLowerCase().includes(q)
      );
    }

    list = sortRows(list, appState.candSort.col, appState.candSort.dir);

    root.querySelectorAll('[data-move-chip]').forEach(btn => {
      const active = btn.dataset.moveChip === moveFilter;
      btn.classList.toggle('active', active);
      btn.setAttribute('aria-pressed', active ? 'true' : 'false');
    });

    // Register current filtered & sorted rows with unified Export menu
    setExportContext({
      csvLabel: `후보 목록 CSV 내려받기 (${fmtInt(list.length)}팀)`,
      csvFilename: `crate_digger_candidates_${appState.dataEnd || 'export'}.csv`,
      csvHeaders: ['rank', 'team_key', 'display_name', 'genre', 'score', 'why', 'next_gig', 'n_branch', 'gigs_1y', 'venues', 'last_seen'],
      csvRows: list.map((r, idx) => [
        idx + 1,
        r.team_key,
        r.display_name || r.team_key,
        r.primary_genre || '',
        r.score ?? '',
        r.why_line || '',
        r.next_gig_text || '',
        r.n_branch ?? 0,
        r.gigs_1y ?? 0,
        r.venues ?? 0,
        r.last_seen || '',
      ]),
    });

    const shown = list.slice(0, visibleCount);
    root.querySelector('#candCountText').textContent = `${fmtInt(shown.length)} / ${fmtInt(list.length)}팀`;

    root.querySelectorAll('th.sortable').forEach(th => {
      const col = th.dataset.sort;
      const baseLabel = th.dataset.label || th.textContent.replace(/ [▲▼]$/, '');
      th.dataset.label = baseLabel;
      th.textContent = col === appState.candSort.col
        ? `${baseLabel} ${appState.candSort.dir === 'asc' ? '▲' : '▼'}`
        : baseLabel;
    });

    const tbody = root.querySelector('#candTbody');
    if (!shown.length) {
      tbody.innerHTML = `<tr><td colspan="7" style="padding:0;border:none;">${renderEmptyState({
        title: '조건에 맞는 후보 팀이 없습니다',
        message: '검색어 또는 변동 필터를 해제하거나 조건을 초기화해 보세요.',
        showReset: true,
      })}</td></tr>`;
      root.querySelector('#candMoreRow').hidden = true;
      root.querySelector('#candPhotoCredit').hidden = true;
      return;
    }

    const hasAnyImg = shown.some(r => appState.imagesByTeam.has(r.team_key));
    root.querySelector('#candPhotoCredit').hidden = !hasAnyImg;

    const riserTitle = diff.prevDate ? `${diff.prevDate} 대비 상승` : '이전 대비 상승';

    tbody.innerHTML = shown.map((r, idx) => {
      const subParts = [];
      if (r.primary_genre) subParts.push(escapeHtml(r.primary_genre));
      if (r.had_outcome) subParts.push(escapeHtml(TERMS.priorOutcome));

      let moveBadge = '';
      if (r.is_new) {
        moveBadge = '<span class="delta-badge is-new">신규</span>';
      } else if (r.riser) {
        let txt = '상승';
        if (r.riser.rank_gain > 0) txt = `+${r.riser.rank_gain}`;
        else if (r.riser.score_gain >= 0.05) txt = `+${fmtNum(r.riser.score_gain, 1)}`;
        moveBadge = `<span class="delta-badge is-up" title="${escapeHtml(riserTitle)}">${escapeHtml(txt)}</span>`;
      }

      const nextGigCell = r.next_gig_text
        ? `<span class="next-gig-chip">${escapeHtml(r.next_gig_text)}${r.next_gig.count > 1 ? ` 외 ${r.next_gig.count - 1}` : ''}</span>`
        : '<span class="muted">—</span>';

      const isExpanded = expandedTeamKey === r.team_key;

      return `
        <tr class="clickable" tabindex="0" data-team-key="${escapeHtml(r.team_key)}">
          <td class="num muted">${idx + 1}</td>
          <td>
            <div class="row-team-cell">
              <button type="button" class="cand-expand-btn" data-expand-team="${escapeHtml(r.team_key)}" aria-expanded="${isExpanded ? 'true' : 'false'}" aria-label="${escapeHtml(r.display_name || r.team_key)} 미리보기 ${isExpanded ? '접기' : '펼치기'}" title="${isExpanded ? '미리보기 접기' : '미리보기 펼치기'}">${isExpanded ? '▾' : '▸'}</button>
              ${avatarHtml(r.team_key, r.display_name, 28, { shape: 'circle', genre: r.primary_genre })}
              <div class="row-team-text">
                <div class="row-team-name">
                  <span class="cand-mobile-rank">#${idx + 1}</span>
                  <strong>${escapeHtml(r.display_name || r.team_key)}</strong>
                  ${moveBadge}
                </div>
                ${subParts.length ? `<div class="muted small">${subParts.join(' · ')}</div>` : ''}
                <div class="cand-mobile-meta">
                  <span class="cand-mobile-why">${escapeHtml(r.why_line)}</span>
                  ${r.next_gig_text ? `<span class="next-gig-chip">${escapeHtml(r.next_gig_text)}</span>` : ''}
                </div>
              </div>
            </div>
          </td>
          <td class="why-cell">${escapeHtml(r.why_line)}</td>
          <td class="nowrap next-gig-col">${nextGigCell}</td>
          <td class="num"><strong>${fmtNum(r.score, 2)}</strong></td>
          <td class="nowrap cand-listen-col">${renderRowListenControl(r)}</td>
          <td class="nowrap">${watchButtonHtml(r.team_key, r.display_name || r.team_key, true, true)}</td>
        </tr>
      `;
    }).join('');

    wireAvatarFallbacks(tbody);
    wireSpotifyButtons(tbody);

    if (expandedTeamKey) {
      const targetTr = [...tbody.querySelectorAll('tr.clickable')].find(el => el.dataset.teamKey === expandedTeamKey);
      if (targetTr) openPreviewRow(expandedTeamKey, targetTr);
      else expandedTeamKey = null;
    }

    const moreRow = root.querySelector('#candMoreRow');
    const rem = list.length - shown.length;
    if (rem > 0) {
      moreRow.hidden = false;
      moreRow.innerHTML = `
        <span>${fmtInt(shown.length)} / ${fmtInt(list.length)}팀 표시</span>
        <button type="button" class="btn btn-sm" id="btnCandMore">${fmtInt(Math.min(20, rem))}팀 더 보기</button>
      `;
      moreRow.querySelector('#btnCandMore').addEventListener('click', () => {
        visibleCount += 20;
        paintTable();
      });
    } else {
      moreRow.hidden = true;
    }
  }

  function formatPrecedentPreview(p) {
    if (!p) return '<span class="muted">겹치는 과거 수상 팀 선례 없음</span>';
    const dt = p.outcome_date ? ` · ${escapeHtml(String(p.outcome_date).slice(0, 7))}` : '';
    const shared = p.shared_list ? ` — <span class="muted">${escapeHtml(p.shared_list)}</span>` : '';
    return `${gradeBadgeHtml(p.outcome_grade)} <a href="#/team/${encodeURIComponent(p.past_team)}"><strong>${escapeHtml(p.display_name || p.past_team)}</strong></a> <span class="muted">(${escapeHtml(p.outcome_label || TERMS.outcome)}${dt})</span>${shared}`;
  }

  function closePreviewRows() {
    const tbody = root.querySelector('#candTbody');
    if (!tbody) return;
    tbody.querySelectorAll('tr.cand-preview-row').forEach(el => el.remove());
    tbody.querySelectorAll('.cand-expand-btn').forEach(btn => {
      btn.setAttribute('aria-expanded', 'false');
      btn.textContent = '▸';
      btn.title = '미리보기 펼치기';
    });
  }

  function openPreviewRow(teamKey, tr) {
    const r = rowByKey.get(teamKey);
    if (!r || !tr) return;
    closePreviewRows();
    const btn = tr.querySelector('.cand-expand-btn');
    if (btn) {
      btn.setAttribute('aria-expanded', 'true');
      btn.textContent = '▾';
      btn.title = '미리보기 접기';
    }
    const nextGigHtml = r.next_gig_text
      ? `<strong>${escapeHtml(r.next_gig_text)}</strong>${r.next_gig.count > 1 ? ` <span class="muted">외 ${fmtInt(r.next_gig.count - 1)}건</span>` : ''}`
      : '<span class="muted">예정된 공연 기록 없음</span>';
    const whyDetail = scorePartsLine(r);

    const previewTr = document.createElement('tr');
    previewTr.className = 'cand-preview-row';
    previewTr.dataset.previewFor = teamKey;
    previewTr.innerHTML = `
      <td colspan="7" class="cand-preview-cell">
        <div class="cand-preview-box">
          <div class="cand-preview-items">
            <div class="cand-preview-item">
              <span class="cand-preview-lbl">왜 후보인가</span>
              <span class="cand-preview-val">${escapeHtml(whyDetail)}</span>
            </div>
            <div class="cand-preview-item">
              <span class="cand-preview-lbl">비슷한 선례</span>
              <span class="cand-preview-val" data-preview-prec><span class="muted">선례 불러오는 중...</span></span>
            </div>
            <div class="cand-preview-item">
              <span class="cand-preview-lbl">다음 공연</span>
              <span class="cand-preview-val">${nextGigHtml}</span>
            </div>
          </div>
          <div class="cand-preview-actions">
            <a class="btn btn-sm" href="#/team/${encodeURIComponent(teamKey)}">팀 상세 보기 →</a>
          </div>
        </div>
      </td>
    `;
    tr.insertAdjacentElement('afterend', previewTr);

    queryTopPrecedent(teamKey).then(p => {
      if (!previewTr.isConnected || expandedTeamKey !== teamKey) return;
      const slot = previewTr.querySelector('[data-preview-prec]');
      if (slot) slot.innerHTML = formatPrecedentPreview(p);
    });
  }

  wireCandTabs(root);
  paintTable();

  root.querySelector('#candFilterInput').addEventListener('input', () => {
    visibleCount = 20;
    paintTable();
  });

  root.querySelectorAll('[data-move-chip]').forEach(btn => {
    btn.addEventListener('click', () => {
      const target = btn.dataset.moveChip;
      moveFilter = (moveFilter === target) ? '' : target;
      visibleCount = 20;
      paintTable();
    });
  });

  const triggerRecompute = () => {
    syncHash(true);
    window.dispatchEvent(new CustomEvent('app:recompute'));
  };

  root.querySelector('#candGenreSel').addEventListener('change', (e) => {
    appState.cfg.genre = e.target.value || '';
    triggerRecompute();
  });

  root.querySelector('#candPeriodSel').addEventListener('change', (e) => {
    appState.cfg.period_days = Number(e.target.value) || 0;
    triggerRecompute();
  });

  root.querySelectorAll('[data-branch-chip]').forEach(btn => {
    btn.addEventListener('click', () => {
      const b = btn.dataset.branchChip;
      const cur = new Set(appState.cfg.branches);
      if (cur.has(b)) {
        if (cur.size <= 1) return;
        cur.delete(b);
      } else {
        cur.add(b);
      }
      appState.cfg.branches = ALL_BRANCHES.filter(x => cur.has(x));
      triggerRecompute();
    });
  });

  root.querySelector('#candNewcomerInp').addEventListener('change', (e) => {
    appState.cfg.newcomer_years = Math.max(1, Math.min(15, Math.round(Number(e.target.value) || 3)));
    triggerRecompute();
  });

  root.querySelector('#candExcludeFamous').addEventListener('change', (e) => {
    appState.cfg.exclude_famous = e.target.checked;
    triggerRecompute();
  });

  root.querySelector('#candOnlyNoOutcome').addEventListener('change', (e) => {
    appState.cfg.only_no_outcome = e.target.checked;
    triggerRecompute();
  });

  root.querySelector('#candLimitSel').addEventListener('change', (e) => {
    appState.cfg.limit = Number(e.target.value) || 100;
    triggerRecompute();
  });

  root.querySelectorAll('th.sortable').forEach(th => {
    th.setAttribute('tabindex', '0');
    const onSort = () => {
      const col = th.dataset.sort;
      if (appState.candSort.col === col) {
        appState.candSort.dir = appState.candSort.dir === 'desc' ? 'asc' : 'desc';
      } else {
        appState.candSort.col = col;
        appState.candSort.dir = (col === 'display_name' || col === 'next_gig_sort') ? 'asc' : 'desc';
      }
      paintTable();
    };
    th.addEventListener('click', onSort);
    th.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        onSort();
      }
    });
  });

  const tbodyEl = root.querySelector('#candTbody');
  tbodyEl.addEventListener('click', (e) => {
    const expandBtn = e.target.closest('.cand-expand-btn');
    if (expandBtn) {
      e.stopPropagation();
      const tk = expandBtn.dataset.expandTeam;
      const tr = expandBtn.closest('tr.clickable');
      if (expandedTeamKey === tk) {
        expandedTeamKey = null;
        closePreviewRows();
      } else {
        expandedTeamKey = tk;
        openPreviewRow(tk, tr);
      }
      return;
    }
    if (e.target.closest('button') || e.target.closest('a')) return;
    const tr = e.target.closest('tr.clickable');
    if (tr && tr.dataset.teamKey) {
      navigateTo('team', tr.dataset.teamKey);
    }
  });
  tbodyEl.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    if (e.target.closest('button') || e.target.closest('a')) return;
    const tr = e.target.closest('tr.clickable');
    if (tr && tr.dataset.teamKey) {
      e.preventDefault();
      navigateTo('team', tr.dataset.teamKey);
    }
  });
}
