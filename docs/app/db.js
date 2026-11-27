import * as duckdb from 'https://cdn.jsdelivr.net/npm/@duckdb/duckdb-wasm@1.32.0/+esm';
import { ALL_BRANCHES, appState, DEFAULT_WEIGHTS } from './state.js';

const DUCKDB_CDN = 'https://cdn.jsdelivr.net/npm/@duckdb/duckdb-wasm@1.32.0/dist';
const MANUAL_BUNDLES = {
  mvp: {
    mainModule: `${DUCKDB_CDN}/duckdb-mvp.wasm`,
    mainWorker: `${DUCKDB_CDN}/duckdb-browser-mvp.worker.js`,
  },
  eh: {
    mainModule: `${DUCKDB_CDN}/duckdb-eh.wasm`,
    mainWorker: `${DUCKDB_CDN}/duckdb-browser-eh.worker.js`,
  },
};

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const VERSIONED_PREFIXES = ['lab/data/', 'lab/sql/', 'data/', 'score_tuning.md'];

let dbInstance = null;
let connInstance = null;
let assetVersion = '';
let macroReloadAttempted = false;
let macroReloadPromise = null;

// Raw optional CSV texts kept for lazy DuckDB table creation when #/sql opens
let rawAuxCsv = { links: null, videos: null, images: null };
let auxTablesCreated = false;
let auxTablesPromise = null;

// Bounded LRU query caches (cleared on bootstrap / macro reload)
const QUERY_CACHE_MAX = 20;
const candidatesCache = new Map();       // keyWithoutLimit -> { limit, rows }
const debutCandidatesCache = new Map();  // sql -> result
const upcomingGigsCache = new Map();     // asOf::days -> rows
const weeklySignalsCache = new Map();    // start::end -> { total, byBranch }
const teamDetailCache = new Map();       // teamKey::scoreParams -> detail
const egoNetCache = new Map();           // teamKey::period::limit -> rows
const sceneNetCache = new Map();         // sql -> result
const backtestCache = new Map();         // sqlKey -> blocks
const signalHitsCache = new Map();       // sql -> { cutoff, rows }
const scorecardCache = new Map();        // sql -> result
const discoveryStageCache = new Map();   // sql -> { rows, byTeam }
const rankChangeCache = new Map();       // sql -> { rows, byTeam, nowDate, weekDate, monthDate }
const risingPresetCache = new Map();     // sql -> rows
const venueShowsCache = new Map();       // venue::limit -> rows
const pendingGigs1yCache = new Map();    // asOf -> Map<team_key, count>
let teamLastSeenCache = null;            // Map<team_key, isoDate>
const sqlTemplatePromises = new Map();   // name -> Promise<string>

function lruGet(map, key) {
  if (!map.has(key)) return undefined;
  const val = map.get(key);
  map.delete(key);
  map.set(key, val);
  return val;
}

function lruSet(map, key, val, max = QUERY_CACHE_MAX) {
  if (map.has(key)) map.delete(key);
  map.set(key, val);
  if (map.size > max) {
    const oldest = map.keys().next().value;
    map.delete(oldest);
  }
}

function clearQueryCaches() {
  candidatesCache.clear();
  debutCandidatesCache.clear();
  upcomingGigsCache.clear();
  weeklySignalsCache.clear();
  teamDetailCache.clear();
  egoNetCache.clear();
  sceneNetCache.clear();
  backtestCache.clear();
  signalHitsCache.clear();
  scorecardCache.clear();
  discoveryStageCache.clear();
  rankChangeCache.clear();
  risingPresetCache.clear();
  venueShowsCache.clear();
  pendingGigs1yCache.clear();
  teamLastSeenCache = null;
}

function localTodayIso() {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

// ---------- Arrow JS value normalization ----------

function decodeArrowDecimal(raw, scale) {
  if (typeof raw === 'number') return raw / Math.pow(10, scale);
  if (typeof raw === 'bigint') return Number(raw) / Math.pow(10, scale);
  if (raw && raw.length >= 4 && typeof raw[0] === 'number') {
    const negative = (raw[raw.length - 1] & 0x80000000) !== 0;
    let val = 0n;
    for (let i = raw.length - 1; i >= 0; i--) {
      const word = BigInt(negative ? (~raw[i] >>> 0) : (raw[i] >>> 0));
      val = (val << 32n) + word;
    }
    if (negative) val = -(val + 1n);
    return Number(val) / Math.pow(10, scale);
  }
  const parsed = Number(raw);
  return Number.isNaN(parsed) ? null : parsed;
}

function formatArrowValue(val, field) {
  if (val === null || val === undefined) return null;
  const typeStr = field && field.type ? String(field.type) : '';
  if (typeStr.includes('Decimal')) {
    return decodeArrowDecimal(val, field.type.scale || 0);
  }
  if (typeStr.includes('Date')) {
    if (val instanceof Date) return val.toISOString().slice(0, 10);
    if (typeof val === 'number' || typeof val === 'bigint') {
      const n = Number(val);
      const ms = Math.abs(n) < 1000000 ? n * 86400000 : n;
      return new Date(ms).toISOString().slice(0, 10);
    }
    return String(val).slice(0, 10);
  }
  if (typeof val === 'bigint') return Number(val);
  return val;
}

function arrowToRows(table) {
  const fields = table.schema.fields;
  const numRows = table.numRows;
  const cols = fields.map((f, idx) => ({ field: f, vec: table.getChildAt(idx) }));
  const rows = new Array(numRows);
  for (let r = 0; r < numRows; r++) {
    const obj = {};
    for (let c = 0; c < cols.length; c++) {
      obj[cols[c].field.name] = formatArrowValue(cols[c].vec.get(r), cols[c].field);
    }
    rows[r] = obj;
  }
  return { columns: fields.map(f => f.name), rows };
}

function isLabScoredError(sql, err) {
  if (!sql || !String(sql).includes('lab_scored')) return false;
  const msg = String(err?.message || err || '');
  return /lab_scored|does not support the supplied arguments|Macro/i.test(msg);
}

async function reloadLabMacrosOnce() {
  if (macroReloadPromise) return macroReloadPromise;
  if (macroReloadAttempted) return false;
  macroReloadAttempted = true;
  macroReloadPromise = (async () => {
    try {
      const reloadOpts = { cache: 'reload', bust: true };
      const loadedNames = Object.keys(appState.sqlTemplates).filter(k => k !== 'features' && appState.sqlTemplates[k]);
      const [featSql, ...others] = await Promise.all([
        fetchText('lab/sql/features.sql', false, reloadOpts),
        ...loadedNames.map(k => fetchText(`lab/sql/${k}.sql`, true, reloadOpts)),
      ]);
      if (!featSql) return false;
      await connInstance.query(featSql);
      appState.sqlTemplates.features = featSql;
      loadedNames.forEach((k, i) => {
        if (others[i]) appState.sqlTemplates[k] = others[i];
      });
      clearQueryCaches();
      return true;
    } catch (_) {
      return false;
    } finally {
      macroReloadPromise = null;
    }
  })();
  return macroReloadPromise;
}

export async function getSqlTemplate(name) {
  if (!name) return '';
  if (appState.sqlTemplates[name]) return appState.sqlTemplates[name];
  if (sqlTemplatePromises.has(name)) return sqlTemplatePromises.get(name);
  const p = (async () => {
    const txt = await fetchText(`lab/sql/${name}.sql`, true);
    if (txt) appState.sqlTemplates[name] = txt;
    return txt || '';
  })();
  sqlTemplatePromises.set(name, p);
  try {
    return await p;
  } finally {
    sqlTemplatePromises.delete(name);
  }
}

export async function runRawSql(sql) {
  if (!connInstance) throw new Error('DuckDB-WASM이 아직 초기화되지 않았습니다.');
  try {
    const res = await connInstance.query(sql);
    return arrowToRows(res);
  } catch (err) {
    if ((!macroReloadAttempted || macroReloadPromise) && isLabScoredError(sql, err)) {
      const reloaded = await reloadLabMacrosOnce();
      if (reloaded) {
        const res = await connInstance.query(sql);
        return arrowToRows(res);
      }
    }
    throw err;
  }
}

// ---------- Strict placeholder validation ----------

function sqlDate(val, fallback) {
  const s = typeof val === 'string' && DATE_RE.test(val) ? val : fallback;
  return `'${s}'`;
}

function sqlInt(val, min, max, fallback) {
  const n = Number(val);
  if (!Number.isFinite(n)) return String(fallback);
  return String(Math.max(min, Math.min(max, Math.round(n))));
}

function sqlNum(val, min, max, fallback) {
  const n = Number(val);
  if (!Number.isFinite(n)) return String(fallback);
  const clamped = Math.max(min, Math.min(max, n));
  return String(Math.round(clamped * 1000) / 1000);
}

function sqlBool(val) {
  return val ? 'true' : 'false';
}

function sqlTier(val) {
  return `'${['any', 'final', 'mid'].includes(val) ? val : 'any'}'`;
}

function sqlGenre(val) {
  if (!val || !appState.validGenres.includes(val)) return "''";
  return `'${val.replace(/'/g, "''")}'`;
}

function sqlBranches(list) {
  const clean = (Array.isArray(list) ? list : []).filter(b => ALL_BRANCHES.includes(b));
  const use = clean.length ? clean : ALL_BRANCHES;
  return `[${use.map(b => `'${b}'`).join(',')}]`;
}

function sqlKList(list) {
  const nums = [...new Set((Array.isArray(list) ? list : [])
    .map(n => Math.round(Number(n)))
    .filter(n => Number.isFinite(n) && n >= 1 && n <= 5000))]
    .sort((a, b) => a - b);
  return `[${(nums.length ? nums : [20, 50, 100, 200]).join(',')}]`;
}

export function sqlStringLiteral(val) {
  return `'${String(val ?? '').replace(/'/g, "''")}'`;
}

export function fillTemplate(tpl, map) {
  let out = tpl;
  for (const [k, v] of Object.entries(map)) {
    out = out.split(`{{${k}}}`).join(v);
  }
  return out;
}

/** @param {object} [cfg] 기본은 지금 화면 설정 — 저장 필터는 저장해 둔 설정을 넘긴다 */
export function buildParams(overrides = {}, cfg = appState.cfg) {
  const c = cfg;
  const fallbackAsOf = appState.dataEnd || '2026-11-27';
  return {
    cutoff: sqlDate(overrides.cutoff || c.cutoffs[0] || '2025-01-01', '2025-01-01'),
    as_of: sqlDate(overrides.as_of || c.as_of, fallbackAsOf),
    lookback_years: sqlInt(c.lookback_years, 1, 15, 3),
    newcomer_years: sqlInt(c.newcomer_years, 1, 15, 3),
    exclude_famous: sqlBool(c.exclude_famous),
    outcome_tier: sqlTier(c.outcome_tier),
    horizon_months: sqlInt(c.horizon_months, 1, 60, 24),
    genre: sqlGenre(overrides.genre !== undefined ? overrides.genre : c.genre),
    branches: sqlBranches(c.branches),
    w_branch: sqlNum(c.w_branch, 0, 10, DEFAULT_WEIGHTS.w_branch),
    w_stage: sqlNum(c.w_stage, 0, 10, DEFAULT_WEIGHTS.w_stage),
    w_peer: sqlNum(c.w_peer, 0, 10, DEFAULT_WEIGHTS.w_peer),
    w_dmz: sqlNum(c.w_dmz, 0, 10, DEFAULT_WEIGHTS.w_dmz),
    w_gigs: sqlNum(c.w_gigs, 0, 10, DEFAULT_WEIGHTS.w_gigs),
    w_outlets: sqlNum(c.w_outlets, 0, 10, DEFAULT_WEIGHTS.w_outlets),
    outlet_cap: sqlInt(c.outlet_cap, 1, 10, DEFAULT_WEIGHTS.outlet_cap),
    w_recent: sqlNum(c.w_recent, 0, 10, DEFAULT_WEIGHTS.w_recent),
    w_venues: sqlNum(c.w_venues, 0, 10, DEFAULT_WEIGHTS.w_venues),
    w_winner: sqlNum(c.w_winner, 0, 10, DEFAULT_WEIGHTS.w_winner),
    w_context: sqlNum(c.w_context, 0, 10, DEFAULT_WEIGHTS.w_context),
    w_collab: sqlNum(c.w_collab, 0, 10, DEFAULT_WEIGHTS.w_collab),
    k_list: sqlKList(c.k_list),
    only_no_outcome: sqlBool(overrides.only_no_outcome !== undefined ? overrides.only_no_outcome : c.only_no_outcome),
    limit: sqlInt(overrides.limit !== undefined ? overrides.limit : c.limit, 10, 1000, 100),
    team_key: sqlStringLiteral(overrides.team_key || ''),
  };
}

// ---------- Bootstrap ----------

function resolveFetchUrl(path, bust = true) {
  if (!bust || !assetVersion) return path;
  if (!VERSIONED_PREFIXES.some(prefix => path.startsWith(prefix))) return path;
  const sep = path.includes('?') ? '&' : '?';
  return `${path}${sep}v=${encodeURIComponent(assetVersion)}`;
}

export async function fetchText(path, optional = false, opts = {}) {
  const { cache, bust = true } = opts;
  const url = resolveFetchUrl(path, bust);
  const init = cache ? { cache } : undefined;
  try {
    const r = await fetch(url, init);
    if (!r.ok) {
      if (optional) return null;
      throw new Error(`${path} 불러오기 실패 (HTTP ${r.status})`);
    }
    return r.text();
  } catch (err) {
    if (optional) return null;
    throw err;
  }
}

export async function fetchJson(path, optional = false, opts = {}) {
  const { cache, bust = true } = opts;
  const url = resolveFetchUrl(path, bust);
  const init = cache ? { cache } : undefined;
  try {
    const r = await fetch(url, init);
    if (!r.ok) {
      if (optional) return null;
      throw new Error(`${path} 불러오기 실패 (HTTP ${r.status})`);
    }
    return await r.json();
  } catch (err) {
    if (optional) return null;
    throw err;
  }
}

/**
 * 스냅샷 목록에서 비교 기준(prevDate)을 고른다.
 * 최신 날짜에서 7일 이상 이전(<= latest - 7일) 중 가장 늦은 스냅샷을 선택하고,
 * 없으면 바로 앞 스냅샷으로 폴백한다.
 */
export function pickWeeklyPrevSnapshot(dates, latestDate = null) {
  const sorted = [...new Set((Array.isArray(dates) ? dates : []).map(d => String(d || '').trim()).filter(d => DATE_RE.test(d)))]
    .sort((a, b) => b.localeCompare(a));
  if (!sorted.length) return { latestDate: null, prevDate: null };
  const latest = (latestDate && DATE_RE.test(latestDate)) ? latestDate : sorted[0];
  const earlier = sorted.filter(d => d < latest);
  if (!earlier.length) return { latestDate: latest, prevDate: null };
  const targetMs = Date.parse(`${latest}T00:00:00Z`) - 7 * 86400000;
  const targetStr = new Date(targetMs).toISOString().slice(0, 10);
  const atLeast7d = earlier.find(d => d <= targetStr);
  return { latestDate: latest, prevDate: atLeast7d || earlier[earlier.length - 1] };
}

function parseSnapshotCsv(text) {
  const map = new Map();
  if (!text) return map;
  const lines = text.trim().split(/\r?\n/);
  for (let i = 1; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line) continue;
    // team_key,score,rank (team_key has no commas in normalized key, handle quoted safely)
    let key = '', score = 0, rank = 0;
    if (line.startsWith('"')) {
      const m = line.match(/^"((?:""|[^"])*)",([^,]+),([^,]+)$/);
      if (!m) continue;
      key = m[1].replace(/""/g, '"');
      score = Number(m[2]);
      rank = Number(m[3]);
    } else {
      const parts = line.split(',');
      if (parts.length < 3) continue;
      key = parts[0];
      score = Number(parts[1]);
      rank = Number(parts[2]);
    }
    if (key) map.set(key, { team_key: key, score, rank });
  }
  return map;
}

