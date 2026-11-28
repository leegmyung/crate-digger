import {
  appState, cloneDefaults, destroyActiveCharts, exportTableToCsv,
  getWatchlist, hasCustomWeights, navigateTo, parseHash,
  resetViewFilters, setExportContext, syncHash, toggleWatch,
} from './state.js';
import {
  bootstrapData, computeDataHealth, fetchText, getSnapshotDiff,
  loadAlertsJson, loadSourceReview, queryCandidates, queryWeeklyDigestExtras,
} from './db.js';
import { applyKeyAliases, parseAliasCsv, remapHash } from './key_aliases.js';
import {
  buildWeeklySummaryText, cssVar, escapeHtml,
  fmtInt, friendlySqlError, getWatchlistAlerts, hideRowHoverPreview,
  renderViewSkeleton, WATCH_LABELS,
} from './ui.js';
import { initGlobalSearch } from './components/global_search.js';
import { initMiniPlayer } from './components/mini_player.js';
import { initCompareTray } from './components/compare_tray.js';
import { initChartPng } from './chart_png.js';

const ADVANCED_ROUTES = new Set(['verify', 'backtest', 'signals', 'evidence', 'scorecard', 'quality', 'sql']);

const VIEW_LOADERS = {
  today: () => import('./views/today.js').then(m => m.renderTodayView),
  candidates: () => import('./views/candidates.js').then(m => m.renderCandidatesView),
  team: () => import('./views/team.js').then(m => m.renderTeamView),
  watchlist: () => import('./views/watchlist.js').then(m => m.renderWatchlistView),
  verify: () => import('./views/verify.js').then(m => m.renderVerifyView),
  venues: () => import('./views/venues.js').then(m => m.renderVenuesView),
  venue: () => import('./views/venue.js').then(m => m.renderVenueView),
  quality: () => import('./views/quality.js').then(m => m.renderQualityView),
  sql: () => import('./views/sql.js').then(m => m.renderSqlView),
  // 정보 구조 v2: 아직 화면이 없는 새 주소 (묶음 F·G·B에서 진짜 화면으로 교체)
  charts: () => import('./views/charts.js').then(m => m.renderChartsView),   // 묶음 F
  alerts: () => import('./views/alerts.js').then(m => m.renderAlertsView),
  search: () => import('./views/search.js').then(m => m.renderSearchView),
  help: () => import('./views/help.js').then(m => m.renderHelpView),
  compare: () => import('./views/compare.js').then(m => m.renderCompareView),
};

// 왼쪽 메뉴 키(data-route) — 안쪽 경로 이름과 다를 수 있음 (docs/app_structure_v2.md 2-1)
const NAV_TARGETS = {
  home: () => ({ route: 'today' }),
  discover: () => { appState.candTab = 'all'; return { route: 'candidates' }; },
  charts: () => { appState.chartKind = 'all'; appState.chartParam = ''; return { route: 'charts' }; },
  venues: () => { appState.venuesTab = 'overview'; return { route: 'venues' }; },
  cities: () => { appState.venuesTab = 'city'; return { route: 'venues' }; },
  festivals: () => { appState.venuesTab = 'festival'; appState.festivalName = ''; return { route: 'venues' }; },
  alerts: () => ({ route: 'alerts' }),
  mine: () => { appState.mineTab = 'watch'; return { route: 'watchlist' }; },
  verify: () => ({ route: 'verify' }),
  quality: () => ({ route: 'quality' }),
  sql: () => ({ route: 'sql' }),
};

/** 지금 화면이 왼쪽 메뉴의 어느 칸인가. 팀 상세는 메뉴에 없음. */
function currentNavKey() {
  const r = appState.route;
  if (r === 'today') return 'home';
  if (r === 'candidates') return appState.candTab === 'debut' ? 'charts' : 'discover';
  if (r === 'charts') return 'charts';
  if (r === 'venues') {
    if (appState.venuesTab === 'city') return 'cities';
    if (appState.venuesTab === 'festival') return 'festivals';
    return 'venues';
  }
  if (r === 'venue') return 'venues';
  if (r === 'watchlist') return 'mine';
  if (r === 'alerts') return 'alerts';
  if (r === 'quality' || r === 'sql') return r;
  if (ADVANCED_ROUTES.has(r)) return 'verify';
  return '';
}
const loadedViews = new Map();

