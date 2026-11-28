// 화면 바꾸기 도우미 (app.js renderCurrentView) — 순수 함수, tests/js/render_guard.test.mjs

/**
 * '불러오는 중' 뼈대를 지금 그려도 되나.
 * 화면 함수가 이미 자기 틀(예: <div id="venueListHost">)을 그렸으면 덮지 않는다 — 덮으면 나중에 받은 자료가
 * 떨어져 나간 칸에 그려져 화면이 영영 뼈대로 남는다 (느린 망에서 #/venues, 2026-11-28).
 * @param {{ pending: string|undefined, seq: number, current: number, startNode: object|null, firstNode: object|null }} s
 *   pending = root.dataset.skelPending, seq = 이 그리기 번호, current = 지금 그리기 번호,
 *   startNode = 그리기 시작할 때 root 의 첫 요소, firstNode = 지금 root 의 첫 요소
 */
export function skeletonAllowed({ pending, seq, current, startNode, firstNode }) {
  if (seq !== current) return false;
  if (pending !== String(seq)) return false;
  return firstNode === startNode;
}