async function initEngine() {
  const bundle = await duckdb.selectBundle(MANUAL_BUNDLES);
  const workerCode = `importScripts("${bundle.mainWorker}");`;
  const workerUrl = URL.createObjectURL(new Blob([workerCode], { type: 'text/javascript' }));
  const worker = new Worker(workerUrl);
  const logger = new duckdb.ConsoleLogger(duckdb.LogLevel.WARNING);
  const db = new duckdb.AsyncDuckDB(logger, worker);
  await db.instantiate(bundle.mainModule, bundle.pthreadWorker);
  URL.revokeObjectURL(workerUrl);
  const conn = await db.connect();
  dbInstance = db;
  connInstance = conn;
}

const VIDEO_ID_RE = /^[A-Za-z0-9_-]{11}$/;
const VIDEO_KIND_ORDER = { stage: 0, official_live: 1, official: 2, search: 3 };

/**
 * images.csv(team_key,url,source) → { urlMap, metaMap }.
 * 스포티파이 아티스트 사진(i.scdn.co)만 허용하며, 없으면 화면에서 모노그램으로 표시한다.
 */
function parseImagesCsv(text) {
  const urlMap = new Map();
  const metaMap = new Map();
  if (!text) return { urlMap, metaMap };
  const lines = text.trim().split(/\r?\n/).slice(1);
  const row = /^(.*),(https:\/\/i\.scdn\.co\/[^\s,]+),([^,]*)$/;
  for (const line of lines) {
    const m = line.match(row);
    if (!m) continue;
    const teamKey = m[1].replace(/^"(.*)"$/, '$1').replace(/""/g, '"');
    const url = m[2];
    const source = (m[3] || '').trim().toLowerCase() || 'spotify';
    if (!teamKey || urlMap.has(teamKey)) continue;
    urlMap.set(teamKey, url);
    metaMap.set(teamKey, { url, source });
  }
  return { urlMap, metaMap };
}

export function parseCsvObjects(text) {
  if (!text) return [];
  const rows = [];
  let row = [];
  let field = '';
  let inQuotes = false;
  const n = text.length;
  for (let i = 0; i < n; i++) {
    const ch = text[i];
    if (inQuotes) {
      if (ch === '"') {
        if (i + 1 < n && text[i + 1] === '"') {
          field += '"';
          i += 1;
        } else {
          inQuotes = false;
        }
      } else {
        field += ch;
      }
    } else if (ch === '"') {
      inQuotes = true;
    } else if (ch === ',') {
      row.push(field);
      field = '';
    } else if (ch === '\r') {
      if (i + 1 < n && text[i + 1] === '\n') i += 1;
      row.push(field);
      field = '';
      if (row.length > 1 || row[0] !== '') rows.push(row);
      row = [];
    } else if (ch === '\n') {
      row.push(field);
      field = '';
      if (row.length > 1 || row[0] !== '') rows.push(row);
      row = [];
    } else {
      field += ch;
    }
  }
  if (field !== '' || row.length > 0) {
    row.push(field);
    if (row.length > 1 || row[0] !== '') rows.push(row);
  }
  if (rows.length < 2) return [];
  const headers = rows[0].map(h => h.replace(/^\uFEFF/, '').trim());
  const out = new Array(rows.length - 1);
  for (let r = 1; r < rows.length; r++) {
    const vals = rows[r];
    const obj = {};
    for (let c = 0; c < headers.length; c++) {
      obj[headers[c]] = vals[c] !== undefined ? vals[c] : '';
    }
    out[r - 1] = obj;
  }
  return out;
}

function parseTeamsCsvIndex(text) {
  const rows = parseCsvObjects(text);
  const genreCounts = new Map();
  const teamIndex = [];
  const newcomerCheckByTeam = new Map();
  const firstReleaseByTeam = new Map();
  const genreConfidenceByTeam = new Map();
  for (const r of rows) {
    const team_key = r.team_key || '';
    if (!team_key) continue;
    const display_name = r.display_name || team_key;
    const primary_genre = r.primary_genre || '';
    teamIndex.push({ team_key, display_name, primary_genre });
    if (primary_genre) {
      genreCounts.set(primary_genre, (genreCounts.get(primary_genre) || 0) + 1);
    }
    if (Object.prototype.hasOwnProperty.call(r, 'newcomer_check')) {
      const nc = String(r.newcomer_check || '').trim().toLowerCase();
      if (nc) newcomerCheckByTeam.set(team_key, nc);
    }
    if (r.first_release) {
      const fr = String(r.first_release).trim().slice(0, 10);
      if (DATE_RE.test(fr)) firstReleaseByTeam.set(team_key, fr);
    }
    if (Object.prototype.hasOwnProperty.call(r, 'genre_confidence')) {
      const gc = String(r.genre_confidence || '').trim().toLowerCase();
      if (gc) genreConfidenceByTeam.set(team_key, gc);
    }
  }
  teamIndex.sort((a, b) => (a.display_name < b.display_name ? -1 : a.display_name > b.display_name ? 1 : 0));
  const validGenres = [...genreCounts.entries()]
    .sort((a, b) => (b[1] - a[1]) || (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0))
    .map(e => e[0]);
  return { teamIndex, validGenres, newcomerCheckByTeam, firstReleaseByTeam, genreConfidenceByTeam };
}

function parseProgramsCsvMap(text) {
  const rows = parseCsvObjects(text);
  const map = new Map();
  for (const r of rows) {
    if (r.program && r.label) map.set(r.program, r.label);
  }
  return map;
}

function indexLinksRows(rows) {
  const map = new Map();
  for (const r of rows) {
    const k = r.team_key;
    const plat = r.platform;
    const url = r.url;
    if (!k || !plat || typeof url !== 'string' || !url.startsWith('https://')) continue;
    if (!map.has(k)) map.set(k, new Map());
    map.get(k).set(plat, url);
  }
  return map;
}

function indexVideosRows(rows) {
  const map = new Map();
  for (const r of rows) {
    const k = r.team_key;
    const vid = String(r.video_id || '').trim();
    if (!k || !VIDEO_ID_RE.test(vid)) continue;
    if (!map.has(k)) map.set(k, []);
    map.get(k).push({
      video_id: vid,
      title: String(r.title || ''),
      channel_title: String(r.channel_title || ''),
      published_at: String(r.published_at || ''),
      kind: String(r.kind || 'search'),
    });
  }
  return map;
}

export const DROP_CHECK_TABLES = new Set(['raw_kr_gig', 'raw_press', 'raw_kr_release']);

export const COLLECT_TABLE_LABELS = {
  raw_kr_gig: '공연 수집',
  raw_press: '기사 수집',
  raw_kr_release: '발매 수집',
  raw_kr_selection: '선정·지원 수집',
  raw_artist_profile: '프로필 수집',
  raw_outcome: '정답 기록',
};

export function formatRunLabel(r) {
  const src = r?.source || '알 수 없는 소스';
  const tbl = COLLECT_TABLE_LABELS[String(r?.table || '')];
  return tbl ? `${tbl}(${src})` : src;
}

export function isRunDropped(r) {
  if (!r || r.prev_rows === null || r.prev_rows === undefined) return false;
  const prev = Number(r.prev_rows);
  const cur = Number(r.rows);
  return DROP_CHECK_TABLES.has(String(r.table || '')) && prev >= 20 && cur < prev * 0.3;
}

/**
 * 자동 데이터 이상 점검 (collect.json + dashboard.json + meta.json).
 * 정상일 때는 배너를 띄우지 않고, 이상이 있을 때만 전 화면 상단에 자동 표시한다.
 */
export function computeDataHealth(meta = appState.meta, collect = appState.collectJson, dash = appState.dashboardJson) {
  const issues = [];
  let severity = 'ok';
  const pushIssue = (sev, msg) => {
    issues.push({ severity: sev, message: msg });
    if (sev === 'error') severity = 'error';
    else if (severity === 'ok') severity = 'warn';
  };

  // 1) collect.json runs check (per table+source: file_ok === false, rows === 0, or prev_rows sudden drop)
  //    - 매일 전체 적재 표(raw_kr_gig, raw_press, raw_kr_release): 0행 즉시 주의 + prev_rows ≥ 20 & <30% 급감 판정
  //    - 증분/수동 표(raw_artist_profile, raw_outcome 등): 급감 판정 제외, 0행이 3일 연속일 때만 주의
  const runs = Array.isArray(collect?.runs) ? collect.runs : [];
  let totalSources = 0;
  let okSources = 0;
  let lastCollectedDate = '';
  if (runs.length) {
    const runsByKey = new Map();
    for (const r of runs) {
      const dateStr = String(r.date || '');
      if (dateStr > lastCollectedDate) lastCollectedDate = dateStr;
      const key = `${r.table || ''}::${r.source || ''}`;
      if (!runsByKey.has(key)) runsByKey.set(key, []);
      runsByKey.get(key).push(r);
    }
    totalSources = runsByKey.size;
    const failed = [];
    const zeroRows = [];
    const dropped = [];
    for (const list of runsByKey.values()) {
      list.sort((a, b) => String(b.date || '').localeCompare(String(a.date || '')));
      const latest = list[0];
      const label = formatRunLabel(latest);
      const isDailyFull = DROP_CHECK_TABLES.has(String(latest.table || ''));
      if (latest.file_ok === false) {
        failed.push(label);
      } else if (Number(latest.rows) === 0) {
        if (isDailyFull) {
          zeroRows.push(label);
        } else {
          // 증분/수동 표는 최근 3회 연속 0행일 때만 주의
          const recent3 = list.slice(0, 3);
          if (recent3.length >= 3 && recent3.every(x => Number(x.rows) === 0)) {
            zeroRows.push(`${label} 3일 연속`);
          } else {
            okSources += 1;
          }
        }
      } else {
        okSources += 1;
        if (isRunDropped(latest)) {
          dropped.push(`${label} ${latest.prev_rows}→${latest.rows}`);
        }
      }
    }
    if (failed.length) {
      pushIssue('error', `수집 파일 오류 ${failed.length}건 (${failed.slice(0, 3).join(', ')})`);
    }
    if (zeroRows.length) {
      pushIssue('warn', `수집 건수 0건 소스 ${zeroRows.length}곳 (${zeroRows.slice(0, 3).join(', ')})`);
    }
    if (dropped.length) {
      pushIssue('warn', `평소 대비 수집량 급감: ${dropped.slice(0, 3).join(', ')}`);
    }
  } else if (collect?.generated) {
    lastCollectedDate = String(collect.generated).slice(0, 10);
  }

  // 1b) meta.json prev_rows core table drop check
  if (meta?.prev_rows && meta?.rows) {
    for (const [k, label] of [['signals', '신호'], ['teams', '팀'], ['outcomes', '정답']]) {
      const prev = Number(meta.prev_rows[k] || 0);
      const cur = Number(meta.rows[k] || 0);
      if (prev >= 50 && cur < prev * 0.8) {
        pushIssue('warn', `${label} 행 수가 직전(${prev}) 대비 크게 줄었습니다(${cur})`);
      }
    }
  }

  // 2) dashboard.json errors & error-level quality checks & monthly gig volume drop
  const dashErrors = Array.isArray(dash?.errors) ? dash.errors : [];
  if (dashErrors.length) {
    pushIssue('error', `대시보드 집계 오류 ${dashErrors.length}건`);
  }

  const qualityRows = Array.isArray(dash?.sections?.quality) ? dash.sections.quality : [];
  const qualErrors = qualityRows.filter(q => q.level === 'error');
  if (qualErrors.length) {
    pushIssue('error', `품질 오류 ${qualErrors.length}건 (${qualErrors[0].item || ''})`);
  }

  const gigsByMonth = Array.isArray(dash?.sections?.gigs_by_month) ? dash.sections.gigs_by_month : [];
  if (gigsByMonth.length >= 5) {
    // Compare latest completed month (second-to-last if last is current in-progress month) against prior 3 months
    const dataMonth = String(meta?.data_end || '').slice(0, 7);
    const completed = gigsByMonth.filter(m => m.month && (!dataMonth || m.month < dataMonth));
    if (completed.length >= 4) {
      const latestM = completed[completed.length - 1];
      const prior3 = completed.slice(-4, -1);
      const avg3 = prior3.reduce((acc, m) => acc + (Number(m.gigs) || 0), 0) / 3;
      if (avg3 >= 30 && (Number(latestM.gigs) || 0) < avg3 * 0.5) {
        pushIssue('warn', `${latestM.month} 공연 수집량(${latestM.gigs}건)이 직전 3개월 평균(${Math.round(avg3)}건) 대비 50% 이상 감소`);
      }
    }
  }

  // 3) Staleness check (> 3 days behind current date or > 3 days mismatch between collect and data_end)
  const dataEndStr = meta?.data_end || '';
  if (dataEndStr && /^\d{4}-\d{2}-\d{2}$/.test(dataEndStr)) {
    const endMs = Date.parse(`${dataEndStr}T00:00:00Z`);
    const nowMs = Date.now();
    const diffDays = Math.floor((nowMs - endMs) / 86400000);
    if (diffDays > 3) {
      pushIssue('warn', `데이터 갱신이 ${diffDays}일째 멈춰 있습니다 (마지막 기준일 ${dataEndStr})`);
    }
    if (lastCollectedDate && /^\d{4}-\d{2}-\d{2}$/.test(lastCollectedDate)) {
      const collMs = Date.parse(`${lastCollectedDate}T00:00:00Z`);
      const gap = Math.abs(Math.floor((endMs - collMs) / 86400000));
      if (gap > 3) {
        pushIssue('warn', `수집일(${lastCollectedDate})과 분석 기준일(${dataEndStr}) 차이가 ${gap}일입니다`);
      }
    }
  }

  const ok = issues.length === 0;
  const summaryLabel = ok
    ? (totalSources > 0 ? `수집 정상 (${okSources}/${totalSources})` : '수집 정상')
    : `수집 확인 필요 (${issues.length}건)`;

  return {
    ok,
    severity,
    issues,
    totalSources,
    okSources,
    lastCollectedDate,
    summaryLabel,
  };
}

