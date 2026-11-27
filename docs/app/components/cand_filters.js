/**
 * 2-1: 후보 목록 필터 줄 한 줄 구조 (+ 필터 추가 묶음 메뉴 · 적용 꼬리표 ⓧ · 375px 접힘)
 * 2-2: 첫 발매 N개월 필터 + 문장형 프리셋 5종 (숨은 조건 없이 꼬리표로 전부 노출)
 * 2-4: 순위 옆 지난달/지난주 대비 ▲▼ 텍스트 및 300위 밖 구간 포맷
 */
import { ALL_BRANCHES } from '../state.js';
import {
  escapeHtml, fmtInt, INFO_TIPS, infoTip, STAGE_META, STAGE_ORDER, TERMS,
} from '../ui.js';

export const RELEASE_MONTH_OPTIONS = [6, 12, 18, 24, 36];

export const CAND_PRESETS = [
  {
    id: 'debut12',
    label: '갓 데뷔 (12개월)',
    tipTitle: '갓 데뷔 (12개월)',
    tip: INFO_TIPS.preset_debut12,
  },
  {
    id: 'blank',
    label: '백지 신인',
    tipTitle: '백지 신인',
    tip: INFO_TIPS.preset_blank,
  },
  {
    id: 'selected',
    label: '선정 직후',
    tipTitle: '선정 직후',
    tip: INFO_TIPS.preset_selected,
  },
  {
    id: 'regional',
    label: '지방 씬',
    tipTitle: '지방 씬',
    tip: INFO_TIPS.preset_regional,
  },
  {
    id: 'rising',
    label: '떠오르는 팀',
    tipTitle: '떠오르는 팀',
    tip: INFO_TIPS.preset_rising,
  },
];

// 첫 발매 N개월 규칙은 저장 필터와 같은 규칙을 쓰려고 saved_match.js 한 곳에 둔다
export { matchesReleaseMonths, subtractMonthsIso } from './saved_match.js';

/** 현재 적용된 필터들을 제거 가능한 꼬리표 목록으로 만든다(숨은 조건 없음). */
export function buildActiveFilterChips(appState) {
  const c = appState.cfg;
  const chips = [];

  if (appState.candPreset === 'rising') {
    chips.push({ key: 'preset', label: '떠오르는 팀 (최근 30일 언급 ↑)', removable: true });
    if (c.exclude_famous) {
      chips.push({ key: 'rising_famous', label: '유명 팀 제외', removable: false, presetCond: true });
    }
    chips.push({ key: 'rising_tier', label: '공연장 체급 ≤ M', removable: false, presetCond: true });
    chips.push({ key: 'rising_fans', label: '멜론 팬 ≤ 10,000', removable: false, presetCond: true });
  }
  if (c.genre) {
    chips.push({ key: 'genre', label: `장르: ${c.genre}`, removable: true });
  }
  if (Number(appState.candReleaseMonths) > 0) {
    chips.push({ key: 'rm', label: `첫 발매 ${appState.candReleaseMonths}개월 이내`, removable: true });
  }
  if (appState.candRegion === 'non_seoul') {
    chips.push({ key: 'region', label: '지역: 지방 씬 (서울 외)', removable: true });
  }
  if (appState.candStage) {
    const meta = STAGE_META[Number(appState.candStage)];
    chips.push({ key: 'stage', label: `단계: ${meta ? meta.short : appState.candStage}`, removable: true });
  }
  if (appState.candMove) {
    const mvLabel = appState.candMove === 'new'
      ? '새로 들어옴'
      : appState.candMove === 'riser'
        ? '상승'
        : '예정 공연';
    chips.push({ key: 'move', label: `변화: ${mvLabel}`, removable: true });
  }
  if (c.branches.length < ALL_BRANCHES.length) {
    chips.push({ key: 'branches', label: `갈래: ${c.branches.join('·')}`, removable: true });
  }
  if (Number(c.period_days) > 0) {
    chips.push({ key: 'period', label: `최근 ${c.period_days}일`, removable: true });
  }
  if (Number(c.newcomer_years) !== 3) {
    chips.push({ key: 'newcomer_years', label: `신인 ${c.newcomer_years}년 이내`, removable: true });
  }
  if (!c.exclude_famous) {
    chips.push({ key: 'exclude_famous', label: '유명 팀 포함', removable: true });
  }
  if (!c.only_no_outcome) {
    chips.push({ key: 'only_no_outcome', label: `${TERMS.priorOutcome} 포함`, removable: true });
  }
  if (appState.candQuery && appState.candQuery.trim()) {
    chips.push({ key: 'query', label: `검색: ${appState.candQuery.trim()}`, removable: true });
  }

  return chips;
}

