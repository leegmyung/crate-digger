/**
 * 시·도 지도 (#/cities 첫 화면 · #/city/<이름>) — 단순한 면 지도(위성 아님) + 색 농도 + 숫자 라벨 + 말풍선.
 * 시·도를 누르면 그 지역으로 확대되며 공연장 좌표를 열점(번진 원)과 점으로 보여 주고, 점을 누르면 #/venue/<이름>.
 * 경계: docs/app/data/kr_sido.json (Natural Earth, 퍼블릭 도메인 — scripts/build_kr_map.py 로 만듦).
 * 라이브러리 없이 SVG 로 그린다(위도 36도 기준 등장방형 투영 — 한국 정도 넓이에서는 충분히 반듯하다).
 * 다른 앱 모듈을 부르지 않는다(node 로 순수 함수 검사: tests/js/region_map.test.mjs).
 */

/** 공연장 목록의 도시 → 시·도 짧은 이름. 없는 도시는 좌표로 찾는다(sidoOfVenue). */
export const CITY_TO_SIDO = Object.freeze({
  서울: '서울', 부산: '부산', 대구: '대구', 인천: '인천', 광주: '광주', 대전: '대전', 울산: '울산', 세종: '세종',
  수원: '경기', 안양: '경기', 성남: '경기', 고양: '경기', 부천: '경기', 용인: '경기', 파주: '경기', 의정부: '경기',
  안산: '경기', 화성: '경기', 남양주: '경기', 평택: '경기', 김포: '경기', 광명: '경기', 시흥: '경기', 하남: '경기',
  춘천: '강원', 원주: '강원', 강릉: '강원', 속초: '강원',
  청주: '충북', 충주: '충북', 천안: '충남', 아산: '충남', 공주: '충남',
  전주: '전북', 군산: '전북', 익산: '전북', 목포: '전남', 여수: '전남', 순천: '전남', 광양: '전남', 구례: '전남', 나주: '전남',
  포항: '경북', 경주: '경북', 안동: '경북', 구미: '경북',
  창원: '경남', 진주: '경남', 거제: '경남', 김해: '경남', 통영: '경남', 양산: '경남',
  제주: '제주', 서귀포: '제주',
});

export const METRICS = Object.freeze({
  venues: { label: '공연장 수', unit: '곳', desc: '공연 기록이 있는 공연장' },
  nights: { label: '최근 12개월 공연 밤', unit: '일', desc: '최근 12개월 공연 날짜 수(같은 날·같은 공연장 = 1)' },
  teams: { label: '활동 팀 수', unit: '팀', desc: '최근 1년 이 지역 무대에 선 팀(도시별 합이라 한 팀이 두 번 셀 수 있음)' },
});

const LON0 = 124.4;
const LAT0 = 38.75;
const SCALE = 100; // 1도 = 100 단위
const KX = Math.cos((36 * Math.PI) / 180);
const MIN_VIEW_W = 30; // 확대 최소 폭(단위) — 아주 작은 시·도도 너무 크게 키우지 않게
const ZOOM_MS = 450;
const DOT_PX = [4, 9]; // 점 반지름(화면 px) 최소·최대 — 최근 12개월 공연 밤으로 키운다
const HEAT_PX = 28;
const BLUR_PX = 11;
const TOP_VENUES = 8;
const MAX_STAGE_VH = 72; // 지도 높이 상한(화면 높이 %) — 폭으로 막아야 SVG 비율과 겹친 라벨 위치가 어긋나지 않는다
/** 좁은 광역시 라벨은 바다·빈 곳으로 빼고 이음선을 긋는다 [경도, 위도] */
const LABEL_AT = Object.freeze({
  서울: [127.05, 38.05], 인천: [125.95, 37.62], 세종: [126.85, 36.82], 대전: [127.62, 36.18],
  광주: [126.55, 35.38], 대구: [128.93, 35.95], 울산: [129.72, 35.62], 부산: [129.3, 34.98],
});
/** 이음선 없이 자리만 옮기는 라벨(가운데가 다른 라벨과 겹치는 도) [경도, 위도] */
const LABEL_POS = Object.freeze({ 경기: [127.48, 37.62], 충남: [126.72, 36.4], 경북: [128.75, 36.5] });

