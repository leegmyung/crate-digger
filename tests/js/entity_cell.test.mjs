// 표·목록 '이름 칸' 공통 마크업 (docs/layout_rules.md) — node --test
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { entityCellHtml } from '../../docs/app/components/entity_cell.js';

test('이름 칸: 사진 · 이름 줄 · 아래 줄 · 오른쪽 버튼 순서', () => {
  const html = entityCellHtml({ avatar: '<img class="avatar">', name: '<a>팀</a>', sub: '<span class="pill">예정 1일</span>', actions: '<button>▶</button>' });
  const order = ['class="avatar"', 'cell-entity-name', 'cell-entity-sub', 'cell-entity-actions'].map(s => html.indexOf(s));
  assert.ok(order.every(i => i >= 0), html);
  assert.deepEqual([...order].sort((a, b) => a - b), order);
  // 배지는 이름 줄이 아니라 아래 줄에 (이름 길이에 따라 배지 위치가 들쭉날쭉하지 않게)
  const nameLine = html.slice(html.indexOf('cell-entity-name'), html.indexOf('cell-entity-sub'));
  assert.ok(!nameLine.includes('예정'), nameLine);
});

test('아래 줄·버튼이 없으면 그 칸을 만들지 않음', () => {
  const html = entityCellHtml({ name: '팀' });
  assert.ok(html.includes('cell-entity-name'));
  assert.ok(!html.includes('cell-entity-sub'));
  assert.ok(!html.includes('cell-entity-actions'));
});

test('이름 줄에 title(말줄임 될 때 전체 이름)을 붙일 수 있음 — 따옴표는 이스케이프', () => {
  const html = entityCellHtml({ name: '팀', title: 'A "B" <C>' });
  assert.ok(html.includes('title="A &quot;B&quot; &lt;C&gt;"'), html);
});
