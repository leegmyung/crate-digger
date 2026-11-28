/**
 * 팀 상세 3-2(4칸 상태 막대)·3-3(변화 줄) 계산 — 다른 모듈을 부르지 않는 순수 함수.
 * 날짜는 모두 'YYYY-MM-DD' 글자, 기간 창은 (시작 전날, 끝날] = 끝날 포함 N일.
 */

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const DAY_MS = 86400000;
const ALL_BRANCH_COUNT = 4; // 발매 · 공연 · 선정·지원 · 큐레이션

/** 활동 막대 눈금: 6개월 신호 이만큼이면 막대가 가득 참 */
const ACTIVITY_FULL = 20;
/** 씬 연결 막대 눈금: 같은 무대 수상 팀 이만큼이면 가득 참 */
const SCENE_FULL = 10;

export function isoMinusDays(iso, days) {
  if (!DATE_RE.test(String(iso || ''))) return null;
  const ms = Date.parse(`${iso}T00:00:00Z`) - days * DAY_MS;
  return new Date(ms).toISOString().slice(0, 10);
}

function countWindow(rows, fromExcl, toIncl) {
  const inWin = rows.filter(r => r.d > fromExcl && r.d <= toIncl);
  const gigKeys = new Set(inWin.filter(r => r.branch === '공연').map(r => `${r.d}|${r.venue}`));
  return { signals: inWin.length, gigs: gigKeys.size };
}

/**
 * 기준일 끝 N일 창과 그 직전 N일 창의 신호 수·공연 수(같은 날 같은 곳은 1회). 제외 신호는 안 센다.
 * @param {Array<{signal_date?: string, branch?: string, venue?: string, role?: string}>} timeline
 * @returns {{ cur: {signals:number,gigs:number}, prev: {signals:number,gigs:number},
 *             from: string, to: string, prevFrom: string, prevTo: string } | null}
 */
export function windowCounts(timeline, asOf, days) {
  const curStart = isoMinusDays(asOf, days);
  if (!curStart) return null;
  const prevStart = isoMinusDays(asOf, days * 2);
  const rows = (timeline || [])
    .filter(s => s && s.role !== 'excluded')
    .map(s => ({ d: String(s.signal_date || '').slice(0, 10), branch: s.branch || '', venue: String(s.venue || '').trim() }))
    .filter(r => DATE_RE.test(r.d));
  return {
    cur: countWindow(rows, curStart, asOf),
    prev: countWindow(rows, prevStart, curStart),
    from: isoMinusDays(asOf, days - 1),
    to: asOf,
    prevFrom: isoMinusDays(asOf, days * 2 - 1),
    prevTo: curStart,
  };
}

function logRatio(n, full) {
  return Math.min(1, Math.log1p(n) / Math.log1p(full));
}

function validCount(n) {
  if (n === null || n === undefined || n === '') return null;
  const v = Number(n);
  return Number.isFinite(v) && v >= 0 ? v : null;
}

/** 최근 6개월 신호 수 → 상태 이름·막대 위치(로그 눈금) */
export function activityState(n180) {
  const n = validCount(n180);
  if (n === null) return null;
  const label = n === 0 ? '조용함' : n <= 2 ? '가끔' : n <= 9 ? '꾸준함' : '활발';
  return { label, ratio: logRatio(n, ACTIVITY_FULL) };
}

/** 신호 갈래 수(4개 중) */
export function branchState(nBranch) {
  const n = validCount(nBranch);
  if (n === null) return null;
  const capped = Math.min(n, ALL_BRANCH_COUNT);
  return { label: `${capped}종류`, ratio: capped / ALL_BRANCH_COUNT };
}

/** 같은 무대에 선 수상 팀 수 → 상태 이름·막대 위치(로그 눈금) */
export function sceneState(nWinners) {
  const n = validCount(nWinners);
  if (n === null) return null;
  return { label: n === 0 ? '아직 없음' : `${n}팀`, ratio: logRatio(n, SCENE_FULL) };
}

