import {
  appState, cloneDefaults, destroyActiveCharts, exportTableToCsv,
  getWatchlist, hasCustomWeights, navigateTo, parseHash,
  setExportContext, syncHash, toggleWatch,
} from './state.js';
import {
  bootstrapData, computeDataHealth, getSnapshotDiff,
  queryCandidates, queryWeeklyDigestExtras,
} from './db.js';
import {
  avatarHtml, buildWeeklySummaryText, cssVar, escapeHtml,
  fmtInt, friendlySqlError, renderViewSkeleton, wireAvatarFallbacks,
} from './ui.js';
import { renderTodayView } from './views/today.js';
import { renderCandidatesView } from './views/candidates.js';
import { renderTeamView } from './views/team.js';
import { renderWatchlistView } from './views/watchlist.js';
import { renderVerifyView } from './views/verify.js';
import { renderVenuesView } from './views/venues.js';
import { renderQualityView } from './views/quality.js';
import { renderSqlView } from './views/sql.js';

const ADVANCED_ROUTES = new Set(['verify', 'backtest', 'signals', 'evidence', 'scorecard', 'quality', 'sql']);

let renderSeq = 0;
let toastTimer = null;

function showToast(msg) {
  const el = document.getElementById('appToast');
  if (!el) return;
  el.textContent = msg;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, 2200);
}

function setStatus(text, busy = false) {
  const el = document.getElementById('topStatus');
  if (!el) return;
  el.textContent = text;
  el.classList.toggle('busy', busy);
}

function setGlobalError(msg) {
  const el = document.getElementById('globalError');
  if (!el) return;
  if (!msg) {
    el.hidden = true;
    el.textContent = '';
  } else {
    el.hidden = false;
    el.textContent = msg;
  }
}

function renderAnomalyBanner() {
  const el = document.getElementById('dataAnomalyBanner');
  const health = appState.dataHealth;
  if (!el || !health || health.ok || !health.issues.length) {
    if (el) {
      el.hidden = true;
      el.innerHTML = '';
    }
    return;
  }
  const summary = health.issues.map(i => i.message).join(' · ');
  el.className = `anomaly-banner ${health.severity === 'error' ? 'is-error' : 'is-warn'}`;
  el.innerHTML = `
    <div class="anomaly-banner-text">
      <strong>데이터 수집 확인 필요</strong>
      <span>${escapeHtml(summary)}</span>
    </div>
    <a class="btn btn-sm" href="#/quality">수집 현황 보기</a>
  `;
  el.hidden = false;
}

function setAdvancedNavOpen(open) {
  const list = document.getElementById('navAdvList');
  const toggle = document.getElementById('navAdvToggle');
  if (!list || !toggle) return;
  list.hidden = !open;
  toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
  toggle.classList.toggle('is-open', open);
}

function updateNavActive() {
  const route = appState.route;
  document.querySelectorAll('.nav-link[data-route]').forEach(a => {
    const active = a.dataset.route === route;
    a.classList.toggle('active', active);
    if (active) a.setAttribute('aria-current', 'page');
    else a.removeAttribute('aria-current');
  });

  if (ADVANCED_ROUTES.has(route)) {
    setAdvancedNavOpen(true);
  }

  const wc = document.getElementById('navWatchCount');
  if (wc) {
    const n = getWatchlist().length;
    wc.textContent = n > 0 ? String(n) : '';
  }

  const customW = hasCustomWeights();
  const hasIssue = !appState.dataHealth.ok;

  const weightBadge = document.getElementById('navWeightBadge');
  if (weightBadge) weightBadge.textContent = customW ? '수정됨' : '';

  const healthBadge = document.getElementById('navHealthBadge');
  if (healthBadge) healthBadge.textContent = hasIssue ? '확인' : '';

  const advBadge = document.getElementById('navAdvBadge');
  if (advBadge) {
    advBadge.textContent = hasIssue ? '!' : (customW ? '수정' : '');
  }
}

function updateExportMenuUI() {
  const lbl = document.getElementById('exportCsvLabel');
  if (!lbl) return;
  lbl.textContent = appState.exportCtx.csvLabel || '지금 보는 표 CSV 내려받기';
}

function closeMobileNav() {
  document.getElementById('navRail')?.classList.remove('open');
  document.getElementById('navBackdrop')?.classList.remove('open');
  document.getElementById('mobileMenuBtn')?.setAttribute('aria-expanded', 'false');
}

function resetAllFiltersAndWeights() {
  appState.cfg = cloneDefaults();
  appState.cfg.as_of = appState.dataEnd;
  syncHash(true);
  renderCurrentView();
}

// ---------- Autocomplete Team Search (with 24px Avatars) ----------

