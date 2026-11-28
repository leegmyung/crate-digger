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
    desc: '첫 발매 1년 안',
    label: '갓 데뷔 (12개월)',
    tipTitle: '갓 데뷔 (12개월)',
    tip: INFO_TIPS.preset_debut12,
  },
  {
    id: 'blank',
    desc: '아직 남의 언급 없음',
    label: '백지 신인',
    tipTitle: '백지 신인',
    tip: INFO_TIPS.preset_blank,
  },
  {
    id: 'selected',
    desc: '선정·수상 후보 단계',
    label: '선정 직후',
    tipTitle: '선정 직후',
    tip: INFO_TIPS.preset_selected,
  },
  {
    id: 'regional',
    desc: '서울 밖에서 활동',
    label: '지방 씬',
    tipTitle: '지방 씬',
    tip: INFO_TIPS.preset_regional,
  },
  {
    id: 'rising',
    desc: '최근 30일 언급 늘어남',
    label: '떠오르는 팀',
    tipTitle: '떠오르는 팀',
    tip: INFO_TIPS.preset_rising,
  },
];

// 첫 발매 N개월 규칙은 저장 필터와 같은 규칙을 쓰려고 saved_match.js 한 곳에 둔다
export { matchesReleaseMonths, subtractMonthsIso } from './saved_match.js';

/** 발굴 ↔ 차트 역할 (docs/ux_simplify_2026-11-28.md ④) — 머리말에 한 줄씩 */
export const ROLE_LINES = Object.freeze({
  discover: '발굴 = 내 조건으로 신인 후보를 거르는 도구 (프리셋은 자주 쓰는 조건 묶음)',
  charts: '차트 = 정의가 고정된 순위표 · 매주 지난주와 비교 · 필터 없음',
});

// 차트 탭과 이름이 겹치는 프리셋 → 같은 정의의 차트 탭
const PRESET_CHART = {
  rising: { href: '#/charts/rising', label: '떠오르는', same: true },
  debut12: { href: '#/charts/debut', label: '갓 데뷔', same: false },
};

/** 차트와 겹치는 프리셋을 골랐을 때 '조건 vs 순위' 안내 한 줄 (아니면 '') */
export function presetChartNoteHtml(presetId) {
  const c = PRESET_CHART[presetId];
  if (!c) return '';
  const rel = c.same
    ? `차트의 '${c.label}'과 같은 조건입니다 — 여기선 다른 조건을 더 걸 수 있고, 차트는 순위와 지난주 대비를 보여 줍니다`
    : `차트의 '${c.label}'은 아직 언급 없는 신인만 따로 매긴 순위입니다 — 여기선 첫 발매 1년 안의 모든 후보를 조건으로 거릅니다`;
  return `<p class="disc-preset-note small" role="note">${escapeHtml(rel)} · <a href="${c.href}">차트에서 순위로 보기 →</a></p>`;
}

/**
 * 발굴 프리셋 줄 (docs/ux_simplify_2026-11-28.md ③) — 자주 쓰는 조합 5개 + 내가 담은 조건(저장 필터).
 * 누르면 조건이 걸리고, 다시 누르면 풀린다. 버튼 data- 는 예전 패널 프리셋과 같다(candidates.js 연결 그대로).
 */
