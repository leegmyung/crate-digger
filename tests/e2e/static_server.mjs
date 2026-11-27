// 점검용 작은 정적 서버 — node tests/e2e/static_server.mjs <폴더> <포트>
// python http.server 는 동시 요청이 몰리면 연결을 끊는 일이 있어 점검에는 이걸 쓴다.
import http from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join, normalize, resolve } from 'node:path';

const [rootArg, portArg = '8792'] = process.argv.slice(2);
if (!rootArg) {
  console.error('사용법: node tests/e2e/static_server.mjs <폴더> <포트>');
  process.exit(2);
}
const ROOT = resolve(rootArg);
const TYPES = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8', '.json': 'application/json', '.csv': 'text/csv; charset=utf-8',
  '.sql': 'text/plain; charset=utf-8', '.md': 'text/plain; charset=utf-8', '.svg': 'image/svg+xml',
  '.png': 'image/png', '.jpg': 'image/jpeg', '.webp': 'image/webp', '.wasm': 'application/wasm',
};

http.createServer(async (req, res) => {
  try {
    const pathname = decodeURIComponent(new URL(req.url, 'http://local').pathname);
    const file = join(ROOT, normalize(pathname.endsWith('/') ? `${pathname}index.html` : pathname));
    if (!file.startsWith(ROOT)) {
      res.writeHead(403);
      res.end();
      return;
    }
    const body = await readFile(file);
    res.writeHead(200, { 'Content-Type': TYPES[extname(file)] || 'application/octet-stream', 'Cache-Control': 'no-store' });
    res.end(body);
  } catch (_) {
    res.writeHead(404);
    res.end('not found');
  }
}).listen(Number(portArg), '127.0.0.1', () => {
  console.log(`정적 서버: http://127.0.0.1:${portArg}/ (${rootArg})`);
});
