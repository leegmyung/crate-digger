// 375 폭 점검 규칙 (tests/e2e/m375_rules.mjs) — 누르는 곳 크기 · 고정 플레이어가 내용 가림 · 글자 잘림 판정 (node --test)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { MIN_TAP, clippedTexts, coveredByFixed, smallTargets, spills } from '../e2e/m375_rules.mjs';

const t = (over) => ({ sel: 'button.btn', text: '담기', w: 60, h: 44, hitW: 0, hitH: 0, inline: false, ...over });

test('누르는 곳: 가로·세로 둘 중 하나라도 44px 미만이면 문제 (넓힌 누름 영역 hit 이 있으면 그것으로)', () => {
  assert.equal(MIN_TAP, 44);
  const out = smallTargets([
    t({}),                                   // 통과
    t({ sel: 'button.cd-infotip-btn', w: 18, h: 18 }),            // 작음
    t({ sel: 'button.cd-infotip-btn', w: 18, h: 18, hitW: 44, hitH: 44 }), // ::after 로 넓힘 → 통과
    t({ sel: 'a.btn', w: 120, h: 32 }),      // 낮음
  ]);
  assert.deepEqual(out.map(x => x.sel), ['button.cd-infotip-btn', 'a.btn']);
  assert.match(out[1].why, /32px/);
});

test('누르는 곳: 문장 속 글자 링크(inline)는 크기 규칙에서 뺌 (WCAG 2.5.8 예외)', () => {
  assert.deepEqual(smallTargets([t({ sel: 'a', w: 40, h: 18, inline: true })]), []);
});

test('고정 플레이어: 화면 아래에 붙은 고정 띠 높이만큼 내용 끝에 여백이 없으면 가림', () => {
  assert.equal(coveredByFixed({ fixedBottom: [{ sel: '.mini-player', h: 72 }], contentPadBottom: 80 }).length, 0);
  const out = coveredByFixed({ fixedBottom: [{ sel: '.mini-player', h: 72 }], contentPadBottom: 16 });
  assert.equal(out.length, 1);
  assert.match(out[0].why, /72px/);
  assert.equal(coveredByFixed({ fixedBottom: [], contentPadBottom: 0 }).length, 0);
});

test('글자 잘림: 넘쳐서 잘렸는데 전체 글자를 볼 길(title)이 없으면 문제', () => {
  const out = clippedTexts([
    { sel: 'span.name', text: '아주 긴 팀 이름', overflow: true, hasTitle: true },
    { sel: 'span.why', text: '두 줄 넘는 이유', overflow: true, hasTitle: false },
    { sel: 'span.ok', text: '짧음', overflow: false, hasTitle: false },
  ]);
  assert.deepEqual(out.map(x => x.sel), ['span.why']);
});

test('겹침: 칸보다 글자가 넓은데 잘리지도 줄바꿈되지도 않아 옆 칸으로 넘치면 문제 (2px 미만 오차는 봐줌)', () => {
  const out = spills([
    { sel: 'th.cmp-label', text: '매거진·큐레이션 소개', boxW: 84, contentW: 150 },
    { sel: 'td', text: '7.20', boxW: 120, contentW: 121 },
    { sel: 'td.ok', text: '짧음', boxW: 120, contentW: 40 },
  ]);
  assert.deepEqual(out.map(x => x.sel), ['th.cmp-label']);
  assert.match(out[0].why, /66px/);
});
