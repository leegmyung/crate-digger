// 팀 페이지 '관계' 탭의 관계망 (SVG + D3 v7). 씬 네트워크(공연장 화면)는 graph_scene.js.
// 원리(Chartmetric·Obsidian 그래프, 베끼지 않고 원리만):
//   크기 = 중요도(오늘 점수 순위·정답 등급) · 색 = 종류(칩이 범례 겸 필터) · 선 굵기 = 같은 무대 횟수
//   마우스 올리면 이웃만 밝게 · 누르면 옆 패널(좁은 화면은 아래 시트) · 라벨은 확대 수준에 맞춰 겹치지 않게.
import { appState, registerChart, syncHash } from '../state.js';
import { queryEgoNetwork, queryNodeExpansion } from '../db.js';
import { ensureD3, fmtInt, formatSourceKey, wireAvatarFallbacks } from '../ui.js';
import {
  buildAdjacency, edgeWidthFor, estimateLabelWidth, filterGraph, importanceOf, labelBudget, labelFontSize,
  labelPriority, nodeRadiusFor, pickVisibleLabels, relationKindOf, rowToGraphParts, shortLabel,
} from './graph_model.js';
import {
  filterChipsHtml, isUnscoredSourceNode, neighborsOf, panelHtml, tooltipHtml,
} from './graph_panel.js';

import { drawNodeShape, ensureGraphCss, periodToggleHtml, shellHtml } from './graph_shell.js';

export { mountSceneNetworkBlock } from './graph_scene.js';

const INITIAL_NODE_CAP = 60;
const CAP_STEP = 40;
const MAX_NODES = 300;
const ZOOM_STEP = 1.35;
const SCALE_EXTENT = [0.25, 4];
const LABEL_BASE = 11;
const EGO_LABEL_BASE = 13;
const LABEL_EVERY_TICKS = 8;
const PRE_TICKS = 160;
const NARROW_PX = 760;          // 이보다 좁으면 패널이 아래 시트 (css/graph.css 의 @container 와 같은 값)
const EXPAND_LIMIT = 10;

/** 1단계 이웃이 앉는 고리 반지름 — 종류별로 층을 나눠 한눈에 읽히게 */
const RING_BY_KIND = { agency: 95, co_stage: 150, venue: 225, outcome: 195, program: 205, outlet: 240, scene: 260 };
/** 선 길이 기본값 (양 끝 반지름을 더함) */
const DIST_BY_KIND = { agency: 38, co_stage: 52, venue: 70, outcome: 60, program: 62, outlet: 70, scene: 80 };

const endId = v => (v && typeof v === 'object' ? v.id : v);
const edgeKey = (a, b) => (a < b ? `${a}__${b}` : `${b}__${a}`);

/**
 * 팀 상세 화면 '관계' 탭에 관계망 블록(+ 크게 보기)을 붙인다.
 * @param {HTMLElement} hostEl
 * @param {{ teamKey: string, displayName: string, primaryGenre?: string }} opts
 * @returns {{ destroy(): void }}
 */
