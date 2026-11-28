// 공연장 전후 흐름 그림 검사 — docs/app/components/venue_flow.js
// 왼쪽 = 이곳 전에 선 곳 → 가운데 = 이곳 → 오른쪽 = 이곳 뒤에 처음 선 곳. 색 = 이곳보다 큰/비슷한/작은 무대, 굵기 = 팀 수.
import test from 'node:test';
import assert from 'node:assert/strict';
import { buildVenueFlow, relTier, flowLayout } from '../../docs/app/components/venue_flow.js';

const tierOf = new Map([['A.O.R', 'S'], ['프리즘홀', 'M'], ['롤링홀', 'L'], ['예스24 라이브홀', 'XL'], ['Club 빵', 'S']]);

test('체급 비교: 이곳보다 큰 무대 up · 같은 same · 작은 down · 모르면 unknown', () => {
  assert.equal(relTier('L', 'M'), 'up');
  assert.equal(relTier('XL', 'S'), 'up');
  assert.equal(relTier('M', 'M'), 'same');
  assert.equal(relTier('S', 'M'), 'down');
  assert.equal(relTier('', 'M'), 'unknown');
  assert.equal(relTier('L', '?'), 'unknown');
});

test('표본이 작거나 앞뒤가 없으면 그림 대신 문장', () => {
  const small = buildVenueFlow({ venue: 'Club FF', tier: 'M', before: [['A.O.R', 3]], after: [], sample: 3, tierOf });
  assert.equal(small.kind, 'sentence');
  assert.match(small.html, /3팀뿐/);
  const none = buildVenueFlow({ venue: 'Club FF', tier: 'M', before: [], after: [], sample: 40, tierOf });
  assert.equal(none.kind, 'sentence');
});

test('그림: 넓은 판·좁은 판 두 장, 공연장마다 그 공연장 페이지 링크', () => {
  const r = buildVenueFlow({
    venue: 'Club FF', tier: 'M', sample: 120, tierOf,
    before: [['A.O.R', 133], ['Club 빵', 112]],
    after: [['롤링홀', 56], ['프리즘홀', 30], ['모르는곳', 9]],
  });
  assert.equal(r.kind, 'svg');
  assert.equal((r.html.match(/<svg /g) || []).length, 2);
  assert.match(r.html, /class="vf-svg vfl-svg is-wide"/);
  assert.match(r.html, /class="vfl-svg is-compact"/);
  assert.match(r.html, /href="#\/venue\/A\.O\.R"/);
  assert.match(r.html, /href="#\/venue\/%EB%A1%A4%EB%A7%81%ED%99%80"/);
  assert.match(r.html, /133팀/);
  // 색: 롤링홀(L) > 이곳(M) = up, 프리즘홀(M) = same, A.O.R(S) = down, 모르는곳 = unknown
  assert.match(r.html, /vfl-item is-up[^>]*data-vfl="롤링홀"/);
  assert.match(r.html, /vfl-item is-same[^>]*data-vfl="프리즘홀"/);
  assert.match(r.html, /vfl-item is-down[^>]*data-vfl="A\.O\.R"/);
  assert.match(r.html, /vfl-item is-unknown[^>]*data-vfl="모르는곳"/);
});

test('범례: 그림에 있는 색만, 굵기 설명 포함', () => {
  const r = buildVenueFlow({ venue: 'Club FF', tier: 'M', sample: 50, tierOf, before: [['A.O.R', 20]], after: [['롤링홀', 10]] });
  assert.match(r.html, /vfl-key is-up/);
  assert.match(r.html, /vfl-key is-down/);
  assert.doesNotMatch(r.html, /vfl-key is-same/);
  assert.match(r.html, /굵기 = 팀 수/);
});

test('표본 20팀 미만이면 앞뒤 3곳까지만', () => {
  const many = Array.from({ length: 8 }, (_, i) => [`곳${i}`, 20 - i]);
  const r = buildVenueFlow({ venue: 'X', tier: 'S', sample: 12, tierOf, before: many, after: [] });
  assert.equal((r.html.match(/data-vfl="곳/g) || []).length, 3 * 2, '두 판 × 3곳');
  const big = buildVenueFlow({ venue: 'X', tier: 'S', sample: 60, tierOf, before: many, after: [] });
  assert.equal((big.html.match(/data-vfl="곳/g) || []).length, 6 * 2);
});

test('배치: 굵기는 팀 수에 비례, 이름 칸은 서로 안 겹치고, 모두 그림 안에 든다', () => {
  const L = flowLayout({ before: [['a', 100], ['b', 50], ['c', 5]], after: [['d', 80]], width: 760 });
  const [a, b, c] = L.left;
  assert.ok(a.h > b.h && b.h > c.h);
  assert.ok(c.h >= 3, '아주 적어도 보이는 굵기');
  for (let i = 1; i < L.left.length; i++) {
    assert.ok(L.left[i].slotTop >= L.left[i - 1].slotTop + L.left[i - 1].slotH - 0.01, '이름 칸 겹침 없음');
  }
  const bottoms = [...L.left, ...L.right].map(n => n.slotTop + n.slotH);
  assert.ok(Math.max(...bottoms) <= L.height);
  assert.ok(L.center.h > 0 && L.center.y + L.center.h <= L.height);
});

test('이름의 HTML 은 글자로', () => {
  const r = buildVenueFlow({ venue: '<b>v</b>', tier: 'M', sample: 50, tierOf, before: [['<i>x</i>', 9]], after: [] });
  assert.doesNotMatch(r.html, /<b>v|<i>x/);
});
