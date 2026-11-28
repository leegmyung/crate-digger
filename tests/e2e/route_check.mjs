// 앱 화면 점검 (수동·선택 실행, 파이썬 unittest 와 별개)
// 경로 20곳(tests/e2e/routes.mjs — 씬 네트워크·공연장 흐름 탭·도시 확대 지도 포함) × 화이트·블랙 × 1280·1920·375px 마다: 콘솔 오류 0, 가로 넘침 0, 빈 화면 없음, 시간 제한 안에 그려짐.
// 앱을 한 번 띄운 뒤 주소(#/...)·테마·폭만 바꿔 가며 본다. 크롬은 헤드리스로 따로 띄운다(내 브라우저와 무관).
//
//   node tests/e2e/route_check.mjs --base http://127.0.0.1:8792/dashboard.html \
//     [--chrome <크롬 실행 파일>] [--debug-port 0] [--limit-ms 20000] [--out 결과.json]
//
// --debug-port 기본값 0 = 크롬이 비어 있는 포트를 스스로 고른다(여러 작업자가 동시에 돌려도 안 겹침).
//
// 크롬 경로는 --chrome, 없으면 환경변수 CHROME_PATH, 없으면 흔한 설치 위치를 차례로 찾는다.
// 하나라도 실패하면 종료 코드 1.
import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import {
  BOOT_LIMIT_MS, MIN_TEXT, READY_EXPR, connectChrome, findChrome, removeProfile, sleep, waitUntil,
} from './cdp.mjs';

import { ROUTES, WIDTHS, THEMES, routeHash, routeLabel } from './routes.mjs';

const MOBILE_BELOW = 600;
const SETTLE_MS = 400;

function parseArgs(argv) {
  const opts = { base: '', chrome: process.env.CHROME_PATH || '', debugPort: 0, limitMs: 20000, out: '' };
  for (let i = 0; i < argv.length; i += 2) {
    const [k, v] = [argv[i], argv[i + 1]];
    if (k === '--base') opts.base = v;
    else if (k === '--chrome') opts.chrome = v;
    else if (k === '--debug-port') opts.debugPort = Number(v);
    else if (k === '--limit-ms') opts.limitMs = Number(v);
    else if (k === '--out') opts.out = v;
    else throw new Error(`모르는 인자: ${k}`);
  }
  if (!opts.base) throw new Error('--base <앱 주소> 가 필요합니다 (예: http://127.0.0.1:8792/dashboard.html)');
  opts.chrome = findChrome(opts.chrome);
  if (!Number.isFinite(opts.debugPort) || !Number.isFinite(opts.limitMs)) throw new Error('--debug-port, --limit-ms 는 숫자여야 합니다');
  return opts;
}

const MEASURE_EXPR = `(() => {
  const de = document.documentElement; const vr = document.getElementById('viewRoot');
  const clipped = (e) => { for (let p = e.parentElement; p && p !== document.body; p = p.parentElement) {
    if (['auto', 'scroll', 'hidden', 'clip'].includes(getComputedStyle(p).overflowX)) return true; } return false; };
  const over = [...document.querySelectorAll('body *')].filter(e => {
    const r = e.getBoundingClientRect(); return r.width > 0 && r.right > de.clientWidth + 1 && !clipped(e);
  }).slice(0, 3).map(e => e.tagName.toLowerCase() + '.' + String(e.className).slice(0, 40));
  return { scrollW: de.scrollWidth, clientW: de.clientWidth, over, textLen: vr ? vr.textContent.trim().length : 0 };
})()`;

async function checkOne(cdp, entry, limitMs) {
  cdp.takeErrors();
  const t0 = Date.now();
  await cdp.ev(`(() => { location.hash = '#/__route_check_reset'; })()`);
  await sleep(150);
  await cdp.ev(`(() => { location.hash = '#/${routeHash(entry)}'; })()`);
  const ready = await waitUntil(cdp.ev, READY_EXPR, limitMs);
  await sleep(SETTLE_MS);
  // 동작 경로(예: 지도 시·도 누르기): 화면이 뜬 뒤 실행하고, 그 결과 화면을 잰다
  const acted = typeof entry === 'object' && entry.act ? await cdp.ev(entry.act) : true;
  if (typeof entry === 'object' && entry.act) await sleep(SETTLE_MS * 2);
  const ms = Date.now() - t0;
  const m = await cdp.ev(MEASURE_EXPR);
  const errors = cdp.takeErrors();
  const problems = [];
  if (!ready) problems.push(`시간 초과(${limitMs}ms)`);
  if (!acted) problems.push('동작 대상 없음');
  if (errors.length) problems.push(`콘솔 오류 ${errors.length}건`);
  if (m.scrollW > m.clientW || m.over.length) problems.push(`가로 넘침 ${m.scrollW}>${m.clientW} ${m.over.join(' ')}`.trim());
  if (m.textLen <= MIN_TEXT) problems.push(`빈 화면(글자 ${m.textLen})`);
  return { ms, ready, errors: errors.slice(0, 3), ...m, problems };
}

async function run(opts) {
  const profileDir = mkdtempSync(join(tmpdir(), 'route-check-'));
  const results = [];
  let cdp = null;
  try {
    cdp = await connectChrome(opts.chrome, opts.debugPort, profileDir);
    await cdp.send('Emulation.setDeviceMetricsOverride', { width: 1280, height: 900, deviceScaleFactor: 1, mobile: false });
    await cdp.send('Page.navigate', { url: `${opts.base}#/home` });
    if (!await waitUntil(cdp.ev, READY_EXPR, BOOT_LIMIT_MS)) throw new Error(`앱이 ${BOOT_LIMIT_MS / 1000}초 안에 뜨지 않았습니다`);
    const bootErrors = cdp.takeErrors();
    if (bootErrors.length) results.push({ route: '(부팅)', width: 1280, theme: '-', ms: 0, errors: bootErrors, problems: [`부팅 중 콘솔 오류 ${bootErrors.length}건`] });
    for (const width of WIDTHS) {
      await cdp.send('Emulation.setDeviceMetricsOverride', { width, height: 900, deviceScaleFactor: 1, mobile: width < MOBILE_BELOW });
      for (const theme of THEMES) {
        await cdp.ev(`(() => { document.documentElement.dataset.theme = '${theme}'; })()`);
        for (const route of ROUTES) {
          const r = { route: routeLabel(route), width, theme, ...await checkOne(cdp, route, opts.limitMs) };
          results.push(r);
          console.log(`${r.problems.length ? '✗' : '✓'} ${r.route.padEnd(18)} ${String(width).padStart(4)} ${theme.padEnd(5)} ${String(r.ms).padStart(6)}ms ${r.problems.join(' · ')}`);
        }
      }
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
  if (opts.out) writeFileSync(opts.out, JSON.stringify(results, null, 1));
  const failed = results.filter(r => r.problems.length);
  const maxMs = Math.max(0, ...results.map(r => r.ms));
  console.log(`\n${results.length}칸 중 실패 ${failed.length} · 가장 느린 화면 ${maxMs}ms (제한 ${opts.limitMs}ms)`);
  failed.forEach(r => console.log(`  ✗ ${r.route} ${r.width} ${r.theme}: ${r.problems.join(' · ')} ${r.errors?.[0] || ''}`));
  process.exit(failed.length ? 1 : 0);
}

main().catch((e) => {
  console.error(`점검 실패: ${e.message}`);
  process.exit(1);
});
