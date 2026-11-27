import { appState, navigateTo, registerChart, syncHash } from '../state.js';
import { queryEgoNetwork, queryNodeExpansion, querySceneNetwork } from '../db.js';
import {
  avatarHtml, cssVar, ensureD3, escapeHtml, fmtInt, fmtNum,
  formatNextGigText, formatSourceKey, ROLE_META, roleBadgeHtml, TERMS, wireAvatarFallbacks,
} from '../ui.js';

let nextGraphInstanceId = 1;

const INITIAL_NODE_CAP = 60;
const CAP_STEP = 30;

const RELATION_LABELS = {
  co_stage: '같은 무대',
  same_agency: '같은 소속사',
  venue: '공연장',
  outcome: TERMS.outcome,
  program: '선정·지원',
  outlet: TERMS.outlet,
  scene: '씬 묶음',
};

const TYPE_LABELS = {
  ego: '현재 팀',
  team: '팀',
  venue: '공연장',
  outcome: TERMS.outcome,
  program: '선정·지원',
  outlet: TERMS.outlet,
  scene: '씬 묶음',
};

function shortLabel(text, maxLen = 14) {
  const s = String(text || '').trim();
  return s.length > maxLen ? `${s.slice(0, maxLen - 1)}…` : s;
}

function monogramOf(name) {
  const s = String(name || '').trim();
  if (!s) return '?';
  const ch = Array.from(s)[0] || '?';
  return /[a-z]/.test(ch) ? ch.toUpperCase() : ch;
}

function formatNodeDisplayLabel(row) {
  if (!row) return '';
  if (row.node_type === 'outlet') {
    const info = formatSourceKey(row.node_key || row.label);
    return info.label || row.label || row.node_key;
  }
  return row.label || row.node_key || '';
}

function normalizeEdgeKey(a, b) {
  return a < b ? `${a}__${b}` : `${b}__${a}`;
}

function nodeRadius(d) {
  if (d.node_type === 'ego') return 24;
  if (d.node_type === 'team') {
    const w = Math.max(1, Number(d.maxWeight) || 1);
    return Math.min(20, 14 + Math.sqrt(w) * 1.7);
  }
  if (d.node_type === 'outcome') return 15;
  if (d.node_type === 'scene') return 15;
  if (d.node_type === 'venue') return 13;
  if (d.node_type === 'program') return 12;
  return 11; // outlet
}

function linkWidth(l) {
  const w = Math.max(1, Number(l.weight) || 1);
  if (l.relation === 'co_stage') return Math.min(5.2, 1.3 + Math.sqrt(w) * 1.25);
  if (l.relation === 'venue') return Math.min(3.6, 1.1 + Math.sqrt(w) * 0.75);
  if (l.relation === 'same_agency') return 1.6;
  if (l.relation === 'outcome') return 1.8;
  return 1.25;
}

function linkDistance(l) {
  const rel = l.relation;
  if (rel === 'co_stage') {
    const w = Math.max(1, Number(l.weight) || 1);
    return Math.max(88, 134 - Math.min(36, Math.sqrt(w) * 14));
  }
  if (rel === 'same_agency') return 118;
  if (rel === 'outcome') return 108;
  if (rel === 'program') return 116;
  if (rel === 'venue') return 124;
  if (rel === 'scene') return 138;
  return 120;
}

function readThemePalette() {
  return {
    bg: cssVar('--graph-bg') || cssVar('--surface') || '#f7f7f9',
    ink: cssVar('--ink') || '#111111',
    muted: cssVar('--ink-muted') || '#4a505c',
    accent: cssVar('--accent') || '#1d4ed8',
    edge: cssVar('--graph-edge') || '#cbd2dc',
    edgeAgency: cssVar('--graph-edge-agency') || '#8b95a5',
    edgeHi: cssVar('--graph-edge-hi') || '#1d4ed8',
    teamFill: cssVar('--graph-node-team-fill') || '#eef2ff',
    teamStroke: cssVar('--graph-node-team') || '#3b82f6',
    venueFill: cssVar('--graph-node-venue-fill') || '#ecfeff',
    venueStroke: cssVar('--graph-node-venue') || '#0f766e',
    programFill: cssVar('--graph-node-program-fill') || '#fffbeb',
    programStroke: cssVar('--graph-node-program') || '#b45309',
    outletFill: cssVar('--graph-node-outlet-fill') || '#f5f3ff',
    outletStroke: cssVar('--graph-node-outlet') || '#6d28d9',
    sceneFill: cssVar('--graph-node-scene-fill') || '#f3f4f6',
    sceneStroke: cssVar('--graph-node-scene') || '#64748b',
    gradeS: cssVar('--graph-grade-s') || '#b45309',
    gradeA: cssVar('--graph-grade-a') || '#1d4ed8',
    gradeB: cssVar('--graph-grade-b') || '#4b5563',
    gradeSFg: cssVar('--graph-grade-s-fg') || '#ffffff',
    gradeAFg: cssVar('--graph-grade-a-fg') || '#ffffff',
    gradeBFg: cssVar('--graph-grade-b-fg') || '#ffffff',
  };
}

function outcomeColor(grade, pal) {
  const g = String(grade || '').toUpperCase();
  if (g === 'S') return { fill: pal.gradeS, fg: pal.gradeSFg };
  if (g === 'A') return { fill: pal.gradeA, fg: pal.gradeAFg };
  return { fill: pal.gradeB, fg: pal.gradeBFg };
}

function describeRelationEdge(l) {
  const rels = Array.isArray(l.relations) && l.relations.length ? l.relations : [l.relation];
  const parts = rels.map(r => {
    const lbl = RELATION_LABELS[r] || r;
    if (r === 'co_stage' && l.weight > 0) return `${lbl} ${Math.round(l.weight)}회`;
    if (r === 'venue' && l.weight > 0) return `${lbl} ${Math.round(l.weight)}회`;
    return lbl;
  });
  return parts.join(' · ');
}

function nodeSignalRole(node) {
  if (!node || (node.node_type !== 'program' && node.node_type !== 'outlet')) return '';
  const r = String(node.role || node.detail || '').trim();
  return ROLE_META[r] ? r : '';
}

function isUnscoredSourceNode(node) {
  const r = nodeSignalRole(node);
  return r === 'pending' || r === 'excluded';
}

function unscoredTooltipText(role) {
  return ROLE_META[role]?.unscoredTitle || '점수에 안 쓰는 출처 — 검증 대기';
}

function formatInspectorDetail(node, egoId, links) {
  if (!node) return '';
  const parts = [];
  if (node.node_type === 'ego') {
    parts.push('중심 팀');
    if (node.primary_genre) parts.push(node.primary_genre);
  } else {
    parts.push(TYPE_LABELS[node.node_type] || node.node_type);
    if (node.primary_genre) parts.push(node.primary_genre);
    if (node.node_type === 'outcome' && node.grade) parts.push(`${node.grade}등급`);
    const srcRole = nodeSignalRole(node);
    if (srcRole) {
      if (!isUnscoredSourceNode(node)) {
        parts.push(ROLE_META[srcRole].fullLabel);
      }
    } else if (node.detail) {
      parts.push(node.detail);
    }
  }
  const deg = links.reduce((acc, l) => {
    const s = typeof l.source === 'object' ? l.source.id : l.source;
    const t = typeof l.target === 'object' ? l.target.id : l.target;
    return acc + (s === node.id || t === node.id ? 1 : 0);
  }, 0);
  if (deg > 0) parts.push(`현재 연결 ${deg}`);
  if (node.id !== egoId && node.last_date) parts.push(`최근 ${String(node.last_date).slice(0, 10)}`);
  return parts.filter(Boolean).join(' · ');
}

/**
 * 팀 상세 화면에 인터랙티브 '관계망' 미리보기 블록 + 크게 보기 모달을 마운트한다.
 * 반환값: { destroy() }
 */
