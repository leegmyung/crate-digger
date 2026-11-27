/**
 * 팀 상세 3-5 '사건 기록' — 날짜 왼쪽 · 별 1~5 · 큰 사건 행엔 전후 28일 공연·언급 수 작은 표.
 * 자료: docs/lab/data/event_stars.csv (scripts/event_stars.py). 파일이 없으면 이 부분은 그리지 않는다.
 */
import { appState } from '../state.js';
import { escapeHtml, fmtInt, INFO_TIPS, infoTip, renderNoRecordLine } from '../ui.js';

const FIRST_SHOWN = 6;
const WINDOW_DAYS = 28;
/** 전후 28일 표를 붙이는 사건(선정·큰 공연장 첫 출연·매체 첫 소개 + 정답·처음 서울 공연) */
const WINDOW_KINDS = new Set(['selection', 'big_venue_first', 'magazine', 'outcome', 'first_seoul_gig']);

function starsHtml(n) {
  const full = '★'.repeat(n);
  const empty = '☆'.repeat(5 - n);
  return `<span class="event-stars" role="img" aria-label="별 ${n}개">${full}<span class="event-stars-empty">${empty}</span></span>`;
}

function cell(v) {
  return v === null || v === undefined ? '—' : fmtInt(v);
}

function windowTableHtml(ev) {
  if (!WINDOW_KINDS.has(ev.kind)) return '';
  if (ev.gigs_before === null && ev.mentions_before === null) return '';
  const partial = ev.after_days !== null && ev.after_days < WINDOW_DAYS;
  const afterHead = partial ? `후 ${fmtInt(ev.after_days)}일(진행 중)` : `후 ${WINDOW_DAYS}일`;
  return `
    <table class="event-window" aria-label="사건 전후 ${WINDOW_DAYS}일">
      <thead><tr><th></th><th>전 ${WINDOW_DAYS}일</th><th>${escapeHtml(afterHead)}</th></tr></thead>
      <tbody>
        <tr><th scope="row">공연</th><td>${cell(ev.gigs_before)}</td><td>${cell(ev.gigs_after)}</td></tr>
        <tr><th scope="row">언급</th><td>${cell(ev.mentions_before)}</td><td>${cell(ev.mentions_after)}</td></tr>
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
      <ol class="event-list">${shown.map(eventRowHtml).join('')}</ol>
      ${more > 0 ? `<div class="more-row"><span>${fmtInt(shown.length)} / ${fmtInt(past.length)}건</span><button type="button" class="btn btn-sm" data-event-more="1">사건 모두 보기</button></div>` : ''}
    </div>`;
}
