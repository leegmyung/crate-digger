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

let dbInstance = null;
let connInstance = null;

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

export async function runRawSql(sql) {
  if (!connInstance) throw new Error('DuckDB-WASM이 아직 초기화되지 않았습니다.');
  const res = await connInstance.query(sql);
  return arrowToRows(res);
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

function fillTemplate(tpl, map) {
  let out = tpl;
  for (const [k, v] of Object.entries(map)) {
    out = out.split(`{{${k}}}`).join(v);
  }
  return out;
}

export function buildParams(overrides = {}) {
  const c = appState.cfg;
  const fallbackAsOf = appState.dataEnd || '2026-11-27';
  return {
    cutoff: sqlDate(overrides.cutoff || c.cutoffs[0] || '2025-01-01', '2025-01-01'),
    as_of: sqlDate(overrides.as_of || c.as_of, fallbackAsOf),
    lookback_years: sqlInt(c.lookback_years, 1, 15, 3),
    newcomer_years: sqlInt(c.newcomer_years, 1, 15, 3),
    exclude_famous: sqlBool(c.exclude_famous),
    outcome_tier: sqlTier(c.outcome_tier),
    horizon_months: sqlInt(c.horizon_months, 1, 60, 24),
    genre: sqlGenre(c.genre),
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
    k_list: sqlKList(c.k_list),
    only_no_outcome: sqlBool(overrides.only_no_outcome !== undefined ? overrides.only_no_outcome : c.only_no_outcome),
    limit: sqlInt(overrides.limit !== undefined ? overrides.limit : c.limit, 10, 1000, 100),
    team_key: sqlStringLiteral(overrides.team_key || ''),
  };
}

// ---------- Bootstrap ----------

async function fetchText(path, optional = false) {
  try {
    const r = await fetch(path);
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

async function fetchJson(path, optional = false) {
  try {
    const r = await fetch(path);
    if (!r.ok) {
      if (optional) return null;
      throw new Error(`${path} 불러오기 실패 (HTTP ${r.status})`);
    }
    return r.json();
  } catch (err) {
    if (optional) return null;
    throw err;
  }
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
 * 우선순위: 스포티파이(i.scdn.co) → 유튜브 채널 썸네일(yt3.ggpht.com / yt3.googleusercontent.com).
 */
function parseImagesCsv(text) {
  const urlMap = new Map();
  const metaMap = new Map();
  if (!text) return { urlMap, metaMap };
  const lines = text.trim().split(/\r?\n/).slice(1);
  const row = /^(.*),(https:\/\/(?:i\.scdn\.co|yt3\.ggpht\.com|yt3\.googleusercontent\.com)\/[^\s,]+),([^,]*)$/;
  const priority = src => (src === 'spotify' ? 0 : src === 'youtube' ? 1 : 2);
  for (const line of lines) {
    const m = line.match(row);
    if (!m) continue;
    const teamKey = m[1].replace(/^"(.*)"$/, '$1').replace(/""/g, '"');
    const url = m[2];
    const source = (m[3] || '').trim().toLowerCase() || (url.includes('i.scdn.co') ? 'spotify' : 'youtube');
    if (!teamKey) continue;
    const prev = metaMap.get(teamKey);
    if (!prev || priority(source) < priority(prev.source)) {
      urlMap.set(teamKey, url);
      metaMap.set(teamKey, { url, source });
    }
  }
  return { urlMap, metaMap };
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

  // 1) collect.json runs check (latest run per table+source: file_ok === false, rows === 0, or prev_rows sudden drop)
  const runs = Array.isArray(collect?.runs) ? collect.runs : [];
  let totalSources = 0;
  let okSources = 0;
  let lastCollectedDate = '';
  if (runs.length) {
    const latestByKey = new Map();
    for (const r of runs) {
      const dateStr = String(r.date || '');
      if (dateStr > lastCollectedDate) lastCollectedDate = dateStr;
      const key = `${r.table || ''}::${r.source || ''}`;
      const prev = latestByKey.get(key);
      if (!prev || dateStr > String(prev.date || '')) {
        latestByKey.set(key, r);
      }
    }
    const latestRuns = [...latestByKey.values()];
    totalSources = latestRuns.length;
    const failed = [];
    const zeroRows = [];
    const dropped = [];
    for (const r of latestRuns) {
      const name = r.source || '알 수 없는 소스';
      if (r.file_ok === false) {
        failed.push(name);
      } else if (Number(r.rows) === 0) {
        zeroRows.push(name);
      } else {
        okSources += 1;
        if (Number(r.prev_rows) >= 20 && Number(r.rows) < Number(r.prev_rows) * 0.5) {
          dropped.push(`${name}(${r.prev_rows}→${r.rows})`);
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
      pushIssue('warn', `직전 대비 수집량 50% 이상 급감: ${dropped.slice(0, 3).join(', ')}`);
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

export async function bootstrapData(onStatus = () => {}) {
  onStatus('데이터·SQL·DuckDB-WASM 불러오는 중...');
  const [
    meta,
    sigCsv,
    teamsCsv,
    outCsv,
    progCsv,
    featSql,
    btSql,
    candSql,
    sigHitSql,
    precSql,
    teamSql,
    relSql,
    snapIdx,
    dashJson,
    collectJson,
  ] = await Promise.all([
    fetchJson('lab/data/meta.json'),
    fetchText('lab/data/signals.csv'),
    fetchText('lab/data/teams.csv'),
    fetchText('lab/data/outcomes.csv'),
    fetchText('lab/data/programs.csv'),
    fetchText('lab/sql/features.sql'),
    fetchText('lab/sql/backtest.sql'),
    fetchText('lab/sql/candidates.sql'),
    fetchText('lab/sql/signal_hits.sql'),
    fetchText('lab/sql/precedents.sql', true),
    fetchText('lab/sql/team.sql', true),
    fetchText('lab/sql/related.sql', true),
    fetchJson('lab/data/snapshots/index.json', true),
    fetchJson('data/dashboard.json', true),
    fetchJson('data/collect.json', true),
    initEngine(),
  ]);

  appState.meta = meta;
  appState.dataEnd = meta?.data_end || '2026-11-27';
  appState.dashboardJson = dashJson;
  appState.collectJson = collectJson;
  appState.dataHealth = computeDataHealth(meta, collectJson, dashJson);
  appState.sqlTemplates = {
    features: featSql || '',
    backtest: btSql || '',
    candidates: candSql || '',
    signal_hits: sigHitSql || '',
    precedents: precSql || '',
    team: teamSql || '',
    related: relSql || '',
  };

  // Optional datasets gated by meta.rows to avoid noisy 404s before files exist
  const hasLinksMeta = !meta?.rows || meta.rows.links === undefined || meta.rows.links > 0;
  const hasVideosMeta = Boolean(meta?.rows && Number(meta.rows.videos) > 0);
  const hasImagesMeta = Boolean(meta?.rows && Number(meta.rows.images) > 0);
  const [linksCsv, videosCsv, imagesCsv] = await Promise.all([
    hasLinksMeta ? fetchText('lab/data/links.csv', true) : Promise.resolve(null),
    hasVideosMeta ? fetchText('lab/data/videos.csv', true) : Promise.resolve(null),
    hasImagesMeta ? fetchText('lab/data/images.csv', true) : Promise.resolve(null),
  ]);

  onStatus('브라우저 DB에 표 적재 중...');
  const regTasks = [
    dbInstance.registerFileText('signals.csv', sigCsv),
    dbInstance.registerFileText('teams.csv', teamsCsv),
    dbInstance.registerFileText('outcomes.csv', outCsv),
    dbInstance.registerFileText('programs.csv', progCsv),
  ];
  if (linksCsv) regTasks.push(dbInstance.registerFileText('links.csv', linksCsv));
  if (videosCsv) regTasks.push(dbInstance.registerFileText('videos.csv', videosCsv));
  if (imagesCsv) regTasks.push(dbInstance.registerFileText('images.csv', imagesCsv));
  await Promise.all(regTasks);

  let createSql = `
    CREATE TABLE signals AS SELECT * FROM read_csv_auto('signals.csv', header=true);
    CREATE TABLE teams AS SELECT * FROM read_csv_auto('teams.csv', header=true);
    CREATE TABLE outcomes AS SELECT * FROM read_csv_auto('outcomes.csv', header=true);
    CREATE TABLE programs AS SELECT * FROM read_csv_auto('programs.csv', header=true);
  `;
  if (linksCsv) createSql += `CREATE TABLE links AS SELECT * FROM read_csv_auto('links.csv', header=true);`;
  if (videosCsv) createSql += `CREATE TABLE videos AS SELECT * FROM read_csv_auto('videos.csv', header=true);`;
  if (imagesCsv) createSql += `CREATE TABLE images AS SELECT * FROM read_csv_auto('images.csv', header=true);`;
  await connInstance.query(createSql);
  await connInstance.query(featSql);

  const snapDates = Array.isArray(snapIdx?.dates) ? snapIdx.dates : [];
  const snapReconstructed = Array.isArray(snapIdx?.reconstructed) ? snapIdx.reconstructed : [];
  const latestDate = snapDates[0] || null;
  const prevDate = snapDates[1] || null;

  const [genreRes, rangeRes, teamIdxRes, snapLatestTxt, snapPrevTxt, linksRes, videosRes] = await Promise.all([
    runRawSql(`
      SELECT primary_genre, COUNT(*) AS n
      FROM teams
      WHERE COALESCE(primary_genre, '') <> ''
      GROUP BY primary_genre
      ORDER BY n DESC, primary_genre
    `),
    runRawSql(`
      SELECT MIN(announced_date) AS min_d, MAX(announced_date) AS max_d, COUNT(*) AS n
      FROM outcomes
      WHERE counted
    `),
    runRawSql(`
      SELECT team_key, display_name, primary_genre
      FROM teams
      ORDER BY display_name
    `),
    latestDate ? fetchText(`lab/data/snapshots/${latestDate}.csv`, true) : Promise.resolve(null),
    prevDate ? fetchText(`lab/data/snapshots/${prevDate}.csv`, true) : Promise.resolve(null),
    linksCsv ? runRawSql(`SELECT team_key, platform, url FROM links`) : Promise.resolve({ rows: [] }),
    videosCsv ? runRawSql(`SELECT team_key, video_id, title, channel_title, published_at, kind FROM videos`) : Promise.resolve({ rows: [] }),
  ]);

  appState.validGenres = genreRes.rows.map(r => r.primary_genre);
  if (rangeRes.rows.length) {
    appState.outcomeRange = {
      min: rangeRes.rows[0].min_d,
      max: rangeRes.rows[0].max_d,
      counted: Number(rangeRes.rows[0].n) || 0,
    };
  }
  appState.teamIndex = teamIdxRes.rows;
  appState.linksByTeam = indexLinksRows(linksRes.rows);
  appState.videosByTeam = indexVideosRows(videosRes.rows);
  const parsedImgs = parseImagesCsv(imagesCsv);
  appState.imagesByTeam = parsedImgs.urlMap;
  appState.imageMetaByTeam = parsedImgs.metaMap;
  appState.snapshots = {
    dates: snapDates,
    reconstructed: snapReconstructed,
    latestDate,
    prevDate,
    latest: parseSnapshotCsv(snapLatestTxt),
    prev: parseSnapshotCsv(snapPrevTxt),
  };
  appState.ready = true;
}

// ---------- High-level query helpers ----------

export async function queryCandidates(overrides = {}) {
  const c = appState.cfg;
  const limit = overrides.limit !== undefined ? overrides.limit : c.limit;
  const sql = fillTemplate(appState.sqlTemplates.candidates, buildParams({ ...overrides, limit }));
  appState.lastSql.candidates = sql;
  const { rows } = await runRawSql(sql);

  // Apply global recent activity period filter if set (> 0 days)
  const days = Number(c.period_days) || 0;
  if (days > 0 && rows.length) {
    const asOfDate = new Date(`${c.as_of || appState.dataEnd}T00:00:00Z`);
    const minDate = new Date(asOfDate.getTime() - days * 86400000).toISOString().slice(0, 10);
    return rows.filter(r => r.last_seen && r.last_seen >= minDate);
  }
  return rows;
}

export async function queryBacktestAll() {
  const cutoffs = appState.cfg.cutoffs;
  if (!cutoffs.length) return [];
  const sqlList = [];
  const blocks = [];
  for (const d of cutoffs) {
    const sql = fillTemplate(appState.sqlTemplates.backtest, buildParams({ cutoff: d }));
    sqlList.push(`-- 기준일 ${d}\n${sql.trim()}`);
    const { rows } = await runRawSql(sql);
    blocks.push({ cutoff: d, rows });
  }
  appState.lastSql.backtest = sqlList.join('\n\n');
  return blocks;
}

export async function querySignalHits(cutoff) {
  const useCutoff = cutoff || appState.cfg.signal_cutoff || appState.cfg.cutoffs[0] || '2025-01-01';
  const sql = fillTemplate(appState.sqlTemplates.signal_hits, buildParams({ cutoff: useCutoff }));
  appState.lastSql.signals = sql;
  const { rows } = await runRawSql(sql);
  return { cutoff: useCutoff, rows };
}

export async function queryTeamDetail(teamKey) {
  const keyLit = sqlStringLiteral(teamKey);
  const p = buildParams({ team_key: teamKey });

  const scoreSql = `
    SELECT team_key, display_name, ROUND(score, 2) AS score, n_branch, best_stage,
           peer_selected, dmz, gigs_1y, outlets, recent180, venues, peer_winner,
           first_seen, last_seen, primary_genre, profile_status, had_outcome,
           ROUND(pts_branch, 2) AS pts_branch, ROUND(pts_stage, 2) AS pts_stage,
           ROUND(pts_peer, 2) AS pts_peer, ROUND(pts_dmz, 2) AS pts_dmz,
           ROUND(pts_gigs, 2) AS pts_gigs, ROUND(pts_outlets, 2) AS pts_outlets,
           ROUND(pts_recent, 2) AS pts_recent, ROUND(pts_venues, 2) AS pts_venues,
           ROUND(pts_winner, 2) AS pts_winner
    FROM lab_scored(DATE ${p.as_of}, ${p.lookback_years}, 50, false,
                    'any', 1, '', ${p.branches},
                    ${p.w_branch}, ${p.w_stage}, ${p.w_peer}, ${p.w_dmz}, ${p.w_gigs}, ${p.w_outlets}, ${p.outlet_cap},
                    ${p.w_recent}, ${p.w_venues}, ${p.w_winner})
    WHERE team_key = ${keyLit}
    LIMIT 1
  `;

  const teamProfileSql = `SELECT * FROM teams WHERE team_key = ${keyLit} LIMIT 1`;
  const outcomesSql = `
    SELECT announced_date, program, program_label, tier, counted
    FROM outcomes
    WHERE team_key = ${keyLit}
    ORDER BY announced_date DESC
  `;

  const timelineSql = appState.sqlTemplates.team
    ? fillTemplate(appState.sqlTemplates.team, { team_key: keyLit })
    : `SELECT signal_date, branch, source, program, program AS program_label, venue, false AS is_upcoming FROM signals WHERE team_key = ${keyLit} ORDER BY signal_date DESC`;
  appState.lastSql.team = timelineSql;

  let precPromise = Promise.resolve({ rows: [] });
  if (appState.sqlTemplates.precedents) {
    const precSql = fillTemplate(appState.sqlTemplates.precedents, { team_key: keyLit });
    appState.lastSql.precedents = precSql;
    precPromise = runRawSql(precSql);
  }

  let relPromise = Promise.resolve({ rows: [] });
  if (appState.sqlTemplates.related) {
    const relSql = fillTemplate(appState.sqlTemplates.related, { team_key: keyLit });
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

  return {
    profile: profileRes.rows[0] || null,
    scored: scoreRes.rows[0] || null,
    timeline: timelineRes.rows,
    outcomes: outcomeRes.rows,
    precedents: precRes.rows,
    related: relRes.rows,
    links: appState.linksByTeam.get(teamKey) || new Map(),
    videos: appState.videosByTeam.get(teamKey) || [],
  };
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
                      ${p.w_recent}, ${p.w_venues}, ${p.w_winner})
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
  const byBranch = {};
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
  } catch (_) {}

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
