/**
 * '비교에 담기' — 어느 화면이든 data-compare-team 버튼을 누르면 담고/빼고, 화면 아래 오른쪽 '비교 n팀 →' 띠로 #/compare 이동.
 * (Chartmetric '비교' 담기처럼. 미니 플레이어처럼 #viewRoot 바깥에 한 번만 만든다)
 */
import { appState } from '../state.js';
import { escapeHtml } from '../ui.js';
import {
  COMPARE_MAX, compareHash, getCompareList, setCompareList, toggleCompareKey,
} from '../compare_list.js';

let tray = null;
let markRaf = 0;
const names = new Map();   // 팀 키 → 화면에 보인 이름 (띠에 쓰려고)

function toast(msg) {
  window.dispatchEvent(new CustomEvent('app:toast', { detail: msg }));
}

function labelFor(on, icon) {
  if (icon) return on ? '✓' : '⇄';
  return on ? '✓ 비교 중' : '＋ 비교';
}

/**
 * '＋ 비교' 버튼. variant 'icon' 은 표 안 작은 버튼.
 * @param {string} teamKey
 * @param {string} [teamName]
 * @param {{ variant?: 'icon'|'sm' }} [opts]
 */
export function compareToggleHtml(teamKey, teamName = '', opts = {}) {
  if (!teamKey) return '';
  const name = teamName || teamKey;
  const on = getCompareList().includes(teamKey);
  const icon = opts.variant === 'icon';
  const cls = icon ? 'btn btn-icon compare-btn' : 'btn btn-sm compare-btn';
  return `<button type="button" class="${cls}${on ? ' is-on' : ''}" data-compare-team="${escapeHtml(teamKey)}" data-compare-name="${escapeHtml(name)}" data-compare-variant="${icon ? 'icon' : 'sm'}" aria-pressed="${on}" aria-label="${escapeHtml(name)} ${on ? '비교에서 빼기' : '비교에 담기'}" title="${on ? '비교에서 빼기' : `비교에 담기 (최대 ${COMPARE_MAX}팀)`}">${labelFor(on, icon)}</button>`;
}

function markButtons() {
  markRaf = 0;
  const list = getCompareList();
  document.querySelectorAll('[data-compare-team]').forEach(btn => {
    const on = list.includes(btn.dataset.compareTeam);
    if (btn.classList.contains('is-on') === on) return;
    btn.classList.toggle('is-on', on);
    btn.setAttribute('aria-pressed', String(on));
    const name = btn.dataset.compareName || btn.dataset.compareTeam;
    btn.setAttribute('aria-label', `${name} ${on ? '비교에서 빼기' : '비교에 담기'}`);
    btn.textContent = labelFor(on, btn.dataset.compareVariant === 'icon');
  });
}

function scheduleMark() {
  if (!markRaf) markRaf = requestAnimationFrame(markButtons);
}

function renderTray() {
  if (!tray) return;
  const list = getCompareList();
  const onComparePage = /^#\/compare(?:\?|$)/.test(window.location.hash);
  if (!list.length || onComparePage) {
    tray.hidden = true;
    tray.innerHTML = '';
    document.body.classList.remove('has-compare-tray');
    return;
  }
  const shown = list.map(k => names.get(k) || appState.teamIndex?.find(t => t.team_key === k)?.display_name || k);
  tray.hidden = false;
  document.body.classList.add('has-compare-tray');
  tray.innerHTML = `
    <span class="ct-names" title="${escapeHtml(shown.join(', '))}"><strong>비교 ${list.length}/${COMPARE_MAX}</strong> ${escapeHtml(shown.join(' · '))}</span>
    <a class="btn btn-sm btn-primary" href="${escapeHtml(compareHash(list))}">${list.length >= 2 ? '나란히 보기 →' : '보기 →'}</a>
    <button type="button" class="btn btn-sm" data-compare-clear aria-label="비교 목록 비우기">비우기</button>`;
}

function onDocClick(e) {
  const btn = e.target.closest?.('[data-compare-team]');
  if (btn) {
    // 표 행·카드의 '눌러서 이동'보다 먼저 받는다
    e.preventDefault();
    e.stopPropagation();
    const key = btn.dataset.compareTeam;
    names.set(key, btn.dataset.compareName || key);
    const res = toggleCompareKey(getCompareList(), key);
    if (res.full) {
      toast(`비교는 ${COMPARE_MAX}팀까지예요 — 하나를 빼고 담아 주세요`);
      return;
    }
    setCompareList(res.list);
    return;
  }
  if (tray && tray.contains(e.target) && e.target.closest('[data-compare-clear]')) {
    setCompareList([]);
  }
}

/** 이름을 미리 알려 둔다 (비교 화면이 팀 이름을 알았을 때 등). */
export function rememberCompareName(teamKey, name) {
  if (teamKey && name) names.set(teamKey, name);
}

/** 한 번만 부른다 (app.js boot). */
export function initCompareTray() {
  if (tray) return;
  tray = document.createElement('div');
  tray.id = 'compareTray';
  tray.className = 'compare-tray';
  tray.setAttribute('role', 'region');
  tray.setAttribute('aria-label', '비교에 담은 팀');
  tray.hidden = true;
  document.body.appendChild(tray);
  document.addEventListener('click', onDocClick, true);
  window.addEventListener('app:compare-changed', () => {
    renderTray();
    scheduleMark();
  });
  window.addEventListener('hashchange', renderTray);
  const root = document.getElementById('viewRoot');
  if (root && typeof MutationObserver !== 'undefined') {
    new MutationObserver(scheduleMark).observe(root, { childList: true, subtree: true });
  }
  renderTray();
}