export function mountTeamGraphBlock(hostEl, { teamKey, displayName, primaryGenre = '' }) {
  if (!hostEl || !teamKey) return { destroy() {} };

  const instanceId = nextGraphInstanceId++;
  let destroyed = false;
  let period = 'all'; // 'all' | '1y'
  let nodeCap = INITIAL_NODE_CAP;
  let isModalOpen = false;
  let loading = false;

  const egoId = `team:${teamKey}`;
  const nodesMap = new Map();
  const linksMap = new Map();
  const expandedIds = new Set();
  const pendingBuffer = []; // buffered { parentId, row } when nodeCap is reached
  let selectedId = egoId;
  let hoveredId = null;

  let simulation = null;
  let svgSel = null;
  let zoomBehavior = null;
  let gRoot = null;
  let gLinks = null;
  let gNodes = null;
  let currentWidth = 640;
  let currentHeight = 320;
  let modalBackdrop = null;
  let modalSlot = null;
  let themeObserver = null;
  let resizeObserver = null;
  let clickTimer = null;
  let clipCounter = 0;

  // Build initial shell inside hostEl
  hostEl.innerHTML = `
    <section class="block graph-block" id="teamGraphBlock">
      <div class="graph-head">
        <div class="graph-head-title">
          <h2>관계망</h2>
          <span class="block-meta" data-graph-meta>불러오는 중...</span>
        </div>
        <div class="graph-head-actions">
          <div class="seg-toggle graph-period-toggle" role="group" aria-label="관계망 기간">
            <button type="button" class="seg-btn active" data-graph-period="all" aria-pressed="true">전체</button>
            <button type="button" class="seg-btn" data-graph-period="1y" aria-pressed="false">최근 1년</button>
          </div>
          <button type="button" class="btn btn-sm" data-graph-expand-modal aria-label="관계망 크게 보기">크게 보기 ⤢</button>
        </div>
      </div>

      <div class="graph-body-slot" data-graph-inline-slot>
        <div class="graph-surface" data-graph-surface>
          <div class="graph-stage" data-graph-stage>
            <svg class="graph-svg" data-graph-svg role="img" aria-label="${escapeHtml(displayName)} 관계망 그래프"></svg>
            <div class="graph-float-ctrls" aria-label="그래프 조작">
              <button type="button" class="graph-ctrl-btn" data-graph-zoom="in" title="확대" aria-label="확대">+</button>
              <button type="button" class="graph-ctrl-btn" data-graph-zoom="out" title="축소" aria-label="축소">−</button>
              <button type="button" class="graph-ctrl-btn" data-graph-zoom="fit" title="화면에 맞춤" aria-label="화면에 맞춤">맞춤</button>
              <button type="button" class="graph-ctrl-btn is-accent" data-graph-more hidden></button>
              <button type="button" class="graph-ctrl-btn" data-graph-reset hidden>초기화</button>
            </div>
            <div class="graph-tooltip" data-graph-tooltip hidden></div>
            <div class="graph-empty" data-graph-empty hidden></div>
          </div>

          <div class="graph-legend" aria-label="노드 범례">
            <span class="graph-leg-item"><i class="graph-swatch is-team"></i>팀<span class="graph-leg-sub">(실선 무대·점선 소속사)</span></span>
            <span class="graph-leg-item"><i class="graph-swatch is-venue"></i>공연장</span>
            <span class="graph-leg-item"><i class="graph-swatch is-outcome"></i>${escapeHtml(TERMS.outcome)}(S·A·B)</span>
            <span class="graph-leg-item"><i class="graph-swatch is-program"></i>선정·지원</span>
            <span class="graph-leg-item"><i class="graph-swatch is-outlet"></i>${escapeHtml(TERMS.outlet)}</span>
            <span class="graph-leg-item"><i class="graph-swatch is-scene"></i>씬 묶음</span>
            <span class="graph-leg-item" title="점수에 안 쓰는 출처 — 검증 대기·제외">${roleBadgeHtml('pending', { context: 'timeline', compact: true })}점수 미반영</span>
          </div>

          <div class="graph-inspector" data-graph-inspector>
            <span class="graph-insp-hint">노드 클릭 = 연결 펼치기 · 팀 더블클릭 = 상세 이동 · 드래그·확대 가능</span>
          </div>
        </div>
      </div>
    </section>
  `;

  const inlineSlot = hostEl.querySelector('[data-graph-inline-slot]');
  const surfaceEl = hostEl.querySelector('[data-graph-surface]');
  const stageEl = hostEl.querySelector('[data-graph-stage]');
  const svgEl = hostEl.querySelector('[data-graph-svg]');
  const metaEl = hostEl.querySelector('[data-graph-meta]');
  const tooltipEl = hostEl.querySelector('[data-graph-tooltip]');
  const emptyEl = hostEl.querySelector('[data-graph-empty]');
  const inspectorEl = hostEl.querySelector('[data-graph-inspector]');
  const moreBtn = hostEl.querySelector('[data-graph-more]');
  const resetBtn = hostEl.querySelector('[data-graph-reset]');
  const expandModalBtn = hostEl.querySelector('[data-graph-expand-modal]');

  function createEgoNode() {
    return {
      id: egoId,
      node_type: 'ego',
      node_key: teamKey,
      label: displayName || teamKey,
      detail: '',
      grade: '',
      last_date: '',
      primary_genre: primaryGenre || '',
      maxWeight: 3,
      photoUrl: appState.imagesByTeam.get(teamKey) || '',
      expanded: false,
      x: currentWidth / 2,
      y: currentHeight / 2,
      fx: null,
      fy: null,
    };
  }

  function addNeighborRow(parentNode, row) {
    if (!row || !row.node_id) return { addedNode: false, addedLink: false, capped: false };
    const id = String(row.node_id);
    if (id === parentNode.id) return { addedNode: false, addedLink: false, capped: false };

    let targetNode = nodesMap.get(id);
    let addedNode = false;

    if (!targetNode) {
      if (nodesMap.size >= nodeCap) {
        return { addedNode: false, addedLink: false, capped: true };
      }
      const angle = Math.random() * Math.PI * 2;
      const dist = 54 + Math.random() * 38;
      const px = Number.isFinite(parentNode.x) ? parentNode.x : currentWidth / 2;
      const py = Number.isFinite(parentNode.y) ? parentNode.y : currentHeight / 2;
      const photoUrl = row.node_type === 'team' ? (appState.imagesByTeam.get(row.node_key) || '') : '';
      targetNode = {
        id,
        node_type: row.node_type || 'team',
        node_key: String(row.node_key || ''),
        label: formatNodeDisplayLabel(row),
        detail: String(row.detail || ''),
        grade: String(row.grade || ''),
        last_date: row.last_date ? String(row.last_date).slice(0, 10) : '',
        primary_genre: String(row.primary_genre || ''),
        maxWeight: Math.max(1, Number(row.weight) || 1),
        photoUrl,
        expanded: false,
        x: px + Math.cos(angle) * dist,
        y: py + Math.sin(angle) * dist,
      };
      nodesMap.set(id, targetNode);
      addedNode = true;
    } else {
      const w = Math.max(1, Number(row.weight) || 1);
      if (w > (targetNode.maxWeight || 1)) targetNode.maxWeight = w;
      if (!targetNode.detail && row.detail) targetNode.detail = String(row.detail);
      if (!targetNode.grade && row.grade) targetNode.grade = String(row.grade);
    }

    const eKey = normalizeEdgeKey(parentNode.id, targetNode.id);
    const existingEdge = linksMap.get(eKey);
    const rel = row.relation || row.node_type || 'co_stage';
    const weight = Math.max(1, Number(row.weight) || 1);
    let addedLink = false;

    if (!existingEdge) {
      linksMap.set(eKey, {
        id: eKey,
        source: parentNode.id,
        target: targetNode.id,
        relation: rel,
        relations: [rel],
        weight,
        detail: String(row.detail || ''),
      });
      addedLink = true;
    } else {
      if (!existingEdge.relations.includes(rel)) {
        existingEdge.relations.push(rel);
        // Prefer co_stage as primary visual style if both co_stage and same_agency exist
        if (rel === 'co_stage') existingEdge.relation = 'co_stage';
      }
      if (weight > existingEdge.weight) existingEdge.weight = weight;
    }

    return { addedNode, addedLink, capped: false };
  }

  function updateMetaAndControls() {
    const nNodes = nodesMap.size;
    const nLinks = linksMap.size;
    const periodTxt = period === '1y' ? '최근 1년' : '전체';
    if (metaEl) {
      metaEl.textContent = loading
        ? '불러오는 중...'
        : `${periodTxt} · 노드 ${fmtInt(nNodes)} · 연결 ${fmtInt(nLinks)}`;
    }
    if (modalBackdrop) {
      const modalMeta = modalBackdrop.querySelector('[data-graph-modal-meta]');
      if (modalMeta) {
        modalMeta.textContent = `${displayName} · ${periodTxt} · 노드 ${fmtInt(nNodes)} · 연결 ${fmtInt(nLinks)}`;
      }
    }

    const pendingCount = countUniquePending();
    if (moreBtn) {
      if (pendingCount > 0) {
        moreBtn.hidden = false;
        moreBtn.textContent = `더 보기 (+${fmtInt(Math.min(CAP_STEP, pendingCount))})`;
      } else {
        moreBtn.hidden = true;
      }
    }

    const hasExpandedExtra = expandedIds.size > 1 || nodeCap > INITIAL_NODE_CAP;
    if (resetBtn) {
      resetBtn.hidden = !hasExpandedExtra;
    }

    // Sync period toggle buttons (both inline and modal if open)
    const periodBtns = [
      ...hostEl.querySelectorAll('[data-graph-period]'),
      ...(modalBackdrop ? modalBackdrop.querySelectorAll('[data-graph-period]') : []),
    ];
    periodBtns.forEach(btn => {
      const active = btn.dataset.graphPeriod === period;
      btn.classList.toggle('active', active);
      btn.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
  }

  function countUniquePending() {
    const seen = new Set();
    for (const item of pendingBuffer) {
      if (item?.row?.node_id && !nodesMap.has(item.row.node_id)) {
        seen.add(item.row.node_id);
      }
    }
    return seen.size;
  }

  function renderInspector(statusNote = '') {
    if (!inspectorEl) return;
    const node = nodesMap.get(selectedId);
    if (!node) {
      inspectorEl.innerHTML = '<span class="graph-insp-hint">노드 클릭 = 연결 펼치기 · 팀 더블클릭 = 상세 이동 · 드래그·확대 가능</span>';
      return;
    }
    const linksArr = [...linksMap.values()];
    const detailTxt = formatInspectorDetail(node, egoId, linksArr);
    const badgeCls = `is-${node.node_type}`;
    const srcRole = nodeSignalRole(node);
    const refBadgeHtml = isUnscoredSourceNode(node)
      ? roleBadgeHtml(srcRole, { context: 'timeline', compact: true })
      : '';
    const noteHtml = statusNote ? `<span class="graph-insp-status">${escapeHtml(statusNote)}</span>` : '';

    let actionBtn = '';
    if (node.node_type === 'team' && node.node_key && node.id !== egoId) {
      actionBtn = `<button type="button" class="btn btn-sm graph-insp-action" data-go-team="${escapeHtml(node.node_key)}">팀 상세 보기 →</button>`;
    } else if (node.node_type === 'scene' && node.node_key) {
      actionBtn = `<button type="button" class="btn btn-sm graph-insp-action" data-go-scene="${escapeHtml(node.node_key)}">공연장·씬 보기 →</button>`;
    }

    inspectorEl.innerHTML = `
      <div class="graph-insp-main">
        <span class="graph-type-pill ${badgeCls}">${escapeHtml(TYPE_LABELS[node.node_type] || node.node_type)}</span>
        <strong class="graph-insp-name">${escapeHtml(node.label)}</strong>
        ${refBadgeHtml}
        <span class="graph-insp-detail">${escapeHtml(detailTxt)}</span>
        ${noteHtml}
      </div>
      <div class="graph-insp-right">
        ${actionBtn}
      </div>
    `;

    inspectorEl.querySelector('[data-go-team]')?.addEventListener('click', (e) => {
      const tk = e.currentTarget.dataset.goTeam;
      if (!tk) return;
      closeModal();
      navigateTo('team', tk);
    });
    inspectorEl.querySelector('[data-go-scene]')?.addEventListener('click', (e) => {
      const sid = Number(e.currentTarget.dataset.goScene);
      closeModal();
      if (Number.isFinite(sid)) appState.focusSceneId = sid;
      navigateTo('venues', '');
    });
  }

  function showTooltip(evt, html) {
    if (!tooltipEl || !stageEl) return;
    tooltipEl.innerHTML = html;
    tooltipEl.hidden = false;
    positionTooltip(evt);
  }

  function positionTooltip(evt) {
    if (!tooltipEl || tooltipEl.hidden || !stageEl || !evt) return;
    const rect = stageEl.getBoundingClientRect();
    const tw = tooltipEl.offsetWidth || 160;
    const th = tooltipEl.offsetHeight || 42;
    let x = evt.clientX - rect.left + 12;
    let y = evt.clientY - rect.top - th - 10;
    if (x + tw > rect.width - 8) x = Math.max(8, evt.clientX - rect.left - tw - 12);
    if (y < 8) y = Math.min(rect.height - th - 8, evt.clientY - rect.top + 14);
    tooltipEl.style.left = `${Math.round(x)}px`;
    tooltipEl.style.top = `${Math.round(y)}px`;
  }

  function hideTooltip() {
    if (tooltipEl) tooltipEl.hidden = true;
  }

  function getNeighborSet(nodeId) {
    const set = new Set([nodeId]);
    for (const l of linksMap.values()) {
      const s = typeof l.source === 'object' ? l.source.id : l.source;
      const t = typeof l.target === 'object' ? l.target.id : l.target;
      if (s === nodeId) set.add(t);
      else if (t === nodeId) set.add(s);
    }
    return set;
  }

  function applyHighlightAndTheme() {
    if (!svgSel || !gNodes || !gLinks) return;
    const pal = readThemePalette();
    const focusId = hoveredId;
    const nbrs = focusId ? getNeighborSet(focusId) : null;

    gLinks.selectAll('line.graph-link')
      .attr('stroke', l => {
        const s = typeof l.source === 'object' ? l.source.id : l.source;
        const t = typeof l.target === 'object' ? l.target.id : l.target;
        if (focusId && (s === focusId || t === focusId)) return pal.edgeHi;
        if (l.relation === 'same_agency') return pal.edgeAgency;
        return pal.edge;
      })
      .attr('stroke-opacity', l => {
        const s = typeof l.source === 'object' ? l.source.id : l.source;
        const t = typeof l.target === 'object' ? l.target.id : l.target;
        if (focusId) return (s === focusId || t === focusId) ? 0.92 : 0.12;
        if (l.relation === 'co_stage') return 0.65;
        if (l.relation === 'same_agency') return 0.6;
        return 0.48;
      });

    gNodes.selectAll('g.graph-node').each(function (d) {
      const g = window.d3.select(this);
      const isDimmed = Boolean(nbrs && !nbrs.has(d.id));
      const isSelected = d.id === selectedId;
      const isHovered = d.id === hoveredId;
      const unscored = isUnscoredSourceNode(d);
      g.attr('opacity', isDimmed ? 0.16 : (unscored && !isSelected && !isHovered ? 0.78 : 1));

      // Update shape colors for current White / True Black theme
      if (d.node_type === 'ego') {
        g.select('.gn-base').attr('fill', pal.teamFill).attr('stroke', pal.accent);
        g.select('.gn-ring').attr('stroke', isSelected || isHovered ? pal.accent : pal.accent);
        g.select('.gn-mono').attr('fill', pal.accent);
      } else if (d.node_type === 'team') {
        g.select('.gn-base')
          .attr('fill', pal.teamFill)
          .attr('stroke', isSelected || isHovered ? pal.accent : pal.teamStroke);
        g.select('.gn-ring')
          .attr('stroke', pal.accent)
          .attr('opacity', d.expanded || isSelected ? 0.85 : 0);
        g.select('.gn-mono').attr('fill', pal.teamStroke);
      } else if (d.node_type === 'venue') {
        g.select('.gn-base')
          .attr('fill', pal.venueFill)
          .attr('stroke', isSelected || isHovered ? pal.accent : pal.venueStroke);
        g.select('.gn-glyph').attr('fill', pal.venueStroke);
      } else if (d.node_type === 'outcome') {
        const oc = outcomeColor(d.grade, pal);
        g.select('.gn-base')
          .attr('fill', oc.fill)
          .attr('stroke', isSelected || isHovered ? pal.accent : oc.fill);
        g.select('.gn-glyph').attr('fill', oc.fg);
      } else if (d.node_type === 'program') {
        g.select('.gn-base')
          .attr('fill', pal.programFill)
          .attr('stroke', isSelected || isHovered ? pal.accent : pal.programStroke);
      } else if (d.node_type === 'outlet') {
        g.select('.gn-base')
          .attr('fill', pal.outletFill)
          .attr('stroke', isSelected || isHovered ? pal.accent : pal.outletStroke);
      } else if (d.node_type === 'scene') {
        g.select('.gn-base')
          .attr('fill', pal.sceneFill)
          .attr('stroke', isSelected || isHovered ? pal.accent : pal.sceneStroke);
        g.select('.gn-glyph').attr('fill', pal.sceneStroke);
      }

      g.select('.gn-label')
        .attr('fill', isSelected || isHovered || d.node_type === 'ego' ? pal.ink : pal.muted)
        .attr('stroke', pal.bg);
      g.select('.gn-ref-tag')
        .attr('fill', pal.muted)
        .attr('stroke', pal.bg);
    });
  }

  function fitToView(duration = 280) {
    if (destroyed || !svgSel || !zoomBehavior || !nodesMap.size || !svgEl || !svgEl.isConnected) return;
    const d3 = window.d3;
    const rect = stageEl.getBoundingClientRect();
    const w = Math.max(240, rect.width || currentWidth);
    const h = Math.max(220, rect.height || currentHeight);
    currentWidth = w;
    currentHeight = h;
    zoomBehavior.extent([[0, 0], [w, h]]);

    const pts = [...nodesMap.values()].filter(n => Number.isFinite(n.x) && Number.isFinite(n.y));
    if (!pts.length) return;

    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    for (const n of pts) {
      const pad = nodeRadius(n) + 28;
      if (n.x - pad < minX) minX = n.x - pad;
      if (n.x + pad > maxX) maxX = n.x + pad;
      if (n.y - pad < minY) minY = n.y - pad;
      if (n.y + pad > maxY) maxY = n.y + pad;
    }
    const bw = Math.max(80, maxX - minX);
    const bh = Math.max(80, maxY - minY);
    const scale = Math.max(0.36, Math.min(1.3, 0.88 * Math.min(w / bw, h / bh)));
    const cx = (minX + maxX) / 2;
    const cy = (minY + maxY) / 2;
    const tx = w / 2 - cx * scale;
    const ty = h / 2 - cy * scale;

    const transform = d3.zoomIdentity.translate(tx, ty).scale(scale);
    svgSel.interrupt();
    if (duration > 0) {
      svgSel.transition().duration(duration).call(zoomBehavior.transform, transform);
    } else {
      svgSel.call(zoomBehavior.transform, transform);
    }
  }

  function ensureSvgInitialized() {
    if (svgSel || !window.d3 || !svgEl) return;
    const d3 = window.d3;
    const rect = stageEl.getBoundingClientRect();
    currentWidth = Math.max(280, rect.width || 640);
    currentHeight = Math.max(240, rect.height || 320);

    svgSel = d3.select(svgEl);

    svgSel.selectAll('*').remove();
    svgSel.append('defs').attr('class', 'graph-defs');

    gRoot = svgSel.append('g').attr('class', 'graph-root');
    gLinks = gRoot.append('g').attr('class', 'graph-links');
    gNodes = gRoot.append('g').attr('class', 'graph-nodes');

    zoomBehavior = d3.zoom()
      .extent([[0, 0], [currentWidth, currentHeight]])
      .scaleExtent([0.28, 3.2])
      .on('zoom', (event) => {
        gRoot.attr('transform', event.transform);
      });

    svgSel.call(zoomBehavior).on('dblclick.zoom', null);

    // Click empty background clears selection back to ego
    svgSel.on('click', (event) => {
      if (event.target === svgEl) {
        selectedId = egoId;
        hoveredId = null;
        hideTooltip();
        applyHighlightAndTheme();
        renderInspector();
      }
    });

    simulation = d3.forceSimulation()
      .force('link', d3.forceLink().id(d => d.id).distance(linkDistance).strength(0.5))
      .force('charge', d3.forceManyBody().strength(d => (d.node_type === 'ego' ? -440 : -280)).distanceMax(520))
      .force('center', d3.forceCenter(currentWidth / 2, currentHeight / 2))
      .force('collide', d3.forceCollide().radius(d => nodeRadius(d) + 22).iterations(3))
      .force('x', d3.forceX(currentWidth / 2).strength(0.04))
      .force('y', d3.forceY(currentHeight / 2).strength(0.04))
      .alphaDecay(0.032)
      .on('tick', () => {
        gLinks.selectAll('line.graph-link')
          .attr('x1', d => d.source.x)
          .attr('y1', d => d.source.y)
          .attr('x2', d => d.target.x)
          .attr('y2', d => d.target.y);

        gNodes.selectAll('g.graph-node')
          .attr('transform', d => `translate(${d.x.toFixed(1)},${d.y.toFixed(1)})`);
      });
  }

  function renderGraph({ reheat = 0.5, autoFit = false } = {}) {
    if (destroyed) return;
    if (!window.d3) {
      if (emptyEl) {
        emptyEl.hidden = false;
        emptyEl.textContent = '그래프 라이브러리(D3)를 불러오지 못했습니다.';
      }
      return;
    }
    ensureSvgInitialized();
    const d3 = window.d3;
    const nodes = [...nodesMap.values()];
    const links = [...linksMap.values()];

    if (emptyEl) {
      if (nodes.length <= 1) {
        emptyEl.hidden = false;
        emptyEl.textContent = period === '1y'
          ? '최근 1년 안에 연결된 기록이 없습니다. 상단에서 "전체"를 눌러 보세요.'
          : '연결된 공연·선정·매체 기록이 아직 없습니다.';
      } else {
        emptyEl.hidden = true;
      }
    }

    const defs = svgSel.select('defs.graph-defs');

    // Bind links
    const linkJoin = gLinks.selectAll('line.graph-link')
      .data(links, d => d.id);

    linkJoin.exit().remove();

    const linkEnter = linkJoin.enter()
      .append('line')
      .attr('class', d => `graph-link is-${d.relation}`)
      .attr('stroke-linecap', 'round');

    linkEnter.merge(linkJoin)
      .attr('stroke-width', linkWidth)
      .attr('stroke-dasharray', d => (d.relation === 'same_agency' ? '4 3' : (d.relation === 'scene' ? '2 3' : null)))
      .on('mouseenter', function (evt, d) {
        const sObj = typeof d.source === 'object' ? d.source : null;
        const tObj = typeof d.target === 'object' ? d.target : null;
        const sLbl = sObj ? sObj.label : d.source;
        const tLbl = tObj ? tObj.label : d.target;
        const desc = describeRelationEdge(d);
        const unscoredNode = isUnscoredSourceNode(tObj) ? tObj : (isUnscoredSourceNode(sObj) ? sObj : null);
        const unscoredRole = unscoredNode ? nodeSignalRole(unscoredNode) : '';
        const refBadge = unscoredRole ? roleBadgeHtml(unscoredRole, { context: 'timeline', compact: true }) : '';
        const extra = d.detail && d.relation === 'co_stage'
          ? `<div class="gt-sub">${escapeHtml(d.detail)}</div>`
          : (unscoredRole ? `<div class="gt-sub">${escapeHtml(unscoredTooltipText(unscoredRole))}</div>` : '');
        showTooltip(evt, `<div class="gt-head"><strong>${escapeHtml(sLbl)} ↔ ${escapeHtml(tLbl)}</strong>${refBadge}</div><div class="gt-sub">${escapeHtml(desc)}</div>${extra}`);
      })
      .on('mousemove', positionTooltip)
      .on('mouseleave', hideTooltip);

    // Bind nodes
    const nodeJoin = gNodes.selectAll('g.graph-node')
      .data(nodes, d => d.id);

    nodeJoin.exit().remove();

    let dragMoved = false;
    const dragBehavior = d3.drag()
      .on('start', (event, d) => {
        dragMoved = false;
        if (!event.active) simulation.alphaTarget(0.22).restart();
        d.fx = d.x;
        d.fy = d.y;
      })
      .on('drag', (event, d) => {
        if (Math.abs(event.dx) > 1.5 || Math.abs(event.dy) > 1.5) dragMoved = true;
        d.fx = event.x;
        d.fy = event.y;
      })
      .on('end', (event, d) => {
        if (!event.active) simulation.alphaTarget(0);
        d.fx = null;
        d.fy = null;
      });

    const nodeEnter = nodeJoin.enter()
      .append('g')
      .attr('class', d => `graph-node is-${d.node_type}`)
      .attr('data-node-id', d => d.id)
      .attr('data-node-type', d => d.node_type)
      .style('cursor', 'pointer')
      .call(dragBehavior);

    nodeEnter.each(function (d) {
      const g = d3.select(this);
      const r = nodeRadius(d);

      if (d.node_type === 'ego' || d.node_type === 'team') {
        g.append('circle')
          .attr('class', 'gn-ring')
          .attr('r', r + (d.node_type === 'ego' ? 4 : 3))
          .attr('fill', 'none')
          .attr('stroke-width', d.node_type === 'ego' ? 2 : 1.5)
          .attr('stroke-dasharray', d.node_type === 'ego' ? null : '2 2');

        g.append('circle')
          .attr('class', 'gn-base')
          .attr('r', r)
          .attr('stroke-width', d.node_type === 'ego' ? 2.4 : 1.7);

        g.append('text')
          .attr('class', 'gn-mono')
          .attr('text-anchor', 'middle')
          .attr('dominant-baseline', 'central')
          .attr('font-size', d.node_type === 'ego' ? 14 : 10.5)
          .attr('font-weight', 700)
          .style('pointer-events', 'none')
          .text(monogramOf(d.label));

        if (d.photoUrl) {
          const clipId = `cg-clip-${instanceId}-${++clipCounter}`;
          defs.append('clipPath')
            .attr('id', clipId)
            .append('circle')
            .attr('r', Math.max(4, r - 1));

          const imgEl = g.append('image')
            .attr('class', 'gn-photo')
            .attr('href', d.photoUrl)
            .attr('x', -r)
            .attr('y', -r)
            .attr('width', r * 2)
            .attr('height', r * 2)
            .attr('preserveAspectRatio', 'xMidYMid slice')
            .attr('clip-path', `url(#${clipId})`)
            .style('pointer-events', 'none');

          imgEl.on('error', function () {
            d3.select(this).remove();
          });
        }
      } else if (d.node_type === 'venue') {
        const s = r * 1.72;
        g.append('rect')
          .attr('class', 'gn-base')
          .attr('x', -s / 2)
          .attr('y', -s / 2)
          .attr('width', s)
          .attr('height', s)
          .attr('rx', 5)
          .attr('stroke-width', 1.6);
        g.append('text')
          .attr('class', 'gn-glyph')
          .attr('text-anchor', 'middle')
          .attr('dominant-baseline', 'central')
          .attr('font-size', 9.5)
          .attr('font-weight', 700)
          .style('pointer-events', 'none')
          .text('공');
      } else if (d.node_type === 'outcome') {
        g.append('circle')
          .attr('class', 'gn-base')
          .attr('r', r)
          .attr('stroke-width', 2);
        g.append('text')
          .attr('class', 'gn-glyph')
          .attr('text-anchor', 'middle')
          .attr('dominant-baseline', 'central')
          .attr('font-size', 11)
          .attr('font-weight', 800)
          .style('pointer-events', 'none')
          .text(String(d.grade || '상').toUpperCase());
      } else if (d.node_type === 'program') {
        const s = r * 1.5;
        const rect = g.append('rect')
          .attr('class', 'gn-base')
          .attr('x', -s / 2)
          .attr('y', -s / 2)
          .attr('width', s)
          .attr('height', s)
          .attr('rx', 2.5)
          .attr('transform', 'rotate(45)')
          .attr('stroke-width', 1.6);
        if (isUnscoredSourceNode(d)) rect.attr('stroke-dasharray', '3 2');
      } else if (d.node_type === 'scene') {
        g.append('circle')
          .attr('class', 'gn-base')
          .attr('r', r)
          .attr('stroke-width', 1.7)
          .attr('stroke-dasharray', '3 2');
        g.append('text')
          .attr('class', 'gn-glyph')
          .attr('text-anchor', 'middle')
          .attr('dominant-baseline', 'central')
          .attr('font-size', 9.5)
          .attr('font-weight', 700)
          .style('pointer-events', 'none')
          .text(`#${d.node_key}`);
      } else {
        // outlet
        const circle = g.append('circle')
          .attr('class', 'gn-base')
          .attr('r', r)
          .attr('stroke-width', 1.5);
        if (isUnscoredSourceNode(d)) circle.attr('stroke-dasharray', '3 2');
      }

      g.append('text')
        .attr('class', 'gn-label')
        .attr('y', r + 13)
        .attr('text-anchor', 'middle')
        .attr('font-size', d.node_type === 'ego' ? 12 : 11)
        .attr('font-weight', d.node_type === 'ego' ? 700 : 500)
        .attr('paint-order', 'stroke')
        .attr('stroke-width', 3)
        .attr('stroke-linejoin', 'round')
        .style('pointer-events', 'none')
        .text(shortLabel(d.label, d.node_type === 'ego' ? 18 : 13));

      if (isUnscoredSourceNode(d)) {
        const srcRole = nodeSignalRole(d);
        g.append('title').text(unscoredTooltipText(srcRole));
        g.append('text')
          .attr('class', 'gn-ref-tag')
          .attr('y', r + 24)
          .attr('text-anchor', 'middle')
          .attr('font-size', 9)
          .attr('font-weight', 600)
          .attr('paint-order', 'stroke')
          .attr('stroke-width', 2.5)
          .attr('stroke-linejoin', 'round')
          .style('pointer-events', 'none')
          .text(TERMS.unscored);
      }
    });

    const nodeMerged = nodeEnter.merge(nodeJoin);

    nodeMerged
      .on('mouseenter', function (evt, d) {
        hoveredId = d.id;
        applyHighlightAndTheme();
        const typeLbl = TYPE_LABELS[d.node_type] || d.node_type;
        const srcRole = nodeSignalRole(d);
        const unscored = isUnscoredSourceNode(d);
        const refBadge = unscored ? roleBadgeHtml(srcRole, { context: 'timeline', compact: true }) : '';
        let sub = '';
        if (srcRole) {
          sub = unscored ? unscoredTooltipText(srcRole) : ROLE_META[srcRole].fullLabel;
        } else {
          sub = d.detail || d.primary_genre || '';
        }
        const actionHint = d.node_type === 'team' && d.id !== egoId
          ? '클릭: 연결 펼치기 · 더블클릭: 팀 상세'
          : (d.expanded ? '연결 펼쳐짐' : '클릭: 연결 펼치기');
        showTooltip(evt, `
          <div class="gt-head"><strong>${escapeHtml(d.label)}</strong>${refBadge}</div>
          <div class="gt-sub">${escapeHtml(typeLbl)}${sub ? ` · ${escapeHtml(sub)}` : ''}</div>
          <div class="gt-hint">${escapeHtml(actionHint)}</div>
        `);
      })
      .on('mousemove', positionTooltip)
      .on('mouseleave', () => {
        hoveredId = null;
        hideTooltip();
        applyHighlightAndTheme();
      })
      .on('click', (evt, d) => {
        evt.stopPropagation();
        if (dragMoved) return;
        clearTimeout(clickTimer);
        clickTimer = setTimeout(() => {
          handleNodeClick(d);
        }, 180);
      })
      .on('dblclick', (evt, d) => {
        evt.stopPropagation();
        clearTimeout(clickTimer);
        if (d.node_type === 'team' && d.node_key && d.id !== egoId) {
          closeModal();
          navigateTo('team', d.node_key);
        } else if (d.node_type === 'scene' && d.node_key) {
          closeModal();
          appState.focusSceneId = Number(d.node_key);
          navigateTo('venues', '');
        }
      });

    simulation.nodes(nodes);
    simulation.force('link').links(links);

    const rect = stageEl.getBoundingClientRect();
    currentWidth = Math.max(260, rect.width || currentWidth);
    currentHeight = Math.max(220, rect.height || currentHeight);
    if (zoomBehavior) zoomBehavior.extent([[0, 0], [currentWidth, currentHeight]]);
    simulation.force('center', d3.forceCenter(currentWidth / 2, currentHeight / 2));
    simulation.force('x', d3.forceX(currentWidth / 2).strength(0.04));
    simulation.force('y', d3.forceY(currentHeight / 2).strength(0.04));

    if (reheat > 0) {
      simulation.alpha(reheat).restart();
    }
    if (autoFit) {
      // Pre-tick for calm, well-spaced initial settle before fitting
      for (let i = 0; i < 70; i++) simulation.tick();
      gLinks.selectAll('line.graph-link')
        .attr('x1', d => d.source.x)
        .attr('y1', d => d.source.y)
        .attr('x2', d => d.target.x)
        .attr('y2', d => d.target.y);
      gNodes.selectAll('g.graph-node')
        .attr('transform', d => `translate(${d.x.toFixed(1)},${d.y.toFixed(1)})`);
      fitToView(0);
    }

    applyHighlightAndTheme();
    updateMetaAndControls();
  }

  async function handleNodeClick(node) {
    if (destroyed || !node) return;
    selectedId = node.id;
    applyHighlightAndTheme();

    if (expandedIds.has(node.id)) {
      renderInspector('이미 연결 펼침');
      return;
    }

    renderInspector('연결 불러오는 중...');
    try {
      const rows = await queryNodeExpansion(node, { period, limit: 10 });
      if (destroyed) return;
      expandedIds.add(node.id);
      node.expanded = true;

      let addedNodes = 0;
      let addedLinks = 0;
      let cappedCount = 0;

      for (const r of rows) {
        const res = addNeighborRow(node, r);
        if (res.capped) {
          pendingBuffer.push({ parentId: node.id, row: r });
          cappedCount += 1;
        } else {
          if (res.addedNode) addedNodes += 1;
          if (res.addedLink) addedLinks += 1;
        }
      }

      if (addedNodes > 0 || addedLinks > 0) {
        renderGraph({ reheat: 0.45, autoFit: false });
      } else {
        applyHighlightAndTheme();
        updateMetaAndControls();
      }

      let note = '';
      if (addedNodes > 0) note = `이웃 +${fmtInt(addedNodes)} 펼침`;
      else if (addedLinks > 0) note = `연결 +${fmtInt(addedLinks)} 추가`;
      else if (cappedCount > 0) note = `상한(${nodeCap}개) 도달 — "더 보기"로 확장`;
      else note = '추가 연결 없음';
      renderInspector(note);
    } catch (_) {
      if (!destroyed) renderInspector('연결 조회 오류');
    }
  }

  function flushPendingBuffer() {
    nodeCap += CAP_STEP;
    let addedNodes = 0;
    let addedLinks = 0;
    const stillPending = [];

    for (const item of pendingBuffer) {
      const parent = nodesMap.get(item.parentId);
      if (!parent) continue;
      const res = addNeighborRow(parent, item.row);
      if (res.capped) {
        stillPending.push(item);
      } else {
        if (res.addedNode) addedNodes += 1;
        if (res.addedLink) addedLinks += 1;
      }
    }
    pendingBuffer.length = 0;
    pendingBuffer.push(...stillPending);

    if (addedNodes > 0 || addedLinks > 0) {
      renderGraph({ reheat: 0.42, autoFit: false });
      renderInspector(`노드 +${fmtInt(addedNodes)} 더 표시`);
    } else {
      updateMetaAndControls();
    }
  }

  async function loadInitialGraph() {
    if (destroyed) return;
    loading = true;
    nodesMap.clear();
    linksMap.clear();
    expandedIds.clear();
    pendingBuffer.length = 0;
    nodeCap = INITIAL_NODE_CAP;
    selectedId = egoId;
    hoveredId = null;
    updateMetaAndControls();

    const ego = createEgoNode();
    nodesMap.set(ego.id, ego);
    expandedIds.add(ego.id);
    ego.expanded = true;

    try {
      const rows = await queryEgoNetwork(teamKey, { period, limitPerKind: 10 });
      if (destroyed) return;
      for (const r of rows) {
        const res = addNeighborRow(ego, r);
        if (res.capped) {
          pendingBuffer.push({ parentId: ego.id, row: r });
        }
      }
    } catch (_) {
      // Keep ego node rendered cleanly
    } finally {
      loading = false;
      if (!destroyed) {
        renderGraph({ reheat: 0.55, autoFit: true });
        renderInspector();
      }
    }
  }

  // ---------- Modal open / close ----------

  function onModalKeydown(e) {
    if (e.key === 'Escape' && isModalOpen) {
      e.preventDefault();
      closeModal();
    }
  }

  function openModal() {
    if (isModalOpen || destroyed) return;
    isModalOpen = true;

    modalBackdrop = document.createElement('div');
    modalBackdrop.className = 'graph-modal-backdrop';
    modalBackdrop.setAttribute('role', 'dialog');
    modalBackdrop.setAttribute('aria-modal', 'true');
    modalBackdrop.setAttribute('aria-label', `${displayName} 관계망 크게 보기`);

    modalBackdrop.innerHTML = `
      <div class="graph-modal">
        <div class="graph-modal-head">
          <div>
            <h2 class="graph-modal-title">관계망</h2>
            <span class="block-meta" data-graph-modal-meta></span>
          </div>
          <div class="graph-head-actions">
            <div class="seg-toggle graph-period-toggle" role="group" aria-label="관계망 기간">
              <button type="button" class="seg-btn ${period === 'all' ? 'active' : ''}" data-graph-period="all" aria-pressed="${period === 'all'}">전체</button>
              <button type="button" class="seg-btn ${period === '1y' ? 'active' : ''}" data-graph-period="1y" aria-pressed="${period === '1y'}">최근 1년</button>
            </div>
            <button type="button" class="btn btn-sm" data-graph-close-modal>닫기 ✕</button>
          </div>
        </div>
        <div class="graph-modal-body" data-graph-modal-slot></div>
      </div>
    `;

    modalSlot = modalBackdrop.querySelector('[data-graph-modal-slot]');
    modalSlot.appendChild(surfaceEl);
    surfaceEl.classList.add('is-expanded');
    document.body.appendChild(modalBackdrop);
    document.body.classList.add('graph-modal-open');

    modalBackdrop.addEventListener('click', (e) => {
      if (e.target === modalBackdrop) closeModal();
    });
    modalBackdrop.querySelector('[data-graph-close-modal]')?.addEventListener('click', closeModal);
    modalBackdrop.querySelectorAll('[data-graph-period]').forEach(btn => {
      btn.addEventListener('click', () => {
        const nextP = btn.dataset.graphPeriod;
        if (nextP && nextP !== period) {
          period = nextP;
          loadInitialGraph();
        }
      });
    });

    document.addEventListener('keydown', onModalKeydown);
    updateMetaAndControls();

    requestAnimationFrame(() => {
      if (!destroyed) fitToView(220);
    });
  }

  function closeModal() {
    if (!isModalOpen) return;
    isModalOpen = false;
    if (svgSel) {
      try { svgSel.interrupt(); } catch (_) {}
    }
    document.removeEventListener('keydown', onModalKeydown);
    document.body.classList.remove('graph-modal-open');
    surfaceEl.classList.remove('is-expanded');
    if (inlineSlot && surfaceEl && inlineSlot.isConnected) {
      inlineSlot.appendChild(surfaceEl);
    }
    if (modalBackdrop) {
      modalBackdrop.remove();
      modalBackdrop = null;
      modalSlot = null;
    }
    requestAnimationFrame(() => {
      if (!destroyed) fitToView(200);
    });
  }

  // ---------- Wire Controls & Observers ----------

  hostEl.querySelectorAll('[data-graph-period]').forEach(btn => {
    btn.addEventListener('click', () => {
      const nextP = btn.dataset.graphPeriod;
      if (nextP && nextP !== period) {
        period = nextP;
        loadInitialGraph();
      }
    });
  });

  expandModalBtn?.addEventListener('click', openModal);

  moreBtn?.addEventListener('click', flushPendingBuffer);

  resetBtn?.addEventListener('click', () => {
    loadInitialGraph();
  });

  surfaceEl.querySelectorAll('[data-graph-zoom]').forEach(btn => {
    btn.addEventListener('click', () => {
      if (!svgSel || !zoomBehavior || !svgEl.isConnected) return;
      const mode = btn.dataset.graphZoom;
      svgSel.interrupt();
      if (mode === 'in') svgSel.transition().duration(180).call(zoomBehavior.scaleBy, 1.28);
      else if (mode === 'out') svgSel.transition().duration(180).call(zoomBehavior.scaleBy, 1 / 1.28);
      else fitToView(240);
    });
  });

  // Live theme reactivity (White <-> True Black #08090a)
  themeObserver = new MutationObserver(() => {
    if (!destroyed) applyHighlightAndTheme();
  });
  themeObserver.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ['data-theme'],
  });

  if (typeof ResizeObserver !== 'undefined' && stageEl) {
    resizeObserver = new ResizeObserver(() => {
      if (destroyed || !stageEl.isConnected) return;
      const rect = stageEl.getBoundingClientRect();
      if (rect.width > 40 && rect.height > 40) {
        currentWidth = rect.width;
        currentHeight = rect.height;
        if (zoomBehavior) zoomBehavior.extent([[0, 0], [currentWidth, currentHeight]]);
      }
    });
    resizeObserver.observe(stageEl);
  }

  function destroy() {
    if (destroyed) return;
    destroyed = true;
    clearTimeout(clickTimer);
    if (svgSel) {
      try { svgSel.interrupt(); } catch (_) {}
    }
    closeModal();
    if (simulation) {
      try { simulation.stop(); } catch (_) {}
      simulation = null;
    }
    if (themeObserver) {
      try { themeObserver.disconnect(); } catch (_) {}
      themeObserver = null;
    }
    if (resizeObserver) {
      try { resizeObserver.disconnect(); } catch (_) {}
      resizeObserver = null;
    }
  }

  const handle = { destroy };
  registerChart(handle);

  // Load D3 on demand, then fetch and render the ego network
  if (window.d3) {
    loadInitialGraph();
  } else {
    ensureD3()
      .then(() => { if (!destroyed) loadInitialGraph(); })
      .catch(() => { if (!destroyed) loadInitialGraph(); });
  }

  return handle;
}

