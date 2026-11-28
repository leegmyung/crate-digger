/**
 * 팀 상세 3-5 '사건 기록' — 날짜 왼쪽 · 별 1~5 · 큰 사건 행엔 전후 28일 공연·언급 수 작은 표.
 * 자료: docs/lab/data/event_stars.csv (scripts/event_stars.py). 파일이 없으면 이 부분은 그리지 않는다.
 */
import { appState } from '../state.js';
import { escapeHtml, fmtInt, INFO_TIPS, infoTip, renderNoRecordLine } from '../ui.js';
import { eventAfterSentence, eventsSummarySentence } from '../insight_text.js';

const FIRST_SHOWN = 6;
const WINDOW_DAYS = 28;
/** 전후 28일 표를 붙이는 사건(선정·큰 공연장 첫 출연·매체 첫 소개 + 정답·처음 서울 공연) */
const WINDOW_KINDS = new Set(['selection', 'big_venue_first', 'magazine', 'outcome', 'first_seoul_gig']);

function starsHtml(n) {
  const full = '★'.repeat(n);
  const empty = '☆'.repeat(5 - n);
  return `<span class="event-stars" role="img" aria-label="별 ${n}개">${full}<span class="event-stars-empty">${empty}</span></span>`;
}

const isNum = v => v !== null && v !== undefined && Number.isFinite(Number(v));

/** 칸 하나: 숫자 + 칸 안 막대(그 줄 큰 값 = 100%, 0부터). 전 = 비교 회색, 후 = 늘었을 때만 주인공 색 (css/graph.css 그림 규칙) */
function cell(v, max, side, up = false) {
  if (!isNum(v)) return '<td>—</td>';
  const w = max > 0 ? Math.round((Number(v) / max) * 100) : 0;
  const cls = `ew-bar is-${side}${up ? ' is-up' : ''}`;
  return `<td><span class="ew-cell"><span class="ew-v">${fmtInt(v)}</span><i class="${cls}" style="--w:${w}%" aria-hidden="true"></i></span></td>`;
}

function windowRow(label, before, after) {
  const max = Math.max(isNum(before) ? Number(before) : 0, isNum(after) ? Number(after) : 0);
  const up = isNum(before) && isNum(after) && Number(after) > Number(before);
  return `<tr><th scope="row">${label}</th>${cell(before, max, 'before')}${cell(after, max, 'after', up)}</tr>`;
}

/** 큰 사건 전후 28일 작은 표 (시험용으로 내보냄) */
export function windowTableHtml(ev) {
  if (!WINDOW_KINDS.has(ev.kind)) return '';
  if (ev.gigs_before === null && ev.mentions_before === null) return '';
  const partial = ev.after_days !== null && ev.after_days !== undefined && ev.after_days < WINDOW_DAYS;
  const afterHead = partial ? `후 ${fmtInt(ev.after_days)}일(진행 중)` : `후 ${WINDOW_DAYS}일`;
  return `
    <table class="event-window" aria-label="사건 전후 ${WINDOW_DAYS}일">
      <thead><tr><th></th><th>전 ${WINDOW_DAYS}일</th><th>${escapeHtml(afterHead)}</th></tr></thead>
      <tbody>
        ${windowRow('공연', ev.gigs_before, ev.gigs_after)}
        ${windowRow('언급', ev.mentions_before, ev.mentions_after)}
      </tbody>
    </table>`;
}

/** 사건 설명 속 프로그램 코드(band_discovery 등)를 programs.csv 이름으로 바꾼다 */
function readableDetail(detail) {
  let out = String(detail || '');
  for (const [code, label] of appState.programLabels || []) {
    if (code && out.includes(code)) out = out.split(code).join(label);
  }
  return out;
}

/** Chartmetric 이벤트 분석기 요약처럼: 큰 사건들 뒤 28일 평균 변화 한 줄 */
function summaryLine(past, asOf) {
  const txt = eventsSummarySentence(past, asOf);
  return txt ? `<p class="event-summary">${escapeHtml(txt)}</p>` : '';
}

function eventRowHtml(ev) {
  return `
    <li class="event-row">
      <span class="event-date">${escapeHtml(ev.date)}</span>
      <div class="event-main">
        <div class="event-line">
          ${starsHtml(ev.stars)}
          <strong class="event-kind">${escapeHtml(ev.kind_label)}</strong>
          <span class="event-detail" title="${escapeHtml(readableDetail(ev.reason))}">${escapeHtml(readableDetail(ev.detail))}</span>
        </div>
        ${eventAfterSentence(ev) ? `<p class="event-after small">${escapeHtml(eventAfterSentence(ev))}</p>` : ''}
        ${windowTableHtml(ev)}
      </div>
    </li>`;
}

/**
 * @param {Array<object>|null} events 이 팀의 사건(없으면 null → 빈 문자열)
 * @param {boolean} showAll
 */
export function renderEventLogHtml(events, asOf, showAll = false) {
  if (!events) return '';
  const past = events.filter(e => e.date <= asOf).sort((a, b) => b.date.localeCompare(a.date));
  if (!past.length) {
    return `<div class="event-log">${renderNoRecordLine('별점을 매길 사건이 아직 없습니다')}</div>`;
  }
  const shown = showAll ? past : past.slice(0, FIRST_SHOWN);
  const more = past.length - shown.length;
  const fives = past.filter(e => e.stars >= 4).length;
  return `
    <div class="event-log">
      <div class="event-log-head">
        <span class="event-log-title">사건 ${fmtInt(past.length)}건${fives ? ` · 별 4개 이상 ${fmtInt(fives)}건` : ''}${infoTip('사건 별점', INFO_TIPS.event_stars, { compact: true })}</span>
      </div>
      ${summaryLine(past, asOf)}
      <ol class="event-list">${shown.map(eventRowHtml).join('')}</ol>
      ${more > 0 ? `<div class="more-row"><span>${fmtInt(shown.length)} / ${fmtInt(past.length)}건</span><button type="button" class="btn btn-sm" data-event-more="1">사건 모두 보기</button></div>` : ''}
    </div>`;
}
