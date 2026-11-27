// 아직 화면이 없는 새 주소의 자리 (정보 구조 v2 묶음 A — docs/app_structure_v2.md).
// 차트(갓 데뷔 말고)·알림·검색은 다음 묶음(F·G·B)에서 이 자리를 진짜 화면으로 바꾼다.
// 그동안은 지금 있는 화면으로 가는 길만 알려 준다 (빈 화면으로 두지 않기).
import { appState } from '../state.js';
import { escapeHtml } from '../ui.js';

const CHART_LABELS = {
  all: '전체 순위',
  genre: '장르별',
  city: '도시별',
  rising: '떠오르는 팀',
  debut: '갓 데뷔',
};

function chartsHtml() {
  const kind = appState.chartKind || 'all';
  const param = appState.chartParam ? ` · ${escapeHtml(appState.chartParam)}` : '';
  const links = Object.entries(CHART_LABELS).map(([k, label]) => {
    const href = k === 'all' ? '#/charts' : `#/charts/${k}`;
    const cur = k === kind ? ' aria-current="page"' : '';
    return `<a class="btn" href="${href}"${cur}>${escapeHtml(label)}</a>`;
  }).join(' ');
  return `
    <h1 class="view-title">차트 — ${escapeHtml(CHART_LABELS[kind] || kind)}${param}</h1>
    <p class="muted">정의가 정해진 순위표 묶음입니다. 지금은 <strong>갓 데뷔</strong>만 열 수 있고, 나머지는 준비 중이에요.</p>
    <nav class="placeholder-links" aria-label="차트 종류">${links}</nav>
    <p class="muted small">비슷한 목록은 지금도 <a href="#/discover?preset=rising">발굴 — 떠오르는 팀 프리셋</a>이나
      <a href="#/discover">발굴 전체</a>에서 볼 수 있어요.</p>`;
}

function alertsHtml() {
  return `
    <h1 class="view-title">알림</h1>
    <p class="muted">받은 알림과 알림 규칙(저장 필터·공연장 구독)을 한곳에 모을 화면이에요. 준비 중입니다.</p>
    <p><a class="btn btn-primary" href="#/home">홈의 이번 주 알림 보기</a>
       <a class="btn" href="#/mine">내 목록(관심 팀·구독)</a></p>`;
}

function searchHtml() {
  const q = appState.searchQuery || '';
  return `
    <h1 class="view-title">검색${q ? ` — "${escapeHtml(q)}"` : ''}</h1>
    <p class="muted">팀·공연장·도시·페스티벌을 한 번에 찾는 결과 화면이에요. 준비 중입니다.
      지금은 위쪽 검색창에서 팀 이름으로 찾을 수 있어요.</p>`;
}

const RENDERERS = { charts: chartsHtml, alerts: alertsHtml, search: searchHtml };

export async function renderPlaceholderView(root) {
  const fn = RENDERERS[appState.route] || (() => '<p class="muted">준비 중인 화면이에요.</p>');
  root.innerHTML = `<section class="placeholder-view" data-placeholder="${escapeHtml(appState.route)}">${fn()}</section>`;
}
