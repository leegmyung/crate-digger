// 팀 관계망(graph.js)의 옆 패널·말풍선·필터 칩 HTML. 화면 그리기·D3 는 graph.js.
import {
  avatarHtml, escapeHtml, fmtInt, fmtNum, josa, playButtonHtml, ROLE_META, roleBadgeHtml, TERMS,
} from '../ui.js';
import { endId, kindOrder, REL_KINDS, relationKindOf } from './graph_model.js';

/** 관계 종류 이름 (필터 칩 = 범례) */
export const KIND_LABELS = {
  co_stage: '같은 무대',
  agency: '소속사',
  venue: '공연장',
  outcome: TERMS.outcome,
  program: '선정·지원',
  outlet: TERMS.outlet,
  scene: '씬 묶음',
};

/** 노드 종류 이름 */
export const TYPE_LABELS = {
  ego: '이 팀',
  team: '팀',
  agency: '소속사',
  venue: '공연장',
  outcome: TERMS.outcome,
  program: '선정·지원',
  outlet: TERMS.outlet,
  scene: '씬 묶음',
};

const NEIGHBOR_LIST_MAX = 8;

/** 출처 노드의 쓰임(ROLE_META 키) — 점수에 안 쓰는 출처 표시용 */
export function nodeSignalRole(node) {
  if (!node || (node.node_type !== 'program' && node.node_type !== 'outlet')) return '';
  const r = String(node.role || node.detail || '').trim();
  return ROLE_META[r] ? r : '';
}

export function isUnscoredSourceNode(node) {
  const r = nodeSignalRole(node);
  return r === 'pending' || r === 'excluded';
}

/** 선 하나 설명: '같은 무대 6번' · '공연장 12번' · '소속사' */
export function describeLink(l) {
  const rels = Array.isArray(l.relations) && l.relations.length ? l.relations : [l.relation];
  return rels.map(r => {
    const kind = relationKindOf(r);
    const label = KIND_LABELS[kind] || r;
    if (r === 'co_stage' && l.weight > 0) return `${label} ${fmtInt(Math.round(l.weight))}번`;
    if (r === 'venue' && l.weight > 0) return `공연 ${fmtInt(Math.round(l.weight))}번`;
    return label;
  }).join(' · ');
}

/** 필터 칩 (= 색 범례). counts: kind → 노드 수 */
export function filterChipsHtml(counts, hiddenKinds) {
  return REL_KINDS
    .filter(k => counts.get(k.key))
    .map(k => {
      const on = !hiddenKinds.has(k.key);
      return `<button type="button" class="rg-chip k-${k.key}${on ? '' : ' is-off'}" data-rg-kind="${k.key}" aria-pressed="${on}"
        title="${escapeHtml(KIND_LABELS[k.key])} ${on ? '숨기기' : '보이기'}"><i class="rg-dot" aria-hidden="true"></i>${escapeHtml(KIND_LABELS[k.key])}<span class="rg-chip-n">${fmtInt(counts.get(k.key))}</span></button>`;
    }).join('');
}

/** 마우스 올렸을 때 말풍선 */
export function tooltipHtml(node, linkToEgo) {
  const typeLbl = TYPE_LABELS[node.node_type] || node.node_type;
  const bits = [typeLbl];
  if (node.scoreInfo?.rank) bits.push(`오늘 ${fmtInt(node.scoreInfo.rank)}위`);
  if (node.node_type === 'outcome' && node.grade) bits.push(`${node.grade}등급`);
  if (linkToEgo) bits.push(describeLink(linkToEgo));
  else if (node.node_type === 'venue' && node.detail) bits.push(node.detail);
  const role = nodeSignalRole(node);
  const badge = isUnscoredSourceNode(node) ? roleBadgeHtml(role, { context: 'timeline', compact: true }) : '';
  return `<div class="gt-head"><strong>${escapeHtml(node.label)}</strong>${badge}</div><div class="gt-sub">${escapeHtml(bits.join(' · '))}</div>`;
}

function iconHtml(node) {
  if (node.node_type === 'team' || node.node_type === 'ego') {
    return avatarHtml(node.node_key, node.label, 52, { shape: 'circle', genre: node.primary_genre });
  }
  let glyph = '';
  if (node.node_type === 'outcome') glyph = String(node.grade || '').toUpperCase() || '상';
  else if (node.node_type === 'scene') glyph = `#${node.node_key}`;
  else if (node.node_type !== 'program') glyph = Array.from(String(node.label || '').trim())[0] || '';
  return `<span class="rg-p-icon t-${escapeHtml(node.node_type)}" aria-hidden="true">${escapeHtml(glyph)}</span>`;
}

