// 화면 점검 경로 목록 (tests/e2e/route_check.mjs 가 읽는다 · tests/js/e2e_routes.test.mjs 가 검사)
// 문자열 = 주소(#/ 뒤)만, 객체 = { route, label, act } — 화면이 뜬 뒤 act(페이지 안 식)를 실행하고 다시 잰다.

export const ROUTES = [
  'home', 'discover', 'charts', 'venues', 'cities', 'festivals', 'alerts', 'mine',
  'verify/backtest', 'verify/signals', 'verify/evidence', 'verify/scorecard', 'verify/grades', 'verify/quality', 'verify/sql',
  `team/${encodeURIComponent('포져군단')}`,
  `compare?teams=${encodeURIComponent('포져군단')},pcr`,
  // 2026-11-28 추가: 씬 네트워크(캔버스) · 공연장 전후 흐름 탭 · 도시 지도 시·도 확대
  'venues/network',
  `venue/${encodeURIComponent('Club FF')}/flow`,
  {
    route: 'cities',
    label: 'cities(확대)',
    act: "(() => { const b = document.querySelector('[data-sido-row]'); if (b) b.click(); return Boolean(b); })()",
  },
];

export const WIDTHS = [1280, 1920, 375];
export const THEMES = ['light', 'dark'];

/** 주소 부분 (#/ 뒤) */
export function routeHash(r) {
  return typeof r === 'string' ? r : r.route;
}

/** 결과 줄에 찍을 이름 */
export function routeLabel(r) {
  if (typeof r === 'object' && r.label) return r.label;
  return decodeURIComponent(routeHash(r));
}

/** 점검 칸 수 = 경로 × 폭 × 테마 */
export function cellCount() {
  return ROUTES.length * WIDTHS.length * THEMES.length;
}
