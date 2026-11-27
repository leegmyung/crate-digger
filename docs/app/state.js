export const ALL_BRANCHES = ['공연', '선정·지원', '발매', '큐레이션'];
export const PRESET_CUTOFFS = ['2022-01-01', '2023-01-01', '2024-01-01', '2024-07-01', '2025-01-01', '2025-07-01'];
export const PRESET_KS = [10, 20, 30, 50, 100, 200];

export const ROUTES = [
  'today',
  'candidates',
  'team',
  'watchlist',
  'backtest',
  'signals',
  'evidence',
  'venues',
  'quality',
  'sql',
];

// Single source of truth for scoring weights (matches docs/lab/sql/features.sql)
export const DEFAULT_WEIGHTS = {
  w_branch: 2,
  w_stage: 1,
  w_peer: 1,
  w_dmz: 0.5,
  w_gigs: 0.5,
  w_outlets: 1,
  outlet_cap: 3,
};

export const WEIGHT_FIELDS = [
  { key: 'w_branch', label: '갈래 수 (갈래−1)', min: 0, max: 5, step: 0.5, isInt: false },
  { key: 'w_stage', label: '선정 최고 단계 (0~4)', min: 0, max: 3, step: 0.5, isInt: false },
  { key: 'w_peer', label: '선정 팀과 같은 무대', min: 0, max: 3, step: 0.5, isInt: false },
  { key: 'w_dmz', label: 'DMZ 출연', min: 0, max: 3, step: 0.5, isInt: false },
  { key: 'w_gigs', label: '최근 1년 공연 ln(1+n)', min: 0, max: 3, step: 0.5, isInt: false },
  { key: 'w_outlets', label: '큐레이션 매체 수', min: 0, max: 3, step: 0.5, isInt: false },
  { key: 'outlet_cap', label: '큐레이션 매체 상한', min: 1, max: 6, step: 1, isInt: true },
];

export const WEIGHT_KEYS = Object.keys(DEFAULT_WEIGHTS);

export const DEFAULTS = {
  // Global filters
  genre: '',
  branches: [...ALL_BRANCHES],
  period_days: 0, // 0=전체(신호 기간), 30/90/180/365
  newcomer_years: 3,
  exclude_famous: true,
  only_no_outcome: true,
  lookback_years: 3,
  as_of: '2026-11-27',
  limit: 100,

  // Global scoring weights (shared across Today, Candidates, Team, Watchlist, Backtest)
  ...DEFAULT_WEIGHTS,

  // Backtest & Signals
  cutoffs: ['2023-01-01', '2024-01-01', '2025-01-01'],
  horizon_months: 24,
  outcome_tier: 'any',
  k_list: [20, 50, 100, 200],
  compare_k: 20,
  signal_cutoff: '2025-01-01',
};

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const WATCH_KEY = 'crate_digger_watchlist_v1';

export function cloneDefaults() {
  return {
    ...DEFAULTS,
    branches: [...DEFAULTS.branches],
    cutoffs: [...DEFAULTS.cutoffs],
    k_list: [...DEFAULTS.k_list],
  };
}

export const appState = {
  route: 'today',
  routeParam: '',
  cfg: cloneDefaults(),
  knownCutoffs: [...PRESET_CUTOFFS],
  validGenres: [],
  dataEnd: '2026-11-27',
  outcomeRange: { min: null, max: null, counted: 0 },
  ready: false,
  meta: null,
  dashboardJson: null,
  lastSql: {
    backtest: '',
    candidates: '',
    signals: '',
    precedents: '',
    team: '',
    related: '',
  },
  sqlTemplates: {
    features: '',
    backtest: '',
    candidates: '',
    signal_hits: '',
    precedents: '',
    team: '',
    related: '',
  },
  snapshots: {
    dates: [],
    reconstructed: [],
    latestDate: null,
    prevDate: null,
    latest: new Map(),
    prev: new Map(),
  },
  linksByTeam: new Map(),
  videosByTeam: new Map(),
  teamIndex: [], // [{team_key, display_name, primary_genre}] for autocomplete
  candSort: { col: 'score', dir: 'desc' },
  activeCharts: [],
};

export function hasCustomWeights(cfg = appState.cfg) {
  return WEIGHT_KEYS.some(k => Number(cfg[k]) !== Number(DEFAULT_WEIGHTS[k]));
}

export function getActiveFilterSummary(cfg = appState.cfg) {
  const items = [];
  const changedKeys = new Set();
  if (cfg.genre) {
    items.push({ key: 'genre', label: `장르: ${cfg.genre}` });
    changedKeys.add('genre');
  }
  if (cfg.branches.length !== ALL_BRANCHES.length) {
    items.push({ key: 'branches', label: `갈래: ${cfg.branches.join(', ') || '없음'}` });
    changedKeys.add('branches');
  }
  if (Number(cfg.period_days) > 0) {
    items.push({ key: 'period_days', label: `최근 ${cfg.period_days}일` });
    changedKeys.add('period_days');
  }
  if (Number(cfg.newcomer_years) !== DEFAULTS.newcomer_years) {
    items.push({ key: 'newcomer_years', label: `신인 ${cfg.newcomer_years}년` });
    changedKeys.add('newcomer_years');
  }
  if (Boolean(cfg.exclude_famous) !== DEFAULTS.exclude_famous) {
    items.push({ key: 'exclude_famous', label: '유명 팀 포함' });
    changedKeys.add('exclude_famous');
  }
  return { count: items.length, items, changedKeys };
}

