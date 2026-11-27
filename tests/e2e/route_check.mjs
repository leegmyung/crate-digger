// 앱 화면 점검 (수동·선택 실행, 파이썬 unittest 와 별개)
// 메뉴 16곳 × 화이트·블랙 × 1280·1920·375px 마다: 콘솔 오류 0, 가로 넘침 0, 빈 화면 없음, 시간 제한 안에 그려짐.
// 앱을 한 번 띄운 뒤 주소(#/...)·테마·폭만 바꿔 가며 본다. 크롬은 헤드리스로 따로 띄운다(내 브라우저와 무관).
//
//   node tests/e2e/route_check.mjs --base http://127.0.0.1:8792/dashboard.html \
//     [--chrome <크롬 실행 파일>] [--debug-port 0] [--limit-ms 20000] [--out 결과.json]
//
// --debug-port 기본값 0 = 크롬이 비어 있는 포트를 스스로 고른다(여러 작업자가 동시에 돌려도 안 겹침).
//
// 크롬 경로는 --chrome, 없으면 환경변수 CHROME_PATH, 없으면 흔한 설치 위치를 차례로 찾는다.
// 하나라도 실패하면 종료 코드 1.
import { spawn } from 'node:child_process';
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const ROUTES = [
  'home', 'discover', 'charts', 'venues', 'cities', 'festivals', 'alerts', 'mine',
  'verify/backtest', 'verify/signals', 'verify/evidence', 'verify/scorecard', 'verify/grades', 'verify/quality', 'verify/sql',
  `team/${encodeURIComponent('포져군단')}`,
];
const WIDTHS = [1280, 1920, 375];
const THEMES = ['light', 'dark'];
const MOBILE_BELOW = 600;
const MIN_TEXT = 80;           // 본문 글자가 이보다 적으면 빈 화면으로 본다
const BOOT_LIMIT_MS = 60000;   // 첫 부팅(DuckDB 준비) 제한
const POLL_MS = 250;
const CHROME_EXIT_WAIT_MS = 5000;
const SETTLE_MS = 400;
const CHROME_CANDIDATES = [
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/Applications/Chromium.app/Contents/MacOS/Chromium',
  '/usr/bin/google-chrome', '/usr/bin/google-chrome-stable', '/usr/bin/chromium', '/usr/bin/chromium-browser',
];

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
  if (!opts.chrome) opts.chrome = CHROME_CANDIDATES.find(p => existsSync(p)) || '';
  if (!opts.chrome || !existsSync(opts.chrome)) throw new Error('크롬을 찾지 못했습니다 — --chrome 또는 CHROME_PATH 로 알려 주세요');
  if (!Number.isFinite(opts.debugPort) || !Number.isFinite(opts.limitMs)) throw new Error('--debug-port, --limit-ms 는 숫자여야 합니다');
  return opts;
}

const sleep = ms => new Promise(r => setTimeout(r, ms));

/** 크롬 DevTools 연결: send(명령), ev(페이지 안 식 계산), takeErrors(쌓인 오류 꺼내기) */
async function connectChrome(chromePath, port, profileDir) {
  const proc = spawn(chromePath, [
    '--headless=new', `--remote-debugging-port=${port}`, `--user-data-dir=${profileDir}`,
    '--no-first-run', '--no-default-browser-check', '--disable-gpu', 'about:blank',
  ], { stdio: 'ignore' });
  let wsUrl = '';
  let actualPort = port;
  for (let i = 0; i < 75 && !wsUrl; i++) {
    await sleep(200);
    try {
      if (!port) actualPort = Number(readFileSync(join(profileDir, 'DevToolsActivePort'), 'utf8').split('\n')[0]);
      const list = await (await fetch(`http://127.0.0.1:${actualPort}/json/list`)).json();
      wsUrl = list.find(t => t.type === 'page')?.webSocketDebuggerUrl || '';
    } catch (_) { /* 크롬이 아직 뜨는 중 */ }
  }
  if (!wsUrl) {
    proc.kill();
    throw new Error(`크롬 디버깅 포트 ${actualPort || '(자동)'} 에 연결하지 못했습니다`);
  }
  const ws = new WebSocket(wsUrl);
  await new Promise((ok, fail) => { ws.addEventListener('open', ok); ws.addEventListener('error', fail); });
  const pending = new Map();
  let seq = 0;
  let errors = [];
  ws.addEventListener('message', (msg) => {
    const m = JSON.parse(msg.data);
    if (m.id && pending.has(m.id)) {
      pending.get(m.id)(m);
      pending.delete(m.id);
      return;
    }
    const line = errorLine(m);
    if (line) errors.push(line);
  });
  const send = (method, params = {}) => new Promise((r) => {
    const id = ++seq;
    pending.set(id, r);
    ws.send(JSON.stringify({ id, method, params }));
  });
  const ev = async expr => (await send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true })).result?.result?.value;
  const takeErrors = () => { const out = errors; errors = []; return out; };
  const exited = new Promise(r => proc.once('exit', r));
  // 크롬이 완전히 꺼질 때까지 기다린다(꺼지는 중에 프로필 폴더를 지우면 ENOTEMPTY)
  const close = async () => {
    try { ws.close(); } catch (_) { /* 이미 닫힘 */ }
    proc.kill();
    await Promise.race([exited, sleep(CHROME_EXIT_WAIT_MS)]);
  };
  await send('Runtime.enable');
  await send('Log.enable');
  await send('Page.enable');
  return { send, ev, takeErrors, close };
}

