/**
 * 홈 맨 위 '이번 주 볼 신인 5팀' (docs/ux_simplify_2026-11-28.md ①).
 * 후보 점수 순으로 내려가며 최근 14일 안에 신호가 있거나 이번 주 중요한 알림(새 공연·새 정답 제외)이 있는 팀을 고른다.
 * 모자라면 점수 순으로 채운다. 줄 모양은 홈 차트 맛보기와 같다(사진 · 이름 · 한 줄 이유 · ▶ · 점수 · 관심).
 */
import { homeChartRowHtml } from './home_chart_rows.js';
import { fmtNum, plainWhyLine } from './ui.js';
import { isImportantAlert } from './views/today_alerts.js';

const RECENT_DAYS = 14;
export const WEEKLY_PICKS = 5;

function daysBetween(a, b) {
  return (Date.parse(b) - Date.parse(a)) / 86400000;
}

/**
 * @param {Array<{team_key:string, last_seen?:string}>} rows 후보 (점수 순)
 * @param {Array<{type:string, team_key:string}>} alerts
 * @param {string} asOf 기준일 YYYY-MM-DD
 * @param {number} [n]
 * @returns {Array<object>}
 */
export function pickWeeklyTeams(rows, alerts, asOf, n = WEEKLY_PICKS) {
  const alerted = new Set((alerts || []).filter(isImportantAlert).map(a => a.team_key));
  const sorted = [...(rows || [])].sort((x, y) => (Number(y.score) || 0) - (Number(x.score) || 0));
  const isRecent = r => alerted.has(r.team_key)
    || (r.last_seen && daysBetween(String(r.last_seen).slice(0, 10), asOf) <= RECENT_DAYS);
  const picked = sorted.filter(isRecent).slice(0, n);
  const keys = new Set(picked.map(r => r.team_key));
  for (const r of sorted) {
    if (picked.length >= n) break;
    if (!keys.has(r.team_key)) { picked.push(r); keys.add(r.team_key); }
  }
  return picked;
}

/**
 * @param {Array<object>} picks pickWeeklyTeams 결과
 * @returns {string}
 */
export function weeklyPicksHtml(picks) {
  if (!picks?.length) return '';
  const rows = picks.map((r, i) => homeChartRowHtml(i, {
    team_key: r.team_key,
    name: r.display_name || r.team_key,
    genre: plainWhyLine(r),
    metric: Number.isFinite(Number(r.score)) ? `${fmtNum(Number(r.score), 2)}점` : '',
  })).join('');
  return `
    <section class="block ux-weekly-picks" aria-label="이번 주 볼 신인">
      <div class="block-head">
        <h2>이번 주 볼 신인 ${picks.length}팀</h2>
        <a class="small" href="#/discover">발굴에서 더 보기 →</a>
      </div>
      <p class="small muted">후보 점수 순 · 최근 14일 안에 새 신호나 중요한 알림이 있는 팀 먼저</p>
      <ol class="home-chart-list">${rows}</ol>
    </section>`;
}
