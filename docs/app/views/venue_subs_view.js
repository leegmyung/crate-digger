/**
 * 5-5 구독 공연장 묶음 — 관심 목록(구독 해제 가능)과 이번 주 브리핑(소식만)에 같이 쓴다.
 * 구독한 공연장이 근거에 들어간 alerts.json 알림(큰 공연장 첫 출연 · 새 공연 · 백지 신인 첫 언급 · 같은 무대 수상 팀).
 * 구독한 공연장이 없으면 빈 문자열(묶음 숨김).
 */
import { alertsForSubscribedVenues, listVenueSubs, toggleVenueSub } from '../venue_subs.js';
import { alertRowHtml } from './today_alerts.js';
import { escapeHtml, fmtInt } from '../ui.js';

const PER_VENUE = 4;

/**
 * @param {object|null} alertsData
 * @param {{ editable?: boolean, title?: string }} [opts]
 */
export function renderVenueSubsHtml(alertsData, opts = {}) {
  const subs = listVenueSubs();
  if (!subs.length) return '';
  const byVenue = alertsForSubscribedVenues(alertsData, subs);
  const total = [...byVenue.values()].reduce((n, list) => n + list.length, 0);
  const rows = subs.map(v => {
    const list = (byVenue.get(v) || []).slice().sort((a, b) => (Number(b.importance) || 0) - (Number(a.importance) || 0));
    const shown = list.slice(0, PER_VENUE);
    return `
      <li class="venue-sub-item">
        <div class="venue-sub-head">
          <a class="inline-venue-link" href="#/venue/${encodeURIComponent(v)}"><strong>${escapeHtml(v)}</strong></a>
          <span class="small muted">${list.length ? `소식 ${fmtInt(list.length)}건` : '이번 주 소식 없음'}</span>
          ${opts.editable ? `<button type="button" class="btn btn-sm" data-venue-unsub="${escapeHtml(v)}" aria-label="${escapeHtml(v)} 구독 해제">구독 해제</button>` : ''}
        </div>
        ${shown.length ? `<ul class="today-alerts-list">${shown.map(a => alertRowHtml({ a, stars: null })).join('')}</ul>` : ''}
        ${list.length > shown.length ? `<p class="small muted" style="margin:2px 0 0;">외 ${fmtInt(list.length - shown.length)}건</p>` : ''}
      </li>`;
  }).join('');
  return `
    <section class="block venue-subs-block" id="venueSubsBlock" aria-label="구독 공연장">
      <div class="block-head">
        <h2>${escapeHtml(opts.title || '구독 공연장')}</h2>
        <span class="block-meta">${fmtInt(subs.length)}곳 · 소식 ${fmtInt(total)}건</span>
      </div>
      <ul class="venue-sub-list">${rows}</ul>
    </section>`;
}

/** 관심 목록의 '구독 해제' 버튼 연결. onChange 는 다시 그리기 */
export function wireVenueSubs(root, onChange) {
  root.querySelector('#venueSubsBlock')?.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-venue-unsub]');
    if (!btn) return;
    toggleVenueSub(btn.dataset.venueUnsub);
    onChange();
  });
}
