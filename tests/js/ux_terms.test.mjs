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

// ---------- 3차: 데이터에서 오는 글자(알림 종류·알림 문장)도 쉬운 말로 (docs/app/easy_terms.js) ----------
import { easyText, easyAlertTypeLabel } from '../../docs/app/easy_terms.js';

test('알림 문장: 옛 단계 이름·백지·정답 → 쉬운 말 (자료 파일은 매일 새로 만들어져 앱에서 바꿈)', () => {
  assert.equal(easyText('여러 갈래 → 선정·중간 정답'), '여러 곳에서 보임 → 선정·수상 후보');
  assert.equal(easyText('첫 신호 → 여러 갈래'), '첫 신호 → 여러 곳에서 보임');
  assert.equal(easyText('백지 신인 첫 언급 — 공연: 클럽FF'), '언급 전 신인 첫 언급 — 공연: 클럽FF');
  assert.equal(easyText('백지 → 첫 신호'), '언급 전 → 첫 신호');
  assert.equal(easyText('헬로루키 정답'), '헬로루키 수상·선정');
  assert.equal(easyText('2개 갈래에서 언급'), '신호 2종류에서 언급');
  assert.equal(easyText('PCR · 클럽'), 'PCR · 클럽');
  assert.equal(easyText(''), '');
  assert.equal(easyText(null), '');
});

test('알림 종류 이름: 앱의 쉬운 이름이 자료 파일 이름보다 먼저', () => {
  assert.equal(easyAlertTypeLabel('new_outcome', { new_outcome: '새 정답' }), '새 수상·선정');
  assert.equal(easyAlertTypeLabel('blank_first_mention', { blank_first_mention: '백지 신인 첫 언급' }), '언급 전 신인 첫 언급');
  assert.equal(easyAlertTypeLabel('spike', { spike: '언급 급증' }), '언급 급증');
  assert.equal(easyAlertTypeLabel('odd', {}), 'odd');
});
