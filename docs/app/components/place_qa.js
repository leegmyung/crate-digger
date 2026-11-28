/**
 * 장소 질문 상자 (docs/ux_simplify_2026-11-28.md ⑩) — 공연장·도시·페스티벌 머리 바로 아래 같은 자리, 같은 모양.
 * 질문 3개 중 가운데('어디까지 갔나?')를 💡 로 강조. 모양은 css/ux.css 의 .venue-qa.
 */
import { escapeHtml } from '../ui.js';

/**
 * @param {{ q: string, a: string }[]} questions insight_text.js 의 venueQuestions·cityQuestions·festivalQuestions
 * @param {string} [label] 화면 읽기 프로그램용 이름
 */
export function placeQaHtml(questions, label = '이곳 요약 질문') {
  if (!Array.isArray(questions) || !questions.length) return '';
  return `
    <div class="venue-qa" aria-label="${escapeHtml(label)}">
      ${questions.map((x, i) => `<div class="venue-qa-item${i === 1 ? ' is-lead' : ''}"><p class="venue-qa-q">${i === 1 ? '💡 ' : ''}${escapeHtml(x.q)}</p><p class="venue-qa-a">${escapeHtml(x.a)}</p></div>`).join('')}
    </div>`;
}
