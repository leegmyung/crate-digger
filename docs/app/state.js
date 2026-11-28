import { compareHash, compareKeysFromQuery } from './compare_list.js';
export const ALL_BRANCHES = ['공연', '선정·지원', '발매', '큐레이션'];
export const PRESET_CUTOFFS = ['2022-01-01', '2023-01-01', '2024-01-01', '2024-07-01', '2025-01-01', '2025-07-01'];
export const PRESET_KS = [10, 20, 30, 50, 100, 200];

export const ROUTES = [
  'today',
  'candidates',
  'team',
  'watchlist',
  'verify',
  'backtest',
  'signals',
  'evidence',
  'scorecard',
  'venues',
  'venue',
  'quality',
  'sql',
  'charts',
  'alerts',
  'search',
  'help',
  'compare',
];

// ---------- 정보 구조 v2 (docs/app_structure_v2.md) ----------
// 안쪽 경로 이름(today·candidates·venues·watchlist …)은 그대로 두고, 주소(해시)만 새 이름으로 내보낸다.
export const TEAM_TABS = ['overview', 'score', 'events', 'gigs', 'network', 'videos', 'precedents'];
export const VENUE_TABS = ['overview', 'teams', 'gigs', 'flow'];
export const CHART_KINDS = ['all', 'genre', 'city', 'rising', 'debut'];
export const MINE_TABS = ['watch', 'venues', 'filters'];
// 옛 주소 첫 칸 → 새 주소 (쿼리는 그대로 붙여 넘김). candidates·venues·verify는 쿼리를 봐야 해서 legacyToNew 안에서 따로.
export const LEGACY_ROUTES = {
  today: 'home',
  watchlist: 'mine',
  quality: 'verify/quality',
  sql: 'verify/sql',
  backtest: 'verify/backtest',
  signals: 'verify/signals',
  evidence: 'verify/evidence',
  scorecard: 'verify/scorecard',
};

export const VERIFY_TABS = ['backtest', 'scorecard', 'grades', 'signals', 'evidence'];

export const WATCH_STATUSES = [
  { id: 'watching', label: '지켜보는 중' },
  { id: 'listened', label: '들어봄' },
  { id: 'hold', label: '보류' },
];

// Single source of truth for scoring weights (matches docs/lab/sql/features.sql & docs/score_tuning.md)
export const WEIGHT_PRESETS = {
  v2: {
    w_branch: 1,
    w_stage: 1,
    w_peer: 0,
    w_dmz: 0,
    w_gigs: 0,
    w_outlets: 1,
    outlet_cap: 3,
    w_recent: 0,
    w_venues: 1,
    w_winner: 2,
    w_context: 0.5,
    w_collab: 0,
  },
  v1: {
    w_branch: 2,
    w_stage: 2,
    w_peer: 0,
    w_dmz: 0,
    w_gigs: 0,
    w_outlets: 0.5,
    outlet_cap: 3,
    w_recent: 1,
    w_venues: 2,
    w_winner: 1,
    w_context: 0,
    w_collab: 0,
  },
  v0: {
    w_branch: 2,
    w_stage: 1,
    w_peer: 1,
    w_dmz: 0.5,
    w_gigs: 0.5,
    w_outlets: 1,
    outlet_cap: 3,
    w_recent: 0,
    w_venues: 0,
    w_winner: 0,
    w_context: 0,
    w_collab: 0,
  },
};

export const DEFAULT_WEIGHTS = { ...WEIGHT_PRESETS.v2 };

export const WEIGHT_FIELDS = [
  { key: 'w_branch', label: '갈래 수 (갈래−1)', min: 0, max: 5, step: 0.5, isInt: false },
  { key: 'w_stage', label: '선정 최고 단계 (0~4)', min: 0, max: 3, step: 0.5, isInt: false },
  { key: 'w_venues', label: '최근 2년 서로 다른 공연장 수', min: 0, max: 3, step: 0.5, isInt: false },
  { key: 'w_recent', label: '최근 6개월 활동', min: 0, max: 3, step: 0.5, isInt: false },
  { key: 'w_winner', label: '이미 상 받은 팀과 같은 무대', min: 0, max: 3, step: 0.5, isInt: false },
  { key: 'w_outlets', label: '발굴 매체 수', min: 0, max: 3, step: 0.5, isInt: false },
  { key: 'w_context', label: '맥락 매체 수 (약하게)', min: 0, max: 3, step: 0.1, isInt: false },
  { key: 'outlet_cap', label: '매체 수 상한', min: 1, max: 6, step: 1, isInt: true },
  { key: 'w_peer', label: '선정 팀과 같은 무대', min: 0, max: 3, step: 0.5, isInt: false },
  { key: 'w_dmz', label: 'DMZ 출연', min: 0, max: 3, step: 0.5, isInt: false },
  { key: 'w_gigs', label: '최근 1년 공연 ln(1+n)', min: 0, max: 3, step: 0.5, isInt: false },
  { key: 'w_collab', label: '협업(기성 아티스트) — 데이터 수집 중', min: 0, max: 3, step: 0.5, isInt: false, muted: true },
];

