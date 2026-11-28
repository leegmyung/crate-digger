// 관계망 그림의 순수 계산 (브라우저·D3 없이 돈다 — tests/js/graph_model.test.mjs)
// 원리(Chartmetric·Obsidian 그래프): 크기 = 중요도, 색 = 종류, 선 굵기 = 같은 무대 횟수,
// 라벨은 확대 수준에 맞춰 중요한 것부터, 겹치면 숨김.

/** 관계 종류 (필터 칩 = 범례 순서). key 는 relationKindOf() 결과 */
export const REL_KINDS = [
  { key: 'co_stage', nodeType: 'team' },
  { key: 'agency', nodeType: 'agency' },
  { key: 'venue', nodeType: 'venue' },
  { key: 'outcome', nodeType: 'outcome' },
  { key: 'program', nodeType: 'program' },
  { key: 'outlet', nodeType: 'outlet' },
  { key: 'scene', nodeType: 'scene' },
];

const KIND_KEYS = new Set(REL_KINDS.map(k => k.key));

/** 행의 relation → 관계 종류 key */
export function relationKindOf(relation) {
  if (relation === 'same_agency') return 'agency';
  return KIND_KEYS.has(relation) ? relation : 'other';
}

const RANK_FLOOR = 5000; // 이 순위보다 아래는 중요도 바닥
const GRADE_IMPORTANCE = { S: 1, A: 0.72, B: 0.45 };

function clamp01(v) {
  return Math.max(0, Math.min(1, v));
}

/**
 * 노드 중요도 0~1. 팀 = 오늘 점수 순위(로그), 정답 = 등급, 공연장·출처 = 횟수.
 * @param {{ node_type: string, grade?: string, maxWeight?: number }} node
 * @param {{ rank?: number, score?: number } | null} [scoreInfo] 오늘 점수 스냅샷 (팀만)
 */
export function importanceOf(node, scoreInfo = null) {
  const type = node?.node_type;
  if (type === 'ego') return 1;
  if (type === 'team') {
    const rank = Number(scoreInfo?.rank);
    if (Number.isFinite(rank) && rank >= 1) {
      return clamp01(0.12 + 0.88 * (1 - Math.log10(rank) / Math.log10(RANK_FLOOR)));
    }
    return 0.04;
  }
  if (type === 'outcome') return GRADE_IMPORTANCE[String(node.grade || '').toUpperCase()] ?? 0.35;
  const w = Math.max(1, Number(node?.maxWeight) || 1);
  return clamp01(0.15 + Math.sqrt(w - 1) * 0.12);
}

/** 노드 반지름 (그림 좌표 px). importance 는 importanceOf() 값 */
export function nodeRadiusFor(node) {
  const imp = clamp01(Number(node?.importance) || 0);
  switch (node?.node_type) {
    case 'ego': return 30;
    case 'team': return 10.5 + imp * 13;
    case 'outcome': return 10 + imp * 6;
    case 'agency': return 10;
    case 'scene': return 11;
    case 'venue': return 7 + imp * 6;
    case 'program': return 8 + imp * 3;
    default: return 7 + imp * 3; // outlet
  }
}

/** 선 굵기: 같은 무대 = 횟수, 공연장 = 공연 횟수, 나머지는 가는 선 */
export function edgeWidthFor(link) {
  const w = Math.max(1, Number(link?.weight) || 1);
  if (link?.relation === 'co_stage') return Math.min(7, 1.1 + Math.sqrt(w - 1) * 1.2);
  if (link?.relation === 'venue') return Math.min(3.4, 0.9 + Math.sqrt(w - 1) * 0.55);
  if (link?.relation === 'outcome') return 1.6;
  return 1.2;
}

/** 확대 배율 k 에서 보일 라벨 수 */
export function labelBudget(k, total) {
  const n = Math.max(0, Number(total) || 0);
  let budget;
  if (k < 0.6) budget = 8;
  else if (k < 1.05) budget = 28;
  else if (k < 1.5) budget = 60;
  else if (k < 2.2) budget = 120;
  else budget = n;
  return Math.min(n, budget);
}

/** 확대해도 화면 글자가 배율만큼 커지지 않게: 그림 좌표 글자 크기 */
export function labelFontSize(base, k) {
  const kk = Math.max(0.2, Number(k) || 1);
  return base * Math.pow(kk, -0.72);
}

const WIDE_CHAR = /[ᄀ-ᇿ　-鿿가-힯＀-￯]/;

/** 라벨 글자 폭 추정 (화면 px) — 겹침 계산용 */
export function estimateLabelWidth(text, fontSize) {
  let w = 0;
  for (const ch of String(text || '')) w += WIDE_CHAR.test(ch) ? 0.95 : 0.56;
  return w * fontSize;
}

function overlaps(a, b) {
  return !(a.x1 < b.x0 || a.x0 > b.x1 || a.y1 < b.y0 || a.y0 > b.y1);
}

/**
 * 겹치지 않게 보일 라벨을 고른다. 고정(pinned)은 늘 보이고 먼저 자리를 잡는다.
 * @param {Array<{id: string, x: number, y: number, w: number, h: number, priority: number}>} items x,y = 라벨 가운데 위
 * @param {{ budget: number, pinned?: Set<string>, pad?: number }} opts
 * @returns {Set<string>}
 */
