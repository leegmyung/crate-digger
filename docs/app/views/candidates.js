import {
  ALL_BRANCHES, appState, getActiveFilterSummary, getTableDensity, isWatched, navigateTo,
  setExportContext, setTableDensity, syncHash,
} from '../state.js';
import {
  buildNextGigByTeam, ensureVideosLoaded, getSnapshotDiff, queryCandidates, queryDebutCandidates,
  queryDebutScorecard, queryDiscoveryStages, queryRankChange, queryRisingPreset,
  queryTopPrecedent, queryUpcomingGigs,
} from '../db.js';
import {
  avatarHtml, canPlayTeam, dormantBadgeHtml, escapeHtml, fmtInt, fmtNum, formatNextGigText,
  formatRecentActivityCell, formatSourceKey, genreConfidenceBadgeHtml, isWeakGenreConfidence,
  gradeBadgeHtml, INFO_TIPS, infoTip, isDormantTeam, naCell,
  newcomerUnverifiedBadgeHtml, plainWhyLine, playButtonHtml, renderActionBanner,
  renderEmptyState, renderTableCsvBtn, scorePartsLine,
  STAGE_META, STAGE_ORDER, stageBadgeHtml, TERMS, triggerTableCsvExport,
  updateSortHeaders, watchButtonHtml, wireAvatarFallbacks,
  wireTableKeyboardNav, wireTableRowHoverPreview, youtubeQuickInfo,
} from '../ui.js';
import { compareToggleHtml } from '../components/compare_tray.js';
import {
  activePresetOf, formatRankDeltaHtml, matchesReleaseMonths, presetChartNoteHtml, RELEASE_MONTH_OPTIONS, ROLE_LINES,
  renderCandPanelHtml, renderCandResultsBarHtml, renderPresetRowHtml,
} from '../components/cand_filters.js';
import { applySavedFilter, listSavedFilters } from '../saved_filters.js';
import { loadVenueLadder } from '../db_venue.js';
import { renderChartTabsHtml } from './charts.js';
import { attachTeamPeek, peekKeyFromHash } from '../components/team_peek.js';
import { buildHeatRows, nextHeatSort, renderHeatmapHtml } from './candidates_heatmap.js';
import { queryPeerCompare } from '../db_peer.js';
import { wireSavedRow } from './cand_saved.js';