export async function ensureAuxDuckDbTables() {
  if (auxTablesCreated || !dbInstance || !connInstance) return;
  if (auxTablesPromise) return auxTablesPromise;
  auxTablesPromise = (async () => {
    const reg = [];
    let sql = '';
    if (rawAuxCsv.links) {
      reg.push(dbInstance.registerFileText('links.csv', rawAuxCsv.links));
      sql += `CREATE TABLE IF NOT EXISTS links AS SELECT * FROM read_csv_auto('links.csv', header=true);`;
    }
    if (rawAuxCsv.videos) {
      reg.push(dbInstance.registerFileText('videos.csv', rawAuxCsv.videos));
      sql += `CREATE TABLE IF NOT EXISTS videos AS SELECT * FROM read_csv_auto('videos.csv', header=true);`;
    }
    if (rawAuxCsv.images) {
      reg.push(dbInstance.registerFileText('images.csv', rawAuxCsv.images));
      sql += `CREATE TABLE IF NOT EXISTS images AS SELECT * FROM read_csv_auto('images.csv', header=true);`;
    }
    if (reg.length) {
      await Promise.all(reg);
      await connInstance.query(sql);
    }
    auxTablesCreated = true;
  })();
  try {
    await auxTablesPromise;
  } finally {
    auxTablesPromise = null;
  }
}

export async function bootstrapData(onStatus = () => {}) {
  onStatus('데이터·SQL·DuckDB-WASM 불러오는 중...');
  const enginePromise = initEngine();
  const meta = await fetchJson('lab/data/meta.json', false, { cache: 'no-store', bust: false });
  assetVersion = meta?.generated_at ? String(meta.generated_at) : String(Date.now());
  macroReloadAttempted = false;
  macroReloadPromise = null;
  auxTablesCreated = false;
  auxTablesPromise = null;
  clearQueryCaches();

  const hasLinksMeta = !meta?.rows || meta.rows.links === undefined || meta.rows.links > 0;
  const hasVideosMeta = Boolean(meta?.rows && Number(meta.rows.videos) > 0);
  const hasImagesMeta = Boolean(meta?.rows && Number(meta.rows.images) > 0);

  // Chain snapshot CSV fetches right after snapshots/index.json so there is no post-DB waterfall
  const snapBundlePromise = fetchJson('lab/data/snapshots/index.json', true).then(async (snapIdx) => {
    const snapDates = Array.isArray(snapIdx?.dates) ? snapIdx.dates : [];
    const snapReconstructed = Array.isArray(snapIdx?.reconstructed) ? snapIdx.reconstructed : [];
    const { latestDate, prevDate } = pickWeeklyPrevSnapshot(snapDates);
    let monthDate = null;
    if (latestDate) {
      const target30 = new Date(Date.parse(`${latestDate}T00:00:00Z`) - 30 * 86400000).toISOString().slice(0, 10);
      const sorted = [...new Set(snapDates.map(d => String(d || '').trim()).filter(d => DATE_RE.test(d)))]
        .sort((a, b) => b.localeCompare(a));
      const candMonth = sorted.find(d => d <= target30) || null;
      if (candMonth && candMonth !== latestDate && candMonth !== prevDate) {
        monthDate = candMonth;
      }
    }
    const [latestTxt, prevTxt, monthTxt] = await Promise.all([
      latestDate ? fetchText(`lab/data/snapshots/${latestDate}.csv`, true) : Promise.resolve(null),
      prevDate ? fetchText(`lab/data/snapshots/${prevDate}.csv`, true) : Promise.resolve(null),
      monthDate ? fetchText(`lab/data/snapshots/${monthDate}.csv`, true) : Promise.resolve(null),
    ]);
    return { snapDates, snapReconstructed, latestDate, prevDate, monthDate, latestTxt, prevTxt, monthTxt };
  });

  const [
    sigCsv,
    teamsCsv,
    outCsv,
    progCsv,
    featSql,
    candSql,
    debutCandSql,
    snapBundle,
    collectJson,
    linksCsv,
    videosCsv,
    imagesCsv,
  ] = await Promise.all([
    fetchText('lab/data/signals.csv'),
    fetchText('lab/data/teams.csv'),
    fetchText('lab/data/outcomes.csv'),
    fetchText('lab/data/programs.csv'),
    fetchText('lab/sql/features.sql'),
    fetchText('lab/sql/candidates.sql'),
    fetchText('lab/sql/debut_candidates.sql', true),
    snapBundlePromise,
    fetchJson('data/collect.json', true),
    hasLinksMeta ? fetchText('lab/data/links.csv', true) : Promise.resolve(null),
    hasVideosMeta ? fetchText('lab/data/videos.csv', true) : Promise.resolve(null),
    hasImagesMeta ? fetchText('lab/data/images.csv', true) : Promise.resolve(null),
    enginePromise,
  ]);

  rawAuxCsv = { links: linksCsv, videos: videosCsv, images: imagesCsv };
  appState.meta = meta;
  appState.dataEnd = meta?.data_end || '2026-11-27';
  appState.collectJson = collectJson;
  appState.dataHealth = computeDataHealth(meta, collectJson, appState.dashboardJson);
  appState.sqlTemplates = {
    features: featSql || '',
    backtest: '',
    candidates: candSql || '',
    debut_candidates: debutCandSql || '',
    signal_hits: '',
    source_scorecard: '',
    source_scorecard_debut: '',
    precedents: '',
    team: '',
    related: '',
    ego_network: '',
    scene_network: '',
    rank_change: '',
    rising_preset: '',
  };

  onStatus('브라우저 DB에 표 적재 중...');
  const snapCsvEntries = [
    [snapBundle.latestDate, snapBundle.latestTxt],
    [snapBundle.prevDate, snapBundle.prevTxt],
    [snapBundle.monthDate, snapBundle.monthTxt],
  ].filter(([d, txt]) => d && DATE_RE.test(d) && txt);

  await Promise.all([
    dbInstance.registerFileText('signals.csv', sigCsv),
    dbInstance.registerFileText('teams.csv', teamsCsv),
    dbInstance.registerFileText('outcomes.csv', outCsv),
    dbInstance.registerFileText('programs.csv', progCsv),
    ...snapCsvEntries.map(([d, txt]) => dbInstance.registerFileText(`snap_${d}.csv`, txt)),
  ]);

  // Run DuckDB core table load + auxiliary tables (matching scripts/lab_sql.py connect()) + macros
  const dbLoadPromise = (async () => {
    const snapInsertSql = snapCsvEntries.map(([d]) => `
      INSERT INTO snapshots
      SELECT DATE '${d}', CAST(team_key AS VARCHAR), CAST(score AS DOUBLE), CAST(rank AS INTEGER)
      FROM read_csv_auto('snap_${d}.csv', header=true);
    `).join('\n');
    const createSql = `
      CREATE TABLE signals AS SELECT * FROM read_csv_auto('signals.csv', header=true);
      CREATE TABLE teams AS SELECT * FROM read_csv_auto('teams.csv', header=true);
      CREATE TABLE outcomes AS SELECT * FROM read_csv_auto('outcomes.csv', header=true);
      CREATE TABLE programs AS SELECT * FROM read_csv_auto('programs.csv', header=true);
      CREATE TABLE collabs(team_key VARCHAR, partner_key VARCHAR, partner_name VARCHAR, release_date DATE, role VARCHAR, partner_established BOOLEAN);
      CREATE TABLE snapshots(snap_date DATE, team_key VARCHAR, score DOUBLE, rank INTEGER);
      CREATE TABLE team_cities(team_key VARCHAR, home_city VARCHAR, cities INTEGER, first_city VARCHAR, first_date VARCHAR, seoul_first_date VARCHAR, months_to_seoul VARCHAR, nights INTEGER);
      CREATE TABLE venue_tiers(venue VARCHAR, tier VARCHAR);
      ALTER TABLE teams ADD COLUMN IF NOT EXISTS newcomer_check VARCHAR;
      ALTER TABLE teams ADD COLUMN IF NOT EXISTS genre_confidence VARCHAR;
      ALTER TABLE outcomes ADD COLUMN IF NOT EXISTS same_house_sources VARCHAR DEFAULT '';
      ALTER TABLE outcomes ADD COLUMN IF NOT EXISTS same_house_scored BOOLEAN DEFAULT false;
      ${snapInsertSql}
    `;
    await connInstance.query(createSql);
    await connInstance.query(featSql);
    return runRawSql(`
      SELECT MIN(announced_date) AS min_d, MAX(announced_date) AS max_d, COUNT(*) AS n
      FROM outcomes
      WHERE counted
    `);
  })();

  const {
    teamIndex,
    validGenres,
    newcomerCheckByTeam,
    firstReleaseByTeam,
    genreConfidenceByTeam,
  } = parseTeamsCsvIndex(teamsCsv);
  appState.validGenres = validGenres;
  appState.teamIndex = teamIndex;
  appState.newcomerCheckByTeam = newcomerCheckByTeam;
  appState.firstReleaseByTeam = firstReleaseByTeam;
  appState.genreConfidenceByTeam = genreConfidenceByTeam;
  appState.teamCitiesByTeam = new Map();
  appState.programLabels = parseProgramsCsvMap(progCsv);
  appState.linksByTeam = indexLinksRows(parseCsvObjects(linksCsv));
  appState.videosByTeam = indexVideosRows(parseCsvObjects(videosCsv));
  const parsedImgs = parseImagesCsv(imagesCsv);
  appState.imagesByTeam = parsedImgs.urlMap;
  appState.imageMetaByTeam = parsedImgs.metaMap;
  appState.snapshots = {
    dates: snapBundle.snapDates,
    reconstructed: snapBundle.snapReconstructed,
    latestDate: snapBundle.latestDate,
    prevDate: snapBundle.prevDate,
    monthDate: snapBundle.monthDate,
    latest: parseSnapshotCsv(snapBundle.latestTxt),
    prev: parseSnapshotCsv(snapBundle.prevTxt),
  };

  const rangeRes = await dbLoadPromise;
  if (rangeRes.rows.length) {
    appState.outcomeRange = {
      min: rangeRes.rows[0].min_d,
      max: rangeRes.rows[0].max_d,
      counted: Number(rangeRes.rows[0].n) || 0,
    };
  }
  appState.ready = true;
}

// ---------- High-level query helpers ----------

/**
 * 검증 대기(pending) 출처의 최근 1년 공연 일수(팀별).
 * 휴면 판정 시 점수 출처 외 검증 대기 공연도 활동으로 인정하기 위해 사용.
 */
export async function queryPendingGigs1y(asOf) {
  const baseDate = safeIsoDate(asOf || appState.cfg.as_of || appState.dataEnd, '2026-11-27');
  const cached = lruGet(pendingGigs1yCache, baseDate);
  if (cached) return cached;
  try {
    const { rows } = await runRawSql(`
      SELECT team_key, COUNT(DISTINCT signal_date) AS pending_gigs_1y
      FROM signals
      WHERE branch = '공연'
        AND COALESCE(role, 'pending') = 'pending'
        AND signal_date >= DATE '${baseDate}' - INTERVAL 1 YEAR
        AND signal_date <= DATE '${baseDate}'
      GROUP BY team_key
    `);
    const map = new Map();
    for (const r of rows) {
      if (r.team_key) map.set(r.team_key, Number(r.pending_gigs_1y) || 0);
    }
    lruSet(pendingGigs1yCache, baseDate, map);
    return map;
  } catch (_) {
    return new Map();
  }
}

/**
 * 팀별 최근 신호 날짜 맵 (검색 드롭다운용, 1회 캐시).
 */
export async function queryTeamLastSeenMap() {
  if (teamLastSeenCache) return teamLastSeenCache;
  try {
    const { rows } = await runRawSql(`
      SELECT team_key, CAST(MAX(signal_date) AS VARCHAR) AS last_seen
      FROM signals
      WHERE signal_date IS NOT NULL
      GROUP BY team_key
    `);
    const map = new Map();
    for (const r of rows) {
      if (r.team_key && r.last_seen) map.set(r.team_key, String(r.last_seen).slice(0, 10));
    }
    teamLastSeenCache = map;
    return map;
  } catch (_) {
    return new Map();
  }
}