export function pickVisibleLabels(items, { budget, pinned = new Set(), pad = 3 } = {}) {
  const box = it => ({ x0: it.x - it.w / 2 - pad, x1: it.x + it.w / 2 + pad, y0: it.y - pad, y1: it.y + it.h + pad });
  const placed = [];
  const on = new Set();
  for (const it of items) {
    if (!pinned.has(it.id)) continue;
    placed.push(box(it));
    on.add(it.id);
  }
  const rest = items.filter(it => !pinned.has(it.id)).sort((a, b) => b.priority - a.priority);
  let used = 0;
  for (const it of rest) {
    if (used >= budget) break;
    const b = box(it);
    if (placed.some(p => overlaps(p, b))) continue;
    placed.push(b);
    on.add(it.id);
    used += 1;
  }
  return on;
}

const endId = v => (v && typeof v === 'object' ? v.id : v);

/** 이웃 표: id → Set(이웃 id) */
export function buildAdjacency(links) {
  const adj = new Map();
  const add = (a, b) => {
    if (!adj.has(a)) adj.set(a, new Set());
    adj.get(a).add(b);
  };
  for (const l of links || []) {
    const s = endId(l.source);
    const t = endId(l.target);
    add(s, t);
    add(t, s);
  }
  return adj;
}

/**
 * 숨긴 관계 종류를 빼고, 중심(egoId)에서 이어지는 노드만 남긴다.
 * @returns {{ nodes: object[], links: object[] }}
 */
export function filterGraph(nodes, links, hiddenKinds, egoId) {
  const hidden = hiddenKinds || new Set();
  const shownLinks = (links || []).filter(l => !hidden.has(relationKindOf(l.relation)));
  const adj = buildAdjacency(shownLinks);
  const reach = new Set([egoId]);
  const queue = [egoId];
  while (queue.length) {
    const cur = queue.shift();
    for (const nb of adj.get(cur) || []) {
      if (reach.has(nb)) continue;
      reach.add(nb);
      queue.push(nb);
    }
  }
  return {
    nodes: (nodes || []).filter(n => reach.has(n.id)),
    links: shownLinks.filter(l => reach.has(endId(l.source)) && reach.has(endId(l.target))),
  };
}

/**
 * SQL 한 행 → 그림에 더할 노드·선. 같은 소속사 팀은 '소속사' 노드를 거쳐 잇는다(부모 — 소속사 — 팀).
 * 노드는 기본 칸만 채운다(사진·점수는 그리는 쪽에서).
 * @returns {{ nodes: object[], links: Array<{source: string, target: string, relation: string, weight: number, detail: string}> }}
 */
export function rowToGraphParts(parent, row) {
  const empty = { nodes: [], links: [] };
  if (!parent || !row || !row.node_id) return empty;
  const id = String(row.node_id);
  if (id === parent.id) return empty;
  const relation = row.relation || row.node_type || 'co_stage';
  const weight = Math.max(1, Number(row.weight) || 1);
  const detail = String(row.detail || '');
  const node = {
    id,
    node_type: row.node_type || 'team',
    node_key: String(row.node_key || ''),
    label: String(row.label || row.node_key || ''),
    detail,
    grade: String(row.grade || ''),
    role: String(row.role || ''),
    last_date: row.last_date ? String(row.last_date).slice(0, 10) : '',
    primary_genre: String(row.primary_genre || ''),
    maxWeight: weight,
  };
  const agencyName = relation === 'same_agency' ? detail.trim() : '';
  if (agencyName) {
    const agencyId = `agency:${agencyName}`;
    const agency = {
      id: agencyId, node_type: 'agency', node_key: agencyName, label: agencyName,
      detail: '', grade: '', role: '', last_date: '', primary_genre: '', maxWeight: 1,
    };
    return {
      nodes: [agency, node],
      links: [
        { source: parent.id, target: agencyId, relation, weight: 1, detail: agencyName },
        { source: agencyId, target: id, relation, weight: 1, detail: agencyName },
      ],
    };
  }
  return { nodes: [node], links: [{ source: parent.id, target: id, relation, weight, detail }] };
}

const KIND_ORDER = new Map(REL_KINDS.map((k, i) => [k.key, i]));

/** 관계 종류 순서 (같은 무대 → 소속사 → 공연장 → … → 씬). 목록 정렬용 */
export function kindOrder(relation) {
  const kind = relationKindOf(relation);
  return KIND_ORDER.has(kind) ? KIND_ORDER.get(kind) : REL_KINDS.length;
}

/** 라벨 우선순위: 팀 > 그 밖, 중요도·1단계 이웃·연결 수 */
export function labelPriority(node, degree = 0) {
  const typeBonus = node?.node_type === 'team' ? 40 : 0;
  return (Number(node?.importance) || 0) * 100 + typeBonus + (node?.depth === 1 ? 15 : 0) + degree;
}

/** 길면 말줄임 */
export function shortLabel(text, maxLen = 14) {
  const s = String(text || '').trim();
  return s.length > maxLen ? `${s.slice(0, maxLen - 1)}…` : s;
}
