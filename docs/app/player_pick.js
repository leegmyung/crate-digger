/**
 * 바로 듣기 — 팀마다 '무엇을 틀지' 고르는 순수 함수 (화면·appState 없이 돈다 → tests/js/player_pick.test.mjs).
 * 고르는 순서 (Chartmetric·스트리밍 서비스처럼 누르면 바로 소리):
 *   1) players.csv (team_key·kind(spotify|youtube)·id·title·source) — 다른 작업자가 만드는 '대표곡' 표
 *   2) 스포티파이 아티스트 (links.csv) — 인기곡 묶음 플레이어
 *   3) 무대 영상 (videos.csv) — 무대(stage) → 공식 라이브 → 공식 → 검색, 같은 종류면 최신 먼저
 */

const SPOTIFY_ID = /^[A-Za-z0-9]{22}$/;
const SPOTIFY_TYPES = new Set(['track', 'artist', 'album', 'playlist', 'episode']);
const YOUTUBE_ID = /^[A-Za-z0-9_-]{11}$/;
const VIDEO_KIND_ORDER = { stage: 0, official_live: 1, official: 2, search: 3 };
const DEFAULT_MAX_VIDEOS = 3;

/**
 * 스포티파이 주소(open.spotify.com/...)·URI(spotify:track:...)·'track:ID'·맨 id → { type, id }. type 을 모르면 null.
 * @param {string} raw
 * @returns {{ type: string|null, id: string }|null}
 */
export function parseSpotifyRef(raw) {
  const s = String(raw || '').trim();
  if (SPOTIFY_ID.test(s)) return { type: null, id: s };
  const url = s.match(/^https:\/\/open\.spotify\.com\/(?:intl-[a-z]{2}\/)?([a-z]+)\/([A-Za-z0-9]{22})(?:[/?#].*)?$/);
  const uri = s.match(/^(?:spotify:)?([a-z]+):([A-Za-z0-9]{22})$/);
  const m = url || uri;
  if (!m || !SPOTIFY_TYPES.has(m[1])) return null;
  return { type: m[1], id: m[2] };
}

/**
 * 유튜브 영상 주소(watch?v= · youtu.be · embed · shorts)·맨 id → 11자 id. 채널 주소 등은 null.
 * @param {string} raw
 * @returns {string|null}
 */
export function parseYoutubeRef(raw) {
  const s = String(raw || '').trim();
  if (YOUTUBE_ID.test(s)) return s;
  const m = s.match(/^https:\/\/(?:www\.|m\.)?(?:youtube\.com\/(?:watch\?(?:.*&)?v=|embed\/|shorts\/)|youtu\.be\/)([A-Za-z0-9_-]{11})(?:[&?#/].*)?$/);
  return m ? m[1] : null;
}

/**
 * players.csv 행들 → Map(team_key → [{ kind, type, id, title, source }]). 잘못된 행은 빼고, 같은 (kind,id)는 한 번만.
 * @param {Array<Record<string,string>>} rows
 */
export function parsePlayersRows(rows) {
  const out = new Map();
  for (const r of rows || []) {
    const teamKey = String(r?.team_key || '').trim();
    const kind = String(r?.kind || '').trim().toLowerCase();
    if (!teamKey) continue;
    let opt = null;
    if (kind === 'spotify') {
      const ref = parseSpotifyRef(r.id);
      if (ref) opt = { kind, type: ref.type, id: ref.id };
    } else if (kind === 'youtube') {
      const id = parseYoutubeRef(r.id);
      if (id) opt = { kind, type: 'video', id };
    }
    if (!opt) continue;
    const list = out.get(teamKey) || [];
    if (list.some(o => o.kind === opt.kind && o.id === opt.id)) continue;
    out.set(teamKey, [...list, { ...opt, title: String(r.title || '').trim(), source: String(r.source || '').trim() }]);
  }
  return out;
}

function videoRank(v) {
  return VIDEO_KIND_ORDER[v?.kind] ?? 9;
}

/**
 * 한 팀의 들을 거리 목록(앞이 먼저 틀 것).
 * @param {{ players?: object[], spotifyArtistId?: string|null, videos?: object[], maxVideos?: number }} p
 * @returns {Array<{ kind: 'spotify'|'youtube', type: string, id: string, title: string, source: string }>}
 */
export function playOptionsFor({ players = [], spotifyArtistId = null, videos = [], maxVideos = DEFAULT_MAX_VIDEOS } = {}) {
  const artistId = SPOTIFY_ID.test(String(spotifyArtistId || '')) ? spotifyArtistId : null;
  const fromPlayers = (players || []).map(o => (o.kind === 'spotify' && !o.type
    ? { ...o, type: o.id === artistId ? 'artist' : 'track' }
    : o));
  const seen = new Set(fromPlayers.map(o => `${o.kind}:${o.id}`));
  const fromArtist = artistId && !seen.has(`spotify:${artistId}`)
    ? [{ kind: 'spotify', type: 'artist', id: artistId, title: '인기곡', source: 'links' }]
    : [];
  const fromVideos = [...(videos || [])]
    .filter(v => YOUTUBE_ID.test(String(v?.video_id || '')) && !seen.has(`youtube:${v.video_id}`))
    .sort((a, b) => videoRank(a) - videoRank(b)
      || String(b.published_at || '').localeCompare(String(a.published_at || '')))
    .slice(0, Math.max(0, maxVideos))
    .map(v => ({ kind: 'youtube', type: 'video', id: v.video_id, title: String(v.title || '').trim(), source: 'videos' }));
  return [...fromPlayers, ...fromArtist, ...fromVideos];
}

/**
 * 삽입(iframe) 주소. 형식이 틀리면 null (주소에 이상한 값이 끼지 않게).
 * @param {{ kind: string, type?: string, id: string }} opt
 * @param {{ autoplay?: boolean }} [o]
 */
export function embedSrc(opt, { autoplay = false } = {}) {
  if (!opt) return null;
  if (opt.kind === 'spotify') {
    if (!SPOTIFY_ID.test(String(opt.id)) || !SPOTIFY_TYPES.has(opt.type)) return null;
    return `https://open.spotify.com/embed/${opt.type}/${opt.id}?utm_source=generator&theme=0`;
  }
  if (opt.kind === 'youtube') {
    if (!YOUTUBE_ID.test(String(opt.id))) return null;
    return `https://www.youtube-nocookie.com/embed/${opt.id}?rel=0&playsinline=1&modestbranding=1${autoplay ? '&autoplay=1' : ''}`;
  }
  return null;
}
