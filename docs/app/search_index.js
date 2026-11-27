/**
 * 전역 검색 색인 — 팀·공연장·도시·페스티벌 (정보 구조 v2 묶음 B, docs/app_structure_v2.md 2-2).
 * 위쪽 검색 드롭다운(components/global_search.js)과 검색 결과 화면(views/search.js)이 같이 쓴다.
 * 공연장 별칭·이름 맞추기 규칙은 6-4 전역 검색에서 옮겨 온 것(동작 같음).
 */
import { appState } from './state.js';
import { loadVenueProfiles, queryDiscoveryStages, queryTeamLastSeenMap } from './db.js';
import { loadCityProfiles, loadFestivalProfiles } from './db_venue.js';

/** 주요 공연장 한글·영문 별칭 (venue_profiles.json aliases 필드가 없을 때도 양방향 매칭) */
const VENUE_ALIAS_PAIRS = [
  ['club ff', ['클럽 에프에프', '클럽에프에프', '에프에프', 'ff']],
  ['club bbang', ['클럽 빵', '클럽빵', '빵']],
  ['club victim', ['클럽 빅팀', '클럽빅팀', '빅팀']],
  ['club sharp', ['클럽 샤프', '클럽샤프', '샤프']],
  ['strange fruit', ['스트레인지 프룻', '스트레인지프룻', '스푸']],
  ['롤링홀', ['rolling hall', 'rollinghall']],
  ['상상마당', ['sangsangmadang', 'kt&g 상상마당', 'ktg']],
  ['웨스트브릿지', ['west bridge', 'westbridge']],
  ['벨로주', ['veloso', '벨로주 홍대', '벨로주 망원']],
  ['제비다방', ['jebidabang', '취한제비']],
  ['베이비돌', ['baby doll', 'babydoll']],
  ['채널1969', ['channel 1969', 'channel1969', '채널 1969']],
  ['언플러그드', ['unplugged', '카페 언플러그드', 'cafe unplugged']],
  ['프리버드', ['freebird', 'free bird']],
  ['네스트나다', ['nest nada', 'nestnada']],
  ['무신사 개러지', ['musinsa garage', 'musinsagarage', '개러지']],
  ['cj아지트', ['cj azit', 'cjazit', '광흥창']],
  ['a.o.r', ['aor', '에이오알']],
  ['bender', ['벤더', '클럽 벤더']],
  ['노들섬', ['nodeul', 'nodeul island']],
  ['스페이스 브릭', ['space brick', 'spacebrick']],
  ['예스24', ['yes24', '예스24 라이브홀', '예스24 원더로크홀']],
  ['언더스테이지', ['understage', '현대카드 언더스테이지']],
  ['살롱 문보우', ['salon moonbow', 'moonbow']],
  ['생기스튜디오', ['senggi', 'senggi studio']],
  ['오방가르드', ['ovantgarde', '부산 오방가르드']],
  ['얼라이브홀', ['alive hall', 'alivehall']],
  ['프리즘홀', ['prism hall', 'prismhall']],
  ['퍼플홀', ['purple hall', 'purplehall']],
  ['스틸페이스', ['steel face', 'steelface']],
  ['구름아래소극장', ['gureum', '구름아래']],
  ['고창석', []],
  ['인디팍', ['indiepark']],
  ['클럽 온에어', ['club on air', 'onair']],
  ['몽향라이브홀', ['monghyang']],
];

export const TIER_KO = { S: '소형', M: '중형', L: '대형', XL: '초대형' };

export function norm(s) {
  return String(s || '').toLowerCase().replace(/[\s._\-·()[\]]+/g, '');
}

function extraVenueAliases(name) {
  const low = String(name || '').toLowerCase();
  const out = [];
  for (const [needle, aliases] of VENUE_ALIAS_PAIRS) {
    if (low.includes(needle)) {
      out.push(...aliases);
    } else if (aliases.some(a => {
      const al = a.toLowerCase();
      return al.length >= 3 ? low.includes(al) : low === al;
    })) {
      out.push(needle, ...aliases);
    }
  }
  return out;
}


