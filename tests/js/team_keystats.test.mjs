// 팀 머리 '핵심 숫자 4개 + 출처 아이콘' (Chartmetric 아티스트 머리처럼) — 순수 함수 검사 (node --test)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { keyStatTiles, platformLinks } from '../../docs/app/team_keystats.js';

test('점수 팀: 점수·공연·소개·영상 4칸, 순서 고정 (갈래는 아래 4칸 카드에 있어 겹치지 않게)', () => {
  const tiles = keyStatTiles({
    scored: { score: 3.456, gigs_1y: 12, venues: 7, n_branch: 3, outlets: 2, context_outlets: 1 },
    rank: 15, weekChange: 4,
    videos: [{ published_at: '2026-10-01' }, { published_at: '2026-11-02' }],
  });
  assert.deepEqual(tiles.map(t => t.key), ['score', 'gigs', 'press', 'videos']);
  assert.equal(tiles[0].value, '3.46');
  assert.equal(tiles[0].sub, '#15 · 지난주보다 ▲4');
  assert.equal(tiles[1].value, '12');
  assert.equal(tiles[1].sub, '공연장 7곳(2년)');
  assert.equal(tiles[2].value, '2');
  assert.equal(tiles[2].sub, '맥락 매체 1곳 더');
  assert.equal(tiles[3].value, '2');
  assert.equal(tiles[3].sub, '최근 2026-11-02');
  assert.ok(tiles.every(t => t.label && t.src));
});

test('점수 없는 팀·영상 없는 팀은 값 대신 빈칸 표시(null)', () => {
  const tiles = keyStatTiles({ scored: null, rank: null, videos: [] });
  assert.equal(tiles.length, 4);
  assert.equal(tiles[0].value, null);
  assert.equal(tiles[0].sub, '300위 밖');
  assert.equal(tiles[1].value, null);
  assert.equal(tiles[3].value, '0');
  assert.equal(tiles[3].sub, '연결된 영상 없음');
});

test('순위 내려가면 ▼, 그대로면 변화 표시 없음', () => {
  assert.equal(keyStatTiles({ scored: { score: 1 }, rank: 3, weekChange: -2 })[0].sub, '#3 · 지난주보다 ▼2');
  assert.equal(keyStatTiles({ scored: { score: 1 }, rank: 3, weekChange: 0 })[0].sub, '#3');
});

test('출처 아이콘: 아는 플랫폼만, 정해진 순서, https 주소만', () => {
  const links = new Map([
    ['melon', 'https://www.melon.com/artist/detail.htm?artistId=1'],
    ['spotify', 'https://open.spotify.com/artist/x'],
    ['instagram', 'javascript:alert(1)'],
    ['myspace', 'https://myspace.com/x'],
    ['youtube', 'https://www.youtube.com/@x'],
  ]);
  const out = platformLinks(links);
  assert.deepEqual(out.map(p => p.key), ['spotify', 'youtube', 'melon']);
  assert.equal(out[0].label, '스포티파이');
  assert.ok(out.every(p => p.abbr));
  assert.deepEqual(platformLinks(null), []);
});
