// 공연장 화면 '씬' 탭의 전체/장르별 씬 네트워크 (Canvas + D3 v7). 팀 관계망(graph.js)과 같은 디자인(css/graph.css .rg-*).
//   크기 = 오늘 점수 · 색 = 씬 묶음(칩 = 범례, 누르면 그 묶음만 밝게) · 굵은 테두리 = 수상·선정 팀(칩으로 숨김)
//   선 굵기 = 같은 무대 횟수 · 올리면 함께 선 팀만 밝게 · 누르면 옆 패널(좁은 칸은 아래 시트) · 확대하면 사진
import { appState, registerChart, syncHash } from '../state.js';
import { querySceneNetwork } from '../db.js';
import { ensureD3, escapeHtml, fmtInt, TERMS, wireAvatarFallbacks } from '../ui.js';
import { ensureGraphCss } from './graph_shell.js';
import { isHiddenNode, matchTeams, roleCounts, sceneFocusSet, sceneRadius } from './graph_scene_model.js';
import { sceneChipsHtml, scenePanelHtml, sceneTooltipHtml, searchMenuHtml } from './graph_scene_panel.js';
import { drawScene } from './graph_scene_draw.js';

const SCENE_FALLBACK_COLORS = ['#2563eb', '#0f766e', '#d97706', '#7c3aed', '#db2777', '#0284c7', '#65a30d', '#ea580c'];
const LIMIT_CHOICES = [100, 150, 250, 300];
const NARROW_PX = 760;
const DBLCLICK_MS = 340;
const ZOOM_STEP = 1.32;
const SCALE_EXTENT = [0.28, 4.5];
const TOP_TEAMS = 6;

const ICON_FIT = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M2 6V2h4M10 2h4v4M14 10v4h-4M6 14H2v-4" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>';
const ICON_RESET = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3.2 7.2a5 5 0 1 1 1.3 4.3M3 3.5v3.7h3.7" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>';

function shellHtml(currentGenre, currentLimit, validGenres) {
  return `
    <section class="block rg sn scene-net-block" id="sceneNetworkBlock">
      <div class="rg-head">
        <div class="rg-head-title">
          <h2>씬 네트워크</h2>
          <span class="block-meta" data-sn-meta>불러오는 중...</span>
        </div>
        <div class="rg-head-actions">
          <div class="seg-toggle scene-net-limit-toggle" role="group" aria-label="표시 팀 수">
            ${LIMIT_CHOICES.map(n => `<button type="button" class="seg-btn ${currentLimit === n ? 'active' : ''}" data-sn-limit="${n}" aria-pressed="${currentLimit === n}">${n}팀</button>`).join('')}
          </div>
          <button type="button" class="btn btn-sm" data-sn-open-modal aria-label="씬 네트워크 크게 보기">크게 보기 ⤢</button>
        </div>
      </div>
      <div class="scene-net-toolbar">
        <div class="scene-net-genres" role="group" aria-label="장르 필터">
          <button type="button" class="chip-btn ${currentGenre === '' ? 'active' : ''}" data-sn-genre="" aria-pressed="${currentGenre === ''}">전체</button>
          ${validGenres.map(g => `<button type="button" class="chip-btn ${currentGenre === g ? 'active' : ''}" data-sn-genre="${escapeHtml(g)}" aria-pressed="${currentGenre === g}">${escapeHtml(g)}</button>`).join('')}
        </div>
        <div class="scene-net-search" data-sn-search-wrap>
          <input type="search" class="scene-net-search-input" data-sn-search placeholder="그림 안 팀 찾기..." autocomplete="off" aria-label="씬 네트워크 안 팀 찾기">
          <div class="scene-net-search-menu" data-sn-search-menu hidden></div>
        </div>
      </div>
      <div class="rg-slot" data-sn-inline-slot>
        <div class="rg-surface" data-sn-surface>
          <div class="rg-filters" role="group" aria-label="씬 묶음과 역할 (색 범례 · 누르면 강조·숨김)" data-sn-chips></div>
          <div class="rg-body" data-sn-body>
            <div class="rg-stage" data-sn-stage>
              <canvas class="sn-canvas" data-sn-canvas role="img" aria-label="씬 네트워크 그래프 — 같은 무대에 함께 선 팀 연결"></canvas>
              <p class="rg-hint" data-sn-hint>올리면 함께 선 팀만 밝게 · 누르면 자세히</p>
              <div class="rg-ctrls" role="group" aria-label="그래프 조작">
                <button type="button" data-sn-zoom="in" title="확대" aria-label="확대">+</button>
                <button type="button" data-sn-zoom="out" title="축소" aria-label="축소">−</button>
                <button type="button" data-sn-zoom="fit" title="화면에 맞추기" aria-label="화면에 맞추기">${ICON_FIT}</button>
                <button type="button" data-sn-reset title="처음으로 (선택·숨김 풀기)" aria-label="처음으로">${ICON_RESET}</button>
              </div>
              <div class="graph-tooltip rg-tip" data-sn-tip hidden></div>
              <div class="graph-empty" data-sn-empty hidden></div>
              <span class="sn-probe" data-sn-probe aria-hidden="true"></span>
            </div>
            <aside class="rg-panel" data-sn-panel aria-label="고른 팀·묶음 자세히" aria-live="polite"></aside>
          </div>
          <p class="rg-foot"><span><i class="rg-key-size" aria-hidden="true"></i>크기 = 오늘 점수</span><span><i class="rg-key-color" aria-hidden="true"></i>색 = 씬 묶음</span><span><i class="sn-role-mark is-winner" aria-hidden="true"></i>굵은 테두리 = ${escapeHtml(TERMS.outcomeTeam)}</span><span><i class="rg-key-line" aria-hidden="true"></i>굵기 = 같은 무대 횟수</span><span class="rg-foot-tip">두 번 누르면 팀 페이지</span></p>
        </div>
      </div>
    </section>`;
}

