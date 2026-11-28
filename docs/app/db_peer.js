/**
 * 이웃 비교(docs/lab/sql/peer_compare.sql) 질의 — 색 지도(2-5)와 팀 상세 동료 비교(3-4)가 같이 쓴다.
 * db.js 가 이미 커서, 이 질의만 따로 둔다.
 */
import { appState } from './state.js';
import { toNumOrNull } from './util.js';
import {
  buildParams, fetchText, fillTemplate, getSqlTemplate, labExtraListed, parseCsvObjects, runRawSql, sqlStringLiteral,
} from './db.js';

export const MIN_PEERS = 30; // peer_compare.sql 기본값(이웃이 이보다 적으면 '비교군 작음')
const CACHE_MAX = 6;
const peerCache = new Map(); // sql -> { rows, byTeam }

// peer_compare.sql 의 '팀마다 쓸 층' 줄 — scope 를 고르려면 이 줄만 바꾼다(없으면 기본 = 모든 팀 단계만).
// 2026-11-28: 기본을 '단계'로 — 확인된 장르는 사후 수집 편향이라 장르 이웃 등급이 낮게 나옴 (docs/methods.md)
const CHOSEN_LINE = "WHERE scope = '단계'   -- 기본 비교군";
const SCOPE_LINES = {
  stage: "WHERE scope = '단계'",          // 같은 발굴 단계 전체
  genre: "WHERE scope = '단계+장르'",      // 같은 단계 + 같은 장르(profile·press 장르 팀만, 추정 장르 제외)
  genre_then: "WHERE scope = '단계+장르(그때)'", // 기준일에 알 수 있던 장르만 (genre_seen.known_from < 기준일)
};

const PCT_KEYS = [
  'score_pct', 'branch_pct', 'stage_pct', 'outlets_pct', 'venues_pct',
  'winner_pct', 'context_pct', 'gigs_pct', 'top_share',
];

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

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const INSERT_BATCH = 200;
let genreSeenPromise = null;

/**
 * peer_compare.sql 이 읽는 genre_seen 표(장르 근거 공개일, docs/lab/data/genre_seen.csv)를 한 번 만든다.
 * 파일이 보조 목록(meta.json extras)에 없으면 빈 표 — 그래도 SQL 은 돈다('단계+장르(그때)' 판만 비게 됨).
 */
function ensureGenreSeenTable() {
  if (!genreSeenPromise) {
    genreSeenPromise = (async () => {
      await runRawSql('CREATE TABLE IF NOT EXISTS genre_seen(team_key VARCHAR, genre VARCHAR, confidence VARCHAR, '
        + 'first_seen DATE, first_seen_source VARCHAR, known_from DATE, known_from_source VARCHAR, match VARCHAR)');
      if (!labExtraListed('genre_seen')) return;
      const txt = await fetchText('lab/data/genre_seen.csv', true);
      const rows = parseCsvObjects(txt || '').filter(r => r.team_key && DATE_RE.test(String(r.known_from || '')));
      const dateOrNull = v => (DATE_RE.test(String(v || '')) ? `DATE '${v}'` : 'NULL');
      for (let i = 0; i < rows.length; i += INSERT_BATCH) {
        const values = rows.slice(i, i + INSERT_BATCH).map(r => `(${[
          sqlStringLiteral(r.team_key), sqlStringLiteral(r.genre), sqlStringLiteral(r.confidence),
          dateOrNull(r.first_seen), sqlStringLiteral(r.first_seen_source), dateOrNull(r.known_from),
          sqlStringLiteral(r.known_from_source), sqlStringLiteral(r.match),
        ].join(', ')})`).join(', ');
        await runRawSql(`INSERT INTO genre_seen VALUES ${values}`);
      }
    })().catch((err) => {
      genreSeenPromise = null;   // 다음 호출 때 다시
      throw err;
    });
  }
  return genreSeenPromise;
}

/**
 * 기준일 기준 이웃 비교 전체(또는 한 팀). 실패하거나 템플릿이 없으면 빈 결과.
 * @param {{ as_of?: string, team_key?: string, scope?: 'auto'|'stage'|'genre' }} [overrides]
 *   scope: auto·stage = 같은 발굴 단계 전체(기본), genre = 단계+확인된 장르만(장르 모르는 팀은 결과 없음, 참고용 — 사후 수집 편향)
 * @returns {Promise<{ rows: object[], byTeam: Map<string, object>, error: string }>}
 */
export async function queryPeerCompare(overrides = {}) {
  const empty = { rows: [], byTeam: new Map(), error: '' };
  const tpl = await getSqlTemplate('peer_compare');
  if (!tpl) return { ...empty, error: 'peer_compare.sql 을 불러오지 못했습니다' };
  try {
    await ensureGenreSeenTable();
  } catch (err) {
    return { ...empty, error: String(err?.message || err) };
  }
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
