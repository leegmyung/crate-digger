// 용어 다이어트 (docs/ux_simplify_2026-11-28.md ⑥) — 화면 글자만 쉬운 말로, 데이터 값(단계 번호·확신도 코드)은 그대로 (node --test)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { genreConfidenceBadgeHtml, STAGE_META } from '../../docs/app/ui.js';

test('발굴 단계 이름: 백지·여러 갈래·선정·중간 정답 → 쉬운 말', () => {
  assert.equal(STAGE_META[0].label, '언급 전');
  assert.equal(STAGE_META[1].label, '첫 신호');
  assert.equal(STAGE_META[2].label, '여러 곳에서 보임');
  assert.equal(STAGE_META[3].label, '선정·수상 후보');
  assert.equal(STAGE_META[4].label, '졸업');
  for (const k of [0, 1, 2, 3]) {
    assert.doesNotMatch(STAGE_META[k].next, /갈래|정답|DMZ/, `단계 ${k} 다음 단계 설명`);
  }
});

test('장르 확신도 꼬리표: 추정·추정·약함·리뷰 → "추정" 하나 (말풍선에서 근거 구분)', () => {
  for (const conf of ['inferred', 'inferred_low', 'review']) {
    const html = genreConfidenceBadgeHtml('x', conf);
    assert.match(html, />추정</, conf);
    assert.doesNotMatch(html, /추정·약함|>리뷰</, conf);
  }
});
