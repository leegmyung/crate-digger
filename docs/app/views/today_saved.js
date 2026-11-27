/**
 * 5-2 이번 주 브리핑 '저장 필터에 새로 맞는 팀' 카드.
 * 필터마다 데이터 기준일에는 맞고 7일 전 기준일에는 안 맞던 팀(db_saved.js — 저장 때 미리보기와 같은 규칙).
 * 저장 필터가 없으면 카드 대신 '필터 저장하기' 안내.
 */
import { appState } from '../state.js';
import { querySavedNewMatches } from '../db_saved.js';
import { applySavedFilter, listSavedFilters } from '../saved_filters.js';
import { escapeHtml, fmtInt } from '../ui.js';

const NAMES_SHOWN = 6;

export function renderSavedCardShellHtml() {
  const list = listSavedFilters();
  if (!list.length) {
    return `
      <section class="block today-saved-block is-empty" aria-label="저장 필터">
        <div class="today-saved-empty">
          <strong>필터 저장하기</strong>
          <span class="small muted">발굴 화면에서 조건을 고른 뒤 '+ 이 필터 저장'을 누르면, 매주 여기서 그 조건에 새로 맞는 팀을 알려 줍니다.</span>
          <a class="btn btn-sm" href="#/discover">발굴에서 저장 →</a>
        </div>
      </section>`;
  }
  return `
    <section class="block today-saved-block" id="todaySavedBlock" aria-label="저장 필터에 새로 맞는 팀">
      <div class="block-head">
        <div>
          <h2>내 저장 필터에 새로 들어온 팀</h2>
          <span class="block-meta" id="todaySavedMeta">계산 중…</span>
        </div>
        <a class="home-more-link" href="#/mine?tab=filters">필터 관리 →</a>
      </div>
      <ul class="today-saved-list" id="todaySavedList">
        ${list.map(it => `<li class="today-saved-item" data-saved-id="${escapeHtml(it.id)}"><span class="small muted">${escapeHtml(it.name)} — 계산 중…</span></li>`).join('')}
      </ul>
    </section>`;
}

function itemHtml(it, res) {
  if (!res) {
    return `<li class="today-saved-item"><span class="today-saved-name">${escapeHtml(it.name)}</span> <span class="small muted">계산하지 못했습니다</span></li>`;
  }
  const n = res.added.length;
  const names = res.added.slice(0, NAMES_SHOWN)
    .map(r => `<a class="inline-team-link" href="#/team/${encodeURIComponent(r.team_key)}">${escapeHtml(r.display_name)}</a>`)
    .join(' · ');
  const more = n > NAMES_SHOWN ? ` <span class="small muted">외 ${fmtInt(n - NAMES_SHOWN)}팀</span>` : '';
  const moveNote = it.spec?.moveIgnored ? ' <span class="small muted">(변화 조건은 빼고 셈)</span>' : '';
  return `
    <li class="today-saved-item">
      <div class="today-saved-head">
        <button type="button" class="today-saved-name" data-saved-apply="${escapeHtml(it.id)}" title="후보 목록에서 이 필터로 보기">${escapeHtml(it.name)}</button>
        <span class="today-saved-count${n ? ' is-up' : ''}">${n ? `새로 ${fmtInt(n)}팀` : '새 팀 없음'}</span>
        <span class="small muted">지금 ${fmtInt(res.total)}팀${moveNote}</span>
      </div>
      ${n ? `<div class="today-saved-names">${names}${more}</div>` : ''}
    </li>`;
}

/** 카드 자리를 채운다(필터마다 따로 계산) */
export async function fillSavedCard(root) {
  const block = root.querySelector('#todaySavedBlock');
  if (!block) return;
  const list = listSavedFilters();
  const to = appState.dataEnd;
  const results = await Promise.all(list.map(it => querySavedNewMatches(it.spec, to).catch(() => null)));
  if (!block.isConnected) return;
  const first = results.find(Boolean);
  const meta = block.querySelector('#todaySavedMeta');
  if (meta) meta.textContent = first ? `${first.from} → ${first.to} 사이 새로 맞은 팀` : '';
  const ul = block.querySelector('#todaySavedList');
  if (ul) ul.innerHTML = list.map((it, i) => itemHtml(it, results[i])).join('');
  block.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-saved-apply]');
    if (!btn) return;
    const it = listSavedFilters().find(x => x.id === btn.dataset.savedApply);
    if (it) applySavedFilter(it);
  });
}
