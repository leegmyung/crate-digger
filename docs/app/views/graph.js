import { appState, navigateTo, registerChart } from '../state.js';
import { queryEgoNetwork, queryNodeExpansion } from '../db.js';
import { cssVar, escapeHtml, fmtInt, formatSourceKey } from '../ui.js';

let nextGraphInstanceId = 1;

const INITIAL_NODE_CAP = 60;
const CAP_STEP = 30;

const RELATION_LABELS = {
  co_stage: '같은 무대',
  same_agency: '같은 소속사',
  venue: '공연장',
  outcome: '정답',
  program: '선정·지원',
  outlet: '매체',
  scene: '씬 묶음',
};

const TYPE_LABELS = {
  ego: '현재 팀',
  team: '팀',
  venue: '공연장',
  outcome: '정답',
  program: '선정·지원',
  outlet: '매체',
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
    if (node.detail) parts.push(node.detail);
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
            <span class="graph-leg-item"><i class="graph-swatch is-outcome"></i>정답(S·A·B)</span>
            <span class="graph-leg-item"><i class="graph-swatch is-program"></i>선정·지원</span>
            <span class="graph-leg-item"><i class="graph-swatch is-outlet"></i>매체</span>
            <span class="graph-leg-item"><i class="graph-swatch is-scene"></i>씬 묶음</span>
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
      g.attr('opacity', isDimmed ? 0.16 : 1);

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
        const sLbl = typeof d.source === 'object' ? d.source.label : d.source;
        const tLbl = typeof d.target === 'object' ? d.target.label : d.target;
        const desc = describeRelationEdge(d);
        const extra = d.detail && d.relation === 'co_stage' ? `<div class="gt-sub">${escapeHtml(d.detail)}</div>` : '';
        showTooltip(evt, `<strong>${escapeHtml(sLbl)} ↔ ${escapeHtml(tLbl)}</strong><div class="gt-sub">${escapeHtml(desc)}</div>${extra}`);
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
        g.append('rect')
          .attr('class', 'gn-base')
          .attr('x', -s / 2)
          .attr('y', -s / 2)
          .attr('width', s)
          .attr('height', s)
          .attr('rx', 2.5)
          .attr('transform', 'rotate(45)')
          .attr('stroke-width', 1.6);
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
        g.append('circle')
          .attr('class', 'gn-base')
          .attr('r', r)
          .attr('stroke-width', 1.5);
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
    });

    const nodeMerged = nodeEnter.merge(nodeJoin);

    nodeMerged
      .on('mouseenter', function (evt, d) {
        hoveredId = d.id;
        applyHighlightAndTheme();
        const typeLbl = TYPE_LABELS[d.node_type] || d.node_type;
        const sub = d.detail || d.primary_genre || '';
        const actionHint = d.node_type === 'team' && d.id !== egoId
          ? '클릭: 연결 펼치기 · 더블클릭: 팀 상세'
          : (d.expanded ? '연결 펼쳐짐' : '클릭: 연결 펼치기');
        showTooltip(evt, `
          <strong>${escapeHtml(d.label)}</strong>
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

  // Start loading (wait a tick if D3 defer script is still settling)
  if (window.d3) {
    loadInitialGraph();
  } else {
    let tries = 0;
    const waitTimer = setInterval(() => {
      tries += 1;
      if (destroyed) {
        clearInterval(waitTimer);
        return;
      }
      if (window.d3 || tries >= 25) {
        clearInterval(waitTimer);
        loadInitialGraph();
      }
    }, 80);
  }

  return handle;
}