export const WEIGHT_KEYS = Object.keys(DEFAULT_WEIGHTS);

export function getMatchingWeightPreset(cfg = appState.cfg) {
  for (const [name, preset] of Object.entries(WEIGHT_PRESETS)) {
    if (WEIGHT_KEYS.every(k => Number(cfg[k]) === Number(preset[k]))) return name;
  }
  return null;
}

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

  // Global scoring weights (shared across Today, Candidates, Team, Watchlist, Verify)
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
const WATCH_VIEW_KEY = 'crate_digger_watch_view_v1';

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
  verifyTab: 'backtest', // 'backtest' | 'signals' | 'evidence' | 'scorecard'
  candTab: 'all', // 'all' | 'debut'
  venuesTab: 'overview', // 'overview' | 'list' | 'city' | 'festival' | 'network'
  venuesCity: '', // 도시 탭에서 고른 도시
  teamTab: 'overview', // TEAM_TABS — #/team/<키>/<탭>
  venueTab: 'overview', // VENUE_TABS — #/venue/<이름>/<탭>
  chartKind: 'all', // CHART_KINDS — #/charts/<종류>[/<장르·도시>]
  chartParam: '',
  mineTab: 'watch', // MINE_TABS — #/mine?tab=
  compareKeys: [], // 팀 나란히 비교 #/compare?teams= (compare_list.js)
  searchQuery: '', // #/search?q=
  festivalName: '', // #/festival/<이름>
  prevRoute: null,
  prevParam: '',
  cfg: cloneDefaults(),
  knownCutoffs: [...PRESET_CUTOFFS],
  validGenres: [],
  dataEnd: '2026-11-27',
  outcomeRange: { min: null, max: null, counted: 0 },
  ready: false,
  meta: null,
  dashboardJson: null,
  collectJson: null,
  sourceReviewJson: null,
  dataHealth: { ok: true, severity: 'ok', issues: [], totalSources: 0, okSources: 0, lastCollectedDate: '', summaryLabel: '수집 정상' },
  weeklyDigestText: '',
  exportCtx: {
    csvLabel: '',
    csvFilename: '',
    csvHeaders: [],
    csvRows: [],
  },
  lastSql: {
    backtest: '',
    candidates: '',
    debut_candidates: '',
    signals: '',
    scorecard: '',
    debut_scorecard: '',
    precedents: '',
    team: '',
    related: '',
    ego_network: '',
    scene_network: '',
  },
  sqlTemplates: {
    features: '',
    backtest: '',
    candidates: '',
    debut_candidates: '',
    signal_hits: '',
    source_scorecard: '',
    source_scorecard_debut: '',
    precedents: '',
    team: '',
    related: '',
    ego_network: '',
    scene_network: '',
  },
  sourceRolesJson: null,
  alertsJson: null,
  programLabels: new Map(),
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
  imagesByTeam: new Map(), // team_key → 사진 주소 (lab/data/images.csv)
  videosLoaded: false, // 무대 영상 표(videos.csv)를 받았나 — 받기 전엔 '▶ 듣기' 자리만 잡아 두고 받은 뒤 채운다
  playersByTeam: new Map(), // team_key → 바로 듣기 후보 [{kind,type,id,title,source}] (lab/data/players.csv, 없으면 빈 표)
  imageMetaByTeam: new Map(), // team_key → { url, source }
  newcomerCheckByTeam: new Map(), // team_key → 'verified' | 'unverified' | 'first_seen' (optional column)
  firstReleaseByTeam: new Map(), // team_key → 'YYYY-MM-DD'
  genreConfidenceByTeam: new Map(), // team_key → 'inferred' | ...
  teamCitiesByTeam: new Map(), // team_key → { home_city, cities, first_city, ... }
  teamIndex: [], // [{team_key, display_name, primary_genre}] for autocomplete
  candSort: { col: 'score', dir: 'desc' },
  debutSort: { col: 'score', dir: 'desc' },
  candQuery: '',
  candMove: '', // '' | 'new' | 'riser' | 'upcoming'
  candStage: '', // '' | '0' | '1' | '2' | '3' | '4' (졸업 '4' 기본 숨김)
  candReleaseMonths: 0, // 0 | 6 | 12 | 18 | 24 | 36
  candRegion: '', // '' | 'non_seoul'
  candPreset: '', // '' | 'debut12' | 'blank' | 'selected' | 'regional' | 'rising'
  candView: '', // '' (표) | 'heat' (색 지도)
  candCity: '', // 발굴: 활동 도시(team_cities home_city) — 주소 hcity
  candTier: '', // 발굴: 가장 큰 무대 체급 상한 '' | 'S' | 'M' | 'L' — 주소 maxtier
  candGenreInf: '', // 발굴: '' = 추정 장르 포함 | 'exclude' = 장르 고를 때 추정 장르 팀 빼기 — 주소 ginf=0
  scFilter: 'all', // 'all' | 'discovery' | 'context' | 'excluded' | 'pending' | 'mismatch'
  scSort: { col: 'winners_seen', dir: 'desc' },
  venuesCalMode: 'cand', // 'cand' | 'all'
  sceneNetLimit: 150, // 80 | 150 | 250
  teamGraphPeriod: 'all', // 'all' | '1y'
  watchModeParam: null, // 'table' | 'board' | null
  activeCharts: [],
};