function initTeamSearch() {
  const inp = document.getElementById('gfTeamSearch');
  const drop = document.getElementById('gfTeamDrop');
  if (!inp || !drop) return;

  function renderDrop() {
    const q = inp.value.trim().toLowerCase();
    if (!q || !appState.teamIndex.length) {
      drop.hidden = true;
      drop.innerHTML = '';
      return;
    }
    const matches = [];
    for (const t of appState.teamIndex) {
      const dn = String(t.display_name || '').toLowerCase();
      const tk = String(t.team_key || '').toLowerCase();
      if (dn.includes(q) || tk.includes(q)) {
        matches.push({ t, exact: dn.startsWith(q) || tk.startsWith(q) ? 0 : 1 });
        if (matches.length >= 40) break;
      }
    }
    matches.sort((a, b) => a.exact - b.exact);
    const top = matches.slice(0, 10);
    if (!top.length) {
      drop.innerHTML = '<div class="small muted" style="padding:10px 12px;">일치하는 팀이 없습니다.</div>';
      drop.hidden = false;
      return;
    }
    drop.innerHTML = top.map(({ t }) => `
      <button type="button" class="f-search-opt" data-pick-team="${escapeHtml(t.team_key)}">
        <span class="f-search-opt-left">
          ${avatarHtml(t.team_key, t.display_name || t.team_key, 24, { shape: 'circle', genre: t.primary_genre })}
          <strong>${escapeHtml(t.display_name || t.team_key)}</strong>
        </span>
        <span class="small muted">${escapeHtml(t.primary_genre || '')}</span>
      </button>
    `).join('');
    wireAvatarFallbacks(drop);
    drop.hidden = false;
  }

  inp.addEventListener('input', renderDrop);
  inp.addEventListener('focus', renderDrop);
  inp.addEventListener('keydown', e => {
    if (e.key === 'Enter') {
      const first = drop.querySelector('[data-pick-team]');
      if (first) {
        e.preventDefault();
        const key = first.dataset.pickTeam;
        drop.hidden = true;
        inp.value = '';
        navigateTo('team', key);
      }
    } else if (e.key === 'Escape') {
      drop.hidden = true;
    }
  });

  drop.addEventListener('click', e => {
    const btn = e.target.closest('[data-pick-team]');
    if (!btn) return;
    const key = btn.dataset.pickTeam;
    drop.hidden = true;
    inp.value = '';
    navigateTo('team', key);
  });

  document.addEventListener('click', e => {
    if (!e.target.closest('.f-search-wrap')) drop.hidden = true;
  });
}

// ---------- Unified Export Menu ----------

function initExportMenu() {
  const wrap = document.getElementById('exportMenuWrap');
  const btn = document.getElementById('btnExportMenu');
  const drop = document.getElementById('exportDrop');
  if (!wrap || !btn || !drop) return;

  const setOpen = (open) => {
    drop.hidden = !open;
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    wrap.classList.toggle('open', open);
  };

  btn.addEventListener('click', (e) => {
    e.stopPropagation();
    setOpen(drop.hidden);
  });

  document.addEventListener('click', (e) => {
    if (!wrap.contains(e.target)) setOpen(false);
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !drop.hidden) {
      setOpen(false);
      btn.focus();
    }
  });

  drop.addEventListener('click', async (e) => {
    const opt = e.target.closest('[data-export-action]');
    if (!opt) return;
    const action = opt.dataset.exportAction;
    setOpen(false);

    if (action === 'link') {
      syncHash(true);
      try {
        await navigator.clipboard.writeText(window.location.href);
        showToast('현재 화면 링크를 복사했습니다.');
      } catch (_) {
        window.prompt('아래 링크를 복사하세요:', window.location.href);
      }
      return;
    }

    if (action === 'digest') {
      let text = appState.weeklyDigestText;
      if (!text && appState.ready) {
        const candRows = await queryCandidates({ limit: 300 });
        const diff = getSnapshotDiff(candRows);
        const extras = await queryWeeklyDigestExtras(candRows);
        text = buildWeeklySummaryText({
          dataEnd: appState.dataEnd,
          prevDate: diff.prevDate,
          latestDate: diff.latestDate,
          newEntrants: diff.newEntrants,
          risers: diff.risers,
          signalStats: extras.signalStats,
          newVideos7d: extras.newVideos7d,
          top5: candRows.slice(0, 5),
          health: appState.dataHealth,
        });
        appState.weeklyDigestText = text;
      }
      if (!text) return;
      try {
        await navigator.clipboard.writeText(text);
        showToast('주간 브리핑 문장을 복사했습니다.');
      } catch (_) {
        window.prompt('주간 브리핑 문장:', text);
      }
      return;
    }

    if (action === 'csv') {
      const ctx = appState.exportCtx;
      if (ctx.csvHeaders.length && ctx.csvRows.length) {
        exportTableToCsv(ctx.csvFilename || `crate_digger_${appState.dataEnd}.csv`, ctx.csvHeaders, ctx.csvRows);
        showToast('CSV 파일을 내려받았습니다.');
      } else if (appState.ready) {
        const candRows = await queryCandidates({ limit: 100 });
        exportTableToCsv(
          `crate_digger_top100_${appState.dataEnd || 'export'}.csv`,
          ['rank', 'team_key', 'display_name', 'genre', 'score', 'n_branch', 'last_seen'],
          candRows.map((r, i) => [i + 1, r.team_key, r.display_name || r.team_key, r.primary_genre || '', r.score ?? '', r.n_branch ?? 0, r.last_seen || ''])
        );
        showToast('상위 후보 100팀 CSV를 내려받았습니다.');
      }
    }
  });
}