function errorLine(m) {
  if (m.method === 'Runtime.exceptionThrown') {
    const d = m.params.exceptionDetails;
    return `예외 ${(d.exception?.description || d.text || '').slice(0, 200)}`;
  }
  if (m.method === 'Runtime.consoleAPICalled' && m.params.type === 'error') {
    return `console.error ${m.params.args.map(a => a.value ?? a.description ?? '').join(' ').slice(0, 200)}`;
  }
  if (m.method === 'Log.entryAdded' && m.params.entry.level === 'error') {
    return `로그 ${m.params.entry.text.slice(0, 120)} ${(m.params.entry.url || '').slice(0, 120)}`;
  }
  return '';
}

const READY_EXPR = `(() => {
  const r = document.getElementById('viewRoot'); const s = document.getElementById('topStatus');
  return Boolean(r && !r.dataset.skelPending && !r.querySelector('.skel, .skeleton, .view-skeleton')
    && !(s && s.classList.contains('busy')) && r.textContent.trim().length > ${MIN_TEXT});
})()`;

const MEASURE_EXPR = `(() => {
  const de = document.documentElement; const vr = document.getElementById('viewRoot');
  const clipped = (e) => { for (let p = e.parentElement; p && p !== document.body; p = p.parentElement) {
    if (['auto', 'scroll', 'hidden', 'clip'].includes(getComputedStyle(p).overflowX)) return true; } return false; };
  const over = [...document.querySelectorAll('body *')].filter(e => {
    const r = e.getBoundingClientRect(); return r.width > 0 && r.right > de.clientWidth + 1 && !clipped(e);
  }).slice(0, 3).map(e => e.tagName.toLowerCase() + '.' + String(e.className).slice(0, 40));
  return { scrollW: de.scrollWidth, clientW: de.clientWidth, over, textLen: vr ? vr.textContent.trim().length : 0 };
})()`;

async function waitUntil(ev, expr, limitMs) {
  const t0 = Date.now();
  while (Date.now() - t0 < limitMs) {
    await sleep(POLL_MS);
    if (await ev(expr)) return true;
  }
  return false;
}

async function checkOne(cdp, route, limitMs) {
  cdp.takeErrors();
  const t0 = Date.now();
  await cdp.ev(`(() => { location.hash = '#/__route_check_reset'; })()`);
  await sleep(150);
  await cdp.ev(`(() => { location.hash = '#/${route}'; })()`);
  const ready = await waitUntil(cdp.ev, READY_EXPR, limitMs);
  await sleep(SETTLE_MS);
  const ms = Date.now() - t0;
  const m = await cdp.ev(MEASURE_EXPR);
  const errors = cdp.takeErrors();
  const problems = [];
  if (!ready) problems.push(`시간 초과(${limitMs}ms)`);
  if (errors.length) problems.push(`콘솔 오류 ${errors.length}건`);
  if (m.scrollW > m.clientW || m.over.length) problems.push(`가로 넘침 ${m.scrollW}>${m.clientW} ${m.over.join(' ')}`.trim());
  if (m.textLen <= MIN_TEXT) problems.push(`빈 화면(글자 ${m.textLen})`);
  return { ms, ready, errors: errors.slice(0, 3), ...m, problems };
}

function removeProfile(dir) {
  try {
    rmSync(dir, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
  } catch (e) {
    console.warn(`임시 크롬 프로필을 지우지 못했습니다(점검 결과와 무관): ${e.message}`);
  }
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
          const r = { route: decodeURIComponent(route), width, theme, ...await checkOne(cdp, route, opts.limitMs) };
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
