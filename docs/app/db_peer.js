/**
 * 이웃 비교(docs/lab/sql/peer_compare.sql) 질의 — 색 지도(2-5)와 팀 상세 동료 비교(3-4)가 같이 쓴다.
 * db.js 가 이미 커서, 이 질의만 따로 둔다.
 */
import { appState } from './state.js';
import { buildParams, fillTemplate, getSqlTemplate, runRawSql } from './db.js';

export const MIN_PEERS = 30; // peer_compare.sql 기본값(이웃이 이보다 적으면 '비교군 작음')
const CACHE_MAX = 6;
const peerCache = new Map(); // sql -> { rows, byTeam }

// peer_compare.sql 의 '팀마다 쓸 층' 줄 — scope 를 고정하려면 이 줄만 바꾼다(없으면 원래대로)
const CHOSEN_LINE = "WHERE scope = CASE WHEN genre_key IS NULL THEN '단계' ELSE '단계+장르' END";
const SCOPE_LINES = {
  stage: "WHERE scope = '단계'",          // 같은 발굴 단계 전체
  genre: "WHERE scope = '단계+장르'",      // 같은 단계 + 같은 장르(profile·press 장르 팀만, 추정 장르 제외)
};

const PCT_KEYS = [
  'score_pct', 'branch_pct', 'stage_pct', 'outlets_pct', 'venues_pct',
  'winner_pct', 'context_pct', 'gigs_pct', 'top_share',
];

function toNumOrNull(v) {
  if (v === null || v === undefined || v === '') return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function normalizeRow(r) {
  const out = {
    ...r,
    stage: toNumOrNull(r.stage),
    peer_n: toNumOrNull(r.peer_n),
    peer_rank: toNumOrNull(r.peer_rank),
    score: toNumOrNull(r.score),
  };
  for (const k of PCT_KEYS) out[k] = toNumOrNull(r[k]);
  return out;
}

/**
 * 기준일 기준 이웃 비교 전체(또는 한 팀). 실패하거나 템플릿이 없으면 빈 결과.
 * @param {{ as_of?: string, team_key?: string, scope?: 'auto'|'stage'|'genre' }} [overrides]
 *   scope: auto = SQL 기본(장르를 알면 단계+장르), stage = 단계만, genre = 단계+장르만(장르 모르는 팀은 결과 없음)
 * @returns {Promise<{ rows: object[], byTeam: Map<string, object>, error: string }>}
 */
export async function queryPeerCompare(overrides = {}) {
  const empty = { rows: [], byTeam: new Map(), error: '' };
  const tpl = await getSqlTemplate('peer_compare');
  if (!tpl) return { ...empty, error: 'peer_compare.sql 을 불러오지 못했습니다' };
  const params = buildParams({ as_of: overrides.as_of, team_key: overrides.team_key });
  let sql = fillTemplate(tpl, {
    ...params,
    min_peers: String(MIN_PEERS),
    team: params.team_key,
  });
  const scopeLine = SCOPE_LINES[overrides.scope];
  if (scopeLine) {
    if (!sql.includes(CHOSEN_LINE)) return { ...empty, error: 'peer_compare.sql 형식이 바뀌어 비교 기준을 고를 수 없습니다' };
    sql = sql.replace(CHOSEN_LINE, scopeLine);
  }
  appState.lastSql.peer_compare = sql;

  if (peerCache.has(sql)) return peerCache.get(sql);
  try {
    const res = await runRawSql(sql);
    const rows = res.rows.map(normalizeRow);
    const result = { rows, byTeam: new Map(rows.map(r => [r.team_key, r])), error: '' };
    peerCache.set(sql, result);
    if (peerCache.size > CACHE_MAX) peerCache.delete(peerCache.keys().next().value);
    return result;
  } catch (err) {
    return { ...empty, error: String(err?.message || err) };
  }
}