// ---------- Whole / Genre Scene Network (Canvas + D3 v7) ----------

const SCENE_FALLBACK_COLORS = [
  '#2563eb',
  '#0f766e',
  '#d97706',
  '#7c3aed',
  '#db2777',
  '#0284c7',
  '#65a30d',
  '#ea580c',
];

function readScenePalette() {
  const base = readThemePalette();
  const sceneColors = [];
  for (let i = 0; i < 8; i++) {
    sceneColors.push(cssVar(`--scene-c${i}`) || SCENE_FALLBACK_COLORS[i]);
  }
  return {
    ...base,
    surface: cssVar('--bg') || '#ffffff',
    sceneColors,
    sceneOther: cssVar('--scene-c-other') || '#94a3b8',
  };
}

/**
 * 공연장·씬 화면에 전체/장르별 씬 네트워크(Canvas + D3 v7)를 마운트한다.
 * - 노드 = 오늘 점수 상위 N팀(후보 + 정답 팀 포함), 크기 = 점수, 색 = 씬 묶음
 * - 이미 수상·선정된 정답 팀은 등급(S/A/B) 색상 이중 테두리로 구분
 * - 엣지 = 같은 무대에 선 횟수(두께)
 * - 장르 칩 전환 시 URL 해시(#/venues?genre=…)와 동기화
 * - 노드 클릭 시 1-hop 이웃 강조 + 요약 카드, 검색으로 팀 찾아 포커스
 * 반환값: { destroy() }
 */
