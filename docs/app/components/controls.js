/**
 * 1-6: 공용 '자료 없음' 칸(naCell) · 기간 분절 버튼(periodSwitch)
 * - naCell(reason): '—' (또는 '자료 없음') + 마우스·초점·탭 시 이유 말풍선 표시 (0과 '모름' 구분)
 * - periodSwitch(options): 네모 분절 탭, 선택 = 강조색 밑줄, 좌우 화살표 키보드 이동 + aria-selected
 */

function esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/**
 * 표 칸 또는 블록용 '자료 없음' 표시.
 * @param {string} [reason='수집된 기록이 없습니다']
 * @param {{ label?: string, block?: boolean }} [opts]
 */
export function naCell(reason = '수집된 기록이 없습니다', opts = {}) {
  const cleanReason = String(reason || '수집된 기록이 없습니다').trim();
  const text = opts.label ?? (opts.block ? '자료 없음' : '—');
  const cls = opts.block ? 'cd-na-cell is-block' : 'cd-na-cell';
  return `<span class="${cls}" tabindex="0" role="note" data-na-reason="${esc(cleanReason)}" aria-label="${esc(`자료 없음: ${cleanReason}`)}">${esc(text)}</span>`;
}

/**
 * 네모 기간 분절 버튼 (선택 = 강조색 밑줄, 좌우 화살표 키보드 탐색 지원).
 * @param {Array<string|{ id: string, label: string }>} options
 * @param {{ active?: string, name?: string, ariaLabel?: string, id?: string }} [opts]
 */
export function periodSwitch(options = [], opts = {}) {
  const norm = options.map(opt => (
    typeof opt === 'string'
      ? { id: opt, label: opt }
      : { id: String(opt?.id ?? opt?.label ?? ''), label: String(opt?.label ?? opt?.id ?? '') }
  )).filter(o => o.id || o.label);

  if (!norm.length) return '';
  const activeId = norm.some(o => o.id === opts.active) ? opts.active : norm[0].id;
  const nameAttr = opts.name ? ` data-period-name="${esc(opts.name)}"` : '';
  const idAttr = opts.id ? ` id="${esc(opts.id)}"` : '';
  const aria = opts.ariaLabel || '기간 선택';

  return `
    <div class="cd-period-switch" role="tablist" aria-label="${esc(aria)}" data-period-switch="1"${nameAttr}${idAttr}>
      ${norm.map(o => {
        const isSel = o.id === activeId;
        return `<button type="button" class="cd-period-btn${isSel ? ' is-active' : ''}" role="tab" aria-selected="${isSel ? 'true' : 'false'}" tabindex="${isSel ? '0' : '-1'}" data-period-val="${esc(o.id)}">${esc(o.label)}</button>`;
      }).join('')}
    </div>
  `;
}

/**
 * periodSwitch 컨테이너에 클릭 및 좌우 화살표(ArrowLeft/ArrowRight/Home/End) 탐색을 연결한다.
 * @param {ParentNode} root
 * @param {(val: string, switchEl: HTMLElement, btn: HTMLButtonElement) => void} [onChange]
 */
export function wirePeriodSwitch(root, onChange) {
  if (!root) return;
  const switches = root.matches?.('[data-period-switch]')
    ? [root]
    : [...root.querySelectorAll('[data-period-switch]')];

  for (const sw of switches) {
    if (sw.dataset.cdPeriodWired === '1') continue;
    sw.dataset.cdPeriodWired = '1';

    const selectBtn = (btn, shouldFocus = false) => {
      const btns = [...sw.querySelectorAll('.cd-period-btn[role="tab"]')];
      if (!btns.includes(btn)) return;
      const val = btn.dataset.periodVal || '';
      for (const b of btns) {
        const active = b === btn;
        b.classList.toggle('is-active', active);
        b.setAttribute('aria-selected', active ? 'true' : 'false');
        b.setAttribute('tabindex', active ? '0' : '-1');
      }
      if (shouldFocus) btn.focus();
      sw.dispatchEvent(new CustomEvent('cd:period-change', {
        bubbles: true,
        detail: { value: val, name: sw.dataset.periodName || '' },
      }));
      if (typeof onChange === 'function') onChange(val, sw, btn);
    };

    sw.addEventListener('click', (e) => {
      const btn = e.target?.closest?.('.cd-period-btn[role="tab"]');
      if (!btn || !sw.contains(btn)) return;
      selectBtn(btn, false);
    });

    sw.addEventListener('keydown', (e) => {
      const btn = e.target?.closest?.('.cd-period-btn[role="tab"]');
      if (!btn || !sw.contains(btn)) return;
      const btns = [...sw.querySelectorAll('.cd-period-btn[role="tab"]')];
      const idx = btns.indexOf(btn);
      if (idx < 0 || !btns.length) return;

      let nextIdx = -1;
      if (e.key === 'ArrowRight') nextIdx = (idx + 1) % btns.length;
      else if (e.key === 'ArrowLeft') nextIdx = (idx - 1 + btns.length) % btns.length;
      else if (e.key === 'Home') nextIdx = 0;
      else if (e.key === 'End') nextIdx = btns.length - 1;

      if (nextIdx >= 0) {
        e.preventDefault();
        selectBtn(btns[nextIdx], true);
      }
    });
  }
}