// ---------- Theme (White / Black / System) ----------

const THEME_STORAGE_KEY = 'crate_digger_theme';
const VALID_THEME_PREFS = ['light', 'dark', 'system'];

function syncChartThemeDefaults() {
  if (!window.Chart) return;
  const ink = cssVar('--ink');
  const inkMuted = cssVar('--ink-muted');
  const line = cssVar('--line');
  const surface = cssVar('--surface');
  window.Chart.defaults.color = inkMuted || ink;
  window.Chart.defaults.borderColor = line;
  if (window.Chart.defaults.plugins?.tooltip) {
    window.Chart.defaults.plugins.tooltip.backgroundColor = surface;
    window.Chart.defaults.plugins.tooltip.titleColor = ink;
    window.Chart.defaults.plugins.tooltip.bodyColor = ink;
    window.Chart.defaults.plugins.tooltip.borderColor = line;
    window.Chart.defaults.plugins.tooltip.borderWidth = 1;
  }
}

function resolveTheme(pref) {
  if (pref === 'light' || pref === 'dark') return pref;
  const preferDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  return preferDark ? 'dark' : 'light';
}

function applyThemePreference(pref, rerender = false) {
  const cleanPref = VALID_THEME_PREFS.includes(pref) ? pref : 'system';
  const resolved = resolveTheme(cleanPref);
  document.documentElement.dataset.themePref = cleanPref;
  document.documentElement.dataset.theme = resolved;

  document.querySelectorAll('#themeSwitch .theme-seg[data-theme-pref]').forEach(btn => {
    const on = btn.dataset.themePref === cleanPref;
    btn.classList.toggle('active', on);
    btn.setAttribute('aria-checked', on ? 'true' : 'false');
  });

  syncChartThemeDefaults();
  if (rerender && appState.ready) renderCurrentView();
}

function initTheme() {
  let saved = 'system';
  try {
    const raw = window.localStorage.getItem(THEME_STORAGE_KEY);
    if (VALID_THEME_PREFS.includes(raw)) saved = raw;
  } catch (_) {}
  applyThemePreference(saved, false);

  document.getElementById('themeSwitch')?.addEventListener('click', e => {
    const btn = e.target.closest('.theme-seg[data-theme-pref]');
    if (!btn) return;
    const nextPref = btn.dataset.themePref;
    try { window.localStorage.setItem(THEME_STORAGE_KEY, nextPref); } catch (_) {}
    applyThemePreference(nextPref, true);
  });

  if (window.matchMedia) {
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const onSystemChange = () => {
      if (document.documentElement.dataset.themePref === 'system') {
        applyThemePreference('system', true);
      }
    };
    if (mq.addEventListener) mq.addEventListener('change', onSystemChange);
    else if (mq.addListener) mq.addListener(onSystemChange);
  }
}

// ---------- View Dispatcher ----------

async function renderCurrentView() {
  if (!appState.ready) return;
  const seq = ++renderSeq;
  const root = document.getElementById('viewRoot');
  setGlobalError('');
  setExportContext({ csvLabel: '', csvFilename: '', csvHeaders: [], csvRows: [] });
  updateNavActive();
  renderAnomalyBanner();
  closeMobileNav();

  if (!appState.cfg.branches.length) {
    setGlobalError('갈래(공연·선정·지원·발매·큐레이션)를 최소 1개 이상 선택해 주세요.');
    setStatus('필터 확인 필요', false);
    return;
  }

  destroyActiveCharts();
  syncChartThemeDefaults();
  setStatus('계산 중...', true);

  const skelTimer = setTimeout(() => {
    if (seq === renderSeq && root) {
      root.innerHTML = renderViewSkeleton();
    }
  }, 90);

  try {
    const r = appState.route;
    if (r === 'today') await renderTodayView(root);
    else if (r === 'candidates') await renderCandidatesView(root);
    else if (r === 'team') await renderTeamView(root, appState.routeParam);
    else if (r === 'watchlist') await renderWatchlistView(root);
    else if (r === 'verify' || r === 'backtest' || r === 'signals' || r === 'evidence' || r === 'scorecard') await renderVerifyView(root);
    else if (r === 'venues') await renderVenuesView(root);
    else if (r === 'quality') await renderQualityView(root);
    else if (r === 'sql') await renderSqlView(root);
    else await renderTodayView(root);

    clearTimeout(skelTimer);
    if (seq !== renderSeq) return;
    const healthTxt = appState.dataHealth.ok
      ? appState.dataHealth.summaryLabel
      : `⚠ ${appState.dataHealth.summaryLabel}`;
    setStatus(`기준 ${appState.dataEnd} · ${healthTxt}`, false);
  } catch (err) {
    clearTimeout(skelTimer);
    if (seq !== renderSeq) return;
    console.error(err);
    setGlobalError(`화면을 불러오는 중 오류가 발생했습니다: ${friendlySqlError(err)}`);
    setStatus('오류 발생', false);
  }
}

