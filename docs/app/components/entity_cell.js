/**
 * 표·목록의 '이름 칸' 공통 마크업 — [사진] [이름 줄 / 아래 줄] [오른쪽 버튼] (docs/layout_rules.md 2절)
 * 배지·장르·상태는 이름 뒤에 붙이지 않고 '아래 줄'에 둔다. 이름 길이가 달라도 배지·버튼 위치가 줄마다 같게.
 * 모양은 css/tables.css 의 .cell-entity* 가 맡는다.
 */
import { escapeHtml } from '../ui.js';

/**
 * @param {{ avatar?: string, name: string, sub?: string, actions?: string, title?: string, cls?: string }} p
 *   avatar·name·sub·actions 는 이미 만든 HTML(이스케이프는 부르는 쪽 책임), title 은 글자(여기서 이스케이프).
 * @returns {string}
 */
export function entityCellHtml({ avatar = '', name, sub = '', actions = '', title = '', cls = '' }) {
  const titleAttr = title ? ` title="${escapeHtml(title)}"` : '';
  return `<div class="cell-entity${cls ? ` ${cls}` : ''}">${avatar}<div class="cell-entity-text"><span class="cell-entity-name"${titleAttr}>${name}</span>${sub ? `<span class="cell-entity-sub">${sub}</span>` : ''}</div>${actions ? `<span class="cell-entity-actions">${actions}</span>` : ''}</div>`;
}
