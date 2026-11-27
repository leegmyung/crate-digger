import {
  ALL_BRANCHES, appState, cloneDefaults, destroyActiveCharts,
  getActiveFilterSummary, getWatchlist, hasCustomWeights,
  navigateTo, parseHash, syncHash, toggleWatch,
} from './state.js';
import { bootstrapData } from './db.js';
import {
  cssVar, escapeHtml, fmtInt, friendlySqlError, renderViewSkeleton,
} from './ui.js';
import { renderTodayView } from './views/today.js';
import { renderCandidatesView } from './views/candidates.js';
import { renderTeamView } from './views/team.js';
import { renderWatchlistView } from './views/watchlist.js';
import { renderBacktestView } from './views/backtest.js';
import { renderSignalsView } from './views/signals.js';
import { renderEvidenceView } from './views/evidence.js';
import { renderVenuesView } from './views/venues.js';
import { renderQualityView } from './views/quality.js';
import { renderSqlView } from './views/sql.js';

let renderSeq = 0;

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

function updateNavActive() {
  const route = appState.route;
  document.querySelectorAll('.nav-link[data-route]').forEach(a => {
    const active = a.dataset.route === route || (route === 'team' && a.dataset.route === 'team');
    a.classList.toggle('active', active);
    if (active) a.setAttribute('aria-current', 'page');
    else a.removeAttribute('aria-current');
  });
  const wc = document.getElementById('navWatchCount');
  if (wc) {
    const n = getWatchlist().length;
    wc.textContent = n > 0 ? String(n) : '';
  }
  const customNote = document.getElementById('navWeightBadge');
  if (customNote) {
    customNote.textContent = hasCustomWeights() ? '수정됨' : '';
  }
}

function closeMobileNav() {
  document.getElementById('navRail')?.classList.remove('open');
  document.getElementById('navBackdrop')?.classList.remove('open');
  document.getElementById('mobileMenuBtn')?.setAttribute('aria-expanded', 'false');
}

// ---------- Global Filter Bar Sync & Collapsible Summary ----------

function buildBranchCheckboxes() {
  const wrap = document.getElementById('gfBranches');
  if (!wrap) return;
  wrap.innerHTML = ALL_BRANCHES.map(b => `
    <label class="f-check">
      <input type="checkbox" name="gf_branch" value="${escapeHtml(b)}" ${appState.cfg.branches.includes(b) ? 'checked' : ''}>
      <span>${escapeHtml(b)}</span>
    </label>
  `).join('');
}

function populateGenreOptions() {
  const sel = document.getElementById('gfGenre');
  if (!sel) return;
  sel.innerHTML = '<option value="">전체 장르</option>' +
    appState.validGenres.map(g => `<option value="${escapeHtml(g)}">${escapeHtml(g)}</option>`).join('');
  if (appState.cfg.genre && !appState.validGenres.includes(appState.cfg.genre)) {
    appState.cfg.genre = '';
  }
  sel.value = appState.cfg.genre;
}

function updateFilterSummaryUI() {
  const summary = getActiveFilterSummary(appState.cfg);
  const toggleBtn = document.getElementById('btnToggleFilters');
  const toggleLbl = document.getElementById('filterToggleLabel');
  const chipsEl = document.getElementById('filterSummaryChips');

  if (toggleLbl) {
    toggleLbl.textContent = summary.count > 0 ? `필터 · ${summary.count}개 적용됨` : '필터';
  }
  if (toggleBtn) {
    toggleBtn.classList.toggle('btn-active', summary.count > 0);
  }
  if (chipsEl) {
    if (summary.count > 0) {
      chipsEl.innerHTML = summary.items
        .map(it => `<span class="filter-chip">${escapeHtml(it.label)}</span>`)
        .join('') +
        ' <button type="button" class="filter-clear-link" data-action="reset-filters">초기화</button>';
    } else {
      chipsEl.innerHTML = '<span class="muted">기본 조건 (전체 장르 · 3년 · 유명 팀 제외)</span>';
    }
  }

  document.querySelectorAll('[data-filter-field]').forEach(el => {
    const key = el.dataset.filterField;
    el.classList.toggle('is-changed', summary.changedKeys.has(key));
  });
}

function syncGlobalControlsFromState() {
  const c = appState.cfg;
  const gSel = document.getElementById('gfGenre');
  if (gSel) gSel.value = c.genre;
  const pSel = document.getElementById('gfPeriod');
  if (pSel) pSel.value = String(c.period_days);
  const nInp = document.getElementById('gfNewcomer');
  if (nInp) nInp.value = String(c.newcomer_years);
  const exCb = document.getElementById('gfExcludeFamous');
  if (exCb) exCb.checked = c.exclude_famous;
  document.querySelectorAll('input[name="gf_branch"]').forEach(cb => {
    cb.checked = c.branches.includes(cb.value);
  });
  updateFilterSummaryUI();
}

function readGlobalControlsToState() {
  const c = appState.cfg;
  c.genre = document.getElementById('gfGenre')?.value || '';
  c.period_days = Number(document.getElementById('gfPeriod')?.value) || 0;
  c.newcomer_years = Math.max(1, Math.min(15, Math.round(Number(document.getElementById('gfNewcomer')?.value) || 3)));
  c.exclude_famous = Boolean(document.getElementById('gfExcludeFamous')?.checked);
  const checked = [...document.querySelectorAll('input[name="gf_branch"]:checked')].map(el => el.value);
  c.branches = checked;
  syncHash(true);
  updateFilterSummaryUI();
}

