import {
  ALL_BRANCHES, appState, cloneDefaults, destroyActiveCharts,
  getWatchlist, hasCustomWeights, navigateTo, parseHash,
  syncHash, toggleWatch,
} from './state.js';
import { bootstrapData } from './db.js';
import { escapeHtml, fmtInt, friendlySqlError } from './ui.js';
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
}

// ---------- Global Filter Bar Sync ----------

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
      drop.innerHTML = '<div class="small muted" style="padding:8px 10px;">일치하는 팀이 없습니다.</div>';
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

// ---------- Theme ----------

function applyTheme(mode) {
  document.documentElement.dataset.theme = mode;
  const btn = document.getElementById('themeToggle');
  if (btn) btn.textContent = mode === 'dark' ? '라이트 모드' : '다크 모드';
}

function initTheme() {
  let saved = null;
  try { saved = window.localStorage.getItem('crate_digger_theme'); } catch (_) {}
  const preferDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  applyTheme(saved || (preferDark ? 'dark' : 'light'));

  document.getElementById('themeToggle')?.addEventListener('click', () => {
    const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    try { window.localStorage.setItem('crate_digger_theme', next); } catch (_) {}
    applyTheme(next);
    if (appState.ready) renderCurrentView();
  });
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
  const t0 = performance.now();
  setStatus('계산 중...', true);

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

    if (seq !== renderSeq) return;
    const sec = ((performance.now() - t0) / 1000).toFixed(2);
    setStatus(`기준 ${appState.dataEnd} · 계산 완료 (${sec}초)`, false);
  } catch (err) {
    if (seq !== renderSeq) return;
    console.error(err);
    setGlobalError(`화면을 불러오는 중 오류가 발생했습니다: ${friendlySqlError(err)}`);
    setStatus('오류 발생', false);
  }
}

// ---------- Event Wiring ----------

function wireGlobalEvents() {
  // Mobile menu drawer
  document.getElementById('mobileMenuBtn')?.addEventListener('click', () => {
    document.getElementById('navRail')?.classList.toggle('open');
    document.getElementById('navBackdrop')?.classList.toggle('open');
  });
  document.getElementById('navBackdrop')?.addEventListener('click', closeMobileNav);

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

  // Reset all global filters + weights
  document.getElementById('btnGlobalReset')?.addEventListener('click', () => {
    appState.cfg = cloneDefaults();
    appState.cfg.as_of = appState.dataEnd;
    syncGlobalControlsFromState();
    syncHash(true);
    renderCurrentView();
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
    btn.textContent = added ? '관심 중' : '관심 추가';
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