export function resetViewFilters() {
  appState.candSort = { col: 'score', dir: 'desc' };
  appState.debutSort = { col: 'score', dir: 'desc' };
  appState.candQuery = '';
  appState.candMove = '';
  appState.candStage = '';
  appState.candReleaseMonths = 0;
  appState.candRegion = '';
  appState.candPreset = '';
  appState.candView = '';
  appState.candCity = '';
  appState.candTier = '';
  appState.candGenreInf = '';
  appState.scFilter = 'all';
  appState.scSort = { col: 'winners_seen', dir: 'desc' };
  appState.venuesCalMode = 'cand';
  appState.sceneNetLimit = 150;
  appState.teamGraphPeriod = 'all';
}

export function setExportContext({ csvLabel = '', csvFilename = '', csvHeaders = [], csvRows = [], digestText = null } = {}) {
  appState.exportCtx = { csvLabel, csvFilename, csvHeaders, csvRows };
  if (typeof digestText === 'string' && digestText) {
    appState.weeklyDigestText = digestText;
  }
  window.dispatchEvent(new CustomEvent('app:export-ctx'));
}

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

const VALID_CAND_SORTS = new Set(['score', 'display_name', 'next_gig_sort', 'momentum_pct', 'genre_rank']);
const VALID_DEBUT_SORTS = new Set(['score', 'display_name', 'first_release', 'mentions']);
const VALID_SC_SORTS = new Set([
  'label', 'role', 'signal_rows', 'teams', 'rate',
  'winners_seen', 'first_to_see', 'median_lead_months',
]);
const VALID_SC_FILTERS = new Set(['all', 'discovery', 'context', 'excluded', 'pending', 'mismatch']);
const VALID_MOVES = new Set(['new', 'riser', 'upcoming']);
const VALID_STAGES = new Set(['0', '1', '2', '3', '4']);
const VALID_RELEASE_MONTHS = new Set([6, 12, 18, 24, 36]);
const VALID_REGIONS = new Set(['non_seoul']);
const VALID_PRESETS = new Set(['debut12', 'blank', 'selected', 'regional', 'rising']);
const VALID_CAND_VIEWS = new Set(['heat']);
const VENUES_TABS = new Set(['overview', 'list', 'city', 'festival', 'network']);
const VALID_SN_LIMITS = new Set([100, 150, 250, 300]);

function _dec(seg) {
  try { return decodeURIComponent(seg); } catch (_) { return seg; }
}

