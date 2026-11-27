/**
 * 이웃 비교(docs/lab/sql/peer_compare.sql) 질의 — 색 지도(2-5)와 팀 상세 동료 비교(3-4)가 같이 쓴다.
 * db.js 가 이미 커서, 이 질의만 따로 둔다.
 */
import { appState } from './state.js';
import { buildParams, fillTemplate, getSqlTemplate, runRawSql } from './db.js';

const MIN_PEERS = 30; // peer_compare.sql 기본값(이웃이 이보다 적으면 '비교군 작음')
const CACHE_MAX = 6;
const peerCache = new Map(); // sql -> { rows, byTeam }

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
 * @param {{ as_of?: string, team_key?: string }} [overrides]
 * @returns {Promise<{ rows: object[], byTeam: Map<string, object>, error: string }>}
 */
export async function queryPeerCompare(overrides = {}) {
  const empty = { rows: [], byTeam: new Map(), error: '' };
  const tpl = await getSqlTemplate('peer_compare');
  if (!tpl) return { ...empty, error: 'peer_compare.sql 을 불러오지 못했습니다' };
  const params = buildParams({ as_of: overrides.as_of, team_key: overrides.team_key });
  const sql = fillTemplate(tpl, {
    ...params,
    min_peers: String(MIN_PEERS),
    team: params.team_key,
  });
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