/**
 * 2-1/2-2: 문장형 프리셋 줄 + 한 줄 필터 바 + '+ 필터 추가' 묶음 메뉴 HTML을 생성한다.
 */
export function renderCandFilterBarHtml({
  appState,
  counts,
  mobileOpen = false,
  popoverOpen = false,
}) {
  const c = appState.cfg;
  const activeChips = buildActiveFilterChips(appState);
  const removableCount = activeChips.filter(ch => ch.removable).length;
  const activePresetId = appState.candPreset
    || (Number(appState.candReleaseMonths) === 12 && !appState.candStage && !appState.candRegion ? 'debut12'
      : appState.candStage === '0' && !appState.candReleaseMonths && !appState.candRegion ? 'blank'
        : appState.candStage === '3' && !appState.candReleaseMonths && !appState.candRegion ? 'selected'
          : appState.candRegion === 'non_seoul' && !appState.candStage && !appState.candReleaseMonths ? 'regional'
            : '');

  const presetsHtml = CAND_PRESETS.map(p => {
    const isActive = activePresetId === p.id;
    const cnt = counts.presets?.[p.id];
    const cntTxt = (cnt !== null && cnt !== undefined) ? `<span class="cf-preset-cnt">${fmtInt(cnt)}</span>` : '';
    return `
      <span class="cf-preset-item">
        <button type="button" class="cf-preset-btn${isActive ? ' is-active' : ''}" data-cand-preset="${p.id}" aria-pressed="${isActive ? 'true' : 'false'}">
          <span>${escapeHtml(p.label)}</span>${cntTxt}
        </button>${infoTip(p.tipTitle, p.tip, { compact: true })}
      </span>
    `;
  }).join('');

  const chipsHtml = activeChips.map(ch => (
    ch.removable
      ? `<span class="cf-chip" data-chip-key="${escapeHtml(ch.key)}">
          <span>${escapeHtml(ch.label)}</span>
          <button type="button" class="cf-chip-x" data-remove-filter="${escapeHtml(ch.key)}" aria-label="${escapeHtml(ch.label)} 필터 지우기">×</button>
        </span>`
      : `<span class="cf-chip is-derived" title="프리셋에 포함된 조건입니다">${escapeHtml(ch.label)}</span>`
  )).join('');

  const genreMenuItems = [
    `<button type="button" class="cf-opt-btn${!c.genre ? ' is-active' : ''}" data-set-genre=""><span>전체 장르</span><span class="cf-opt-cnt">${fmtInt(counts.total)}</span></button>`,
    ...appState.validGenres.slice(0, 14).map(g => {
      const cnt = counts.genres.get(g) || 0;
      const active = c.genre === g;
      return `<button type="button" class="cf-opt-btn${active ? ' is-active' : ''}" data-set-genre="${escapeHtml(g)}"><span>${escapeHtml(g)}</span><span class="cf-opt-cnt">${fmtInt(cnt)}</span></button>`;
    }),
  ].join('');

  const releaseMenuItems = [
    `<button type="button" class="cf-opt-btn${!appState.candReleaseMonths ? ' is-active' : ''}" data-set-rm="0"><span>전체</span><span class="cf-opt-cnt">${fmtInt(counts.total)}</span></button>`,
    ...RELEASE_MONTH_OPTIONS.map(m => {
      const cnt = counts.releaseMonths[m] || 0;
      const active = Number(appState.candReleaseMonths) === m;
      return `<button type="button" class="cf-opt-btn${active ? ' is-active' : ''}" data-set-rm="${m}"><span>${m}개월 이내</span><span class="cf-opt-cnt">${fmtInt(cnt)}</span></button>`;
    }),
  ].join('');

  const stageMenuItems = STAGE_ORDER.map(code => {
    const meta = STAGE_META[code];
    const cnt = counts.stages[code] || 0;
    const active = appState.candStage === String(code);
    const suffix = code === 4 ? ' (숨김)' : '';
    return `<button type="button" class="cf-opt-btn${active ? ' is-active' : ''}" data-stage-chip="${code}" aria-pressed="${active ? 'true' : 'false'}"><span>${escapeHtml(meta.short)}${suffix}</span><span class="cf-opt-cnt">${fmtInt(cnt)}</span></button>`;
  }).join('');

  const branchMenuItems = ALL_BRANCHES.map(b => {
    const active = c.branches.includes(b);
    const cnt = counts.branches[b] || 0;
    return `<button type="button" class="cf-opt-btn${active ? ' is-active' : ''}" data-branch-chip="${escapeHtml(b)}" aria-pressed="${active ? 'true' : 'false'}"><span>${escapeHtml(b)}</span><span class="cf-opt-cnt">${fmtInt(cnt)}</span></button>`;
  }).join('');

  const moveMenuItems = [
    ['new', '새로 들어옴', counts.moves.new || 0],
    ['riser', '상승', counts.moves.riser || 0],
    ['upcoming', '예정 공연', counts.moves.upcoming || 0],
  ].map(([key, lbl, cnt]) => {
    const active = appState.candMove === key;
    return `<button type="button" class="cf-opt-btn${active ? ' is-active' : ''}" data-move-chip="${key}" aria-pressed="${active ? 'true' : 'false'}"><span>${escapeHtml(lbl)}</span><span class="cf-opt-cnt">${fmtInt(cnt)}</span></button>`;
  }).join('');

  const regionActive = appState.candRegion === 'non_seoul';
  const isHeat = appState.candView === 'heat';
  const regionCnt = counts.nonSeoul;
  const regionCntTxt = counts.hasCityData ? fmtInt(regionCnt) : '준비 중';

  return `
    <section class="inline-filter-bar cf-shell${mobileOpen ? ' is-mobile-open' : ''}" aria-label="후보 목록 필터">
      <div class="cf-presets-row" role="group" aria-label="문장형 프리셋">
        <span class="cf-presets-lbl">프리셋</span>
        <div class="cf-presets-list">${presetsHtml}</div>
      </div>

      <div class="cf-mobile-bar">
        <button type="button" class="cf-mobile-toggle" id="candMobileFilterToggle" aria-expanded="${mobileOpen ? 'true' : 'false'}" aria-controls="candFilterBody">
          <span>필터${removableCount ? ` ${removableCount}` : ''}</span>
          <span class="cf-caret" aria-hidden="true">${mobileOpen ? '▴' : '▾'}</span>
        </button>
        <input type="search" id="candFilterInputMobile" class="input cf-mobile-search" value="${escapeHtml(appState.candQuery || '')}" placeholder="팀·장르·이유 검색..." aria-label="모바일 팀 검색">
      </div>

      <div class="cf-bar" id="candFilterBody">
        <div class="cf-left">
          <div class="cf-add-wrap">
            <button type="button" class="cf-count-btn${removableCount > 0 ? ' has-active' : ''}" id="candFilterCountBtn" aria-expanded="${popoverOpen ? 'true' : 'false'}" aria-controls="candFilterPopover">
              필터${removableCount > 0 ? ` <span class="cf-count-num">${removableCount}</span>` : ''}
            </button>
            <button type="button" class="cf-add-btn" id="candAddFilterBtn" aria-expanded="${popoverOpen ? 'true' : 'false'}" aria-controls="candFilterPopover">
              + 필터 추가
            </button>

            <div class="cf-popover" id="candFilterPopover" ${popoverOpen ? '' : 'hidden'} role="dialog" aria-label="필터 추가 메뉴">
              <div class="cf-pop-grid">
                <div class="cf-pop-group">
                  <div class="cf-pop-title">팀 · 장르</div>
                  <div class="cf-pop-opts cf-pop-scroll">${genreMenuItems}</div>
                </div>

                <div class="cf-pop-group">
                  <div class="cf-pop-title">팀 · 첫 발매 N개월</div>
                  <div class="cf-pop-opts">${releaseMenuItems}</div>
                  <div class="cf-pop-title" style="margin-top:10px;">팀 · 지역</div>
                  <div class="cf-pop-opts">
                    <button type="button" class="cf-opt-btn${regionActive ? ' is-active' : ''}" data-set-region="${regionActive ? '' : 'non_seoul'}" aria-pressed="${regionActive ? 'true' : 'false'}">
                      <span>지방 씬 (서울 외)</span>
                      <span class="cf-opt-cnt">${escapeHtml(regionCntTxt)}</span>
                    </button>
                  </div>
                </div>

                <div class="cf-pop-group">
                  <div class="cf-pop-title">발굴 단계${infoTip('발굴 단계', INFO_TIPS.discovery_stage, { compact: true })}</div>
                  <div class="cf-pop-opts">${stageMenuItems}</div>
                  <div class="cf-pop-title" style="margin-top:10px;">변화</div>
                  <div class="cf-pop-opts">${moveMenuItems}</div>
                </div>

                <div class="cf-pop-group">
                  <div class="cf-pop-title">신호 갈래</div>
                  <div class="cf-pop-opts">${branchMenuItems}</div>
                  <div class="cf-pop-title" style="margin-top:10px;">세부 기준</div>
                  <div class="cf-pop-criteria">
                    <label class="cf-crit-row">
                      <span>신인 기준(년)</span>
                      <input type="number" id="candNewcomerInp" class="input input-num" min="1" max="15" value="${c.newcomer_years}">
                    </label>
                    <label class="cf-crit-check">
                      <input type="checkbox" id="candExcludeFamous" ${c.exclude_famous ? 'checked' : ''}>
                      <span>유명 팀 제외</span>
                    </label>
                    <label class="cf-crit-check">
                      <input type="checkbox" id="candOnlyNoOutcome" ${c.only_no_outcome ? 'checked' : ''}>
                      <span>${escapeHtml(TERMS.priorOutcome)} 팀 제외</span>
                    </label>
                    <label class="cf-crit-row">
                      <span>조회 상한</span>
                      <select id="candLimitSel" class="select" aria-label="조회 상한">
                        <option value="50" ${c.limit === 50 ? 'selected' : ''}>50팀</option>
                        <option value="100" ${c.limit === 100 ? 'selected' : ''}>100팀</option>
                        <option value="200" ${c.limit === 200 ? 'selected' : ''}>200팀</option>
                      </select>
                    </label>
                  </div>
                </div>
              </div>
              <div class="cf-pop-foot">
                <span class="small muted">발굴 단계 4(졸업)는 기본 숨김 · 조건은 주소에 저장됩니다</span>
                <button type="button" class="btn btn-sm" id="candCloseFilterPop">닫기</button>
              </div>
            </div>
          </div>

          <input type="search" id="candFilterInput" class="input cf-inline-search" value="${escapeHtml(appState.candQuery || '')}" placeholder="팀·장르·이유 검색..." aria-label="표 안에서 팀 검색">

          ${chipsHtml ? `<div class="cf-chips" aria-label="적용된 필터">${chipsHtml}</div>` : ''}
          ${removableCount > 0 ? '<button type="button" class="cf-clear-btn" data-action="reset-filters">모두 지우기</button>' : ''}
        </div>

        <div class="cf-right">
          <select id="candPeriodSel" class="select cf-period-sel" aria-label="최근 활동 기간">
            <option value="0" ${Number(c.period_days) === 0 ? 'selected' : ''}>전체 기간 (3년)</option>
            <option value="30" ${Number(c.period_days) === 30 ? 'selected' : ''}>최근 30일</option>
            <option value="90" ${Number(c.period_days) === 90 ? 'selected' : ''}>최근 90일</option>
            <option value="180" ${Number(c.period_days) === 180 ? 'selected' : ''}>최근 180일</option>
            <option value="365" ${Number(c.period_days) === 365 ? 'selected' : ''}>최근 365일</option>
          </select>

          <div class="cf-view-switch" role="group" aria-label="보기 전환">
            <button type="button" class="cf-view-btn${isHeat ? '' : ' is-active'}" data-cand-view="" aria-pressed="${isHeat ? 'false' : 'true'}">표</button>
            <button type="button" class="cf-view-btn${isHeat ? ' is-active' : ''}" data-cand-view="heat" aria-pressed="${isHeat ? 'true' : 'false'}" title="팀 × 신호 8개를 진하기(1~5단계)로 보기">색 지도</button>
          </div>
        </div>
      </div>
    </section>
  `;
}

