/**
 * 팀 상세 3-1 '머리 띠' 사실 줄 + '비교' 버튼 + 위쪽 고정 '쪽 안 목차'(누르면 이동, 스크롤하면 현재 칸 표시).
 * team.js 가 이미 커서 따로 둔다.
 */
import {
  escapeHtml, fmtInt, genreConfidenceBadgeHtml, infoTip, naCell, plainWhyLine,
} from '../ui.js';
import { keyStatTiles, platformLinks } from '../team_keystats.js';

/**
 * 머리 띠 사실 줄: 발굴 단계 · 순위(지난주 ▲▼) · 지역 · 첫 발매 연도 · 장르(추정 꼬리표)
 * @param {{ teamKey: string, stageInfo: object|null, rc: object|null, homeCity: string,
 *           hasCityData: boolean, firstRelease: string, genre: string }} f
 */
export function renderTeamFactsHtml(f) {
  // 발굴 단계·순위는 여기서 빼고 한 곳씩만: 단계 = 아래 상태 칸, 순위·점수 = 한 줄 이유와 숫자 칸 (docs/ux_simplify_2026-11-28.md ②)
  const items = [];
  const cityHtml = f.homeCity
    ? escapeHtml(f.homeCity)
    : naCell(f.hasCityData ? '이 팀의 공연 도시 기록이 없습니다' : '팀별 활동 지역 자료가 아직 없습니다');
  items.push(`<span class="team-fact"><span class="team-fact-lbl">지역</span>${cityHtml}</span>`);

  const yr = /^\d{4}/.test(String(f.firstRelease || '')) ? String(f.firstRelease).slice(0, 4) : '';
  items.push(`<span class="team-fact"><span class="team-fact-lbl">첫 발매</span>${yr ? `${escapeHtml(yr)}년` : naCell('첫 발매 기록이 없습니다')}</span>`);

  if (f.genre && f.genre !== '미분류') {
    items.push(`<span class="team-fact"><span class="team-fact-lbl">장르</span>${escapeHtml(f.genre)}${genreConfidenceBadgeHtml(f.teamKey)}</span>`);
  }
  return `<div class="team-facts" aria-label="팀 요약 정보">${items.join('')}</div>`;
}

/**
 * 팀 머리 맨 위 '왜 이 팀?' 한 줄 — 점수 근거 쉬운 말 + 후보 순위·점수 (docs/ux_simplify_2026-11-28.md ②).
 * @param {object|null} scored 후보 점수 줄 (lab_scored)
 * @param {number|null} rank 후보 순위
 * @returns {string}
 */
export function teamWhyHtml(scored, rank) {
  if (!scored) return '';
  const tail = [rank ? `후보 ${fmtInt(rank)}위` : '', Number.isFinite(Number(scored.score)) ? `${Number(scored.score).toFixed(2)}점` : '']
    .filter(Boolean).join(' · ');
  return `<p class="ux-team-why"><span aria-hidden="true">💡</span> ${escapeHtml(plainWhyLine(scored))}${tail ? ` <span class="ux-team-why-tail">— ${escapeHtml(tail)}</span>` : ''}</p>`;
}

/**
 * Chartmetric 아티스트 머리처럼 '핵심 숫자 4개 + 출처 아이콘' 줄.
 * @param {{ scored: object|null, rc: object|null, videos: object[], links: Map<string,string>|null, displayName: string }} p
 */
export function renderKeyStatsHtml({ scored, rc, videos, links, displayName }) {
  const tiles = keyStatTiles({ scored, rank: rc?.rank ?? null, weekChange: rc?.week_change ?? 0, videos });
  const plats = platformLinks(links);
  const tileHtml = tiles.map(t => `
    <div class="ks-tile" title="${escapeHtml(t.tip)}">
      <span class="ks-label"><span class="ks-src ks-src-${escapeHtml(t.key)}" aria-hidden="true">${escapeHtml(t.src)}</span>${escapeHtml(t.label)}${infoTip(t.label, { what: t.tip }, { compact: true })}</span>
      <strong class="ks-value">${t.value === null ? naCell(t.tip, { label: '—' }) : escapeHtml(t.value)}</strong>
      <span class="ks-sub">${escapeHtml(t.sub)}</span>
    </div>`).join('');
  const platHtml = plats.length
    ? `<div class="ks-plats" aria-label="연결된 플랫폼">
        ${plats.map(p => `<a class="ks-plat ks-plat-${escapeHtml(p.key)}" href="${escapeHtml(p.url)}" target="_blank" rel="noopener noreferrer" title="${escapeHtml(`${displayName} · ${p.label}`)}" aria-label="${escapeHtml(`${displayName} ${p.label}에서 열기`)}">${escapeHtml(p.abbr)}</a>`).join('')}
      </div>`
    : '<div class="ks-plats ks-plats-empty small muted">연결된 플랫폼 없음</div>';
  return `<div class="team-keystats" aria-label="핵심 숫자">${tileHtml}${platHtml}</div>`;
}

/**
 * 팀 머리 단추: 자주 쓰는 2개(듣기·담기)만 보이고 나머지(유튜브·비교·색 지도·인쇄)는 '⋯ 더보기' 안에
 * (docs/ux_simplify_2026-11-28.md ② 원리 6). 빈 항목은 뺀다. 더보기가 비면 메뉴를 만들지 않는다.
 * @param {{ primary: string[], more: string[] }} p
 */
export function teamHeadActionsHtml({ primary = [], more = [] }) {
  const front = primary.filter(Boolean).join('');
  const rest = more.filter(Boolean);
  if (!rest.length) return front;
  return `${front}<details class="ux-more"><summary class="btn" aria-label="더보기 — 유튜브·비교·인쇄">⋯ 더보기</summary><div class="ux-more-menu">${rest.join('')}</div></details>`;
}

/** '비교' = 같은 장르 후보들 사이에서 색 지도로 보기 (장르를 모르면 전체 후보) */
export function compareButtonHtml(genre) {
  const g = genre && genre !== '미분류' ? genre : '';
  const href = `#/discover?view=heat${g ? `&genre=${encodeURIComponent(g)}` : ''}`;
  const title = g ? `${g} 후보들과 색 지도로 비교` : '전체 후보와 색 지도로 비교';
  return `<a class="btn" href="${escapeHtml(href)}" title="${escapeHtml(title)}">색 지도</a>`;
}
