/**
 * 5-1 후보 목록 '저장한 필터' 줄 — 필터 줄 위. 문장 이름으로 저장·적용·이름 바꾸기·지우기.
 * 저장할 때 '알림 규칙 미리보기'(지금 맞는 팀 수 · 최근 4주 주마다 새로 걸린 팀 수 → 한 주 평균 알림 수)를
 * 브리핑 카드와 같은 규칙(db_saved.js)으로 보여 준다 — Chartmetric 알림 만들기의 '알림 예측'처럼.
 */
import { appState, buildHashUrl } from '../state.js';
import { buildActiveFilterChips } from '../components/cand_filters.js';
import { savedFilterName, specFromState } from '../components/saved_match.js';
import { querySavedWeeklyForecast } from '../db_saved.js';
import { alertForecastText } from '../insight_text.js';
import {
  addSavedFilter, applySavedFilter, listSavedFilters, removeSavedFilter, renameSavedFilter, SAVED_MAX,
} from '../saved_filters.js';
import { escapeHtml } from '../ui.js';

const EXAMPLE_NAMES = 3;

const ui = { saving: false, renamingId: '', preview: '', notice: '' };

function currentName() {
  return savedFilterName(buildActiveFilterChips(appState).map(ch => ch.label));
}

function chipHtml(it, currentHash) {
  if (ui.renamingId === it.id) {
    return `
      <form class="saved-form" data-saved-rename-form="${escapeHtml(it.id)}">
        <input class="input saved-input" name="name" value="${escapeHtml(it.name)}" maxlength="60" aria-label="새 이름">
        <button type="submit" class="btn btn-sm">바꾸기</button>
        <button type="button" class="btn btn-sm" data-saved-cancel="1">취소</button>
      </form>`;
  }
  const active = it.hash === currentHash;
  return `
    <span class="saved-chip${active ? ' is-active' : ''}">
      <button type="button" class="saved-apply" data-saved-apply="${escapeHtml(it.id)}" title="이 필터 적용 (저장일 ${escapeHtml(it.created || '')})" aria-pressed="${active}">${escapeHtml(it.name)}</button>
      <button type="button" class="saved-icon" data-saved-rename="${escapeHtml(it.id)}" aria-label="${escapeHtml(it.name)} 이름 바꾸기" title="이름 바꾸기">✎</button>
      <button type="button" class="saved-icon" data-saved-remove="${escapeHtml(it.id)}" aria-label="${escapeHtml(it.name)} 지우기" title="지우기">×</button>
    </span>`;
}

function newFormHtml() {
  return `
    <form class="saved-form saved-new-form" data-saved-new-form="1">
      <input class="input saved-input" name="name" value="${escapeHtml(currentName())}" maxlength="60" aria-label="저장할 필터 이름">
      <button type="submit" class="btn btn-sm btn-primary">저장</button>
      <button type="button" class="btn btn-sm" data-saved-cancel="1">취소</button>
      <span class="saved-preview small muted" aria-live="polite">${escapeHtml(ui.preview || '이 규칙이면 알림이 얼마나 올지 계산 중…')}</span>
    </form>`;
}

export function renderSavedRowHtml() {
  const list = listSavedFilters();
  const currentHash = window.location.hash;
  const full = list.length >= SAVED_MAX;
  return `
    <section class="saved-row" aria-label="저장한 필터">
      <span class="saved-lbl">저장한 필터</span>
      <div class="saved-list">
        ${list.length ? list.map(it => chipHtml(it, currentHash)).join('') : '<span class="small muted">아직 없음 — 지금 조건을 저장하면 홈에서 새로 맞는 팀을 알려 줍니다</span>'}
      </div>
      ${ui.saving ? newFormHtml() : `<button type="button" class="cf-add-btn" data-saved-new="1"${full ? ` disabled title="저장 필터는 ${SAVED_MAX}개까지입니다"` : ''}>+ 이 필터 저장</button>`}
      ${ui.notice ? `<p class="saved-notice small muted" role="status">${escapeHtml(ui.notice)}</p>` : ''}
    </section>`;
}

async function loadPreview(host) {
  if (!appState.dataEnd) return;
  try {
    const res = await querySavedWeeklyForecast(specFromState(appState), appState.dataEnd);
    const ex = res.lastWeek.slice(0, EXAMPLE_NAMES).map(r => r.display_name).join(', ');
    const cap = Number(specFromState(appState)?.cfg?.limit) || Number(appState.cfg.limit) || 0;
    ui.preview = `${alertForecastText({ ...res, cap })}${ex ? ` · 지난주 예: ${ex}${res.lastWeek.length > EXAMPLE_NAMES ? ' 등' : ''}` : ''}`;
  } catch (_) {
    ui.preview = '미리보기를 계산하지 못했습니다';
  }
  const el = host.querySelector('.saved-preview');
  if (el && ui.saving) el.textContent = ui.preview;
}

/** @param {HTMLElement} host '#candSavedHost' */
export function wireSavedRow(host) {
  if (!host) return;
  const repaint = (focusSel = '') => {
    host.innerHTML = renderSavedRowHtml();
    if (focusSel) host.querySelector(focusSel)?.focus();
  };
  host.addEventListener('click', (e) => {
    const t = e.target.closest('button');
    if (!t) return;
    const d = t.dataset;
    if (d.savedApply) {
      const it = listSavedFilters().find(x => x.id === d.savedApply);
      if (it) applySavedFilter(it);
      return;
    }
    if (d.savedNew) {
      Object.assign(ui, { saving: true, renamingId: '', preview: '', notice: '' });
      repaint('.saved-new-form input');
      loadPreview(host);
      return;
    }
    if (d.savedRename) {
      Object.assign(ui, { renamingId: d.savedRename, saving: false, notice: '' });
      repaint('[data-saved-rename-form] input');
      return;
    }
    if (d.savedRemove) {
      const it = listSavedFilters().find(x => x.id === d.savedRemove);
      const ok = removeSavedFilter(d.savedRemove);
      ui.notice = `'${it?.name || ''}' 필터를 지웠습니다${ok ? '' : ' (브라우저 저장이 막혀 이 탭에서만 반영)'}`;
      repaint();
      return;
    }
    if (d.savedCancel) {
      Object.assign(ui, { saving: false, renamingId: '', notice: '' });
      repaint('[data-saved-new]');
    }
  });
  host.addEventListener('submit', (e) => {
    e.preventDefault();
    const form = e.target;
    const name = form.querySelector('input[name="name"]')?.value || '';
    if (form.dataset.savedNewForm) {
      const res = addSavedFilter({ name, hash: buildHashUrl('candidates', ''), spec: specFromState(appState) });
      ui.notice = !res.ok ? res.reason
        : (res.persisted ? `'${res.item.name}' 저장 — 홈에서 새로 맞는 팀을 보여 줍니다`
          : `'${res.item.name}' 저장 — 브라우저 저장이 막혀 이 탭을 닫으면 사라집니다`);
      ui.saving = false;
    } else if (form.dataset.savedRenameForm) {
      const ok = renameSavedFilter(form.dataset.savedRenameForm, name);
      ui.notice = ok ? '이름을 바꿨습니다' : '이름을 바꿨습니다 (브라우저 저장이 막혀 이 탭에서만 반영)';
      ui.renamingId = '';
    }
    repaint();
  });
  repaint();
}