const hasNum = v => v !== null && v !== undefined && v !== '' && Number.isFinite(Number(v));
const r1 = n => Math.round(n * 10) / 10;
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
const fmt = n => Number(n || 0).toLocaleString('ko-KR');

/** [경도, 위도] → SVG 좌표 [x, y] (북쪽이 위) */
export function project(lon, lat) {
  return [(lon - LON0) * KX * SCALE, (LAT0 - lat) * SCALE];
}

/** 고리 목록 → SVG 경로 d (구멍은 fill-rule: evenodd 로) */
export function ringsPath(rings) {
  return rings.map(r => `M${r.map(([x, y]) => project(x, y).map(r1).join(',')).join('L')}Z`).join('');
}

const pathCache = new WeakMap();
/** 시·도 경계 경로 [{ name, full, d }] — 같은 자료(geo)면 한 번만 계산 */
export function boundaryPaths(geo) {
  if (!geo?.regions) return [];
  if (!pathCache.has(geo)) pathCache.set(geo, geo.regions.map(r => ({ name: r.name, full: r.full, d: ringsPath(r.rings) })));
  return pathCache.get(geo);
}

/**
 * 다른 지도(같은 위도 36도 등장방형, 축척·자리만 다름)의 좌표 함수 toXY(경도, 위도) → [x, y] 에
 * 이 모듈 좌표(project)를 맞추는 SVG matrix(a, 0, 0, d, e, f). 경계 경로를 다시 계산하지 않고 transform 으로 깐다.
 */
export function alignMatrix(toXY) {
  const [p1x, p1y] = project(126, 37);
  const [p2x, p2y] = project(129, 35);
  const [q1x, q1y] = toXY(126, 37);
  const [q2x, q2y] = toXY(129, 35);
  const a = (q2x - q1x) / (p2x - p1x);
  const d = (q2y - q1y) / (p2y - p1y);
  return [a, 0, 0, d, q1x - a * p1x, q1y - d * p1y];
}

/** 짝·홀 규칙 점-다각형 검사 (구멍 고리도 같이 넘기면 구멍 안은 false) */
export function pointInRings(lon, lat, rings) {
  let inside = false;
  for (const ring of rings) {
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const [xi, yi] = ring[i];
      const [xj, yj] = ring[j];
      if ((yi > lat) !== (yj > lat) && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) inside = !inside;
    }
  }
  return inside;
}

/** 도시 이름 → 시·도 짧은 이름 (끝의 '시'·'군'은 떼고도 찾는다). 모르면 null */
export function sidoOfCity(city) {
  const name = String(city || '').trim();
  if (!name) return null;
  return CITY_TO_SIDO[name] || CITY_TO_SIDO[name.replace(/(시|군)$/, '')] || null;
}

/** 공연장 → 시·도: 도시 이름이 먼저, 모르면 좌표로 */
export function sidoOfVenue(v, geo) {
  const byCity = sidoOfCity(v?.city);
  if (byCity) return byCity;
  if (!hasNum(v?.lat) || !hasNum(v?.lon)) return null;
  const hit = (geo?.regions || []).find(r => pointInRings(Number(v.lon), Number(v.lat), r.rings));
  return hit ? hit.name : null;
}

/** 기준 날짜가 든 달부터 뒤로 n달 합 */
export function sumRecentMonths(monthly, asOf, n = 12) {
  const [y, m] = String(asOf).split('-').map(Number);
  let s = 0;
  for (let i = 0; i < n; i += 1) {
    const ym = new Date(Date.UTC(y, m - 1 - i, 1)).toISOString().slice(0, 7);
    s += Number(monthly?.[ym]) || 0;
  }
  return s;
}

