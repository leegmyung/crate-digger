/**
 * 내 목록 분석 — 관심 팀 묶음을 한눈에 (Chartmetric 숏리스트의 '목록 전체 분석'처럼).
 * 단계 분포 · 최근 움직임 · 장르 · 다가오는 공연. 순수 함수 (tests/js/watch_summary.test.mjs), 그리기는 views/watchlist.js.
 */

const STAGES = [0, 1, 2, 3, 4];
const TOP_GENRES = 3;

/**
 * @param {{ teams: object[], stageByTeam: Map<string, number>, stageLabels?: Record<number,string>,
 *           upcoming: Array<{ signal_date: string, team_key: string, display_name: string, venue: string }>, maxUpcoming?: number }} p
 */
export function watchSummary({ teams = [], stageByTeam = new Map(), stageLabels = {}, upcoming = [], maxUpcoming = 3 }) {
  const keys = new Set(teams.map(t => t.team_key));
  const stageCounts = new Map();
  let noStage = 0;
  for (const t of teams) {
    const st = stageByTeam.get(t.team_key);
    if (st === undefined || st === null) noStage += 1;
    else stageCounts.set(Number(st), (stageCounts.get(Number(st)) || 0) + 1);
  }
  const genreCounts = new Map();
  for (const t of teams) {
    const g = String(t.primary_genre || '').trim();
    if (g && g !== '미분류') genreCounts.set(g, (genreCounts.get(g) || 0) + 1);
  }
  const seen = new Set();
  const gigs = [];
  for (const g of upcoming) {
    if (!keys.has(g.team_key)) continue;
    const id = `${g.signal_date}|${g.team_key}|${g.venue}`;
    if (seen.has(id)) continue;
    seen.add(id);
    gigs.push({ date: String(g.signal_date).slice(0, 10), team_key: g.team_key, name: g.display_name || g.team_key, venue: g.venue || '' });
  }
  gigs.sort((a, b) => a.date.localeCompare(b.date) || a.name.localeCompare(b.name, 'ko'));
  return {
    total: teams.length,
    stages: STAGES.filter(s => stageCounts.has(s)).map(s => ({ stage: s, label: stageLabels[s] || String(s), n: stageCounts.get(s) })),
    noStage,
    active7d: teams.filter(t => Number(t.recent_7d) > 0).length,
    rankUp: teams.filter(t => Number(t.rank_delta) > 0).length,
    rankDown: teams.filter(t => Number(t.rank_delta) < 0).length,
    newInSnap: teams.filter(t => t.is_new_in_snap).length,
    topGenres: [...genreCounts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], 'ko'))
      .slice(0, TOP_GENRES).map(([genre, n]) => ({ genre, n })),
    upcomingTotal: gigs.length,
    upcomingTeams: new Set(gigs.map(g => g.team_key)).size,
    nextGigs: gigs.slice(0, maxUpcoming),
  };
}

/** 한 줄 요약 (관심 팀이 없으면 '') */
export function watchSummaryLine(s, days) {
  if (!s.total) return '';
  const parts = [`최근 7일 움직인 팀 ${s.active7d}`, `순위 오른 팀 ${s.rankUp}`, `내린 팀 ${s.rankDown}`];
  if (s.newInSnap) parts.push(`새로 300위 안 ${s.newInSnap}`);
  parts.push(s.upcomingTotal ? `앞으로 ${days}일 공연 ${s.upcomingTeams}팀 ${s.upcomingTotal}회` : `앞으로 ${days}일 잡힌 공연 없음`);
  return `관심 ${s.total}팀 — ${parts.join(' · ')}`;
}
