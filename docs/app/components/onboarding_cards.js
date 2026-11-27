/**
 * 6-1: 첫 방문 할 일 3장 — 관심 팀 추가 · 필터 저장 · 공연장 구독.
 * 각 항목을 완료하면 해당 카드가 사라지고, 3가지를 모두 마치면 영역 전체가 숨겨진다.
 */
import { getWatchlist } from '../state.js';
import { listSavedFilters } from '../saved_filters.js';
import { listVenueSubs } from '../venue_subs.js';
import { escapeHtml } from '../ui.js';

export function renderOnboardingStripHtml() {
  const tasks = [
    {
      id: 'watch',
      title: '관심 팀 추가',
      desc: '지켜볼 팀을 담아 두면 최근 7일 새 신호와 순위 변동을 모아 봅니다.',
      cta: '후보 목록에서 고르기',
      href: '#/candidates',
      done: getWatchlist().length > 0,
    },
    {
      id: 'filter',
      title: '필터 저장',
      desc: '자주 보는 장르·발굴 단계 조건을 저장해 매주 새 팀을 확인합니다.',
      cta: '조건 만들고 저장하기',
      href: '#/candidates',
      done: listSavedFilters().length > 0,
    },
    {
      id: 'venue',
      title: '공연장 구독',
      desc: '관심 공연장을 구독하면 처음 선 신인과 새 공연 소식을 받아 봅니다.',
      cta: '공연장 둘러보기',
      href: '#/venues',
      done: listVenueSubs().length > 0,
    },
  ];

  const remaining = tasks.filter(t => !t.done);
  if (!remaining.length) return '';

  const doneCount = tasks.length - remaining.length;
  return `
    <section class="onboard-strip" id="todayOnboardStrip" aria-label="처음 시작하기">
      <div class="onboard-head">
        <span class="onboard-title">처음 시작하기</span>
        <span class="onboard-meta">완료 ${doneCount} / ${tasks.length} · 마치면 자동으로 사라집니다</span>
      </div>
      <div class="onboard-grid">
        ${remaining.map(t => `
          <article class="onboard-card" data-onboard-task="${escapeHtml(t.id)}">
            <h3 class="onboard-card-title">${escapeHtml(t.title)}</h3>
            <p class="onboard-card-desc">${escapeHtml(t.desc)}</p>
            <a class="btn btn-sm onboard-card-cta" href="${escapeHtml(t.href)}">${escapeHtml(t.cta)} →</a>
          </article>
        `).join('')}
      </div>
    </section>
  `;
}
