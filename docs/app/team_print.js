/**
 * 팀 한 장 요약 (브라우저 인쇄 → 'PDF로 저장') — 팀 머리·핵심 숫자 4칸·발굴 단계·최근 사건 5개·공연 5개만 한 장에.
 * 고르기·그리기는 순수 함수 (tests/js/team_print.test.mjs). 인쇄 단추는 views/team.js, 인쇄 모양은 css/print.css.
 */

import { escapeHtml as esc } from './util.js';

const MAX_UPCOMING = 2;
const DEFAULT_N = 5;
const NO_VENUE = '공연장 미정';

/**
 * 공연 n개: 같은 날·같은 공연장은 한 번, 예정 공연(최대 2개, 가까운 순) 먼저, 나머지는 최근 순.
 * @param {Array<{ signal_date: string, branch: string, venue?: string }>} timeline
 * @param {string} asOf YYYY-MM-DD
 */
export function recentGigs(timeline, asOf, n = DEFAULT_N) {
  const seen = new Set();
  const gigs = [];
  for (const r of timeline || []) {
    if (r.branch !== '공연') continue;
    const date = String(r.signal_date || '').slice(0, 10);
    const venue = String(r.venue || '').trim() || NO_VENUE;
    const id = `${date}|${venue}`;
    if (!date || seen.has(id)) continue;
    seen.add(id);
    gigs.push({ date, venue, upcoming: date > asOf });
  }
  const upcoming = gigs.filter(g => g.upcoming).sort((a, b) => a.date.localeCompare(b.date)).slice(0, MAX_UPCOMING);
  const past = gigs.filter(g => !g.upcoming).sort((a, b) => b.date.localeCompare(a.date));
  return [...upcoming, ...past].slice(0, n);
}

/**
 * 최근 사건 n개: 사건 별점(event_stars)이 있으면 기준일까지 최근 순, 없으면 공연을 뺀 신호·정답(team.js mergedTimeline).
 * @param {object[]|null} events event_stars 행
 * @param {object[]} merged team.js mergedTimeline 행 { sortDate, branch, program, isOutcome }
 */
export function recentEvents(events, merged, asOf, n = DEFAULT_N) {
  if (events && events.length) {
    return events.filter(e => e.date <= asOf)
      .sort((a, b) => b.date.localeCompare(a.date))
      .slice(0, n)
      .map(e => ({ date: e.date, label: e.kind_label || e.kind || '', detail: e.detail || '', stars: e.stars || 0 }));
  }
  return (merged || []).filter(m => m.branch !== '공연' && m.sortDate && m.sortDate <= asOf)
    .sort((a, b) => b.sortDate.localeCompare(a.sortDate))
    .slice(0, n)
    .map(m => ({ date: m.sortDate, label: [m.branch, m.program || m.text].filter(Boolean).join(' · '), detail: '', stars: 0 }));
}

/**
 * 인쇄용 한 장. photoHtml·factsHtml·keyStatsHtml 은 앱이 이미 만든(이스케이프된) HTML, 나머지 글자는 여기서 이스케이프.
 */
export function printSheetHtml(m) {
  const events = (m.events || []).map(e => `
      <li><span class="ps-date">${esc(e.date)}</span>
        ${e.stars ? `<span class="ps-stars" aria-label="별 ${esc(e.stars)}개">${'★'.repeat(Math.max(0, Math.min(5, Number(e.stars) || 0)))}</span>` : ''}
        <strong>${esc(e.label)}</strong> ${e.detail ? `<span class="ps-detail">${esc(e.detail)}</span>` : ''}</li>`).join('');
  const gigs = (m.gigs || []).map(g => `
      <li><span class="ps-date">${esc(g.date)}</span> ${esc(g.venue)}${g.upcoming ? ' <span class="ps-tag">예정</span>' : ''}</li>`).join('');
  return `
    <article class="print-sheet" aria-label="${esc(m.name)} 한 장 요약">
      <header class="ps-head">
        ${m.photoHtml || ''}
        <div class="ps-title">
          <h1>${esc(m.name)}</h1>
          ${m.factsHtml || ''}
        </div>
      </header>
      ${m.keyStatsHtml || ''}
      <section class="ps-stage"><h2>발굴 단계</h2>
        <p><strong>${esc(m.stageLabel || '계산 안 됨')}</strong>${m.stageNext ? ` — 다음: ${esc(m.stageNext)}` : ''}</p></section>
      <div class="ps-cols">
        <section><h2>최근 사건</h2>${events ? `<ol class="ps-list">${events}</ol>` : '<p>기록 없음</p>'}</section>
        <section><h2>공연</h2>${gigs ? `<ol class="ps-list">${gigs}</ol>` : '<p>기록 없음</p>'}</section>
      </div>
      <footer class="ps-foot">Gigle Research · 기준 ${esc(m.asOf)} · ${esc(m.url || '')}</footer>
    </article>`;
}