/** city_profiles.cities → 시·도별 { venues, nights(최근 12개월), teams(최근 1년), cities } + 시·도를 모르는 도시 */
export function aggregateBySido(cities, asOf) {
  const bySido = {};
  const unknown = [];
  for (const [name, c] of Object.entries(cities || {})) {
    const sido = sidoOfCity(name);
    if (!sido) {
      unknown.push(name);
      continue;
    }
    const cur = bySido[sido] || { venues: 0, nights: 0, teams: 0, cities: [] };
    bySido[sido] = {
      venues: cur.venues + (Number(c.venues_with_gigs) || 0),
      nights: cur.nights + sumRecentMonths(c.monthly, asOf, 12),
      teams: cur.teams + (Number(c.teams_1y) || 0),
      cities: [...cur.cities, name],
    };
  }
  return { bySido, unknown };
}

/** 색 단계 0(기록 없음)~5 — 로그 눈금(서울이 너무 커서 고른 눈금이면 지방이 다 옅어진다) */
export function colorLevel(v, max) {
  if (!(Number(v) > 0) || !(Number(max) > 0)) return 0;
  return Math.min(5, 1 + Math.floor((4 * Math.log1p(v)) / Math.log1p(max) + 1e-9));
}

/** 단계 L 이 시작하는 값(범례용) */
function levelFloor(level, max) {
  return level <= 1 ? 1 : Math.ceil(Math.expm1(((level - 1) * Math.log1p(max)) / 4) - 1e-6);
}

/** 경위도 범위 → 틀 비율(가로/세로)에 맞춘 viewBox [x, y, w, h] */
export function fitViewBox(bbox, aspect, pad = 0.08) {
  const [x0, y0] = project(bbox[0], bbox[3]);
  const [x1, y1] = project(bbox[2], bbox[1]);
  let w = Math.max((x1 - x0) * (1 + 2 * pad), MIN_VIEW_W);
  let h = (y1 - y0) * (1 + 2 * pad);
  if (w / h < aspect) w = h * aspect;
  else h = w / aspect;
  return [(x0 + x1) / 2 - w / 2, (y0 + y1) / 2 - h / 2, w, h];
}

/** 시·도 안에 있고 좌표가 있는 공연장('@계정'은 공연장이 아니라 뺀다) */
export function venuesInSido(venues, sido, geo) {
  return (venues || []).filter(v => !String(v.name || '').startsWith('@')
    && hasNum(v.lat) && hasNum(v.lon) && sidoOfVenue(v, geo) === sido);
}

function unionBbox(regions) {
  return regions.reduce((b, r) => [Math.min(b[0], r.bbox[0]), Math.min(b[1], r.bbox[1]),
    Math.max(b[2], r.bbox[2]), Math.max(b[3], r.bbox[3])], [180, 90, -180, -90]);
}

function nationViewBox(geo) {
  const b = unionBbox(geo.regions);
  const [x0, y0] = project(b[0], b[3]);
  const [x1, y1] = project(b[2], b[1]);
  const pad = 8;
  return [x0 - pad, y0 - pad, x1 - x0 + 2 * pad, y1 - y0 + 2 * pad];
}

/** 가장 큰 고리의 무게중심 [경도, 위도] */
function ringCentroid(ring) {
  let a = 0;
  let cx = 0;
  let cy = 0;
  for (let i = 0; i < ring.length - 1; i += 1) {
    const [x1, y1] = ring[i];
    const [x2, y2] = ring[i + 1];
    const f = x1 * y2 - x2 * y1;
    a += f;
    cx += (x1 + x2) * f;
    cy += (y1 + y2) * f;
  }
  return a ? [cx / (3 * a), cy / (3 * a)] : ring[0];
}

const ringArea = r => Math.abs(r.reduce((s, [x1, y1], i) => (i ? s + r[i - 1][0] * y1 - x1 * r[i - 1][1] : s), 0));
const biggestRing = region => [...region.rings].sort((p, q) => ringArea(q) - ringArea(p))[0];

function anchorOf(region) {
  return ringCentroid(biggestRing(region));
}