// ---------- Event Wiring ----------

function wireGlobalEvents() {
  const mobileBtn = document.getElementById('mobileMenuBtn');
  mobileBtn?.addEventListener('click', () => {
    const rail = document.getElementById('navRail');
    const open = !rail?.classList.contains('open');
    rail?.classList.toggle('open', open);
    document.getElementById('navBackdrop')?.classList.toggle('open', open);
    mobileBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
  });
  document.getElementById('navBackdrop')?.addEventListener('click', closeMobileNav);

  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeMobileNav();
  });

  // Collapsible Advanced sidebar group
  const advToggle = document.getElementById('navAdvToggle');
  const advList = document.getElementById('navAdvList');
  advToggle?.addEventListener('click', () => {
    if (!advList) return;
    setAdvancedNavOpen(advList.hidden);
  });

  // Left nav links keep current query params
  document.querySelectorAll('.nav-link[data-route]').forEach(a => {
    a.addEventListener('click', e => {
      e.preventDefault();
      navigateTo(a.dataset.route, '');
    });
  });

  // Any reset-filters button
  document.addEventListener('click', e => {
    if (e.target.closest('[data-action="reset-filters"]')) {
      resetAllFiltersAndWeights();
    }
  });

  // Delegated watch button click inside any view
  document.getElementById('viewRoot')?.addEventListener('click', e => {
    const btn = e.target.closest('button[data-watch-key]');
    if (!btn) return;
    e.stopPropagation();
    const added = toggleWatch(btn.dataset.watchKey, btn.dataset.watchName);
    btn.classList.toggle('btn-active', added);
    const fullLbl = btn.querySelector('.watch-lbl-full');
    const shortLbl = btn.querySelector('.watch-lbl-short');
    if (fullLbl || shortLbl) {
      if (fullLbl) fullLbl.textContent = added ? '관심 중' : '관심 추가';
      if (shortLbl) shortLbl.textContent = added ? '★' : '☆';
      btn.setAttribute('aria-label', `${btn.dataset.watchName || ''} ${added ? '관심 중' : '관심 추가'}`.trim());
    } else {
      btn.textContent = added ? '★ 관심 중' : '☆ 관심 추가';
    }
    updateNavActive();
    if (appState.route === 'today') renderCurrentView();
  });

  window.addEventListener('hashchange', () => {
    parseHash();
    renderCurrentView();
  });

  window.addEventListener('app:route', () => {
    renderCurrentView();
  });

  window.addEventListener('app:recompute', () => {
    renderCurrentView();
  });

  window.addEventListener('app:watchlist', updateNavActive);
  window.addEventListener('app:export-ctx', updateExportMenuUI);

  // Allow live health recomputation (also helpful for automated verification)
  window.addEventListener('app:refresh-health', () => {
    appState.dataHealth = computeDataHealth();
    renderAnomalyBanner();
    updateNavActive();
  });
}

// ---------- Boot ----------

async function boot() {
  initTheme();
  initTeamSearch();
  initExportMenu();
  wireGlobalEvents();
  parseHash();
  updateNavActive();

  try {
    await bootstrapData(msg => setStatus(msg, true));

    if (!window.location.hash.includes('as_of=')) {
      appState.cfg.as_of = appState.dataEnd;
    }
    parseHash();

    const r = appState.meta?.rows || {};
    const footMeta = document.getElementById('navDataMeta');
    if (footMeta) {
      footMeta.textContent = `기준 ${appState.dataEnd} · 신호 ${fmtInt(r.signals)} · 팀 ${fmtInt(r.teams)}`;
    }

    await renderCurrentView();
  } catch (err) {
    console.error(err);
    setStatus('초기화 실패', false);
    setGlobalError(`앱을 초기화하지 못했습니다: ${friendlySqlError(err)}. 로컬 서버(http://) 또는 GitHub Pages에서 열어 주세요.`);
  }
}

boot();