export function destroyActiveCharts() {
  for (const ch of appState.activeCharts) {
    try { ch.destroy(); } catch (_) {}
  }
  appState.activeCharts = [];
}

export function registerChart(ch) {
  if (ch) appState.activeCharts.push(ch);
  return ch;
}

// ---------- Hash Routing + Query Sync ----------

export function parseHash() {
  const raw = window.location.hash.replace(/^#/, '');
  if (!raw) {
    appState.route = 'today';
    appState.routeParam = '';
    return;
  }

  let pathPart = '';
  let queryPart = '';
  if (raw.startsWith('/')) {
    const qIdx = raw.indexOf('?');
    pathPart = qIdx >= 0 ? raw.slice(1, qIdx) : raw.slice(1);
    queryPart = qIdx >= 0 ? raw.slice(qIdx + 1) : '';
  } else {
    // Legacy lab hash like #w_branch=0&tab=candidates
    queryPart = raw;
  }

  const segs = pathPart.split('/').filter(Boolean);
  if (segs[0] === 'team' && segs[1]) {
    appState.route = 'team';
    try {
      appState.routeParam = decodeURIComponent(segs.slice(1).join('/'));
    } catch (_) {
      appState.routeParam = segs[1];
    }
  } else if (segs[0] && ROUTES.includes(segs[0])) {
    appState.route = segs[0];
    appState.routeParam = '';
  } else if (!pathPart && queryPart) {
    appState.route = 'backtest';
    appState.routeParam = '';
  } else {
    appState.route = 'today';
    appState.routeParam = '';
  }

  if (!queryPart) return;
  const p = new URLSearchParams(queryPart);
  const c = appState.cfg;

  for (const key of ['w_branch', 'w_stage', 'w_peer', 'w_dmz', 'w_gigs', 'w_outlets']) {
    if (p.has(key)) {
      const n = Number(p.get(key));
      if (Number.isFinite(n) && n >= 0 && n <= 10) c[key] = n;
    }
  }
  for (const [key, min, max] of [
    ['outlet_cap', 1, 10],
    ['lookback_years', 1, 15],
    ['newcomer_years', 1, 15],
    ['horizon_months', 1, 60],
    ['period_days', 0, 3650],
    ['limit', 10, 500],
    ['compare_k', 1, 5000],
  ]) {
    if (p.has(key)) {
      const n = Number(p.get(key));
      if (Number.isFinite(n) && n >= min && n <= max) c[key] = Math.round(n);
    }
  }
  if (p.has('exclude_famous')) c.exclude_famous = p.get('exclude_famous') !== 'false';
  if (p.has('only_no_outcome')) c.only_no_outcome = p.get('only_no_outcome') !== 'false';
  if (p.has('outcome_tier') && ['any', 'final', 'mid'].includes(p.get('outcome_tier'))) {
    c.outcome_tier = p.get('outcome_tier');
  }
  if (p.has('as_of') && DATE_RE.test(p.get('as_of'))) c.as_of = p.get('as_of');
  if (p.has('signal_cutoff') && DATE_RE.test(p.get('signal_cutoff'))) c.signal_cutoff = p.get('signal_cutoff');
  if (p.has('genre')) c.genre = p.get('genre');
  if (p.has('branches')) {
    const bs = p.get('branches').split(',').filter(b => ALL_BRANCHES.includes(b));
    if (bs.length) c.branches = bs;
  }
  if (p.has('cutoffs')) {
    const ds = p.get('cutoffs').split(',').filter(d => DATE_RE.test(d));
    if (ds.length) {
      c.cutoffs = [...new Set(ds)].sort();
      for (const d of c.cutoffs) {
        if (!appState.knownCutoffs.includes(d)) appState.knownCutoffs.push(d);
      }
      appState.knownCutoffs.sort();
    }
  }
  if (p.has('k_list')) {
    const ks = p.get('k_list').split(',').map(Number).filter(n => Number.isFinite(n) && n >= 1 && n <= 5000);
    if (ks.length) c.k_list = [...new Set(ks)].sort((a, b) => a - b);
  }
}

export function buildHashUrl(route = appState.route, param = appState.routeParam, forceAll = false) {
  const c = appState.cfg;
  const p = new URLSearchParams();
  const defAsOf = appState.dataEnd || DEFAULTS.as_of;

  const setIf = (k, v, defVal) => {
    const sv = Array.isArray(v) ? v.join(',') : String(v);
    const sd = Array.isArray(defVal) ? defVal.join(',') : String(defVal);
    if (forceAll || sv !== sd) p.set(k, sv);
  };

  setIf('genre', c.genre, DEFAULTS.genre);
  setIf('branches', c.branches, DEFAULTS.branches);
  setIf('period_days', c.period_days, DEFAULTS.period_days);
  setIf('newcomer_years', c.newcomer_years, DEFAULTS.newcomer_years);
  setIf('exclude_famous', c.exclude_famous, DEFAULTS.exclude_famous);
  setIf('only_no_outcome', c.only_no_outcome, DEFAULTS.only_no_outcome);
  setIf('lookback_years', c.lookback_years, DEFAULTS.lookback_years);
  setIf('as_of', c.as_of, defAsOf);
  setIf('limit', c.limit, DEFAULTS.limit);
  setIf('w_branch', c.w_branch, DEFAULTS.w_branch);
  setIf('w_stage', c.w_stage, DEFAULTS.w_stage);
  setIf('w_peer', c.w_peer, DEFAULTS.w_peer);
  setIf('w_dmz', c.w_dmz, DEFAULTS.w_dmz);
  setIf('w_gigs', c.w_gigs, DEFAULTS.w_gigs);
  setIf('w_outlets', c.w_outlets, DEFAULTS.w_outlets);
  setIf('outlet_cap', c.outlet_cap, DEFAULTS.outlet_cap);
  setIf('cutoffs', c.cutoffs, DEFAULTS.cutoffs);
  setIf('horizon_months', c.horizon_months, DEFAULTS.horizon_months);
  setIf('outcome_tier', c.outcome_tier, DEFAULTS.outcome_tier);
  setIf('k_list', c.k_list, DEFAULTS.k_list);
  setIf('compare_k', c.compare_k, DEFAULTS.compare_k);
  setIf('signal_cutoff', c.signal_cutoff, DEFAULTS.signal_cutoff);

  const basePath = route === 'team' && param ? `#/team/${encodeURIComponent(param)}` : `#/${route}`;
  const qs = p.toString();
  return qs ? `${basePath}?${qs}` : basePath;
}

export function syncHash(replace = true) {
  const next = buildHashUrl();
  if (window.location.hash === next) return;
  if (replace) {
    window.history.replaceState(null, '', next);
  } else {
    window.location.hash = next;
  }
}

export function navigateTo(route, param = '') {
  appState.route = route;
  appState.routeParam = param;
  const next = buildHashUrl(route, param);
  if (window.location.hash !== next) {
    window.location.hash = next;
  } else {
    window.dispatchEvent(new CustomEvent('app:route'));
  }
}

// ---------- Watchlist (localStorage with try/catch) ----------

let memWatchlist = [];

export function getWatchlist() {
  try {
    const raw = window.localStorage.getItem(WATCH_KEY);
    if (!raw) return [...memWatchlist];
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) {
      memWatchlist = parsed.filter(item => item && typeof item.team_key === 'string');
      return [...memWatchlist];
    }
  } catch (_) {}
  return [...memWatchlist];
}

