/**
 * 팀 상세 3-1 '머리 띠' 사실 줄 + '비교' 버튼 + 위쪽 고정 '쪽 안 목차'(누르면 이동, 스크롤하면 현재 칸 표시).
 * team.js 가 이미 커서 따로 둔다.
 */
import {
  escapeHtml, fmtInt, genreConfidenceBadgeHtml, naCell, stageBadgeHtml,
} from '../ui.js';

let tocObserver = null; // 다시 그릴 때 이전 관찰을 끊는다

/**
 * 머리 띠 사실 줄: 발굴 단계 · 순위(지난주 ▲▼) · 지역 · 첫 발매 연도 · 장르(추정 꼬리표)
 * @param {{ teamKey: string, stageInfo: object|null, rc: object|null, homeCity: string,
 *           hasCityData: boolean, firstRelease: string, genre: string }} f
 */
export function renderTeamFactsHtml(f) {
  const items = [];
  if (f.stageInfo) items.push(`<span class="team-fact">${stageBadgeHtml(f.stageInfo.stage)}</span>`);

  if (f.rc && f.rc.rank !== null && f.rc.rank !== undefined) {
    const ch = f.rc.week_change;
    const delta = ch > 0 ? `<span class="rank-delta is-up">▲${fmtInt(ch)}</span>`
      : ch < 0 ? `<span class="rank-delta is-down">▼${fmtInt(-ch)}</span>` : '';
    items.push(`<span class="team-fact"><span class="team-fact-lbl">순위</span><strong>#${fmtInt(f.rc.rank)}</strong>${delta}</span>`);
  } else {
    items.push(`<span class="team-fact"><span class="team-fact-lbl">순위</span>${naCell('상위 300 스냅샷에 들지 않은 팀입니다', { label: '300위 밖' })}</span>`);
  }

  const cityHtml = f.homeCity
    ? escapeHtml(f.homeCity)
    : naCell(f.hasCityData ? '이 팀의 공연 도시 기록이 없습니다' : '팀별 활동 지역 자료가 아직 없습니다');
  items.push(`<span class="team-fact"><span class="team-fact-lbl">지역</span>${cityHtml}</span>`);

  const yr = /^\d{4}/.test(String(f.firstRelease || '')) ? String(f.firstRelease).slice(0, 4) : '';
  items.push(`<span class="team-fact"><span class="team-fact-lbl">첫 발매</span>${yr ? `${escapeHtml(yr)}년` : naCell('첫 발매 기록이 없습니다')}</span>`);

  if (f.genre && f.genre !== '미분류') {
    items.push(`<span class="team-fact"><span class="team-fact-lbl">장르</span>${escapeHtml(f.genre)}${genreConfidenceBadgeHtml(f.teamKey)}</span>`);
  }
  return `<div class="team-facts" aria-label="팀 요약 정보">${items.join('')}</div>`;
}

/** '비교' = 같은 장르 후보들 사이에서 색 지도로 보기 (장르를 모르면 전체 후보) */
export function compareButtonHtml(genre) {
  const g = genre && genre !== '미분류' ? genre : '';
  const href = `#/discover?view=heat${g ? `&genre=${encodeURIComponent(g)}` : ''}`;
  const title = g ? `${g} 후보들과 색 지도로 비교` : '전체 후보와 색 지도로 비교';
  return `<a class="btn" href="${escapeHtml(href)}" title="${escapeHtml(title)}">비교</a>`;
}

/**
 * @param {Array<{ id: string, label: string }>} items 화면에 실제로 있는 칸만
 */
export function renderTeamTocHtml(items) {
  if (!items.length) return '';
  return `
    <nav class="team-toc" id="teamToc" aria-label="이 쪽 안 목차">
      ${items.map((it, i) => `<a class="team-toc-link${i === 0 ? ' is-active' : ''}" href="#${escapeHtml(it.id)}" data-toc-target="${escapeHtml(it.id)}">${escapeHtml(it.label)}</a>`).join('')}
    </nav>`;
}

/** 목차: 누르면 그 칸으로 부드럽게 이동(주소 해시는 바꾸지 않음), 스크롤하면 현재 칸 강조 */
export function wireTeamToc(root) {
  const toc = root.querySelector('#teamToc');
  if (!toc) return;
  const header = document.querySelector('.top-header');
  const headerSticky = header && getComputedStyle(header).position === 'sticky';
  const headerH = headerSticky ? header.getBoundingClientRect().height : 0;
  const tocH = toc.getBoundingClientRect().height;
  root.style.setProperty('--team-toc-top', `${Math.round(headerH)}px`);
  root.style.setProperty('--team-scroll-pad', `${Math.round(headerH + tocH + 8)}px`);

  const links = [...toc.querySelectorAll('[data-toc-target]')];
  const setActive = (id) => {
    for (const a of links) {
      const on = a.dataset.tocTarget === id;
      a.classList.toggle('is-active', on);
      if (on) a.setAttribute('aria-current', 'location');
      else a.removeAttribute('aria-current');
    }
  };

  toc.addEventListener('click', (e) => {
    const a = e.target.closest('[data-toc-target]');
    if (!a) return;
    e.preventDefault(); // 해시 라우터와 부딪히지 않게
    const target = root.querySelector(`#${CSS.escape(a.dataset.tocTarget)}`);
    if (!target) return;
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    target.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' });
    setActive(a.dataset.tocTarget);
  });

  if (tocObserver) tocObserver.disconnect();
  if (typeof IntersectionObserver === 'undefined') return;
  const visible = new Map();
  tocObserver = new IntersectionObserver((entries) => {
    for (const en of entries) visible.set(en.target.id, en.isIntersecting ? en.boundingClientRect.top : null);
    const firstVisible = links
      .map(a => a.dataset.tocTarget)
      .find(id => visible.get(id) !== null && visible.get(id) !== undefined);
    if (firstVisible) setActive(firstVisible);
  }, { rootMargin: `-${Math.round(headerH + tocH)}px 0px -55% 0px`, threshold: 0 });
  for (const a of links) {
    const sec = root.querySelector(`#${CSS.escape(a.dataset.tocTarget)}`);
    if (sec) tocObserver.observe(sec);
  }
}
