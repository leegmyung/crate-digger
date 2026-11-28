/**
 * 정보 구조 v2 '내 목록' (#/mine?tab=watch|venues|filters) 도우미:
 * - 상단 탭 바 (관심 팀 · 구독 공연장 · 저장한 필터)
 * - 저장한 필터 조건 요약 & 관리 패널 (이름 바꾸기 · 지우기 · 발굴에서 열기 · 지난 7일 새로 맞은 팀 계산)
 * - 구독 공연장 빈 상태 / 탭 패널 래퍼 (venue_subs_view.js 재사용)
 */
import { appState, MINE_TABS } from '../state.js';
import { querySavedNewMatches } from '../db_saved.js';
import {
  applySavedFilter, listSavedFilters, removeSavedFilter, renameSavedFilter, SAVED_MAX,
} from '../saved_filters.js';
import { listVenueSubs } from '../venue_subs.js';
import { renderVenueSubsHtml, wireVenueSubs } from './venue_subs_view.js';
import { escapeHtml, fmtInt, renderEmptyState } from '../ui.js';

const STAGE_NAMES = {
  '0': '언급 전 신인',
  '1': '첫 신호',
  '2': '여러 곳에서 보임',
  '3': '선정·수상 후보',
  '4': '졸업',
};

const NAMES_SHOWN = 6;

/** 저장 필터 규격(spec) → 사람이 읽기 쉬운 조건 태그 배열 */
export function summarizeFilterSpec(spec) {
  if (!spec || typeof spec !== 'object') return ['기본 조건'];
  const parts = [];
  const cfg = spec.cfg || {};
  if (spec.preset === 'rising') parts.push('프리셋: 떠오르는 팀');
  if (cfg.genre) parts.push(`장르: ${cfg.genre}`);
  if (spec.stage !== undefined && spec.stage !== '') {
    parts.push(`단계: ${STAGE_NAMES[String(spec.stage)] || spec.stage}`);
  }
  if (Number(spec.rm) > 0) parts.push(`첫 발매 ${Number(spec.rm)}개월 이내`);
  if (spec.region === 'non_seoul') parts.push('서울 외 지역');
  if (Number(spec.periodDays) > 0) parts.push(`최근 ${Number(spec.periodDays)}일`);
  if (Array.isArray(cfg.branches) && cfg.branches.length > 0 && cfg.branches.length < 4) {
    parts.push(`신호 종류: ${cfg.branches.join(', ')}`);
  }
  if (Number(cfg.min_branches) > 1) parts.push(`최소 ${Number(cfg.min_branches)}종류`);
  if (spec.query) parts.push(`검색: "${spec.query}"`);
  if (spec.moveIgnored) parts.push('변화 조건 제외');
  return parts.length ? parts : ['전체 후보 (기본 조건)'];
}

export function normalizeMineTab(tab) {
  if (tab === 'teams' || tab === 'watch') return 'watch';
  return MINE_TABS.includes(tab) ? tab : 'watch';
}

/** #/mine 상단 탭 줄 */
export function renderMineTabsHtml(activeTab, { watchCount = 0, venueCount = 0, filterCount = 0 } = {}) {
  const cur = normalizeMineTab(activeTab);
  const tabs = [
    { id: 'watch', label: '관심 팀', count: watchCount, href: '#/mine' },
    { id: 'venues', label: '구독 공연장', count: venueCount, href: '#/mine?tab=venues' },
    { id: 'filters', label: '저장한 필터', count: filterCount, href: '#/mine?tab=filters' },
  ];
  return `
    <nav class="v2-tabs mine-tabs" role="tablist" aria-label="내 목록 탭">
      ${tabs.map(t => `
        <button
          type="button"
          role="tab"
          class="v2-tab${cur === t.id ? ' is-active' : ''}"
          aria-selected="${cur === t.id}"
          data-mine-tab="${t.id}"
        >
          <span>${escapeHtml(t.label)}</span>
          <span class="v2-tab-count">${fmtInt(t.count)}</span>
        </button>
      `).join('')}
    </nav>
  `;
}

/** #/mine?tab=venues 본문 (venue_subs_view.js 재사용 + 빈 상태) */
export function renderMineVenuesPanelHtml(alertsData) {
  const subs = listVenueSubs();
  if (!subs.length) {
    return renderEmptyState({
      title: '구독 중인 공연장이 없습니다',
      message: '공연장 페이지에서 구독을 누르면 처음 선 신인과 새 공연 소식을 모아 봅니다.',
      showReset: false,
      actionLabel: '공연장 둘러보기',
      actionHref: '#/venues',
    });
  }
  return `
    ${renderVenueSubsHtml(alertsData, { editable: true, title: '구독 중인 공연장' })}
    <div class="mine-sub-foot">
      <a class="btn btn-sm" href="#/venues">공연장 더 둘러보기 →</a>
      <a class="home-more-link" href="#/alerts">전체 알림 센터 →</a>
    </div>
  `;
}

