// 375 폭 한 바퀴 점검 (수동·선택 실행) — 화면마다: 가로 넘침 · 누르는 곳 44px 미만 · 잘린 글자(전체 글자 없음) ·
// 화면 아래 고정 띠(미니 플레이어·비교 담기)가 내용 끝을 가림 · 콘솔 오류. 판정 규칙은 m375_rules.mjs(테스트 있음).
//
//   node tests/e2e/m375_check.mjs --base http://127.0.0.1:8792/dashboard.html [--shots docs/ux/2026-11-28/m375] [--theme dark]
//   bash scripts/m375_check.sh  (서버 띄우기·끄기까지)
//
// 관계망·차트 그림 안(svg)은 다른 작업 몫이라 누르는 곳 검사에서 뺀다.
import { mkdirSync, mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { BOOT_LIMIT_MS, READY_EXPR, connectChrome, findChrome, removeProfile, sleep, waitUntil } from './cdp.mjs';
import { clippedTexts, coveredByFixed, smallTargets, spills } from './m375_rules.mjs';

const enc = encodeURIComponent;
const TEAM = enc('포져군단');
const TEAM_TABS = ['', '/score', '/events', '/gigs', '/network', '/videos', '/precedents'];
export const M375_ROUTES = [
  'home', 'discover', 'charts', 'charts/debut',
  'venues', 'venues/list', `venue/${enc('Club FF')}`, `venue/${enc('Club FF')}/teams`,
  'cities', `city/${enc('부산')}`, 'festivals', 'festival/burock_rookies',
  ...TEAM_TABS.map(t => `team/${TEAM}${t}`),
  'alerts', 'mine', 'mine?tab=venues', 'mine?tab=filters',
  `search?q=${enc('포')}`, `compare?teams=${TEAM},pcr`, 'help',
];
// 화면 아래 고정 띠(미니 플레이어 + 비교 담기)를 연 채로 다시 보는 화면
const BAR_ROUTES = ['home', 'discover', `team/${TEAM}`, `venue/${enc('Club FF')}`, 'charts'];
const OPEN_BARS_EXPR = `(async () => {
  const keys = [...new Set([...document.querySelectorAll('[data-compare-team]')].map(b => b.dataset.compareTeam))].slice(0, 2);
  for (const k of keys) document.querySelector('[data-compare-team="' + CSS.escape(k) + '"]:not(.is-on)')?.click();
  document.querySelector('button[data-play-name]')?.click();
  await new Promise(r => setTimeout(r, 900));
  window.scrollTo(0, document.documentElement.scrollHeight);
  return { tray: document.body.classList.contains('has-compare-tray'), player: document.body.classList.contains('has-mini-player') };
})()`;
const CLOSE_BARS_EXPR = `(() => { document.querySelector('[data-mp-close]')?.click();
  document.querySelectorAll('[data-compare-team].is-on').forEach(b => b.click()); try { localStorage.removeItem('gr_compare_v1'); } catch (_) {} })()`;
const WIDTH = 375;
const HEIGHT = 812;
const SETTLE_MS = 600;

function parseArgs(argv) {
  const opts = { base: '', chrome: '', shots: '', theme: 'dark', limitMs: 20000, only: '' };
  for (let i = 0; i < argv.length; i += 2) {
    const [k, v] = [argv[i], argv[i + 1]];
    if (k === '--base') opts.base = v;
    else if (k === '--chrome') opts.chrome = v;
    else if (k === '--shots') opts.shots = v;
    else if (k === '--theme') opts.theme = v;
    else if (k === '--limit-ms') opts.limitMs = Number(v);
    else if (k === '--only') opts.only = v;
    else throw new Error(`모르는 인자: ${k}`);
  }
  if (!opts.base) throw new Error('--base <앱 주소> 가 필요합니다');
  opts.chrome = findChrome(opts.chrome);
  return opts;
}

// 페이지 안에서 재기: 누르는 곳 · 잘린 글자 · 고정 띠 · 가로 넘침
const MEASURE_EXPR = `(() => {
  const de = document.documentElement; const vw = de.clientWidth; const vh = window.innerHeight;
  const sel = e => e.tagName.toLowerCase() + (e.classList.length ? '.' + [...e.classList].slice(0, 2).join('.') : '') + (e.id ? '#' + e.id : '');
  const shown = e => { if (!e.getClientRects().length) return false; const cs = getComputedStyle(e);
    if (cs.visibility === 'hidden' || Number(cs.opacity) === 0) return false;
    if (e.closest('[hidden], details:not([open]) > :not(summary), [aria-hidden="true"], svg, .graph-stage, .rg-stage, canvas')) return false;
    const r = e.getBoundingClientRect(); return r.right > 0 && r.left < vw && r.bottom + window.scrollY > 0; };   // 화면 위로 숨긴 것(건너뛰기 링크) 제외
  // 넓힌 누름 영역: ::after 가 absolute 면 그 크기(폭·높이 px)로 본다 · 라벨 안 체크칸은 라벨 크기
  const hit = e => { const a = getComputedStyle(e, '::after');
    if (e.tagName === 'INPUT' && e.closest('label')) { const lr = e.closest('label').getBoundingClientRect(); return { hitW: lr.width, hitH: lr.height }; }
    if (a.content === 'none' || a.position !== 'absolute') return { hitW: 0, hitH: 0 };
    return { hitW: parseFloat(a.width) || 0, hitH: parseFloat(a.height) || 0 }; };
  // 글자 링크(팀 이름·문장 속 링크)는 크기 규칙 예외 — 단추 모양 링크(.btn·칩·탭·아이콘)만 단추로 본다
  const BUTTONISH = /(^|[ -])(btn|chip|tab|seg|pill|plat|quick-link|more-link)([ -]|$)/;
  const textLink = e => e.tagName === 'A' && !BUTTONISH.test(e.className) && e.getAttribute('role') !== 'button' && e.getAttribute('role') !== 'tab';
  const targets = [...document.querySelectorAll('button, summary, select, a[href], input:not([type=hidden]), [role=tab]')]
    .filter(e => shown(e) && !/(^|\s)(rg|sn)-/.test(e.className) && !e.closest('[class*="rg-"], [class*="sn-"]'))   // 관계망 판(다른 작업 몫)
    .map(e => { const r = e.getBoundingClientRect(); const cs = getComputedStyle(e);
      const inline = textLink(e) || (e.tagName === 'A' && cs.display === 'inline' && !e.classList.contains('btn'));
      return { sel: sel(e), text: (e.getAttribute('aria-label') || e.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 24), w: r.width, h: r.height, inline, ...hit(e) }; });
  const clipped = [...document.querySelectorAll('#viewRoot *')].filter(e => {
    if (!shown(e) || !e.textContent.trim()) return false; const cs = getComputedStyle(e);
    const ell = cs.textOverflow === 'ellipsis' || cs.webkitLineClamp !== 'none' && cs.webkitLineClamp !== '';
    return ell && (e.scrollWidth > e.clientWidth + 1 || e.scrollHeight > e.clientHeight + 1);
  }).map(e => ({ sel: sel(e), text: e.textContent.trim().slice(0, 24), overflow: true,
    hasTitle: Boolean(e.closest('[title]')) }));
  // 겹침: 표 칸·카드 안 글자가 칸보다 넓은데 잘리지 않고(overflow visible) 옆으로 넘침 — 관계망·그림 안은 뺌
  const spill = [...document.querySelectorAll('#viewRoot th, #viewRoot td, #viewRoot [class*="kpi"], #viewRoot [class*="card"] > *')].filter(e => {
    if (!shown(e) || !e.textContent.trim() || e.closest('[class*="rg-"], [class*="sn-"]')) return false;
    const cs = getComputedStyle(e); return cs.overflowX === 'visible' && cs.display !== 'inline';
  }).map(e => { const r = e.getBoundingClientRect(); let lo = r.left; let hi = r.right;
    // 보이는 글자만 잰다: ::after 누름 영역은 원래 안 잡히고, 화면 읽기 전용(1px) 글자는 뺌
    const tw = document.createTreeWalker(e, NodeFilter.SHOW_TEXT);
    for (let n = tw.nextNode(); n; n = tw.nextNode()) {
      const pe = n.parentElement; if (!n.textContent.trim() || !pe || pe.getBoundingClientRect().width <= 1 || !shown(pe)) continue;
      const rg = document.createRange(); rg.selectNodeContents(n);
      for (const q of rg.getClientRects()) { lo = Math.min(lo, q.left); hi = Math.max(hi, q.right); }
    }
    return { sel: sel(e), text: e.textContent.trim().replace(/\s+/g, ' ').slice(0, 24), boxW: r.width, contentW: hi - lo }; });
  // 화면 아래쪽 고정 띠: 각 띠 윗변에서 화면 아래까지 = 가리는 높이 (비교 띠는 플레이어 위에 떠 있음). 잠깐 뜨는 알림(toast)은 뺌
  const fixedBottom = [...document.querySelectorAll('body *')].filter(e => {
    if (!shown(e) || e.closest('.app-toast, #appToast')) return false; const cs = getComputedStyle(e); if (cs.position !== 'fixed') return false;
    const r = e.getBoundingClientRect(); return r.height > 0 && r.top > vh * 0.4 && r.bottom <= vh + 1 && r.width >= 120;
  }).map(e => ({ sel: sel(e), h: vh - e.getBoundingClientRect().top }));
  const padOf = e => (e ? parseFloat(getComputedStyle(e).paddingBottom) || 0 : 0);
  const vr = document.getElementById('viewRoot');
  let contentPadBottom = 0; for (let p = vr; p && p !== de; p = p.parentElement) contentPadBottom += padOf(p);
  const clippedX = (e) => { for (let p = e.parentElement; p && p !== document.body; p = p.parentElement) {
    if (['auto', 'scroll', 'hidden', 'clip'].includes(getComputedStyle(p).overflowX)) return true; } return false; };
  const over = [...document.querySelectorAll('body *')].filter(e => { const r = e.getBoundingClientRect();
    return r.width > 0 && r.right > vw + 1 && !clippedX(e) && shown(e); }).slice(0, 3).map(sel);
  return { targets, clipped, spill, fixedBottom, contentPadBottom, scrollW: de.scrollWidth, clientW: vw, over, height: de.scrollHeight };
})()`;

function dedupe(list) {
  const m = new Map();
  for (const x of list) {
    const k = `${x.sel}|${x.why}`;
    if (!m.has(k)) m.set(k, { ...x, n: 0 });
    m.get(k).n += 1;
  }
  return [...m.values()];
}

async function checkRoute(cdp, route, opts) {
  cdp.takeErrors();
  await cdp.ev(`(() => { location.hash = '#/__m375_reset'; })()`);
  await sleep(150);
  await cdp.ev(`(() => { location.hash = '#/${route}'; window.scrollTo(0, 0); })()`);
  const ready = await waitUntil(cdp.ev, READY_EXPR, opts.limitMs);
  await sleep(SETTLE_MS);
  const m = await cdp.ev(MEASURE_EXPR);
  const errors = cdp.takeErrors();
  const issues = {
    overflow: m.scrollW > m.clientW || m.over.length ? [`${m.scrollW}>${m.clientW} ${m.over.join(' ')}`] : [],
    small: dedupe(smallTargets(m.targets)),
    clipped: dedupe(clippedTexts(m.clipped)),
    spill: dedupe(spills(m.spill)),
    covered: coveredByFixed(m),
    errors,
  };
  if (!ready) issues.errors.push('시간 초과');
  if (opts.shots) {
    // 화면 전체를 1배(가로 375px)로 — 저장소에 올릴 그림이 너무 크지 않게
    const shot = await cdp.send('Page.captureScreenshot', {
      format: 'jpeg', quality: 60, captureBeyondViewport: true, clip: { x: 0, y: 0, width: WIDTH, height: m.height, scale: 0.5 },
    });
    const name = decodeURIComponent(route).replace(/[?=/&,]+/g, '_').replace(/_+$/, '') || 'home';
    if (shot.result?.data) writeFileSync(join(opts.shots, `${name}.jpg`), Buffer.from(shot.result.data, 'base64'));
  }
  return { route: decodeURIComponent(route), height: m.height, ...issues };
}

function report(r, results) {
  results.push(r);
  const n = r.overflow.length + r.small.length + r.clipped.length + r.spill.length + r.covered.length + r.errors.length;
  console.log(`${n ? '✗' : '✓'} ${r.route.padEnd(30)} 세로 ${String(r.height).padStart(5)}px  넘침 ${r.overflow.length} · 작은 단추 ${r.small.length} · 잘림 ${r.clipped.length} · 겹침 ${r.spill.length} · 가림 ${r.covered.length} · 오류 ${r.errors.length}`);
  for (const x of r.overflow) console.log(`    넘침 ${x}`);
  for (const x of r.small) console.log(`    작음 ${x.why.padEnd(9)} ×${x.n} ${x.sel} "${x.text}"`);
  for (const x of r.clipped) console.log(`    잘림 ×${x.n} ${x.sel} "${x.text}"`);
  for (const x of r.spill) console.log(`    겹침 ${x.why} ×${x.n} ${x.sel} "${x.text}"`);
  for (const x of r.covered) console.log(`    가림 ${x.why} ${x.sel}`);
  for (const x of r.errors) console.log(`    오류 ${x}`);
}

async function run(opts) {
  const profileDir = mkdtempSync(join(tmpdir(), 'm375-check-'));
  if (opts.shots) mkdirSync(opts.shots, { recursive: true });
  const results = [];
  let cdp = null;
  try {
    cdp = await connectChrome(opts.chrome, 0, profileDir);
    await cdp.send('Emulation.setDeviceMetricsOverride', { width: WIDTH, height: HEIGHT, deviceScaleFactor: 2, mobile: true });
    await cdp.send('Emulation.setTouchEmulationEnabled', { enabled: true });
    await cdp.send('Page.navigate', { url: `${opts.base}#/home` });
    if (!await waitUntil(cdp.ev, READY_EXPR, BOOT_LIMIT_MS)) throw new Error('앱이 뜨지 않았습니다');
    await cdp.ev(`(() => { document.documentElement.dataset.theme = '${opts.theme}'; })()`);
    const routes = opts.only ? M375_ROUTES.filter(r => decodeURIComponent(r).includes(opts.only)) : M375_ROUTES;
    for (const route of routes) {
      const r = await checkRoute(cdp, route, opts);
      report(r, results);
    }
    for (const route of opts.only ? [] : BAR_ROUTES) {
      await checkRoute(cdp, route, { ...opts, shots: '' });
      const opened = await cdp.ev(OPEN_BARS_EXPR);
      await sleep(SETTLE_MS);
      const m = await cdp.ev(MEASURE_EXPR);
      const r = { route: `${decodeURIComponent(route)} (플레이어${opened.player ? '' : ' 못 엶'}·비교${opened.tray ? '' : ' 못 엶'} 열림)`, height: m.height,
        overflow: m.scrollW > m.clientW ? [`${m.scrollW}>${m.clientW}`] : [], small: [], clipped: [], spill: [], covered: coveredByFixed(m), errors: [] };
      if (!opened.player && !opened.tray) r.errors.push('고정 띠를 열지 못함');
      report(r, results);
      await cdp.ev(CLOSE_BARS_EXPR);
    }
  } finally {
    if (cdp) await cdp.close();
    removeProfile(profileDir);
  }
  return results;
}

async function main() {
  let opts;
  try {
    opts = parseArgs(process.argv.slice(2));
  } catch (e) {
    console.error(e.message);
    process.exit(1);
  }
  const results = await run(opts);
  const bad = results.filter(r => r.overflow.length + r.small.length + r.clipped.length + r.spill.length + r.covered.length + r.errors.length);
  console.log(`\n375 폭 ${results.length}화면 중 문제 있는 화면 ${bad.length}`);
  process.exit(bad.length ? 1 : 0);
}

main().catch((e) => {
  console.error(`점검 실패: ${e.message}`);
  process.exit(1);
});
