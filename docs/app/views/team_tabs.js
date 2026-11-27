// 팀 페이지 탭 (정보 구조 v2 묶음 C — docs/app_structure_v2.md 2-3)
// 고정 머리(team.js) 아래 탭 7개. 주소 #/team/<키>/<탭>. 탭을 바꾸면 그 자리에서 칸만 바꾸고 주소는 pushState(뒤로 가기 가능).
import { appState, buildHashUrl, TEAM_TABS } from '../state.js';
import { escapeHtml } from '../ui.js';

/** 탭 정의: 이름 · 근거 줄(검증 쪽 링크) */
export const TEAM_TAB_DEFS = {
  overview: {
    label: '개요',
    evidence: [['데이터 수집·품질', '#/verify/quality'], ['점수 신뢰도', '#/verify/backtest']],
    note: '상태 막대·변화는 기준일 전 신호만 씀',
  },
  score: {
    label: '점수',
    evidence: [['점수 신뢰도·백테스트', '#/verify/backtest'], ['출처 성적표', '#/verify/scorecard']],
    note: '점수는 검증된 발굴 출처만, 공연장 수는 최근 2년',
  },
  events: {
    label: '사건',
    evidence: [['신호 원본', '#/verify/signals'], ['정답·근거', '#/verify/evidence']],
    note: '별점은 그때 작은 팀일수록 높음(점수 미반영)',
  },
  gigs: {
    label: '공연',
    evidence: [['공연 근거', '#/verify/evidence'], ['공연장 체급 출처·수집 상태', '#/verify/quality']],
    note: '공연은 인디스트릿·상상마당·인디고·공연장 인스타 기록',
  },
  network: {
    label: '관계',
    evidence: [['정답(수상) 근거', '#/verify/evidence'], ['출처 성적표', '#/verify/scorecard']],
    note: '같은 무대·같은 소속사 연결 — 같은 집안 정답은 검증에서 뺌',
  },
  videos: {
    label: '영상',
    evidence: [['수집 상태', '#/verify/quality']],
    note: '무대 영상·채널은 연결된 계정 기준',
  },
  precedents: {
    label: '선례',
    evidence: [['점수 신뢰도·백테스트', '#/verify/backtest'], ['정답 근거', '#/verify/evidence']],
    note: '같은 경로였던 과거 수상 팀 — 예측이 아니라 참고',
  },
};

export function activeTeamTab() {
  return TEAM_TABS.includes(appState.teamTab) ? appState.teamTab : 'overview';
}

/** 탭 줄 (기존 '쪽 안 목차' 자리). counts: { videos: n, ... } 는 이름 옆 숫자 */
export function renderTeamTabsHtml(teamKey, active, counts = {}) {
  const base = `#/team/${encodeURIComponent(teamKey)}`;
  const links = TEAM_TABS.map(tab => {
    const def = TEAM_TAB_DEFS[tab];
    const on = tab === active;
    const href = tab === 'overview' ? base : `${base}/${tab}`;
    const n = counts[tab];
    return `<a class="team-toc-link team-tab${on ? ' is-active' : ''}" role="tab" id="teamTab-${tab}"
      href="${escapeHtml(href)}" data-team-tab="${tab}" aria-selected="${on ? 'true' : 'false'}"
      aria-controls="teamPanel-${tab}" tabindex="${on ? '0' : '-1'}">${escapeHtml(def.label)}${n ? ` <span class="team-tab-n">${n}</span>` : ''}</a>`;
  }).join('');
  return `<nav class="team-toc team-tabs" id="teamTabs" role="tablist" aria-label="팀 페이지 탭">${links}</nav>`;
}

/** 탭 칸 하나: 내용 + 근거 줄 */
export function teamPanelHtml(tab, active, innerHtml) {
  const def = TEAM_TAB_DEFS[tab];
  const ev = def.evidence.map(([label, href]) => `<a href="${escapeHtml(href)}">${escapeHtml(label)}</a>`).join(' · ');
  return `
    <div class="team-tabpanel" id="teamPanel-${tab}" role="tabpanel" aria-labelledby="teamTab-${tab}" data-team-panel="${tab}"${tab === active ? '' : ' hidden'}>
      ${innerHtml}
      <p class="team-evidence-line">근거: ${escapeHtml(def.note)} — ${ev}</p>
    </div>`;
}

/**
 * 탭 바꾸기를 연결한다. onShow(tab) 은 탭이 처음 보일 때 한 번 (관계망 그림처럼 숨은 칸에서 그리면 크기가 틀리는 것용).
 * @returns {{ show: (tab: string) => void }}
 */
export function wireTeamTabs(root, onShow) {
  const nav = root.querySelector('#teamTabs');
  const shown = new Set();
  // 탭 띠를 위쪽 고정 머리 바로 아래에 붙인다 (예전 쪽 안 목차와 같은 방식)
  const header = document.querySelector('.top-header');
  if (header && getComputedStyle(header).position === 'sticky') {
    root.style.setProperty('--team-toc-top', `${Math.round(header.getBoundingClientRect().height)}px`);
  }
  function show(tab, { push = true, focus = false } = {}) {
    if (!TEAM_TABS.includes(tab)) return;
    appState.teamTab = tab;
    root.querySelectorAll('[data-team-panel]').forEach(p => { p.hidden = p.dataset.teamPanel !== tab; });
    nav?.querySelectorAll('[data-team-tab]').forEach(a => {
      const on = a.dataset.teamTab === tab;
      a.classList.toggle('is-active', on);
      a.setAttribute('aria-selected', on ? 'true' : 'false');
      a.setAttribute('tabindex', on ? '0' : '-1');
      if (on && focus) a.focus();
    });
    if (push) {
      const next = buildHashUrl();
      if (window.location.hash !== next) {
        try { window.history.pushState(null, '', next); } catch (_) { /* 주소를 못 바꿔도 탭은 바뀜 */ }
      }
    }
    if (!shown.has(tab)) {
      shown.add(tab);
      onShow?.(tab);
    }
  }
  nav?.addEventListener('click', e => {
    const a = e.target.closest('[data-team-tab]');
    if (!a || e.metaKey || e.ctrlKey || e.shiftKey) return;
    e.preventDefault();
    show(a.dataset.teamTab);
  });
  nav?.addEventListener('keydown', e => {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft' && e.key !== 'Home' && e.key !== 'End') return;
    e.preventDefault();
    const i = TEAM_TABS.indexOf(activeTeamTab());
    const n = TEAM_TABS.length;
    const next = e.key === 'Home' ? 0 : e.key === 'End' ? n - 1 : (i + (e.key === 'ArrowRight' ? 1 : -1) + n) % n;
    show(TEAM_TABS[next], { focus: true });
  });
  show(activeTeamTab(), { push: false });
  return { show };
}
