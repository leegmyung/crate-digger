/**
 * 공연장·씬 '페스티벌' 탭 — festival_profiles.json 을 간단히:
 * 회차별 라인업 수 · 이 페스티벌 새 팀 비율 · 첫 페스티벌(신인) 비율 · 그 뒤 정답 팀 · 같은 집안 ⚠️ · 페스티벌 간 이동.
 */
import { loadFestivalProfiles } from '../db_venue.js';
import { escapeHtml, fmtInt, gradeBadgeHtml, naCell } from '../ui.js';

function pct(v) {
  return v === null || v === undefined ? '—' : `${Math.round(Number(v) * 100)}%`;
}

function editionRow(year, e) {
  const winners = Array.isArray(e.later_winners) ? e.later_winners : [];
  const names = winners.slice(0, 4).map(w => `<a href="#/team/${encodeURIComponent(w.team_key)}">${escapeHtml(w.name)}</a> ${gradeBadgeHtml(w.grade)}`).join(' · ');
  return `
    <tr>
      <td class="mono" data-label="회차">${escapeHtml(year)}${e.upcoming ? ' <span class="venue-upcoming-pill">예정</span>' : ''}</td>
      <td class="num" data-label="라인업">${fmtInt(e.lineup)}팀</td>
      <td class="num" data-label="새 팀">${pct(e.new_to_festival_share)}</td>
      <td class="num" data-label="첫 페스티벌">${pct(e.first_festival_share)}</td>
      <td data-label="그 뒤 정답">${e.upcoming ? naCell('아직 열리지 않은 회차라 세지 않습니다', { label: '—' }) : `<span><strong>${fmtInt(e.later_winners_total || 0)}팀</strong>${names ? ` <span class="small">${names}</span>` : ''}${winners.length > 4 ? ` <span class="small muted">외 ${fmtInt(winners.length - 4)}</span>` : ''}</span>`}</td>
    </tr>`;
}

function festivalCard(key, f) {
  const eds = Object.entries(f.editions || {}).sort((a, b) => b[0].localeCompare(a[0]));
  const sameHouse = f.same_house?.is_outcome || (f.same_house?.outcome_programs || []).length;
  return `
    <section class="block fest-card">
      <div class="block-head">
        <div>
          <h3>${escapeHtml(f.label || key)}</h3>
          <span class="block-meta">${f.kind === 'outcome' ? '정답 프로그램' : '신호(라인업)'} · 회차 ${fmtInt(eds.length)}개 · 누적 ${fmtInt(f.teams_total || 0)}팀</span>
        </div>
      </div>
      ${sameHouse ? `<p class="fest-same-house">⚠️ 같은 집안 — ${escapeHtml(f.same_house?.note || '정답 프로그램과 같은 행사라 그 정답은 \'그 뒤 정답\'에서 뺐습니다')}</p>` : ''}
      <div class="table-wrap">
        <table class="data-table stack-table fest-table">
          <thead><tr><th>회차</th><th class="num">라인업</th><th class="num" title="앞선 회차(우리 데이터)에 없던 팀 비율">새 팀</th><th class="num" title="우리 데이터의 첫 페스티벌 출연이 이 회차였던 팀 비율">첫 페스티벌</th><th>그 뒤 정답</th></tr></thead>
          <tbody>${eds.map(([y, e]) => editionRow(y, e)).join('')}</tbody>
        </table>
      </div>
    </section>`;
}

/** @param {HTMLElement} host */
export async function renderFestivalTab(host) {
  const fp = await loadFestivalProfiles();
  if (!fp?.festivals) {
    host.innerHTML = `<section class="block">${naCell('페스티벌 프로필(festival_profiles.json)이 아직 없습니다', { block: true })}</section>`;
    return;
  }
  const labels = Object.fromEntries(Object.entries(fp.festivals).map(([k, f]) => [k, f.label || k]));
  const flows = (fp.flows || []).slice(0, 10);
  host.innerHTML = `
    <p class="small muted fest-note">새 팀 = 이 페스티벌 앞선 회차에 없던 팀 · 첫 페스티벌 = 우리 데이터의 첫 페스티벌 출연이 이 회차 · 그 뒤 정답 = 회차 뒤에 받은 센 정답(같은 집안 정답은 뺌)${fp.as_of ? ` · 기준 ${escapeHtml(fp.as_of)}` : ''}</p>
    <div class="fest-grid">${Object.entries(fp.festivals).map(([k, f]) => festivalCard(k, f)).join('')}</div>
    ${flows.length ? `
      <section class="block">
        <div class="block-head"><h3>페스티벌 사이 이동</h3><span class="block-meta">먼저 선 곳 → 나중에 선 곳 (팀 수 · 걸린 기간 중앙값)</span></div>
        <ul class="city-list">${flows.map(fl => `<li>${escapeHtml(labels[fl.from] || fl.from)} → ${escapeHtml(labels[fl.to] || fl.to)} <strong>${fmtInt(fl.teams)}팀</strong>${fl.median_months !== null && fl.median_months !== undefined ? ` <span class="small muted">· ${fl.median_months}개월</span>` : ''}</li>`).join('')}</ul>
      </section>` : ''}`;
}