const DEBUT_MIN_SAMPLE = 5;
const HEAT_MIN_ROWS = 25; // 색 지도는 촘촘해서 한 화면 25줄부터
let candDocListeners = null; // 후보 필터 묶음 메뉴의 문서 단위 듣기(다시 그릴 때 끊음)
// 쉬운 화면 ③: 필터 패널은 기본 접힘('+ 필터 추가'로 엶) · 채움 숫자(51/100팀)·장르 순위 칸은 '고급 보기'에서만.
// 조건을 바꾸면 화면을 다시 그리므로 이 탭이 열려 있는 동안 상태를 기억한다.
let discoverPanelOpen = false;
let discoverAdvanced = false;
const DEBUT_DOC_URL = 'https://github.com/leegmyung/crate-digger/blob/main/docs/debut_cohort.md';
const VALID_SORT_COLS = new Set(['score', 'display_name', 'next_gig_sort', 'momentum_pct', 'genre_rank']);
const VALID_DEBUT_SORT_COLS = new Set(['score', 'first_release', 'display_name', 'mentions']);

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
    if (safeCol === 'genre_rank') {
      const ga = a.genre_rank;
      const gb = b.genre_rank;
      if (ga === null || ga === undefined) {
        if (gb === null || gb === undefined) return (Number(b.score) || -1) - (Number(a.score) || -1);
        return 1;
      }
      if (gb === null || gb === undefined) return -1;
      if (ga !== gb) return (ga - gb) * mult;
      return (Number(b.score) || -1) - (Number(a.score) || -1);
    }
    if (safeCol === 'momentum_pct') {
      const va = a.momentum_pct;
      const vb = b.momentum_pct;
      if (va === null || va === undefined) {
        if (vb === null || vb === undefined) return (Number(b.score) || -1) - (Number(a.score) || -1);
        return 1;
      }
      if (vb === null || vb === undefined) return -1;
      if (va !== vb) return (va - vb) * mult;
      const ra = Number(a.recent_n) || 0;
      const rb = Number(b.recent_n) || 0;
      if (ra !== rb) return (ra - rb) * mult;
      return (Number(b.score) || -1) - (Number(a.score) || -1);
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

function hasRowListenLink(r) {
  if (canPlayTeam(r.team_key)) return true;
  const yt = youtubeQuickInfo(r.team_key);
  return Boolean(yt && (yt.kind === 'channel' || yt.kind === 'video'));
}

/** '▶' = 화면 아래 미니 플레이어에서 바로 듣기. 틀 거리가 없고 유튜브 채널만 있으면 채널 링크. */
function renderRowListenControl(r) {
  const name = r.display_name || r.team_key;
  const yt = youtubeQuickInfo(r.team_key);
  if (canPlayTeam(r.team_key) || !(yt && yt.kind === 'channel')) {
    const play = playButtonHtml(r.team_key, name, { variant: 'icon' });
    if (play) return play;
  }
  if (yt && yt.kind === 'channel') {
    return `<a class="btn btn-icon btn-yt-mini" href="${escapeHtml(yt.url)}" target="_blank" rel="noopener noreferrer" title="유튜브 공식 채널" aria-label="${escapeHtml(r.display_name || r.team_key)} 유튜브 공식 채널">YT</a>`;
  }
  if (yt && yt.kind === 'video') {
    return `<a class="btn btn-icon btn-yt-mini" href="#/team/${encodeURIComponent(r.team_key)}" title="최근 무대 영상 ${yt.count}개" aria-label="${escapeHtml(r.display_name || r.team_key)} 무대 영상">영상</a>`;
  }
  return naCell('연결된 스포티파이·유튜브 링크가 없습니다');
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
    if (safeCol === 'mentions') {
      const ma = a.mentions?.length || 0;
      const mb = b.mentions?.length || 0;
      if (ma !== mb) return (ma - mb) * mult;
      return ((Number(b.score) || 0) - (Number(a.score) || 0));
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
  const initialPeek = peekKeyFromHash();
  const asOf = c.as_of || appState.dataEnd || '2026-11-27';
  const [debutData, debutScorecard] = await Promise.all([
    queryDebutCandidates({ as_of: asOf }),
    queryDebutScorecard({ horizonMonths: c.horizon_months || 24 }),
    ensureVideosLoaded().catch(() => null), // 표의 '영상' 버튼(스포티파이·유튜브 채널 없는 팀)용
  ]);

  if (!VALID_DEBUT_SORT_COLS.has(appState.debutSort?.col)) {
    appState.debutSort = { col: 'score', dir: 'desc' };
  }
  const debutSort = appState.debutSort;
  const debutByKey = new Map(debutData.mentioned.map(t => [t.team_key, t]));
  let expandedDebutKey = null;
  let lastDebutCsvSpec = { filename: `crate_digger_debut_${asOf}.csv`, headers: [], rows: [] };

  const bannerHtml = renderActionBanner({
    title: '갓 데뷔',
    lead: debutData.total
      ? `기준일(${escapeHtml(asOf)}) 전 12개월 내 첫 발매·그 전 신호 없는 갓 데뷔 신인 <strong>${fmtInt(debutData.total)}팀</strong>(언급 있음 ${fmtInt(debutData.mentioned.length)}팀 · 아직 언급 없음 ${fmtInt(debutData.unmentioned.length)}팀)입니다.`
      : `기준일(${escapeHtml(asOf)}) 전 12개월 내 조건에 맞는 갓 데뷔 신인이 없습니다.`,
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
        const rateTxt = r.rate !== null && r.rate !== undefined ? `${fmtNum(r.rate, 1)}%` : '—';
        const liftTxt = r.lift !== null && r.lift !== undefined ? `${fmtNum(r.lift, 1)}배` : '—';
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
    ? `데뷔 코호트 검증 기준 첫 발매 뒤 ${fmtInt(debutScorecard.mentionMonths)}개월 안에 어느 출처에도 안 나온 언급 전 신인이 <strong>${fmtInt(debutScorecard.unmentionedPct)}%</strong>(${fmtInt(unm.teams)}/${fmtInt(debutScorecard.cohortTeams)}팀, 그중 ${escapeHtml(TERMS.outcome)} ${fmtInt(unm.hits)}팀)입니다 — 아직 언급이 없는 팀이 가장 큰 발굴 기회입니다.`
    : '아직 어느 출처에도 언급되지 않은 언급 전 신인은 선행 발굴 후보로 따로 모아 둡니다.';

  root.innerHTML = `
    ${renderChartTabsHtml('debut')}
    ${bannerHtml}

    <section class="inline-filter-bar" aria-label="갓 데뷔 필터">
      <div class="inline-filter-row">
        <input type="search" id="debutFilterInput" class="input cand-search-input" value="${escapeHtml(appState.candQuery || '')}" placeholder="팀 이름·장르·언급 출처 검색..." aria-label="갓 데뷔 표 안에서 검색">
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
            기준일(${escapeHtml(asOf)}) 전 12개월 안에 첫 발매가 있고 첫 발매 이전 외부 신호가 0건인 팀만 모았습니다. 자기 발매(발매 신호)는 언급으로 세지 않습니다.
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
      <p class="debut-limit-note">한계: 첫 발매일은 멜론·스포티파이 프로필이 있는 팀에만 있어 전체 갓 데뷔 신인의 일부만 보입니다.</p>
    </section>

    <div class="block" style="padding:0;overflow:hidden;">
      <div class="table-bar">
        <div class="table-bar-left">
          <span class="table-bar-title" id="debutTableBarTitle">첫 발매 뒤 언급 팀</span>
          <span class="table-kb-hint">↑↓ 이동 · Enter 미리보기 · → 표 안 펼치기</span>
        </div>
        <div class="table-bar-right">
          ${renderTableCsvBtn('btnDebutCsv', 'CSV 내려받기')}
        </div>
      </div>
      <div class="table-wrap table-sticky">
        <table class="data-table debut-table" id="debutTable">
          <thead>
            <tr>
              <th class="num">#</th>
              <th class="sortable" data-debut-sort="display_name">팀</th>
              <th class="nowrap sortable" data-debut-sort="first_release">첫 발매일</th>
              <th class="sortable" data-debut-sort="mentions">첫 발매 뒤 언급 출처 · 데뷔 신뢰도</th>
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


  function closeDebutPreviewRows() {
    const tbody = root.querySelector('#debutTbody');
    if (!tbody) return;
    tbody.querySelectorAll('tr.cand-preview-row').forEach(el => el.remove());
    tbody.querySelectorAll('.cand-expand-btn').forEach(btn => {
      btn.setAttribute('aria-expanded', 'false');
      btn.textContent = '▸';
      btn.title = '미리보기 펼치기';
    });
  }

  function openDebutPreviewRow(teamKey, tr) {
    const r = debutByKey.get(teamKey);
    if (!r || !tr) return;
    closeDebutPreviewRows();
    const btn = tr.querySelector('.cand-expand-btn');
    if (btn) {
      btn.setAttribute('aria-expanded', 'true');
      btn.textContent = '▾';
      btn.title = '미리보기 접기';
    }
    const mentionDetails = r.mentions.map(m => {
      const info = formatSourceKey(m.src);
      const sc = debutScorecard?.bySrc?.get(m.src);
      const daysTxt = m.days_to_mention !== null && m.days_to_mention !== undefined ? `+${fmtInt(m.days_to_mention)}일` : '—';
      const scTxt = sc && sc.rate !== null && sc.rate !== undefined
        ? ` (코호트 ${fmtNum(sc.rate, 1)}% · ${fmtNum(sc.lift, 1)}배)`
        : '';
      return `${info.label} ${daysTxt}${scTxt}`;
    }).join(' · ');

    const previewTr = document.createElement('tr');
    previewTr.className = 'cand-preview-row';
    previewTr.dataset.previewFor = teamKey;
    previewTr.innerHTML = `
      <td colspan="7" class="cand-preview-cell">
        <div class="cand-preview-box">
          <div class="cand-preview-items">
            <div class="cand-preview-item">
              <span class="cand-preview-lbl">첫 발매</span>
              <span class="cand-preview-val mono">${escapeHtml(r.first_release || '—')}${r.primary_genre ? ` · ${escapeHtml(r.primary_genre)}` : ''}</span>
            </div>
            <div class="cand-preview-item">
              <span class="cand-preview-lbl">언급 출처 (${fmtInt(r.mentions.length)}곳)</span>
              <span class="cand-preview-val">${escapeHtml(mentionDetails || '—')}</span>
            </div>
            <div class="cand-preview-item">
              <span class="cand-preview-lbl">현재 점수</span>
              <span class="cand-preview-val mono">${r.score !== null ? `${fmtNum(r.score, 2)}점` : '점수 미산출'}</span>
            </div>
          </div>
          <div class="cand-preview-actions">
            <a class="btn btn-sm" href="#/team/${encodeURIComponent(teamKey)}">팀 상세 보기 →</a>
          </div>
        </div>
      </td>
    `;
    tr.insertAdjacentElement('afterend', previewTr);
  }

  function paintDebut() {
    const qRaw = (root.querySelector('#debutFilterInput')?.value || '').trim();
    appState.candQuery = qRaw;
    const q = qRaw.toLowerCase();
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
    const barTitle = root.querySelector('#debutTableBarTitle');
    if (barTitle) barTitle.textContent = `첫 발매 뒤 언급 팀 (${fmtInt(filteredMentioned.length)}팀)`;
    const unmSumEl = root.querySelector('#debutUnmSummary');
    if (unmSumEl) unmSumEl.textContent = `아직 언급 없음 (${fmtInt(filteredUnmentioned.length)}팀)`;

    updateSortHeaders(root.querySelector('#debutTable'), debutSort.col, debutSort.dir, 'debutSort');

    lastDebutCsvSpec = {
      filename: `crate_digger_debut_${asOf}.csv`,
      headers: ['#', '팀', '장르', '첫 발매일', '첫 발매 뒤 언급 출처', '점수'],
      rows: filteredMentioned.map((r, idx) => [
        idx + 1,
        r.display_name || r.team_key,
        r.primary_genre || '',
        r.first_release || '',
        r.mentions.map(m => `${formatSourceKey(m.src).label}(+${m.days_to_mention ?? '?'}일)`).join(' / '),
        r.score !== null && r.score !== undefined ? fmtNum(r.score, 2) : '',
      ]),
    };

    setExportContext({
      csvLabel: `갓 데뷔 CSV 내려받기 (${fmtInt(filteredMentioned.length)}팀)`,
      csvFilename: lastDebutCsvSpec.filename,
      csvHeaders: lastDebutCsvSpec.headers,
      csvRows: lastDebutCsvSpec.rows,
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
        if (r.primary_genre) subParts.push(r.primary_genre);
        if (r.had_outcome) subParts.push(TERMS.priorOutcome);
        const subText = subParts.join(' · ');
        const mentionsHtml = `<div class="debut-mention-list">${r.mentions.map(m => renderDebutMentionChip(m, debutScorecard)).join('')}</div>`;
        const isExpanded = expandedDebutKey === r.team_key;
        const nameTxt = r.display_name || r.team_key;
        return `
          <tr class="clickable" tabindex="0" data-nav-row="1" data-team-key="${escapeHtml(r.team_key)}">
            <td class="num muted">${idx + 1}</td>
            <td>
              <div class="row-team-cell">
                <button type="button" class="cand-expand-btn" data-debut-expand="${escapeHtml(r.team_key)}" aria-expanded="${isExpanded ? 'true' : 'false'}" aria-label="${escapeHtml(nameTxt)} 미리보기 ${isExpanded ? '접기' : '펼치기'}" title="${isExpanded ? '미리보기 접기' : '미리보기 펼치기'}">${isExpanded ? '▾' : '▸'}</button>
                ${avatarHtml(r.team_key, nameTxt, 28, { shape: 'circle', genre: r.primary_genre })}
                <div class="row-team-text">
                  <div class="row-team-name">
                    <span class="cand-mobile-rank">#${idx + 1}</span>
                    <strong class="cell-truncate" title="${escapeHtml(nameTxt)}">${escapeHtml(nameTxt)}</strong>
                    ${newcomerUnverifiedBadgeHtml(r.team_key)}
                  </div>
                  ${subText ? `<div class="muted small row-team-sub cell-truncate" title="${escapeHtml(subText)}">${escapeHtml(subText)}</div>` : ''}
                  <div class="debut-mobile-meta">
                    <span class="mono muted small">첫 발매 ${escapeHtml(r.first_release || '—')}</span>
                    ${mentionsHtml}
                  </div>
                </div>
              </div>
            </td>
            <td class="nowrap mono muted debut-date-col">${escapeHtml(r.first_release || '—')}</td>
            <td class="debut-mentions-col">${mentionsHtml}</td>
            <td class="num"><strong>${r.score !== null ? fmtNum(r.score, 2) : '—'}</strong></td>
            <td class="nowrap cand-listen-col">${renderRowListenControl(r)}</td>
            <td class="nowrap">${watchButtonHtml(r.team_key, nameTxt, true, true)} ${compareToggleHtml(r.team_key, nameTxt, { variant: 'icon' })}</td>
          </tr>
        `;
      }).join('');
      wireAvatarFallbacks(tbody);
      if (expandedDebutKey) {
        const targetTr = [...tbody.querySelectorAll('tr[data-nav-row]')].find(el => el.dataset.teamKey === expandedDebutKey);
        if (targetTr) openDebutPreviewRow(expandedDebutKey, targetTr);
        else expandedDebutKey = null;
      }
    }

    const unmBody = root.querySelector('#debutUnmBody');
    if (filteredUnmentioned.length) {
      unmBody.innerHTML = `
        <ul class="debut-unmentioned-list">
          ${filteredUnmentioned.map(r => `
            <li>
              <a class="debut-unm-team" href="#/team/${encodeURIComponent(r.team_key)}">
                ${avatarHtml(r.team_key, r.display_name, 24, { shape: 'circle', genre: r.primary_genre })}
                <strong class="cell-truncate" title="${escapeHtml(r.display_name)}">${escapeHtml(r.display_name)}</strong>
                ${r.primary_genre ? `<span class="small muted">${escapeHtml(r.primary_genre)}</span>` : ''}
              </a>
              <span class="debut-unm-right">
                <span class="mono small muted">첫 발매 ${escapeHtml(r.first_release || '—')}</span>
                ${watchButtonHtml(r.team_key, r.display_name, true, true)}
              </span>
            </li>
          `).join('')}
        </ul>
      `;
      wireAvatarFallbacks(unmBody);
    } else {
      unmBody.innerHTML = `<p class="small muted" style="margin:6px 0 0 0;">현재 기준일(${escapeHtml(asOf)}) 프로필 보유 갓 데뷔 신인 중 첫 발매 뒤 언급이 0건인 팀은 없습니다.</p>`;
    }

    const hasAnyImg = [...filteredMentioned, ...filteredUnmentioned].some(r => appState.imagesByTeam.has(r.team_key));
    root.querySelector('#debutPhotoCredit').hidden = !hasAnyImg;
  }

  paintDebut();

  root.querySelector('#btnDebutCsv')?.addEventListener('click', () => {
    triggerTableCsvExport(lastDebutCsvSpec);
  });

  let debutSearchTimer = null;
  root.querySelector('#debutFilterInput')?.addEventListener('input', () => {
    paintDebut();
    clearTimeout(debutSearchTimer);
    debutSearchTimer = setTimeout(() => syncHash(true), 200);
  });

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
    const onSort = () => {
      const col = th.dataset.debutSort;
      if (debutSort.col === col) {
        debutSort.dir = debutSort.dir === 'desc' ? 'asc' : 'desc';
      } else {
        debutSort.col = col;
        debutSort.dir = col === 'display_name' ? 'asc' : 'desc';
      }
      syncHash(true);
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
    const expBtn = e.target.closest('[data-debut-expand]');
    if (expBtn) {
      e.stopPropagation();
      const tk = expBtn.dataset.debutExpand;
      const tr = expBtn.closest('tr[data-nav-row]');
      if (expandedDebutKey === tk) {
        expandedDebutKey = null;
        closeDebutPreviewRows();
      } else {
        expandedDebutKey = tk;
        openDebutPreviewRow(tk, tr);
      }
      return;
    }
    if (e.target.closest('button') || e.target.closest('a')) return;
    const tr = e.target.closest('tr[data-nav-row]');
    if (tr && tr.dataset.teamKey) openDebutPeek(tr.dataset.teamKey);
  });

  wireTableKeyboardNav(tbodyEl, {
    onActivate: (tr) => {
      if (tr.dataset.teamKey) openDebutPeek(tr.dataset.teamKey);
    },
    onToggleExpand: (tr, key) => {
      const tk = tr.dataset.teamKey;
      if (!tk) return;
      if (key === 'ArrowLeft') {
        if (expandedDebutKey === tk) {
          expandedDebutKey = null;
          closeDebutPreviewRows();
        }
      } else if (expandedDebutKey !== tk) {
        expandedDebutKey = tk;
        openDebutPreviewRow(tk, tr);
      }
    },
  });

  wireTableRowHoverPreview(tbodyEl, (tr) => {
    const r = debutByKey.get(tr.dataset.teamKey);
    if (!r) return '';
    const mTxt = r.mentions.slice(0, 3).map(m => {
      const info = formatSourceKey(m.src);
      const d = m.days_to_mention !== null && m.days_to_mention !== undefined ? ` +${fmtInt(m.days_to_mention)}일` : '';
      return `${info.label}${d}`;
    }).join(', ') + (r.mentions.length > 3 ? ` 외 ${r.mentions.length - 3}곳` : '');
    return `
      <div class="rhp-head">
        <strong>${escapeHtml(r.display_name || r.team_key)}</strong>
        <span class="rhp-score">${r.score !== null ? `${fmtNum(r.score, 2)}점` : '—'}</span>
      </div>
      <div class="rhp-meta">${escapeHtml([r.primary_genre || '장르 미분류', `첫 발매 ${r.first_release || '—'}`].join(' · '))}</div>
      <div class="rhp-lines">
        <div class="rhp-line"><span class="rhp-lbl">언급 출처</span>${escapeHtml(mTxt || '—')}</div>
      </div>
      <div class="rhp-foot">클릭·Enter로 오른쪽 미리보기 · →로 표 안에서 펼치기</div>
    `;
  });
  // 줄을 누르거나 Enter → 오른쪽 미리보기(▸ 펼침은 그대로), 주소의 ?peek= 도 연다
  const openDebutPeek = attachTeamPeek(root, { initialKey: initialPeek });
}

export async function renderCandidatesView(root) {
  const initialPeek = peekKeyFromHash();
  if (appState.candTab === 'debut') {
    await renderDebutCandidatesView(root);
    return;
  }

  const asOf = appState.cfg.as_of || appState.dataEnd || '2026-11-27';
  const isRisingPreset = appState.candPreset === 'rising';
  const [rawRows, upcomingRaw, stageData, rankChangeData, risingRaw, ladder] = await Promise.all([
    queryCandidates(),
    queryUpcomingGigs({ asOf }),
    queryDiscoveryStages({ as_of: asOf }),
    queryRankChange({ as_of: asOf }),
    isRisingPreset ? queryRisingPreset() : Promise.resolve(null),
    loadVenueLadder(),
    ensureVideosLoaded().catch(() => null), // 표의 '영상' 버튼(스포티파이·유튜브 채널 없는 팀)용
  ]);
  // 가장 큰 무대 체급(venue_ladder.json teams[].max) — 발굴 '체급' 필터
  const TIER_RANK = { S: 1, M: 2, L: 3, XL: 4 };
  const maxTierOf = key => ladder?.teams?.[key]?.max || '';

  const c = appState.cfg;
  const nextGigByTeam = buildNextGigByTeam(upcomingRaw);
  const diff = getSnapshotDiff(rawRows);
  const newSet = new Set(diff.newEntrants.map(t => t.team_key));
  const riserMap = new Map(diff.risers.map(t => [t.team_key, t]));
  const stageByTeam = stageData?.byTeam || new Map();
  const rcByTeam = rankChangeData?.byTeam || new Map();
  const hasCityData = appState.teamCitiesByTeam.size > 0;

  const isKnownGenre = (g) => {
    const s = String(g || '').trim();
    return Boolean(s && s !== '미분류');
  };

  const rows = rawRows.map(r => {
    const ng = nextGigByTeam.get(r.team_key) || null;
    const riser = riserMap.get(r.team_key) || null;
    const st = stageByTeam.get(r.team_key) || null;
    const rc = rcByTeam.get(r.team_key) || null;
    const cityInfo = appState.teamCitiesByTeam.get(r.team_key) || null;
    const firstRel = appState.firstReleaseByTeam.get(r.team_key) || st?.first_release || '';
    const genreConf = appState.genreConfidenceByTeam.get(r.team_key) || '';
    const knownGenre = isKnownGenre(r.primary_genre);
    return {
      ...r,
      first_release: firstRel,
      genre_confidence: genreConf,
      home_city: cityInfo?.home_city || rc?.home_city || '',
      why_line: plainWhyLine(r),
      next_gig: ng,
      next_gig_text: ng ? formatNextGigText(ng) : '',
      is_new: newSet.has(r.team_key),
      riser,
      rank_change: rc,
      genre_rank: knownGenre && rc?.genre_rank ? rc.genre_rank : null,
      genre_n: knownGenre && rc?.genre_n ? rc.genre_n : null,
      stage_info: st,
      stage: st ? st.stage : null,
      stage_label: st ? (STAGE_META[st.stage]?.label || st.stage_label || '') : '',
      momentum_pct: st ? st.momentum_pct : null,
      recent_n: st ? st.recent_n : 0,
      prev_n: st ? st.prev_n : 0,
      is_dormant: isDormantTeam({ ...r, next_gig: ng }),
    };
  });

  // Fallback genre rank within current scored list for teams outside snapshot top-300
  const genreBuckets = new Map();
  for (const r of rows) {
    if (r.stage === 4 || !isKnownGenre(r.primary_genre)) continue;
    const g = r.primary_genre;
    if (!genreBuckets.has(g)) genreBuckets.set(g, []);
    genreBuckets.get(g).push(r);
  }
  for (const bucket of genreBuckets.values()) {
    bucket.sort((a, b) => (Number(b.score) || -1) - (Number(a.score) || -1));
    const n = bucket.length;
    bucket.forEach((r, idx) => {
      if (r.genre_rank === null || r.genre_rank === undefined) {
        r.genre_rank = idx + 1;
        r.genre_n = n;
      }
    });
  }

  const rowByKey = new Map(rows.map(r => [r.team_key, r]));
  const allRowByKey = new Map(rowByKey);

  // Build rows for stages outside default lab_scored ('0' 백지 & '4' 졸업)
  function buildStageFallbackRows(targetStage) {
    const out = [];
    const lim = Math.max(10, Number(c.limit) || 100);
    for (const s of (stageData?.rows || [])) {
      if (s.stage !== targetStage) continue;
      if (c.genre && s.primary_genre !== c.genre) continue;
      const existing = rowByKey.get(s.team_key);
      if (existing) {
        out.push(existing);
      } else {
        const ng = nextGigByTeam.get(s.team_key) || null;
        const rc = rcByTeam.get(s.team_key) || null;
        const cityInfo = appState.teamCitiesByTeam.get(s.team_key) || null;
        const knownGenre = isKnownGenre(s.primary_genre);
        const why = targetStage === 0
          ? (s.first_release ? `첫 발매 ${s.first_release} · 남의 언급 없음` : '첫 발매만 기록 · 남의 언급 없음')
          : (s.best_grade_before
            ? `${s.best_grade_before}등급 ${TERMS.outcome} (졸업)`
            : '유명 팀 (졸업)');
        const synth = {
          team_key: s.team_key,
          display_name: s.display_name || s.team_key,
          primary_genre: s.primary_genre || '',
          first_release: appState.firstReleaseByTeam.get(s.team_key) || s.first_release || '',
          genre_confidence: appState.genreConfidenceByTeam.get(s.team_key) || '',
          home_city: cityInfo?.home_city || rc?.home_city || '',
          score: null,
          why_line: why,
          next_gig: ng,
          next_gig_text: ng ? formatNextGigText(ng) : '',
          is_new: false,
          riser: null,
          rank_change: rc,
          genre_rank: knownGenre && rc?.genre_rank ? rc.genre_rank : null,
          genre_n: knownGenre && rc?.genre_n ? rc.genre_n : null,
          had_outcome: Boolean(s.best_grade_before),
          stage_info: s,
          stage: s.stage,
          stage_label: STAGE_META[s.stage]?.label || s.stage_label || '',
          momentum_pct: s.momentum_pct,
          recent_n: s.recent_n,
          prev_n: s.prev_n,
          last_seen: s.last_mention || s.first_release || '',
          is_dormant: false,
        };
        out.push(synth);
        if (!allRowByKey.has(synth.team_key)) allRowByKey.set(synth.team_key, synth);
      }
      if (out.length >= lim) break;
    }
    return out;
  }

  // Build rows for '떠오르는 팀' preset (docs/lab/sql/rising_preset.sql)
  const risingRows = Array.isArray(risingRaw) ? risingRaw.map(rr => {
    const existing = rowByKey.get(rr.team_key);
    const ng = existing?.next_gig || nextGigByTeam.get(rr.team_key) || null;
    const st = existing?.stage_info || stageByTeam.get(rr.team_key) || null;
    const rc = existing?.rank_change || rcByTeam.get(rr.team_key) || null;
    const cityInfo = appState.teamCitiesByTeam.get(rr.team_key) || null;
    const genre = rr.primary_genre || existing?.primary_genre || '';
    const knownGenre = isKnownGenre(genre);
    // growth 는 ln(1+최근) − ln(1+직전) 이라 '몇 배'가 아니다 → 건수만 평문으로 보여 준다
    const risingWhy = `최근 30일 ${fmtInt(rr.recent_n)}건 (직전 30일 ${fmtInt(rr.prev_n)}건) · 신호 ${fmtInt(rr.recent_branches)}종류`;
    const merged = {
      ...(existing || {}),
      team_key: rr.team_key,
      display_name: rr.display_name || existing?.display_name || rr.team_key,
      primary_genre: genre,
      first_release: existing?.first_release || appState.firstReleaseByTeam.get(rr.team_key) || st?.first_release || '',
      genre_confidence: existing?.genre_confidence || appState.genreConfidenceByTeam.get(rr.team_key) || '',
      home_city: existing?.home_city || cityInfo?.home_city || rc?.home_city || '',
      score: rr.score !== null && rr.score !== undefined ? rr.score : (existing?.score ?? null),
      why_line: risingWhy,
      next_gig: ng,
      next_gig_text: ng ? formatNextGigText(ng) : '',
      is_new: existing ? existing.is_new : newSet.has(rr.team_key),
      riser: existing ? existing.riser : (riserMap.get(rr.team_key) || null),
      rank_change: rc,
      genre_rank: knownGenre ? (existing?.genre_rank ?? rc?.genre_rank ?? null) : null,
      genre_n: knownGenre ? (existing?.genre_n ?? rc?.genre_n ?? null) : null,
      stage_info: st,
      stage: st ? st.stage : (existing?.stage ?? null),
      stage_label: st ? (STAGE_META[st.stage]?.label || st.stage_label || '') : (existing?.stage_label || ''),
      momentum_pct: st ? st.momentum_pct : (rr.prev_n > 0 ? Math.round(((rr.recent_n - rr.prev_n) / rr.prev_n) * 100) : (rr.recent_n > 0 ? 100 : null)),
      recent_n: rr.recent_n,
      prev_n: rr.prev_n,
      is_dormant: existing ? existing.is_dormant : false,
      rising_meta: rr,
    };
    if (!allRowByKey.has(merged.team_key)) allRowByKey.set(merged.team_key, merged);
    return merged;
  }) : null;

  const blankRows = buildStageFallbackRows(0);
  const gradRows = buildStageFallbackRows(4);
  const defaultRows = rows.filter(r => r.stage !== 4); // 졸업은 기본 숨김

  const stageCounts = {
    0: blankRows.length,
    1: defaultRows.filter(r => r.stage === 1).length,
    2: defaultRows.filter(r => r.stage === 2).length,
    3: defaultRows.filter(r => r.stage === 3).length,
    4: gradRows.length,
  };

  const genreCounts = new Map();
  for (const r of defaultRows) {
    if (isKnownGenre(r.primary_genre)) {
      genreCounts.set(r.primary_genre, (genreCounts.get(r.primary_genre) || 0) + 1);
    }
  }

  const releaseMonthCounts = {};
  for (const m of RELEASE_MONTH_OPTIONS) {
    releaseMonthCounts[m] = defaultRows.filter(r => matchesReleaseMonths(r.first_release, m, asOf)).length;
  }

  const branchCounts = {
    '공연': defaultRows.filter(r => Number(r.venues) > 0 || Number(r.gigs_1y) > 0).length,
    '선정·지원': defaultRows.filter(r => Number(r.best_stage) > 0).length,
    '발매': defaultRows.filter(r => Boolean(r.first_release)).length,
    '큐레이션': defaultRows.filter(r => Number(r.outlets) > 0 || Number(r.context_outlets) > 0).length,
  };

  if (!VALID_SORT_COLS.has(appState.candSort.col)) {
    appState.candSort.col = 'score';
    appState.candSort.dir = 'desc';
  }

  const newCount = defaultRows.filter(r => r.is_new).length;
  const riserCount = defaultRows.filter(r => Boolean(r.riser)).length;
  const upcomingCount = defaultRows.filter(r => Boolean(r.next_gig)).length;
  const nonSeoulCount = defaultRows.filter(r => r.home_city && r.home_city !== '서울').length;

  const filterCounts = {
    total: defaultRows.length,
    genres: genreCounts,
    releaseMonths: releaseMonthCounts,
    stages: stageCounts,
    branches: branchCounts,
    moves: { new: newCount, riser: riserCount, upcoming: upcomingCount },
    hasCityData,
    nonSeoul: nonSeoulCount,
    cities: defaultRows.reduce((m, r) => (r.home_city ? m.set(r.home_city, (m.get(r.home_city) || 0) + 1) : m), new Map()),
    hasLadder: Boolean(ladder?.teams),
    tiers: Object.fromEntries(['S', 'M', 'L'].map(t => [t, defaultRows.filter(r => TIER_RANK[maxTierOf(r.team_key)] && TIER_RANK[maxTierOf(r.team_key)] <= TIER_RANK[t]).length])),
    presets: {
      debut12: releaseMonthCounts[12],
      blank: blankRows.length,
      selected: stageCounts[3],
      regional: hasCityData ? nonSeoulCount : null,
      rising: risingRows ? risingRows.length : null,
    },
  };

  let visibleCount = 20;
  let expandedTeamKey = null;
  let lastCandCsvSpec = null;
  let popoverOpen = false;
  let density = getTableDensity();
  let heatSort = { col: 'rank', dir: 'asc' };
  let peerData = null; // 색 지도용 이웃 비교 (처음 색 지도로 바꿀 때 한 번 불러옴)
  let peerLoading = false;

  const topName = defaultRows[0] ? `${defaultRows[0].display_name} (${fmtNum(defaultRows[0].score, 2)}점)` : '없음';
  // 예전 '요약' 상자 → 머리 아래 한 줄 (세로 공간을 표에 양보)
  const summaryLineHtml = defaultRows.length
    ? `후보 상위 <strong>${fmtInt(defaultRows.length)}팀</strong> · 1위 <strong>${escapeHtml(topName)}</strong> · 예정 공연 잡힌 팀 <strong>${fmtInt(upcomingCount)}팀</strong>`
    : '현재 조건에 맞는 신인 후보가 없습니다.';

  const deltaRefLabel = rankChangeData?.monthDate
    ? `지난달(${rankChangeData.monthDate})`
    : (rankChangeData?.weekDate ? `지난주(${rankChangeData.weekDate})` : '이전 스냅샷');

  root.innerHTML = `
    <div class="discover-head">
      <h1 class="discover-title">발굴</h1>
      <p class="small muted disc-role">${escapeHtml(ROLE_LINES.discover)} · 정해진 순위표는 <a href="#/charts">차트</a> · 점수가 얼마나 맞았는지는 <a href="#/verify/backtest">검증</a></p>
      <p class="small disc-summary">${summaryLineHtml}</p>
    </div>
    <div id="candPresetHost"></div>
    <div id="candPresetNote"></div>
    <div class="discover-layout${discoverPanelOpen ? '' : ' is-panel-closed'}" id="candFilterBarHost">
    <aside class="discover-panel${discoverPanelOpen ? ' is-open' : ''}" id="candPanel" aria-label="발굴 필터"${discoverPanelOpen ? '' : ' hidden'}>
      <div class="dp-head"><strong>필터</strong><button type="button" class="btn btn-sm dp-close" id="candPanelClose" aria-label="필터 닫기">닫기</button></div>
      <div id="candPanelHost"></div>
    </aside>
    <div class="discover-results">
    <div class="disc-toolrow"><div id="candResultsBar"></div><div id="candSavedHost" class="disc-save-host"></div></div>

    <div class="block" style="padding:0;overflow:hidden;">
      <div class="table-bar">
        <div class="table-bar-left">
          <strong id="candTableBarTitle">신인 후보 목록</strong>
          <span class="small muted" id="candCountText"></span>
          ${infoTip('단축키', { what: '↑↓ 줄 이동 · Enter 오른쪽 빠른 보기 · → 표 안에서 펼치기 · ← 접기' }, { compact: true })}
        </div>
        <div class="table-bar-right">
          <details class="ux-more disc-view-more">
            <summary class="btn btn-sm" aria-label="보기 설정 — 고급 보기·표 밀도·CSV">보기 설정 ▾</summary>
            <div class="ux-more-menu">
              <label class="cf-crit-check"><input type="checkbox" id="candAdvancedChk"${discoverAdvanced ? ' checked' : ''}><span>고급 보기 (장르 순위·최근 활동 칸 · 칸마다 채움 숫자)</span></label>
              <div class="density-switch" role="group" aria-label="표 밀도">
                <button type="button" class="density-btn${density === 'compact' ? ' is-active' : ''}" data-density="compact" aria-pressed="${density === 'compact' ? 'true' : 'false'}">촘촘</button>
                <button type="button" class="density-btn${density === 'comfortable' ? ' is-active' : ''}" data-density="comfortable" aria-pressed="${density === 'comfortable' ? 'true' : 'false'}">편하게</button>
              </div>
              ${renderTableCsvBtn('btnCandCsv', 'CSV 내려받기')}
            </div>
          </details>
        </div>
      </div>
      <div id="candHeatHost" class="heat-host" hidden></div>
      <div class="table-wrap table-sticky" id="candTableWrap">
        <table class="data-table cand-table is-density-${density}${discoverAdvanced ? ' is-advanced' : ''}" id="candTable">
          <thead>
            <tr>
              <th class="num cand-rank-th">#${infoTip(`순위 변동 (${deltaRefLabel})`, INFO_TIPS.rank_change, { compact: true })}<span class="th-coverage" data-cov="rank"></span></th>
              <th class="sortable" data-sort="display_name">팀<span class="th-coverage" data-cov="team"></span></th>
              <th class="nowrap sortable cand-genre-rank-col" data-sort="genre_rank">장르 순위${infoTip('장르 안 순위', INFO_TIPS.genre_rank, { compact: true })}<span class="th-coverage" data-cov="genre_rank"></span></th>
              <th>주목 이유<span class="th-coverage" data-cov="why"></span></th>
              <th class="nowrap sortable next-gig-col" data-sort="next_gig_sort">다음 공연<span class="th-coverage" data-cov="next_gig"></span></th>
              <th class="num nowrap sortable cand-activity-col" data-sort="momentum_pct">최근 활동${infoTip('최근 활동', INFO_TIPS.recent_activity, { compact: true })}<span class="th-coverage" data-cov="activity"></span></th>
              <th class="num sortable cand-score-col" data-sort="score">점수${infoTip('종합 점수', INFO_TIPS.score, { compact: true })}<span class="th-coverage" data-cov="score"></span></th>
              <th class="nowrap cand-listen-col">듣기<span class="th-coverage" data-cov="listen"></span></th>
              <th class="nowrap cand-watch-col">담기<span class="th-coverage" data-cov="watch"></span></th>
            </tr>
          </thead>
          <tbody id="candTbody"></tbody>
        </table>
      </div>
      <div class="more-row" id="candMoreRow" hidden></div>
    </div>
    <p class="photo-credit" id="candPhotoCredit" hidden>아티스트 사진 출처: Spotify</p>
    </div>
    </div>
  `;

  function updateColumnCoverage(list) {
    const total = list.length;
    const fmtCov = (n) => (total > 0 ? `${fmtInt(n)}/${fmtInt(total)}팀` : '0/0팀');
    const cov = {
      rank: fmtCov(list.filter(r => r.rank_change && (r.rank_change.month_label || r.rank_change.week_label)).length),
      team: fmtCov(total),
      genre_rank: fmtCov(list.filter(r => r.genre_rank !== null && r.genre_rank !== undefined).length),
      why: fmtCov(list.filter(r => Boolean(r.why_line)).length),
      next_gig: fmtCov(list.filter(r => Boolean(r.next_gig_text)).length),
      activity: fmtCov(list.filter(r => r.stage_info && r.stage_info.momentum_pct !== null && r.stage_info.momentum_pct !== undefined).length),
      score: fmtCov(list.filter(r => r.score !== null && r.score !== undefined).length),
      listen: fmtCov(list.filter(r => hasRowListenLink(r)).length),
      watch: fmtCov(list.filter(r => isWatched(r.team_key)).length),
    };
    root.querySelectorAll('.th-coverage[data-cov]').forEach(el => {
      const k = el.dataset.cov;
      if (k && cov[k] !== undefined) el.textContent = cov[k];
    });
  }

  // 2-5 색 지도: 활성이면 표 대신 색 지도를 그리고 true 를 돌려준다
  function paintHeatIfActive(list) {
    const heatHost = root.querySelector('#candHeatHost');
    const tableWrap = root.querySelector('#candTableWrap');
    const isHeat = appState.candView === 'heat';
    if (heatHost) heatHost.hidden = !isHeat;
    if (tableWrap) tableWrap.hidden = isHeat;
    root.querySelector('.density-switch')?.toggleAttribute('hidden', isHeat);
    root.querySelector('.table-kb-hint')?.toggleAttribute('hidden', isHeat);
    if (!isHeat || !heatHost) return false;

    if (!peerData && !peerLoading) {
      peerLoading = true;
      queryPeerCompare({ as_of: asOf }).then(res => {
        peerData = res;
        peerLoading = false;
        if (heatHost.isConnected && appState.candView === 'heat') paintTable();
      });
    }
    const heatRows = buildHeatRows(list, {
      peerByTeam: peerData?.byTeam || new Map(),
      cities: appState.teamCitiesByTeam,
    });
    const limit = Math.max(visibleCount, HEAT_MIN_ROWS);
    heatHost.innerHTML = list.length
      ? renderHeatmapHtml(heatRows, { sort: heatSort, limit, loading: peerLoading, error: peerData?.error || '' })
      : renderEmptyState({
        title: '조건에 맞는 후보 팀이 없습니다',
        message: '검색어 또는 적용된 필터 꼬리표를 지우거나 조건을 초기화해 보세요.',
        showReset: true,
      });
    root.querySelector('#candPhotoCredit').hidden = true;
    const countEl = root.querySelector('#candCountText');
    if (countEl) countEl.textContent = `${fmtInt(Math.min(limit, list.length))} / ${fmtInt(list.length)}팀`;
    paintMoreRow(list.length, Math.min(limit, list.length));
    return true;
  }

  function paintMoreRow(total, shownCount) {
    const moreRow = root.querySelector('#candMoreRow');
    const rem = total - shownCount;
    if (rem <= 0) {
      moreRow.hidden = true;
      return;
    }
    moreRow.hidden = false;
    moreRow.innerHTML = `
      <span>${fmtInt(shownCount)} / ${fmtInt(total)}팀 표시</span>
      <button type="button" class="btn btn-sm" id="btnCandMore">${fmtInt(Math.min(20, rem))}팀 더 보기</button>
    `;
    moreRow.querySelector('#btnCandMore').addEventListener('click', () => {
      visibleCount = Math.max(visibleCount, shownCount) + 20;
      paintTable();
    });
  }

  function paintTable() {
    const qRaw = String(appState.candQuery || '').trim();
    const q = qRaw.toLowerCase();
    const moveFilter = appState.candMove || '';
    const stageFilter = appState.candStage || '';
    const releaseMonths = Number(appState.candReleaseMonths) || 0;
    const regionFilter = appState.candRegion || '';

    let list;
    if (appState.candPreset === 'rising' && risingRows) {
      list = risingRows;
      if (stageFilter) list = list.filter(r => String(r.stage) === stageFilter);
    } else if (stageFilter === '0') {
      list = blankRows;
    } else if (stageFilter === '4') {
      list = gradRows;
    } else if (stageFilter === '1' || stageFilter === '2' || stageFilter === '3') {
      list = defaultRows.filter(r => String(r.stage) === stageFilter);
    } else {
      list = defaultRows;
    }

    if (releaseMonths > 0) {
      list = list.filter(r => matchesReleaseMonths(r.first_release, releaseMonths, asOf));
    }

    if (regionFilter === 'non_seoul') {
      list = list.filter(r => r.home_city && r.home_city !== '서울');
    }
    // 발굴 패널의 새 조건: 활동 도시 · 가장 큰 무대 체급 상한 · 장르를 골랐을 때 추정 장르 빼기
    if (appState.candCity) list = list.filter(r => r.home_city === appState.candCity);
    if (appState.candTier) {
      const cap = TIER_RANK[appState.candTier];
      list = list.filter(r => TIER_RANK[maxTierOf(r.team_key)] && TIER_RANK[maxTierOf(r.team_key)] <= cap);
    }
    if (appState.candGenreInf === 'exclude' && c.genre) list = list.filter(r => !isWeakGenreConfidence(r.genre_confidence));

    if (moveFilter === 'new') list = list.filter(r => r.is_new);
    else if (moveFilter === 'riser') list = list.filter(r => Boolean(r.riser));
    else if (moveFilter === 'upcoming') list = list.filter(r => Boolean(r.next_gig));

    if (q) {
      list = list.filter(r =>
        String(r.display_name || '').toLowerCase().includes(q) ||
        String(r.team_key || '').toLowerCase().includes(q) ||
        String(r.primary_genre || '').toLowerCase().includes(q) ||
        String(r.why_line || '').toLowerCase().includes(q) ||
        String(r.next_gig_text || '').toLowerCase().includes(q) ||
        String(r.stage_label || '').toLowerCase().includes(q)
      );
    }

    list = sortRows(list, appState.candSort.col, appState.candSort.dir);

    lastCandCsvSpec = {
      filename: `crate_digger_candidates_${appState.dataEnd || 'export'}.csv`,
      headers: ['#', '팀', '장르', '장르 순위', '발굴 단계', '주목 이유', '다음 공연', '최근 활동', '점수'],
      rows: list.map((r, idx) => {
        const act = formatRecentActivityCell(r.stage_info);
        const grTxt = (r.genre_rank !== null && r.genre_rank !== undefined && r.primary_genre)
          ? `${r.primary_genre} ${r.genre_rank}/${r.genre_n}`
          : '장르 미정';
        return [
          idx + 1,
          r.display_name || r.team_key,
          r.primary_genre || '',
          grTxt,
          r.stage_label || '',
          r.why_line || '',
          r.next_gig_text ? `${r.next_gig_text}${r.next_gig?.count > 1 ? ` 외 ${r.next_gig.count - 1}` : ''}` : '',
          act.text,
          r.score !== null && r.score !== undefined ? fmtNum(r.score, 2) : '',
        ];
      }),
    };

    // Register current filtered & sorted rows with unified Export menu
    setExportContext({
      csvLabel: `발굴 결과 CSV 내려받기 (${fmtInt(list.length)}팀)`,
      csvFilename: lastCandCsvSpec.filename,
      csvHeaders: lastCandCsvSpec.headers,
      csvRows: lastCandCsvSpec.rows,
    });

    const shown = list.slice(0, visibleCount);
    const countEl = root.querySelector('#candCountText');
    if (countEl) countEl.textContent = `${fmtInt(shown.length)} / ${fmtInt(list.length)}팀`;

    const barTitle = root.querySelector('#candTableBarTitle');
    if (barTitle) {
      const stMeta = stageFilter ? STAGE_META[Number(stageFilter)] : null;
      if (appState.candPreset === 'rising') {
        barTitle.textContent = `떠오르는 팀 (${fmtInt(list.length)}팀)`;
      } else if (stMeta) {
        barTitle.textContent = `${stMeta.label} (${fmtInt(list.length)}팀)`;
      } else {
        barTitle.textContent = `신인 후보 (${fmtInt(list.length)}팀)`;
      }
    }

    updateColumnCoverage(list);
    updateSortHeaders(root.querySelector('#candTable'), appState.candSort.col, appState.candSort.dir, 'sort');

    if (paintHeatIfActive(list)) return;

    const tbody = root.querySelector('#candTbody');
    if (!shown.length) {
      const emptyMsg = (regionFilter === 'non_seoul' && !hasCityData)
        ? '아직 팀별 지역(도시) 데이터가 수집되지 않아 지방 씬 팀을 가를 수 없습니다. 지역 필터를 지우면 전체 후보를 볼 수 있습니다.'
        : '검색어 또는 적용된 필터 꼬리표를 지우거나 조건을 초기화해 보세요.';
      tbody.innerHTML = `<tr><td colspan="9" style="padding:0;border:none;">${renderEmptyState({
        title: (regionFilter === 'non_seoul' && !hasCityData) ? '지방 씬 데이터 준비 중' : '조건에 맞는 후보 팀이 없습니다',
        message: emptyMsg,
        showReset: true,
      })}</td></tr>`;
      root.querySelector('#candMoreRow').hidden = true;
      root.querySelector('#candPhotoCredit').hidden = true;
      return;
    }

    const hasAnyImg = shown.some(r => appState.imagesByTeam.has(r.team_key));
    root.querySelector('#candPhotoCredit').hidden = !hasAnyImg;

    const avatarSize = density === 'compact' ? 22 : 28;

    tbody.innerHTML = shown.map((r, idx) => {
      const stagePill = stageBadgeHtml(r.stage, { short: true });
      const dormantPill = dormantBadgeHtml(r.is_dormant);
      const unverifiedPill = newcomerUnverifiedBadgeHtml(r.team_key);
      const inferredTag = genreConfidenceBadgeHtml(r.team_key, r.genre_confidence);
      const act = formatRecentActivityCell(r.stage_info);
      const hasAct = Boolean(r.stage_info && r.stage_info.momentum_pct !== null && r.stage_info.momentum_pct !== undefined);
      const actCellHtml = hasAct
        ? act.html
        : naCell(act.tooltip || '최근 180일 활동 기록 없음');

      const nextGigCell = r.next_gig_text
        ? `<span class="next-gig-chip" title="${escapeHtml(r.next_gig_text)}">${escapeHtml(r.next_gig_text)}${r.next_gig.count > 1 ? ` 외 ${r.next_gig.count - 1}` : ''}</span>`
        : naCell('예정된 공연 기록이 없습니다');

      const genreRankCell = (r.genre_rank !== null && r.genre_rank !== undefined && isKnownGenre(r.primary_genre))
        ? `<span class="genre-rank-cell" title="${escapeHtml(`${r.primary_genre} 장르 ${r.genre_n}팀 중 ${r.genre_rank}위`)}"><span class="genre-rank-name">${escapeHtml(r.primary_genre)}</span> <strong class="genre-rank-num">${fmtInt(r.genre_rank)}</strong><span class="muted">/${fmtInt(r.genre_n)}</span></span>`
        : naCell('장르가 아직 분류되지 않은 팀입니다', { label: '장르 미정' });

      const whyTxt = r.why_line || '';
      const whyCellHtml = whyTxt
        ? escapeHtml(whyTxt)
        : naCell('점수 근거 문구가 없습니다');

      const scoreCellHtml = (r.score !== null && r.score !== undefined)
        ? `<strong>${fmtNum(r.score, 2)}</strong>`
        : naCell('점수가 아직 계산되지 않았습니다');

      const rankDeltaHtml = formatRankDeltaHtml(r.rank_change, idx + 1);
      const isExpanded = expandedTeamKey === r.team_key;
      const nameTxt = r.display_name || r.team_key;

      const subItems = [];
      if (isKnownGenre(r.primary_genre)) {
        subItems.push(`<span class="row-genre-wrap"><span class="cell-truncate" title="${escapeHtml(r.primary_genre)}">${escapeHtml(r.primary_genre)}</span>${inferredTag}</span>`);
      }
      if (r.had_outcome) {
        subItems.push(`<span class="muted">${escapeHtml(TERMS.priorOutcome)}</span>`);
      }
      const subRowHtml = (stagePill || subItems.length)
        ? `<div class="muted small row-team-sub">${stagePill}${subItems.join('<span class="row-sub-sep">·</span>')}</div>`
        : '';

      return `
        <tr class="clickable" tabindex="0" data-nav-row="1" data-team-key="${escapeHtml(r.team_key)}">
          <td class="num cand-rank-col"><span class="cand-rank-num">${idx + 1}</span>${rankDeltaHtml}</td>
          <td>
            <div class="row-team-cell">
              <button type="button" class="cand-expand-btn" data-expand-team="${escapeHtml(r.team_key)}" aria-expanded="${isExpanded ? 'true' : 'false'}" aria-label="${escapeHtml(nameTxt)} 미리보기 ${isExpanded ? '접기' : '펼치기'}" title="${isExpanded ? '미리보기 접기' : '미리보기 펼치기'}">${isExpanded ? '▾' : '▸'}</button>
              ${avatarHtml(r.team_key, nameTxt, avatarSize, { shape: 'circle', genre: r.primary_genre })}
              <div class="row-team-text">
                <div class="row-team-name">
                  <span class="cand-mobile-rank">#${idx + 1}</span>
                  <strong class="cell-truncate" title="${escapeHtml(nameTxt)}">${escapeHtml(nameTxt)}</strong>
                  ${dormantPill}${unverifiedPill}
                </div>
                ${subRowHtml}
                <div class="cand-mobile-meta">
                  <span class="cand-mobile-why why-clamp" title="${escapeHtml(whyTxt)}">${escapeHtml(whyTxt)}</span>
                  <div class="cand-mobile-chips">
                    ${rankDeltaHtml}
                    ${hasAct ? act.html : ''}
                    ${r.next_gig_text ? `<span class="next-gig-chip">${escapeHtml(r.next_gig_text)}</span>` : ''}
                  </div>
                </div>
              </div>
            </div>
          </td>
          <td class="nowrap cand-genre-rank-col">${genreRankCell}</td>
          <td class="why-cell" title="${escapeHtml(whyTxt)}"><span class="why-clamp">${whyCellHtml}</span></td>
          <td class="nowrap next-gig-col">${nextGigCell}</td>
          <td class="num nowrap cand-activity-col">${actCellHtml}</td>
          <td class="num cand-score-col">${scoreCellHtml}</td>
          <td class="nowrap cand-listen-col">${renderRowListenControl(r)}</td>
          <td class="nowrap cand-watch-col">${watchButtonHtml(r.team_key, nameTxt, true, true)} ${compareToggleHtml(r.team_key, nameTxt, { variant: 'icon' })}</td>
        </tr>
      `;
    }).join('');

    wireAvatarFallbacks(tbody);

    if (expandedTeamKey) {
      const targetTr = [...tbody.querySelectorAll('tr[data-nav-row]')].find(el => el.dataset.teamKey === expandedTeamKey);
      if (targetTr) openPreviewRow(expandedTeamKey, targetTr);
      else expandedTeamKey = null;
    }

    paintMoreRow(list.length, shown.length);
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
    const r = allRowByKey.get(teamKey);
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
    const whyDetail = r.score !== null && r.score !== undefined ? scorePartsLine(r) : (r.why_line || '—');
    const act = formatRecentActivityCell(r.stage_info);

    const previewTr = document.createElement('tr');
    previewTr.className = 'cand-preview-row';
    previewTr.dataset.previewFor = teamKey;
    previewTr.innerHTML = `
      <td colspan="9" class="cand-preview-cell">
        <div class="cand-preview-box">
          <div class="cand-preview-items">
            <div class="cand-preview-item">
              <span class="cand-preview-lbl">왜 후보인가</span>
              <span class="cand-preview-val">${escapeHtml(whyDetail)}</span>
            </div>
            <div class="cand-preview-item">
              <span class="cand-preview-lbl">최근 활동</span>
              <span class="cand-preview-val">${stageBadgeHtml(r.stage)} ${escapeHtml(act.tooltip)}</span>
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

  paintTable();

  root.querySelector('#btnCandCsv')?.addEventListener('click', () => {
    if (lastCandCsvSpec) triggerTableCsvExport(lastCandCsvSpec);
  });

  const host = root.querySelector('#candFilterBarHost');

  // 프리셋 줄(자주 쓰는 조건 5개 + 내가 담은 조건) · 차트와 겹치는 프리셋 안내 (docs/ux_simplify_2026-11-28.md ③④)
  function paintPresetRow() {
    const presetHost = root.querySelector('#candPresetHost');
    if (presetHost) {
      presetHost.innerHTML = renderPresetRowHtml({
        appState, counts: filterCounts, saved: listSavedFilters(), currentHash: window.location.hash,
      });
    }
    const noteHost = root.querySelector('#candPresetNote');
    if (noteHost) noteHost.innerHTML = presetChartNoteHtml(activePresetOf(appState));
  }

  function renderFilterBar({ focusId = '', caret = null } = {}) {
    if (!host) return;
    const panelHost = host.querySelector('#candPanelHost');
    const barHost = host.querySelector('#candResultsBar');
    if (panelHost) {
      // 접힌 묶음 상태를 다시 그려도 유지
      const closed = [...panelHost.querySelectorAll('details.dp-group:not([open]) > summary')].map(x => x.textContent.trim());
      panelHost.innerHTML = renderCandPanelHtml({ appState, counts: filterCounts });
      panelHost.querySelectorAll('details.dp-group > summary').forEach(sm => {
        if (closed.includes(sm.textContent.trim())) sm.parentElement.removeAttribute('open');
      });
    }
    if (barHost) barHost.innerHTML = renderCandResultsBarHtml({ appState, panelOpen: discoverPanelOpen });
    const panel = host.querySelector('#candPanel');
    if (panel) {
      panel.classList.toggle('is-open', discoverPanelOpen);
      panel.hidden = !discoverPanelOpen;
    }
    host.classList.toggle('is-panel-closed', !discoverPanelOpen);
    paintPresetRow();
    if (focusId) {
      const el = host.querySelector(`#${focusId}`);
      if (el) {
        el.focus();
        if (caret !== null && typeof el.setSelectionRange === 'function') el.setSelectionRange(caret, caret);
      }
    }
  }

  // 표만 다시 그리는 필터(단계·변화·첫 발매·지역·검색)
  const refreshLocal = () => {
    visibleCount = 20;
    syncHash(true);
    renderFilterBar();
    paintTable();
  };
  // 질의를 다시 돌려야 하는 필터(장르·갈래·기간·신인 기준·프리셋 '떠오르는 팀' 등)
  const triggerRecompute = () => {
    syncHash(true);
    window.dispatchEvent(new CustomEvent('app:recompute'));
  };

  const PRESET_STATE = {
    debut12: { candReleaseMonths: 12, candStage: '', candRegion: '' },
    blank: { candReleaseMonths: 0, candStage: '0', candRegion: '' },
    selected: { candReleaseMonths: 0, candStage: '3', candRegion: '' },
    regional: { candReleaseMonths: 0, candStage: '', candRegion: 'non_seoul' },
  };

  function applyPreset(id) {
    const wasRising = appState.candPreset === 'rising';
    const isActive = activePresetOf(appState) === id;
    appState.candReleaseMonths = 0;
    appState.candStage = '';
    appState.candRegion = '';
    appState.candPreset = '';
    if (!isActive) {
      if (id === 'rising') {
        appState.candPreset = 'rising';
      } else if (PRESET_STATE[id]) {
        Object.assign(appState, PRESET_STATE[id]);
      }
    }
    popoverOpen = false;
    const needsQuery = wasRising !== (appState.candPreset === 'rising');
    if (needsQuery) triggerRecompute();
    else refreshLocal();
  }

  function removeFilter(key) {
    const local = {
      rm: () => { appState.candReleaseMonths = 0; },
      region: () => { appState.candRegion = ''; },
      city: () => { appState.candCity = ''; },
      tier: () => { appState.candTier = ''; },
      ginf: () => { appState.candGenreInf = ''; },
      stage: () => { appState.candStage = ''; },
      move: () => { appState.candMove = ''; },
      query: () => { appState.candQuery = ''; },
    };
    const recompute = {
      preset: () => { appState.candPreset = ''; },
      genre: () => { appState.cfg.genre = ''; },
      branches: () => { appState.cfg.branches = [...ALL_BRANCHES]; },
      period: () => { appState.cfg.period_days = 0; },
      newcomer_years: () => { appState.cfg.newcomer_years = 3; },
      exclude_famous: () => { appState.cfg.exclude_famous = true; },
      only_no_outcome: () => { appState.cfg.only_no_outcome = true; },
    };
    if (local[key]) {
      local[key]();
      refreshLocal();
    } else if (recompute[key]) {
      recompute[key]();
      triggerRecompute();
    }
  }

  function toggleBranch(b) {
    const cur = new Set(appState.cfg.branches);
    if (cur.has(b)) {
      if (cur.size <= 1) return;
      cur.delete(b);
    } else {
      cur.add(b);
    }
    appState.cfg.branches = ALL_BRANCHES.filter(x => cur.has(x));
    triggerRecompute();
  }

  host?.addEventListener('click', (e) => {
    if (e.target.closest('.cd-infotip')) return;
    const t = e.target.closest('button');
    if (!t || !host.contains(t)) return;
    const d = t.dataset;
    if (d.candPreset) return applyPreset(d.candPreset);
    if (d.candView !== undefined) {
      appState.candView = d.candView === 'heat' ? 'heat' : '';
      return refreshLocal();
    }
    if (d.removeFilter) return removeFilter(d.removeFilter);
    if (d.setGenre !== undefined) {
      appState.cfg.genre = d.setGenre || '';
      popoverOpen = false;
      return triggerRecompute();
    }
    if (d.setRm !== undefined) {
      appState.candReleaseMonths = Number(d.setRm) || 0;
      return refreshLocal();
    }
    if (d.setTier !== undefined) {
      appState.candTier = ['S', 'M', 'L'].includes(d.setTier) ? d.setTier : '';
      return refreshLocal();
    }
    if (t.id === 'candPanelClose') {
      discoverPanelOpen = false;
      renderFilterBar();
      host.querySelector('#candMobileFilterToggle')?.focus();
      return undefined;
    }
    if (d.setRegion !== undefined) {
      appState.candRegion = d.setRegion || '';
      return refreshLocal();
    }
    if (d.stageChip !== undefined) {
      appState.candStage = (appState.candStage === d.stageChip) ? '' : d.stageChip;
      return refreshLocal();
    }
    if (d.moveChip !== undefined) {
      appState.candMove = (appState.candMove === d.moveChip) ? '' : d.moveChip;
      return refreshLocal();
    }
    if (d.branchChip) return toggleBranch(d.branchChip);
    if (t.id === 'candFilterCountBtn' || t.id === 'candAddFilterBtn') {
      popoverOpen = !popoverOpen;
      return renderFilterBar();
    }
    if (t.id === 'candCloseFilterPop') {
      popoverOpen = false;
      return renderFilterBar();
    }
    if (t.id === 'candMobileFilterToggle') {
      discoverPanelOpen = !discoverPanelOpen;
      return renderFilterBar({ focusId: 'candMobileFilterToggle' });
    }
    return undefined;
  });

  let candQueryHashTimer = null;
  host?.addEventListener('input', (e) => {
    const inp = e.target;
    if (inp.id !== 'candFilterInput' && inp.id !== 'candFilterInputMobile') return;
    appState.candQuery = inp.value;
    visibleCount = 20;
    paintTable();
    clearTimeout(candQueryHashTimer);
    candQueryHashTimer = setTimeout(() => {
      syncHash(true);
      if (!inp.isConnected) return;
      renderFilterBar({ focusId: inp.id, caret: inp.selectionStart });
    }, 400);
  });

  host?.addEventListener('change', (e) => {
    const el = e.target;
    if (el.id === 'candNewcomerInp') {
      appState.cfg.newcomer_years = Math.max(1, Math.min(15, Math.round(Number(el.value) || 3)));
    } else if (el.id === 'candExcludeFamous') {
      appState.cfg.exclude_famous = el.checked;
    } else if (el.id === 'candOnlyNoOutcome') {
      appState.cfg.only_no_outcome = el.checked;
    } else if (el.id === 'candLimitSel') {
      appState.cfg.limit = Number(el.value) || 100;
    } else if (el.id === 'candCitySel') {
      appState.candCity = el.value || '';
      refreshLocal();
      return;
    } else if (el.id === 'candGenreInfChk') {
      appState.candGenreInf = el.checked ? '' : 'exclude';
      refreshLocal();
      return;
    } else if (el.id === 'candPeriodSel') {
      appState.cfg.period_days = Number(el.value) || 0;
    } else {
      return;
    }
    triggerRecompute();
  });

  // 묶음 메뉴: 바깥 클릭·Esc 로 닫기 (다시 그릴 때 이전 듣기를 끊는다)
  if (candDocListeners) candDocListeners.abort();
  candDocListeners = new AbortController();
  const docOpts = { signal: candDocListeners.signal };
  document.addEventListener('click', (e) => {
    if (!popoverOpen || !host?.isConnected) return;
    if (e.target.closest('.cf-add-wrap')) return;
    popoverOpen = false;
    renderFilterBar();
  }, docOpts);
  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape' || !popoverOpen || !host?.isConnected) return;
    popoverOpen = false;
    renderFilterBar({ focusId: 'candAddFilterBtn' });
  }, docOpts);

  root.querySelectorAll('[data-density]').forEach(btn => {
    btn.addEventListener('click', () => {
      const next = btn.dataset.density;
      if (next === density) return;
      density = next;
      setTableDensity(next);
      const table = root.querySelector('#candTable');
      table?.classList.remove('is-density-compact', 'is-density-comfortable');
      table?.classList.add(`is-density-${next}`);
      root.querySelectorAll('[data-density]').forEach(b => {
        const on = b.dataset.density === next;
        b.classList.toggle('is-active', on);
        b.setAttribute('aria-pressed', on ? 'true' : 'false');
      });
      paintTable();
    });
  });

  renderFilterBar();
  wireSavedRow(root.querySelector('#candSavedHost'), { onChange: paintPresetRow });
  root.querySelector('#candPresetHost')?.addEventListener('click', (e) => {
    if (e.target.closest('.cd-infotip')) return;
    const b = e.target.closest('button');
    if (!b) return;
    if (b.dataset.candPreset) {
      applyPreset(b.dataset.candPreset);
      return;
    }
    if (b.dataset.savedApply) {
      const it = listSavedFilters().find(x => x.id === b.dataset.savedApply);
      if (it) applySavedFilter(it);
    }
  });
  root.querySelector('#candAdvancedChk')?.addEventListener('change', (e) => {
    discoverAdvanced = e.target.checked;
    root.querySelector('#candTable')?.classList.toggle('is-advanced', discoverAdvanced);
  });

  const heatHostEl = root.querySelector('#candHeatHost');
  const onHeatActivate = (target) => {
    if (target.closest('.cd-infotip') || target.closest('.cd-na-cell')) return;
    const th = target.closest('th[data-heat-sort]');
    if (th) {
      heatSort = nextHeatSort(heatSort, th.dataset.heatSort);
      paintTable();
      heatHostEl.querySelector(`th[data-heat-sort="${th.dataset.heatSort}"]`)?.focus();
      return;
    }
    const tr = target.closest('tr[data-team-key]');
    if (tr) openPeekFor(tr.dataset.teamKey);
  };
  heatHostEl?.addEventListener('click', (e) => onHeatActivate(e.target));
  heatHostEl?.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    if (!e.target.matches('th[data-heat-sort], tr[data-team-key]')) return;
    e.preventDefault();
    onHeatActivate(e.target);
  });

  root.querySelectorAll('th.sortable').forEach(th => {
    th.setAttribute('tabindex', '0');
    const onSort = () => {
      const col = th.dataset.sort;
      if (appState.candSort.col === col) {
        appState.candSort.dir = appState.candSort.dir === 'desc' ? 'asc' : 'desc';
      } else {
        appState.candSort.col = col;
        appState.candSort.dir = (col === 'display_name' || col === 'next_gig_sort' || col === 'genre_rank') ? 'asc' : 'desc';
      }
      syncHash(true);
      paintTable();
    };
    th.addEventListener('click', e => {
      if (e.target.closest('.cd-infotip')) return;
      onSort();
    });
    th.addEventListener('keydown', e => {
      if (e.target.closest('.cd-infotip')) return;
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
      const tr = expandBtn.closest('tr[data-nav-row]');
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
    const tr = e.target.closest('tr[data-nav-row]');
    if (tr && tr.dataset.teamKey) {
      openPeekFor(tr.dataset.teamKey);
    }
  });

  wireTableKeyboardNav(tbodyEl, {
    onActivate: (tr) => {
      if (tr.dataset.teamKey) openPeekFor(tr.dataset.teamKey);
    },
    onToggleExpand: (tr, key) => {
      const tk = tr.dataset.teamKey;
      if (!tk) return;
      if (key === 'ArrowLeft') {
        if (expandedTeamKey === tk) {
          expandedTeamKey = null;
          closePreviewRows();
        }
      } else if (expandedTeamKey !== tk) {
        expandedTeamKey = tk;
        openPreviewRow(tk, tr);
      }
    },
  });

  wireTableRowHoverPreview(tbodyEl, (tr) => {
    const r = allRowByKey.get(tr.dataset.teamKey);
    if (!r) return '';
    const metaParts = [r.primary_genre || '장르 미분류'];
    if (r.stage_label) metaParts.push(r.stage_label);
    if (r.last_seen) metaParts.push(`최근 신호 ${r.last_seen}`);
    const nextTxt = r.next_gig_text
      ? `${r.next_gig_text}${r.next_gig?.count > 1 ? ` 외 ${r.next_gig.count - 1}건` : ''}`
      : '예정 공연 없음';
    const act = formatRecentActivityCell(r.stage_info);
    return `
      <div class="rhp-head">
        <strong>${escapeHtml(r.display_name || r.team_key)}</strong>
        <span class="rhp-score">${r.score !== null && r.score !== undefined ? `${fmtNum(r.score, 2)}점` : '—'}</span>
      </div>
      <div class="rhp-meta">${escapeHtml(metaParts.join(' · '))}</div>
      <div class="rhp-lines">
        <div class="rhp-line"><span class="rhp-lbl">점수 근거</span>${escapeHtml((r.score !== null && r.score !== undefined ? scorePartsLine(r) : '') || r.why_line || '—')}</div>
        <div class="rhp-line"><span class="rhp-lbl">최근 활동</span>${escapeHtml(act.tooltip)}</div>
        <div class="rhp-line"><span class="rhp-lbl">다음 공연</span>${escapeHtml(nextTxt)}</div>
      </div>
      <div class="rhp-foot">클릭·Enter로 오른쪽 미리보기 · →로 표 안에서 펼치기</div>
    `;
  });
  // 줄을 누르거나 Enter → 오른쪽 미리보기(▸ 펼침은 그대로), 주소의 ?peek= 도 연다
  const openPeekFor = attachTeamPeek(root, { initialKey: appState.candTab === 'debut' ? '' : initialPeek });
}
