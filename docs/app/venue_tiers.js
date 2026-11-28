// 공연장 크기 표(venue_tiers.csv, 약 2KB) — 순수 함수, tests/js/render_guard.test.mjs
// 예전엔 venue_profiles.json(약 600KB)을 통째로 받아 크기만 뽑았다. 같은 값이 venue_tiers.csv 에 있다
// (scripts/export_venue_tiers.py — 파이썬 lab_sql.connect 의 venue_tiers 표와 같은 출처).

const VALID = new Set(['S', 'M', 'L', 'XL']);

/** CSV 행 [{venue, tier}] → Map(공연장 → S|M|L|XL) */
export function parseVenueTierRows(rows) {
  const out = new Map();
  for (const r of rows || []) {
    const venue = String(r?.venue || '').trim();
    const tier = String(r?.tier || '').trim().toUpperCase();
    if (venue && VALID.has(tier)) out.set(venue, tier);
  }
  return out;
}

const quote = s => `'${String(s).replace(/'/g, "''")}'`;

/** Map → INSERT INTO venue_tiers VALUES 뒤에 붙일 값 줄 */
export function venueTierValuesSql(map) {
  return [...map.entries()].map(([v, t]) => `(${quote(v)}, ${quote(t)})`).join(', ');
}

/**
 * venue_index.json(약 18KB, scripts/venue_index.py) → 팀 '공연' 탭이 쓰는 { tiers, cities } (예전엔 venue_profiles.json 600KB 에서 뽑음).
 * @returns {{ tiers: Map<string,string>, cities: Map<string,string> } | null}
 */
export function venueMetaFromIndex(json) {
  const venues = json && typeof json === 'object' ? json.venues : null;
  if (!venues || typeof venues !== 'object' || Array.isArray(venues)) return null;
  const tiers = new Map();
  const cities = new Map();
  for (const [name, info] of Object.entries(venues)) {
    const tier = String(info?.tier || '').trim().toUpperCase();
    const city = String(info?.city || '').trim();
    if (VALID.has(tier)) tiers.set(name, tier);
    if (city) cities.set(name, city);
  }
  return { tiers, cities };
}