function saveWatchlist(list) {
  memWatchlist = list;
  try {
    window.localStorage.setItem(WATCH_KEY, JSON.stringify(list));
  } catch (_) {}
  window.dispatchEvent(new CustomEvent('app:watchlist'));
}

export function isWatched(teamKey) {
  return getWatchlist().some(it => it.team_key === teamKey);
}

export function toggleWatch(teamKey, displayName = '') {
  const list = getWatchlist();
  const idx = list.findIndex(it => it.team_key === teamKey);
  let added = false;
  if (idx >= 0) {
    list.splice(idx, 1);
  } else {
    list.unshift({
      team_key: teamKey,
      display_name: displayName || teamKey,
      added_at: new Date().toISOString().slice(0, 10),
    });
    added = true;
  }
  saveWatchlist(list);
  return added;
}

export function exportWatchlistCsv(rows) {
  const header = ['team_key', 'display_name', 'score', 'rank_now', 'rank_delta', 'recent_7d_signals', 'last_seen', 'added_at'];
  const esc = v => {
    const s = String(v ?? '');
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const lines = [header.join(',')];
  for (const r of rows) {
    lines.push([
      r.team_key,
      r.display_name,
      r.score ?? '',
      r.rank_now ?? '',
      r.rank_delta ?? '',
      r.recent_7d ?? 0,
      r.last_seen ?? '',
      r.added_at ?? '',
    ].map(esc).join(','));
  }
  const blob = new Blob(['\ufeff' + lines.join('\n')], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `crate_digger_watchlist_${appState.dataEnd || 'export'}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

const PLATFORM_KEY = 'crate_digger_platform_v1';
const VALID_PLATFORMS = ['melon', 'genie', 'bugs', 'spotify', 'youtube', 'instagram'];

export function getPreferredPlatform() {
  try {
    const v = window.localStorage.getItem(PLATFORM_KEY);
    if (v && VALID_PLATFORMS.includes(v)) return v;
  } catch (_) {}
  return 'melon';
}

export function setPreferredPlatform(platform) {
  if (!VALID_PLATFORMS.includes(platform)) return;
  try {
    window.localStorage.setItem(PLATFORM_KEY, platform);
  } catch (_) {}
}