export function wireMineVenuesPanel(root, onChange) {
  wireVenueSubs(root, onChange);
}

/** #/mine?tab=filters 본문 — 저장한 필터 목록 + 이름 바꾸기/삭제 + 새로 맞은 팀 수 비동기 채우기 */
export function renderMineFiltersPanelHtml({ renamingId = '', notice = '' } = {}) {
  const list = listSavedFilters();
  if (!list.length) {
    return renderEmptyState({
      title: '저장한 필터가 없습니다',
      message: '발굴 화면에서 원하는 조건을 고르고 "☆ 이 조건 담기"를 누르면 매주 새로 맞는 팀을 이곳과 홈에서 모아 봅니다.',
      showReset: false,
      actionLabel: '발굴에서 필터 만들기',
      actionHref: '#/discover',
    });
  }
  return `
    <section class="block mine-filters-block" id="mineFiltersBlock" aria-label="저장한 필터 목록">
      <div class="block-head">
        <div>
          <h2>저장한 필터</h2>
          <span class="block-meta" id="mineFiltersMeta">${fmtInt(list.length)} / ${fmtInt(SAVED_MAX)}개 · 최근 7일 새로 맞는 팀 계산 중…</span>
        </div>
        <a class="btn btn-sm" href="#/discover">+ 발굴에서 새 필터 저장</a>
      </div>
      ${notice ? `<p class="mine-notice small muted" role="status">${escapeHtml(notice)}</p>` : ''}
      <ul class="mine-filter-list">
        ${list.map(it => {
          const tags = summarizeFilterSpec(it.spec);
          const isRenaming = renamingId === it.id;
          return `
            <li class="mine-filter-item" data-saved-id="${escapeHtml(it.id)}">
              <div class="mine-filter-top">
                <div class="mine-filter-title-wrap">
                  ${isRenaming ? `
                    <form class="saved-form" data-mine-rename-form="${escapeHtml(it.id)}">
                      <input class="input saved-input" name="name" value="${escapeHtml(it.name)}" maxlength="60" aria-label="새 필터 이름">
                      <button type="submit" class="btn btn-sm btn-primary">저장</button>
                      <button type="button" class="btn btn-sm" data-mine-cancel="1">취소</button>
                    </form>
                  ` : `
                    <strong class="mine-filter-name">${escapeHtml(it.name)}</strong>
                    ${it.created ? `<span class="small muted mono">저장 ${escapeHtml(it.created)}</span>` : ''}
                  `}
                </div>
                ${isRenaming ? '' : `
                  <div class="mine-filter-actions">
                    <button type="button" class="btn btn-sm btn-primary" data-mine-apply="${escapeHtml(it.id)}">발굴에서 열기</button>
                    <button type="button" class="btn btn-sm" data-mine-rename="${escapeHtml(it.id)}">이름 변경</button>
                    <button type="button" class="btn btn-sm" data-mine-remove="${escapeHtml(it.id)}">지우기</button>
                  </div>
                `}
              </div>
              <div class="mine-filter-tags">
                ${tags.map(t => `<span class="mine-cond-tag">${escapeHtml(t)}</span>`).join('')}
              </div>
              <div class="mine-filter-match" data-mine-match="${escapeHtml(it.id)}">
                <span class="small muted">최근 7일 새로 맞는 팀 계산 중…</span>
              </div>
            </li>
          `;
        }).join('')}
      </ul>
    </section>
  `;
}

