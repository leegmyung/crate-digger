/**
 * 긴 순위 목록은 처음 20줄만 보이고 나머지는 '더 보기'로 (docs/ux_simplify_2026-11-28.md ⑧).
 * 375 폭에서 차트 50줄이 13,590px까지 길어지던 문제를 줄인다. 줄은 그대로 그려 두고 숨기기만 한다(검색·인쇄 영향 없음).
 */

export const LIST_FIRST = 20;

/**
 * @param {number} total 전체 줄 수
 * @param {number} shown 지금 보이는 줄 수
 * @returns {string} 단추 글자 (남은 줄이 없으면 '')
 */
export function moreLabel(total, shown) {
  const rest = Number(total) - Number(shown);
  return rest > 0 ? `${rest}팀 더 보기` : '';
}

/**
 * 표 몸통(tbody)의 줄을 처음 first 줄만 보이게 하고, 표 아래에 '더 보기' 단추를 붙인다.
 * @param {HTMLElement|null} tbody
 * @param {number} [first]
 */
export function collapseRows(tbody, first = LIST_FIRST) {
  if (!tbody) return;
  const rows = [...tbody.querySelectorAll(':scope > tr')];
  const label = moreLabel(rows.length, first);
  if (!label) return;
  rows.slice(first).forEach(tr => tr.classList.add('ux-row-extra'));
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'btn btn-sm ux-more-btn';
  btn.textContent = label;
  btn.addEventListener('click', () => {
    rows.forEach(tr => tr.classList.remove('ux-row-extra'));
    btn.remove();
  });
  tbody.closest('table')?.after(btn);
}
