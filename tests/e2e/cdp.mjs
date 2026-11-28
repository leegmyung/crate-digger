// 크롬 DevTools 연결 도우미 — route_check.mjs(메뉴 102칸 점검)와 m375_check.mjs(375 폭 점검)가 같이 쓴다.
import { spawn } from 'node:child_process';
import { existsSync, readFileSync, rmSync } from 'node:fs';
import { join } from 'node:path';

export const MIN_TEXT = 80;           // 본문 글자가 이보다 적으면 빈 화면으로 본다
export const BOOT_LIMIT_MS = 60000;   // 첫 부팅(DuckDB 준비) 제한
const POLL_MS = 250;
const CHROME_EXIT_WAIT_MS = 5000;
export const CHROME_CANDIDATES = [
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/Applications/Chromium.app/Contents/MacOS/Chromium',
  '/usr/bin/google-chrome', '/usr/bin/google-chrome-stable', '/usr/bin/chromium', '/usr/bin/chromium-browser',
];

/** 크롬 경로: 인자 → CHROME_PATH → 흔한 설치 위치 */
export function findChrome(given = '') {
  const p = given || process.env.CHROME_PATH || CHROME_CANDIDATES.find(c => existsSync(c)) || '';
  if (!p || !existsSync(p)) throw new Error('크롬을 찾지 못했습니다 — --chrome 또는 CHROME_PATH 로 알려 주세요');
  return p;
}

export const sleep = ms => new Promise(r => setTimeout(r, ms));

/** 크롬 DevTools 연결: send(명령), ev(페이지 안 식 계산), takeErrors(쌓인 오류 꺼내기) */
export async function connectChrome(chromePath, port, profileDir) {
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

export const READY_EXPR = `(() => {
  const r = document.getElementById('viewRoot'); const s = document.getElementById('topStatus');
  return Boolean(r && !r.dataset.skelPending && !r.querySelector('.skel, .skeleton, .view-skeleton')
    && !(s && s.classList.contains('busy')) && r.textContent.trim().length > ${MIN_TEXT});
})()`;

export async function waitUntil(ev, expr, limitMs) {
  const t0 = Date.now();
  while (Date.now() - t0 < limitMs) {
    await sleep(POLL_MS);
    if (await ev(expr)) return true;
  }
  return false;
}

export function removeProfile(dir) {
  try {
    rmSync(dir, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
  } catch (e) {
    console.warn(`임시 크롬 프로필을 지우지 못했습니다(점검 결과와 무관): ${e.message}`);
  }
}