/** 이름 하나가 검색어와 얼마나 맞나: 0 앞부분 일치 · 1 포함 · 2 공백·기호 빼고 포함 · -1 아님 */
function matchPrio(names, qLow, qNorm) {
  let best = -1;
  for (const raw of names) {
    const low = String(raw || '').toLowerCase();
    if (!low) continue;
    let p = -1;
    if (low.startsWith(qLow)) p = 0;
    else if (low.includes(qLow)) p = 1;
    else if (qNorm && norm(raw).includes(qNorm)) p = 2;
    if (p >= 0 && (best < 0 || p < best)) best = p;
  }
  return best;
}

let indexPromise = null;
let indexAsOf = '';

/**
 * 팀 말고 나머지 색인(공연장·도시·페스티벌)과 팀 보조 정보(발굴 단계·마지막 신호일)를 한 번만 만든다.
 * @returns {Promise<{venues: object[], cities: object[], festivals: object[], stageByTeam: Map, lastSeenByTeam: Map}>}
 */
export function loadSearchIndex() {
  const asOf = appState.cfg.as_of || appState.dataEnd || '';
  if (indexPromise && indexAsOf === asOf) return indexPromise;
  indexAsOf = asOf;
  indexPromise = Promise.all([
    loadVenueProfiles().catch(() => null),
    loadCityProfiles().catch(() => null),
    loadFestivalProfiles().catch(() => null),
    queryDiscoveryStages({ as_of: asOf }).catch(() => null),
    queryTeamLastSeenMap().catch(() => null),
  ]).then(([vp, cp, fp, stData, lsMap]) => ({
    venues: buildVenueIndex(vp),
    cities: buildCityIndex(cp),
    festivals: buildFestivalIndex(fp),
    stageByTeam: stData?.byTeam || new Map(),
    lastSeenByTeam: lsMap || new Map(),
  }));
  return indexPromise;
}

function buildVenueIndex(vp) {
  if (!vp || !vp.venues) return [];
  const list = Object.entries(vp.venues).map(([name, info]) => {
    const rawAliases = [
      ...(Array.isArray(info.aliases) ? info.aliases : []),
      ...extraVenueAliases(name),
    ];
    return {
      name,
      lowName: name.toLowerCase(),
      normName: norm(name),
      searchKeys: [name, ...rawAliases].map(norm).filter(Boolean),
      city: String(info.city || ''),
      tier: String(info.tier || ''),
      discovery: Number(info.discovery) || 0,
      nights: Number(info.nights) || 0,
      last_night: String(info.last_night || '').slice(0, 10),
    };
  });
  list.sort((a, b) => (b.discovery - a.discovery) || (b.nights - a.nights));
  list.forEach((v, i) => { v.rank = i + 1; });
  return list;
}

function buildCityIndex(cp) {
  if (!cp || !cp.cities) return [];
  return Object.entries(cp.cities).map(([name, c]) => ({
    name,
    venues: Number(c.venues_with_gigs) || 0,
    nights: Number(c.nights) || 0,
    upcoming: Number(c.upcoming_nights) || 0,
    firstStage1y: Number(c.first_stage_teams_1y) || 0,
    laterWinners: Number(c.later_winners_total) || 0,
  })).sort((a, b) => b.nights - a.nights);
}

function buildFestivalIndex(fp) {
  if (!fp || !fp.festivals) return [];
  return Object.entries(fp.festivals).map(([key, f]) => {
    const years = Object.keys(f.editions || {}).sort();
    return {
      key,
      label: String(f.label || key),
      kind: String(f.kind || ''),
      years,
      teams: Number(f.teams_total) || 0,
    };
  }).sort((a, b) => b.teams - a.teams);
}