/** 옛 주소 → 새 주소 해시('#/…') 또는 null(이미 새 주소). 쿼리는 그대로 두고, 경로로 옮긴 vtab·ctab·vmode·city 만 뺀다. */
export function legacyToNew(pathPart, queryPart) {
  const p = new URLSearchParams(queryPart || '');
  const segs = (pathPart || '').split('/').filter(Boolean);
  const head = segs[0] || '';
  let next = null;
  if (!pathPart && queryPart) {
    next = 'verify/backtest';                       // 옛 실험실 해시 #w_branch=…&tab=… (예전처럼 검증으로)
  } else if (LEGACY_ROUTES[head]) {
    next = LEGACY_ROUTES[head];
  } else if (head === 'candidates') {
    next = (segs[1] === 'debut' || p.get('ctab') === 'debut') ? 'charts/debut' : 'discover';
    p.delete('ctab');
  } else if (head === 'venues' && (p.has('vmode') || p.get('tab') === 'city' || p.get('tab') === 'festival' || segs[1] === 'city' || segs[1] === 'festival')) {
    const tabParam = p.get('tab') === 'city' || p.get('tab') === 'festival' ? p.get('tab') : '';
    const mode = segs[1] === 'city' || segs[1] === 'festival' ? segs[1] : (tabParam || p.get('vmode'));
    p.delete('vmode');
    if (tabParam) p.delete('tab');
    if (mode === 'city') {
      const city = (p.get('city') || '').trim();
      p.delete('city');
      next = city ? `city/${encodeURIComponent(city)}` : 'cities';
    } else if (mode === 'festival') {
      next = 'festivals';
    } else {
      next = VENUES_TABS.has(mode) ? `venues/${mode}` : 'venues';
    }
  } else if (head === 'verify' && (!segs[1] || p.has('vtab'))) {
    const vt = p.get('vtab');
    p.delete('vtab');
    next = `verify/${segs[1] || (VERIFY_TABS.includes(vt) ? vt : 'backtest')}`;
  }
  if (next === null) return null;
  const qs = p.toString();
  return `#/${next}${qs ? `?${qs}` : ''}`;
}

export function parseHash() {
  parseHashString(window.location.hash);
}

