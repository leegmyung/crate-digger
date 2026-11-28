/**
 * 그래프 PNG 내려받기 — 외부 라이브러리 없이 canvas 로.
 * - SVG 그래프(관계망 graph-svg · 공연장 흐름 vf-svg · 공연장 점 지도): 화면에 보이는 색(CSS 변수)을 요소마다 style 로 박아 넣은 뒤
 *   이미지로 그려 canvas → PNG. (CSS 변수는 따로 떨어진 SVG 이미지에서 안 풀리므로)
 * - Chart.js 그래프(canvas): 배경색을 깔아 PNG.
 * 화면이 그려질 때마다 대상 그래프 오른쪽 위에 작은 'PNG' 단추를 붙인다 (app.js boot 에서 initChartPng 한 번).
 * 순수 부분(파일 이름·크기)은 tests/js/team_print.test.mjs.
 */

const SCALE = 2;                       // 선명하게 2배로
const SVG_TARGETS = 'svg.graph-svg, svg.vf-svg, .venue-map svg, svg[data-png]';
const STYLE_PROPS = ['fill', 'fill-opacity', 'stroke', 'stroke-width', 'stroke-opacity', 'stroke-dasharray', 'opacity',
  'font-size', 'font-family', 'font-weight', 'text-anchor', 'dominant-baseline', 'visibility', 'display'];
const SVG_NS = 'http://www.w3.org/2000/svg';

/** 내려받을 파일 이름: 글자·숫자·한글만 남기고 나머지는 '_' (+ 기준일). */
export function pngFileName(label, day = '') {
  const base = String(label || 'chart').replace(/[^\p{L}\p{N}]+/gu, '_').replace(/^_+|_+$/g, '') || 'chart';
  return `${day ? `${base}_${day}` : base}.png`;
}

/** 그릴 크기: 화면 크기 × 배율, 화면 크기가 0이면(숨은 칸) viewBox 크기로. */
export function pngSize(rect, scale = SCALE, fallback = { width: 600, height: 400 }) {
  const w = rect?.width > 0 ? rect.width : fallback.width;
  const h = rect?.height > 0 ? rect.height : fallback.height;
  return { width: Math.round(w * scale), height: Math.round(h * scale) };
}

function download(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function backgroundColor() {
  return getComputedStyle(document.body).backgroundColor || '#ffffff';
}

/** 화면에 보이는 계산된 스타일을 복제본 요소마다 박아 넣는다. */
function inlineStyles(src, dst) {
  const cs = getComputedStyle(src);
  const style = STYLE_PROPS.map(p => `${p}:${cs.getPropertyValue(p)}`).join(';');
  dst.setAttribute('style', `${dst.getAttribute('style') || ''};${style}`);
  const sk = src.children;
  const dk = dst.children;
  for (let i = 0; i < sk.length && i < dk.length; i += 1) inlineStyles(sk[i], dk[i]);
}

function viewBoxSize(svg) {
  const vb = svg.viewBox?.baseVal;
  return vb && vb.width ? { width: vb.width, height: vb.height } : undefined;
}

function svgToPng(svg, filename) {
  const rect = svg.getBoundingClientRect();
  const size = pngSize(rect, SCALE, viewBoxSize(svg));
  const clone = svg.cloneNode(true);
  inlineStyles(svg, clone);
  clone.setAttribute('xmlns', SVG_NS);
  clone.setAttribute('width', String(size.width / SCALE));
  clone.setAttribute('height', String(size.height / SCALE));
  if (!clone.getAttribute('viewBox') && rect.width) clone.setAttribute('viewBox', `0 0 ${rect.width} ${rect.height}`);
  const markup = new XMLSerializer().serializeToString(clone);
  const img = new Image();
  img.onload = () => {
    const canvas = document.createElement('canvas');
    canvas.width = size.width;
    canvas.height = size.height;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = backgroundColor();
    ctx.fillRect(0, 0, size.width, size.height);
    ctx.drawImage(img, 0, 0, size.width, size.height);
    canvas.toBlob(b => { if (b) download(b, filename); }, 'image/png');
  };
  img.onerror = () => window.dispatchEvent(new CustomEvent('app:toast', { detail: 'PNG로 바꾸지 못했습니다' }));
  img.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(markup)}`;
}

function canvasToPng(src, filename) {
  const canvas = document.createElement('canvas');
  canvas.width = src.width;
  canvas.height = src.height;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = backgroundColor();
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(src, 0, 0);
  canvas.toBlob(b => { if (b) download(b, filename); }, 'image/png');
}

function labelOf(el) {
  return el.getAttribute('aria-label') || el.closest('[aria-label]')?.getAttribute('aria-label')
    || el.closest('section, .block')?.querySelector('h2, h3')?.textContent || document.title;
}

function attachButtons(root) {
  const targets = [...root.querySelectorAll(SVG_TARGETS)];
  if (window.Chart?.getChart) {
    for (const cv of root.querySelectorAll('canvas')) if (window.Chart.getChart(cv)) targets.push(cv);
  }
  for (const el of targets) {
    const host = el.parentElement;
    if (!host || host.querySelector(':scope > .png-btn')) continue;
    if (getComputedStyle(host).position === 'static') host.style.position = 'relative';
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'btn btn-sm png-btn';
    btn.textContent = 'PNG';
    btn.title = '이 그래프를 PNG 그림으로 내려받기';
    btn.setAttribute('aria-label', `${labelOf(el)} PNG 내려받기`);
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      const target = host.querySelector(':scope > svg, :scope > canvas') || el;
      const name = pngFileName(labelOf(target), document.querySelector('#topStatus')?.textContent?.match(/\d{4}-\d{2}-\d{2}/)?.[0] || '');
      if (target instanceof HTMLCanvasElement) canvasToPng(target, name);
      else svgToPng(target, name);
    });
    host.appendChild(btn);
  }
}

let started = false;
let raf = 0;

/** 한 번만 부른다 (app.js boot). 화면이 바뀔 때마다 새 그래프에 단추를 붙인다. */
export function initChartPng() {
  if (started) return;
  started = true;
  const root = document.getElementById('viewRoot');
  if (!root || typeof MutationObserver === 'undefined') return;
  new MutationObserver(() => {
    if (raf) return;
    raf = requestAnimationFrame(() => {
      raf = 0;
      attachButtons(root);
    });
  }).observe(root, { childList: true, subtree: true });
}
