/**
 * 홈 '차트 맛보기'(떠오르는 5 · 갓 데뷔 5) 한 줄 — 사진 · 이름·장르 · ▶ 바로 듣기 · 핵심 숫자 · ☆ 담기.
 * 다른 팀 목록과 같이 ▶를 둔다 (docs/ui_review_2026-11-28.md).
 */
import { avatarHtml, escapeHtml, playButtonHtml, watchButtonHtml } from './ui.js';

/**
 * @param {number} idx 0부터
 * @param {{ team_key: string, name: string, genre?: string, metric?: string }} row
 * @returns {string}
 */
export function homeChartRowHtml(idx, row) {
  const { team_key: key, name, genre = '', metric = '' } = row;
  return `
          <li class="home-chart-row">
            <span class="home-chart-rank mono">${idx + 1}</span>
            <a class="home-chart-team" href="#/team/${encodeURIComponent(key)}">
              ${avatarHtml(key, name, 28, { shape: 'circle', genre })}
              <span class="home-chart-team-text">
                <strong class="cell-truncate">${escapeHtml(name)}</strong>
                ${genre ? `<span class="small muted cell-truncate">${escapeHtml(genre)}</span>` : ''}
              </span>
            </a>
            <span class="home-chart-play">${playButtonHtml(key, name, { variant: 'icon' })}</span>
            <span class="home-chart-metric mono">${escapeHtml(metric || '—')}</span>
            <span class="home-chart-act">${watchButtonHtml(key, name, true, true)}</span>
          </li>
        `;
}
