/**
 * 팀 상세 '관계' 탭 맨 위 '비슷한 팀' — Chartmetric similar artists 처럼 유사도 % + 무엇이 겹치는지 꼬리표.
 * 계산: docs/lab/sql/similar_teams.sql (같은 무대 40 · 같은 출처 25 · 같은 장르 20 · 비슷한 체급 15, 정답 정보는 안 씀).
 */
import { appState } from '../state.js';
import { compareToggleHtml } from '../components/compare_tray.js';
import { INFO_TIPS, avatarHtml, escapeHtml, fmtInt, infoTip, playButtonHtml, renderNoRecordLine } from '../ui.js';

const SHOWN_FIRST = 8;

function sourceLabel(code) {
  return appState.programLabels?.get(code) || code;
}

function chipsHtml(r) {
  const chips = [];
  if (Number(r.shared_stages) > 0) {
    chips.push(`같은 무대 ${fmtInt(r.shared_stages)}번${r.last_shared ? ` (마지막 ${escapeHtml(String(r.last_shared).slice(0, 10))})` : ''}`);
  }
  if (Number(r.shared_sources) > 0) {
    const names = String(r.source_names || '').split(' · ').filter(Boolean).map(sourceLabel);
    chips.push(`같은 출처 ${escapeHtml(names.slice(0, 3).join(' · '))}${names.length > 3 ? ` 외 ${names.length - 3}` : ''}`);
  }
  if (r.same_genre) chips.push(`같은 장르 ${escapeHtml(r.primary_genre || '')}`);
  if (Number(r.part_level) >= 10) chips.push('비슷한 체급');
  return chips.map(c => `<span class="sim-chip">${c}</span>`).join('');
}

function rowHtml(r) {
  const name = r.display_name || r.related_team;
  const pct = Math.max(0, Math.min(100, Number(r.sim_pct) || 0));
  const parts = `같은 무대 ${r.part_stage} + 같은 출처 ${r.part_source} + 같은 장르 ${r.part_genre} + 비슷한 체급 ${r.part_level} = ${pct}%`;
  return `
    <li class="sim-row">
      <span class="team-cell-inline sim-team">
        ${avatarHtml(r.related_team, name, 28, { shape: 'circle', genre: r.primary_genre })}
        <a href="#/team/${encodeURIComponent(r.related_team)}"><strong>${escapeHtml(name)}</strong></a>
        ${r.profile_status === 'famous' ? '<span class="sim-famous" title="이미 유명한 팀으로 분류됨">유명</span>' : ''}
      </span>
      <span class="sim-score" title="${escapeHtml(parts)}">
        <span class="sim-bar" aria-hidden="true"><span style="width:${pct}%"></span></span>
        <strong>${pct}%</strong>
      </span>
      <span class="sim-chips">${chipsHtml(r)}</span>
      <span class="sim-actions">
        ${playButtonHtml(r.related_team, name, { variant: 'icon' })}
        ${compareToggleHtml(r.related_team, name, { variant: 'icon' })}
      </span>
    </li>`;
}

/**
 * @param {object[]|null} rows similar_teams.sql 결과 (null = 계산 중)
 * @param {boolean} showAll
 */
export function renderSimilarHtml(rows, showAll = false) {
  const head = `
    <div class="block-head">
      <h2>비슷한 팀${infoTip('비슷한 팀', INFO_TIPS.similar_teams, { compact: true })}</h2>
      <span class="small muted">둘러보기용 — 예측력 확인 안 됨 · 유사도 = 같은 무대 40 · 같은 출처 25 · 같은 장르 20 · 비슷한 체급 15 (수상 여부는 안 씀) — % 위에 마우스를 올리면 나눠 보기</span>
    </div>`;
  if (rows === null) return `${head}<p class="small muted">비슷한 팀 찾는 중…</p>`;
  if (!rows.length) return `${head}${renderNoRecordLine('같은 무대나 같은 출처로 이어진 팀이 아직 없습니다')}`;
  const shown = showAll ? rows : rows.slice(0, SHOWN_FIRST);
  const more = rows.length - shown.length;
  return `${head}
    <ol class="sim-list">${shown.map(rowHtml).join('')}</ol>
    ${more > 0 ? `<div class="more-row"><button type="button" class="btn btn-sm" data-sim-more="1">${fmtInt(more)}팀 더 보기</button></div>` : ''}`;
}
