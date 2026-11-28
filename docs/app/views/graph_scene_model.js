// 씬 네트워크(graph_scene.js)의 순수 계산 — 브라우저 없이 돈다 (tests/js/graph_scene.test.mjs)

const R_MIN = 5.5;
const R_SPAN = 10.5;
const SEARCH_LIMIT = 8;

/** 점수 → 반지름 (그 화면 안 최저~최고 점수 기준) */
export function sceneRadius(score, minScore, maxScore) {
  const span = Math.max(0.5, (Number(maxScore) || 0) - (Number(minScore) || 0));
  const norm = Math.max(0, Math.min(1, ((Number(score) || 0) - (Number(minScore) || 0)) / span));
  return R_MIN + Math.pow(norm, 0.85) * R_SPAN;
}

/** 'winner' = 이미 수상·선정된 팀, 'cand' = 신인 후보 */
export function roleOf(node) {
  return node?.had_outcome ? 'winner' : 'cand';
}

export function isHiddenNode(node, hiddenRoles) {
  return Boolean(hiddenRoles?.has(roleOf(node)));
}

/** 역할별 팀 수 */
export function roleCounts(nodes) {
  const out = new Map([['cand', 0], ['winner', 0]]);
  for (const n of nodes || []) out.set(roleOf(n), out.get(roleOf(n)) + 1);
  return out;
}

/**
 * 밝게 보일 팀 묶음. 올린 팀 > 고른 팀 > 고른 씬 묶음. 없으면 null.
 * @returns {{ focusId: string|null, set: Set<string> } | null}
 */
export function sceneFocusSet({ hoveredId, selectedId, activeCommId, nodes, adjMap, nodeById, hiddenRoles }) {
  const visible = n => n && !isHiddenNode(n, hiddenRoles);
  const focusId = [hoveredId, selectedId].find(id => id && visible(nodeById?.get(id))) || null;
  if (focusId) {
    const set = new Set([focusId]);
    for (const item of adjMap?.get(focusId) || []) {
      if (visible(item.neighbor)) set.add(item.neighbor.id);
    }
    return { focusId, set };
  }
  if (activeCommId !== null && activeCommId !== undefined) {
    return { focusId: null, set: new Set((nodes || []).filter(n => n.communityId === activeCommId && visible(n)).map(n => n.id)) };
  }
  return null;
}

/** 그림 안 팀 찾기: 이름 앞글자 일치 먼저, 그다음 점수 순 */
export function matchTeams(nodes, query, limit = SEARCH_LIMIT) {
  const q = String(query || '').trim().toLowerCase();
  if (!q) return [];
  return (nodes || [])
    .filter(n => String(n.display_name || '').toLowerCase().includes(q) || String(n.team_key || '').toLowerCase().includes(q))
    .sort((a, b) => {
      const as = String(a.display_name || '').toLowerCase().startsWith(q) ? 0 : 1;
      const bs = String(b.display_name || '').toLowerCase().startsWith(q) ? 0 : 1;
      return (as - bs) || ((Number(b.score) || 0) - (Number(a.score) || 0));
    })
    .slice(0, limit);
}

/** 라벨을 먼저 붙일 순서 — 점수·연결 수·수상 여부 */
export function sceneLabelPriority(node) {
  return (Number(node?.score) || 0) * 4 + (Number(node?.degree) || 0) * 1.2 + (node?.had_outcome ? 10 : 0);
}