/** 확대할 범위 [서, 남, 동, 북] — 가장 큰 땅 + 그 시·도 공연장 점. 멀리 떨어진 작은 섬(울릉도·독도)까지 넣으면 본토가 너무 작아진다 */
export function zoomBbox(region, pts = []) {
  const ring = biggestRing(region);
  const xs = [...ring.map(([x]) => x), ...pts.map(p => Number(p.lon))];
  const ys = [...ring.map(([, y]) => y), ...pts.map(p => Number(p.lat))];
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
}

const metricValue = (bySido, sido, metric) => Number(bySido?.[sido]?.[metric]) || 0;
const maxOf = (bySido, metric) => Math.max(0, ...Object.values(bySido || {}).map(s => Number(s[metric]) || 0));

function regionAria(region, bySido, metric) {
  const v = metricValue(bySido, region.name, metric);
  return `${region.full} ${METRICS[metric].label} ${fmt(v)}${METRICS[metric].unit} — 눌러서 확대`;
}

function labelsHtml(geo, bySido, metric, vb) {
  const max = maxOf(bySido, metric);
  const pct = ([x, y]) => [((x - vb[0]) / vb[2]) * 100, ((y - vb[1]) / vb[3]) * 100];
  return geo.regions.map(r => {
    const at = LABEL_AT[r.name] || LABEL_POS[r.name] || anchorOf(r);
    const [lx, ly] = pct(project(...at));
    const v = metricValue(bySido, r.name, metric);
    const out = Boolean(LABEL_AT[r.name]);
    const dark = !out && colorLevel(v, max) >= 4;
    return `<button type="button" class="rm-label${out ? ' is-out' : ''}${dark ? ' on-dark' : ''}${v ? '' : ' is-zero'}" data-sido="${esc(r.name)}"
      style="left:${r1(lx)}%;top:${r1(ly)}%" tabindex="-1" aria-hidden="true"><span class="rm-label-name">${esc(r.name)}</span><span class="rm-label-num" data-num>${v ? fmt(v) : '—'}</span></button>`;
  }).join('');
}

const MARK_R = 2.6; // 독도 같은 아주 작은 섬 표시 점 반지름(단위)
const MARK_LABEL_DY = 2.4; // 점 아래 라벨 자리(%)

/** 너무 작아 면으로는 안 보이는 섬(독도) — 그 시·도 색 점 */
function marksSvg(geo, bySido, metric) {
  const max = maxOf(bySido, metric);
  return (geo.marks || []).map(m => {
    const [x, y] = project(m.lon, m.lat);
    return `<circle class="rm-mark lv-${colorLevel(metricValue(bySido, m.sido, metric), max)}" data-sido="${esc(m.sido)}" data-mark="${esc(m.name)}" cx="${r1(x)}" cy="${r1(y)}" r="${MARK_R}"/>`;
  }).join('');
}

function markLabelsHtml(geo, vb) {
  return (geo.marks || []).map(m => {
    const [x, y] = project(m.lon, m.lat);
    const left = ((x - vb[0]) / vb[2]) * 100;
    const top = ((y - vb[1]) / vb[3]) * 100 + MARK_LABEL_DY;
    return `<span class="rm-mark-label" style="left:${r1(left)}%;top:${r1(top)}%" aria-hidden="true">${esc(m.name)}</span>`;
  }).join('');
}

function leadersSvg(geo) {
  return geo.regions.filter(r => LABEL_AT[r.name]).map(r => {
    const [x1, y1] = project(...anchorOf(r));
    const [x2, y2] = project(...LABEL_AT[r.name]);
    return `<line class="rm-leader" x1="${r1(x1)}" y1="${r1(y1)}" x2="${r1(x2)}" y2="${r1(y2)}"/><circle class="rm-anchor" cx="${r1(x1)}" cy="${r1(y1)}" r="1.6"/>`;
  }).join('');
}