/** 발굴 단계 0~4 → 막대 위치 */
export function stageRatio(stage) {
  const n = validCount(stage);
  return n === null ? null : Math.min(n, 4) / 4;
}

// ---------- 3-4 동료 비교 · 3-6 공연 블록 ----------

const FESTIVAL_MIN_ACTS = 13; // 같은 날 같은 곳 13팀 이상 = 페스티벌(따로 셈, lineup_roles 와 같은 기준)
const TOP_VENUES = 3;
const YEAR_DAYS = 365;

/** peer_compare.sql 등급 → 화면 낱말 */
const GRADE_WORDS = { 탁월: '탁월', 훌륭: '좋음', 평균: '보통', '평균 이하': '아래', '비교군 작음': '비교할 팀이 적음' };
export function peerGradeWord(grade) {
  return GRADE_WORDS[String(grade || '')] || '';
}

/** top_share(0~1, 작을수록 위) → '상위 x%'의 x (최소 1) */
export function topSharePct(topShare) {
  const v = validCount(topShare);
  return v === null ? null : Math.max(1, Math.round(v * 100));
}

function countBy(items, keyFn) {
  const m = new Map();
  for (const it of items) {
    const k = keyFn(it);
    m.set(k, (m.get(k) || 0) + 1);
  }
  return m;
}

/**
 * 공연 블록 요약. tiers/cities 가 null 이면 그 칸은 null(= 자료 없음).
 * @param {{ gigActs: Array<{date:string, venue:string, acts:number}>, asOf: string,
 *           tiers?: Map<string,string>|null, cities?: Map<string,string>|null }} p
 */
export function gigSummary({ gigActs, asOf, tiers = null, cities = null }) {
  const yearStart = isoMinusDays(asOf, YEAR_DAYS);
  if (!yearStart) return null;
  const rows = (gigActs || []).filter(g => g && DATE_RE.test(String(g.date || '')));
  const past = rows.filter(g => g.date <= asOf);
  const last12 = past.filter(g => g.date > yearStart);
  const regular12 = last12.filter(g => (Number(g.acts) || 1) < FESTIVAL_MIN_ACTS);

  let tierCounts = null;
  if (tiers) {
    tierCounts = { S: 0, M: 0, L: 0, XL: 0, unknown: 0 };
    for (const g of regular12) {
      const t = tiers.get(g.venue);
      if (t && t in tierCounts) tierCounts[t] += 1;
      else tierCounts.unknown += 1;
    }
  }

  let cityCounts = null;
  let cityUnknown = 0;
  if (cities) {
    const known = regular12.filter(g => cities.has(g.venue));
    cityUnknown = regular12.length - known.length;
    cityCounts = [...countBy(known, g => cities.get(g.venue)).entries()]
      .map(([city, n]) => ({ city, n }))
      .sort((a, b) => b.n - a.n || a.city.localeCompare(b.city));
  }

  const topVenues = [...countBy(past, g => g.venue).entries()]
    .map(([venue, n]) => ({ venue, n }))
    .sort((a, b) => b.n - a.n || a.venue.localeCompare(b.venue))
    .slice(0, TOP_VENUES);

  return {
    total12: regular12.length,
    festivals12: last12.length - regular12.length,
    tierCounts,
    cityCounts,
    cityUnknown,
    topVenues,
    upcoming: rows.filter(g => g.date > asOf),
  };
}

/** lineup_roles.csv 한 줄 → 단독·헤드라이너(여러 팀)·서포트·역할 모름 (headline 은 단독 포함이라 뺌) */
export function lineupSplit(lr) {
  if (!lr || !(Number(lr.gigs) > 0)) return null;
  const solo = Number(lr.solo) || 0;
  const head = Number(lr.head) || 0;
  const support = Number(lr.support) || 0;
  const total = Number(lr.gigs);
  return {
    solo,
    headline: Math.max(0, head - solo),
    support,
    unknown: Math.max(0, total - head - support),
    total,
  };
}