export function mountTeamGraphBlock(hostEl, { teamKey, displayName, primaryGenre = '' }) {
  if (!hostEl || !teamKey) return { destroy() {} };

  const egoId = `team:${teamKey}`;
  let destroyed = false;
  let period = appState.teamGraphPeriod === '1y' ? '1y' : 'all';
  let nodeCap = INITIAL_NODE_CAP;
  let loading = false;
  let statusNote = '';
  let selectedId = null;
  let hoveredId = null;
  let hasFitted = false;

  const nodesMap = new Map();
  const linksMap = new Map();
  const expandedIds = new Set();
  const loadingIds = new Set();
  const hiddenKinds = new Set();
  let pending = []; // 상한에 걸려 못 넣은 { parentId, row }

  let shown = { nodes: [], links: [] };
  let adjacency = new Map();
  let nodeById = new Map();

  let svgSel = null;
  let gRoot = null;
  let gLinks = null;
  let gNodes = null;
  let gLabels = null;
  let defs = null;
  let zoomBehavior = null;
  let simulation = null;
  let clipSeq = 0;
  let tickCount = 0;
  let labelRaf = 0;
  let lastLabelK = 0;
  let width = 640;
  let height = 460;
  let resizeObserver = null;
  let modalBackdrop = null;
  const instance = Math.random().toString(36).slice(2, 8);

  hostEl.innerHTML = shellHtml(displayName, period);
  const $ = sel => hostEl.querySelector(sel);
  const inlineSlot = $('[data-rg-inline-slot]');
  const surfaceEl = $('[data-rg-surface]');
  const bodyEl = $('[data-rg-body]');
  const stageEl = $('[data-rg-stage]');
  const svgEl = $('[data-rg-svg]');
  const metaEl = $('[data-rg-meta]');
  const filtersEl = $('[data-rg-filters]');
  const panelEl = $('[data-rg-panel]');
  const tipEl = $('[data-rg-tip]');
  const emptyEl = $('[data-rg-empty]');
  const moreBtn = $('[data-rg-more]');
  const hintEl = $('[data-rg-hint]');
  if (window.matchMedia?.('(pointer: coarse)').matches && hintEl) hintEl.textContent = '누르면 자세히 · 두 번 누르면 연결 펼치기';

  // ---------- 데이터 ----------

  function decorate(node, parent, depthAdd) {
    if (node.node_type === 'outlet') node.label = formatSourceKey(node.node_key || node.label).label || node.label;
    if (node.node_type === 'team' || node.node_type === 'ego') {
      node.photoUrl = appState.imagesByTeam?.get(node.node_key) || '';
      node.scoreInfo = appState.snapshots?.latest?.get(node.node_key) || null;
    }
    node.importance = importanceOf(node, node.scoreInfo);
    node.r = nodeRadiusFor(node);
    node.depth = (parent?.depth || 0) + depthAdd;
    const angle = Math.random() * Math.PI * 2;
    const dist = 40 + Math.random() * 40;
    node.x = (Number.isFinite(parent?.x) ? parent.x : width / 2) + Math.cos(angle) * dist;
    node.y = (Number.isFinite(parent?.y) ? parent.y : height / 2) + Math.sin(angle) * dist;
    return node;
  }

  function createEgo() {
    const ego = decorate({
      id: egoId, node_type: 'ego', node_key: teamKey, label: displayName || teamKey, detail: '', grade: '', role: '',
      last_date: '', primary_genre: primaryGenre || '', maxWeight: 1, kind: 'ego',
    }, null, 0);
    ego.x = width / 2;
    ego.y = height / 2;
    ego.fx = ego.x;
    ego.fy = ego.y;
    return ego;
  }

  /** 행 하나를 더한다. 상한에 걸리면 { capped: true } */
  function addRow(parent, row) {
    const parts = rowToGraphParts(parent, row);
    const fresh = parts.nodes.filter(n => !nodesMap.has(n.id));
    if (fresh.length && nodesMap.size + fresh.length > nodeCap) return { capped: true };
    const kind = relationKindOf(row.relation || row.node_type);
    parts.nodes.forEach((n, i) => {
      const existing = nodesMap.get(n.id);
      if (existing) {
        mergeNode(existing, n);
        return;
      }
      nodesMap.set(n.id, decorate({ ...n, kind }, parent, i + 1));
    });
    for (const l of parts.links) {
      const key = edgeKey(l.source, l.target);
      const ex = linksMap.get(key);
      if (ex) {
        if (!ex.relations.includes(l.relation)) {
          ex.relations = [...ex.relations, l.relation];
          if (l.relation === 'co_stage') ex.relation = 'co_stage';
        }
        ex.weight = Math.max(ex.weight, l.weight);
        if (!ex.detail && l.detail) ex.detail = l.detail;
      } else {
        linksMap.set(key, { ...l, id: key, relations: [l.relation] });
      }
    }
    return { capped: false };
  }

  function mergeNode(existing, n) {
    if (n.maxWeight > existing.maxWeight) {
      existing.maxWeight = n.maxWeight;
      if (existing.node_type !== 'team' && existing.node_type !== 'ego') {
        existing.importance = importanceOf(existing, existing.scoreInfo);
        existing.r = nodeRadiusFor(existing);
      }
    }
    if (!existing.detail && n.detail) existing.detail = n.detail;
    if (!existing.grade && n.grade) existing.grade = n.grade;
    if (!existing.last_date && n.last_date) existing.last_date = n.last_date;
  }

  function addRows(parent, rows) {
    let capped = 0;
    const before = nodesMap.size;
    for (const r of rows) {
      if (addRow(parent, r).capped) {
        pending = [...pending, { parentId: parent.id, row: r }];
        capped += 1;
      }
    }
    return { addedNodes: nodesMap.size - before, capped };
  }

  function pendingCount() {
    return new Set(pending.map(p => p.row?.node_id).filter(id => id && !nodesMap.has(id))).size;
  }

  // ---------- 그리기 ----------

  function ensureSvg() {
    if (svgSel || !window.d3) return;
    const d3 = window.d3;
    measure();
    svgSel = d3.select(svgEl);
    svgSel.selectAll('*').remove();
    defs = svgSel.append('defs');
    gRoot = svgSel.append('g').attr('class', 'rg-root');
    gLinks = gRoot.append('g').attr('class', 'rg-links');
    gNodes = gRoot.append('g').attr('class', 'rg-nodes');
    gLabels = gRoot.append('g').attr('class', 'rg-labels');

    zoomBehavior = d3.zoom()
      .scaleExtent(SCALE_EXTENT)
      .extent([[0, 0], [width, height]])
      .on('zoom', (event) => {
        gRoot.attr('transform', event.transform);
        scheduleLabels();
      });
    svgSel.call(zoomBehavior).on('dblclick.zoom', null);
    svgSel.on('click', (event) => {
      if (event.target === svgEl) select(null);
    });

    simulation = d3.forceSimulation()
      .force('link', d3.forceLink().id(d => d.id)
        .distance(l => (DIST_BY_KIND[relationKindOf(l.relation)] || 60) + l.source.r + l.target.r)
        .strength(l => (l.source.depth === 0 || l.target.depth === 0 ? 0.35 : 0.6)))
      .force('charge', d3.forceManyBody().strength(d => -160 - d.r * 9).distanceMax(420))
      .force('collide', d3.forceCollide().radius(d => d.r + 7).iterations(2))
      .force('ring', d3.forceRadial(d => ringRadius(d), width / 2, height / 2).strength(d => (d.depth === 1 ? 0.32 : 0)))
      .alphaDecay(0.035)
      .on('tick', onTick)
      .on('end', scheduleLabels);
  }

  function ringRadius(d) {
    const base = RING_BY_KIND[d.kind] || 200;
    if (d.kind === 'co_stage') return base - Math.min(55, Math.sqrt(Math.max(0, d.maxWeight - 1)) * 14);
    return base;
  }

  function measure() {
    const rect = stageEl.getBoundingClientRect();
    if (rect.width > 40 && rect.height > 40) {
      width = rect.width;
      height = rect.height;
    }
    zoomBehavior?.extent([[0, 0], [width, height]]);
  }

  function onTick() {
    gLinks.selectAll('line').attr('x1', d => d.source.x).attr('y1', d => d.source.y)
      .attr('x2', d => d.target.x).attr('y2', d => d.target.y);
    gNodes.selectAll('g.rg-node').attr('transform', d => `translate(${d.x.toFixed(1)},${d.y.toFixed(1)})`);
    gLabels.selectAll('text').attr('x', d => d.x).attr('y', d => d.y + d.r + 3);
    tickCount += 1;
    if (tickCount % LABEL_EVERY_TICKS === 0) scheduleLabels();
  }

  function updateEmptyNote() {
    if (nodesMap.size <= 1 && !loading) {
      showEmpty(period === '1y'
        ? '최근 1년 안에 이어진 기록이 없습니다. 위에서 "전체"를 눌러 보세요.'
        : '이어진 공연·선정·매체 기록이 아직 없습니다.');
    } else if (shown.nodes.length <= 1 && nodesMap.size > 1) {
      showEmpty('모든 종류를 숨겼습니다. 위 칩을 눌러 다시 켜 보세요.');
    } else {
      emptyEl.hidden = true;
    }
  }

  function joinElements() {
    const d3 = window.d3;
    gLinks.selectAll('line').data(shown.links, d => d.id).join(
      enter => enter.append('line').attr('stroke-linecap', 'round'),
    ).attr('class', d => `rg-link k-${relationKindOf(d.relation)}`)
      .attr('stroke-width', d => edgeWidthFor(d));

    gNodes.selectAll('g.rg-node').data(shown.nodes, d => d.id).join(
      enter => enter.append('g')
        .attr('class', d => `rg-node t-${d.node_type}${isUnscoredSourceNode(d) ? ' is-unscored' : ''}`)
        .attr('tabindex', 0)
        .attr('role', 'button')
        .attr('aria-label', d => `${d.label} 자세히`)
        .each(function eachNode(d) {
          drawNodeShape(d3.select(this), d, `rg-clip-${instance}-${++clipSeq}`, defs);
        })
        .call(dragBehavior())
        .on('mouseenter', (event, d) => setHover(d.id, event))
        .on('mousemove', event => positionTip(event))
        .on('mouseleave', () => setHover(null))
        .on('click', (event, d) => {
          event.stopPropagation();
          select(d.id);
        })
        .on('dblclick', (event, d) => {
          event.stopPropagation();
          expand(d.id);
        })
        .on('keydown', (event, d) => {
          if (event.key !== 'Enter' && event.key !== ' ') return;
          event.preventDefault();
          if (selectedId === d.id) expand(d.id);
          else select(d.id);
        }),
    );

    gLabels.selectAll('text').data(shown.nodes, d => d.id).join(
      enter => enter.append('text')
        .attr('class', d => `rg-label t-${d.node_type}`)
        .attr('text-anchor', 'middle')
        .attr('dominant-baseline', 'hanging')
        .text(d => shortLabel(d.label, d.node_type === 'ego' ? 20 : 14)),
    );
    lastLabelK = 0; // 새 라벨에도 글자 크기를 다시 매긴다
  }

  function renderGraph({ autoFit = false, reheat = 0.5 } = {}) {
    if (destroyed) return;
    if (!window.d3) {
      showEmpty('그래프 라이브러리(D3)를 불러오지 못했습니다.');
      return;
    }
    ensureSvg();
    shown = filterGraph([...nodesMap.values()], [...linksMap.values()], hiddenKinds, egoId);
    adjacency = buildAdjacency(shown.links);
    nodeById = new Map(shown.nodes.map(n => [n.id, n]));
    if (selectedId && !nodeById.has(selectedId)) {
      selectedId = null;
      bodyEl.classList.remove('has-sel');
    }
    updateEmptyNote();
    joinElements();

    simulation.nodes(shown.nodes);
    simulation.force('link').links(shown.links);
    simulation.force('ring').x(width / 2).y(height / 2);
    if (autoFit) {
      simulation.alpha(1).stop();
      for (let i = 0; i < PRE_TICKS; i++) simulation.tick();
      onTick();
      fitToView(0);
      simulation.alpha(0.06).restart();
    } else if (reheat > 0) {
      simulation.alpha(reheat).restart();
    }
    applyFocus();
    renderFilters();
    renderPanel();
    updateMeta();
  }

  function dragBehavior() {
    return window.d3.drag()
      .clickDistance(4)
      .on('start', (event, d) => {
        if (!event.active) simulation.alphaTarget(0.18).restart();
        d.fx = d.x;
        d.fy = d.y;
      })
      .on('drag', (event, d) => {
        d.fx = event.x;
        d.fy = event.y;
      })
      .on('end', (event, d) => {
        if (!event.active) simulation.alphaTarget(0);
        if (d.id !== egoId) {
          d.fx = null;
          d.fy = null;
        }
      });
  }

  function showEmpty(msg) {
    emptyEl.textContent = msg;
    emptyEl.hidden = false;
  }

  // ---------- 강조·라벨 ----------

  function focusSet() {
    const focusId = hoveredId || selectedId;
    if (!focusId || !nodeById.has(focusId)) return null;
    return new Set([focusId, ...(adjacency.get(focusId) || [])]);
  }

  function applyFocus() {
    if (!svgSel) return;
    const focusId = hoveredId || selectedId;
    const nb = focusSet();
    svgEl.classList.toggle('has-focus', Boolean(nb));
    gNodes.selectAll('g.rg-node')
      .classed('is-nb', d => Boolean(nb?.has(d.id)))
      .classed('is-focus', d => d.id === focusId)
      .classed('is-selected', d => d.id === selectedId);
    gLinks.selectAll('line').classed('is-hi', d => Boolean(focusId) && (endId(d.source) === focusId || endId(d.target) === focusId));
    gLabels.selectAll('text').classed('is-nb', d => Boolean(nb?.has(d.id)));
    scheduleLabels();
  }

  function scheduleLabels() {
    if (labelRaf || destroyed) return;
    labelRaf = requestAnimationFrame(() => {
      labelRaf = 0;
      if (!destroyed) updateLabels();
    });
  }

  const labelBaseOf = d => (d.node_type === 'ego' ? EGO_LABEL_BASE : LABEL_BASE);

  function updateLabels() {
    if (!svgSel) return;
    const t = window.d3.zoomTransform(svgEl);
    const k = t.k;
    const labels = gLabels.selectAll('text');
    if (Math.abs(k - lastLabelK) / Math.max(k, 0.01) > 0.02) {
      lastLabelK = k;
      labels.attr('font-size', d => labelFontSize(labelBaseOf(d), k))
        .attr('stroke-width', d => labelFontSize(labelBaseOf(d), k) * 0.32);
    }
    const nb = focusSet();
    const pinned = new Set([egoId]);
    if (selectedId) pinned.add(selectedId);
    if (hoveredId) pinned.add(hoveredId);
    const items = [];
    for (const n of shown.nodes) {
      if (!Number.isFinite(n.x) || (nb && !nb.has(n.id))) continue;
      const sx = t.applyX(n.x);
      const sy = t.applyY(n.y) + (n.r + 3) * k;
      if (sx < -60 || sx > width + 60 || sy < -30 || sy > height + 30) continue;
      const screenFs = labelFontSize(labelBaseOf(n), k) * k;
      const text = shortLabel(n.label, n.node_type === 'ego' ? 20 : 14);
      items.push({
        id: n.id, x: sx, y: sy, w: estimateLabelWidth(text, screenFs), h: screenFs * 1.15,
        priority: labelPriority(n, adjacency.get(n.id)?.size || 0),
      });
    }
    const budget = nb ? nb.size : labelBudget(k, shown.nodes.length);
    const on = pickVisibleLabels(items, { budget, pinned });
    labels.classed('is-on', d => on.has(d.id));
  }

  function setHover(id, event) {
    hoveredId = id;
    if (id) {
      hintEl?.classList.add('is-gone');
      const n = nodeById.get(id);
      if (n) showTip(event, tooltipHtml(n, n.id === egoId ? null : linkBetween(egoId, n.id)));
    } else {
      tipEl.hidden = true;
    }
    applyFocus();
  }

  function linkBetween(a, b) {
    return linksMap.get(edgeKey(a, b)) || null;
  }

  function showTip(event, html) {
    tipEl.innerHTML = html;
    tipEl.hidden = false;
    positionTip(event);
  }

  function positionTip(event) {
    if (tipEl.hidden || !event) return;
    const rect = stageEl.getBoundingClientRect();
    const tw = tipEl.offsetWidth || 160;
    const th = tipEl.offsetHeight || 40;
    let x = event.clientX - rect.left + 14;
    let y = event.clientY - rect.top - th - 10;
    if (x + tw > rect.width - 8) x = Math.max(8, event.clientX - rect.left - tw - 14);
    if (y < 8) y = Math.min(rect.height - th - 8, event.clientY - rect.top + 16);
    tipEl.style.left = `${Math.round(x)}px`;
    tipEl.style.top = `${Math.round(y)}px`;
  }

  // ---------- 고르기·펼치기 ----------

  function isNarrow() {
    return surfaceEl.clientWidth < NARROW_PX;
  }

  function select(id) {
    selectedId = id && nodeById.has(id) ? id : null;
    statusNote = '';
    hintEl?.classList.add('is-gone');
    bodyEl.classList.toggle('has-sel', Boolean(selectedId));
    applyFocus();
    renderPanel();
    if (selectedId && isNarrow()) centerOn(selectedId, { topShare: 0.3 });
  }

  /** 노드를 화면 안 원하는 높이(topShare: 0 위 ~ 1 아래)로 옮긴다 — 아래 시트에 가리지 않게 */
  function centerOn(id, { topShare = 0.5, duration = 320 } = {}) {
    const n = nodeById.get(id);
    if (!n || !svgSel || !Number.isFinite(n.x)) return;
    const t = window.d3.zoomTransform(svgEl);
    const k = Math.max(t.k, 0.9);
    const next = window.d3.zoomIdentity.translate(width / 2 - n.x * k, height * topShare - n.y * k).scale(k);
    svgSel.interrupt().transition().duration(duration).call(zoomBehavior.transform, next);
  }

  async function expand(id) {
    const node = nodesMap.get(id);
    if (!node || destroyed) return;
    if (selectedId !== id) select(id);
    if (expandedIds.has(id) || loadingIds.has(id) || node.node_type === 'agency') {
      statusNote = node.node_type === 'agency' ? '소속사는 더 펼칠 연결이 없습니다.' : '이미 펼친 노드입니다.';
      renderPanel();
      return;
    }
    loadingIds.add(id);
    renderPanel();
    try {
      const rows = await queryNodeExpansion(node, { period, limit: EXPAND_LIMIT });
      if (destroyed) return;
      expandedIds.add(id);
      const { addedNodes, capped } = addRows(node, rows);
      if (rows.length) renderGraph({ reheat: 0.45 });
      if (addedNodes > 0) statusNote = `새로 ${fmtInt(addedNodes)}곳 펼침`;
      else if (capped > 0) statusNote = `한 번에 ${fmtInt(nodeCap)}개까지 — 아래 '더 보기'로 늘리세요`;
      else statusNote = '더 이어진 곳이 없습니다.';
    } catch (_) {
      statusNote = '연결을 불러오지 못했습니다. 잠시 뒤 다시 눌러 보세요.';
    } finally {
      loadingIds.delete(id);
      if (!destroyed) {
        renderPanel();
        updateMeta();
      }
    }
  }

  function flushPending() {
    nodeCap = Math.min(MAX_NODES, nodeCap + CAP_STEP);
    const items = pending;
    pending = [];
    const before = nodesMap.size;
    for (const item of items) {
      const parent = nodesMap.get(item.parentId);
      if (parent && addRow(parent, item.row).capped) pending = [...pending, item];
    }
    const added = nodesMap.size - before;
    statusNote = added ? `${fmtInt(added)}곳 더 그림` : '';
    renderGraph({ reheat: 0.4 });
  }

  // ---------- 패널·필터·글줄 ----------

  function renderPanel() {
    const ego = nodesMap.get(egoId);
    const node = (selectedId && nodeById.get(selectedId)) || ego;
    if (!node) {
      panelEl.innerHTML = '';
      return;
    }
    const expandState = loadingIds.has(node.id) ? 'loading' : (expandedIds.has(node.id) ? 'done' : '');
    panelEl.innerHTML = panelHtml({
      node,
      egoNode: ego,
      linkToEgo: node.id === egoId ? null : linkBetween(egoId, node.id),
      neighbors: neighborsOf(node.id, shown.links, nodeById),
      isSelected: Boolean(selectedId),
      expandState,
      statusNote,
    });
    panelEl.setAttribute('aria-hidden', isNarrow() && !selectedId ? 'true' : 'false');
    wireAvatarFallbacks(panelEl);
  }

  function renderFilters() {
    const counts = new Map();
    for (const n of nodesMap.values()) {
      if (n.id !== egoId) counts.set(n.kind, (counts.get(n.kind) || 0) + 1);
    }
    filtersEl.innerHTML = filterChipsHtml(counts, hiddenKinds);
  }

  function updateMeta() {
    const periodTxt = period === '1y' ? '최근 1년' : '전체 기간';
    const txt = loading
      ? '불러오는 중...'
      : `${periodTxt} · ${fmtInt(Math.max(0, shown.nodes.length - 1))}곳 · 연결 ${fmtInt(shown.links.length)}`;
    metaEl.textContent = txt;
    const modalMeta = modalBackdrop?.querySelector('[data-rg-modal-meta]');
    if (modalMeta) modalMeta.textContent = `${displayName} · ${txt}`;
    const more = pendingCount();
    moreBtn.hidden = !(more > 0 && nodeCap < MAX_NODES);
    moreBtn.textContent = `더 보기 +${fmtInt(Math.min(CAP_STEP, more))}`;
    const periodBtns = [
      ...hostEl.querySelectorAll('[data-graph-period]'),
      ...(modalBackdrop ? modalBackdrop.querySelectorAll('[data-graph-period]') : []),
    ];
    periodBtns.forEach((btn) => {
      const on = btn.dataset.graphPeriod === period;
      btn.classList.toggle('active', on);
      btn.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
  }

  // ---------- 확대 ----------

  function fitToView(duration = 280) {
    if (!svgSel || !shown.nodes.length || !svgEl.isConnected) return;
    measure();
    let minX = Infinity;
    let maxX = -Infinity;
    let minY = Infinity;
    let maxY = -Infinity;
    for (const n of shown.nodes) {
      if (!Number.isFinite(n.x)) continue;
      minX = Math.min(minX, n.x - n.r - 24);
      maxX = Math.max(maxX, n.x + n.r + 24);
      minY = Math.min(minY, n.y - n.r - 10);
      maxY = Math.max(maxY, n.y + n.r + 22);
    }
    if (!Number.isFinite(minX)) return;
    const bw = Math.max(80, maxX - minX);
    const bh = Math.max(80, maxY - minY);
    const k = Math.max(0.32, Math.min(1.5, 0.92 * Math.min(width / bw, height / bh)));
    const next = window.d3.zoomIdentity
      .translate(width / 2 - ((minX + maxX) / 2) * k, height / 2 - ((minY + maxY) / 2) * k)
      .scale(k);
    svgSel.interrupt();
    if (duration > 0) svgSel.transition().duration(duration).call(zoomBehavior.transform, next);
    else svgSel.call(zoomBehavior.transform, next);
    hasFitted = true;
  }

  function zoomBy(factor) {
    if (!svgSel) return;
    svgSel.interrupt().transition().duration(200).call(zoomBehavior.scaleBy, factor);
  }

  function resetAll() {
    hiddenKinds.clear();
    selectedId = null;
    hoveredId = null;
    statusNote = '';
    bodyEl.classList.remove('has-sel');
    if (expandedIds.size > 1 || nodeCap > INITIAL_NODE_CAP) {
      loadInitial();
      return;
    }
    const ego = nodesMap.get(egoId);
    if (ego) {
      ego.fx = width / 2;
      ego.fy = height / 2;
    }
    renderGraph({ reheat: 0.3 });
    fitToView(300);
  }

  // ---------- 불러오기 ----------

  async function loadInitial() {
    if (destroyed) return;
    loading = true;
    nodesMap.clear();
    linksMap.clear();
    expandedIds.clear();
    pending = [];
    nodeCap = INITIAL_NODE_CAP;
    selectedId = null;
    hoveredId = null;
    statusNote = '';
    bodyEl.classList.remove('has-sel');
    measure();
    updateMeta();
    const ego = createEgo();
    nodesMap.set(egoId, ego);
    expandedIds.add(egoId);
    try {
      const rows = await queryEgoNetwork(teamKey, { period, limitPerKind: EXPAND_LIMIT });
      if (destroyed) return;
      addRows(ego, rows);
    } catch (_) {
      statusNote = '관계망을 불러오지 못했습니다.';
    } finally {
      loading = false;
      if (!destroyed) renderGraph({ autoFit: true });
    }
  }

  function setPeriod(next) {
    if (!next || next === period) return;
    period = next;
    appState.teamGraphPeriod = period === '1y' ? '1y' : 'all';
    syncHash(true);
    loadInitial();
  }

  // ---------- 크게 보기 ----------

  function onKeydown(e) {
    if (e.key !== 'Escape') return;
    if (selectedId) select(null);
    else if (modalBackdrop) closeModal();
  }

  function openModal() {
    if (modalBackdrop || destroyed) return;
    modalBackdrop = document.createElement('div');
    modalBackdrop.className = 'graph-modal-backdrop rg-modal-backdrop';
    modalBackdrop.setAttribute('role', 'dialog');
    modalBackdrop.setAttribute('aria-modal', 'true');
    modalBackdrop.setAttribute('aria-label', `${displayName} 관계망 크게 보기`);
    modalBackdrop.innerHTML = `
      <div class="graph-modal rg rg-modal">
        <div class="rg-head">
          <div class="rg-head-title">
            <h2>관계망</h2>
            <span class="block-meta" data-rg-modal-meta></span>
          </div>
          <div class="rg-head-actions">
            ${periodToggleHtml(period)}
            <button type="button" class="btn btn-sm" data-rg-close-modal>닫기 ✕</button>
          </div>
        </div>
        <div class="rg-modal-slot" data-rg-modal-slot></div>
      </div>`;
    modalBackdrop.querySelector('[data-rg-modal-slot]').appendChild(surfaceEl);
    surfaceEl.classList.add('is-expanded');
    document.body.appendChild(modalBackdrop);
    document.body.classList.add('graph-modal-open');
    modalBackdrop.addEventListener('click', (e) => {
      if (e.target === modalBackdrop || e.target.closest('[data-rg-close-modal]')) {
        closeModal();
        return;
      }
      const p = e.target.closest('[data-graph-period]');
      if (p) setPeriod(p.dataset.graphPeriod);
    });
    updateMeta();
    requestAnimationFrame(() => {
      if (!destroyed) fitToView(220);
    });
    modalBackdrop.querySelector('[data-rg-close-modal]')?.focus();
  }

  function closeModal() {
    if (!modalBackdrop) return;
    svgSel?.interrupt();
    document.body.classList.remove('graph-modal-open');
    surfaceEl.classList.remove('is-expanded');
    if (inlineSlot?.isConnected) inlineSlot.appendChild(surfaceEl);
    modalBackdrop.remove();
    modalBackdrop = null;
    requestAnimationFrame(() => {
      if (!destroyed) fitToView(200);
    });
  }

  // ---------- 단추 연결 ----------

  hostEl.querySelector('.rg-head')?.addEventListener('click', (e) => {
    const p = e.target.closest('[data-graph-period]');
    if (p) setPeriod(p.dataset.graphPeriod);
    if (e.target.closest('[data-rg-open-modal]')) openModal();
  });

  function onSurfaceClick(e) {
    const t = e.target;
    const zoom = t.closest('[data-rg-zoom]');
    if (zoom) {
      const mode = zoom.dataset.rgZoom;
      if (mode === 'in') zoomBy(ZOOM_STEP);
      else if (mode === 'out') zoomBy(1 / ZOOM_STEP);
      else fitToView(260);
      return;
    }
    if (t.closest('[data-rg-reset]')) {
      resetAll();
      return;
    }
    if (t.closest('[data-rg-more]')) {
      flushPending();
      return;
    }
    const chip = t.closest('[data-rg-kind]');
    if (chip) {
      const kind = chip.dataset.rgKind;
      if (hiddenKinds.has(kind)) hiddenKinds.delete(kind);
      else hiddenKinds.add(kind);
      renderGraph({ reheat: 0.35 });
      return;
    }
    onPanelClick(t);
  }

  function onPanelClick(t) {
    if (t.closest('[data-rg-close]')) {
      select(null);
      return;
    }
    const jump = t.closest('[data-rg-jump]');
    if (jump) {
      select(jump.dataset.rgJump);
      centerOn(jump.dataset.rgJump, { topShare: isNarrow() ? 0.3 : 0.5 });
      return;
    }
    const exp = t.closest('[data-rg-expand]');
    if (exp) {
      expand(exp.dataset.rgExpand);
      return;
    }
    const scene = t.closest('[data-rg-scene]');
    if (scene) {
      const sid = Number(scene.dataset.rgScene);
      if (Number.isFinite(sid)) appState.focusSceneId = sid;
      closeModal();
      window.location.hash = '#/venues/network';
      return;
    }
    // 패널 안 페이지 이동 링크: 모달이면 닫고, 주소 이동은 링크가 한다
    if (t.closest('a[href^="#/"]')) closeModal();
  }

  // 겉칸(surface)은 크게 보기에서 모달로 옮겨 가므로 여기에 한 번만 건다
  surfaceEl.addEventListener('click', onSurfaceClick);
  document.addEventListener('keydown', onKeydown);

  if (typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(() => {
      if (destroyed || !stageEl.isConnected) return;
      measure();
      simulation?.force('ring')?.x(width / 2).y(height / 2);
      if (!hasFitted && shown.nodes.length > 1) fitToView(0);
      panelEl.setAttribute('aria-hidden', isNarrow() && !selectedId ? 'true' : 'false');
    });
    resizeObserver.observe(stageEl);
  }

  function destroy() {
    if (destroyed) return;
    destroyed = true;
    if (labelRaf) cancelAnimationFrame(labelRaf);
    try { svgSel?.interrupt(); } catch (_) { /* 이미 멈춤 */ }
    closeModal();
    simulation?.stop();
    simulation = null;
    resizeObserver?.disconnect();
    resizeObserver = null;
    document.removeEventListener('keydown', onKeydown);
  }

  const handle = { destroy };
  registerChart(handle);

  Promise.all([ensureGraphCss(), window.d3 ? Promise.resolve() : ensureD3().catch(() => null)])
    .then(() => {
      if (!destroyed) loadInitial();
    });

  return handle;
}