function legendHtml(bySido, metric) {
  const max = maxOf(bySido, metric);
  const item = (l, txt) => `<span class="rm-legend-item"><span class="rm-swatch lv-${l}"></span><span class="rm-legend-num">${txt}</span></span>`;
  const steps = [1, 2, 3, 4, 5].map(l => item(l, `${fmt(levelFloor(l, max))}${l === 5 ? '' : '~'}`));
  return `<span class="rm-legend-lbl">${esc(METRICS[metric].label)}</span>${item(0, '0')}${steps.join('')}`;
}

const ZOOM_LEGEND = '<span class="rm-legend-item"><span class="rm-legend-dot"></span>점 = 공연장(클수록 최근 12개월 공연 많음)</span>'
  + '<span class="rm-legend-item"><span class="rm-legend-heat"></span>번진 색 = 공연장이 몰린 곳</span>';

function metricButtons(metric) {
  return Object.entries(METRICS).map(([k, m]) => `<button type="button" class="rm-seg" data-map-metric="${k}" aria-pressed="${k === metric}" title="${esc(m.desc)}">${esc(m.label)}</button>`).join('');
}

/** 지도 HTML (처음 그리기 — 전국) */
export function regionMapHtml({ geo, bySido, metric = 'venues', uid = 'rm' }) {
  const vb = nationViewBox(geo);
  const max = maxOf(bySido, metric);
  const paths = geo.regions.map(r => `<path class="rm-region lv-${colorLevel(metricValue(bySido, r.name, metric), max)}" data-sido="${esc(r.name)}"
    role="button" tabindex="0" aria-label="${esc(regionAria(r, bySido, metric))}" d="${ringsPath(r.rings)}"/>`).join('');
  return `<div class="rm" data-region-map>
    <div class="rm-bar">
      <div class="rm-segs" role="group" aria-label="색으로 볼 숫자">${metricButtons(metric)}</div>
      <button type="button" class="btn btn-sm rm-back" data-map-back hidden>← 전국으로</button>
    </div>
    <p class="rm-crumb small muted" data-map-crumb aria-live="polite">전국 · 시·도를 누르면 확대돼 공연장이 보입니다</p>
    <div class="rm-stage" data-map-stage style="max-width:calc(${MAX_STAGE_VH}vh * ${(vb[2] / vb[3]).toFixed(3)})">
      <svg class="rm-svg" viewBox="${vb.map(r1).join(' ')}" role="group" aria-label="시·도별 ${esc(METRICS[metric].label)} 지도">
        <defs><filter id="${uid}-blur" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur data-map-blur stdDeviation="4"/></filter></defs>
        <g class="rm-regions">${paths}</g>
        <g class="rm-leaders">${leadersSvg(geo)}</g>
        <g class="rm-marks" data-map-marks>${marksSvg(geo, bySido, metric)}</g>
        <g class="rm-heat" data-map-heat filter="url(#${uid}-blur)"></g>
        <g class="rm-dots" data-map-dots></g>
      </svg>
      <div class="rm-labels" data-map-labels>${labelsHtml(geo, bySido, metric, vb)}${markLabelsHtml(geo, vb)}</div>
      <div class="rm-tip" data-map-tip role="tooltip" hidden></div>
    </div>
    <div class="rm-legend small" data-map-legend>${legendHtml(bySido, metric)}</div>
    <div class="rm-venues" data-map-venues hidden></div>
    <p class="rm-source small muted">경계: Natural Earth(퍼블릭 도메인) · 공연장 점 = 좌표가 있는 곳만 · 점 크기 = 최근 12개월 공연 밤</p>
  </div>`;
}