function resolveRouteKey(r) {
  if (r === 'backtest' || r === 'signals' || r === 'evidence' || r === 'scorecard') return 'verify';
  return VIEW_LOADERS[r] ? r : 'today';
}

async function loadViewRenderer(route) {
  const key = resolveRouteKey(route);
  if (loadedViews.has(key)) return loadedViews.get(key);
  const fn = await VIEW_LOADERS[key]();
  loadedViews.set(key, fn);
  return fn;
}

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

function setGlobalError(msg, rawErr = null) {
  const el = document.getElementById('globalError');
  if (!el) return;
  if (!msg) {
    el.hidden = true;
    el.innerHTML = '';
    return;
  }
  const rawText = rawErr
    ? String(rawErr?.stack || rawErr?.message || rawErr).trim()
    : '';
  el.hidden = false;
  el.innerHTML = `
    <div class="global-err-body">
      <p class="global-err-msg">${escapeHtml(msg)}</p>
      <div class="global-err-actions">
        <button type="button" class="btn btn-sm btn-primary" data-action="retry-view">다시 불러오기</button>
        <a class="btn btn-sm" href="#/verify/quality">데이터 수집·품질 보기</a>
      </div>
      ${rawText ? `
        <details class="global-err-details">
          <summary>기술 오류 원문 보기</summary>
          <pre>${escapeHtml(rawText)}</pre>
        </details>
      ` : ''}
    </div>
  `;
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
    <a class="btn btn-sm" href="#/verify/quality">수집 현황 보기</a>
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
  const navRoute = currentNavKey();
  document.querySelectorAll('.nav-link[data-route]').forEach(a => {
    const active = a.dataset.route === navRoute;
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

  const reviewSuggestions = Array.isArray(appState.sourceReviewJson?.suggestions)
    ? appState.sourceReviewJson.suggestions
    : [];
  const reviewDot = document.getElementById('navReviewDot');
  if (reviewDot) {
    const hasReview = reviewSuggestions.length > 0;
    reviewDot.hidden = !hasReview;
    if (hasReview) {
      const tip = `출처 재분류 검토 제안 ${reviewSuggestions.length}건`;
      reviewDot.title = tip;
      reviewDot.setAttribute('aria-label', tip);
    }
  }

  const alertBadge = document.getElementById('topWatchAlertsBadge');
  if (alertBadge) {
    const wAlerts = getWatchlistAlerts(appState.alertsJson, getWatchlist());
    if (wAlerts.length > 0) {
      alertBadge.hidden = false;
      alertBadge.textContent = `관심 알림 ${fmtInt(wAlerts.length)}`;
      const tip = `관심 팀의 최근 알림 ${fmtInt(wAlerts.length)}건 (새 공연 포함) — 알림 센터에서 보기`;
      alertBadge.title = tip;
      alertBadge.setAttribute('aria-label', tip);
    } else {
      alertBadge.hidden = true;
      alertBadge.textContent = '';
    }
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
  resetViewFilters();
  syncHash(true);
  renderCurrentView();
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

/**
 * 화면 폭 종류(넓은 화면 정리): 표·목록 화면은 넓게, 읽는 화면은 적당히 (css/shell.css body[data-layout]).
 * table = 발굴·차트·공연장 목록·씬·검증 표·SQL·데이터 품질 / read = 홈·팀·공연장·도시·페스티벌·알림·내 목록·검색
 */
function layoutKind() {
  const r = appState.route;
  if (r === 'candidates' || r === 'charts' || r === 'sql' || r === 'quality') return 'table';
  if (r === 'verify') return 'table';
  if (r === 'venues' && appState.venuesTab !== 'city' && appState.venuesTab !== 'festival') return 'table';
  if (r === 'venues' && !appState.venuesCity && !appState.festivalName) return 'table';   // 도시·페스티벌 목록
  return 'read';
}

async function renderCurrentView() {
  if (!appState.ready) return;
  const seq = ++renderSeq;
  const root = document.getElementById('viewRoot');
  setGlobalError('');
  setExportContext({ csvLabel: '', csvFilename: '', csvHeaders: [], csvRows: [] });
  updateNavActive();
  renderAnomalyBanner();
  closeMobileNav();
  hideRowHoverPreview();
  document.body.dataset.layout = layoutKind();

  if (!appState.cfg.branches.length) {
    setGlobalError('갈래(공연·선정·지원·발매·큐레이션)를 최소 1개 이상 선택해 주세요.');
    setStatus('필터 확인 필요', false);
    return;
  }

  destroyActiveCharts();
  syncChartThemeDefaults();
  setStatus('계산 중...', true);

  root.dataset.skelPending = String(seq);
  const skelTimer = setTimeout(() => {
    if (seq === renderSeq && root && root.dataset.skelPending === String(seq)) {
      root.innerHTML = renderViewSkeleton();
    }
  }, 90);

  try {
    const r = appState.route;
    const renderFn = await loadViewRenderer(r);
    if (seq !== renderSeq) return;
    if (r === 'team' || r === 'venue') await renderFn(root, appState.routeParam);
    else await renderFn(root);

    clearTimeout(skelTimer);
    delete root.dataset.skelPending;
    if (seq !== renderSeq) return;
    const healthTxt = appState.dataHealth.ok
      ? appState.dataHealth.summaryLabel
      : `⚠ ${appState.dataHealth.summaryLabel}`;
    setStatus(`기준 ${appState.dataEnd} · ${healthTxt}`, false);
  } catch (err) {
    clearTimeout(skelTimer);
    delete root.dataset.skelPending;
    if (seq !== renderSeq) return;
    console.error(err);
    setGlobalError(`화면을 불러오는 중 오류가 발생했습니다. ${friendlySqlError(err)}`, err);
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
    const willOpen = advList.hidden;
    setAdvancedNavOpen(willOpen);
    if (willOpen) {
      loadSourceReview().then(() => updateNavActive()).catch(() => {});
    }
  });

  // Left nav links keep current query params
  document.querySelectorAll('.nav-link[data-route]').forEach(a => {
    a.addEventListener('click', e => {
      e.preventDefault();
      const target = NAV_TARGETS[a.dataset.route];
      navigateTo(target ? target().route : a.dataset.route, '');
    });
  });

  // Any reset-filters or retry-view button
  document.addEventListener('click', e => {
    if (e.target.closest('[data-action="reset-filters"]')) {
      resetAllFiltersAndWeights();
    } else if (e.target.closest('[data-action="retry-view"]')) {
      if (appState.ready) renderCurrentView();
      else window.location.reload();
    }
  });

  // '⋯ 더보기' 메뉴(.ux-more): 안의 링크·단추를 누르거나 바깥을 누르거나 Esc → 닫기 (docs/ux_simplify_2026-11-28.md)
  document.addEventListener('click', e => {
    const inMenuAction = e.target.closest('.ux-more-menu a, .ux-more-menu button:not(.density-btn)');
    document.querySelectorAll('details.ux-more[open]').forEach(d => {
      if (inMenuAction ? d.contains(inMenuAction) : !d.contains(e.target)) d.removeAttribute('open');
    });
  });
  document.addEventListener('keydown', e => {
    if (e.key !== 'Escape') return;
    document.querySelectorAll('details.ux-more[open]').forEach(d => {
      d.removeAttribute('open');
      d.querySelector('summary')?.focus();
    });
  });

  // Delegated watch button click inside any view
  document.getElementById('viewRoot')?.addEventListener('click', e => {
    const btn = e.target.closest('button[data-watch-key]');
    if (!btn) return;
    e.stopPropagation();
    const added = toggleWatch(btn.dataset.watchKey, btn.dataset.watchName);
    btn.classList.toggle('btn-active', added);
    btn.setAttribute('aria-pressed', String(added));
    const label = added ? WATCH_LABELS.on : WATCH_LABELS.off;
    const fullLbl = btn.querySelector('.watch-lbl-full');
    const shortLbl = btn.querySelector('.watch-lbl-short');
    if (fullLbl || shortLbl) {
      if (fullLbl) fullLbl.textContent = label;
      if (shortLbl) shortLbl.textContent = added ? '★' : '☆';
      btn.setAttribute('aria-label', `${btn.dataset.watchName || ''} ${label}`.trim());
    } else {
      btn.textContent = `${added ? '★' : '☆'} ${label}`;
    }
    if (added) showToast('내 목록에 담았어요 · 새 소식이 홈·알림에 모여요');
    updateNavActive();
    if (appState.route === 'today') renderCurrentView();
  });

  window.addEventListener('hashchange', () => {
    const fixedHash = remapHash(window.location.hash, keyAliasMap);   // 옛 팀 키 주소 → 새 키 (docs/lab/data/key_aliases.csv)
    if (fixedHash !== window.location.hash) history.replaceState(null, '', fixedHash);
    const prevR = appState.route;
    const prevP = appState.routeParam;
    parseHash();
    if (prevR && appState.route && appState.route !== prevR) {
      appState.prevRoute = prevR;
      appState.prevParam = prevP;
    }
    renderCurrentView();
  });

  window.addEventListener('app:route', () => {
    renderCurrentView();
  });

  window.addEventListener('app:recompute', () => {
    renderCurrentView();
  });

  window.addEventListener('app:watchlist', updateNavActive);
  window.addEventListener('app:alerts-loaded', updateNavActive);
  window.addEventListener('app:export-ctx', updateExportMenuUI);
  window.addEventListener('app:toast', (e) => {
    if (e.detail) showToast(String(e.detail));
  });

  // Allow live health recomputation (also helpful for automated verification)
  window.addEventListener('app:refresh-health', () => {
    appState.dataHealth = computeDataHealth();
    renderAnomalyBanner();
    updateNavActive();
  });
}

// ---------- Boot ----------

// 팀 대표 키가 바뀐 뒤 저장된 관심 팀·비교 담기·옛 주소를 새 키로 (scripts/key_aliases.py → docs/lab/data/key_aliases.csv)
let keyAliasMap = new Map();

async function applyKeyAliasesOnBoot() {
  keyAliasMap = parseAliasCsv(await fetchText('lab/data/key_aliases.csv', true).catch(() => null));
  if (!keyAliasMap.size) return;
  const moved = applyKeyAliases(keyAliasMap);
  if (moved.watch) window.dispatchEvent(new CustomEvent('app:watchlist'));
  if (moved.compare) window.dispatchEvent(new CustomEvent('app:compare-changed'));
  const fixedHash = remapHash(window.location.hash, keyAliasMap);
  if (fixedHash !== window.location.hash) history.replaceState(null, '', fixedHash);
}

async function boot() {
  initTheme();
  initGlobalSearch();
  initMiniPlayer();
  initCompareTray();
  initChartPng();
  initExportMenu();
  wireGlobalEvents();
  parseHash();
  updateNavActive();

  try {
    // Preload the initial route JS module and optional alerts.json concurrently with DuckDB + CSV bootstrap
    const initialViewPromise = loadViewRenderer(appState.route).catch(() => null);
    const alertsBootPromise = loadAlertsJson().catch(() => null);
    await Promise.all([
      bootstrapData(msg => setStatus(msg, true)),
      initialViewPromise,
      alertsBootPromise,
    ]);

    if (!window.location.hash.includes('as_of=')) {
      appState.cfg.as_of = appState.dataEnd;
    }
    await applyKeyAliasesOnBoot();
    parseHash();
    updateNavActive();

    const r = appState.meta?.rows || {};
    const footMeta = document.getElementById('navDataMeta');
    if (footMeta) {
      footMeta.textContent = `기준 ${appState.dataEnd} · 신호 ${fmtInt(r.signals)} · 팀 ${fmtInt(r.teams)}`;
    }

    await renderCurrentView();
  } catch (err) {
    console.error(err);
    setStatus('초기화 실패', false);
    setGlobalError(`앱을 초기화하지 못했습니다. ${friendlySqlError(err)}`, err);
  }
}

boot();
