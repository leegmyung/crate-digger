// 홈·팀 개요 마무리 다듬기 판정 (tests/e2e/polish_rules.mjs) — 제목 위계 · 간격 단계 · 카드 모양 통일 · 빈 칸 문구 (node --test)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  MAX_HEADING_LEVELS, SPACE_STEPS, cardMismatch, headingLevels, offStepSpacing, unevenBlockGaps, unevenEmptyTexts,
} from '../e2e/polish_rules.mjs';

test('제목 크기는 3단계 이하 (화면 제목 · 블록 제목 · 칸 제목)', () => {
  assert.equal(MAX_HEADING_LEVELS, 3);
  assert.deepEqual(headingLevels([{ sel: 'h1', size: 24 }, { sel: 'h2', size: 17 }, { sel: 'h2.x', size: 17 }, { sel: 'h3', size: 15 }]),
    { levels: [24, 17, 15], problem: '' });
  const bad = headingLevels([{ sel: 'h1', size: 24 }, { sel: 'h2', size: 18 }, { sel: 'h2.b', size: 17 }, { sel: 'h3', size: 15 }]);
  assert.deepEqual(bad.levels, [24, 18, 17, 15]);
  assert.match(bad.problem, /4단계/);
  assert.match(bad.problem, /18px.*h2/);   // 어느 것이 튀는지 알려 줌
});

test('간격은 단계(4·8·12·16·24·32…)만 — 블록 사이·카드 안 여백', () => {
  assert.deepEqual(SPACE_STEPS, [0, 4, 8, 12, 16, 24, 32, 40, 48]);
  const out = offStepSpacing([
    { sel: '.block', prop: 'margin-bottom', px: 16 },
    { sel: '.team-head', prop: 'gap', px: 18 },
    { sel: '.ks-tile', prop: 'padding-top', px: 14 },
    { sel: '.x', prop: 'padding-left', px: 12.5 },   // 반올림 0.5 허용 안 함
  ]);
  assert.deepEqual(out.map(x => x.sel), ['.team-head', '.ks-tile', '.x']);
});

test('카드 모양 통일: 테두리·모서리·그림자가 가장 흔한 모양과 다르면 문제', () => {
  const cards = [
    { sel: '.block', border: '1px solid c', radius: '8px', shadow: 'none' },
    { sel: '.block', border: '1px solid c', radius: '8px', shadow: 'none' },
    { sel: '.ks-tile', border: '1px solid c', radius: '8px', shadow: 'none' },
    { sel: '.action-banner', border: '1px solid c', radius: '8px', shadow: '0 1px 2px x' },
    { sel: '.home-card', border: '1px solid c', radius: '12px', shadow: 'none' },
  ];
  const out = cardMismatch(cards);
  assert.deepEqual(out.map(x => x.sel), ['.action-banner', '.home-card']);
  assert.match(out[0].why, /그림자/);
  assert.match(out[1].why, /모서리 12px/);
});

test('빈 칸 문구: 같은 뜻(자료 없음)인데 말이 여러 가지면 알려 줌', () => {
  const out = unevenEmptyTexts(['자료 없음', '자료 없음', '기록이 없습니다.', '아직 기록 없음', '데이터 없음']);
  assert.deepEqual(out.variants, ['데이터 없음', '자료 없음', '기록이 없습니다.', '아직 기록 없음'].sort());
  assert.equal(unevenEmptyTexts(['자료 없음', '자료 없음']).variants.length, 1);
});

test('블록 사이 세로 간격은 한 가지 (16px 사이에 32px 하나가 끼면 문제, 1px 반올림은 봐줌)', () => {
  assert.deepEqual(unevenBlockGaps([16, 16, 32, 16]), { gaps: [16, 32], problem: '블록 사이 간격 2가지(16·32px)' });
  assert.deepEqual(unevenBlockGaps([16, 17, 16]).problem, '');
  assert.deepEqual(unevenBlockGaps([]).problem, '');
});
