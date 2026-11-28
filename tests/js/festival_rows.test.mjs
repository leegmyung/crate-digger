// 페스티벌 회차표 한 줄 — 공식 라인업 수(해외 포함)와 종류 꼬리표 (node --test)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { editionRowHtml, festivalKindLabel } from '../../docs/app/views/festival_rows.js';

test('라인업 칸: 국내 팀 수 + 공식 전체 수(해외 포함)', () => {
  const html = editionRowHtml('2024', { lineup: 42, official_lineup: 58, later_winners: [] });
  assert.match(html, /42팀/);
  assert.match(html, /공식 58/);
});

test('공식 수가 없으면 국내 팀 수만', () => {
  const html = editionRowHtml('2021', { lineup: 7, later_winners: [] });
  assert.doesNotMatch(html, /공식/);
});

test('종류 꼬리표: 정답 표 · 라인업 표 · 신호', () => {
  assert.equal(festivalKindLabel('outcome'), '수상·선정 프로그램');
  assert.equal(festivalKindLabel('lineup'), '공식 라인업');
  assert.equal(festivalKindLabel('signal'), '신호(라인업)');
});