function parseHashString(hash) {
  const raw = String(hash || '').replace(/^#/, '');
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

  // 옛 주소는 새 주소로 넘김 — 뒤로 가기 기록을 더럽히지 않게 replaceState (docs/app_structure_v2.md 3절)
  const legacy = legacyToNew(pathPart, queryPart);
  if (legacy) {
    try {
      window.history.replaceState(null, '', legacy);
    } catch (_) { /* file:// 등에서 막히면 주소는 그대로, 해석만 새 주소로 */ }
    parseHashString(legacy);
    return;
  }

  const p = new URLSearchParams(queryPart);
  const segs = pathPart.split('/').filter(Boolean);
  const head = segs[0] || '';
  let cityFromPath = '';
  appState.routeParam = '';
  appState.festivalName = '';
  if ((head === 'team' || head === 'venue') && segs[1]) {
    const tabs = head === 'team' ? TEAM_TABS : VENUE_TABS;
    // 키·이름은 encodeURIComponent 라 '/'가 %2F 로 들어감 → 세 번째 칸이 있으면 그건 탭(모르는 탭이면 개요)
    const last = segs[segs.length - 1];
    const hasTabSeg = segs.length >= 3;
    const tab = hasTabSeg && tabs.includes(last) ? last : 'overview';
    appState.route = head;
    appState.routeParam = _dec((hasTabSeg ? segs.slice(1, -1) : segs.slice(1)).join('/'));
    if (head === 'team') appState.teamTab = tab;
    else appState.venueTab = tab;
  } else if (head === 'home') {
    appState.route = 'today';
  } else if (head === 'discover') {
    appState.route = 'candidates';
    appState.candTab = 'all';
  } else if (head === 'charts') {
    const kind = CHART_KINDS.includes(segs[1]) ? segs[1] : 'all';
    if (kind === 'debut') {
      appState.route = 'candidates';           // 갓 데뷔 차트 = 지금의 후보 목록 '갓 데뷔' 탭 (묶음 F에서 차트 화면으로)
      appState.candTab = 'debut';
    } else {
      appState.route = 'charts';
      appState.chartKind = kind;
      appState.chartParam = segs[2] ? _dec(segs.slice(2).join('/')).slice(0, 40) : '';
    }
  } else if (head === 'venues') {
    appState.route = 'venues';
    if (['overview', 'list', 'network'].includes(segs[1])) appState.venuesTab = segs[1];
    else appState.venuesTab = (p.has('genre') && p.get('genre')) ? 'network' : 'overview';
  } else if (head === 'cities' || head === 'city') {
    appState.route = 'venues';
    appState.venuesTab = 'city';
    cityFromPath = head === 'city' && segs[1] ? _dec(segs.slice(1).join('/')).slice(0, 30) : '';
  } else if (head === 'festivals' || head === 'festival') {
    appState.route = 'venues';
    appState.venuesTab = 'festival';
    appState.festivalName = head === 'festival' && segs[1] ? _dec(segs.slice(1).join('/')).slice(0, 60) : '';
  } else if (head === 'alerts') {
    appState.route = 'alerts';
  } else if (head === 'mine') {
    appState.route = 'watchlist';
    appState.mineTab = MINE_TABS.includes(p.get('tab')) ? p.get('tab') : 'watch';
  } else if (head === 'help') {
    appState.route = 'help';
  } else if (head === 'compare') {
    appState.route = 'compare';
    appState.compareKeys = compareKeysFromQuery(queryPart);   // 키 안 쉼표를 지키려고 원문에서 직접 나눔
  } else if (head === 'search') {
    appState.route = 'search';
    appState.searchQuery = String(p.get('q') || '').slice(0, 100);
  } else if (head === 'verify') {
    const sub = segs[1] || 'backtest';
    if (sub === 'quality' || sub === 'sql') {
      appState.route = sub;
    } else {
      appState.route = 'verify';
      appState.verifyTab = VERIFY_TABS.includes(sub) ? sub : 'backtest';
    }
  } else {
    appState.route = 'today';
  }

  if (p.has('vtab') && VERIFY_TABS.includes(p.get('vtab'))) {
    appState.verifyTab = p.get('vtab');
  }
  if (p.has('ctab') && (p.get('ctab') === 'debut' || p.get('ctab') === 'all')) {
    appState.candTab = p.get('ctab');
  }
  if (appState.route === 'venues') appState.venuesCity = cityFromPath || (p.get('city') || '').slice(0, 30);

  // Restore per-view UI filters from URL (reset to default when absent for that view)
  if (appState.route === 'candidates') {
    appState.candQuery = p.has('q') ? String(p.get('q') || '').slice(0, 100) : '';
    const mv = p.get('move') || '';
    appState.candMove = VALID_MOVES.has(mv) ? mv : '';
    const st = p.get('stage') || '';
    appState.candStage = VALID_STAGES.has(st) ? st : '';
    const rmNum = Number(p.get('rm') || 0);
    appState.candReleaseMonths = VALID_RELEASE_MONTHS.has(rmNum) ? rmNum : 0;
    const reg = p.get('region') || '';
    appState.candRegion = VALID_REGIONS.has(reg) ? reg : '';
    const pr = p.get('preset') || '';
    appState.candPreset = VALID_PRESETS.has(pr) ? pr : '';
    const vw = p.get('view') || '';
    appState.candView = VALID_CAND_VIEWS.has(vw) ? vw : '';
    appState.candCity = (p.get('hcity') || '').slice(0, 30);
    appState.candTier = ['S', 'M', 'L'].includes(p.get('maxtier')) ? p.get('maxtier') : '';
    appState.candGenreInf = p.get('ginf') === '0' ? 'exclude' : '';
    const sortCol = p.get('sort') || '';
    const sortDir = p.get('dir') === 'asc' ? 'asc' : (p.get('dir') === 'desc' ? 'desc' : '');
    if (appState.candTab === 'debut') {
      appState.debutSort = {
        col: VALID_DEBUT_SORTS.has(sortCol) ? sortCol : 'score',
        dir: sortDir || (sortCol === 'display_name' ? 'asc' : 'desc'),
      };
    } else {
      appState.candSort = {
        col: VALID_CAND_SORTS.has(sortCol) ? sortCol : 'score',
        dir: sortDir || ((sortCol === 'display_name' || sortCol === 'next_gig_sort' || sortCol === 'genre_rank') ? 'asc' : 'desc'),
      };
    }
  } else if (appState.route === 'verify' && appState.verifyTab === 'scorecard') {
    const roleVal = p.get('role') || 'all';
    appState.scFilter = VALID_SC_FILTERS.has(roleVal) ? roleVal : 'all';
    const sortCol = p.get('sort') || '';
    const sortDir = p.get('dir') === 'asc' ? 'asc' : (p.get('dir') === 'desc' ? 'desc' : '');
    appState.scSort = {
      col: VALID_SC_SORTS.has(sortCol) ? sortCol : 'winners_seen',
      dir: sortDir || ((sortCol === 'label' || sortCol === 'role') ? 'asc' : 'desc'),
    };
  } else if (appState.route === 'venues') {
    appState.venuesCalMode = p.get('cal') === 'all' ? 'all' : 'cand';
    const snLim = Number(p.get('sn_limit'));
    appState.sceneNetLimit = VALID_SN_LIMITS.has(snLim) ? snLim : 150;
  } else if (appState.route === 'team') {
    appState.teamGraphPeriod = p.get('gp') === '1y' ? '1y' : 'all';
  } else if (appState.route === 'watchlist') {
    const wm = p.get('wmode');
    appState.watchModeParam = (wm === 'board' || wm === 'table') ? wm : null;
  }

  if (!queryPart) return;
  const c = appState.cfg;

  for (const key of WEIGHT_KEYS) {
    if (key === 'outlet_cap') continue;
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

/** 안쪽 경로 → 새 주소 경로(정보 구조 v2). 탭·도시·검색어처럼 경로에 들어가는 상태도 여기서. p 에는 쿼리로 남는 것만 넣는다. */
function publicPath(normRoute, param, verifyTab, p) {
  const enc = encodeURIComponent;
  const withTab = (base, tab, tabs) => (tab && tab !== 'overview' && tabs.includes(tab) ? `${base}/${tab}` : base);
  switch (normRoute) {
    case 'team':
      return param ? withTab(`#/team/${enc(param)}`, appState.teamTab, TEAM_TABS) : '#/discover';
    case 'venue':
      return param ? withTab(`#/venue/${enc(param)}`, appState.venueTab, VENUE_TABS) : '#/venues';
    case 'today':
      return '#/home';
    case 'candidates':
      return appState.candTab === 'debut' ? '#/charts/debut' : '#/discover';
    case 'charts': {
      const kind = CHART_KINDS.includes(appState.chartKind) ? appState.chartKind : 'all';
      if (kind === 'all') return '#/charts';
      return `#/charts/${kind}${appState.chartParam ? `/${enc(appState.chartParam)}` : ''}`;
    }
    case 'venues': {
      const vt = appState.venuesTab;
      if (vt === 'city') return appState.venuesCity ? `#/city/${enc(appState.venuesCity)}` : '#/cities';
      if (vt === 'festival') return appState.festivalName ? `#/festival/${enc(appState.festivalName)}` : '#/festivals';
      if (vt === 'list' || vt === 'network') return `#/venues/${vt}`;
      return appState.cfg.genre ? '#/venues/overview' : '#/venues';   // 장르가 있으면 '씬 네트워크'로 해석되지 않게 탭을 적음
    }
    case 'watchlist':
      if (appState.mineTab && appState.mineTab !== 'watch' && MINE_TABS.includes(appState.mineTab)) p.set('tab', appState.mineTab);
      return '#/mine';
    case 'alerts':
      return '#/alerts';
    case 'help':
      return '#/help';
    case 'search':
      if (appState.searchQuery) p.set('q', appState.searchQuery);
      return '#/search';
    case 'compare':
      return '#/compare';
    case 'verify':
      return `#/verify/${verifyTab}`;
    case 'quality':
    case 'sql':
      return `#/verify/${normRoute}`;
    default:
      return `#/${normRoute}`;
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
  for (const wk of WEIGHT_KEYS) {
    setIf(wk, c[wk], DEFAULT_WEIGHTS[wk]);
  }
  setIf('cutoffs', c.cutoffs, DEFAULTS.cutoffs);
  setIf('horizon_months', c.horizon_months, DEFAULTS.horizon_months);
  setIf('outcome_tier', c.outcome_tier, DEFAULTS.outcome_tier);
  setIf('k_list', c.k_list, DEFAULTS.k_list);
  setIf('compare_k', c.compare_k, DEFAULTS.compare_k);
  setIf('signal_cutoff', c.signal_cutoff, DEFAULTS.signal_cutoff);

  let normRoute = route;
  let normVerifyTab = appState.verifyTab || 'backtest';
  if (VERIFY_TABS.includes(route)) {
    normRoute = 'verify';
    normVerifyTab = route;
  }
  const basePath = publicPath(normRoute, param, normVerifyTab, p);

  // Serialize active view-specific filter & sort state so refresh/share preserves exact view
  if (normRoute === 'candidates') {
    if (appState.candQuery && appState.candQuery.trim()) p.set('q', appState.candQuery.trim());
    if (appState.candTab === 'debut') {
      const ds = appState.debutSort || { col: 'score', dir: 'desc' };
      if (ds.col !== 'score' || ds.dir !== 'desc') {
        p.set('sort', ds.col);
        p.set('dir', ds.dir);
      }
    } else {
      if (appState.candMove && VALID_MOVES.has(appState.candMove)) p.set('move', appState.candMove);
      if (appState.candStage && VALID_STAGES.has(appState.candStage)) p.set('stage', appState.candStage);
      if (appState.candReleaseMonths && VALID_RELEASE_MONTHS.has(Number(appState.candReleaseMonths))) {
        p.set('rm', String(appState.candReleaseMonths));
      }
      if (appState.candRegion && VALID_REGIONS.has(appState.candRegion)) p.set('region', appState.candRegion);
      if (appState.candPreset && VALID_PRESETS.has(appState.candPreset)) p.set('preset', appState.candPreset);
      if (appState.candView && VALID_CAND_VIEWS.has(appState.candView)) p.set('view', appState.candView);
      if (appState.candCity) p.set('hcity', appState.candCity);
      if (appState.candTier) p.set('maxtier', appState.candTier);
      if (appState.candGenreInf === 'exclude') p.set('ginf', '0');
      const cs = appState.candSort || { col: 'score', dir: 'desc' };
      if (cs.col !== 'score' || cs.dir !== 'desc') {
        p.set('sort', cs.col);
        p.set('dir', cs.dir);
      }
    }
  } else if (normRoute === 'verify' && normVerifyTab === 'scorecard') {
    if (appState.scFilter && appState.scFilter !== 'all') p.set('role', appState.scFilter);
    const ss = appState.scSort || { col: 'winners_seen', dir: 'desc' };
    if (ss.col !== 'winners_seen' || ss.dir !== 'desc') {
      p.set('sort', ss.col);
      p.set('dir', ss.dir);
    }
  } else if (normRoute === 'venues') {
    if (appState.venuesTab === 'network') {
      if (appState.sceneNetLimit && appState.sceneNetLimit !== 150) {
        p.set('sn_limit', String(appState.sceneNetLimit));
      }
    } else if (appState.venuesCalMode === 'all') {
      p.set('cal', 'all');
    }
  } else if (normRoute === 'team') {
    if (appState.teamGraphPeriod === '1y') p.set('gp', '1y');
  } else if (normRoute === 'watchlist') {
    const wm = appState.watchModeParam || getWatchlistViewMode();
    if (wm === 'board') p.set('wmode', 'board');
  }

  // 팀 미리보기(?peek=, components/team_peek.js)는 화면 상태가 아니라 주소에만 있으므로,
  // 같은 화면 주소를 다시 쓸 때(필터·정렬 변경)는 그대로 남긴다. 다른 화면으로 가면 빠진다.
  const curHash = typeof window !== 'undefined' ? String(window.location.hash || '') : '';
  const curPeek = new URLSearchParams(curHash.split('?')[1] || '').get('peek');
  if (curPeek && curHash.split('?')[0] === basePath) p.set('peek', curPeek);
  const qs = p.toString();
  if (normRoute === 'compare') {
    // teams 는 팀마다 따로 인코딩해 쉼표로 잇는다(URLSearchParams 로 넣으면 쉼표가 %2C 가 돼 키 안 쉼표와 구별이 안 됨)
    const base = compareHash(appState.compareKeys || []);
    return qs ? `${base}${base.includes('?') ? '&' : '?'}${qs}` : base;
  }
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
  if (appState.route && appState.route !== route) {
    appState.prevRoute = appState.route;
    appState.prevParam = appState.routeParam;
  }
  if (VERIFY_TABS.includes(route)) {
    appState.verifyTab = route;
    appState.route = 'verify';
    appState.routeParam = '';
  } else {
    if (route !== appState.route || param !== appState.routeParam) {
      if (route === 'team') appState.teamTab = 'overview';        // 다른 팀·공연장으로 가면 첫 탭부터
      if (route === 'venue') appState.venueTab = 'overview';
    }
    appState.route = route;
    appState.routeParam = param;
  }
  const next = buildHashUrl(appState.route, appState.routeParam);
  if (window.location.hash !== next) {
    window.location.hash = next;
  } else {
    window.dispatchEvent(new CustomEvent('app:route'));
  }
}

// ---------- Watchlist (localStorage with try/catch + optional 3-state status) ----------

let memWatchlist = [];
const VALID_WATCH_STATUS = new Set(WATCH_STATUSES.map(s => s.id));

function normalizeWatchItem(item) {
  return {
    team_key: item.team_key,
    display_name: item.display_name || item.team_key,
    added_at: item.added_at || '',
    status: VALID_WATCH_STATUS.has(item.status) ? item.status : 'watching',
  };
}

export function getWatchlist() {
  try {
    const raw = window.localStorage.getItem(WATCH_KEY);
    if (!raw) return memWatchlist.map(normalizeWatchItem);
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) {
      memWatchlist = parsed.filter(item => item && typeof item.team_key === 'string').map(normalizeWatchItem);
      return [...memWatchlist];
    }
  } catch (_) {}
  return memWatchlist.map(normalizeWatchItem);
}

function saveWatchlist(list) {
  memWatchlist = list.map(normalizeWatchItem);
  try {
    window.localStorage.setItem(WATCH_KEY, JSON.stringify(memWatchlist));
  } catch (_) {}
  window.dispatchEvent(new CustomEvent('app:watchlist'));
}

export function isWatched(teamKey) {
  return getWatchlist().some(it => it.team_key === teamKey);
}

export function getWatchStatus(teamKey) {
  const found = getWatchlist().find(it => it.team_key === teamKey);
  return found ? found.status : 'watching';
}

export function setWatchStatus(teamKey, status) {
  if (!VALID_WATCH_STATUS.has(status)) return;
  const list = getWatchlist();
  const idx = list.findIndex(it => it.team_key === teamKey);
  if (idx < 0) return;
  list[idx] = { ...list[idx], status };
  saveWatchlist(list);
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
      status: 'watching',
    });
    added = true;
  }
  saveWatchlist(list);
  return added;
}

