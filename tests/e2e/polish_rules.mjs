// 홈·팀 개요 마무리 다듬기 판정 규칙 — 페이지에서 잰 숫자를 받아 문제만 돌려준다 (순수 함수, tests/js/polish_rules.test.mjs).
// 재는 쪽은 tests/e2e/polish_check.mjs. 기준: docs/design_spec_from_chartmetric.md 2·3·8절.

export const MAX_HEADING_LEVELS = 3;                       // 화면 제목 · 블록 제목 · 칸 제목
export const SPACE_STEPS = [0, 4, 8, 12, 16, 24, 32, 40, 48]; // 간격 단계(4의 배수 중 정한 것만)

/** @param {{sel:string, size:number}[]} heads 제목 글자 크기(px) */
export function headingLevels(heads) {
  const bySize = new Map();
  for (const h of heads || []) {
    const s = Math.round(h.size * 10) / 10;
    if (!bySize.has(s)) bySize.set(s, []);
    bySize.get(s).push(h.sel);
  }
  const levels = [...bySize.keys()].sort((a, b) => b - a);
  if (levels.length <= MAX_HEADING_LEVELS) return { levels, problem: '' };
  // 가장 가까운 두 크기(거의 같아 위계가 흐려지는 쌍) 중 쓰인 곳이 적은 쪽을 튀는 것으로 알려 줌
  let pair = [levels[0], levels[1]];
  for (let i = 1; i < levels.length - 1; i++) {
    if (levels[i] - levels[i + 1] < pair[0] - pair[1]) pair = [levels[i], levels[i + 1]];
  }
  const odd = bySize.get(pair[1]).length < bySize.get(pair[0]).length ? pair[1] : pair[0];
  return { levels, problem: `제목 크기 ${levels.length}단계(${levels.join('·')}px) — ${odd}px: ${[...new Set(bySize.get(odd))].join(', ')}` };
}

/** @param {{sel:string, prop:string, px:number}[]} items */
export function offStepSpacing(items) {
  return (items || []).filter(x => !SPACE_STEPS.includes(x.px))
    .map(x => ({ sel: x.sel, prop: x.prop, why: `${x.prop} ${x.px}px` }));
}

/**
 * 가장 흔한 카드 모양(테두리·모서리·그림자)과 다른 카드.
 * @param {{sel:string, border:string, radius:string, shadow:string}[]} cards
 */
export function cardMismatch(cards) {
  const count = (key) => {
    const m = new Map();
    for (const c of cards || []) m.set(c[key], (m.get(c[key]) || 0) + 1);
    return [...m.entries()].sort((a, b) => b[1] - a[1])[0]?.[0];
  };
  const want = { border: count('border'), radius: count('radius'), shadow: count('shadow') };
  const out = [];
  for (const c of cards || []) {
    const why = [];
    if (c.border !== want.border) why.push(`테두리 ${c.border}`);
    if (c.radius !== want.radius) why.push(`모서리 ${c.radius}`);
    if (c.shadow !== want.shadow) why.push(`그림자 ${c.shadow}`);
    if (why.length) out.push({ sel: c.sel, why: why.join(' · ') });
  }
  return out;
}

/** 빈 칸 문구 종류 — 같은 뜻을 여러 말로 쓰면 variants 가 2개 이상 */
export function unevenEmptyTexts(texts) {
  const variants = [...new Set((texts || []).map(t => String(t).trim()).filter(Boolean))].sort();
  return { variants };
}

/** 화면의 큰 블록 사이 세로 간격 — 한 가지여야(±1px 반올림 허용) */
export function unevenBlockGaps(gaps) {
  const kinds = [];
  for (const g of gaps || []) {
    if (!kinds.some(k => Math.abs(k - g) <= 1)) kinds.push(g);
  }
  kinds.sort((a, b) => a - b);
  return { gaps: kinds, problem: kinds.length > 1 ? `블록 사이 간격 ${kinds.length}가지(${kinds.join('·')}px)` : '' };
}