/**
 * 2-4: 순위 옆 지난달(없으면 지난주) 대비 ▲▼ 평문 글자색 표시.
 * - 배지(pill) 없이 글자색만(--up / --down / --ink-muted)
 * - 상위 300 밖에서 진입 시 잡음 대신 구간 표시('300위 밖→200위대' 등)
 */
export function formatRankDeltaHtml(rc, displayRank) {
  if (!rc) return '';
  const useMonth = Boolean(rc.month_date);
  const label = useMonth ? (rc.month_label || '') : (rc.week_label || '');
  const delta = useMonth ? rc.month_change : rc.week_change;
  const refDate = useMonth ? rc.month_date : rc.week_date;
  const periodWord = useMonth ? '지난달' : '지난주';
  const tipPrefix = refDate ? `${periodWord}(${refDate}) 대비` : `${periodWord} 대비`;

  if (!label) return '';

  const curRank = Number(rc.rank || displayRank || 0);
  if (label === 'NEW') {
    if (curRank > 100 && curRank <= 300) {
      const band = Math.floor(curRank / 100) * 100;
      return `<span class="rank-delta is-bracket" title="${escapeHtml(`${tipPrefix}: 상위 300 밖에서 ${band}위대로 진입`)}">300위 밖→${band}위대</span>`;
    }
    if (curRank > 0 && curRank <= 100) {
      return `<span class="rank-delta is-up" title="${escapeHtml(`${tipPrefix}: 상위 300 밖에서 ${curRank}위로 신규 진입`)}">NEW</span>`;
    }
    return '';
  }

  if (delta !== null && delta !== undefined && Number.isFinite(delta)) {
    if (delta > 0) {
      return `<span class="rank-delta is-up" title="${escapeHtml(`${tipPrefix} ${delta}계단 상승`)}">▲${fmtInt(delta)}</span>`;
    }
    if (delta < 0) {
      return `<span class="rank-delta is-down" title="${escapeHtml(`${tipPrefix} ${Math.abs(delta)}계단 하락`)}">▼${fmtInt(Math.abs(delta))}</span>`;
    }
    return `<span class="rank-delta is-flat" title="${escapeHtml(`${tipPrefix} 순위 유지`)}">–</span>`;
  }

  if (label === '–') {
    return `<span class="rank-delta is-flat" title="${escapeHtml(`${tipPrefix} 순위 유지`)}">–</span>`;
  }
  return '';
}