export function renderPresetRowHtml({ appState, counts, saved = [], currentHash = '' }) {
  const activeId = activePresetOf(appState);
  const cards = CAND_PRESETS.map((p) => {
    const cnt = counts?.presets?.[p.id];
    const on = activeId === p.id;
    const cntHtml = cnt !== null && cnt !== undefined ? `<span class="disc-preset-cnt">${fmtInt(cnt)}</span>` : '';
    return `<span class="disc-preset-item"><button type="button" class="disc-preset${on ? ' is-active' : ''}" data-cand-preset="${p.id}" aria-pressed="${on ? 'true' : 'false'}"><span class="disc-preset-top"><span class="disc-preset-lbl">${escapeHtml(p.label)}</span>${cntHtml}</span><span class="disc-preset-desc">${escapeHtml(p.desc || '')}</span></button>${infoTip(p.tipTitle, p.tip, { compact: true })}</span>`;
  }).join('');
  const mine = saved.map((it) => {
    const on = currentHash && it.hash === currentHash;
    return `<button type="button" class="disc-saved${on ? ' is-active' : ''}" data-saved-apply="${escapeHtml(it.id)}" aria-pressed="${on ? 'true' : 'false'}" title="담은 조건 적용 — 이름 바꾸기·지우기는 내 목록 › 저장한 필터">★ ${escapeHtml(it.name)}</button>`;
  }).join('');
  return `
    <div class="disc-presets" role="group" aria-label="자주 쓰는 조건">
      <div class="disc-preset-list">${cards}</div>
      <div class="disc-saved-list"><span class="disc-saved-lbl">내 조건</span>${mine || '<span class="small muted">아직 없음 — 조건을 고른 뒤 ☆ 이 조건 담기</span>'}${saved.length ? '<a class="small disc-saved-manage" href="#/mine?tab=filters">관리</a>' : ''}</div>
    </div>`;
}

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
  if (appState.candCity) {
    chips.push({ key: 'city', label: `활동 도시: ${appState.candCity}`, removable: true });
  }
  if (appState.candTier) {
    chips.push({ key: 'tier', label: `가장 큰 무대 ≤ ${appState.candTier}`, removable: true });
  }
  if (appState.candGenreInf === 'exclude' && c.genre) {
    chips.push({ key: 'ginf', label: '추정 장르 빼기', removable: true });
  }
  if (appState.candQuery && appState.candQuery.trim()) {
    chips.push({ key: 'query', label: `검색: ${appState.candQuery.trim()}`, removable: true });
  }

  return chips;
}

const TIER_OPTIONS = [['S', 'S만 (~150명)'], ['M', 'M 이하 (~400명)'], ['L', 'L 이하 (~1,000명)']];

export function activePresetOf(appState) {
  return appState.candPreset
    || (Number(appState.candReleaseMonths) === 12 && !appState.candStage && !appState.candRegion ? 'debut12'
      : appState.candStage === '0' && !appState.candReleaseMonths && !appState.candRegion ? 'blank'
        : appState.candStage === '3' && !appState.candReleaseMonths && !appState.candRegion ? 'selected'
          : appState.candRegion === 'non_seoul' && !appState.candStage && !appState.candReleaseMonths ? 'regional'
            : '');
}

function optBtn(attr, value, label, cnt, active) {
  const cntHtml = cnt === null || cnt === undefined ? '' : `<span class="cf-opt-cnt">${typeof cnt === 'number' ? fmtInt(cnt) : escapeHtml(cnt)}</span>`;
  return `<button type="button" class="cf-opt-btn${active ? ' is-active' : ''}" ${attr}="${escapeHtml(value)}" aria-pressed="${active ? 'true' : 'false'}"><span>${escapeHtml(label)}</span>${cntHtml}</button>`;
}

function group(title, body, open = true, tipHtml = '') {
  return `<details class="dp-group"${open ? ' open' : ''}><summary class="dp-group-title">${escapeHtml(title)}${tipHtml}</summary><div class="dp-group-body">${body}</div></details>`;
}

/**
 * 발굴(#/discover) 필터 패널('+ 필터 추가'로 여닫음, 기본 닫힘) — 팀(장르·추정 장르·지역·도시) · 단계(발굴 단계·첫 발매 N개월) ·
 * 신호(갈래·가장 큰 무대 체급) · 변화(최근 활동·새로 들어옴/상승/예정 공연) · 세부 기준. 프리셋은 결과 위 프리셋 줄(renderPresetRowHtml).
 * 버튼·입력의 data-·id 는 예전 필터 줄과 같아 candidates.js 의 연결을 그대로 쓴다. 항목마다 해당 팀 수.
 */
