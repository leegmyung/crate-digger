// 씬 네트워크(graph_scene.js) 캔버스 그리기 — 선 → 노드(사진) → 라벨 순. 배경은 그리지 않아 css 점 무늬가 비친다.
import { estimateLabelWidth, labelBudget, pickVisibleLabels, shortLabel } from './graph_model.js';
import { isHiddenNode, sceneLabelPriority } from './graph_scene_model.js';

const PHOTO_MIN_SCREEN_R = 9;   // 화면에서 이보다 작으면 사진 대신 색 동그라미
const PHOTO_MAX = 160;          // 한 번에 그리는 사진 수 상한 (성능)
const DIM_NODE = 0.12;
const DIM_EDGE = 0.06;
const LABEL_FONT = '"Pretendard", -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", sans-serif';

function strokeLine(ctx, s, g) {
  ctx.beginPath();
  ctx.moveTo(s.x, s.y);
  ctx.lineTo(g.x, g.y);
  ctx.stroke();
}

function drawEdges(ctx, st, inv) {
  const { edges, focus, pal, hiddenRoles } = st;
  const ok = e => e.source && e.target && Number.isFinite(e.source.x) && Number.isFinite(e.target.x)
    && !isHiddenNode(e.source, hiddenRoles) && !isHiddenNode(e.target, hiddenRoles);
  const isHi = e => (focus.focusId
    ? (e.source.id === focus.focusId || e.target.id === focus.focusId)
    : (focus.set.has(e.source.id) && focus.set.has(e.target.id)));
  ctx.lineCap = 'round';
  if (!st.focusOn) {
    ctx.strokeStyle = pal.edge;
    ctx.globalAlpha = 0.5;
    for (const e of edges) {
      if (!ok(e)) continue;
      ctx.lineWidth = Math.min(4.2, 0.6 + Math.sqrt(e.weight) * 0.8) * inv;
      strokeLine(ctx, e.source, e.target);
    }
    return;
  }
  ctx.strokeStyle = pal.edge;
  ctx.globalAlpha = DIM_EDGE;
  for (const e of edges) {
    if (!ok(e) || isHi(e)) continue;
    ctx.lineWidth = Math.min(3.4, 0.55 + Math.sqrt(e.weight) * 0.7) * inv;
    strokeLine(ctx, e.source, e.target);
  }
  ctx.strokeStyle = st.hiColor;
  ctx.globalAlpha = 0.9;
  for (const e of edges) {
    if (!ok(e) || !isHi(e)) continue;
    ctx.lineWidth = Math.min(5, 1 + Math.sqrt(e.weight) * 1.05) * inv;
    strokeLine(ctx, e.source, e.target);
  }
}

function drawNode(ctx, st, n, alpha, inv, photoBudget) {
  const { pal, k } = st;
  const r = n.r || 7;
  ctx.globalAlpha = alpha;
  if (n.id === st.selectedId || n.id === st.hoveredId) {
    ctx.beginPath();
    ctx.arc(n.x, n.y, r + (n.had_outcome ? 6.5 : 4.5) * inv, 0, Math.PI * 2);
    ctx.strokeStyle = n.id === st.selectedId ? pal.accent : pal.ink;
    ctx.lineWidth = (n.id === st.selectedId ? 2.6 : 1.6) * inv;
    ctx.stroke();
  }
  if (n.had_outcome) {
    ctx.beginPath();
    ctx.arc(n.x, n.y, r + 2.8 * inv, 0, Math.PI * 2);
    ctx.fillStyle = pal.stage;
    ctx.fill();
    ctx.strokeStyle = st.ringOf(n);
    ctx.lineWidth = 2.6 * inv;
    ctx.stroke();
  }
  const color = st.colorOf(n);
  const img = r * k >= PHOTO_MIN_SCREEN_R && photoBudget.left > 0 ? st.photoOf(n) : null;
  ctx.beginPath();
  ctx.arc(n.x, n.y, r, 0, Math.PI * 2);
  ctx.fillStyle = color;
  ctx.fill();
  if (img) {
    photoBudget.left -= 1;
    ctx.save();
    ctx.beginPath();
    ctx.arc(n.x, n.y, Math.max(2, r - 1.2 * inv), 0, Math.PI * 2);
    ctx.clip();
    const side = Math.min(img.naturalWidth, img.naturalHeight) || 1;
    ctx.drawImage(img, (img.naturalWidth - side) / 2, (img.naturalHeight - side) / 2, side, side, n.x - r, n.y - r, r * 2, r * 2);
    ctx.restore();
    ctx.beginPath();
    ctx.arc(n.x, n.y, r, 0, Math.PI * 2);
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.8 * inv;
    ctx.stroke();
  } else if (!n.had_outcome) {
    ctx.strokeStyle = pal.stage;
    ctx.lineWidth = 1.2 * inv;
    ctx.stroke();
  }
}