/** 시·도 표 (지도 옆) — 고른 숫자 큰 순, 줄을 누르면 지도가 확대된다 */
export function sidoTableHtml({ geo, bySido, metric = 'venues' }) {
  const rows = geo.regions
    .map(r => ({ r, s: bySido[r.name] }))
    .sort((a, b) => metricValue(bySido, b.r.name, metric) - metricValue(bySido, a.r.name, metric)
      || a.r.name.localeCompare(b.r.name, 'ko'));
  const cell = (s, k) => (s?.[k] ? fmt(s[k]) : '<span class="muted">—</span>');
  return `<table class="rm-table">
    <caption class="small muted">시·도별 · ${esc(METRICS[metric].label)} 큰 순 · 줄을 누르면 지도에서 확대</caption>
    <thead><tr><th scope="col">시·도</th>${Object.entries(METRICS).map(([k, m]) => `<th scope="col" class="num${k === metric ? ' is-on' : ''}">${esc(m.label)}</th>`).join('')}</tr></thead>
    <tbody>${rows.map(({ r, s }) => `<tr>
      <th scope="row"><button type="button" class="rm-row-btn" data-sido-row="${esc(r.name)}">${esc(r.name)}</button>${s?.cities?.length && s.cities.join() !== r.name ? `<span class="small muted rm-row-cities">${esc(s.cities.join('·'))}</span>` : ''}</th>
      ${Object.keys(METRICS).map(k => `<td class="num mono${k === metric ? ' is-on' : ''}">${cell(s, k)}</td>`).join('')}</tr>`).join('')}</tbody>
  </table>`;
}

const prefersReduced = () => typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;
let mountSeq = 0;

function venueTipHtml(v) {
  const n = Number(v.nights12) || 0;
  return `<strong>${esc(v.name)}</strong><span>${esc(v.city || '도시 모름')}${v.tier ? ` · 체급 ${esc(v.tier)}` : ''}</span><span>최근 12개월 공연 ${fmt(n)}일</span><span class="muted">눌러서 공연장 페이지로</span>`;
}

function regionTipHtml(region, bySido) {
  const s = bySido[region.name];
  const lines = Object.entries(METRICS).map(([k, m]) => `<span>${esc(m.label)} <strong>${fmt(s?.[k] || 0)}</strong>${m.unit}</span>`);
  return `<strong>${esc(region.full)}</strong>${lines.join('')}${s?.cities?.length ? `<span class="muted">도시: ${esc(s.cities.join('·'))}</span>` : '<span class="muted">우리 공연 기록 없음</span>'}`;
}

/**
 * 지도를 붙이고 누르기·확대·말풍선을 단다.
 * @param {HTMLElement} host
 * @param {{ geo: object, bySido: object, venues: Array<object>, metric?: string, initial?: string|null,
 *   highlightCity?: string|null, onMetric?: (m: string) => void, onZoom?: (sido: string|null) => void }} opts
 *   venues: [{ name, city, lat, lon, tier, nights12 }]
 */