export function renderCandPanelHtml({ appState, counts }) {
  const c = appState.cfg;

  const genres = [optBtn('data-set-genre', '', '전체 장르', counts.total, !c.genre),
    ...appState.validGenres.slice(0, 14).map(g => optBtn('data-set-genre', g, g, counts.genres.get(g) || 0, c.genre === g))].join('');
  const genreInf = `<label class="cf-crit-check dp-sub"><input type="checkbox" id="candGenreInfChk" ${appState.candGenreInf === 'exclude' ? '' : 'checked'} ${c.genre ? '' : 'disabled'}><span>추정 장르 팀도 포함${c.genre ? '' : ' (장르를 고르면)'}</span></label>`;
  const regionActive = appState.candRegion === 'non_seoul';
  const cityOpts = [...(counts.cities || new Map()).entries()].sort((a, b) => b[1] - a[1]);
  const citySel = counts.hasCityData
    ? `<select id="candCitySel" class="select dp-select" aria-label="활동 도시"><option value="">모든 도시</option>${cityOpts.map(([n, k]) => `<option value="${escapeHtml(n)}"${appState.candCity === n ? ' selected' : ''}>${escapeHtml(n)} (${fmtInt(k)})</option>`).join('')}</select>`
    : '<p class="small muted dp-sub">팀별 활동 도시 자료(team_cities.csv)가 아직 없습니다.</p>';
  const teamBody = `
    <div class="dp-label">장르</div><div class="cf-pop-opts cf-pop-scroll">${genres}</div>${genreInf}
    <div class="dp-label">지역</div><div class="cf-pop-opts">${optBtn('data-set-region', regionActive ? '' : 'non_seoul', '지방 씬 (서울 외)', counts.hasCityData ? counts.nonSeoul : '준비 중', regionActive)}</div>
    <div class="dp-label">활동 도시</div>${citySel}`;

  const stages = STAGE_ORDER.map(code => optBtn('data-stage-chip', String(code), `${STAGE_META[code].short}${code === 4 ? ' (기본 숨김)' : ''}`, counts.stages[code] || 0, appState.candStage === String(code))).join('');
  const releases = [optBtn('data-set-rm', '0', '전체', counts.total, !appState.candReleaseMonths),
    ...RELEASE_MONTH_OPTIONS.map(m => optBtn('data-set-rm', String(m), `${m}개월 이내`, counts.releaseMonths[m] || 0, Number(appState.candReleaseMonths) === m))].join('');
  const stageBody = `<div class="dp-label">발굴 단계${infoTip('발굴 단계', INFO_TIPS.discovery_stage, { compact: true })}</div><div class="cf-pop-opts">${stages}</div>
    <div class="dp-label">첫 발매 N개월</div><div class="cf-pop-opts">${releases}</div>`;

  const branches = ALL_BRANCHES.map(b => optBtn('data-branch-chip', b, b, counts.branches[b] || 0, c.branches.includes(b))).join('');
  const tiers = counts.hasLadder
    ? [optBtn('data-set-tier', '', '체급 상관없음', counts.total, !appState.candTier),
      ...TIER_OPTIONS.map(([t, lbl]) => optBtn('data-set-tier', t, lbl, counts.tiers?.[t] ?? 0, appState.candTier === t))].join('')
    : '<p class="small muted">공연장 체급 사다리 자료(venue_ladder.json)가 아직 없습니다.</p>';
  const signalBody = `<div class="dp-label">신호 갈래</div><div class="cf-pop-opts">${branches}</div>
    <div class="dp-label">가장 큰 무대 체급</div><div class="cf-pop-opts">${tiers}</div>
    <p class="small muted dp-sub">체급을 모르는 공연장만 선 팀은 체급을 고르면 빠집니다</p>`;

  const moves = [['new', '새로 들어옴'], ['riser', '상승'], ['upcoming', '예정 공연']]
    .map(([k, lbl]) => optBtn('data-move-chip', k, lbl, counts.moves[k] || 0, appState.candMove === k)).join('');
  const periodSel = `<select id="candPeriodSel" class="select dp-select" aria-label="최근 활동 기간">
      ${[[0, '전체 기간 (3년)'], [30, '최근 30일'], [90, '최근 90일'], [180, '최근 180일'], [365, '최근 365일']].map(([v, l]) => `<option value="${v}" ${Number(c.period_days) === v ? 'selected' : ''}>${l}</option>`).join('')}
    </select>`;
  const changeBody = `<div class="dp-label">최근 활동 (마지막 신호)</div>${periodSel}
    <div class="dp-label">변화</div><div class="cf-pop-opts">${moves}</div>
    <p class="small muted dp-sub">'떠오르는 팀'은 위 프리셋 줄에 있습니다</p>`;

  const criteriaBody = `<div class="cf-pop-criteria">
      <label class="cf-crit-row"><span>신인 기준(년)</span><input type="number" id="candNewcomerInp" class="input input-num" min="1" max="15" value="${c.newcomer_years}"></label>
      <label class="cf-crit-check"><input type="checkbox" id="candExcludeFamous" ${c.exclude_famous ? 'checked' : ''}><span>유명 팀 제외</span></label>
      <label class="cf-crit-check"><input type="checkbox" id="candOnlyNoOutcome" ${c.only_no_outcome ? 'checked' : ''}><span>${escapeHtml(TERMS.priorOutcome)} 팀 제외</span></label>
      <label class="cf-crit-row"><span>조회 상한</span><select id="candLimitSel" class="select" aria-label="조회 상한">${[50, 100, 200].map(n => `<option value="${n}" ${c.limit === n ? 'selected' : ''}>${n}팀</option>`).join('')}</select></label>
    </div>`;

  return `
    ${group('팀', teamBody)}
    ${group('단계', stageBody)}
    ${group('신호', signalBody)}
    ${group('변화', changeBody)}
    ${group('세부 기준', criteriaBody, false)}
    <p class="small muted dp-foot">조건은 주소에 남습니다 · 발굴 단계 4(졸업)는 기본 숨김</p>`;
}

