/**
 * 팀 머리 '핵심 숫자 4개 + 출처 아이콘' — Chartmetric 아티스트 머리(지표 타일 + 연결 플랫폼 아이콘)를 우리 데이터로.
 * 순수 함수 (tests/js/team_keystats.test.mjs). 그리기는 views/team_head.js.
 *   점수(순위·지난주 변화) · 지난 1년 공연(최근 2년 공연장 수) · 매거진·큐레이션 소개 · 무대 영상
 *   (신호 갈래는 바로 아래 '상태' 4칸 카드에 있어 여기서는 겹치지 않게 뺌)
 */

/** 링크 칸 이름 → 아이콘 글자·이름 (상표 그림 대신 글자 동그라미) */
const PLATFORMS = [
  { key: 'spotify', label: '스포티파이', abbr: 'S' },
  { key: 'youtube', label: '유튜브', abbr: 'YT' },
  { key: 'instagram', label: '인스타그램', abbr: 'IG' },
  { key: 'melon', label: '멜론', abbr: 'M' },
  { key: 'bugs', label: '벅스', abbr: 'B' },
  { key: 'genie', label: '지니', abbr: 'G' },
];

function num(v) {
  const n = Number(v);
  return v === null || v === undefined || v === '' || !Number.isFinite(n) ? null : n;
}

function rankSub(rank, weekChange) {
  const r = num(rank);
  if (r === null) return '300위 밖';
  const ch = num(weekChange) || 0;
  const delta = ch > 0 ? ` · 지난주보다 ▲${ch}` : ch < 0 ? ` · 지난주보다 ▼${-ch}` : '';
  return `#${r}${delta}`;
}

function latestDate(videos) {
  return (videos || []).map(v => String(v?.published_at || '').slice(0, 10)).filter(Boolean).sort().pop() || '';
}

/**
 * @param {{ scored?: object|null, rank?: number|null, weekChange?: number, videos?: object[] }} p
 * @returns {Array<{ key: string, label: string, value: string|null, sub: string, src: string, tip: string }>}
 *   value 가 null 이면 '값 없음'(0점이 아님)으로 그린다.
 */
export function keyStatTiles({ scored = null, rank = null, weekChange = 0, videos = [] } = {}) {
  const score = num(scored?.score);
  const gigs = num(scored?.gigs_1y);
  const venues = num(scored?.venues);
  const outlets = num(scored?.outlets);
  const context = num(scored?.context_outlets);
  const vids = (videos || []).length;
  const last = latestDate(videos);
  return [
    {
      key: 'score', label: '발굴 점수', value: score === null ? null : score.toFixed(2),
      sub: rankSub(rank, weekChange), src: 'Gigle',
      tip: '공연·선정·매거진 신호를 합친 점수와 후보 순위 (검증 › 점수 신뢰도에서 정의)',
    },
    {
      key: 'gigs', label: '지난 1년 공연', value: gigs === null ? null : String(gigs),
      sub: venues === null ? '공연장 기록 없음' : `공연장 ${venues}곳(2년)`, src: '공연',
      tip: '공연 안내·예매처에서 모은 지난 1년 공연 수와 최근 2년 동안 선 공연장 수',
    },
    {
      key: 'press', label: '매거진·큐레이션 소개', value: outlets === null ? null : String(outlets),
      sub: context ? `맥락 매체 ${context}곳 더` : '발굴 매체 기준', src: '매체',
      tip: '발굴 역할 매거진·큐레이터가 이 팀을 소개한 곳 수 (맥락 매체는 점수 비중이 작아 따로 셈)',
    },
    {
      key: 'videos', label: '무대 영상', value: String(vids),
      sub: vids ? `최근 ${last}` : '연결된 영상 없음', src: 'YT',
      tip: '유튜브에서 찾은 무대·라이브 영상 수',
    },
  ];
}

/**
 * 연결된 플랫폼 아이콘 (정해진 순서, https 주소만).
 * @param {Map<string,string>|null} linksMap
 * @returns {Array<{ key: string, label: string, abbr: string, url: string }>}
 */
export function platformLinks(linksMap) {
  if (!linksMap || typeof linksMap.get !== 'function') return [];
  return PLATFORMS
    .map(p => ({ ...p, url: String(linksMap.get(p.key) || '') }))
    .filter(p => /^https:\/\//.test(p.url));
}