function subLine(node, neighborCount) {
  const parts = [];
  if (node.primary_genre) parts.push(node.primary_genre);
  if (node.scoreInfo && Number.isFinite(Number(node.scoreInfo.score))) {
    parts.push(`점수 ${fmtNum(node.scoreInfo.score, 2)} · 오늘 ${fmtInt(node.scoreInfo.rank)}위`);
  }
  if (node.node_type === 'outcome' && node.grade) parts.push(`${node.grade}등급`);
  const role = nodeSignalRole(node);
  if (role && !isUnscoredSourceNode(node)) parts.push(ROLE_META[role].fullLabel);
  else if (!role && node.detail && node.node_type !== 'team' && node.node_type !== 'agency') parts.push(node.detail);
  if (node.node_type === 'agency') parts.push(`같은 소속사 ${fmtInt(Math.max(0, neighborCount - 1))}팀`);
  return parts.join(' · ');
}

function actionsHtml(node, { isEgo, expandState }) {
  const out = [];
  if (node.node_type === 'team' || node.node_type === 'ego') out.push(playButtonHtml(node.node_key, node.label, { variant: 'sm' }));
  if (node.node_type === 'team' && node.node_key && !isEgo) {
    out.push(`<a class="btn btn-sm btn-primary" href="#/team/${encodeURIComponent(node.node_key)}">팀 페이지 →</a>`);
  } else if (node.node_type === 'venue' && node.node_key) {
    out.push(`<a class="btn btn-sm btn-primary" href="#/venue/${encodeURIComponent(node.node_key)}">공연장 페이지 →</a>`);
  } else if (node.node_type === 'scene' && node.node_key) {
    out.push(`<button type="button" class="btn btn-sm btn-primary" data-rg-scene="${escapeHtml(node.node_key)}">씬 지도에서 보기 →</button>`);
  }
  if (!isEgo && node.node_type !== 'agency') {
    const label = expandState === 'loading' ? '불러오는 중…' : (expandState === 'done' ? '연결 펼침 ✓' : '연결 펼치기 +');
    out.push(`<button type="button" class="btn btn-sm" data-rg-expand="${escapeHtml(node.id)}"${expandState ? ' disabled' : ''}>${label}</button>`);
  }
  return out.join('');
}

function neighborsHtml(neighbors) {
  if (!neighbors.length) return '<p class="rg-p-empty">지금 그림 안에서 이어진 곳이 없습니다.</p>';
  const rows = neighbors.slice(0, NEIGHBOR_LIST_MAX).map(({ node, link }) => `
    <li><button type="button" class="rg-nb" data-rg-jump="${escapeHtml(node.id)}">
      <i class="rg-dot t-${escapeHtml(node.node_type)}" aria-hidden="true"></i>
      <span class="rg-nb-name">${escapeHtml(node.label)}</span>
      <span class="rg-nb-meta">${escapeHtml(describeLink(link))}</span>
    </button></li>`).join('');
  const more = neighbors.length > NEIGHBOR_LIST_MAX ? `<li class="rg-nb-more">외 ${fmtInt(neighbors.length - NEIGHBOR_LIST_MAX)}곳</li>` : '';
  return `<ul class="rg-nb-list">${rows}${more}</ul>`;
}

/** '포져군단과' · '산하와' — 받침에 맞는 조사 */
function egoWith(egoNode) {
  const full = josa(egoNode.label, '과', '와');
  return `<b>${escapeHtml(egoNode.label)}</b>${escapeHtml(full.slice(String(egoNode.label).length))}`;
}

