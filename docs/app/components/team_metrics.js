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
  return { label: `${capped}개 갈래`, ratio: capped / ALL_BRANCH_COUNT };
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