/** 발굴 결과 위 줄 — [+ 필터 추가](패널 여닫기) · 검색 · 보기 [표 | 색 지도] · 조건 꼬리표(ⓧ) · 모두 지우기 */
export function renderCandResultsBarHtml({ appState, panelOpen = false }) {
  const activeChips = buildActiveFilterChips(appState);
  const removableCount = activeChips.filter(ch => ch.removable).length;
  const isHeat = appState.candView === 'heat';
  const chipsHtml = activeChips.map(ch => (ch.removable
    ? `<span class="cf-chip" data-chip-key="${escapeHtml(ch.key)}"><span>${escapeHtml(ch.label)}</span><button type="button" class="cf-chip-x" data-remove-filter="${escapeHtml(ch.key)}" aria-label="${escapeHtml(ch.label)} 필터 지우기">×</button></span>`
    : `<span class="cf-chip is-derived" title="프리셋에 포함된 조건입니다">${escapeHtml(ch.label)}</span>`)).join('');
  return `
    <div class="dr-bar">
      <button type="button" class="btn btn-sm dr-filter-toggle${panelOpen ? ' is-active' : ''}" id="candMobileFilterToggle" aria-controls="candPanel" aria-expanded="${panelOpen ? 'true' : 'false'}">${panelOpen ? '필터 닫기 ▴' : '+ 필터 추가 ▾'}${removableCount ? ` <span class="cf-count-num">${removableCount}</span>` : ''}</button>
      <input type="search" id="candFilterInput" class="input dr-search" value="${escapeHtml(appState.candQuery || '')}" placeholder="팀·장르·이유 검색..." aria-label="결과 안에서 팀 검색">
      <div class="cf-view-switch" role="group" aria-label="보기 전환">
        <button type="button" class="cf-view-btn${isHeat ? '' : ' is-active'}" data-cand-view="" aria-pressed="${isHeat ? 'false' : 'true'}">표</button>
        <button type="button" class="cf-view-btn${isHeat ? ' is-active' : ''}" data-cand-view="heat" aria-pressed="${isHeat ? 'true' : 'false'}" title="팀 × 신호 8개를 진하기(1~5단계)로 보기">색 지도</button>
      </div>
    </div>
    ${chipsHtml ? `<div class="cf-chips dr-chips" aria-label="적용된 조건">${chipsHtml}${removableCount > 0 ? '<button type="button" class="cf-clear-btn" data-action="reset-filters">모두 지우기</button>' : ''}</div>` : ''}`;
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
      return `<span class="rank-delta is-up" title="${escapeHtml(`${tipPrefix}: 상위 300 밖에서 ${curRank}위로 신규 진입`)}">새로</span>`;
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