function relationToEgoHtml(node, egoNode, linkToEgo) {
  if (!egoNode || node.id === egoNode.id) return '';
  if (!linkToEgo) {
    return `<p class="rg-p-rel">${egoWith(egoNode)} 바로 잇지는 않음 — 펼친 연결을 거쳐 이어짐</p>`;
  }
  if (linkToEgo.relation === 'venue' && linkToEgo.weight > 0) {
    const subj = josa(egoNode.label, '이', '가').slice(String(egoNode.label).length);
    return `<p class="rg-p-rel"><b>${escapeHtml(egoNode.label)}</b>${escapeHtml(subj)} 여기서 ${fmtInt(Math.round(linkToEgo.weight))}번 공연${node.last_date ? ` · <span class="rg-p-when">마지막 ${escapeHtml(node.last_date)}</span>` : ''}</p>`;
  }
  const when = node.last_date ? ` · <span class="rg-p-when">마지막 ${escapeHtml(node.last_date)}</span>` : '';
  const where = linkToEgo.relation === 'co_stage' && linkToEgo.detail ? `<span class="rg-p-where">${escapeHtml(linkToEgo.detail)}</span>` : '';
  return `<p class="rg-p-rel">${egoWith(egoNode)} ${escapeHtml(describeLink(linkToEgo))}${when}${where}</p>`;
}

const HOW_TO_READ = `
  <div class="rg-p-guide">
    <h4>읽는 법</h4>
    <ul>
      <li><i class="rg-key-size" aria-hidden="true"></i>동그라미 크기 = 오늘 점수 순위 (${escapeHtml(TERMS.outcome)}은 등급)</li>
      <li><i class="rg-key-line" aria-hidden="true"></i>선 굵기 = 같은 무대에 함께 선 횟수</li>
      <li><i class="rg-key-dash" aria-hidden="true"></i>점선 = 같은 소속사 · 씬 묶음</li>
      <li><i class="rg-key-color" aria-hidden="true"></i>색 = 종류 (위 칩을 누르면 숨김)</li>
    </ul>
    <p class="rg-p-tip">마우스를 올리면 이웃만 밝게 · 누르면 자세히 · 두 번 누르면 연결 펼치기 · 휠·두 손가락으로 확대</p>
  </div>`;

/**
 * 옆 패널 (좁은 화면에서는 아래 시트).
 * @param {{ node: object, egoNode: object, linkToEgo: object|null, neighbors: Array<{node: object, link: object}>,
 *           isSelected: boolean, expandState: ''|'loading'|'done', statusNote?: string }} p
 */
export function panelHtml({ node, egoNode, linkToEgo, neighbors, isSelected, expandState, statusNote = '' }) {
  if (!node) return '';
  const isEgo = node.id === egoNode?.id;
  const role = nodeSignalRole(node);
  const badge = isUnscoredSourceNode(node) ? roleBadgeHtml(role, { context: 'timeline', compact: true }) : '';
  const sub = subLine(node, neighbors.length);
  return `
    <div class="rg-p-grip" aria-hidden="true"></div>
    <div class="rg-p-head">
      ${iconHtml(node)}
      <div class="rg-p-title">
        <span class="rg-pill t-${escapeHtml(node.node_type)}"><i class="rg-dot" aria-hidden="true"></i>${escapeHtml(TYPE_LABELS[node.node_type] || node.node_type)}</span>
        <h3>${escapeHtml(node.label)}${badge}</h3>
        ${sub ? `<p class="rg-p-sub">${escapeHtml(sub)}</p>` : ''}
      </div>
      ${isSelected ? '<button type="button" class="rg-p-close" data-rg-close aria-label="선택 닫기">✕</button>' : ''}
    </div>
    ${relationToEgoHtml(node, egoNode, linkToEgo)}
    <div class="rg-p-actions">${actionsHtml(node, { isEgo, expandState })}</div>
    ${statusNote ? `<p class="rg-p-status" role="status">${escapeHtml(statusNote)}</p>` : ''}
    <div class="rg-p-nbs">
      <h4>이어진 곳 <span>${fmtInt(neighbors.length)}</span></h4>
      ${neighborsHtml(neighbors)}
    </div>
    ${isSelected ? '' : HOW_TO_READ}
  `;
}

/** 패널용 이웃 목록: 관계 종류 순(같은 무대 먼저), 같은 종류 안에서는 횟수 큰 순 */
export function neighborsOf(nodeId, links, nodeById) {
  const out = [];
  for (const l of links) {
    const s = endId(l.source);
    const t = endId(l.target);
    if (s !== nodeId && t !== nodeId) continue;
    const other = nodeById.get(s === nodeId ? t : s);
    if (other) out.push({ node: other, link: l });
  }
  return out.sort((a, b) => kindOrder(a.link.relation) - kindOrder(b.link.relation)
    || (Number(b.link.weight) || 0) - (Number(a.link.weight) || 0)
    || (Number(b.node.importance) || 0) - (Number(a.node.importance) || 0));
}