function resetAllFiltersAndWeights() {
  appState.cfg = cloneDefaults();
  appState.cfg.as_of = appState.dataEnd;
  syncGlobalControlsFromState();
  syncHash(true);
  renderCurrentView();
}

// ---------- Autocomplete Team Search ----------

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
        <strong>${escapeHtml(t.display_name || t.team_key)}</strong>
        <span class="small muted">${escapeHtml(t.primary_genre || '')}</span>
      </button>
    `).join('');
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
  updateNavActive();
  closeMobileNav();

  if (!appState.cfg.branches.length) {
    setGlobalError('갈래(공연·선정·지원·발매·큐레이션)를 최소 1개 이상 선택해 주세요.');
    setStatus('필터 확인 필요', false);
    return;
  }

  destroyActiveCharts();
  syncChartThemeDefaults();
  const t0 = performance.now();
  setStatus('계산 중...', true);

  // Show minimal skeleton if query takes >90ms (avoids flicker on instant views)
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
    else if (r === 'backtest') await renderBacktestView(root);
    else if (r === 'signals') await renderSignalsView(root);
    else if (r === 'evidence') await renderEvidenceView(root);
    else if (r === 'venues') await renderVenuesView(root);
    else if (r === 'quality') await renderQualityView(root);
    else if (r === 'sql') await renderSqlView(root);
    else await renderTodayView(root);

    clearTimeout(skelTimer);
    if (seq !== renderSeq) return;
    const sec = ((performance.now() - t0) / 1000).toFixed(2);
    setStatus(`기준 ${appState.dataEnd} · 계산 완료 (${sec}초)`, false);
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
  // Mobile menu drawer
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

  // Collapsible filter drawer toggle
  const filterToggle = document.getElementById('btnToggleFilters');
  const filterDrawer = document.getElementById('globalFilterDrawer');
  filterToggle?.addEventListener('click', () => {
    if (!filterDrawer) return;
    const nextOpen = filterDrawer.hidden;
    filterDrawer.hidden = !nextOpen;
    filterToggle.setAttribute('aria-expanded', nextOpen ? 'true' : 'false');
    filterToggle.classList.toggle('is-open', nextOpen);
  });

  // Left nav links keep current query params
  document.querySelectorAll('.nav-link[data-route]').forEach(a => {
    a.addEventListener('click', e => {
      e.preventDefault();
      const targetRoute = a.dataset.route;
      if (targetRoute === 'team' && appState.routeParam) {
        navigateTo('team', appState.routeParam);
      } else {
        navigateTo(targetRoute, '');
      }
    });
  });

  // Global filter changes
  const filterBar = document.getElementById('globalFilterBar');
  filterBar?.addEventListener('change', e => {
    if (e.target.id === 'gfTeamSearch') return;
    readGlobalControlsToState();
    renderCurrentView();
  });

  // Reset all global filters + weights (top button + any inline empty-state reset button)
  document.getElementById('btnGlobalReset')?.addEventListener('click', resetAllFiltersAndWeights);
  document.addEventListener('click', e => {
    if (e.target.closest('[data-action="reset-filters"]')) {
      resetAllFiltersAndWeights();
    }
  });

  // Share link copy
  document.getElementById('btnCopyLink')?.addEventListener('click', async () => {
    syncHash(true);
    const btn = document.getElementById('btnCopyLink');
    try {
      await navigator.clipboard.writeText(window.location.href);
      btn.textContent = '복사됨';
      setTimeout(() => { btn.textContent = '링크 복사'; }, 1400);
    } catch (_) {
      window.prompt('아래 링크를 복사하세요:', window.location.href);
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
      if (shortLbl) shortLbl.textContent = added ? '✓' : '+';
      btn.setAttribute('aria-label', `${btn.dataset.watchName || ''} ${added ? '관심 중' : '관심 추가'}`.trim());
    } else {
      btn.textContent = added ? '관심 중' : '관심 추가';
    }
    updateNavActive();
    // Refresh Today view watchlist block immediately when toggling from Today
    if (appState.route === 'today') renderCurrentView();
  });

  window.addEventListener('hashchange', () => {
    parseHash();
    syncGlobalControlsFromState();
    renderCurrentView();
  });

  window.addEventListener('app:route', () => {
    renderCurrentView();
  });

  window.addEventListener('app:recompute', () => {
    syncGlobalControlsFromState();
    renderCurrentView();
  });

  window.addEventListener('app:watchlist', updateNavActive);
}

// ---------- Boot ----------

async function boot() {
  initTheme();
  buildBranchCheckboxes();
  initTeamSearch();
  wireGlobalEvents();
  parseHash();
  updateNavActive();

  try {
    await bootstrapData(msg => setStatus(msg, true));

    // Set default as_of to real dataEnd unless hash explicitly overrode it
    if (!window.location.hash.includes('as_of=')) {
      appState.cfg.as_of = appState.dataEnd;
    }
    parseHash();
    populateGenreOptions();
    syncGlobalControlsFromState();

    const r = appState.meta?.rows || {};
    const footMeta = document.getElementById('navDataMeta');
    if (footMeta) {
      footMeta.textContent = `기준 ${appState.dataEnd} · 신호 ${fmtInt(r.signals)} · 팀 ${fmtInt(r.teams)} · 정답 ${fmtInt(r.outcomes)}`;
    }

    await renderCurrentView();
  } catch (err) {
    console.error(err);
    setStatus('초기화 실패', false);
    setGlobalError(`앱을 초기화하지 못했습니다: ${friendlySqlError(err)}. 로컬 서버(http://) 또는 GitHub Pages에서 열어 주세요.`);
  }
}

boot();