/** 팀 찾기 — 앞부분 일치 > 포함 > 공백 무시 포함, 같으면 점수 순위·최근 신호 순. */
export function searchTeams(q, idx, limit = 7) {
  const qLow = String(q || '').trim().toLowerCase();
  const qNorm = norm(q);
  if (!qLow || !appState.teamIndex?.length) return { total: 0, items: [] };
  const latestSnap = appState.snapshots?.latest || new Map();
  const matches = [];
  for (const t of appState.teamIndex) {
    const prio = matchPrio([t.display_name, t.team_key], qLow, qNorm);
    if (prio < 0) continue;
    const snap = latestSnap.get(t.team_key);
    matches.push({
      t,
      prio,
      rank: snap?.rank ? Number(snap.rank) : null,
      st: idx?.stageByTeam?.get(t.team_key) || null,
      lastSeen: idx?.lastSeenByTeam?.get(t.team_key) || '',
    });
  }
  matches.sort((a, b) => (
    (a.prio - b.prio)
    || ((a.rank ?? 99999) - (b.rank ?? 99999))
    || (b.lastSeen.localeCompare(a.lastSeen))
  ));
  return { total: matches.length, items: matches.slice(0, limit) };
}

/** 공연장 찾기 — 한글·영문 별칭 포함, 같으면 발굴 주목도 순. */
export function searchVenues(q, idx, limit = 5) {
  const qLow = String(q || '').trim().toLowerCase();
  const qNorm = norm(q);
  const list = idx?.venues || [];
  if (!qLow || !list.length) return { total: 0, items: [] };
  const matches = [];
  for (const v of list) {
    let prio = -1;
    if (v.lowName.startsWith(qLow)) prio = 0;
    else if (v.lowName.includes(qLow)) prio = 1;
    else if (qNorm && v.searchKeys.some(k => k.startsWith(qNorm))) prio = 1;
    else if (qNorm && v.searchKeys.some(k => k.includes(qNorm))) prio = 2;
    if (prio < 0) continue;
    matches.push({ v, prio });
  }
  matches.sort((a, b) => (a.prio - b.prio) || (a.v.rank - b.v.rank));
  return { total: matches.length, items: matches.slice(0, limit) };
}

export function searchCities(q, idx, limit = 3) {
  const qLow = String(q || '').trim().toLowerCase();
  const list = idx?.cities || [];
  if (!qLow || !list.length) return { total: 0, items: [] };
  const hits = list.map(c => ({ c, prio: matchPrio([c.name], qLow, norm(q)) })).filter(x => x.prio >= 0);
  hits.sort((a, b) => (a.prio - b.prio) || (b.c.nights - a.c.nights));
  return { total: hits.length, items: hits.slice(0, limit) };
}

export function searchFestivals(q, idx, limit = 3) {
  const qLow = String(q || '').trim().toLowerCase();
  const list = idx?.festivals || [];
  if (!qLow || !list.length) return { total: 0, items: [] };
  const hits = list.map(f => ({ f, prio: matchPrio([f.label, f.key], qLow, norm(q)) })).filter(x => x.prio >= 0);
  hits.sort((a, b) => (a.prio - b.prio) || (b.f.teams - a.f.teams));
  return { total: hits.length, items: hits.slice(0, limit) };
}

/** 네 종류를 한꺼번에. limits 예: { teams: 7, venues: 5, cities: 3, festivals: 3 } */
export function searchAll(q, idx, limits = {}) {
  return {
    teams: searchTeams(q, idx, limits.teams ?? 7),
    venues: searchVenues(q, idx, limits.venues ?? 5),
    cities: searchCities(q, idx, limits.cities ?? 3),
    festivals: searchFestivals(q, idx, limits.festivals ?? 3),
  };
}

/** 결과 하나 → 갈 주소 */
export function cityHash(name) {
  return `#/city/${encodeURIComponent(name)}`;
}
export function festivalHash(key) {
  return `#/festival/${encodeURIComponent(key)}`;
}
export function searchPageHash(q) {
  return `#/search?q=${encodeURIComponent(String(q || '').trim())}`;
}