export async function queryCandidates(overrides = {}) {
  const c = appState.cfg;
  const limit = overrides.limit !== undefined ? overrides.limit : c.limit;
  const tpl = await getSqlTemplate('candidates');
  if (!tpl) return [];
  const params = buildParams({ ...overrides, limit });
  const limNum = Number(params.limit) || 100;
  const sql = fillTemplate(tpl, params);
  appState.lastSql.candidates = sql;

  const baseKey = fillTemplate(tpl, { ...params, limit: '__LIM__' });
  const cached = lruGet(candidatesCache, baseKey);
  const asOfIso = safeIsoDate(overrides.as_of || c.as_of || appState.dataEnd, '2026-11-27');
  let rows;
  if (cached && cached.limit >= limNum) {
    rows = cached.rows.slice(0, limNum);
  } else {
    const [res, pendingMap] = await Promise.all([
      runRawSql(sql),
      queryPendingGigs1y(asOfIso),
    ]);
    rows = res.rows.map(r => ({
      ...r,
      pending_gigs_1y: pendingMap.get(r.team_key) || 0,
    }));
    lruSet(candidatesCache, baseKey, { limit: limNum, rows });
  }

  // Apply global recent activity period filter if set (> 0 days)
  const days = Number(c.period_days) || 0;
  if (days > 0 && rows.length) {
    const asOfDate = new Date(`${c.as_of || appState.dataEnd}T00:00:00Z`);
    const minDate = new Date(asOfDate.getTime() - days * 86400000).toISOString().slice(0, 10);
    return rows.filter(r => r.last_seen && r.last_seen >= minDate);
  }
  return rows;
}

export async function queryDiscoveryStages(overrides = {}) {
  const tpl = await getSqlTemplate('discovery_stage');
  if (!tpl) return { rows: [], byTeam: new Map() };
  const c = appState.cfg;
  const fallbackAsOf = appState.dataEnd || '2026-11-27';
  const newcomerYrs = overrides.newcomer_years !== undefined ? overrides.newcomer_years : c.newcomer_years;
  const params = {
    as_of: sqlDate(overrides.as_of || c.as_of, fallbackAsOf),
    newcomer_years: sqlInt(newcomerYrs, 1, 50, 3),
    horizon_months: sqlInt(overrides.horizon_months !== undefined ? overrides.horizon_months : c.horizon_months, 1, 60, 24),
  };
  const sql = fillTemplate(tpl, params);
  if (overrides.newcomer_years === undefined) {
    appState.lastSql.discovery_stage = sql;
  }

  const cached = lruGet(discoveryStageCache, sql);
  if (cached) return cached;

  const res = await runRawSql(sql);
  const rows = res.rows.map(r => ({
    ...r,
    stage: Number(r.stage),
    n_mention_branches: Number(r.n_mention_branches) || 0,
    best_selection: Number(r.best_selection) || 0,
    recent_n: Number(r.recent_n) || 0,
    prev_n: Number(r.prev_n) || 0,
    momentum: r.momentum !== null && r.momentum !== undefined ? Number(r.momentum) : null,
    momentum_pct: r.momentum_pct !== null && r.momentum_pct !== undefined ? Number(r.momentum_pct) : null,
  }));
  const byTeam = new Map(rows.map(r => [r.team_key, r]));
  const result = { rows, byTeam };
  lruSet(discoveryStageCache, sql, result);
  return result;
}

/** meta.json(rows 또는 extras)에 보조 파일이 적혀 있는지. 적혀 있지 않으면 받지 않는다. */
export function labExtraListed(name) {
  const meta = appState.meta || {};
  const rows = meta.rows && typeof meta.rows === 'object' ? meta.rows : {};
  const extras = Array.isArray(meta.extras) ? meta.extras : [];
  return Number(rows[name]) > 0 || extras.includes(name) || extras.includes(`${name}.csv`);
}

let teamCitiesAttempted = false;
let teamCitiesPromise = null;
let venueTiersAttempted = false;
let venueTiersPromise = null;

export async function ensureTeamCitiesLoaded() {
  if (teamCitiesAttempted) return appState.teamCitiesByTeam;
  if (teamCitiesPromise) return teamCitiesPromise;
  teamCitiesPromise = (async () => {
    teamCitiesAttempted = true;
    // 404 콘솔 오류를 막으려고 meta.json 에 team_cities 가 적힌 경우에만 받는다 (없으면 빈 표 그대로)
    if (!labExtraListed('team_cities')) return appState.teamCitiesByTeam;
    const csvTxt = await fetchText('lab/data/team_cities.csv', true);
    if (!csvTxt || !csvTxt.trim()) return appState.teamCitiesByTeam;
    const parsed = parseCsvObjects(csvTxt);
    const map = new Map();
    for (const r of parsed) {
      if (!r.team_key) continue;
      map.set(r.team_key, {
        home_city: String(r.home_city || '').trim(),
        cities: Number(r.cities) || 0,
        first_city: String(r.first_city || '').trim(),
        first_date: String(r.first_date || '').trim(),
        seoul_first_date: String(r.seoul_first_date || '').trim(),
        months_to_seoul: r.months_to_seoul || '',
        nights: Number(r.nights) || 0,
      });
    }
    appState.teamCitiesByTeam = map;
    if (dbInstance && connInstance && parsed.length) {
      try {
        await dbInstance.registerFileText('team_cities.csv', csvTxt);
        await connInstance.query(`DELETE FROM team_cities; INSERT INTO team_cities SELECT * FROM read_csv('team_cities.csv', header=true, all_varchar=true);`);
      } catch (_) {}
    }
    return map;
  })();
  try {
    return await teamCitiesPromise;
  } finally {
    teamCitiesPromise = null;
  }
}

export async function ensureVenueTiersLoaded() {
  if (venueTiersAttempted) return;
  if (venueTiersPromise) return venueTiersPromise;
  venueTiersPromise = (async () => {
    venueTiersAttempted = true;
    if (!connInstance) return;
    try {
      const vp = await loadVenueProfiles();
      const venuesObj = vp && typeof vp === 'object' ? (vp.venues || null) : null;
      if (!venuesObj) return;
      const pairs = Object.entries(venuesObj)
        .filter(([, info]) => info && typeof info === 'object' && info.tier)
        .map(([name, info]) => `(${sqlStringLiteral(name)}, ${sqlStringLiteral(String(info.tier))})`);
      if (!pairs.length) return;
      await connInstance.query(`DELETE FROM venue_tiers; INSERT INTO venue_tiers VALUES ${pairs.join(', ')};`);
    } catch (_) {}
  })();
  try {
    await venueTiersPromise;
  } finally {
    venueTiersPromise = null;
  }
}

export async function queryRankChange(overrides = {}) {
  const tpl = await getSqlTemplate('rank_change');
  const empty = { rows: [], byTeam: new Map(), nowDate: null, weekDate: null, monthDate: null };
  if (!tpl) return empty;
  await ensureTeamCitiesLoaded();
  const c = appState.cfg;
  const fallbackAsOf = appState.dataEnd || '2026-11-27';
  const sql = fillTemplate(tpl, {
    as_of: sqlDate(overrides.as_of || c.as_of, fallbackAsOf),
  });
  appState.lastSql.rank_change = sql;

  const cached = lruGet(rankChangeCache, sql);
  if (cached) return cached;

  try {
    const res = await runRawSql(sql);
    const rows = res.rows.map(r => ({
      ...r,
      score: r.score !== null && r.score !== undefined ? Number(r.score) : null,
      rank: r.rank !== null && r.rank !== undefined ? Number(r.rank) : null,
      week_change: r.week_change !== null && r.week_change !== undefined ? Number(r.week_change) : null,
      month_change: r.month_change !== null && r.month_change !== undefined ? Number(r.month_change) : null,
      genre_rank: r.genre_rank !== null && r.genre_rank !== undefined ? Number(r.genre_rank) : null,
      genre_n: r.genre_n !== null && r.genre_n !== undefined ? Number(r.genre_n) : null,
      genre_week_change: r.genre_week_change !== null && r.genre_week_change !== undefined ? Number(r.genre_week_change) : null,
      genre_month_change: r.genre_month_change !== null && r.genre_month_change !== undefined ? Number(r.genre_month_change) : null,
      city_rank: r.city_rank !== null && r.city_rank !== undefined ? Number(r.city_rank) : null,
      city_n: r.city_n !== null && r.city_n !== undefined ? Number(r.city_n) : null,
    }));
    const byTeam = new Map(rows.map(r => [r.team_key, r]));
    const first = rows[0] || null;
    const result = {
      rows,
      byTeam,
      nowDate: first?.snap_date || null,
      weekDate: first?.week_date || null,
      monthDate: first?.month_date || null,
    };
    lruSet(rankChangeCache, sql, result);
    return result;
  } catch (_) {
    return empty;
  }
}

export async function queryRisingPreset(overrides = {}) {
  const tpl = await getSqlTemplate('rising_preset');
  if (!tpl) return [];
  await ensureVenueTiersLoaded();
  const baseParams = buildParams(overrides);
  const windowDays = sqlInt(overrides.window_days ?? 30, 7, 180, 30);
  const minRecent = sqlInt(overrides.min_recent ?? 2, 1, 50, 2);
  const maxTierRaw = String(overrides.max_tier || 'M').trim().toUpperCase();
  const maxTier = ['S', 'M', 'L', 'XL'].includes(maxTierRaw) ? maxTierRaw : 'M';
  const maxFans = sqlInt(overrides.max_fans ?? 10000, 0, 10000000, 10000);
  const sql = fillTemplate(tpl, {
    ...baseParams,
    window_days: windowDays,
    min_recent: minRecent,
    max_tier: sqlStringLiteral(maxTier),
    max_fans: maxFans,
  });
  appState.lastSql.rising_preset = sql;

  const cached = lruGet(risingPresetCache, sql);
  if (cached) return cached;

  try {
    const res = await runRawSql(sql);
    const rows = res.rows.map(r => ({
      ...r,
      recent_n: Number(r.recent_n) || 0,
      prev_n: Number(r.prev_n) || 0,
      recent_branches: Number(r.recent_branches) || 0,
      growth: r.growth !== null && r.growth !== undefined ? Number(r.growth) : null,
      score: r.score !== null && r.score !== undefined ? Number(r.score) : null,
      fan_count_used: r.fan_count_used !== null && r.fan_count_used !== undefined ? Number(r.fan_count_used) : null,
    }));
    lruSet(risingPresetCache, sql, rows);
    return rows;
  } catch (_) {
    return [];
  }
}

export async function queryBacktestAll() {
  const cutoffs = appState.cfg.cutoffs;
  if (!cutoffs.length) return [];
  const tpl = await getSqlTemplate('backtest');
  if (!tpl) return [];
  const sqls = cutoffs.map(d => fillTemplate(tpl, buildParams({ cutoff: d })));
  const combinedSql = cutoffs.map((d, i) => `-- 기준일 ${d}\n${sqls[i].trim()}`).join('\n\n');
  appState.lastSql.backtest = combinedSql;

  const cached = lruGet(backtestCache, combinedSql);
  if (cached) return cached;

  const blocks = [];
  for (let i = 0; i < cutoffs.length; i += 1) {
    const { rows } = await runRawSql(sqls[i]);
    blocks.push({ cutoff: cutoffs[i], rows });
  }
  lruSet(backtestCache, combinedSql, blocks);
  return blocks;
}

export async function querySignalHits(cutoff) {
  const useCutoff = cutoff || appState.cfg.signal_cutoff || appState.cfg.cutoffs[0] || '2025-01-01';
  const tpl = await getSqlTemplate('signal_hits');
  if (!tpl) return { cutoff: useCutoff, rows: [] };
  const sql = fillTemplate(tpl, buildParams({ cutoff: useCutoff }));
  appState.lastSql.signals = sql;

  const cached = lruGet(signalHitsCache, sql);
  if (cached) return cached;

  const { rows } = await runRawSql(sql);
  const result = { cutoff: useCutoff, rows };
  lruSet(signalHitsCache, sql, result);
  return result;
}

export async function querySourceScorecard({
  cutoffs = ['2024-07-01', '2025-01-01', '2025-07-01'],
  since = '2024-01-01',
  horizonMonths = 24,
} = {}) {
  const cleanCutoffs = (Array.isArray(cutoffs) ? cutoffs : []).filter(d => DATE_RE.test(d));
  const useCutoffs = cleanCutoffs.length ? cleanCutoffs : ['2024-07-01', '2025-01-01', '2025-07-01'];
  const cutoffsSql = useCutoffs.map(d => `(DATE '${d}')`).join(',');
  const sinceLit = sqlDate(since, '2024-01-01');
  const horizonSql = sqlInt(horizonMonths, 1, 60, 24);

  const tpl = await getSqlTemplate('source_scorecard');
  if (!tpl) {
    return { cutoffs: useCutoffs, since: sinceLit.slice(1, -1), horizonMonths: Number(horizonSql), totalWinners: 0, rows: [] };
  }
  const sql = fillTemplate(tpl, {
    cutoffs: cutoffsSql,
    since: sinceLit,
    horizon_months: horizonSql,
  });
  appState.lastSql.scorecard = sql;

  const cached = lruGet(scorecardCache, sql);
  if (cached) return cached;

  const [scRes, winRes] = await Promise.all([
    runRawSql(sql),
    runRawSql(`
      SELECT COUNT(*) AS n FROM (
        SELECT team_key, MIN(announced_date) AS fo
        FROM outcomes
        WHERE counted
        GROUP BY team_key
        HAVING MIN(announced_date) >= DATE ${sinceLit}
      ) w
    `),
  ]);

  const result = {
    cutoffs: useCutoffs,
    since: sinceLit.slice(1, -1),
    horizonMonths: Number(horizonSql),
    totalWinners: Number(winRes.rows[0]?.n) || 0,
    rows: scRes.rows,
  };
  lruSet(scorecardCache, sql, result);
  return result;
}