export function mountSceneNetworkBlock(hostEl, {
  initialGenre = '',
  initialLimit = 150,
  nextGigByTeam = new Map(),
} = {}) {
  if (!hostEl) return { destroy() {} };

  let destroyed = false;
  let currentGenre = String(initialGenre || '');
  let currentLimit = Number(initialLimit) || 150;
  let loadSeq = 0;
  let isModalOpen = false;

  let nodes = [];
  let edges = [];
  let communities = [];
  let nodeById = new Map();
  let adjMap = new Map(); // id -> Array<{ neighbor, weight, detail, last_date }>
  let selectedId = null;
  let hoveredId = null;
  let activeCommId = null;
  let winnerCount = 0;
  let candidateCount = 0;

  let pal = readScenePalette();
  let simulation = null;
  let zoomBehavior = null;
  let canvasSel = null;
  let transform = null; // d3.zoomIdentity
  let currentWidth = 760;
  let currentHeight = 480;
  let fittedWidth = 0;
  let fittedHeight = 0;
  let rafId = 0;
  let needsDraw = false;
  let modalBackdrop = null;
  let modalSlot = null;
  let themeObserver = null;
  let resizeObserver = null;
  let lastClickTime = 0;
  let lastClickNodeId = null;

  const validGenres = Array.isArray(appState.validGenres) ? appState.validGenres : [];
  const limitChoices = [100, 150, 250, 300];

  hostEl.innerHTML = `
    <section class="block scene-net-block" id="sceneNetworkBlock">
      <div class="graph-head">
        <div class="graph-head-title">
          <h2>씬 네트워크</h2>
          <span class="block-meta" data-sn-meta>불러오는 중...</span>
        </div>
        <div class="graph-head-actions">
          <div class="seg-toggle scene-net-limit-toggle" role="group" aria-label="표시 팀 수">
            ${limitChoices.map(n => `
              <button type="button" class="seg-btn ${currentLimit === n ? 'active' : ''}" data-sn-limit="${n}" aria-pressed="${currentLimit === n}">${n}팀</button>
            `).join('')}
          </div>
          <button type="button" class="btn btn-sm" data-sn-expand-modal aria-label="씬 네트워크 크게 보기">크게 보기 ⤢</button>
        </div>
      </div>

      <div class="scene-net-toolbar">
        <div class="scene-net-genres" role="group" aria-label="장르 필터" data-sn-genres>
          <button type="button" class="chip-btn ${currentGenre === '' ? 'active' : ''}" data-sn-genre="" aria-pressed="${currentGenre === ''}">전체</button>
          ${validGenres.map(g => `
            <button type="button" class="chip-btn ${currentGenre === g ? 'active' : ''}" data-sn-genre="${escapeHtml(g)}" aria-pressed="${currentGenre === g}">${escapeHtml(g)}</button>
          `).join('')}
        </div>
        <div class="scene-net-search" data-sn-search-wrap>
          <input type="search" class="scene-net-search-input" data-sn-search placeholder="네트워크 안 팀 검색..." autocomplete="off" aria-label="네트워크 안 팀 검색">
          <div class="scene-net-search-menu" data-sn-search-menu hidden></div>
        </div>
      </div>

      <div class="graph-body-slot" data-sn-inline-slot>
        <div class="graph-surface scene-net-surface" data-sn-surface>
          <div class="graph-stage scene-net-stage" data-sn-stage>
            <canvas class="scene-net-canvas" data-sn-canvas role="img" aria-label="씬 네트워크 그래프"></canvas>
            <div class="graph-float-ctrls" aria-label="그래프 조작">
              <button type="button" class="graph-ctrl-btn" data-sn-zoom="in" title="확대" aria-label="확대">+</button>
              <button type="button" class="graph-ctrl-btn" data-sn-zoom="out" title="축소" aria-label="축소">−</button>
              <button type="button" class="graph-ctrl-btn" data-sn-zoom="fit" title="화면에 맞춤" aria-label="화면에 맞춤">맞춤</button>
              <button type="button" class="graph-ctrl-btn" data-sn-clear hidden>선택 해제</button>
            </div>
            <div class="graph-tooltip" data-sn-tooltip hidden></div>
            <div class="graph-empty" data-sn-empty hidden></div>
          </div>

          <div class="scene-net-legend" data-sn-legend aria-label="씬 묶음 범례"></div>

          <div class="scene-net-card" data-sn-card>
            <span class="graph-insp-hint">노드 클릭 = 함께 선 팀 강조 · 검색으로 팀 찾기 · 굵은 테두리 = ${escapeHtml(TERMS.outcomeTeam)}</span>
          </div>
        </div>
      </div>
    </section>
  `;

  const inlineSlot = hostEl.querySelector('[data-sn-inline-slot]');
  const surfaceEl = hostEl.querySelector('[data-sn-surface]');
  const stageEl = hostEl.querySelector('[data-sn-stage]');
  const canvasEl = hostEl.querySelector('[data-sn-canvas]');
  const metaEl = hostEl.querySelector('[data-sn-meta]');
  const tooltipEl = hostEl.querySelector('[data-sn-tooltip]');
  const emptyEl = hostEl.querySelector('[data-sn-empty]');
  const legendEl = hostEl.querySelector('[data-sn-legend]');
  const cardEl = hostEl.querySelector('[data-sn-card]');
  const clearBtn = hostEl.querySelector('[data-sn-clear]');
  const searchInput = hostEl.querySelector('[data-sn-search]');
  const searchMenu = hostEl.querySelector('[data-sn-search-menu]');
  const searchWrap = hostEl.querySelector('[data-sn-search-wrap]');

  function showEmpty(msg) {
    if (!emptyEl) return;
    emptyEl.textContent = msg;
    emptyEl.hidden = false;
  }

  function hideEmpty() {
    if (emptyEl) emptyEl.hidden = true;
  }

  function nodeColor(n) {
    if (n && n.colorSlot >= 0 && n.colorSlot < pal.sceneColors.length) {
      return pal.sceneColors[n.colorSlot];
    }
    return pal.sceneOther;
  }

  function gradeRingColor(n) {
    return outcomeColor(n?.outcome_grade, pal).fill;
  }

  function updateMeta() {
    if (!metaEl) return;
    const genreTxt = currentGenre || '전체 장르';
    const pieces = [
      genreTxt,
      `${fmtInt(nodes.length)}팀 (후보 ${fmtInt(candidateCount)} · ${TERMS.outcome} ${fmtInt(winnerCount)})`,
      `연결 ${fmtInt(edges.length)}`,
    ];
    metaEl.textContent = pieces.join(' · ');
    if (clearBtn) {
      clearBtn.hidden = !(selectedId || activeCommId !== null);
    }
  }

  function measureCanvas() {
    if (!stageEl || !canvasEl) return;
    const rect = stageEl.getBoundingClientRect();
    if (rect.width < 40 || rect.height < 40) return;
    currentWidth = Math.round(rect.width);
    currentHeight = Math.round(rect.height);
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const targetW = Math.round(currentWidth * dpr);
    const targetH = Math.round(currentHeight * dpr);
    if (canvasEl.width !== targetW || canvasEl.height !== targetH) {
      canvasEl.width = targetW;
      canvasEl.height = targetH;
    }
    if (zoomBehavior) {
      zoomBehavior.extent([[0, 0], [currentWidth, currentHeight]]);
    }
  }

  function requestDraw() {
    if (destroyed) return;
    needsDraw = true;
    if (!rafId) {
      rafId = window.requestAnimationFrame(() => {
        rafId = 0;
        if (!destroyed && needsDraw) {
          needsDraw = false;
          drawCanvas();
        }
      });
    }
  }

  function screenToWorld(sx, sy) {
    const t = transform || window.d3?.zoomIdentity || { x: 0, y: 0, k: 1 };
    return [(sx - t.x) / t.k, (sy - t.y) / t.k];
  }

  function findNodeAtScreen(sx, sy) {
    if (!nodes.length) return null;
    const [wx, wy] = screenToWorld(sx, sy);
    const k = transform?.k || 1;
    const pad = Math.max(4, 7 / Math.sqrt(k));
    let best = null;
    let bestDistSq = Infinity;
    for (let i = nodes.length - 1; i >= 0; i--) {
      const n = nodes[i];
      if (!Number.isFinite(n.x) || !Number.isFinite(n.y)) continue;
      const dx = wx - n.x;
      const dy = wy - n.y;
      const hitR = (n.r || 7) + (n.had_outcome ? 3 : 0) + pad;
      const d2 = dx * dx + dy * dy;
      if (d2 <= hitR * hitR && d2 < bestDistSq) {
        best = n;
        bestDistSq = d2;
      }
    }
    return best;
  }

  function drawCanvas() {
    if (!canvasEl) return;
    const ctx = canvasEl.getContext('2d');
    if (!ctx) return;

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = currentWidth;
    const h = currentHeight;
    if (canvasEl.width !== Math.round(w * dpr) || canvasEl.height !== Math.round(h * dpr)) {
      measureCanvas();
    }

    ctx.save();
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.fillStyle = pal.bg;
    ctx.fillRect(0, 0, w, h);

    if (!nodes.length) {
      ctx.restore();
      return;
    }

    const t = transform || { x: w / 2, y: h / 2, k: 1 };
    const k = t.k || 1;
    const invSqrtK = 1 / Math.max(0.65, Math.sqrt(k));

    // Determine focus set
    const focusNodeId = selectedId || hoveredId || null;
    let focusSet = null;
    if (focusNodeId && nodeById.has(focusNodeId)) {
      focusSet = new Set([focusNodeId]);
      const nbrs = adjMap.get(focusNodeId) || [];
      for (const item of nbrs) focusSet.add(item.neighbor.id);
    } else if (activeCommId !== null) {
      focusSet = new Set();
      for (const n of nodes) {
        if (n.communityId === activeCommId) focusSet.add(n.id);
      }
    }

    ctx.save();
    ctx.translate(t.x, t.y);
    ctx.scale(k, k);

    // 1. Edges (dimmed first, highlighted on top)
    ctx.lineCap = 'round';
    if (focusSet) {
      ctx.strokeStyle = pal.edge;
      ctx.globalAlpha = 0.08;
      for (let i = 0; i < edges.length; i++) {
        const e = edges[i];
        const s = e.source;
        const g = e.target;
        if (!s || !g || !Number.isFinite(s.x) || !Number.isFinite(g.x)) continue;
        const isHi = focusNodeId
          ? (s.id === focusNodeId || g.id === focusNodeId)
          : (focusSet.has(s.id) && focusSet.has(g.id));
        if (isHi) continue;
        ctx.lineWidth = Math.min(3.4, 0.55 + Math.sqrt(e.weight) * 0.7) * invSqrtK;
        ctx.beginPath();
        ctx.moveTo(s.x, s.y);
        ctx.lineTo(g.x, g.y);
        ctx.stroke();
      }

      ctx.strokeStyle = pal.edgeHi;
      ctx.globalAlpha = 0.78;
      for (let i = 0; i < edges.length; i++) {
        const e = edges[i];
        const s = e.source;
        const g = e.target;
        if (!s || !g || !Number.isFinite(s.x) || !Number.isFinite(g.x)) continue;
        const isHi = focusNodeId
          ? (s.id === focusNodeId || g.id === focusNodeId)
          : (focusSet.has(s.id) && focusSet.has(g.id));
        if (!isHi) continue;
        ctx.lineWidth = Math.min(4.6, 1.0 + Math.sqrt(e.weight) * 1.05) * invSqrtK;
        ctx.beginPath();
        ctx.moveTo(s.x, s.y);
        ctx.lineTo(g.x, g.y);
        ctx.stroke();
      }
    } else {
      ctx.strokeStyle = pal.edge;
      ctx.globalAlpha = 0.36;
      for (let i = 0; i < edges.length; i++) {
        const e = edges[i];
        const s = e.source;
        const g = e.target;
        if (!s || !g || !Number.isFinite(s.x) || !Number.isFinite(g.x)) continue;
        ctx.lineWidth = Math.min(4.2, 0.65 + Math.sqrt(e.weight) * 0.85) * invSqrtK;
        ctx.beginPath();
        ctx.moveTo(s.x, s.y);
        ctx.lineTo(g.x, g.y);
        ctx.stroke();
      }
    }

    // 2. Nodes (dimmed pass, then highlighted pass)
    const drawSingleNode = (n, alpha) => {
      if (!Number.isFinite(n.x) || !Number.isFinite(n.y)) return;
      const r = n.r || 7;
      ctx.globalAlpha = alpha;

      // Selection / hover halo
      if (n.id === selectedId) {
        ctx.beginPath();
        ctx.arc(n.x, n.y, r + (n.had_outcome ? 6.5 : 4.5) * invSqrtK, 0, Math.PI * 2);
        ctx.strokeStyle = pal.edgeHi;
        ctx.lineWidth = 2.4 * invSqrtK;
        ctx.stroke();
      } else if (n.id === hoveredId) {
        ctx.beginPath();
        ctx.arc(n.x, n.y, r + (n.had_outcome ? 5.5 : 3.5) * invSqrtK, 0, Math.PI * 2);
        ctx.strokeStyle = pal.ink;
        ctx.lineWidth = 1.6 * invSqrtK;
        ctx.stroke();
      }

      // Winner distinct double border ring (S/A/B grade)
      if (n.had_outcome) {
        ctx.beginPath();
        ctx.arc(n.x, n.y, r + 2.7 * invSqrtK, 0, Math.PI * 2);
        ctx.fillStyle = pal.bg;
        ctx.fill();
        ctx.strokeStyle = gradeRingColor(n);
        ctx.lineWidth = 2.4 * invSqrtK;
        ctx.stroke();
      }

      // Main circle (colored by scene community)
      ctx.beginPath();
      ctx.arc(n.x, n.y, r, 0, Math.PI * 2);
      ctx.fillStyle = nodeColor(n);
      ctx.fill();

      if (!n.had_outcome) {
        ctx.strokeStyle = pal.bg;
        ctx.lineWidth = 1.2 * invSqrtK;
        ctx.stroke();
      }
    };

    if (focusSet) {
      for (let i = 0; i < nodes.length; i++) {
        const n = nodes[i];
        if (!focusSet.has(n.id) && n.id !== hoveredId) drawSingleNode(n, 0.14);
      }
      for (let i = 0; i < nodes.length; i++) {
        const n = nodes[i];
        if (focusSet.has(n.id) || n.id === hoveredId) drawSingleNode(n, 1);
      }
    } else {
      for (let i = 0; i < nodes.length; i++) {
        drawSingleNode(nodes[i], 0.94);
      }
    }

    ctx.restore(); // back to screen pixel coordinates for crisp, non-blurry labels

    // 3. Labels in screen space with overlap culling
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.lineJoin = 'round';

    const labelCandidates = [];
    if (focusNodeId && nodeById.has(focusNodeId)) {
      const center = nodeById.get(focusNodeId);
      labelCandidates.push({ node: center, priority: 100000, isPrimary: true });
      const nbrs = (adjMap.get(focusNodeId) || []).slice(0, 28);
      for (const item of nbrs) {
        labelCandidates.push({
          node: item.neighbor,
          priority: 1000 + item.weight * 50 + item.neighbor.score,
          isPrimary: false,
        });
      }
      if (hoveredId && hoveredId !== focusNodeId && nodeById.has(hoveredId) && !focusSet?.has(hoveredId)) {
        labelCandidates.push({ node: nodeById.get(hoveredId), priority: 90000, isPrimary: true });
      }
    } else if (activeCommId !== null && focusSet) {
      for (const n of nodes) {
        if (focusSet.has(n.id)) {
          labelCandidates.push({
            node: n,
            priority: n.score * 10 + n.degree * 2 + (n.had_outcome ? 20 : 0),
            isPrimary: false,
          });
        }
      }
    } else {
      const maxLabels = k < 0.85 ? 16 : k < 1.35 ? 28 : k < 2.1 ? 65 : nodes.length;
      const sorted = [...nodes].sort((a, b) => {
        const pa = a.score * 4 + a.degree * 1.2 + (a.had_outcome ? 10 : 0);
        const pb = b.score * 4 + b.degree * 1.2 + (b.had_outcome ? 10 : 0);
        return pb - pa;
      });
      for (let i = 0; i < Math.min(maxLabels, sorted.length); i++) {
        labelCandidates.push({
          node: sorted[i],
          priority: 1000 - i,
          isPrimary: false,
        });
      }
    }

    labelCandidates.sort((a, b) => b.priority - a.priority);
    const placedBoxes = [];

    for (const item of labelCandidates) {
      const n = item.node;
      if (!Number.isFinite(n.x) || !Number.isFinite(n.y)) continue;
      const sx = n.x * k + t.x;
      const sy = n.y * k + t.y;
      if (sx < -40 || sx > w + 40 || sy < -24 || sy > h + 24) continue;

      const fontSize = item.isPrimary ? 12.5 : (n.had_outcome ? 11.5 : 11);
      const fontWeight = (item.isPrimary || n.had_outcome) ? '700' : '600';
      ctx.font = `${fontWeight} ${fontSize}px -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", "Pretendard", sans-serif`;

      const text = shortLabel(n.display_name, item.isPrimary ? 20 : 14);
      const textW = ctx.measureText(text).width;
      const sr = ((n.r || 7) + (n.had_outcome ? 3.5 : 1.5)) * k;
      const ly = sy + Math.max(7, sr) + 3;
      const bx0 = sx - textW / 2 - 4;
      const bx1 = sx + textW / 2 + 4;
      const by0 = ly - 2;
      const by1 = ly + fontSize + 3;

      if (!item.isPrimary) {
        let overlaps = false;
        for (let j = 0; j < placedBoxes.length; j++) {
          const b = placedBoxes[j];
          if (!(bx1 < b[0] || bx0 > b[2] || by1 < b[1] || by0 > b[3])) {
            overlaps = true;
            break;
          }
        }
        if (overlaps) continue;
      }
      placedBoxes.push([bx0, by0, bx1, by1]);

      ctx.globalAlpha = 1;
      ctx.strokeStyle = pal.bg;
      ctx.lineWidth = 3.6;
      ctx.strokeText(text, sx, ly);
      ctx.fillStyle = item.isPrimary ? pal.ink : (n.had_outcome ? pal.ink : pal.muted);
      ctx.fillText(text, sx, ly);
    }

    ctx.restore();
  }

  function renderLegend() {
    if (!legendEl) return;
    const topComms = communities.slice(0, 8);
    const hasOther = nodes.some(n => n.colorSlot < 0);
    const itemsHtml = topComms.map(c => {
      const color = pal.sceneColors[c.colorSlot] || pal.sceneOther;
      const venueTag = c.topVenues?.[0] ? ` · ${shortLabel(c.topVenues[0], 11)}` : '';
      const isActive = activeCommId === c.id;
      return `
        <button type="button" class="scene-leg-btn ${isActive ? 'is-active' : ''}" data-sn-comm="${c.id}" aria-pressed="${isActive}" title="묶음 ${c.id} (${c.count}팀) 강조">
          <i class="scene-leg-dot" style="background:${color};"></i>
          <span>묶음 ${fmtInt(c.id)}${escapeHtml(venueTag)}</span>
          <span class="scene-leg-cnt">${fmtInt(c.count)}</span>
        </button>
      `;
    }).join('');

    const otherHtml = hasOther
      ? `<span class="scene-leg-static"><i class="scene-leg-dot" style="background:${pal.sceneOther};"></i>기타</span>`
      : '';

    const winnerHtml = `
      <span class="scene-leg-static scene-leg-winner" title="이미 수상·선정된 팀은 S/A/B 등급 색상 테두리로 표시됩니다">
        <i class="scene-leg-ring" style="border-color:${pal.gradeS};"></i>
        <span>${escapeHtml(TERMS.outcomeTeam)}(테두리)</span>
      </span>
    `;

    legendEl.innerHTML = `${itemsHtml}${otherHtml}${winnerHtml}`;
    legendEl.querySelectorAll('[data-sn-comm]').forEach(btn => {
      btn.addEventListener('click', () => {
        const cid = Number(btn.dataset.snComm);
        selectedId = null;
        activeCommId = (activeCommId === cid) ? null : cid;
        renderLegend();
        renderCard();
        updateMeta();
        requestDraw();
      });
    });
  }

  function renderCard() {
    if (!cardEl) return;
    const node = selectedId ? nodeById.get(selectedId) : null;
    if (!node) {
      if (activeCommId !== null) {
        const comm = communities.find(c => c.id === activeCommId);
        const venuesTxt = comm?.topVenues?.length ? comm.topVenues.join(' · ') : '';
        cardEl.innerHTML = `
          <div class="scene-card-comm-bar">
            <span><strong>씬 묶음 ${fmtInt(activeCommId)}</strong>${venuesTxt ? ` (${escapeHtml(venuesTxt)})` : ''} · 현재 그래프 내 <strong>${fmtInt(comm?.count || 0)}팀</strong> 강조 중</span>
            <button type="button" class="btn btn-sm" data-sn-clear-comm>전체 보기</button>
          </div>
        `;
        cardEl.querySelector('[data-sn-clear-comm]')?.addEventListener('click', () => {
          activeCommId = null;
          renderLegend();
          renderCard();
          updateMeta();
          requestDraw();
        });
        return;
      }
      cardEl.innerHTML = `
        <span class="graph-insp-hint">노드 클릭 = 함께 선 팀 강조 · 검색으로 팀 찾기 · 굵은 테두리 = ${escapeHtml(TERMS.outcomeTeam)}</span>
      `;
      return;
    }

    const nbrs = adjMap.get(node.id) || [];
    const winnerNbrs = nbrs.filter(x => x.neighbor.had_outcome).length;
    const candNbrs = nbrs.length - winnerNbrs;
    const ng = nextGigByTeam?.get(node.team_key) || null;
    const commText = node.communityId !== null
      ? `씬 묶음 ${fmtInt(node.communityId)}${node.communityVenues?.length ? ` (${node.communityVenues.join(' · ')})` : ''}`
      : '독립 / 소규모 씬';
    const badgeHtml = node.had_outcome
      ? `<span class="scene-winner-pill is-grade-${escapeHtml((node.outcome_grade || 'b').toLowerCase())}">${escapeHtml(node.outcome_grade ? `${node.outcome_grade}등급 ${TERMS.outcome}` : TERMS.outcomeTeam)}${node.outcome_label ? ` · ${escapeHtml(shortLabel(node.outcome_label, 14))}` : ''}</span>`
      : (node.cand_rank ? `<span class="rank-pill">#${fmtInt(node.cand_rank)} 후보</span>` : '<span class="rank-pill">후보</span>');

    const topNbrs = nbrs.slice(0, 12);
    const moreNbrs = nbrs.length - topNbrs.length;

    cardEl.innerHTML = `
      <div class="scene-card-top">
        <div class="scene-card-ident">
          ${avatarHtml(node.team_key, node.display_name, 38, { shape: 'circle', genre: node.primary_genre })}
          <div class="scene-card-text">
            <div class="scene-card-title-row">
              <strong>${escapeHtml(node.display_name)}</strong>
              ${badgeHtml}
              <span class="scene-card-score mono">${fmtNum(node.score, 2)}점</span>
            </div>
            <div class="scene-card-meta small muted">
              ${node.primary_genre ? `<span>${escapeHtml(node.primary_genre)}</span> · ` : ''}
              <span>${escapeHtml(commText)}</span> ·
              <span>최근 1년 공연 ${fmtInt(node.gigs_1y)}회 · 공연장 ${fmtInt(node.venues)}곳</span>
            </div>
            ${ng ? `<div class="scene-card-gig"><span class="next-gig-chip">다음 공연 ${escapeHtml(formatNextGigText(ng))}</span></div>` : ''}
          </div>
        </div>
        <div class="scene-card-actions">
          <a class="btn btn-sm btn-primary" href="#/team/${encodeURIComponent(node.team_key)}" data-sn-open-team>팀 상세 →</a>
          <button type="button" class="btn btn-sm" data-sn-card-close aria-label="선택 닫기">닫기</button>
        </div>
      </div>
      <div class="scene-card-nbrs">
        <div class="scene-card-nbrs-head small muted">
          같은 무대 연결 <strong>${fmtInt(nbrs.length)}팀</strong>${nbrs.length ? ` (신인 후보 ${fmtInt(candNbrs)} · ${escapeHtml(TERMS.outcome)} ${fmtInt(winnerNbrs)})` : ''}
        </div>
        ${topNbrs.length ? `
          <div class="scene-card-nbr-chips">
            ${topNbrs.map(item => `
              <button type="button" class="scene-nbr-chip ${item.neighbor.had_outcome ? 'is-winner' : ''}" data-sn-jump="${escapeHtml(item.neighbor.id)}" title="${escapeHtml(item.detail || '같은 무대')}">
                <i class="scene-leg-dot" style="background:${nodeColor(item.neighbor)};"></i>
                <span>${escapeHtml(item.neighbor.display_name)}</span>
                ${item.neighbor.had_outcome
                  ? `<em class="scene-nbr-grade">${escapeHtml(item.neighbor.outcome_grade || TERMS.outcome)}</em>`
                  : (item.neighbor.cand_rank ? `<em class="scene-nbr-rank">#${fmtInt(item.neighbor.cand_rank)}</em>` : '')}
                <span class="scene-nbr-wt mono">${Math.round(item.weight)}회</span>
              </button>
            `).join('')}
            ${moreNbrs > 0 ? `<span class="small muted">외 ${fmtInt(moreNbrs)}팀</span>` : ''}
          </div>
        ` : '<p class="small muted" style="margin:4px 0 0 0;">현재 선택된 팀 수 범위 안에서 같은 무대 연결이 없습니다.</p>'}
      </div>
    `;

    wireAvatarFallbacks(cardEl);

    cardEl.querySelector('[data-sn-open-team]')?.addEventListener('click', () => {
      closeModal();
    });
    cardEl.querySelector('[data-sn-card-close]')?.addEventListener('click', () => {
      selectedId = null;
      renderCard();
      updateMeta();
      requestDraw();
    });
    cardEl.querySelectorAll('[data-sn-jump]').forEach(btn => {
      btn.addEventListener('click', () => {
        const targetId = btn.dataset.snJump;
        if (targetId && nodeById.has(targetId)) {
          focusOnTeam(targetId, true);
        }
      });
    });
  }

  function showTooltip(node, clientX, clientY) {
    if (!tooltipEl || !stageEl || !node) return;
    const rect = stageEl.getBoundingClientRect();
    const x = Math.max(12, Math.min(rect.width - 210, clientX - rect.left + 14));
    const y = Math.max(12, Math.min(rect.height - 64, clientY - rect.top - 10));
    const roleTag = node.had_outcome
      ? `${node.outcome_grade || ''}등급 ${TERMS.outcome}`
      : (node.cand_rank ? `후보 #${node.cand_rank}` : '후보');
    const commTag = node.communityId !== null ? `묶음 ${node.communityId}` : '기타';
    tooltipEl.innerHTML = `
      <strong>${escapeHtml(node.display_name)}</strong>
      <span class="graph-tt-sub">${escapeHtml(roleTag)} · ${fmtNum(node.score, 1)}점 · ${escapeHtml(commTag)} · 연결 ${fmtInt(node.degree)}</span>
    `;
    tooltipEl.style.left = `${x}px`;
    tooltipEl.style.top = `${y}px`;
    tooltipEl.hidden = false;
  }

  function hideTooltip() {
    if (tooltipEl) tooltipEl.hidden = true;
  }

  function fitToView(duration = 260) {
    if (!window.d3 || !canvasSel || !zoomBehavior || !nodes.length) return;
    measureCanvas();
    let minX = Infinity;
    let maxX = -Infinity;
    let minY = Infinity;
    let maxY = -Infinity;
    for (const n of nodes) {
      if (!Number.isFinite(n.x) || !Number.isFinite(n.y)) continue;
      const r = (n.r || 8) + 8;
      if (n.x - r < minX) minX = n.x - r;
      if (n.x + r > maxX) maxX = n.x + r;
      if (n.y - r < minY) minY = n.y - r;
      if (n.y + r > maxY) maxY = n.y + r;
    }
    if (!Number.isFinite(minX)) return;
    const pad = 42;
    const bw = Math.max(120, maxX - minX);
    const bh = Math.max(120, maxY - minY);
    const scale = Math.max(0.35, Math.min(1.85, Math.min((currentWidth - pad * 2) / bw, (currentHeight - pad * 2) / bh)));
    const cx = (minX + maxX) / 2;
    const cy = (minY + maxY) / 2;
    const nextT = window.d3.zoomIdentity
      .translate(currentWidth / 2 - cx * scale, currentHeight / 2 - cy * scale)
      .scale(scale);

    fittedWidth = currentWidth;
    fittedHeight = currentHeight;
    canvasSel.interrupt();
    if (duration > 0) {
      canvasSel.transition().duration(duration).call(zoomBehavior.transform, nextT);
    } else {
      canvasSel.call(zoomBehavior.transform, nextT);
    }
  }

  function focusOnTeam(teamId, animate = true) {
    const n = nodeById.get(teamId);
    if (!n) return;
    activeCommId = null;
    selectedId = n.id;
    renderLegend();
    renderCard();
    updateMeta();
    requestDraw();

    if (window.d3 && canvasSel && zoomBehavior && Number.isFinite(n.x) && Number.isFinite(n.y)) {
      measureCanvas();
      fittedWidth = currentWidth;
      fittedHeight = currentHeight;
      const targetK = Math.max(1.45, Math.min(2.4, transform?.k || 1.65));
      const nextT = window.d3.zoomIdentity
        .translate(currentWidth / 2 - n.x * targetK, currentHeight / 2 - n.y * targetK)
        .scale(targetK);
      canvasSel.interrupt();
      if (animate) {
        canvasSel.transition().duration(320).call(zoomBehavior.transform, nextT);
      } else {
        canvasSel.call(zoomBehavior.transform, nextT);
      }
    }
  }

  function ensureCanvasInteractions() {
    if (!window.d3 || !canvasEl || canvasSel) return;
    const d3 = window.d3;
    measureCanvas();
    transform = d3.zoomIdentity;
    canvasSel = d3.select(canvasEl);

    zoomBehavior = d3.zoom()
      .extent([[0, 0], [currentWidth, currentHeight]])
      .scaleExtent([0.28, 4.5])
      .on('zoom', (event) => {
        transform = event.transform;
        requestDraw();
      });

    let dragStartScreen = null;
    let draggedMoved = false;

    const dragBehavior = d3.drag()
      .subject((event) => {
        const [sx, sy] = d3.pointer(event.sourceEvent || event, canvasEl);
        return findNodeAtScreen(sx, sy) || undefined;
      })
      .on('start', (event) => {
        const n = event.subject;
        if (!n) return;
        const [sx, sy] = d3.pointer(event.sourceEvent || event, canvasEl);
        dragStartScreen = [sx, sy];
        draggedMoved = false;
        n.fx = n.x;
        n.fy = n.y;
        hideTooltip();
      })
      .on('drag', (event) => {
        const n = event.subject;
        if (!n) return;
        const [sx, sy] = d3.pointer(event.sourceEvent || event, canvasEl);
        if (dragStartScreen) {
          const dist = Math.hypot(sx - dragStartScreen[0], sy - dragStartScreen[1]);
          if (dist > 4) {
            draggedMoved = true;
            if (simulation && !event.active) simulation.alphaTarget(0.18).restart();
          }
        }
        if (draggedMoved) {
          const [wx, wy] = screenToWorld(sx, sy);
          n.fx = wx;
          n.fy = wy;
          requestDraw();
        }
      })
      .on('end', (event) => {
        const n = event.subject;
        if (!n) return;
        if (simulation && !event.active) simulation.alphaTarget(0);
        n.fx = null;
        n.fy = null;
        if (!draggedMoved) {
          // Click on node
          const now = Date.now();
          if (lastClickNodeId === n.id && now - lastClickTime < 340) {
            lastClickTime = 0;
            lastClickNodeId = null;
            closeModal();
            navigateTo(`#/team/${encodeURIComponent(n.team_key)}`);
            return;
          }
          lastClickTime = now;
          lastClickNodeId = n.id;
          activeCommId = null;
          selectedId = (selectedId === n.id) ? null : n.id;
          renderLegend();
          renderCard();
          updateMeta();
          requestDraw();
        }
      });

    // Attach drag BEFORE zoom so dragging a node works while empty canvas pans/zooms
    canvasSel.call(dragBehavior);
    canvasSel.call(zoomBehavior);

    // Click on empty background clears selection
    let bgDownPos = null;
    canvasEl.addEventListener('pointerdown', (e) => {
      const rect = canvasEl.getBoundingClientRect();
      const hit = findNodeAtScreen(e.clientX - rect.left, e.clientY - rect.top);
      bgDownPos = hit ? null : [e.clientX, e.clientY];
    });
    canvasEl.addEventListener('pointerup', (e) => {
      if (!bgDownPos) return;
      const dist = Math.hypot(e.clientX - bgDownPos[0], e.clientY - bgDownPos[1]);
      bgDownPos = null;
      if (dist <= 5 && (selectedId !== null || activeCommId !== null)) {
        selectedId = null;
        activeCommId = null;
        renderLegend();
        renderCard();
        updateMeta();
        requestDraw();
      }
    });

    canvasEl.addEventListener('pointermove', (e) => {
      if (e.buttons) return;
      const rect = canvasEl.getBoundingClientRect();
      const hit = findNodeAtScreen(e.clientX - rect.left, e.clientY - rect.top);
      const nextHover = hit ? hit.id : null;
      if (nextHover !== hoveredId) {
        hoveredId = nextHover;
        canvasEl.style.cursor = hit ? 'pointer' : 'grab';
        requestDraw();
      }
      if (hit) showTooltip(hit, e.clientX, e.clientY);
      else hideTooltip();
    });

    canvasEl.addEventListener('pointerleave', () => {
      if (hoveredId !== null) {
        hoveredId = null;
        requestDraw();
      }
      hideTooltip();
    });
  }

  function startSimulation() {
    if (!window.d3) return;
    if (simulation) {
      try { simulation.stop(); } catch (_) {}
      simulation = null;
    }
    if (!nodes.length) {
      requestDraw();
      return;
    }

    const d3 = window.d3;
    measureCanvas();
    ensureCanvasInteractions();

    // Compute score -> radius mapping
    let minScore = Infinity;
    let maxScore = -Infinity;
    for (const n of nodes) {
      if (n.score < minScore) minScore = n.score;
      if (n.score > maxScore) maxScore = n.score;
    }
    const span = Math.max(0.5, maxScore - minScore);
    for (const n of nodes) {
      const norm = Math.max(0, Math.min(1, (n.score - minScore) / span));
      n.r = 5.5 + Math.pow(norm, 0.85) * 10.5;
    }

    // Deterministic initial placement gently grouped by community slot
    const golden = Math.PI * (3 - Math.sqrt(5));
    const slotCount = Math.max(1, Math.min(8, communities.length));
    nodes.forEach((n, idx) => {
      const a = idx * golden;
      const rad = 28 + Math.sqrt(idx + 1) * 18;
      if (n.colorSlot >= 0) {
        const sectorAngle = (n.colorSlot / slotCount) * Math.PI * 2;
        const cx = Math.cos(sectorAngle) * 110;
        const cy = Math.sin(sectorAngle) * 110;
        n.x = cx + Math.cos(a) * (rad * 0.55);
        n.y = cy + Math.sin(a) * (rad * 0.55);
      } else {
        n.x = Math.cos(a) * (rad * 1.1);
        n.y = Math.sin(a) * (rad * 1.1);
      }
      n.vx = 0;
      n.vy = 0;
    });

    const chargeBase = nodes.length > 220 ? -82 : nodes.length > 140 ? -102 : -125;

    simulation = d3.forceSimulation(nodes)
      .force('link', d3.forceLink(edges)
        .id(d => d.id)
        .distance(e => Math.max(34, 78 - Math.min(34, Math.sqrt(e.weight) * 12)))
        .strength(e => Math.min(0.68, 0.18 + Math.sqrt(e.weight) * 0.1)))
      .force('charge', d3.forceManyBody()
        .strength(n => chargeBase - (n.r || 8) * 3.2)
        .distanceMax(340))
      .force('collide', d3.forceCollide(n => (n.r || 8) + (n.had_outcome ? 5 : 3.2)).iterations(2))
      .force('x', d3.forceX(0).strength(0.055))
      .force('y', d3.forceY(0).strength(0.055))
      .alphaDecay(0.032)
      .on('tick', requestDraw);

    // Pre-tick synchronously so initial render is already cleanly clustered
    simulation.stop();
    const preTicks = nodes.length > 200 ? 75 : 95;
    for (let i = 0; i < preTicks; i++) {
      simulation.tick();
    }
    fitToView(0);
    requestDraw();
    simulation.alpha(0.16).restart();
  }

  async function loadNetwork() {
    const seq = ++loadSeq;
    if (!window.d3) {
      showEmpty('그래프 라이브러리(D3)를 불러오지 못했습니다.');
      return;
    }
    if (metaEl) metaEl.textContent = '불러오는 중...';
    showEmpty('씬 네트워크를 계산하는 중...');

    try {
      const res = await querySceneNetwork({ limit: currentLimit, genre: currentGenre });
      if (destroyed || seq !== loadSeq) return;

      nodes = res.nodes || [];
      edges = res.edges || [];
      communities = res.communities || [];
      winnerCount = res.winnerCount || 0;
      candidateCount = res.candidateCount || 0;

      nodeById = new Map(nodes.map(n => [n.id, n]));
      adjMap = new Map(nodes.map(n => [n.id, []]));
      for (const e of edges) {
        const a = nodeById.get(e.source);
        const b = nodeById.get(e.target);
        if (!a || !b) continue;
        adjMap.get(a.id).push({ neighbor: b, weight: e.weight, detail: e.detail, last_date: e.last_date });
        adjMap.get(b.id).push({ neighbor: a, weight: e.weight, detail: e.detail, last_date: e.last_date });
      }
      for (const list of adjMap.values()) {
        list.sort((x, y) => (y.weight - x.weight) || (y.neighbor.score - x.neighbor.score));
      }

      if (selectedId && !nodeById.has(selectedId)) selectedId = null;
      if (activeCommId !== null && !communities.some(c => c.id === activeCommId)) activeCommId = null;
      hoveredId = null;
      pal = readScenePalette();

      if (!nodes.length) {
        showEmpty(currentGenre ? `'${currentGenre}' 장르에 표시할 팀이 없습니다.` : '표시할 팀 데이터가 없습니다.');
      } else {
        hideEmpty();
      }

      updateMeta();
      renderLegend();
      renderCard();
      startSimulation();
    } catch (err) {
      if (destroyed || seq !== loadSeq) return;
      showEmpty(`씬 네트워크를 불러오지 못했습니다: ${err?.message || err}`);
      if (metaEl) metaEl.textContent = '불러오기 실패';
    }
  }

  // ---- Search autocomplete inside current network ----
  function closeSearchMenu() {
    if (searchMenu) searchMenu.hidden = true;
  }

  function renderSearchMatches(qRaw) {
    if (!searchMenu) return;
    const q = String(qRaw || '').trim().toLowerCase();
    if (!q || !nodes.length) {
      closeSearchMenu();
      return;
    }
    const hits = nodes
      .filter(n => n.display_name.toLowerCase().includes(q) || n.team_key.toLowerCase().includes(q))
      .sort((a, b) => {
        const aStart = a.display_name.toLowerCase().startsWith(q) ? 0 : 1;
        const bStart = b.display_name.toLowerCase().startsWith(q) ? 0 : 1;
        if (aStart !== bStart) return aStart - bStart;
        return b.score - a.score;
      })
      .slice(0, 8);

    if (!hits.length) {
      searchMenu.innerHTML = `<div class="scene-search-empty">현재 네트워크(${fmtInt(nodes.length)}팀)에 일치하는 팀 없음</div>`;
      searchMenu.hidden = false;
      return;
    }

    searchMenu.innerHTML = hits.map(n => `
      <button type="button" class="scene-search-opt" data-sn-pick="${escapeHtml(n.id)}">
        <span class="scene-search-opt-left">
          <i class="scene-leg-dot" style="background:${nodeColor(n)};"></i>
          <strong>${escapeHtml(n.display_name)}</strong>
          ${n.had_outcome
            ? `<em class="scene-nbr-grade">${escapeHtml(n.outcome_grade || TERMS.outcome)}</em>`
            : (n.cand_rank ? `<em class="scene-nbr-rank">#${fmtInt(n.cand_rank)}</em>` : '')}
        </span>
        <span class="small muted mono">${fmtNum(n.score, 1)}점 · 연결 ${fmtInt(n.degree)}</span>
      </button>
    `).join('');
    searchMenu.hidden = false;

    searchMenu.querySelectorAll('[data-sn-pick]').forEach(btn => {
      btn.addEventListener('click', () => {
        const id = btn.dataset.snPick;
        const picked = nodeById.get(id);
        if (picked) {
          if (searchInput) searchInput.value = picked.display_name;
          closeSearchMenu();
          focusOnTeam(picked.id, true);
        }
      });
    });
  }

  searchInput?.addEventListener('input', () => renderSearchMatches(searchInput.value));
  searchInput?.addEventListener('focus', () => {
    if (searchInput.value.trim()) renderSearchMatches(searchInput.value);
  });
  searchInput?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      const first = searchMenu?.querySelector('[data-sn-pick]');
      if (first) {
        e.preventDefault();
        first.click();
      }
    } else if (e.key === 'Escape') {
      closeSearchMenu();
    }
  });

  function onDocClick(e) {
    if (searchWrap && !searchWrap.contains(e.target)) closeSearchMenu();
  }
  document.addEventListener('click', onDocClick);

  // ---- Genre chip clicks (syncs with URL hash #/venues?genre=…) ----
  hostEl.querySelectorAll('[data-sn-genre]').forEach(btn => {
    btn.addEventListener('click', () => {
      const g = btn.dataset.snGenre || '';
      if (g === currentGenre) return;
      currentGenre = g;
      appState.cfg.genre = g;
      syncHash(true);
      hostEl.querySelectorAll('[data-sn-genre]').forEach(b => {
        const active = (b.dataset.snGenre || '') === currentGenre;
        b.classList.toggle('active', active);
        b.setAttribute('aria-pressed', active ? 'true' : 'false');
      });
      if (searchInput) searchInput.value = '';
      closeSearchMenu();
      selectedId = null;
      activeCommId = null;
      loadNetwork();
    });
  });

  // ---- Limit selector (100 / 150 / 250 / 300) ----
  hostEl.querySelectorAll('[data-sn-limit]').forEach(btn => {
    btn.addEventListener('click', () => {
      const lim = Number(btn.dataset.snLimit) || 150;
      if (lim === currentLimit) return;
      currentLimit = lim;
      hostEl.querySelectorAll('[data-sn-limit]').forEach(b => {
        const active = Number(b.dataset.snLimit) === currentLimit;
        b.classList.toggle('active', active);
        b.setAttribute('aria-pressed', active ? 'true' : 'false');
      });
      loadNetwork();
    });
  });

  // ---- Floating zoom & clear controls ----
  hostEl.querySelectorAll('[data-sn-zoom]').forEach(btn => {
    btn.addEventListener('click', () => {
      if (!canvasSel || !zoomBehavior) return;
      const mode = btn.dataset.snZoom;
      canvasSel.interrupt();
      if (mode === 'in') canvasSel.transition().duration(180).call(zoomBehavior.scaleBy, 1.32);
      else if (mode === 'out') canvasSel.transition().duration(180).call(zoomBehavior.scaleBy, 1 / 1.32);
      else fitToView(240);
    });
  });

  clearBtn?.addEventListener('click', () => {
    selectedId = null;
    activeCommId = null;
    renderLegend();
    renderCard();
    updateMeta();
    requestDraw();
  });

  // ---- Fullscreen modal ----
  function onEscKey(e) {
    if (e.key === 'Escape' && isModalOpen) closeModal();
  }

  function openModal() {
    if (isModalOpen || destroyed) return;
    isModalOpen = true;
    modalBackdrop = document.createElement('div');
    modalBackdrop.className = 'graph-modal-backdrop';
    modalBackdrop.innerHTML = `
      <div class="graph-modal" role="dialog" aria-modal="true" aria-label="씬 네트워크 크게 보기">
        <div class="graph-modal-head">
          <div>
            <h2 class="graph-modal-title">씬 네트워크 · ${escapeHtml(currentGenre || '전체')}</h2>
            <span class="small muted">드래그·휠 확대 · 노드 클릭 = 1-hop 이웃 강조</span>
          </div>
          <button type="button" class="btn btn-sm" data-sn-modal-close>닫기 (Esc)</button>
        </div>
        <div class="graph-modal-body" data-sn-modal-slot></div>
      </div>
    `;
    modalSlot = modalBackdrop.querySelector('[data-sn-modal-slot]');
    surfaceEl.classList.add('is-expanded');
    modalSlot.appendChild(surfaceEl);
    document.body.appendChild(modalBackdrop);
    document.body.classList.add('graph-modal-open');

    modalBackdrop.addEventListener('click', (e) => {
      if (e.target === modalBackdrop) closeModal();
    });
    modalBackdrop.querySelector('[data-sn-modal-close]')?.addEventListener('click', closeModal);
    document.addEventListener('keydown', onEscKey);

    requestAnimationFrame(() => {
      if (!destroyed) {
        measureCanvas();
        fitToView(180);
      }
    });
  }

  function closeModal() {
    if (!isModalOpen) return;
    isModalOpen = false;
    document.removeEventListener('keydown', onEscKey);
    document.body.classList.remove('graph-modal-open');
    if (canvasSel) {
      try { canvasSel.interrupt(); } catch (_) {}
    }
    surfaceEl.classList.remove('is-expanded');
    if (inlineSlot && surfaceEl) inlineSlot.appendChild(surfaceEl);
    if (modalBackdrop) {
      modalBackdrop.remove();
      modalBackdrop = null;
      modalSlot = null;
    }
    if (!destroyed) {
      requestAnimationFrame(() => {
        if (!destroyed) {
          measureCanvas();
          fitToView(180);
        }
      });
    }
  }

  hostEl.querySelector('[data-sn-expand-modal]')?.addEventListener('click', openModal);

  // ---- Theme & Resize observers ----
  themeObserver = new MutationObserver(() => {
    if (destroyed) return;
    pal = readScenePalette();
    renderLegend();
    requestDraw();
  });
  themeObserver.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ['data-theme'],
  });

  if (typeof ResizeObserver !== 'undefined' && stageEl) {
    resizeObserver = new ResizeObserver(() => {
      if (destroyed || !stageEl.isConnected) return;
      measureCanvas();
      const bigResize = fittedWidth > 0 && (
        Math.abs(currentWidth - fittedWidth) > 36 || Math.abs(currentHeight - fittedHeight) > 36
      );
      if (bigResize && nodes.length) {
        if (selectedId && nodeById.has(selectedId)) focusOnTeam(selectedId, false);
        else fitToView(0);
      } else {
        requestDraw();
      }
    });
    resizeObserver.observe(stageEl);
  }

  function destroy() {
    if (destroyed) return;
    destroyed = true;
    document.removeEventListener('click', onDocClick);
    if (rafId) {
      cancelAnimationFrame(rafId);
      rafId = 0;
    }
    if (canvasSel) {
      try { canvasSel.interrupt(); } catch (_) {}
    }
    closeModal();
    if (simulation) {
      try { simulation.stop(); } catch (_) {}
      simulation = null;
    }
    if (themeObserver) {
      try { themeObserver.disconnect(); } catch (_) {}
      themeObserver = null;
    }
    if (resizeObserver) {
      try { resizeObserver.disconnect(); } catch (_) {}
      resizeObserver = null;
    }
  }

  const handle = { destroy };
  registerChart(handle);

  if (window.d3) {
    loadNetwork();
  } else {
    ensureD3()
      .then(() => { if (!destroyed) loadNetwork(); })
      .catch(() => { if (!destroyed) loadNetwork(); });
  }

  return handle;
}

