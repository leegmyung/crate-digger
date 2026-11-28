/**
 * 상세 화면(팀·공연장)의 '← 온 곳으로' 단추 (docs/ux_simplify_2026-11-28.md ⑨).
 * 앱 안에서 온 화면이면 그 화면 이름을 붙이고 브라우저 뒤로 가기로 돌아간다 — 발굴 필터·스크롤이 담긴 주소를 그대로 되살림.
 * 주소로 바로 열었거나(이전 화면 없음) 같은 종류 화면에서 왔으면 기본 화면으로 이동한다.
 */

const PARAM_ROUTES = new Set(['team', 'venue']);

/**
 * @param {{ prevRoute?: string|null, prevParam?: string, selfRoute: string, fallbackRoute: string,
 *           label: (route: string) => string|null }} p
 * @returns {{ route: string, param: string, label: string, useHistory: boolean }}
 */
export function backTarget({ prevRoute = null, prevParam = '', selfRoute, fallbackRoute, label }) {
  const fromApp = Boolean(prevRoute && prevRoute !== selfRoute && label(prevRoute));
  const route = fromApp ? prevRoute : fallbackRoute;
  return {
    route,
    param: fromApp && PARAM_ROUTES.has(route) ? String(prevParam || '') : '',
    label: label(route) || label(fallbackRoute) || '',
    useHistory: fromApp,
  };
}