function drawLabels(ctx, st, visible) {
  const { t, k, w, h, focus, pal } = st;
  const pinned = new Set([st.selectedId, st.hoveredId, focus?.focusId].filter(Boolean));
  const pool = focus ? visible.filter(n => focus.set.has(n.id)) : visible;
  const items = [];
  const meta = new Map();
  for (const n of pool) {
    const sx = n.x * k + t.x;
    const sy = n.y * k + t.y;
    if (sx < -40 || sx > w + 40 || sy < -24 || sy > h + 24) continue;
    const primary = pinned.has(n.id);
    const fs = primary ? 12.5 : (n.had_outcome ? 11.5 : 11);
    const text = shortLabel(n.display_name, primary ? 20 : 14);
    const ly = sy + Math.max(7, ((n.r || 7) + (n.had_outcome ? 3.5 : 1.5)) * k) + 3;
    items.push({ id: n.id, x: sx, y: ly, w: estimateLabelWidth(text, fs), h: fs + 2, priority: sceneLabelPriority(n) });
    meta.set(n.id, { sx, ly, fs, text, primary, n });
  }
  const budget = focus ? items.length : labelBudget(k, visible.length);
  const on = pickVisibleLabels(items, { budget, pinned, pad: 4 });
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  ctx.lineJoin = 'round';
  ctx.globalAlpha = 1;
  for (const id of on) {
    const m = meta.get(id);
    if (!m) continue;
    ctx.font = `${m.primary || m.n.had_outcome ? 700 : 600} ${m.fs}px ${LABEL_FONT}`;
    ctx.strokeStyle = pal.stage;
    ctx.lineWidth = 3.6;
    ctx.strokeText(m.text, m.sx, m.ly);
    ctx.fillStyle = m.primary || m.n.had_outcome || focus ? pal.ink : pal.muted;
    ctx.fillText(m.text, m.sx, m.ly);
  }
}

/**
 * @param {CanvasRenderingContext2D} ctx
 * @param {{ w: number, h: number, dpr: number, t: {x: number, y: number, k: number}, nodes: object[], edges: object[],
 *   pal: object, focus: {focusId: string|null, set: Set<string>}|null, selectedId: string|null, hoveredId: string|null,
 *   hiddenRoles: Set<string>, colorOf: Function, ringOf: Function, photoOf: Function }} st
 */
export function drawScene(ctx, st) {
  ctx.save();
  ctx.setTransform(st.dpr, 0, 0, st.dpr, 0, 0);
  ctx.clearRect(0, 0, st.w, st.h);
  if (!st.nodes.length) {
    ctx.restore();
    return;
  }
  const k = st.t.k || 1;
  const inv = 1 / Math.max(0.65, Math.sqrt(k));
  const focus = st.focus;
  const focusNode = focus?.focusId ? st.nodes.find(n => n.id === focus.focusId) : null;
  const draw = {
    ...st, k, focusOn: Boolean(focus), focus: focus || { focusId: null, set: new Set() },
    hiColor: focusNode ? st.colorOf(focusNode) : (focus ? st.pal.accent : st.pal.edge),
  };
  const visible = st.nodes.filter(n => Number.isFinite(n.x) && !isHiddenNode(n, st.hiddenRoles));

  ctx.save();
  ctx.translate(st.t.x, st.t.y);
  ctx.scale(k, k);
  drawEdges(ctx, draw, inv);
  const photoBudget = { left: PHOTO_MAX };
  if (focus) {
    for (const n of visible) if (!focus.set.has(n.id)) drawNode(ctx, draw, n, DIM_NODE, inv, { left: 0 });
    for (const n of visible) if (focus.set.has(n.id)) drawNode(ctx, draw, n, 1, inv, photoBudget);
  } else {
    for (const n of visible) drawNode(ctx, draw, n, 0.96, inv, photoBudget);
  }
  ctx.restore();

  drawLabels(ctx, { ...draw, focus }, visible);
  ctx.restore();
}
