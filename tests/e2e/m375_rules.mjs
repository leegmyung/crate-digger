// 375 폭 점검 판정 규칙 — 페이지에서 잰 숫자를 받아 문제만 돌려준다 (순수 함수, tests/js/m375_rules.test.mjs).
// 재는 쪽은 tests/e2e/m375_check.mjs.

export const MIN_TAP = 44;   // 손가락으로 누르는 곳 최소 크기(px) — Apple HIG 44pt, WCAG 2.5.5

/**
 * @param {{sel:string, text:string, w:number, h:number, hitW?:number, hitH?:number, inline?:boolean}[]} targets
 * @returns {{sel:string, text:string, why:string}[]}
 */
export function smallTargets(targets) {
  const out = [];
  for (const t of targets || []) {
    if (t.inline) continue;                       // 문장 속 글자 링크는 예외
    const w = Math.max(t.w || 0, t.hitW || 0);
    const h = Math.max(t.h || 0, t.hitH || 0);
    if (w >= MIN_TAP && h >= MIN_TAP) continue;
    out.push({ sel: t.sel, text: t.text, why: `${Math.round(w)}×${Math.round(h)}px` });
  }
  return out;
}

/**
 * 화면 아래 고정 띠(미니 플레이어·비교 담기 등)가 내용 끝을 가리는지.
 * @param {{fixedBottom:{sel:string,h:number}[], contentPadBottom:number}} m
 */
export function coveredByFixed({ fixedBottom = [], contentPadBottom = 0 }) {
  const tallest = fixedBottom.reduce((a, b) => (b.h > (a?.h || 0) ? b : a), null);
  if (!tallest || tallest.h <= contentPadBottom) return [];
  return [{ sel: tallest.sel, why: `고정 띠 ${Math.round(tallest.h)}px > 내용 아래 여백 ${Math.round(contentPadBottom)}px` }];
}

/**
 * @param {{sel:string, text:string, overflow:boolean, hasTitle:boolean}[]} items
 */
export function clippedTexts(items) {
  return (items || []).filter(x => x.overflow && !x.hasTitle).map(x => ({ sel: x.sel, text: x.text, why: '잘렸는데 전체 글자(title) 없음' }));
}

const SPILL_TOLERANCE = 2;   // 반올림 오차

/**
 * 겹침: 상자(칸)보다 내용이 넓은데 잘리지 않아(overflow: visible) 옆 칸 위로 넘쳐 그려짐.
 * @param {{sel:string, text:string, boxW:number, contentW:number}[]} items
 */
export function spills(items) {
  return (items || []).filter(x => x.contentW - x.boxW >= SPILL_TOLERANCE)
    .map(x => ({ sel: x.sel, text: x.text, why: `칸보다 ${Math.round(x.contentW - x.boxW)}px 넘침` }));
}
