/**
 * 단계 4 공연장·도시 데이터 — 도시 프로필 · 페스티벌 프로필 · 체급 사다리 불러오기 + 공연장 출연 팀 / 도시 첫 무대 질의.
 * JSON 은 meta.json extras 에 적힌 경우에만 받는다(없으면 null → 화면은 '자료 없음').
 */
import {
  fetchJson, labExtraListed, runRawSql, sqlStringLiteral,
} from './db.js';

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const memo = new Map();

function onceJson(name) {
  if (!memo.has(name)) {
    memo.set(name, (async () => {
      if (!labExtraListed(name)) return null;
      const raw = await fetchJson(`lab/data/${name}.json`, true);
      return raw && typeof raw === 'object' ? raw : null;
    })().catch(() => null));
  }
  return memo.get(name);
}

/** city_profiles.json — { as_of, notes, seoul_flow, cities } | null */
export const loadCityProfiles = () => onceJson('city_profiles');
/** festival_profiles.json — { as_of, notes, festivals, flows } | null */
export const loadFestivalProfiles = () => onceJson('festival_profiles');
/** venue_ladder.json — { as_of, teams, venues } | null (venues[name].teams = 처음 선 팀 수) */
export const loadVenueLadder = () => onceJson('venue_ladder');

const GRADE_RANK_SQL = "MAX(CASE grade WHEN 'S' THEN 3 WHEN 'A' THEN 2 WHEN 'B' THEN 1 ELSE 0 END)";
const GRADE_BY_RANK = { 3: 'S', 2: 'A', 1: 'B' };

/**
 * 4-2 이 공연장에 선 팀: 첫 출연일 · 마지막 · 공연 수(서로 다른 날) · 예정 · 정답(등급·첫 발표일).
 * @returns {Promise<object[]>}
 */
export async function queryVenueTeams(venue, asOf) {
  const v = String(venue || '').trim();
  if (!v || !DATE_RE.test(String(asOf || ''))) return [];
  const sql = `
    WITH g AS (
      SELECT DISTINCT team_key, CAST(signal_date AS VARCHAR) AS d FROM signals
      WHERE branch = '공연' AND TRIM(COALESCE(venue, '')) = ${sqlStringLiteral(v)} AND signal_date IS NOT NULL
    ),
    o AS (
      SELECT team_key, CAST(MIN(announced_date) AS VARCHAR) AS first_outcome, ${GRADE_RANK_SQL} AS best_grade
      FROM outcomes WHERE counted GROUP BY team_key
    )
    SELECT g.team_key, COALESCE(t.display_name, g.team_key) AS display_name, COALESCE(t.primary_genre, '') AS primary_genre,
           MIN(CASE WHEN g.d <= '${asOf}' THEN g.d END) AS first_here,
           MAX(CASE WHEN g.d <= '${asOf}' THEN g.d END) AS last_here,
           COUNT(DISTINCT CASE WHEN g.d <= '${asOf}' THEN g.d END) AS gigs,
           COUNT(DISTINCT CASE WHEN g.d > '${asOf}' THEN g.d END) AS upcoming,
           ANY_VALUE(o.first_outcome) AS first_outcome, ANY_VALUE(o.best_grade) AS best_grade
    FROM g LEFT JOIN teams t USING (team_key) LEFT JOIN o USING (team_key)
    GROUP BY g.team_key, t.display_name, t.primary_genre`;
  try {
    const res = await runRawSql(sql);
    return res.rows.map(r => ({
      team_key: r.team_key,
      display_name: r.display_name,
      primary_genre: r.primary_genre,
      first_here: r.first_here || '',
      last_here: r.last_here || '',
      gigs: Number(r.gigs) || 0,
      upcoming: Number(r.upcoming) || 0,
      first_outcome: r.first_outcome || '',
      grade: GRADE_BY_RANK[Number(r.best_grade)] || '',
    }));
  } catch (_) {
    return [];
  }
}

/**
 * 4-5 도시 첫 무대: 우리 데이터에서 도시를 아는 첫 공연이 이 도시였고, 그 날짜가 기준일 전 days 일 안인 팀.
 * @param {Map<string,string>} venueCity 공연장 → 도시 (venue_profiles.json)
 */
export async function queryCityFirstStageTeams(city, venueCity, asOf, days = 90) {
  if (!city || !venueCity || !venueCity.size || !DATE_RE.test(String(asOf || ''))) return [];
  const values = [...venueCity.entries()].map(([v, c]) => `(${sqlStringLiteral(v)}, ${sqlStringLiteral(c)})`).join(', ');
  const sql = `
    WITH vc(venue, city) AS (VALUES ${values}),
    g AS (
      SELECT s.team_key, CAST(s.signal_date AS VARCHAR) AS d, TRIM(s.venue) AS venue, vc.city
      FROM signals s JOIN vc ON vc.venue = TRIM(s.venue)
      WHERE s.branch = '공연' AND s.signal_date <= DATE '${asOf}'
    ),
    f AS (
      SELECT team_key, MIN(d) AS first_date, arg_min(city, d) AS first_city, arg_min(venue, d) AS first_venue
      FROM g GROUP BY team_key
    )
    SELECT f.team_key, COALESCE(t.display_name, f.team_key) AS display_name, COALESCE(t.primary_genre, '') AS primary_genre,
           f.first_date, f.first_venue
    FROM f LEFT JOIN teams t USING (team_key)
    WHERE f.first_city = ${sqlStringLiteral(city)} AND f.first_date > CAST(DATE '${asOf}' - INTERVAL ${Number(days) || 90} DAY AS VARCHAR)
    ORDER BY f.first_date DESC, display_name`;
  try {
    const res = await runRawSql(sql);
    return res.rows.map(r => ({ ...r, first_date: String(r.first_date).slice(0, 10) }));
  } catch (_) {
    return [];
  }
}
