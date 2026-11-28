// 첫 진입에 받을 파일 고르기 — docs/app/boot_files.js · docs/app/venue_tiers.js venueMetaFromIndex
import test from 'node:test';
import assert from 'node:assert/strict';
import { signalsParquetOk } from '../../docs/app/boot_files.js';
import { venueMetaFromIndex } from '../../docs/app/venue_tiers.js';

test('signals Parquet: 행 수가 meta.rows.signals 와 같을 때만 읽는다', () => {
  assert.equal(signalsParquetOk({ rows: { signals: 62079 }, extras_rows: { 'signals.parquet': 62079 } }), true);
  assert.equal(signalsParquetOk({ rows: { signals: 62079 }, extras_rows: { 'signals.parquet': 61000 } }), false, '낡은 Parquet');
  assert.equal(signalsParquetOk({ rows: { signals: 62079 }, extras_rows: {} }), false, '목록에 없음');
  assert.equal(signalsParquetOk({ rows: { signals: 0 }, extras_rows: { 'signals.parquet': 0 } }), false, '빈 표');
  assert.equal(signalsParquetOk(null), false);
  assert.equal(signalsParquetOk({ extras_rows: { 'signals.parquet': 5 } }), false, 'rows 없음');
});

test('venue_index.json → 크기·도시 표 (팀 공연 탭)', () => {
  const m = venueMetaFromIndex({ as_of: 'x', venues: { 'Club FF': { city: '서울', tier: 'M' }, 부산홀: { city: '부산' }, 이상: { tier: 'Q' } } });
  assert.deepEqual([...m.tiers.entries()], [['Club FF', 'M']]);
  assert.deepEqual([...m.cities.entries()], [['Club FF', '서울'], ['부산홀', '부산']]);
  assert.equal(venueMetaFromIndex(null), null);
  assert.equal(venueMetaFromIndex({ venues: [] }), null);
});
