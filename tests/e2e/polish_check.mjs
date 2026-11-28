// 홈·팀 개요 마무리 점검 (수동·선택 실행) — 1280·1920·375 × 밝게·어둡게: 제목 크기 3단계 이하 · 간격 단계 ·
// 카드 테두리/모서리/그림자 통일 · 빈 칸 문구 종류 · 사진 없는 팀 머리(이니셜 원) 크기. 판정은 polish_rules.mjs(테스트 있음).
//
//   node tests/e2e/polish_check.mjs --base http://127.0.0.1:8792/dashboard.html [--shots docs/ux/2026-11-28/polish] [--prefix after]
import { mkdirSync, mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { BOOT_LIMIT_MS, READY_EXPR, connectChrome, findChrome, removeProfile, sleep, waitUntil } from './cdp.mjs';
import { cardMismatch, headingLevels, offStepSpacing, unevenBlockGaps, unevenEmptyTexts } from './polish_rules.mjs';

const enc = encodeURIComponent;
// 사진 있는 팀(포져군단) · 사진 없는 팀(머리글자 원)
export const POLISH_ROUTES = [
  { name: 'home', route: 'home', ready: '.ux-weekly-picks' },
  { name: 'team_photo', route: `team/${enc('포져군단')}`, ready: '.team-head' },
  { name: 'team_initial', route: 'team/pcr', ready: '.team-head' },
];
const WIDTHS = [1280, 1920, 375];
const THEMES = ['light', 'dark'];

function parseArgs(argv) {
  const opts = { base: '', chrome: '', shots: '', prefix: 'after' };
  for (let i = 0; i < argv.length; i += 2) {
    const [k, v] = [argv[i], argv[i + 1]];
    if (k === '--base') opts.base = v;
    else if (k === '--chrome') opts.chrome = v;
    else if (k === '--shots') opts.shots = v;
    else if (k === '--prefix') opts.prefix = v;
    else throw new Error(`모르는 인자: ${k}`);
  }
  if (!opts.base) throw new Error('--base <앱 주소> 가 필요합니다');
  opts.chrome = findChrome(opts.chrome);
  return opts;
}

// 카드 = 테두리·둥근 모서리가 있는 넓은 상자 (단추·입력칸·꼬리표·표 칸·그림 안은 제외)
const MEASURE_EXPR = `(() => {
  const vr = document.getElementById('viewRoot');
  const sel = e => e.tagName.toLowerCase() + (e.classList.length ? '.' + [...e.classList].slice(0, 2).join('.') : '');
  const shown = e => e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden' && !e.closest('[hidden], details:not([open]) > :not(summary)');
  const px = v => Math.round(parseFloat(v) * 10) / 10 || 0;
  const heads = [...vr.querySelectorAll('h1, h2, h3')].filter(shown).map(e => ({ sel: sel(e), size: px(getComputedStyle(e).fontSize) }));
  const isCard = e => { const cs = getComputedStyle(e); const r = e.getBoundingClientRect();
    return px(cs.borderTopWidth) > 0 && px(cs.borderTopLeftRadius) >= 6 && r.width >= 140 && r.height >= 40
      && !e.matches('button, a, input, select, textarea, summary, td, th, svg *, .btn, [class*="pill"], [class*="tag"], [class*="chip"], [class*="badge"], .avatar, .cd-infotip *, .team-peek, .mini-player *');
  };
  const cardEls = [...vr.querySelectorAll('*')].filter(e => shown(e) && isCard(e));
  const cards = cardEls.map(e => { const cs = getComputedStyle(e);
    return { sel: sel(e), border: cs.borderTopWidth + ' ' + cs.borderTopStyle + ' ' + cs.borderTopColor, radius: cs.borderTopLeftRadius, shadow: cs.boxShadow }; });
  const spacing = [];
  for (const e of cardEls) {
    const cs = getComputedStyle(e);
    spacing.push({ sel: sel(e), prop: 'padding-top', px: px(cs.paddingTop) }, { sel: sel(e), prop: 'padding-left', px: px(cs.paddingLeft) });
  }
  // 위아래·옆으로 이어진 카드 사이 간격(같은 부모 안 형제)
  for (const e of cardEls) {
    const n = e.nextElementSibling; if (!n || !shown(n) || !isCard(n)) continue;
    const a = e.getBoundingClientRect(); const b = n.getBoundingClientRect();
    if (b.top >= a.bottom - 1 && Math.abs(b.left - a.left) < 2) spacing.push({ sel: sel(e) + ' ↓ ' + sel(n), prop: '세로 간격', px: Math.round(b.top - a.bottom) });
    else if (Math.abs(b.top - a.top) < 2 && b.left >= a.right - 1) spacing.push({ sel: sel(e) + ' → ' + sel(n), prop: '가로 간격', px: Math.round(b.left - a.right) });
  }
  const empties = [...vr.querySelectorAll('.cd-na-cell, .na-cell, .no-record, .no-record-line, [class*="empty"] p, .muted.small')]
    .filter(e => shown(e) && /없|모름|N\\/A/.test(e.textContent) && e.textContent.trim().length <= 40).map(e => e.textContent.trim().replace(/\\s+/g, ' '));
  const av = vr.querySelector('.team-head .avatar, .team-avatar-col .avatar');
  const avatar = av ? { cls: String(av.className), w: Math.round(av.getBoundingClientRect().width), h: Math.round(av.getBoundingClientRect().height),
    font: px(getComputedStyle(av).fontSize), text: av.textContent.trim().slice(0, 3) } : null;
  // 화면의 큰 블록(홈 묶음 · 팀 머리 아래 블록) 사이 세로 간격 — 감싼 상자 안 마지막 카드 기준
  const top = vr.querySelector('#homePageRoot') || vr;
  const kids = [...top.children].filter(e => shown(e) && e.getBoundingClientRect().height > 8);
  const blockGaps = [];
  for (let i = 1; i < kids.length; i++) {
    const p = kids[i - 1]; const last = p.querySelector(':scope > .block:last-child') || p;
    const a = last.getBoundingClientRect(); const b = kids[i].getBoundingClientRect();
    if (b.top >= a.bottom - 1 && Math.abs(b.left - a.left) < 40) blockGaps.push(Math.round(b.top - a.bottom));
  }
  return { heads, cards, spacing, empties, avatar, blockGaps, height: document.documentElement.scrollHeight };
})()`;

async function run(opts) {
  const profile = mkdtempSync(join(tmpdir(), 'polish-check-'));
  if (opts.shots) mkdirSync(opts.shots, { recursive: true });
  const cdp = await connectChrome(opts.chrome, 0, profile);
  let problems = 0;
  try {
    await cdp.send('Emulation.setDeviceMetricsOverride', { width: 1280, height: 900, deviceScaleFactor: 1, mobile: false });
    await cdp.send('Page.navigate', { url: `${opts.base}#/home` });
    if (!await waitUntil(cdp.ev, READY_EXPR, BOOT_LIMIT_MS)) throw new Error('앱이 뜨지 않았습니다');
    for (const w of WIDTHS) {
      await cdp.send('Emulation.setDeviceMetricsOverride', { width: w, height: w < 600 ? 812 : 1000, deviceScaleFactor: 1, mobile: w < 600 });
      for (const theme of THEMES) {
        await cdp.ev(`(() => { document.documentElement.dataset.theme = '${theme}'; })()`);
        for (const r of POLISH_ROUTES) {
          await cdp.ev(`(() => { location.hash = '#/__polish'; })()`);
          await sleep(150);
          await cdp.ev(`(() => { location.hash = '#/${r.route}'; window.scrollTo(0, 0); })()`);
          await waitUntil(cdp.ev, READY_EXPR, 20000);
          await waitUntil(cdp.ev, `Boolean(document.querySelector('${r.ready}'))`, 30000);
          await sleep(700);
          const m = await cdp.ev(MEASURE_EXPR);
          const h = headingLevels(m.heads);
          const off = offStepSpacing(m.spacing);
          const cardBad = cardMismatch(m.cards);
          const empt = unevenEmptyTexts(m.empties);
          const gapsRes = r.name === 'home' ? unevenBlockGaps(m.blockGaps) : { gaps: [], problem: '' };
          const n = (h.problem ? 1 : 0) + off.length + cardBad.length + (empt.variants.length > 2 ? 1 : 0) + (gapsRes.problem ? 1 : 0);
          problems += n;
          console.log(`${n ? '✗' : '✓'} ${r.name.padEnd(13)} ${String(w).padStart(4)} ${theme.padEnd(5)} 제목 ${h.levels.join('·')}px · 간격 벗어남 ${off.length} · 카드 다름 ${cardBad.length} · 빈 칸 문구 ${empt.variants.length}종${m.avatar ? ` · 머리 사진 ${m.avatar.w}×${m.avatar.h}${m.avatar.text ? ` '${m.avatar.text}' ${m.avatar.font}px` : ''}` : ''}`);
          if (h.problem) console.log(`    제목 ${h.problem}`);
          if (gapsRes.problem) console.log(`    간격 ${gapsRes.problem}`);
          for (const x of off.slice(0, 8)) console.log(`    간격 ${x.why} ${x.sel}`);
          for (const x of cardBad.slice(0, 6)) console.log(`    카드 ${x.why} ${x.sel}`);
          if (empt.variants.length > 2) console.log(`    빈 칸 문구 ${empt.variants.join(' / ')}`);
          if (opts.shots && w !== 1920) {
            const shot = await cdp.send('Page.captureScreenshot', { format: 'jpeg', quality: 60, captureBeyondViewport: true,
              clip: { x: 0, y: 0, width: w, height: Math.min(m.height, w < 600 ? 2400 : 1800), scale: 1 } });
            writeFileSync(join(opts.shots, `${opts.prefix}_${r.name}_${w}_${theme}.jpg`), Buffer.from(shot.result.data, 'base64'));
          }
        }
      }
    }
  } finally {
    await cdp.close();
    removeProfile(profile);
  }
  return problems;
}

async function main() {
  let opts;
  try {
    opts = parseArgs(process.argv.slice(2));
  } catch (e) {
    console.error(e.message);
    process.exit(1);
  }
  const n = await run(opts);
  console.log(`\n홈·팀 개요 다듬기 점검: 문제 ${n}건`);
  process.exit(n ? 1 : 0);
}

main().catch((e) => {
  console.error(`점검 실패: ${e.message}`);
  process.exit(1);
});