export async function queryTeamDetail(teamKey) {
  const keyLit = sqlStringLiteral(teamKey);
  const p = buildParams({ team_key: teamKey });
  const todayIso = localTodayIso();

  const scoreSql = `
    SELECT team_key, display_name, ROUND(score, 2) AS score, n_branch, best_stage,
           peer_selected, dmz, gigs_1y, outlets, context_outlets, collab_est, recent180, venues, peer_winner,
           first_seen, last_seen, primary_genre, profile_status, had_outcome,
           ROUND(pts_branch, 2) AS pts_branch, ROUND(pts_stage, 2) AS pts_stage,
           ROUND(pts_peer, 2) AS pts_peer, ROUND(pts_dmz, 2) AS pts_dmz,
           ROUND(pts_gigs, 2) AS pts_gigs, ROUND(pts_outlets, 2) AS pts_outlets,
           ROUND(pts_context, 2) AS pts_context, ROUND(pts_collab, 2) AS pts_collab,
           ROUND(pts_recent, 2) AS pts_recent, ROUND(pts_venues, 2) AS pts_venues,
           ROUND(pts_winner, 2) AS pts_winner
    FROM lab_scored(DATE ${p.as_of}, ${p.lookback_years}, 50, false,
                    'any', 1, '', ${p.branches},
                    ${p.w_branch}, ${p.w_stage}, ${p.w_peer}, ${p.w_dmz}, ${p.w_gigs}, ${p.w_outlets}, ${p.outlet_cap},
                    ${p.w_recent}, ${p.w_venues}, ${p.w_winner}, ${p.w_context}, ${p.w_collab})
    WHERE team_key = ${keyLit}
    LIMIT 1
  `;

  // Use JS local date literal instead of CURRENT_DATE so DuckDB-WASM does not auto-download the icu extension (~1.4s cold stall)
  const timelineSql = `
    SELECT s.signal_date, s.branch, s.source, s.program,
           COALESCE(pr.label, NULLIF(s.program, '')) AS program_label,
           NULLIF(s.venue, '') AS venue,
           COALESCE(s.role, 'pending') AS role,
           s.signal_date > DATE '${todayIso}' AS is_upcoming
    FROM signals s
    LEFT JOIN programs pr ON pr.program = s.program
    WHERE s.team_key = ${keyLit}
    ORDER BY s.signal_date DESC, s.branch
  `;
  appState.lastSql.team = timelineSql;

  const cacheKey = `${todayIso}::${scoreSql}`;
  const cached = lruGet(teamDetailCache, cacheKey);
  if (cached) return cached;

  const teamProfileSql = `SELECT * FROM teams WHERE team_key = ${keyLit} LIMIT 1`;
  const outcomesSql = `
    SELECT announced_date, program, program_label, tier, result, counted, grade, weight
    FROM outcomes
    WHERE team_key = ${keyLit}
    ORDER BY announced_date DESC, weight DESC
  `;

  const [precTpl, relTpl] = await Promise.all([
    getSqlTemplate('precedents'),
    getSqlTemplate('related'),
  ]);

  let precPromise = Promise.resolve({ rows: [] });
  if (precTpl) {
    const precSql = fillTemplate(precTpl, { team_key: keyLit });
    appState.lastSql.precedents = precSql;
    precPromise = runRawSql(precSql);
  }

  let relPromise = Promise.resolve({ rows: [] });
  if (relTpl) {
    const relSql = fillTemplate(relTpl, { team_key: keyLit });
    appState.lastSql.related = relSql;
    relPromise = runRawSql(relSql);
  }

  const [profileRes, scoreRes, timelineRes, outcomeRes, precRes, relRes] = await Promise.all([
    runRawSql(teamProfileSql),
    runRawSql(scoreSql),
    runRawSql(timelineSql),
    runRawSql(outcomesSql),
    precPromise,
    relPromise,
  ]);

  // Enrich precedent rows with counted outcome grade & weight (S/A/B) without modifying precedents.sql
  let precedents = precRes.rows;
  if (precedents.length) {
    const pKeys = [...new Set(precedents.map(r => r.past_team).filter(Boolean))];
    if (pKeys.length) {
      const inList = pKeys.map(k => sqlStringLiteral(k)).join(', ');
      try {
        const gRes = await runRawSql(`
          SELECT team_key, announced_date, program_label, grade, weight
          FROM outcomes
          WHERE counted AND team_key IN (${inList})
          ORDER BY announced_date ASC, weight DESC
        `);
        const exactMap = new Map();
        const firstMap = new Map();
        for (const r of gRes.rows) {
          const exactKey = `${r.team_key}::${r.announced_date}::${r.program_label}`;
          if (!exactMap.has(exactKey)) exactMap.set(exactKey, r);
          if (!firstMap.has(r.team_key)) firstMap.set(r.team_key, r);
        }
        precedents = precedents.map(row => {
          const match =
            exactMap.get(`${row.past_team}::${row.outcome_date}::${row.outcome_label}`) ||
            firstMap.get(row.past_team);
          return {
            ...row,
            outcome_grade: match?.grade || '',
            outcome_weight: match?.weight ?? null,
          };
        });
      } catch (_) {}
    }
  }

  const result = {
    profile: profileRes.rows[0] || null,
    scored: scoreRes.rows[0] || null,
    timeline: timelineRes.rows,
    outcomes: outcomeRes.rows,
    precedents,
    related: relRes.rows,
    links: appState.linksByTeam.get(teamKey) || new Map(),
    videos: appState.videosByTeam.get(teamKey) || [],
  };
  lruSet(teamDetailCache, cacheKey, result);
  return result;
}

const topPrecedentCache = new Map();

export async function queryTopPrecedent(teamKey) {
  if (!teamKey) return null;
  if (topPrecedentCache.has(teamKey)) return topPrecedentCache.get(teamKey);
  const tpl = await getSqlTemplate('precedents');
  if (!tpl) return null;
  try {
    const sql = fillTemplate(tpl, { team_key: sqlStringLiteral(teamKey) });
    const { rows } = await runRawSql(sql);
    const top = rows[0] || null;
    topPrecedentCache.set(teamKey, top);
    return top;
  } catch (_) {
    return null;
  }
}

export async function queryWatchlistEnriched(watchItems) {
  if (!watchItems.length) return [];
  const keys = watchItems.map(it => sqlStringLiteral(it.team_key)).join(', ');
  const p = buildParams();
  const asOf = appState.cfg.as_of || appState.dataEnd;

  const [scoreRes, profRes, recentRes] = await Promise.all([
    runRawSql(`
      SELECT team_key, display_name, ROUND(score, 2) AS score, n_branch, gigs_1y, last_seen, primary_genre
      FROM lab_scored(DATE ${p.as_of}, ${p.lookback_years}, 50, false,
                      'any', 1, '', ${p.branches},
                      ${p.w_branch}, ${p.w_stage}, ${p.w_peer}, ${p.w_dmz}, ${p.w_gigs}, ${p.w_outlets}, ${p.outlet_cap},
                      ${p.w_recent}, ${p.w_venues}, ${p.w_winner}, ${p.w_context}, ${p.w_collab})
      WHERE team_key IN (${keys})
    `),
    runRawSql(`
      SELECT team_key, display_name, first_seen, primary_genre, profile_status
      FROM teams
      WHERE team_key IN (${keys})
    `),
    runRawSql(`
      SELECT team_key,
             COUNT(*) FILTER (WHERE signal_date >= DATE '${asOf}' - INTERVAL 7 DAY AND signal_date <= DATE '${asOf}') AS recent_7d,
             MAX(signal_date) FILTER (WHERE signal_date <= DATE '${asOf}') AS latest_sig_date
      FROM signals
      WHERE team_key IN (${keys})
      GROUP BY team_key
    `),
  ]);

  const byScore = new Map(scoreRes.rows.map(r => [r.team_key, r]));
  const byProf = new Map(profRes.rows.map(r => [r.team_key, r]));
  const byRecent = new Map(recentRes.rows.map(r => [r.team_key, r]));
  const { latest, prev } = appState.snapshots;

  return watchItems.map(item => {
    const sc = byScore.get(item.team_key);
    const pr = byProf.get(item.team_key);
    const rc = byRecent.get(item.team_key);
    const snapNow = latest.get(item.team_key);
    const snapPrev = prev.get(item.team_key);
    const rankDelta = (snapNow && snapPrev) ? (snapPrev.rank - snapNow.rank) : null;
    const scoreDelta = (snapNow && snapPrev) ? Math.round((snapNow.score - snapPrev.score) * 100) / 100 : null;
    return {
      team_key: item.team_key,
      display_name: sc?.display_name || pr?.display_name || item.display_name || item.team_key,
      added_at: item.added_at,
      status: item.status || 'watching',
      score: sc?.score ?? null,
      n_branch: sc?.n_branch ?? 0,
      gigs_1y: sc?.gigs_1y ?? 0,
      primary_genre: sc?.primary_genre || pr?.primary_genre || '',
      last_seen: rc?.latest_sig_date || sc?.last_seen || '',
      recent_7d: Number(rc?.recent_7d) || 0,
      rank_now: snapNow?.rank ?? null,
      rank_delta: rankDelta,
      score_delta: scoreDelta,
      is_new_in_snap: Boolean(snapNow && !snapPrev),
    };
  });
}

/**
 * 주간 브리핑 보조 통계:
 * 1) 최근 7일(또는 직전 스냅샷 이후) 새 신호 건수 및 갈래별 분포
 * 2) 최근 7일 공개 새 영상 수 + 상위 후보 중 최근 무대/공식 영상 최대 3개
 */
export async function queryWeeklyDigestExtras(candRows = []) {
  const endDate = appState.snapshots.latestDate || appState.dataEnd || '2026-11-27';
  const prevDate = appState.snapshots.prevDate;
  const startDate = prevDate || new Date(Date.parse(`${endDate}T00:00:00Z`) - 7 * 86400000).toISOString().slice(0, 10);

  let totalSignals = 0;
  let byBranch = {};
  const sigCacheKey = `${startDate}::${endDate}`;
  const cachedSig = lruGet(weeklySignalsCache, sigCacheKey);
  if (cachedSig) {
    totalSignals = cachedSig.totalSignals;
    byBranch = cachedSig.byBranch;
  } else {
    try {
      const { rows } = await runRawSql(`
        SELECT branch, COUNT(*) AS n
        FROM signals
        WHERE signal_date >= DATE '${startDate}' AND signal_date <= DATE '${endDate}'
        GROUP BY branch
        ORDER BY n DESC
      `);
      for (const r of rows) {
        const cnt = Number(r.n) || 0;
        byBranch[r.branch] = cnt;
        totalSignals += cnt;
      }
      lruSet(weeklySignalsCache, sigCacheKey, { totalSignals, byBranch });
    } catch (_) {}
  }

  // Count videos published in the 7-day window across all teams
  let newVideos7d = 0;
  for (const vids of appState.videosByTeam.values()) {
    for (const v of vids) {
      const pub = String(v.published_at || '').slice(0, 10);
      if (pub && pub >= startDate && pub <= endDate) {
        newVideos7d += 1;
      }
    }
  }

  // Pick up to 3 recent stage/official videos from top candidates (one video per team for variety)
  const candRank = new Map();
  candRows.forEach((r, i) => {
    candRank.set(r.team_key, { rank: i + 1, display_name: r.display_name || r.team_key, genre: r.primary_genre || '' });
  });
  const cutoff30 = new Date(Date.parse(`${endDate}T00:00:00Z`) - 45 * 86400000).toISOString().slice(0, 10);
  const picked = [];
  const usedTeams = new Set();

  const collectFromTop = (maxRank, minPub) => {
    const pool = [];
    for (const [tk, info] of candRank.entries()) {
      if (info.rank > maxRank || usedTeams.has(tk)) continue;
      const vids = appState.videosByTeam.get(tk) || [];
      if (!vids.length) continue;
      const sorted = [...vids].sort((a, b) => {
        const pubCmp = String(b.published_at || '').localeCompare(String(a.published_at || ''));
        if (pubCmp !== 0) return pubCmp;
        return (VIDEO_KIND_ORDER[a.kind] ?? 9) - (VIDEO_KIND_ORDER[b.kind] ?? 9);
      });
      const best = sorted.find(v => !minPub || String(v.published_at || '').slice(0, 10) >= minPub);
      if (best) {
        pool.push({
          ...best,
          team_key: tk,
          display_name: info.display_name,
          genre: info.genre,
          rank: info.rank,
        });
      }
    }
    pool.sort((a, b) => {
      const pubCmp = String(b.published_at || '').localeCompare(String(a.published_at || ''));
      if (pubCmp !== 0) return pubCmp;
      return a.rank - b.rank;
    });
    for (const v of pool) {
      if (picked.length >= 3) break;
      if (usedTeams.has(v.team_key)) continue;
      usedTeams.add(v.team_key);
      picked.push(v);
    }
  };

  collectFromTop(60, cutoff30);
  if (picked.length < 3) collectFromTop(120, '');

  return {
    startDate,
    endDate,
    signalStats: { total: totalSignals, byBranch },
    newVideos7d,
    recentStageVideos: picked.slice(0, 3),
  };
}

export function getSnapshotDiff(scoredRows = []) {
  const { latestDate, prevDate, latest, prev } = appState.snapshots;
  if (!latestDate || !prevDate || !latest.size) {
    return { latestDate, prevDate, newEntrants: [], risers: [] };
  }
  const byTeam = new Map(appState.teamIndex.map(t => [t.team_key, t]));
  const byScored = new Map(scoredRows.map(r => [r.team_key, r]));
  const genreFilter = appState.cfg.genre;

  const newEntrants = [];
  const risers = [];

  for (const [k, now] of latest.entries()) {
    const info = byTeam.get(k);
    const sc = byScored.get(k);
    const genre = sc?.primary_genre || info?.primary_genre || '';
    if (genreFilter && genre !== genreFilter) continue;

    const old = prev.get(k);
    const display_name = sc?.display_name || info?.display_name || k;
    if (!old) {
      newEntrants.push({
        team_key: k,
        display_name,
        genre,
        rank_now: now.rank,
        score_now: now.score,
      });
    } else {
      const rankGain = old.rank - now.rank;
      const scoreGain = Math.round((now.score - old.score) * 100) / 100;
      if (scoreGain > 0 || rankGain >= 3) {
        risers.push({
          team_key: k,
          display_name,
          genre,
          rank_now: now.rank,
          rank_prev: old.rank,
          rank_gain: rankGain,
          score_now: now.score,
          score_gain: scoreGain,
        });
      }
    }
  }

  newEntrants.sort((a, b) => a.rank_now - b.rank_now);
  risers.sort((a, b) => (b.score_gain - a.score_gain) || (b.rank_gain - a.rank_gain) || (a.rank_now - b.rank_now));

  return { latestDate, prevDate, newEntrants, risers };
}

function safeIsoDate(v, fallback = '2026-11-27') {
  const s = String(v || '').trim();
  return /^\d{4}-\d{2}-\d{2}$/.test(s) ? s : fallback;
}

/**
 * 예정 공연 조회 (signals 직접 쿼리, branch='공연' AND signal_date >= 기준일).
 * indistreet + indiego 중복 행은 (signal_date, venue, team_key) 기준 DISTINCT 제거.
 */
