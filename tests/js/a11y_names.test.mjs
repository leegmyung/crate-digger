// 접근성 이름 검사 (Lighthouse label-content-name-mismatch, 2026-11-28)
// 화면에 보이는 글자(예: 'YT')가 링크의 접근 이름(aria-label) 안에 있어야 음성 명령·화면 읽기가 맞는다.
import test from 'node:test';
import assert from 'node:assert/strict';
import { renderKeyStatsHtml } from '../../docs/app/views/team_head.js';

test('팀 머리 플랫폼 링크: aria-label 이 보이는 글자로 시작하고 팀 이름·플랫폼을 담는다', () => {
  const links = new Map([
    ['youtube', 'https://www.youtube.com/channel/abc'],
    ['instagram', 'https://www.instagram.com/abc/'],
  ]);
  const html = renderKeyStatsHtml({ scored: { score: 3 }, rc: null, videos: [], links, displayName: '포져군단' });
  const anchors = [...html.matchAll(/<a class="ks-plat[^"]*"[^>]*aria-label="([^"]*)"[^>]*>([^<]*)<\/a>/g)];
  assert.ok(anchors.length >= 2, '플랫폼 링크 2개');
  for (const [, label, visible] of anchors) {
    assert.ok(visible.trim(), '보이는 글자 있음');
    assert.ok(label.startsWith(visible.trim()), `"${label}" 이 "${visible}" 로 시작`);
    assert.match(label, /포져군단/);
  }
});
