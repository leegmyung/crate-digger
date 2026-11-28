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

import { catalogTableHtml } from '../../docs/app/views/festival_rows.js';

test('날짜·장소만 표: 페스티벌마다 한 줄, 회차 연도는 근거 글 링크, 라인업 페스티벌은 페이지로', () => {
  const html = catalogTableHtml([
    { name: '잔다리페스타', festival: null, editions: { 2024: { dates: ['2024-10-03', '2024-10-04'], venue: '홍대 일대', url: 'https://www.festivallife.kr/festival/?bmode=view&idx=2' } } },
    { name: '그랜드민트페스티벌', festival: 'gmf', editions: { 2022: { dates: ['2022-10-22'], venue: '올림픽공원', url: 'https://www.festivallife.kr/festival/?bmode=view&idx=1' } } },
  ]);
  assert.match(html, /잔다리페스타/);
  assert.match(html, /10\/03~10\/04/);
  assert.match(html, /홍대 일대/);
  assert.match(html, /href="https:\/\/www\.festivallife\.kr\/festival\/\?bmode=view&amp;idx=2"/);
  assert.match(html, /href="#\/festival\/gmf"/);
  assert.equal((html.match(/<tr>/g) || []).length, 3);   // 머리 1 + 2줄
});

test('목록이 비면 빈 글자', () => {
  assert.equal(catalogTableHtml([]), '');
});
