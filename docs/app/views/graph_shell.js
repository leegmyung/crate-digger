// 팀 관계망(graph.js)의 뼈대 HTML · 노드 모양 그리기 · 스타일 파일 붙이기.
import { escapeHtml } from '../ui.js';

const CSS_TIMEOUT_MS = 2500;

// ---------- 스타일 파일 (dashboard.html 에 없으면 여기서 붙인다) ----------

const GRAPH_CSS_HREF = new URL('../css/graph.css', import.meta.url).href;
let cssReady = null;

export function ensureGraphCss() {
  if (cssReady) return cssReady;
  const has = [...document.querySelectorAll('link[rel="stylesheet"]')].some(l => l.href === GRAPH_CSS_HREF);
  if (has) {
    cssReady = Promise.resolve();
    return cssReady;
  }
  cssReady = new Promise((resolve) => {
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = GRAPH_CSS_HREF;
    link.addEventListener('load', () => resolve());
    link.addEventListener('error', () => resolve()); // 스타일이 없어도 그림은 그린다
    setTimeout(resolve, CSS_TIMEOUT_MS);
    document.head.appendChild(link);
  });
  return cssReady;
}

// ---------- 노드 모양 ----------

function polygonPath(r, sides, rotate = 0) {
  const pts = [];
  for (let i = 0; i < sides; i++) {
    const a = rotate + (i * 2 * Math.PI) / sides;
    pts.push(`${(Math.cos(a) * r).toFixed(2)},${(Math.sin(a) * r).toFixed(2)}`);
  }
  return `M${pts.join('L')}Z`;
}

function monogramOf(name) {
  const ch = Array.from(String(name || '').trim())[0] || '?';
  return /[a-z]/.test(ch) ? ch.toUpperCase() : ch;
}

/** 종류별 모양을 g 안에 그린다. clipId 는 사진 동그라미 자르기용 */
export function drawNodeShape(g, d, clipId, defs) {
  const r = d.r;
  g.append('circle').attr('class', 'rg-ring').attr('r', r + (d.node_type === 'ego' ? 6 : 4));
  const type = d.node_type;
  if (type === 'venue') {
    const s = r * 1.7;
    g.append('rect').attr('class', 'rg-disc').attr('x', -s / 2).attr('y', -s / 2)
      .attr('width', s).attr('height', s).attr('rx', r * 0.38);
  } else if (type === 'program') {
    g.append('path').attr('class', 'rg-disc').attr('d', polygonPath(r * 1.25, 4));
  } else if (type === 'agency') {
    g.append('path').attr('class', 'rg-disc').attr('d', polygonPath(r * 1.12, 6, Math.PI / 6));
  } else {
    g.append('circle').attr('class', 'rg-disc').attr('r', r);
  }

  if ((type === 'team' || type === 'ego') && d.photoUrl) {
    defs.append('clipPath').attr('id', clipId).append('circle').attr('r', Math.max(4, r - 1.5));
    g.append('image').attr('class', 'rg-photo').attr('href', d.photoUrl)
      .attr('x', -r).attr('y', -r).attr('width', r * 2).attr('height', r * 2)
      .attr('preserveAspectRatio', 'xMidYMid slice').attr('clip-path', `url(#${clipId})`)
      .on('error', function onPhotoError() {
        window.d3.select(this).remove();
        g.append('text').attr('class', 'rg-glyph').attr('font-size', Math.max(9, r * 0.8)).text(monogramOf(d.label));
      });
    // 사진 위 얇은 테두리 (종류 색)
    g.append('circle').attr('class', 'rg-photo-edge').attr('r', r);
    return;
  }
  let glyph = '';
  if (type === 'team' || type === 'ego') glyph = monogramOf(d.label);
  else if (type === 'outcome') glyph = String(d.grade || '상').toUpperCase();
  else if (type === 'scene') glyph = `#${d.node_key}`;
  if (glyph) {
    const fs = type === 'scene' ? 8.5 : Math.max(9, r * (type === 'outcome' ? 0.95 : 0.8));
    g.append('text').attr('class', 'rg-glyph').attr('font-size', fs).text(glyph);
  }
}

// ---------- 화면 뼈대 ----------

const ICON_FIT = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M2 6V2h4M10 2h4v4M14 10v4h-4M6 14H2v-4" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>';
const ICON_RESET = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3.2 7.2a5 5 0 1 1 1.3 4.3M3 3.5v3.7h3.7" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>';

export function periodToggleHtml(period) {
  return `
    <div class="seg-toggle graph-period-toggle" role="group" aria-label="관계망 기간">
      <button type="button" class="seg-btn ${period === 'all' ? 'active' : ''}" data-graph-period="all" aria-pressed="${period === 'all'}">전체</button>
      <button type="button" class="seg-btn ${period === '1y' ? 'active' : ''}" data-graph-period="1y" aria-pressed="${period === '1y'}">최근 1년</button>
    </div>`;
}

export function shellHtml(displayName, period) {
  return `
    <section class="block rg graph-block" id="teamGraphBlock">
      <div class="rg-head">
        <div class="rg-head-title">
          <h2>관계망</h2>
          <span class="block-meta" data-rg-meta>불러오는 중...</span>
        </div>
        <div class="rg-head-actions">
          ${periodToggleHtml(period)}
          <button type="button" class="btn btn-sm" data-rg-open-modal aria-label="관계망 크게 보기">크게 보기 ⤢</button>
        </div>
      </div>
      <div class="rg-slot" data-rg-inline-slot>
        <div class="rg-surface" data-rg-surface>
          <div class="rg-filters" role="group" aria-label="관계 종류 (색 범례 · 눌러서 숨기기)" data-rg-filters></div>
          <div class="rg-body" data-rg-body>
            <div class="rg-stage" data-rg-stage>
              <svg class="graph-svg rg-svg" data-rg-svg role="img" aria-label="${escapeHtml(displayName)} 관계망 그래프"></svg>
              <p class="rg-hint" data-rg-hint>마우스를 올리면 이웃만 밝게 · 누르면 자세히</p>
              <div class="rg-ctrls" role="group" aria-label="그래프 조작">
                <button type="button" data-rg-zoom="in" title="확대" aria-label="확대">+</button>
                <button type="button" data-rg-zoom="out" title="축소" aria-label="축소">−</button>
                <button type="button" data-rg-zoom="fit" title="화면에 맞추기" aria-label="화면에 맞추기">${ICON_FIT}</button>
                <button type="button" data-rg-reset title="처음으로 (펼친 연결·숨김 풀기)" aria-label="처음으로">${ICON_RESET}</button>
              </div>
              <button type="button" class="rg-more" data-rg-more hidden></button>
              <div class="graph-tooltip rg-tip" data-rg-tip hidden></div>
              <div class="graph-empty" data-rg-empty hidden></div>
            </div>
            <aside class="rg-panel" data-rg-panel aria-label="고른 노드 자세히" aria-live="polite"></aside>
          </div>
          <p class="rg-foot"><span><i class="rg-key-size" aria-hidden="true"></i>크기 = 오늘 점수 순위</span><span><i class="rg-key-line" aria-hidden="true"></i>굵기 = 같은 무대 횟수</span><span><i class="rg-key-dash" aria-hidden="true"></i>점선 = 같은 소속사</span><span class="rg-foot-tip">두 번 누르면 연결 펼치기</span></p>
        </div>
      </div>
    </section>`;
}