/** 저장 필터별 최신 매칭 수를 DuckDB에서 비동기로 채운다 */
export async function fillMineFiltersMatches(root) {
  const block = root.querySelector('#mineFiltersBlock');
  if (!block) return;
  const list = listSavedFilters();
  if (!list.length) return;
  const to = appState.dataEnd;
  const results = await Promise.all(list.map(it => querySavedNewMatches(it.spec, to).catch(() => null)));
  if (!block.isConnected) return;

  const first = results.find(Boolean);
  const meta = block.querySelector('#mineFiltersMeta');
  if (meta) {
    meta.textContent = first
      ? `${fmtInt(list.length)} / ${fmtInt(SAVED_MAX)}개 · ${first.from} → ${first.to} 기준`
      : `${fmtInt(list.length)} / ${fmtInt(SAVED_MAX)}개`;
  }

  list.forEach((it, idx) => {
    const slot = block.querySelector(`[data-mine-match="${CSS.escape(it.id)}"]`);
    if (!slot) return;
    const res = results[idx];
    if (!res) {
      slot.innerHTML = '<span class="small muted">매칭 수를 계산하지 못했습니다.</span>';
      return;
    }
    const n = res.added.length;
    const names = res.added.slice(0, NAMES_SHOWN)
      .map(r => `<a class="inline-team-link" href="#/team/${encodeURIComponent(r.team_key)}">${escapeHtml(r.display_name)}</a>`)
      .join(' · ');
    const more = n > NAMES_SHOWN ? ` <span class="small muted">외 ${fmtInt(n - NAMES_SHOWN)}팀</span>` : '';
    slot.innerHTML = `
      <div class="mine-filter-match-line">
        <span class="today-saved-count${n ? ' is-up' : ''}">${n ? `지난 7일 새로 ${fmtInt(n)}팀` : '지난 7일 새 팀 없음'}</span>
        <span class="small muted">현재 전체 ${fmtInt(res.total)}팀</span>
      </div>
      ${n ? `<div class="today-saved-names">${names}${more}</div>` : ''}
    `;
  });
}

/** 저장 필터 패널 이벤트 연결 */
export function wireMineFiltersPanel(root, uiState, onRepaint) {
  const block = root.querySelector('#mineFiltersBlock');
  if (!block) return;
  block.addEventListener('click', (e) => {
    const btn = e.target.closest('button');
    if (!btn) return;
    const d = btn.dataset;
    if (d.mineApply) {
      const it = listSavedFilters().find(x => x.id === d.mineApply);
      if (it) applySavedFilter(it);
      return;
    }
    if (d.mineRename) {
      uiState.renamingId = d.mineRename;
      uiState.notice = '';
      onRepaint();
      root.querySelector('[data-mine-rename-form] input')?.focus();
      return;
    }
    if (d.mineRemove) {
      const it = listSavedFilters().find(x => x.id === d.mineRemove);
      const ok = removeSavedFilter(d.mineRemove);
      uiState.renamingId = '';
      uiState.notice = `'${it?.name || ''}' 필터를 지웠습니다${ok ? '' : ' (이 탭에서만 반영)'}`;
      onRepaint();
      return;
    }
    if (d.mineCancel) {
      uiState.renamingId = '';
      uiState.notice = '';
      onRepaint();
    }
  });
  block.addEventListener('submit', (e) => {
    const form = e.target.closest('[data-mine-rename-form]');
    if (!form) return;
    e.preventDefault();
    const id = form.dataset.mineRenameForm;
    const name = form.querySelector('input[name="name"]')?.value || '';
    const ok = renameSavedFilter(id, name);
    uiState.renamingId = '';
    uiState.notice = ok ? '필터 이름을 바꿨습니다.' : '필터 이름을 바꿨습니다 (이 탭에서만 반영).';
    onRepaint();
  });
}

/** 공통 하단 근거 줄 (홈·알림·내 목록 → 검증 쪽 연결) */
export function renderEvidenceFooterHtml({ extraNote = '' } = {}) {
  const health = appState.dataHealth || { ok: true, totalSources: 0, okSources: 0, summaryLabel: '수집 정상' };
  const updatedRaw = appState.meta?.generated_at || appState.dataEnd || '';
  const updatedStr = updatedRaw ? String(updatedRaw).replace('T', ' ').slice(0, 16) : '—';
  const healthHtml = health.ok
    ? `<span class="ev-status-ok">${health.totalSources > 0 ? `수집 정상 (${fmtInt(health.okSources)}/${fmtInt(health.totalSources)} 출처)` : '수집 정상'}</span>`
    : `<a class="ev-status-warn" href="#/verify/quality">${escapeHtml(health.summaryLabel || '수집 점검 필요')}</a>`;

  return `
    <footer class="home-evidence-bar" aria-label="데이터 근거 및 검증 링크">
      <div class="home-evidence-meta">
        <span>데이터 갱신 <span class="mono">${escapeHtml(updatedStr)}</span></span>
        <span class="ev-sep" aria-hidden="true">·</span>
        ${healthHtml}
        ${extraNote ? `<span class="ev-sep" aria-hidden="true">·</span><span>${escapeHtml(extraNote)}</span>` : ''}
      </div>
      <div class="home-evidence-links">
        <a href="#/verify/backtest">점수 검증·성적표 →</a>
        <a href="#/verify/grades">정답 규칙 →</a>
        <a href="#/verify/quality">데이터 품질 →</a>
      </div>
    </footer>
  `;
}
