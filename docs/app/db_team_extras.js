/**
 * 팀 상세 보조 데이터(3-5 사건 별점 · 3-6 공연 블록) 불러오기.
 * 모두 meta.json extras 에 적힌 경우에만 받는다(없으면 빈 결과 → 화면은 그 칸만 '자료 없음').
 *   event_stars.csv   scripts/event_stars.py
 *   lineup_roles.csv  scripts/lineup_roles.py
 *   venue_tiers.csv   scripts/export_venue_tiers.py (없으면 venue_profiles.json 의 tier)
 *   venue_index.json 의 city → 공연장 도시 (scripts/venue_index.py, 없으면 venue_profiles.json 의 city)
 */
import {
  fetchJson, fetchText, fillTemplate, getSqlTemplate, labExtraListed, loadVenueProfiles, parseCsvObjects, runRawSql,
  sqlStringLiteral,
} from './db.js';
import { venueMetaFromIndex } from './venue_tiers.js';
import { toNumOrNull as num } from './util.js';

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const VALID_TIERS = new Set(['S', 'M', 'L', 'XL']);
const memo = new Map(); // 이름 -> Promise

function once(name, fn) {
  if (!memo.has(name)) memo.set(name, fn().catch(() => null));
  return memo.get(name);
}

async function loadCsvIfListed(file) {
  if (!labExtraListed(file.replace(/\.csv$/, ''))) return null;
  const txt = await fetchText(`lab/data/${file}`, true);
  return txt && txt.trim() ? parseCsvObjects(txt) : null;
}

/** team_key -> 사건 행[] (날짜 오름차순). 파일이 없으면 null */
export function loadEventStars() {
  return once('event_stars', async () => {
    const rows = await loadCsvIfListed('event_stars.csv');
    if (!rows) return null;
    const byTeam = new Map();
    for (const r of rows) {
      const date = String(r.date || '').slice(0, 10);
      if (!r.team_key || !DATE_RE.test(date)) continue;
      const ev = {
        date,
        kind: r.kind || '',
        kind_label: r.kind_label || r.kind || '',
        stars: Math.max(1, Math.min(5, num(r.stars) || 1)),
        reason: r.reason || '',
        detail: r.detail || '',
        stage_at: num(r.stage_at),
        gigs_before: num(r.gigs_before_28),
        gigs_after: num(r.gigs_after_28),
        mentions_before: num(r.mentions_before_28),
        mentions_after: num(r.mentions_after_28),
        after_days: num(r.after_window_days),
      };
      if (!byTeam.has(r.team_key)) byTeam.set(r.team_key, []);
      byTeam.get(r.team_key).push(ev);
    }
    return byTeam;
  });
}

/** team_key -> { gigs, solo, head(단독 포함), support, avg_lineup, first_headline_date, support_to_headline }. 없으면 null */
export function loadLineupRoles() {
  return once('lineup_roles', async () => {
    const rows = await loadCsvIfListed('lineup_roles.csv');
    if (!rows) return null;
    const byTeam = new Map();
    for (const r of rows) {
      if (!r.team_key) continue;
      byTeam.set(r.team_key, {
        gigs: num(r.gigs) || 0,
        solo: num(r.solo_gigs) || 0,
        head: num(r.headline_gigs) || 0,
        support: num(r.support_gigs) || 0,
        avg_lineup: num(r.avg_lineup),
        first_headline_date: String(r.first_headline_date || ''),
        support_to_headline: String(r.support_to_headline || '') === '1',
      });
    }
    return byTeam;
  });
}

/** { tiers: Map venue->tier | null, cities: Map venue->city | null } — 각각 자료가 없으면 null */
export function loadVenueMeta() {
  return once('venue_meta', async () => {
    let tiers = null;
    const tierRows = await loadCsvIfListed('venue_tiers.csv');
    if (tierRows) {
      tiers = new Map(tierRows
        .map(r => [String(r.venue || '').trim(), String(r.tier || '').trim().toUpperCase()])
        .filter(([v, t]) => v && VALID_TIERS.has(t)));
    }
    let cities = null;
    // 작은 venue_index.json(약 18KB, 이름 → 도시·크기)이 있으면 그걸로 — 예전엔 도시만 쓰려고 venue_profiles.json(약 600KB)을 받음
    if (labExtraListed('venue_index')) {
      const idx = venueMetaFromIndex(await fetchJson('lab/data/venue_index.json', true));
      if (idx) {
        if (!tiers && idx.tiers.size) tiers = idx.tiers;
        return { tiers, cities: idx.cities.size ? idx.cities : null };
      }
    }
    if (labExtraListed('venue_profiles')) {
      const vp = await loadVenueProfiles();
      const venues = vp?.venues && typeof vp.venues === 'object' ? vp.venues : null;
      if (venues) {
        cities = new Map();
        const fromProfiles = new Map();
        for (const [name, info] of Object.entries(venues)) {
          if (info?.city) cities.set(name, String(info.city));
          const t = String(info?.tier || '').toUpperCase();
          if (VALID_TIERS.has(t)) fromProfiles.set(name, t);
        }
        if (!tiers && fromProfiles.size) tiers = fromProfiles;
      }
    }
    return { tiers, cities };
  });
}

/**
 * 이 팀의 공연(날짜·공연장)마다 같은 무대 출연 팀 수 — 13팀 이상은 페스티벌로 따로 센다.
 * @returns {Promise<Array<{ date: string, venue: string, acts: number }>>}
 */
export async function queryTeamGigActs(teamKey) {
  if (!teamKey) return [];
  const sql = `
    WITH g AS (
      SELECT DISTINCT team_key, CAST(signal_date AS VARCHAR) AS d, TRIM(venue) AS venue FROM signals
      WHERE branch = '공연' AND COALESCE(TRIM(venue), '') NOT IN ('', '공연장 미정')
    )
    SELECT a.d AS date, a.venue, COUNT(DISTINCT b.team_key) AS acts
    FROM g a JOIN g b ON b.d = a.d AND b.venue = a.venue
    WHERE a.team_key = ${sqlStringLiteral(teamKey)}
    GROUP BY a.d, a.venue
    ORDER BY a.d`;
  try {
    const res = await runRawSql(sql);
    return res.rows.map(r => ({ date: String(r.date).slice(0, 10), venue: String(r.venue), acts: Number(r.acts) || 1 }));
  } catch (_) {
    return [];
  }
}

const similarMemo = new Map(); // team|asOf -> Promise<rows>

/**
 * 비슷한 팀 (docs/lab/sql/similar_teams.sql — 같은 무대·같은 출처·같은 장르·비슷한 체급, 정답 정보는 안 씀).
 * @returns {Promise<object[]>} 유사도 높은 순 최대 12팀, 실패하면 []
 */
export function querySimilarTeams(teamKey, asOf) {
  if (!teamKey || !DATE_RE.test(String(asOf || ''))) return Promise.resolve([]);
  const key = `${teamKey}|${asOf}`;
  if (!similarMemo.has(key)) {
    similarMemo.set(key, (async () => {
      const tpl = await getSqlTemplate('similar_teams');
      if (!tpl) return [];
      const res = await runRawSql(fillTemplate(tpl, { team_key: sqlStringLiteral(teamKey), as_of: `DATE '${asOf}'`, sim_limit: '12' }));
      return res.rows;
    })().catch(() => []));
  }
  return similarMemo.get(key);
}