export async function queryUpcomingGigs({ asOf, days = 0 } = {}) {
  const baseDate = safeIsoDate(asOf || appState.cfg.as_of || appState.dataEnd, '2026-11-27');
  const daysNum = Math.max(0, Number(days) || 0);
  const cacheKey = `${baseDate}::${daysNum}`;
  const cached = lruGet(upcomingGigsCache, cacheKey);
  if (cached) return cached;

  let endDate = '';
  let endClause = '';
  if (daysNum > 0) {
    const endMs = Date.parse(`${baseDate}T00:00:00Z`) + daysNum * 86400000;
    endDate = new Date(endMs).toISOString().slice(0, 10);
    const fullCached = lruGet(upcomingGigsCache, `${baseDate}::0`);
    if (fullCached) {
      const sliced = fullCached.filter(r => r.signal_date <= endDate);
      lruSet(upcomingGigsCache, cacheKey, sliced);
      return sliced;
    }
    endClause = `AND s.signal_date <= DATE '${endDate}'`;
  }
  const { rows } = await runRawSql(`
    SELECT DISTINCT
      CAST(s.signal_date AS VARCHAR) AS signal_date,
      COALESCE(NULLIF(TRIM(s.venue), ''), '공연장 미정') AS venue,
      s.team_key,
      COALESCE(t.display_name, s.team_key) AS display_name,
      COALESCE(t.primary_genre, '') AS primary_genre
    FROM signals s
    LEFT JOIN teams t USING (team_key)
    WHERE s.branch = '공연'
      AND s.signal_date >= DATE '${baseDate}'
      ${endClause}
    ORDER BY signal_date ASC, venue ASC, display_name ASC
  `);
  lruSet(upcomingGigsCache, cacheKey, rows);
  return rows;
}

/**
 * 같은 날·같은 공연장의 예정 공연을 한 줄(이벤트)로 묶는다.
 * candRankMap: Map<team_key, { rank, score, display_name, primary_genre }>
 */
export function groupUpcomingEvents(rawRows = [], candRankMap = new Map()) {
  const byKey = new Map();
  for (const r of rawRows) {
    const date = String(r.signal_date || '').slice(0, 10);
    const venue = String(r.venue || '공연장 미정').trim() || '공연장 미정';
    if (!date || !r.team_key) continue;
    const evKey = `${date}::${venue}`;
    let ev = byKey.get(evKey);
    if (!ev) {
      ev = {
        signal_date: date,
        venue,
        seenTeams: new Set(),
        candidateTeams: [],
        otherTeams: [],
      };
      byKey.set(evKey, ev);
    }
    if (ev.seenTeams.has(r.team_key)) continue;
    ev.seenTeams.add(r.team_key);

    const cand = candRankMap.get(r.team_key);
    if (cand) {
      ev.candidateTeams.push({
        team_key: r.team_key,
        display_name: cand.display_name || r.display_name || r.team_key,
        primary_genre: cand.primary_genre || r.primary_genre || '',
        rank: cand.rank,
        score: cand.score,
      });
    } else {
      ev.otherTeams.push({
        team_key: r.team_key,
        display_name: r.display_name || r.team_key,
        primary_genre: r.primary_genre || '',
      });
    }
  }

  const events = [...byKey.values()].map(ev => {
    ev.candidateTeams.sort((a, b) => a.rank - b.rank);
    return {
      signal_date: ev.signal_date,
      venue: ev.venue,
      candidateTeams: ev.candidateTeams,
      otherTeams: ev.otherTeams,
      hasCandidate: ev.candidateTeams.length > 0,
      bestRank: ev.candidateTeams.length ? ev.candidateTeams[0].rank : Infinity,
      totalTeams: ev.candidateTeams.length + ev.otherTeams.length,
    };
  });

  events.sort((a, b) => {
    const dCmp = a.signal_date.localeCompare(b.signal_date);
    if (dCmp !== 0) return dCmp;
    if (a.bestRank !== b.bestRank) return a.bestRank - b.bestRank;
    return a.venue.localeCompare(b.venue, 'ko');
  });
  return events;
}

/** team_key → 가장 빠른 예정 공연 1건 + 전체 예정 공연 수 */
export function buildNextGigByTeam(rawRows = []) {
  const map = new Map();
  for (const r of rawRows) {
    const tk = r.team_key;
    const date = String(r.signal_date || '').slice(0, 10);
    const venue = String(r.venue || '공연장 미정').trim() || '공연장 미정';
    if (!tk || !date) continue;
    const existing = map.get(tk);
    if (!existing) {
      map.set(tk, { signal_date: date, venue, count: 1, seen: new Set([`${date}::${venue}`]) });
    } else {
      const k = `${date}::${venue}`;
      if (!existing.seen.has(k)) {
        existing.seen.add(k);
        existing.count += 1;
      }
      if (date < existing.signal_date) {
        existing.signal_date = date;
        existing.venue = venue;
      }
    }
  }
  return map;
}

/**
 * 이번 달(기준일 YYYY-MM) 신인 후보가 많이 선 공연장 TOP 및 공연장별 상위 후보 팀 목록.
 */
export async function queryMonthlyNewcomerVenues(candRows = [], asOf = null) {
  const baseDate = safeIsoDate(asOf || appState.cfg.as_of || appState.dataEnd, '2026-11-27');
  const ym = baseDate.slice(0, 7);
  const [yStr, mStr] = ym.split('-');
  const monthLabel = `${yStr}년 ${Number(mStr)}월`;

  const candMap = new Map();
  candRows.forEach((r, i) => {
    candMap.set(r.team_key, { ...r, rank: i + 1 });
  });

  const { rows } = await runRawSql(`
    SELECT DISTINCT
      CAST(s.signal_date AS VARCHAR) AS signal_date,
      TRIM(s.venue) AS venue,
      s.team_key,
      COALESCE(t.display_name, s.team_key) AS display_name,
      COALESCE(t.primary_genre, '') AS primary_genre
    FROM signals s
    LEFT JOIN teams t USING (team_key)
    WHERE s.branch = '공연'
      AND SUBSTR(CAST(s.signal_date AS VARCHAR), 1, 7) = '${ym}'
      AND TRIM(COALESCE(s.venue, '')) <> ''
      AND TRIM(COALESCE(s.venue, '')) <> '공연장 미정'
    ORDER BY s.signal_date DESC
  `);

  const byVenue = new Map();
  for (const r of rows) {
    const v = r.venue;
    if (!v) continue;
    let entry = byVenue.get(v);
    if (!entry) {
      entry = {
        venue: v,
        gigKeys: new Set(),
        allTeams: new Set(),
        candByKey: new Map(),
      };
      byVenue.set(v, entry);
    }
    entry.gigKeys.add(`${r.signal_date}::${r.team_key}`);
    entry.allTeams.add(r.team_key);

    const cand = candMap.get(r.team_key);
    if (cand) {
      const prev = entry.candByKey.get(r.team_key);
      if (!prev) {
        entry.candByKey.set(r.team_key, {
          ...cand,
          lastGigDate: r.signal_date,
          gigCountMonth: 1,
        });
      } else {
        prev.gigCountMonth += 1;
        if (r.signal_date > prev.lastGigDate) prev.lastGigDate = r.signal_date;
      }
    }
  }

  const venues = [...byVenue.values()]
    .map(e => {
      const candidates = [...e.candByKey.values()].sort((a, b) => a.rank - b.rank);
      const totalTeams = e.allTeams.size;
      const candidateCount = candidates.length;
      return {
        venue: e.venue,
        monthGigs: e.gigKeys.size,
        totalTeams,
        candidateCount,
        candidateRatio: totalTeams ? (100 * candidateCount) / totalTeams : 0,
        candidates,
      };
    })
    .filter(v => v.candidateCount > 0)
    .sort((a, b) => (b.candidateCount - a.candidateCount) || (b.totalTeams - a.totalTeams) || a.venue.localeCompare(b.venue, 'ko'));

  return { ym, monthLabel, venues };
}

export function getTeamExternalLinks(teamKey, displayName = '') {
  const dj = appState.dashboardJson;
  if (!dj || !dj.sections) return [];
  const links = [];
  const seen = new Set();
  const norm = s => String(s || '').toLowerCase().replace(/\s+/g, '');
  const kNorm = norm(teamKey);
  const dNorm = norm(displayName);

  const add = (title, url, source, date) => {
    if (!url || seen.has(url)) return;
    seen.add(url);
    links.push({ title: title || source || url, url, source: source || '', date: date || '' });
  };

  for (const c of (dj.sections.candidates || [])) {
    if (c.artist_key === teamKey || norm(c.artist) === kNorm || (dNorm && norm(c.artist) === dNorm)) {
      for (const s of (c.signals || [])) {
        if (s.url) add(s.detail || s.source_label || s.source, s.url, s.source_label || s.source, s.date);
      }
    }
  }
  for (const p of (dj.sections.recent_press || [])) {
    if (p.artist_key === teamKey || norm(p.artist) === kNorm || (dNorm && norm(p.artist) === dNorm)) {
      if (p.url) add(p.title || p.outlet, p.url, p.source_label || p.outlet || p.source, p.published_at);
    }
  }
  return links.slice(0, 12);
}

let sceneMapCache = undefined;
let sceneMapPromise = null;

export async function loadSceneMap() {
  if (sceneMapCache !== undefined) return sceneMapCache;
  if (sceneMapPromise) return sceneMapPromise;
  sceneMapPromise = (async () => {
    const raw = await fetchJson('lab/data/scene_map.json', true);
    if (!raw || !Array.isArray(raw.communities) || !raw.communities.length) {
      sceneMapCache = null;
      return null;
    }
    const communities = [...raw.communities].sort(
      (a, b) => (Number(b.size) || 0) - (Number(a.size) || 0) || (Number(a.id) || 0) - (Number(b.id) || 0)
    );
    const communityById = new Map();
    for (const c of communities) communityById.set(c.id, c);
    const teamToCommunity = new Map();
    if (Array.isArray(raw.nodes)) {
      for (const n of raw.nodes) {
        if (!n || !n.team_key) continue;
        const comm = communityById.get(n.community);
        if (comm) teamToCommunity.set(n.team_key, comm);
      }
    }
    // Also index top_candidates & hubs defensively in case nodes omit anything
    for (const c of communities) {
      for (const t of (c.top_candidates || [])) {
        if (t?.team_key && !teamToCommunity.has(t.team_key)) teamToCommunity.set(t.team_key, c);
      }
      for (const h of (c.hubs || [])) {
        if (h?.team_key && !teamToCommunity.has(h.team_key)) teamToCommunity.set(h.team_key, c);
      }
    }
    sceneMapCache = { raw, communities, communityById, teamToCommunity };
    appState.sceneMap = sceneMapCache;
    return sceneMapCache;
  })();
  try {
    return await sceneMapPromise;
  } finally {
    sceneMapPromise = null;
  }
}

let dashboardJsonPromise = null;

/**
 * docs/data/dashboard.json(397KB)을 필요할 때만 1회 지연 로드한다.
 * 팀 상세·공연장·검증(evidence)·데이터 품질 화면에서 사용.
 */
export async function loadDashboardJson() {
  if (appState.dashboardJson) return appState.dashboardJson;
  if (dashboardJsonPromise) return dashboardJsonPromise;
  dashboardJsonPromise = (async () => {
    const dj = await fetchJson('data/dashboard.json', true);
    if (dj) {
      appState.dashboardJson = dj;
      const prevLevel = appState.dataHealth?.level;
      appState.dataHealth = computeDataHealth(appState.meta, appState.collectJson, dj);
      if (prevLevel !== appState.dataHealth.level && typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent('app:refresh-health'));
      }
    }
    return appState.dashboardJson || null;
  })();
  try {
    return await dashboardJsonPromise;
  } finally {
    dashboardJsonPromise = null;
  }
}

let sourceReviewPromise = null;

/**
 * docs/data/source_review.json을 필요할 때만 1회 지연 로드한다.
 * 출처 성적표·설정(고급) 메뉴에서 사용.
 */
export async function loadSourceReview() {
  if (appState.sourceReviewJson) return appState.sourceReviewJson;
  if (sourceReviewPromise) return sourceReviewPromise;
  sourceReviewPromise = (async () => {
    const sr = await fetchJson('data/source_review.json', true);
    if (sr) appState.sourceReviewJson = sr;
    return appState.sourceReviewJson || null;
  })();
  try {
    return await sourceReviewPromise;
  } finally {
    sourceReviewPromise = null;
  }
}

let sourceRolesCache = undefined;
let sourceRolesPromise = null;

export async function loadSourceRoles() {
  if (sourceRolesCache !== undefined) return sourceRolesCache;
  if (sourceRolesPromise) return sourceRolesPromise;
  sourceRolesPromise = (async () => {
    const raw = await fetchJson('lab/data/source_roles.json', true);
    sourceRolesCache = (raw && typeof raw === 'object') ? raw : null;
    return sourceRolesCache;
  })();
  try {
    return await sourceRolesPromise;
  } finally {
    sourceRolesPromise = null;
  }
}

let alertsCache = undefined;
let alertsPromise = null;

/**
 * docs/data/alerts.json을 1회 지연 로드한다.
 * 파일이 없거나 alerts가 비어 있으면 null을 반환(오류 없음).
 */