export function mountRegionMap(host, opts) {
  const { geo, bySido, venues = [], highlightCity = null, onMetric, onZoom } = opts;
  const uid = `rm${(mountSeq += 1)}`;
  const st = { metric: METRICS[opts.metric] ? opts.metric : 'venues', sido: null, raf: 0 };
  host.innerHTML = regionMapHtml({ geo, bySido, metric: st.metric, uid });
  const q = sel => host.querySelector(sel);
  const svg = q('.rm-svg');
  const stage = q('[data-map-stage]');
  const tip = q('[data-map-tip]');
  const nationVb = nationViewBox(geo);
  st.vb = nationVb;
  const aspect = nationVb[2] / nationVb[3];
  const byName = new Map(geo.regions.map(r => [r.name, r]));
  const venueByName = new Map(venues.map(v => [v.name, v]));

  const setVb = vb => {
    st.vb = vb;
    svg.setAttribute('viewBox', vb.map(n => n.toFixed(2)).join(' '));
  };
  const animateTo = (target, done) => {
    cancelAnimationFrame(st.raf);
    const from = st.vb;
    const dur = prefersReduced() ? 0 : ZOOM_MS;
    const t0 = performance.now();
    const step = now => {
      const k = dur ? Math.min(1, (now - t0) / dur) : 1;
      const e = 1 - (1 - k) ** 3;
      setVb(from.map((v, i) => v + (target[i] - v) * e));
      if (k < 1) st.raf = requestAnimationFrame(step);
      else if (done) done();
    };
    st.raf = requestAnimationFrame(step);
  };

  const drawVenues = (sido, targetVb) => {
    const upp = targetVb[2] / Math.max(200, svg.clientWidth || 600); // 화면 1px = 몇 단위
    const list = sido ? venuesInSido(venues, sido, geo) : [];
    const maxN = Math.max(1, ...list.map(v => Number(v.nights12) || 0));
    const sorted = [...list].sort((a, b) => (Number(a.nights12) || 0) - (Number(b.nights12) || 0));
    q('[data-map-blur]').setAttribute('stdDeviation', (BLUR_PX * upp).toFixed(3));
    q('[data-map-heat]').innerHTML = sorted.map(v => {
      const [x, y] = project(Number(v.lon), Number(v.lat));
      const w = Math.sqrt((Number(v.nights12) || 0) / maxN);
      return `<circle cx="${x.toFixed(2)}" cy="${y.toFixed(2)}" r="${(HEAT_PX * upp * (0.6 + 0.6 * w)).toFixed(3)}" fill-opacity="${(0.18 + 0.5 * w).toFixed(2)}"/>`;
    }).join('');
    q('[data-map-dots]').innerHTML = sorted.map(v => {
      const [x, y] = project(Number(v.lon), Number(v.lat));
      const w = Math.sqrt((Number(v.nights12) || 0) / maxN);
      const r = (DOT_PX[0] + (DOT_PX[1] - DOT_PX[0]) * w) * upp;
      const here = highlightCity && v.city === highlightCity ? ' is-here' : (highlightCity ? ' is-other' : '');
      return `<a href="#/venue/${encodeURIComponent(v.name)}" class="rm-dot-link" data-venue="${esc(v.name)}" aria-label="${esc(`${v.name} — 최근 12개월 공연 ${fmt(v.nights12)}일`)}"><circle class="rm-dot${here}" cx="${x.toFixed(2)}" cy="${y.toFixed(2)}" r="${r.toFixed(3)}"/></a>`;
    }).join('');
    return list;
  };

  const venueListHtml = (sido, list, total) => {
    const top = [...list].sort((a, b) => (Number(b.nights12) || 0) - (Number(a.nights12) || 0)).slice(0, TOP_VENUES);
    if (!top.length) return `<p class="small muted">${esc(sido)}에는 좌표가 있는 공연장이 아직 없습니다.</p>`;
    return `<p class="small muted rm-venues-head">${esc(sido)} 공연장 · 최근 12개월 공연 많은 순${total > list.length ? ` · 지도엔 좌표 있는 ${fmt(list.length)}곳(전체 ${fmt(total)}곳)` : ''}</p>
      <ol class="rm-venue-list">${top.map(v => `<li><a class="inline-venue-link" href="#/venue/${encodeURIComponent(v.name)}">${esc(v.name)}</a> <span class="small muted">${fmt(v.nights12)}일</span></li>`).join('')}</ol>`;
  };

  const regionTarget = region => fitViewBox(zoomBbox(region, venuesInSido(venues, region.name, geo)), aspect, 0.06);

  const zoomTo = sido => {
    const region = sido ? byName.get(sido) : null;
    st.sido = region ? region.name : null;
    const target = region ? regionTarget(region) : nationVb;
    svg.classList.toggle('is-zoomed', Boolean(region));
    host.querySelectorAll('.rm-region').forEach(p => p.classList.toggle('is-on', p.dataset.sido === st.sido));
    q('[data-map-labels]').hidden = Boolean(region);
    q('[data-map-back]').hidden = !region;
    const list = drawVenues(st.sido, target);
    const crumb = q('[data-map-crumb]');
    const box = q('[data-map-venues]');
    if (region) {
      const total = Number(bySido[region.name]?.venues) || list.length;
      crumb.textContent = `전국 › ${region.full} · 점 ${fmt(list.length)}곳 — 점을 누르면 공연장 페이지로`;
      box.innerHTML = venueListHtml(region.name, list, total);
      box.hidden = false;
      q('[data-map-legend]').innerHTML = ZOOM_LEGEND;
    } else {
      crumb.textContent = '전국 · 시·도를 누르면 확대돼 공연장이 보입니다';
      box.hidden = true;
      q('[data-map-legend]').innerHTML = legendHtml(bySido, st.metric);
    }
    animateTo(target);
    if (onZoom) onZoom(st.sido);
  };

  const setMetric = metric => {
    if (!METRICS[metric]) return;
    st.metric = metric;
    const max = maxOf(bySido, metric);
    host.querySelectorAll('.rm-region').forEach(p => {
      const r = byName.get(p.dataset.sido);
      p.setAttribute('class', `rm-region lv-${colorLevel(metricValue(bySido, r.name, metric), max)}${p.dataset.sido === st.sido ? ' is-on' : ''}`);
      p.setAttribute('aria-label', regionAria(r, bySido, metric));
    });
    q('[data-map-labels]').innerHTML = labelsHtml(geo, bySido, metric, nationVb) + markLabelsHtml(geo, nationVb);
    q('[data-map-marks]').innerHTML = marksSvg(geo, bySido, metric);
    q('[data-map-legend]').innerHTML = st.sido ? ZOOM_LEGEND : legendHtml(bySido, metric);
    host.querySelectorAll('[data-map-metric]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.mapMetric === metric)));
    if (onMetric) onMetric(metric);
  };

  const hideTip = () => { tip.hidden = true; };
  const showTip = (html, ev) => {
    tip.innerHTML = html;
    tip.hidden = false;
    const box = stage.getBoundingClientRect();
    const x = ev.clientX - box.left;
    const y = ev.clientY - box.top;
    const tw = tip.offsetWidth;
    tip.style.left = `${Math.max(4, Math.min(box.width - tw - 4, x + 12))}px`;
    tip.style.top = `${Math.max(4, y - tip.offsetHeight - 12)}px`;
  };

  host.addEventListener('click', e => {
    const m = e.target.closest('[data-map-metric]');
    if (m) { setMetric(m.dataset.mapMetric); return; }
    if (e.target.closest('[data-map-back]')) { zoomTo(null); return; }
    if (e.target.closest('[data-venue]')) return; // 링크가 알아서 공연장 페이지로
    const r = e.target.closest('[data-sido]');
    if (r && r.dataset.sido !== st.sido) { hideTip(); zoomTo(r.dataset.sido); }
  });
  host.addEventListener('keydown', e => {
    const r = e.target.closest('path[data-sido]');
    if (r && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); zoomTo(r.dataset.sido); }
    if (e.key === 'Escape' && st.sido) zoomTo(null);
  });
  stage.addEventListener('pointermove', e => {
    if (e.pointerType === 'touch') return;
    const dot = e.target.closest('[data-venue]');
    if (dot) { showTip(venueTipHtml(venueByName.get(dot.dataset.venue) || { name: dot.dataset.venue }), e); return; }
    const mark = e.target.closest('[data-mark]');
    if (mark && byName.get(mark.dataset.sido)) {
      showTip(`<strong>${esc(mark.dataset.mark)}</strong><span>${esc(byName.get(mark.dataset.sido).full)} 울릉군</span><span class="muted">눌러서 ${esc(mark.dataset.sido)} 확대</span>`, e);
      return;
    }
    const r = e.target.closest('[data-sido]');
    if (r && byName.get(r.dataset.sido)) { showTip(regionTipHtml(byName.get(r.dataset.sido), bySido), e); return; }
    hideTip();
  });
  stage.addEventListener('pointerleave', hideTip);

  if (opts.initial && byName.has(opts.initial)) {
    const target = regionTarget(byName.get(opts.initial));
    zoomTo(opts.initial);
    cancelAnimationFrame(st.raf);
    setVb(target); // 처음 열 때는 움직이지 않고 바로 확대된 모습
  }
  return { zoomTo, setMetric, get sido() { return st.sido; }, get metric() { return st.metric; } };
}