/**
 * 공연장·씬 화면에 전체/장르별 씬 네트워크를 붙인다.
 * @returns {{ destroy(): void }}
 */
export function mountSceneNetworkBlock(hostEl, { initialGenre = '', initialLimit = 150, nextGigByTeam = new Map() } = {}) {
  if (!hostEl) return { destroy() {} };

  let destroyed = false;
  let currentGenre = String(initialGenre || '');
  let currentLimit = Number(initialLimit) || 150;
  let loadSeq = 0;

  let nodes = [];
  let edges = [];
  let communities = [];
  let nodeById = new Map();
  let adjMap = new Map();
  let selectedId = null;
  let hoveredId = null;
  let activeCommId = null;
  const hiddenRoles = new Set();
  let stats = { genre: '', teams: 0, cand: 0, winners: 0, links: 0 };

  let pal = null;
  let simulation = null;
  let zoomBehavior = null;
  let canvasSel = null;
  let transform = null;
  let width = 760;
  let height = 460;
  let fittedWidth = 0;
  let fittedHeight = 0;
  let rafId = 0;
  let modalBackdrop = null;
  let themeObserver = null;
  let resizeObserver = null;
  let lastClick = { id: null, time: 0 };
  const photos = new Map(); // url → { img, ok }

  const validGenres = Array.isArray(appState.validGenres) ? appState.validGenres : [];
  hostEl.innerHTML = shellHtml(currentGenre, currentLimit, validGenres);
  const $ = sel => hostEl.querySelector(sel);
  const inlineSlot = $('[data-sn-inline-slot]');
  const surfaceEl = $('[data-sn-surface]');
  const bodyEl = $('[data-sn-body]');
  const stageEl = $('[data-sn-stage]');
  const canvasEl = $('[data-sn-canvas]');
  const metaEl = $('[data-sn-meta]');
  const chipsEl = $('[data-sn-chips]');
  const panelEl = $('[data-sn-panel]');
  const tipEl = $('[data-sn-tip]');
  const emptyEl = $('[data-sn-empty]');
  const hintEl = $('[data-sn-hint]');
  const probeEl = $('[data-sn-probe]');
  const searchInput = $('[data-sn-search]');
  const searchMenu = $('[data-sn-search-menu]');
  const searchWrap = $('[data-sn-search-wrap]');
  if (window.matchMedia?.('(pointer: coarse)').matches && hintEl) hintEl.textContent = '누르면 자세히 · 두 번 누르면 팀 페이지';

  // ---------- 색 (css 변수 → 캔버스가 읽을 수 있는 rgb) ----------

  function resolveColor(value, fallback) {
    probeEl.style.color = '';
    probeEl.style.color = value;
    const out = getComputedStyle(probeEl).color;
    return out && out !== 'rgba(0, 0, 0, 0)' ? out : fallback;
  }

  function readPalette() {
    return {
      stage: resolveColor('var(--rg-stage)', '#f7f6f2'),
      edge: resolveColor('var(--rg-edge)', '#bbb'),
      accent: resolveColor('var(--accent)', '#b4501f'),
      ink: resolveColor('var(--ink)', '#111'),
      muted: resolveColor('var(--ink-muted)', '#555'),
      grade: {
        S: resolveColor('var(--graph-grade-s)', '#b45309'),
        A: resolveColor('var(--graph-grade-a)', '#b45309'),
        B: resolveColor('var(--graph-grade-b)', '#5c574f'),
      },
      scene: SCENE_FALLBACK_COLORS.map((c, i) => resolveColor(`var(--scene-c${i}, ${c})`, c)),
      other: resolveColor('var(--scene-c-other, #94a3b8)', '#94a3b8'),
    };
  }

  const colorOf = item => (item && item.colorSlot >= 0 && item.colorSlot < pal.scene.length ? pal.scene[item.colorSlot] : pal.other);
  const ringOf = n => pal.grade[String(n.outcome_grade || '').toUpperCase()] || pal.grade.B;

  /** 확대해서 크게 보일 때만 사진을 받아 그린다 (받으면 다시 그림) */
  function photoOf(n) {
    const url = n.imageUrl || appState.imagesByTeam?.get(n.team_key) || '';
    if (!url) return null;
    const hit = photos.get(url);
    if (hit) return hit.ok ? hit.img : null;
    const img = new Image();
    const entry = { img, ok: false };
    photos.set(url, entry);
    img.decoding = 'async';
    img.referrerPolicy = 'no-referrer';
    img.onload = () => {
      entry.ok = true;
      requestDraw();
    };
    img.src = url;
    return null;
  }

  // ---------- 그리기 ----------

  function measure() {
    const rect = stageEl.getBoundingClientRect();
    if (rect.width < 40 || rect.height < 40) return;
    width = Math.round(rect.width);
    height = Math.round(rect.height);
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const tw = Math.round(width * dpr);
    const th = Math.round(height * dpr);
    if (canvasEl.width !== tw || canvasEl.height !== th) {
      canvasEl.width = tw;
      canvasEl.height = th;
    }
    zoomBehavior?.extent([[0, 0], [width, height]]);
  }

  function focus() {
    return sceneFocusSet({ hoveredId, selectedId, activeCommId, nodes, adjMap, nodeById, hiddenRoles });
  }

  function requestDraw() {
    if (destroyed || rafId) return;
    rafId = requestAnimationFrame(() => {
      rafId = 0;
      if (destroyed || !pal) return;
      const ctx = canvasEl.getContext('2d');
      if (!ctx) return;
      drawScene(ctx, {
        w: width, h: height, dpr: Math.min(window.devicePixelRatio || 1, 2),
        t: transform || { x: width / 2, y: height / 2, k: 1 },
        nodes, edges, pal, focus: focus(), selectedId, hoveredId, hiddenRoles, colorOf, ringOf, photoOf,
      });
    });
  }

  function screenToWorld(sx, sy) {
    const t = transform || { x: 0, y: 0, k: 1 };
    return [(sx - t.x) / t.k, (sy - t.y) / t.k];
  }

  function findNodeAtScreen(sx, sy) {
    const [wx, wy] = screenToWorld(sx, sy);
    const k = transform?.k || 1;
    const pad = Math.max(4, 7 / Math.sqrt(k));
    let best = null;
    let bestD = Infinity;
    for (let i = nodes.length - 1; i >= 0; i--) {
      const n = nodes[i];
      if (!Number.isFinite(n.x) || isHiddenNode(n, hiddenRoles)) continue;
      const hitR = (n.r || 7) + (n.had_outcome ? 3 : 0) + pad;
      const d2 = (wx - n.x) ** 2 + (wy - n.y) ** 2;
      if (d2 <= hitR * hitR && d2 < bestD) {
        best = n;
        bestD = d2;
      }
    }
    return best;
  }

  // ---------- 패널·칩·글줄 ----------

  function renderChips() {
    chipsEl.innerHTML = sceneChipsHtml({ communities, colorOf, activeCommId, counts: roleCounts(nodes), hiddenRoles });
  }

  function renderPanel() {
    const node = selectedId ? nodeById.get(selectedId) : null;
    const community = activeCommId !== null ? communities.find(c => c.id === activeCommId) : null;
    let html;
    if (node) {
      html = scenePanelHtml({
        mode: 'team', node, colorOf, nextGig: nextGigByTeam?.get(node.team_key) || null,
        neighbors: (adjMap.get(node.id) || []).filter(x => !isHiddenNode(x.neighbor, hiddenRoles)),
      });
    } else if (community) {
      const members = nodes.filter(n => n.communityId === community.id && !isHiddenNode(n, hiddenRoles))
        .sort((a, b) => b.score - a.score);
      html = scenePanelHtml({ mode: 'community', community, members, colorOf });
    } else {
      const topTeams = nodes.filter(n => !isHiddenNode(n, hiddenRoles)).sort((a, b) => b.score - a.score).slice(0, TOP_TEAMS);
      html = scenePanelHtml({ mode: 'summary', stats, communities, topTeams, colorOf });
    }
    panelEl.innerHTML = html;
    wireAvatarFallbacks(panelEl);
    const hasSel = Boolean(node || community);
    bodyEl.classList.toggle('has-sel', hasSel);
    panelEl.setAttribute('aria-hidden', isNarrow() && !hasSel ? 'true' : 'false');
  }

  function updateMeta() {
    const shown = nodes.filter(n => !isHiddenNode(n, hiddenRoles)).length;
    metaEl.textContent = `${currentGenre || '전체 장르'} · ${fmtInt(shown)}팀 · 연결 ${fmtInt(edges.length)}`;
  }

  function refreshAll() {
    renderChips();
    renderPanel();
    updateMeta();
    requestDraw();
  }

  function isNarrow() {
    return surfaceEl.clientWidth < NARROW_PX;
  }

  function showEmpty(msg) {
    emptyEl.textContent = msg;
    emptyEl.hidden = false;
  }

  function showTip(n, clientX, clientY) {
    const rect = stageEl.getBoundingClientRect();
    tipEl.innerHTML = sceneTooltipHtml(n);
    tipEl.hidden = false;
    const tw = tipEl.offsetWidth || 200;
    const x = Math.max(8, Math.min(rect.width - tw - 8, clientX - rect.left + 14));
    const y = Math.max(8, Math.min(rect.height - 64, clientY - rect.top - 10));
    tipEl.style.left = `${x}px`;
    tipEl.style.top = `${y}px`;
  }

  // ---------- 고르기·확대 ----------

  function selectTeam(id) {
    selectedId = id && nodeById.has(id) ? id : null;
    if (selectedId) activeCommId = null;
    hintEl?.classList.add('is-gone');
    refreshAll();
    if (selectedId && isNarrow()) centerOn(selectedId, { topShare: 0.3, minK: 1 });
  }

  function selectCommunity(cid) {
    selectedId = null;
    activeCommId = activeCommId === cid ? null : cid;
    hintEl?.classList.add('is-gone');
    refreshAll();
    if (activeCommId !== null && isNarrow()) {
      // 아래 시트에 가리지 않게 그 묶음 팀들을 위쪽 칸에 맞춘다
      fitToView(300, { only: n => n.communityId === activeCommId, topShare: 0.38 });
    }
  }

  function clearSelection() {
    selectedId = null;
    activeCommId = null;
    refreshAll();
  }

  function centerOn(id, { topShare = 0.5, minK = 1.45 } = {}) {
    const n = nodeById.get(id);
    if (!n || !canvasSel || !Number.isFinite(n.x)) return;
    measure();
    const k = Math.max(minK, Math.min(2.4, transform?.k || 1.65));
    const next = window.d3.zoomIdentity.translate(width / 2 - n.x * k, height * topShare - n.y * k).scale(k);
    fittedWidth = width;
    fittedHeight = height;
    canvasSel.interrupt().transition().duration(320).call(zoomBehavior.transform, next);
  }

  function focusOnTeam(id) {
    selectTeam(id);
    centerOn(id, { topShare: isNarrow() ? 0.3 : 0.5 });
  }

  /** 보이는 팀(또는 only 조건 팀)을 화면에 맞춘다. topShare < 1 이면 위쪽 그만큼의 높이에만 맞춘다 */
  function fitToView(duration = 260, { only = null, topShare = 1 } = {}) {
    if (!canvasSel || !zoomBehavior) return;
    measure();
    const vis = nodes.filter(n => Number.isFinite(n.x) && !isHiddenNode(n, hiddenRoles) && (!only || only(n)));
    if (!vis.length) return;
    let minX = Infinity;
    let maxX = -Infinity;
    let minY = Infinity;
    let maxY = -Infinity;
    for (const n of vis) {
      const r = (n.r || 8) + 8;
      minX = Math.min(minX, n.x - r);
      maxX = Math.max(maxX, n.x + r);
      minY = Math.min(minY, n.y - r);
      maxY = Math.max(maxY, n.y + r + 14);
    }
    const pad = 36;
    const areaH = height * topShare;
    const k = Math.max(0.35, Math.min(1.85, Math.min((width - pad * 2) / Math.max(120, maxX - minX), (areaH - pad * 2) / Math.max(120, maxY - minY))));
    const next = window.d3.zoomIdentity.translate(width / 2 - ((minX + maxX) / 2) * k, areaH / 2 - ((minY + maxY) / 2) * k).scale(k);
    fittedWidth = width;
    fittedHeight = height;
    canvasSel.interrupt();
    if (duration > 0) canvasSel.transition().duration(duration).call(zoomBehavior.transform, next);
    else canvasSel.call(zoomBehavior.transform, next);
  }

  function resetAll() {
    hiddenRoles.clear();
    selectedId = null;
    activeCommId = null;
    refreshAll();
    fitToView(280);
  }

  // ---------- 캔버스 조작 ----------

  function onNodeClick(n) {
    const now = Date.now();
    if (lastClick.id === n.id && now - lastClick.time < DBLCLICK_MS) {
      lastClick = { id: null, time: 0 };
      closeModal();
      window.location.hash = `#/team/${encodeURIComponent(n.team_key)}`;
      return;
    }
    lastClick = { id: n.id, time: now };
    selectTeam(selectedId === n.id ? null : n.id);
  }

  function ensureInteractions() {
    if (!window.d3 || canvasSel) return;
    const d3 = window.d3;
    measure();
    transform = d3.zoomIdentity;
    canvasSel = d3.select(canvasEl);
    zoomBehavior = d3.zoom()
      .extent([[0, 0], [width, height]])
      .scaleExtent(SCALE_EXTENT)
      .on('zoom', (event) => {
        transform = event.transform;
        requestDraw();
      });

    let start = null;
    let moved = false;
    const drag = d3.drag()
      .subject((event) => {
        const [sx, sy] = d3.pointer(event.sourceEvent || event, canvasEl);
        return findNodeAtScreen(sx, sy) || undefined;
      })
      .on('start', (event) => {
        start = d3.pointer(event.sourceEvent || event, canvasEl);
        moved = false;
        event.subject.fx = event.subject.x;
        event.subject.fy = event.subject.y;
        tipEl.hidden = true;
      })
      .on('drag', (event) => {
        const n = event.subject;
        const [sx, sy] = d3.pointer(event.sourceEvent || event, canvasEl);
        if (!moved && Math.hypot(sx - start[0], sy - start[1]) > 4) {
          moved = true;
          if (simulation && !event.active) simulation.alphaTarget(0.18).restart();
        }
        if (moved) {
          [n.fx, n.fy] = screenToWorld(sx, sy);
          requestDraw();
        }
      })
      .on('end', (event) => {
        const n = event.subject;
        if (simulation && !event.active) simulation.alphaTarget(0);
        n.fx = null;
        n.fy = null;
        if (!moved) onNodeClick(n);
      });
    canvasSel.call(drag);
    canvasSel.call(zoomBehavior);

    let bgDown = null;
    canvasEl.addEventListener('pointerdown', (e) => {
      const rect = canvasEl.getBoundingClientRect();
      bgDown = findNodeAtScreen(e.clientX - rect.left, e.clientY - rect.top) ? null : [e.clientX, e.clientY];
    });
    canvasEl.addEventListener('pointerup', (e) => {
      if (!bgDown) return;
      const dist = Math.hypot(e.clientX - bgDown[0], e.clientY - bgDown[1]);
      bgDown = null;
      if (dist <= 5 && (selectedId !== null || activeCommId !== null)) clearSelection();
    });
    canvasEl.addEventListener('pointermove', (e) => {
      if (e.buttons) return;
      const rect = canvasEl.getBoundingClientRect();
      const hit = findNodeAtScreen(e.clientX - rect.left, e.clientY - rect.top);
      const next = hit ? hit.id : null;
      if (next !== hoveredId) {
        hoveredId = next;
        canvasEl.style.cursor = hit ? 'pointer' : 'grab';
        if (hit) hintEl?.classList.add('is-gone');
        requestDraw();
      }
      if (hit) showTip(hit, e.clientX, e.clientY);
      else tipEl.hidden = true;
    });
    canvasEl.addEventListener('pointerleave', () => {
      if (hoveredId !== null) {
        hoveredId = null;
        requestDraw();
      }
      tipEl.hidden = true;
    });
  }

  function startSimulation() {
    simulation?.stop();
    simulation = null;
    if (!nodes.length) {
      requestDraw();
      return;
    }
    const d3 = window.d3;
    measure();
    ensureInteractions();
    const scores = nodes.map(n => n.score);
    const minS = Math.min(...scores);
    const maxS = Math.max(...scores);
    for (const n of nodes) n.r = sceneRadius(n.score, minS, maxS);

    // 묶음별로 살짝 모아 놓고 시작 (매번 같은 자리)
    const golden = Math.PI * (3 - Math.sqrt(5));
    const slots = Math.max(1, Math.min(8, communities.length));
    nodes.forEach((n, i) => {
      const a = i * golden;
      const rad = 28 + Math.sqrt(i + 1) * 18;
      const base = n.colorSlot >= 0 ? (n.colorSlot / slots) * Math.PI * 2 : null;
      n.x = base === null ? Math.cos(a) * rad * 1.1 : Math.cos(base) * 110 + Math.cos(a) * rad * 0.55;
      n.y = base === null ? Math.sin(a) * rad * 1.1 : Math.sin(base) * 110 + Math.sin(a) * rad * 0.55;
      n.vx = 0;
      n.vy = 0;
    });
    const chargeBase = nodes.length > 220 ? -82 : nodes.length > 140 ? -102 : -125;
    simulation = d3.forceSimulation(nodes)
      .force('link', d3.forceLink(edges).id(d => d.id)
        .distance(e => Math.max(34, 78 - Math.min(34, Math.sqrt(e.weight) * 12)))
        .strength(e => Math.min(0.68, 0.18 + Math.sqrt(e.weight) * 0.1)))
      .force('charge', d3.forceManyBody().strength(n => chargeBase - n.r * 3.2).distanceMax(340))
      .force('collide', d3.forceCollide(n => n.r + (n.had_outcome ? 5 : 3.2)).iterations(2))
      .force('x', d3.forceX(0).strength(0.055))
      .force('y', d3.forceY(0).strength(0.055))
      .alphaDecay(0.032)
      .on('tick', requestDraw);
    simulation.stop();
    const pre = nodes.length > 200 ? 75 : 95;
    for (let i = 0; i < pre; i++) simulation.tick();
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
    metaEl.textContent = '불러오는 중...';
    showEmpty('씬 네트워크를 계산하는 중...');
    try {
      const res = await querySceneNetwork({ limit: currentLimit, genre: currentGenre });
      if (destroyed || seq !== loadSeq) return;
      nodes = res.nodes || [];
      edges = res.edges || [];
      communities = res.communities || [];
      stats = { genre: currentGenre, teams: nodes.length, cand: res.candidateCount || 0, winners: res.winnerCount || 0, links: edges.length };
      nodeById = new Map(nodes.map(n => [n.id, n]));
      adjMap = new Map(nodes.map(n => [n.id, []]));
      for (const e of edges) {
        const a = nodeById.get(e.source);
        const b = nodeById.get(e.target);
        if (!a || !b) continue;
        adjMap.get(a.id).push({ neighbor: b, weight: e.weight, detail: e.detail, last_date: e.last_date });
        adjMap.get(b.id).push({ neighbor: a, weight: e.weight, detail: e.detail, last_date: e.last_date });
      }
      for (const list of adjMap.values()) list.sort((x, y) => (y.weight - x.weight) || (y.neighbor.score - x.neighbor.score));
      if (selectedId && !nodeById.has(selectedId)) selectedId = null;
      if (activeCommId !== null && !communities.some(c => c.id === activeCommId)) activeCommId = null;
      hoveredId = null;
      pal = readPalette();
      if (nodes.length) emptyEl.hidden = true;
      else showEmpty(currentGenre ? `'${currentGenre}' 장르에 보일 팀이 없습니다.` : '보일 팀 데이터가 없습니다.');
      refreshAll();
      startSimulation();
    } catch (err) {
      if (destroyed || seq !== loadSeq) return;
      showEmpty(`씬 네트워크를 불러오지 못했습니다: ${err?.message || err}`);
      metaEl.textContent = '불러오기 실패';
    }
  }

  // ---------- 찾기 ----------

  function closeSearchMenu() {
    searchMenu.hidden = true;
  }

  function renderSearch(q) {
    if (!String(q || '').trim() || !nodes.length) {
      closeSearchMenu();
      return;
    }
    searchMenu.innerHTML = searchMenuHtml(matchTeams(nodes, q), nodes.length, colorOf);
    searchMenu.hidden = false;
  }

  searchInput.addEventListener('input', () => renderSearch(searchInput.value));
  searchInput.addEventListener('focus', () => renderSearch(searchInput.value));
  searchInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      const first = searchMenu.querySelector('[data-sn-pick]');
      if (first) {
        e.preventDefault();
        first.click();
      }
    } else if (e.key === 'Escape') closeSearchMenu();
  });
  searchMenu.addEventListener('click', (e) => {
    const pick = e.target.closest('[data-sn-pick]');
    const n = pick && nodeById.get(pick.dataset.snPick);
    if (!n) return;
    searchInput.value = n.display_name;
    closeSearchMenu();
    if (isHiddenNode(n, hiddenRoles)) hiddenRoles.clear();
    focusOnTeam(n.id);
  });
  function onDocClick(e) {
    if (searchWrap && !searchWrap.contains(e.target)) closeSearchMenu();
  }
  document.addEventListener('click', onDocClick);

  // ---------- 머리 단추: 장르·팀 수·크게 보기 ----------

  function syncSeg(attr, isActive) {
    hostEl.querySelectorAll(`[${attr}]`).forEach((b) => {
      const on = isActive(b);
      b.classList.toggle('active', on);
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
  }

  hostEl.addEventListener('click', (e) => {
    const g = e.target.closest('[data-sn-genre]');
    if (g && (g.dataset.snGenre || '') !== currentGenre) {
      currentGenre = g.dataset.snGenre || '';
      appState.cfg.genre = currentGenre;
      syncHash(true);
      syncSeg('data-sn-genre', b => (b.dataset.snGenre || '') === currentGenre);
      searchInput.value = '';
      closeSearchMenu();
      selectedId = null;
      activeCommId = null;
      loadNetwork();
      return;
    }
    const lim = e.target.closest('[data-sn-limit]');
    if (lim && Number(lim.dataset.snLimit) !== currentLimit) {
      currentLimit = Number(lim.dataset.snLimit) || 150;
      appState.sceneNetLimit = currentLimit;
      syncHash(true);
      syncSeg('data-sn-limit', b => Number(b.dataset.snLimit) === currentLimit);
      loadNetwork();
      return;
    }
    if (e.target.closest('[data-sn-open-modal]')) openModal();
  });

  // ---------- 겉칸(칩·무대 단추·패널) — 크게 보기에서 모달로 옮겨 가므로 여기에 건다 ----------

  function onSurfaceClick(e) {
    const t = e.target;
    const zoom = t.closest('[data-sn-zoom]');
    if (zoom && canvasSel) {
      const mode = zoom.dataset.snZoom;
      canvasSel.interrupt();
      if (mode === 'in') canvasSel.transition().duration(180).call(zoomBehavior.scaleBy, ZOOM_STEP);
      else if (mode === 'out') canvasSel.transition().duration(180).call(zoomBehavior.scaleBy, 1 / ZOOM_STEP);
      else fitToView(240);
      return;
    }
    if (t.closest('[data-sn-reset]')) {
      resetAll();
      return;
    }
    const comm = t.closest('[data-sn-comm], [data-sn-comm-pick]');
    if (comm) {
      selectCommunity(Number(comm.dataset.snComm ?? comm.dataset.snCommPick));
      return;
    }
    const role = t.closest('[data-sn-role]');
    if (role) {
      const key = role.dataset.snRole;
      if (hiddenRoles.has(key)) hiddenRoles.delete(key);
      else hiddenRoles.add(key);
      if (selectedId && isHiddenNode(nodeById.get(selectedId), hiddenRoles)) selectedId = null;
      refreshAll();
      return;
    }
    if (t.closest('[data-sn-close]')) {
      clearSelection();
      return;
    }
    const jump = t.closest('[data-sn-jump]');
    if (jump) {
      focusOnTeam(jump.dataset.snJump);
      return;
    }
    if (t.closest('a[href^="#/"]')) closeModal();
  }
  surfaceEl.addEventListener('click', onSurfaceClick);

  function onKeydown(e) {
    if (e.key !== 'Escape') return;
    if (selectedId !== null || activeCommId !== null) clearSelection();
    else if (modalBackdrop) closeModal();
  }
  document.addEventListener('keydown', onKeydown);

  function openModal() {
    if (modalBackdrop || destroyed) return;
    modalBackdrop = document.createElement('div');
    modalBackdrop.className = 'graph-modal-backdrop rg-modal-backdrop';
    modalBackdrop.setAttribute('role', 'dialog');
    modalBackdrop.setAttribute('aria-modal', 'true');
    modalBackdrop.setAttribute('aria-label', '씬 네트워크 크게 보기');
    modalBackdrop.innerHTML = `
      <div class="graph-modal rg sn rg-modal">
        <div class="rg-head">
          <div class="rg-head-title"><h2>씬 네트워크</h2><span class="block-meta">${escapeHtml(currentGenre || '전체 장르')}</span></div>
          <div class="rg-head-actions"><button type="button" class="btn btn-sm" data-sn-close-modal>닫기 ✕</button></div>
        </div>
        <div class="rg-modal-slot" data-sn-modal-slot></div>
      </div>`;
    modalBackdrop.querySelector('[data-sn-modal-slot]').appendChild(surfaceEl);
    surfaceEl.classList.add('is-expanded');
    document.body.appendChild(modalBackdrop);
    document.body.classList.add('graph-modal-open');
    modalBackdrop.addEventListener('click', (e) => {
      if (e.target === modalBackdrop || e.target.closest('[data-sn-close-modal]')) closeModal();
    });
    requestAnimationFrame(() => {
      if (!destroyed) fitToView(180);
    });
    modalBackdrop.querySelector('[data-sn-close-modal]')?.focus();
  }

  function closeModal() {
    if (!modalBackdrop) return;
    canvasSel?.interrupt();
    document.body.classList.remove('graph-modal-open');
    surfaceEl.classList.remove('is-expanded');
    if (inlineSlot?.isConnected) inlineSlot.appendChild(surfaceEl);
    modalBackdrop.remove();
    modalBackdrop = null;
    requestAnimationFrame(() => {
      if (!destroyed) fitToView(180);
    });
  }

  // ---------- 테마·크기 ----------

  themeObserver = new MutationObserver(() => {
    if (destroyed || !nodes.length) return;
    requestAnimationFrame(() => {
      pal = readPalette();
      renderChips();
      requestDraw();
    });
  });
  themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });

  if (typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(() => {
      if (destroyed || !stageEl.isConnected) return;
      measure();
      const big = fittedWidth > 0 && (Math.abs(width - fittedWidth) > 36 || Math.abs(height - fittedHeight) > 36);
      if (big && nodes.length) {
        if (selectedId) centerOn(selectedId, { topShare: isNarrow() ? 0.3 : 0.5, minK: 1 });
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
    document.removeEventListener('keydown', onKeydown);
    if (rafId) cancelAnimationFrame(rafId);
    try { canvasSel?.interrupt(); } catch (_) { /* 이미 멈춤 */ }
    closeModal();
    simulation?.stop();
    simulation = null;
    themeObserver?.disconnect();
    resizeObserver?.disconnect();
  }

  const handle = { destroy };
  registerChart(handle);

  Promise.all([ensureGraphCss(), window.d3 ? Promise.resolve() : ensureD3().catch(() => null)])
    .then(() => {
      if (!destroyed) loadNetwork();
    });

  return handle;
}