export async function loadAlertsJson() {
  if (alertsCache !== undefined) return alertsCache;
  if (alertsPromise) return alertsPromise;
  alertsPromise = (async () => {
    const raw = await fetchJson('data/alerts.json', true);
    // 알림이 0건이어도 파일이 바르면 빈 목록으로 둔다(브리핑에 '이번 주 새 알림 없음')
    if (!raw || typeof raw !== 'object' || !Array.isArray(raw.alerts)) {
      alertsCache = null;
      appState.alertsJson = null;
      return null;
    }
    const alerts = raw.alerts
      .filter(a => a && typeof a === 'object' && a.team_key)
      .map(a => ({
        ...a,
        type: String(a.type || ''),
        type_label: String(a.type_label || raw.types?.[a.type] || a.type || ''),
        team_key: String(a.team_key),
        name: String(a.name || a.team_key),
        date: String(a.date || ''),
        found_on: String(a.found_on || raw.as_of || ''),
        text: String(a.text || ''),
        evidence: Array.isArray(a.evidence) ? a.evidence : [],
        importance: Number(a.importance) || 0,
      }))
      .sort((a, b) => (b.importance - a.importance) || b.date.localeCompare(a.date) || a.team_key.localeCompare(b.team_key, 'ko'));

    const byTeam = new Map();
    for (const a of alerts) {
      if (!byTeam.has(a.team_key)) byTeam.set(a.team_key, []);
      byTeam.get(a.team_key).push(a);
    }

    alertsCache = {
      generated_at: raw.generated_at || '',
      as_of: String(raw.as_of || ''),
      baseline: raw.baseline && typeof raw.baseline === 'object' ? raw.baseline : null,
      types: raw.types && typeof raw.types === 'object' ? raw.types : {},
      counts_found: raw.counts_found && typeof raw.counts_found === 'object' ? raw.counts_found : {},
      counts_shown: raw.counts_shown && typeof raw.counts_shown === 'object' ? raw.counts_shown : {},
      caps: raw.caps && typeof raw.caps === 'object' ? raw.caps : {},
      snapshots: raw.snapshots && typeof raw.snapshots === 'object' ? raw.snapshots : null,
      alerts,
      byTeam,
    };
    appState.alertsJson = alertsCache;
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('app:alerts-loaded'));
    }
    return alertsCache;
  })();
  try {
    return await alertsPromise;
  } finally {
    alertsPromise = null;
  }
}

let venueProfilesCache = undefined;
let venueProfilesPromise = null;

/**
 * docs/lab/data/venue_profiles.json을 1회 지연 로드한다.
 * 파일이 없거나 비어 있으면 null을 반환(오류 없음).
 */
export async function loadVenueProfiles() {
  if (venueProfilesCache !== undefined) return venueProfilesCache;
  if (venueProfilesPromise) return venueProfilesPromise;
  venueProfilesPromise = (async () => {
    const raw = await fetchJson('lab/data/venue_profiles.json', true);
    if (!raw || typeof raw !== 'object' || !raw.venues || typeof raw.venues !== 'object') {
      venueProfilesCache = null;
      return null;
    }
    venueProfilesCache = {
      as_of: String(raw.as_of || ''),
      notes: raw.notes && typeof raw.notes === 'object' ? raw.notes : {},
      venues: raw.venues,
    };
    return venueProfilesCache;
  })();
  try {
    return await venueProfilesPromise;
  } finally {
    venueProfilesPromise = null;
  }
}

/**
 * 특정 공연장의 최근 공연 기록을 DuckDB signals 테이블에서 조회한다.
 * venue_profiles.json이 아직 없어도 공연 목록은 항상 표시할 수 있다.
 */
export async function queryVenueRecentShows(venueName, limit = 300) {
  const vn = String(venueName || '').trim();
  if (!vn) return [];
  const lim = Math.max(10, Math.min(1000, Number(limit) || 300));
  const key = `${vn}::${lim}`;
  const cached = lruGet(venueShowsCache, key);
  if (cached) return cached;

  const sql = `
    SELECT
      CAST(s.signal_date AS VARCHAR) AS signal_date,
      s.team_key,
      COALESCE(t.display_name, s.team_key) AS display_name,
      COALESCE(t.primary_genre, '') AS primary_genre,
      COALESCE(s.source, '') AS source
    FROM signals s
    LEFT JOIN teams t USING (team_key)
    WHERE s.branch = '공연'
      AND TRIM(COALESCE(s.venue, '')) = ${sqlStringLiteral(vn)}
      AND s.signal_date IS NOT NULL
    ORDER BY s.signal_date DESC, display_name ASC
    LIMIT ${lim}
  `;
  const { rows } = await runRawSql(sql);
  const seen = new Set();
  const deduped = [];
  for (const r of rows) {
    const dt = String(r.signal_date || '').slice(0, 10);
    if (!dt || !r.team_key) continue;
    const dk = `${dt}::${r.team_key}`;
    if (seen.has(dk)) continue;
    seen.add(dk);
    deduped.push({
      signal_date: dt,
      team_key: String(r.team_key),
      display_name: String(r.display_name || r.team_key),
      primary_genre: String(r.primary_genre || ''),
      source: String(r.source || ''),
    });
  }
  lruSet(venueShowsCache, key, deduped);
  return deduped;
}

let scoreTuningCache = undefined;
let scoreTuningPromise = null;

export async function loadScoreTuningSummary() {
  if (scoreTuningCache !== undefined) return scoreTuningCache;
  if (scoreTuningPromise) return scoreTuningPromise;
  scoreTuningPromise = (async () => {
    const md = await fetchText('score_tuning.md', true);
    if (!md) {
      scoreTuningCache = null;
      return null;
    }
    const aucMatch = md.match(/\*\*평균 AUC[^*]*\*\*:\s*(.+)/);
    const aucLine = aucMatch ? aucMatch[1].trim() : '';
    scoreTuningCache = aucLine ? { aucLine } : null;
    return scoreTuningCache;
  })();
  try {
    return await scoreTuningPromise;
  } finally {
    scoreTuningPromise = null;
  }
}

let outcomeGradeSummaryCache = null;

export async function queryOutcomeGradeSummary() {
  if (outcomeGradeSummaryCache) return outcomeGradeSummaryCache;
  const sql = `
    SELECT program,
           MAX(program_label) AS program_label,
           grade,
           weight,
           LOWER(COALESCE(result, '')) AS result,
           COUNT(*)::INT AS total_rows,
           COUNT(*) FILTER (WHERE counted)::INT AS counted_rows
    FROM outcomes
    GROUP BY program, grade, weight, LOWER(COALESCE(result, ''))
    ORDER BY weight DESC, grade ASC, program ASC
  `;
  try {
    const { rows } = await runRawSql(sql);
    outcomeGradeSummaryCache = rows;
    return rows;
  } catch (_) {
    return [];
  }
}

const DEFAULT_DEBUT_CUTOFFS = [
  '2023-01-01', '2023-07-01', '2024-01-01', '2024-07-01', '2025-01-01', '2025-07-01',
];
const debutScorecardCache = new Map();

/**
 * docs/lab/sql/source_scorecard_debut.sql을 브라우저 DuckDB에서 직접 실행해
 * 백지 신인 데뷔 코호트 기준 출처별 적중률·배수·첫 언급 중앙 일수를 계산한다.
 */
export async function queryDebutScorecard({
  cutoffs = DEFAULT_DEBUT_CUTOFFS,
  mentionMonths = 6,
  horizonMonths = 24,
} = {}) {
  const cleanCutoffs = (Array.isArray(cutoffs) ? cutoffs : []).filter(d => DATE_RE.test(d));
  const useCutoffs = cleanCutoffs.length ? cleanCutoffs : DEFAULT_DEBUT_CUTOFFS;
  const mSql = sqlInt(mentionMonths, 1, 24, 6);
  const hSql = sqlInt(horizonMonths, 1, 60, 24);
  const cacheKey = `${useCutoffs.join(',')}|${mSql}|${hSql}`;
  if (debutScorecardCache.has(cacheKey)) return debutScorecardCache.get(cacheKey);

  const tpl = await getSqlTemplate('source_scorecard_debut');
  const empty = {
    cutoffs: useCutoffs,
    mentionMonths: Number(mSql),
    horizonMonths: Number(hSql),
    cohortTeams: 0,
    cohortHits: 0,
    baseRate: null,
    unmentioned: null,
    unmentionedPct: null,
    sourceRows: [],
    bySrc: new Map(),
  };
  if (!tpl) return empty;

  const cutoffsSql = useCutoffs.map(d => `(DATE '${d}')`).join(', ');
  const sql = fillTemplate(tpl, {
    cutoffs: cutoffsSql,
    mention_months: mSql,
    horizon_months: hSql,
  });
  appState.lastSql.debut_scorecard = sql;

  try {
    const { rows } = await runRawSql(sql);
    const first = rows[0] || null;
    const cohortTeams = first ? Number(first.cohort_teams) || 0 : 0;
    const cohortHits = first ? Number(first.cohort_hits) || 0 : 0;
    const baseRate = first && first.base_rate !== null && first.base_rate !== undefined
      ? Number(first.base_rate)
      : null;
    const unmentioned = rows.find(r => r.src === '(언급 없음)') || null;
    const unmentionedPct = unmentioned && cohortTeams > 0
      ? Math.round((Number(unmentioned.teams) / cohortTeams) * 100)
      : null;
    const sourceRows = rows.filter(r => r.src !== '(언급 없음)');
    const bySrc = new Map();
    for (const r of sourceRows) {
      if (r.src) bySrc.set(r.src, r);
    }
    const result = {
      cutoffs: useCutoffs,
      mentionMonths: Number(mSql),
      horizonMonths: Number(hSql),
      cohortTeams,
      cohortHits,
      baseRate,
      unmentioned,
      unmentionedPct,
      sourceRows,
      bySrc,
    };
    debutScorecardCache.set(cacheKey, result);
    return result;
  } catch (_) {
    return empty;
  }
}

/**
 * docs/lab/sql/debut_candidates.sql을 브라우저 DuckDB에서 실행해
 * 기준일 전 12개월 안에 첫 발매(teams.first_release)가 있고 첫 발매 전 외부 신호가 없는 '백지 신인'을 조회한다.
 * 자기 발매(발매 갈래)는 언급으로 세지 않으며, 점수는 features.sql의 lab_scored() 매크로로 계산한다.
 */
export async function queryDebutCandidates(overrides = {}) {
  const p = buildParams(overrides);
  const asOfStr = p.as_of.slice(1, -1);

  const tpl = await getSqlTemplate('debut_candidates');
  if (!tpl) {
    return { asOf: asOfStr, total: 0, mentioned: [], unmentioned: [] };
  }

  const sql = fillTemplate(tpl, p);
  appState.lastSql.debut_candidates = sql;

  const cached = lruGet(debutCandidatesCache, sql);
  if (cached) return cached;

  const { rows } = await runRawSql(sql);
  const byTeam = new Map();
  for (const r of rows) {
    if (!byTeam.has(r.team_key)) {
      byTeam.set(r.team_key, {
        team_key: r.team_key,
        display_name: r.display_name || r.team_key,
        primary_genre: r.primary_genre || '',
        first_release: r.first_release || '',
        profile_status: r.profile_status || '',
        had_outcome: Boolean(r.had_outcome),
        score: r.score !== null && r.score !== undefined ? Number(r.score) : null,
        mentions: [],
      });
    }
    if (r.src) {
      byTeam.get(r.team_key).mentions.push({
        src: r.src,
        role: r.role || 'pending',
        first_mention_date: r.first_mention_date || '',
        days_to_mention: r.days_to_mention !== null && r.days_to_mention !== undefined ? Number(r.days_to_mention) : null,
        mention_cnt: Number(r.mention_cnt) || 1,
      });
    }
  }

  const all = [...byTeam.values()];
  for (const t of all) {
    t.mentions.sort((a, b) => (a.days_to_mention ?? 99999) - (b.days_to_mention ?? 99999));
  }
  const mentioned = all.filter(t => t.mentions.length > 0);
  const unmentioned = all
    .filter(t => t.mentions.length === 0)
    .sort((a, b) => String(b.first_release).localeCompare(String(a.first_release)));

  const result = {
    asOf: asOfStr,
    total: all.length,
    mentioned,
    unmentioned,
  };
  lruSet(debutCandidatesCache, sql, result);
  return result;
}

// ---------- Interactive Team Ego Network Graph ----------

function resolveGraphWindow(period = 'all') {
  const asOf = safeIsoDate(appState.cfg.as_of || appState.dataEnd, '2026-11-27');
  const dataEnd = safeIsoDate(appState.dataEnd, asOf);
  const untilDate = asOf >= dataEnd ? '2099-12-31' : asOf;
  let sinceDate = '1900-01-01';
  if (period === '1y') {
    const ms = Date.parse(`${asOf}T00:00:00Z`) - 365 * 86400000;
    sinceDate = new Date(ms).toISOString().slice(0, 10);
  }
  return { asOf, sinceDate, untilDate };
}

function buildSceneNeighbor(teamKey, sceneMap) {
  const comm = sceneMap?.teamToCommunity?.get(teamKey);
  if (!comm) return null;
  const venuesTxt = Array.isArray(comm.top_venues) && comm.top_venues.length
    ? comm.top_venues.slice(0, 3).map(v => v.venue).join(' · ')
    : '';
  return {
    node_id: `scene:${comm.id}`,
    node_type: 'scene',
    node_key: String(comm.id),
    label: `씬 묶음 ${comm.id}`,
    relation: 'scene',
    weight: Number(comm.size) || 1,
    grade: '',
    detail: venuesTxt ? `${comm.size || 0}팀 · ${venuesTxt}` : `${comm.size || 0}팀`,
    last_date: '',
    primary_genre: '',
  };
}

/**
 * docs/lab/sql/ego_network.sql을 브라우저 DuckDB에서 실행하고,
 * scene_map.json의 속한 씬 묶음을 합쳐 1-hop 이웃 목록을 반환한다.
 */
export async function queryEgoNetwork(teamKey, { period = 'all', limitPerKind = 12 } = {}) {
  if (!teamKey) return [];
  const { sinceDate, untilDate } = resolveGraphWindow(period);
  const lim = sqlInt(limitPerKind, 1, 40, 12);
  const cacheKey = `${teamKey}::${sinceDate}::${untilDate}::${lim}`;
  const cached = lruGet(egoNetCache, cacheKey);
  if (cached) return cached.map(r => ({ ...r }));

  const [tpl, sceneMap] = await Promise.all([
    getSqlTemplate('ego_network'),
    loadSceneMap(),
  ]);

  let sqlRes = { rows: [] };
  if (tpl) {
    const sql = fillTemplate(tpl, {
      team_key: sqlStringLiteral(teamKey),
      since_date: sqlDate(sinceDate, '1900-01-01'),
      until_date: sqlDate(untilDate, '2099-12-31'),
      limit_per_kind: lim,
    });
    appState.lastSql.ego_network = sql;
    sqlRes = await runRawSql(sql);
  }

  const rows = [...(sqlRes.rows || [])];
  const sceneNode = buildSceneNeighbor(teamKey, sceneMap);
  if (sceneNode) rows.push(sceneNode);
  lruSet(egoNetCache, cacheKey, rows);
  return rows.map(r => ({ ...r }));
}