export function getWatchlistViewMode() {
  try {
    const v = window.localStorage.getItem(WATCH_VIEW_KEY);
    if (v === 'board' || v === 'table') return v;
  } catch (_) {}
  return 'table';
}

export function setWatchlistViewMode(mode) {
  if (mode !== 'board' && mode !== 'table') return;
  try {
    window.localStorage.setItem(WATCH_VIEW_KEY, mode);
  } catch (_) {}
}

// ---------- Unified CSV Export ----------

export function exportTableToCsv(filename, headers, rows) {
  const esc = v => {
    const s = String(v ?? '');
    return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const lines = [headers.map(esc).join(',')];
  for (const row of rows) {
    lines.push(row.map(esc).join(','));
  }
  const blob = new Blob(['\ufeff' + lines.join('\n')], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export function exportWatchlistCsv(rows) {
  const statusMap = Object.fromEntries(WATCH_STATUSES.map(s => [s.id, s.label]));
  const headers = ['team_key', 'display_name', 'status', 'score', 'rank_now', 'rank_delta', 'recent_7d_signals', 'last_seen', 'added_at'];
  const csvRows = rows.map(r => [
    r.team_key,
    r.display_name,
    statusMap[r.status] || '지켜보는 중',
    r.score ?? '',
    r.rank_now ?? '',
    r.rank_delta ?? '',
    r.recent_7d ?? 0,
    r.last_seen ?? '',
    r.added_at ?? '',
  ]);
  exportTableToCsv(`crate_digger_watchlist_${appState.dataEnd || 'export'}.csv`, headers, csvRows);
}

const PLATFORM_KEY = 'crate_digger_platform_v1';
const VALID_PLATFORMS = ['spotify', 'youtube'];

export function getPreferredPlatform() {
  try {
    const v = window.localStorage.getItem(PLATFORM_KEY);
    if (v && VALID_PLATFORMS.includes(v)) return v;
  } catch (_) {}
  return 'spotify';
}

export function setPreferredPlatform(platform) {
  if (!VALID_PLATFORMS.includes(platform)) return;
  try {
    window.localStorage.setItem(PLATFORM_KEY, platform);
  } catch (_) {}
}

// ---------- Table Density (2-6: compact default | comfortable) ----------

const TABLE_DENSITY_KEY = 'cd_table_density_v1';
let memoryTableDensity = 'compact';

export function getTableDensity() {
  try {
    const v = window.localStorage.getItem(TABLE_DENSITY_KEY);
    if (v === 'compact' || v === 'comfortable') {
      memoryTableDensity = v;
      return v;
    }
  } catch (_) {}
  return memoryTableDensity;
}

export function setTableDensity(mode) {
  if (mode !== 'compact' && mode !== 'comfortable') return;
  memoryTableDensity = mode;
  try {
    window.localStorage.setItem(TABLE_DENSITY_KEY, mode);
  } catch (_) {}
}
