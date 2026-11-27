/**
 * 5-2 저장 필터에 맞는 팀을 아무 기준일로나 다시 계산 — 브리핑 카드와 저장 때 미리보기가 같은 함수를 쓴다.
 * 규칙: 후보 SQL(저장한 설정 그대로, 기준일만 바꿈) → saved_match.js 의 화면 조건(단계·첫 발매·지역·기간·검색어).
 * '떠오르는 팀' 프리셋은 rising_preset.sql 을 그 기준일로 돌린다. '변화' 조건은 날짜마다 뜻이 달라 뺀다.
 */
import { appState, cloneDefaults } from './state.js';
import {
  buildParams, ensureTeamCitiesLoaded, fillTemplate, getSqlTemplate, queryDiscoveryStages,
  queryRisingPreset, runRawSql,
} from './db.js';
import { isoMinusDays } from './components/team_metrics.js';
import { filterSavedRows, newMatches } from './components/saved_match.js';
import { loadVenueLadder } from './db_venue.js';

const cache = new Map(); // JSON(spec)|asOf -> rows
const CACHE_MAX = 24;
const WEEK_DAYS = 7;

function remember(key, val) {
  cache.set(key, val);
  if (cache.size > CACHE_MAX) cache.delete(cache.keys().next().value);
  return val;
}

async function candidateRows(cfg, asOf) {
  const tpl = await getSqlTemplate('candidates');
  if (!tpl) return [];
  const res = await runRawSql(fillTemplate(tpl, buildParams({ as_of: asOf }, cfg)));
  return res.rows;
}

function stageFallbackRows(stageRows, stage, cfg) {
  const lim = Math.max(10, Number(cfg.limit) || 100);
  return stageRows
    .filter(s => s.stage === stage && (!cfg.genre || s.primary_genre === cfg.genre))
    .slice(0, lim);
}

/**
 * 기준일 asOf 에 저장 필터에 맞는 팀들(후보 순서 그대로).
 * @returns {Promise<Array<{ team_key: string, display_name: string }>>}
 */
export async function querySavedMatches(spec, asOf) {
  const key = `${JSON.stringify(spec)}|${asOf}`;
  if (cache.has(key)) return cache.get(key);
  const cfg = { ...cloneDefaults(), ...spec.cfg, as_of: asOf };
  await ensureTeamCitiesLoaded();
  const stageData = await queryDiscoveryStages({ as_of: asOf, newcomer_years: cfg.newcomer_years });
  const stageByTeam = new Map((stageData?.rows || []).map(s => [s.team_key, s.stage]));

  let rows;
  if (spec.preset === 'rising') {
    rows = await queryRisingPreset({ as_of: asOf });
  } else if (spec.stage === '0' || spec.stage === '4') {
    rows = stageFallbackRows(stageData?.rows || [], Number(spec.stage), cfg);
  } else {
    rows = await candidateRows(cfg, asOf);
  }

  const firstRelease = new Map(appState.firstReleaseByTeam);
  for (const s of stageData?.rows || []) if (s.first_release && !firstRelease.has(s.team_key)) firstRelease.set(s.team_key, s.first_release);
  const homeCity = new Map([...appState.teamCitiesByTeam].map(([k, v]) => [k, v.home_city]));
  const ladder = spec.tier ? await loadVenueLadder() : null;
  const maxTier = new Map(Object.entries(ladder?.teams || {}).map(([k, v]) => [k, v?.max]));
  const genreConf = appState.genreConfidenceByTeam || new Map();

  const matched = filterSavedRows(rows, spec, asOf, { stageByTeam, firstRelease, homeCity, maxTier, genreConf })
    .map(r => ({ team_key: r.team_key, display_name: r.display_name || r.team_key }));
  return remember(key, matched);
}

/**
 * 기준일 to 에 새로 맞는 팀 = to 엔 맞고 to−7일엔 안 맞던 팀.
 * 브리핑 카드는 to = 데이터 기준일, 저장 때 미리보기는 to = 기준일−7일(= '지난주였다면').
 */
export async function querySavedNewMatches(spec, to) {
  const from = isoMinusDays(to, WEEK_DAYS);
  const [nowRows, prevRows] = await Promise.all([querySavedMatches(spec, to), querySavedMatches(spec, from)]);
  return { from, to, total: nowRows.length, added: newMatches(nowRows, prevRows) };
}
