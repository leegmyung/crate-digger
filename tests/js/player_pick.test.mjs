// 바로 듣기: players.csv·스포티파이 링크·무대 영상에서 들을 거리를 고르는 순수 함수 검사 (node --test)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  audioSrc, embedSrc, parsePlayersRows, parseSpotifyRef, parseYoutubeRef, playOptionsFor,
} from '../../docs/app/player_pick.js';

const ART = '4Z8W4fKeB5YxbusRsdQVPb';   // 22자
const TRK = '3n3Ppam7vgaVa1iaRUc9Lp';
const VID = 'dQw4w9WgXcQ';               // 11자

test('스포티파이 주소·URI·맨 id를 읽는다', () => {
  assert.deepEqual(parseSpotifyRef(`https://open.spotify.com/track/${TRK}?si=x`), { type: 'track', id: TRK });
  assert.deepEqual(parseSpotifyRef(`spotify:album:${TRK}`), { type: 'album', id: TRK });
  assert.deepEqual(parseSpotifyRef(`artist:${ART}`), { type: 'artist', id: ART });
  assert.deepEqual(parseSpotifyRef(TRK), { type: null, id: TRK });
  assert.equal(parseSpotifyRef('짧음'), null);
  assert.equal(parseSpotifyRef(`https://evil.example/track/${TRK}`), null);
});

test('유튜브 주소·맨 id를 읽는다', () => {
  assert.equal(parseYoutubeRef(VID), VID);
  assert.equal(parseYoutubeRef(`https://www.youtube.com/watch?v=${VID}&t=3`), VID);
  assert.equal(parseYoutubeRef(`https://youtu.be/${VID}`), VID);
  assert.equal(parseYoutubeRef('https://www.youtube.com/@channel'), null);
  assert.equal(parseYoutubeRef('bad id!'), null);
});

test('players.csv 행: 잘못된 행은 빼고 같은 것은 한 번만', () => {
  const m = parsePlayersRows([
    { team_key: 'a', kind: 'spotify', id: TRK, title: '노래', source: 'spotify_top' },
    { team_key: 'a', kind: 'spotify', id: TRK, title: '노래', source: 'dup' },
    { team_key: 'a', kind: 'youtube', id: VID, title: '무대', source: 'videos' },
    { team_key: 'a', kind: 'soundcloud', id: 'x', title: '', source: '' },
    { team_key: '', kind: 'youtube', id: VID },
    { team_key: 'b', kind: 'youtube', id: 'nope' },
  ]);
  assert.equal(m.size, 1);
  assert.deepEqual(m.get('a').map(o => [o.kind, o.id]), [['spotify', TRK], ['youtube', VID]]);
  assert.equal(m.get('a')[0].title, '노래');
});

test('고르는 순서: players → 스포티파이 아티스트 → 무대 영상(무대 먼저·최신 먼저)', () => {
  const players = parsePlayersRows([{ team_key: 'a', kind: 'youtube', id: VID, title: '대표곡' }]).get('a');
  const opts = playOptionsFor({
    players,
    spotifyArtistId: ART,
    videos: [
      { video_id: 'AAAAAAAAAAA', kind: 'search', published_at: '2026-10-01', title: '검색' },
      { video_id: 'BBBBBBBBBBB', kind: 'stage', published_at: '2025-01-01', title: '옛 무대' },
      { video_id: 'CCCCCCCCCCC', kind: 'stage', published_at: '2026-05-01', title: '새 무대' },
      { video_id: VID, kind: 'stage', published_at: '2026-06-01', title: '같은 영상' },
    ],
  });
  assert.deepEqual(opts.map(o => o.id), [VID, ART, 'CCCCCCCCCCC', 'BBBBBBBBBBB', 'AAAAAAAAAAA']);
  assert.equal(opts[1].type, 'artist');
});

test('맨 스포티파이 id: 팀 아티스트 id와 같으면 artist, 아니면 track', () => {
  const players = parsePlayersRows([
    { team_key: 'a', kind: 'spotify', id: ART },
    { team_key: 'a', kind: 'spotify', id: TRK },
  ]).get('a');
  const opts = playOptionsFor({ players, spotifyArtistId: ART, videos: [] });
  assert.deepEqual(opts.map(o => [o.type, o.id]), [['artist', ART], ['track', TRK]]);
});

test('들을 거리가 없으면 빈 배열, 영상은 최대 개수까지만', () => {
  assert.deepEqual(playOptionsFor({}), []);
  const videos = Array.from({ length: 9 }, (_, i) => ({ video_id: `VVVVVVVVVV${i}`, kind: 'stage', published_at: `2026-0${i + 1}-01` }));
  assert.equal(playOptionsFor({ videos, maxVideos: 3 }).length, 3);
});

test('삽입 주소: 스포티파이 embed·유튜브 nocookie, 그 밖은 null', () => {
  assert.equal(embedSrc({ kind: 'spotify', type: 'track', id: TRK }),
    `https://open.spotify.com/embed/track/${TRK}?utm_source=generator&theme=0`);
  assert.match(embedSrc({ kind: 'youtube', id: VID }, { autoplay: true }),
    new RegExp(`^https://www\\.youtube-nocookie\\.com/embed/${VID}\\?.*autoplay=1`));
  assert.equal(embedSrc({ kind: 'spotify', type: 'track', id: 'x' }), null);
  assert.equal(embedSrc({ kind: 'other', id: VID }), null);
});

const PREVIEW = 'https://audio-ssl.itunes.apple.com/itunes-assets/AudioPreview/x/a.m4a';
const PAGE = 'https://music.apple.com/us/album/x/1?i=7';

test('iTunes 미리듣기 행: https 애플 오디오 주소만, 원래 페이지 링크 같이', () => {
  const m = parsePlayersRows([
    { team_key: 'a', kind: 'itunes', id: PREVIEW, title: '곡', source: 'itunes', page_url: PAGE },
    { team_key: 'b', kind: 'itunes', id: 'http://audio-ssl.itunes.apple.com/a.m4a' },
    { team_key: 'c', kind: 'itunes', id: 'https://evil.example/a.m4a' },
    { team_key: 'd', kind: 'itunes', id: PREVIEW, page_url: 'javascript:alert(1)' },
  ]);
  assert.deepEqual([...m.keys()], ['a', 'd']);
  assert.deepEqual(m.get('a')[0], { kind: 'itunes', type: 'preview', id: PREVIEW, title: '곡', source: 'itunes', pageUrl: PAGE });
  assert.equal(m.get('d')[0].pageUrl, '');
});

test('오디오 주소: iTunes 만 audioSrc, iframe 주소는 없음', () => {
  const opt = { kind: 'itunes', type: 'preview', id: PREVIEW };
  assert.equal(audioSrc(opt), PREVIEW);
  assert.equal(embedSrc(opt), null);
  assert.equal(audioSrc({ kind: 'itunes', id: 'https://evil.example/a.m4a' }), null);
  assert.equal(audioSrc({ kind: 'youtube', id: VID }), null);
});