/**
 * 그래프에서 노드를 클릭했을 때 그 노드의 1-hop 이웃을 DuckDB/scene_map에서 확장 조회한다.
 * - team/ego: ego_network.sql 실행
 * - venue: 해당 공연장에 선 상위 후보·다회 출연 팀
 * - outcome: 해당 정답 프로그램 수상/후보 팀
 * - program: 해당 선정·지원 프로그램 팀
 * - outlet: 해당 매체가 다룬 팀
 * - scene: 해당 씬 묶음의 상위 후보·허브 팀
 */
export async function queryNodeExpansion(node, { period = 'all', limit = 10 } = {}) {
  if (!node || !node.node_type || !node.node_key) return [];
  const type = node.node_type;
  const key = String(node.node_key);
  const lim = Math.max(1, Math.min(30, Math.round(Number(limit) || 10)));

  if (type === 'team' || type === 'ego') {
    return queryEgoNetwork(key, { period, limitPerKind: Math.min(8, lim) });
  }

  if (type === 'scene') {
    const sceneMap = await loadSceneMap();
    const comm = sceneMap?.communityById?.get(Number(key));
    if (!comm) return [];
    const validTeams = appState.teamIndex?.length
      ? new Set(appState.teamIndex.map(t => t.team_key))
      : null;
    const merged = [];
    const seen = new Set();
    for (const c of (comm.top_candidates || [])) {
      if (!c?.team_key || seen.has(c.team_key)) continue;
      if (validTeams && !validTeams.has(c.team_key)) continue;
      seen.add(c.team_key);
      merged.push({
        node_id: `team:${c.team_key}`,
        node_type: 'team',
        node_key: c.team_key,
        label: c.display_name || c.name || c.team_key,
        relation: 'scene',
        weight: Number(c.score) || 1,
        grade: '',
        detail: c.score ? `상위 후보 · ${Number(c.score).toFixed(1)}점` : '상위 후보',
        last_date: '',
        primary_genre: c.primary_genre || '',
      });
    }
    for (const h of (comm.hubs || [])) {
      if (!h?.team_key || seen.has(h.team_key)) continue;
      if (validTeams && !validTeams.has(h.team_key)) continue;
      seen.add(h.team_key);
      const deg = Number(h.degree ?? h.links) || 1;
      merged.push({
        node_id: `team:${h.team_key}`,
        node_type: 'team',
        node_key: h.team_key,
        label: h.display_name || h.name || h.team_key,
        relation: 'scene',
        weight: deg,
        grade: '',
        detail: deg ? `씬 허브 · 연결 ${deg}` : '씬 허브',
        last_date: '',
        primary_genre: h.primary_genre || '',
      });
    }
    return merged.slice(0, lim);
  }

  const { sinceDate, untilDate } = resolveGraphWindow(period);
  const sinceLit = sqlDate(sinceDate, '1900-01-01');
  const untilLit = sqlDate(untilDate, '2099-12-31');
  const keyLit = sqlStringLiteral(key);
  const fetchLim = Math.max(lim * 3, 24);
  const snapLatest = appState.snapshots?.latest || new Map();

  if (type === 'venue') {
    const { rows } = await runRawSql(`
      WITH gig AS (
        SELECT DISTINCT team_key, signal_date
        FROM signals
        WHERE branch = '공연'
          AND TRIM(COALESCE(venue, '')) = ${keyLit}
          AND signal_date >= DATE ${sinceLit}
          AND signal_date <= DATE ${untilLit}
      )
      SELECT 'team:' || g.team_key                AS node_id,
             'team'                               AS node_type,
             g.team_key                           AS node_key,
             COALESCE(t.display_name, g.team_key) AS label,
             'venue'                              AS relation,
             COUNT(*)::DOUBLE                     AS weight,
             ''                                   AS grade,
             COUNT(*)::VARCHAR || '회 공연'        AS detail,
             MAX(g.signal_date)                   AS last_date,
             COALESCE(t.primary_genre, '')        AS primary_genre
      FROM gig g
      JOIN teams t ON t.team_key = g.team_key
      GROUP BY g.team_key, t.display_name, t.primary_genre
      ORDER BY weight DESC, last_date DESC
      LIMIT ${fetchLim}
    `);
    rows.sort((a, b) => {
      const ra = snapLatest.get(a.node_key)?.rank ?? 99999;
      const rb = snapLatest.get(b.node_key)?.rank ?? 99999;
      const aCand = ra < 99999 ? 0 : 1;
      const bCand = rb < 99999 ? 0 : 1;
      if (aCand !== bCand) return aCand - bCand;
      if (aCand === 0 && ra !== rb) return ra - rb;
      return (Number(b.weight) || 0) - (Number(a.weight) || 0);
    });
    return rows.slice(0, lim);
  }

  if (type === 'outcome') {
    const { rows } = await runRawSql(`
      SELECT 'team:' || o.team_key                                         AS node_id,
             'team'                                                        AS node_type,
             o.team_key                                                    AS node_key,
             COALESCE(t.display_name, o.team_key)                          AS label,
             'outcome'                                                     AS relation,
             COALESCE(MAX(o.weight), 1)::DOUBLE                            AS weight,
             COALESCE(ARG_MAX(o.grade, o.weight), '')                      AS grade,
             STRING_AGG(DISTINCT COALESCE(NULLIF(o.result, ''), o.tier, ''), ', ') AS detail,
             MAX(o.announced_date)                                         AS last_date,
             COALESCE(t.primary_genre, '')                                 AS primary_genre
      FROM outcomes o
      JOIN teams t ON t.team_key = o.team_key
      WHERE o.program = ${keyLit}
        AND o.counted
        AND o.announced_date >= DATE ${sinceLit}
        AND o.announced_date <= DATE ${untilLit}
      GROUP BY o.team_key, t.display_name, t.primary_genre
      ORDER BY last_date DESC, weight DESC
      LIMIT ${lim}
    `);
    return rows;
  }

  if (type === 'program') {
    const { rows } = await runRawSql(`
      SELECT 'team:' || s.team_key                AS node_id,
             'team'                               AS node_type,
             s.team_key                           AS node_key,
             COALESCE(t.display_name, s.team_key) AS label,
             'program'                            AS relation,
             COUNT(DISTINCT s.signal_date)::DOUBLE AS weight,
             ''                                   AS grade,
             CAST(MAX(s.signal_date) AS VARCHAR)  AS detail,
             MAX(s.signal_date)                   AS last_date,
             COALESCE(t.primary_genre, '')        AS primary_genre
      FROM signals s
      JOIN teams t ON t.team_key = s.team_key
      WHERE s.branch = '선정·지원'
        AND s.program = ${keyLit}
        AND s.signal_date >= DATE ${sinceLit}
        AND s.signal_date <= DATE ${untilLit}
      GROUP BY s.team_key, t.display_name, t.primary_genre
      ORDER BY last_date DESC, weight DESC
      LIMIT ${fetchLim}
    `);
    rows.sort((a, b) => {
      const ra = snapLatest.get(a.node_key)?.rank ?? 99999;
      const rb = snapLatest.get(b.node_key)?.rank ?? 99999;
      if (ra !== rb) return ra - rb;
      return String(b.last_date || '').localeCompare(String(a.last_date || ''));
    });
    return rows.slice(0, lim);
  }

  if (type === 'outlet') {
    const colonIdx = key.indexOf(':');
    const branch = colonIdx >= 0 ? key.slice(0, colonIdx) : '';
    const source = colonIdx >= 0 ? key.slice(colonIdx + 1) : key;
    const { rows } = await runRawSql(`
      SELECT 'team:' || s.team_key                AS node_id,
             'team'                               AS node_type,
             s.team_key                           AS node_key,
             COALESCE(t.display_name, s.team_key) AS label,
             'outlet'                             AS relation,
             COUNT(*)::DOUBLE                     AS weight,
             ''                                   AS grade,
             COUNT(*)::VARCHAR || '회 언급'        AS detail,
             MAX(s.signal_date)                   AS last_date,
             COALESCE(t.primary_genre, '')        AS primary_genre
      FROM signals s
      JOIN teams t ON t.team_key = s.team_key
      WHERE (${branch ? `s.branch = ${sqlStringLiteral(branch)}` : 'true'})
        AND s.source = ${sqlStringLiteral(source)}
        AND COALESCE(s.role, '') <> 'excluded'
        AND s.signal_date >= DATE ${sinceLit}
        AND s.signal_date <= DATE ${untilLit}
      GROUP BY s.team_key, t.display_name, t.primary_genre
      ORDER BY weight DESC, last_date DESC
      LIMIT ${fetchLim}
    `);
    rows.sort((a, b) => {
      const ra = snapLatest.get(a.node_key)?.rank ?? 99999;
      const rb = snapLatest.get(b.node_key)?.rank ?? 99999;
      const aCand = ra < 99999 ? 0 : 1;
      const bCand = rb < 99999 ? 0 : 1;
      if (aCand !== bCand) return aCand - bCand;
      if (aCand === 0 && ra !== rb) return ra - rb;
      return (Number(b.weight) || 0) - (Number(a.weight) || 0);
    });
    return rows.slice(0, lim);
  }

  return [];
}

/**
 * docs/lab/sql/scene_network.sql을 실행해 전체/장르별 씬 네트워크(상위 N팀 + 같은 무대 엣지)를 반환하고,
 * scene_map.json의 씬 묶음 정보와 결합한다.
 */
export async function querySceneNetwork({ limit = 150, genre } = {}) {
  const tpl = await getSqlTemplate('scene_network');
  if (!tpl) {
    return {
      nodes: [],
      edges: [],
      communities: [],
      winnerCount: 0,
      candidateCount: 0,
      genre: genre ?? appState.cfg.genre ?? '',
      limit,
    };
  }

  const useLimit = Math.max(20, Math.min(400, Math.round(Number(limit) || 150)));
  const useGenre = genre !== undefined ? String(genre || '') : String(appState.cfg.genre || '');
  const { untilDate } = resolveGraphWindow('all');
  const params = buildParams({ limit: useLimit, genre: useGenre });
  const sql = fillTemplate(tpl, {
    ...params,
    until_date: sqlDate(untilDate, '2099-12-31'),
  });
  appState.lastSql.scene_network = sql;

  const cached = lruGet(sceneNetCache, sql);
  if (cached) {
    return {
      ...cached,
      nodes: cached.nodes.map(n => ({ ...n })),
      edges: cached.edges.map(e => ({ ...e })),
      communities: cached.communities.map(c => ({ ...c })),
    };
  }

  const [sqlRes, sceneMap] = await Promise.all([
    runRawSql(sql),
    loadSceneMap(),
  ]);

  const rawRows = sqlRes.rows || [];
  const nodeRows = [];
  const edgeRows = [];
  for (const r of rawRows) {
    if (r.row_kind === 'edge') edgeRows.push(r);
    else if (r.row_kind === 'node') nodeRows.push(r);
  }

  const commCounts = new Map();
  const nodeById = new Map();
  let winnerCount = 0;
  let candidateCount = 0;

  const nodes = nodeRows.map(r => {
    const key = String(r.team_key || '');
    const comm = sceneMap?.teamToCommunity?.get(key) || null;
    const commId = comm && comm.id !== undefined && comm.id !== null ? Number(comm.id) : null;
    const commVenues = comm && Array.isArray(comm.top_venues)
      ? comm.top_venues.slice(0, 3).map(v => v.venue).filter(Boolean)
      : [];
    const hadOutcome = Boolean(r.had_outcome);
    if (hadOutcome) winnerCount += 1;
    else candidateCount += 1;

    if (commId !== null) {
      if (!commCounts.has(commId)) {
        commCounts.set(commId, {
          id: commId,
          count: 0,
          size: Number(comm.size) || 0,
          topVenues: commVenues,
        });
      }
      commCounts.get(commId).count += 1;
    }

    const imgEntry = appState.imagesByTeam?.get(key);
    const node = {
      id: key,
      team_key: key,
      display_name: r.display_name || key,
      score: Number(r.score) || 0,
      cand_rank: r.cand_rank !== null && r.cand_rank !== undefined ? Number(r.cand_rank) : null,
      primary_genre: r.primary_genre || '',
      had_outcome: hadOutcome,
      outcome_grade: r.outcome_grade || '',
      outcome_label: r.outcome_label || '',
      gigs_1y: Number(r.gigs_1y) || 0,
      venues: Number(r.venues) || 0,
      n_branch: Number(r.n_branch) || 0,
      last_date: r.last_date ? String(r.last_date).slice(0, 10) : '',
      communityId: commId,
      communitySize: comm ? Number(comm.size) || 0 : 0,
      communityVenues: commVenues,
      colorSlot: -1,
      imageUrl: imgEntry?.image_url || '',
      degree: 0,
    };
    nodeById.set(key, node);
    return node;
  });

  // Top 8 communities visible in the current network get color slots 0..7
  const communities = [...commCounts.values()]
    .sort((a, b) => (b.count - a.count) || (b.size - a.size) || (a.id - b.id));
  const slotByCommId = new Map();
  communities.slice(0, 8).forEach((c, idx) => {
    c.colorSlot = idx;
    slotByCommId.set(c.id, idx);
  });
  for (const n of nodes) {
    if (n.communityId !== null && slotByCommId.has(n.communityId)) {
      n.colorSlot = slotByCommId.get(n.communityId);
    }
  }

  const edges = [];
  for (const r of edgeRows) {
    const src = String(r.team_key || '');
    const tgt = String(r.target_key || '');
    if (!src || !tgt || src === tgt) continue;
    const a = nodeById.get(src);
    const b = nodeById.get(tgt);
    if (!a || !b) continue;
    a.degree += 1;
    b.degree += 1;
    edges.push({
      source: src,
      target: tgt,
      weight: Math.max(1, Number(r.weight) || 1),
      detail: r.detail || '',
      last_date: r.last_date ? String(r.last_date).slice(0, 10) : '',
    });
  }

  const result = {
    nodes,
    edges,
    communities,
    winnerCount,
    candidateCount,
    genre: useGenre,
    limit: useLimit,
  };
  lruSet(sceneNetCache, sql, result);
  return {
    ...result,
    nodes: result.nodes.map(n => ({ ...n })),
    edges: result.edges.map(e => ({ ...e })),
    communities: result.communities.map(c => ({ ...c })),
  };
}





