/**
 * 페스티벌 페이지 #/festival/<이름> (정보 구조 v2 묶음 E) — 회차표 · 라인업 표(회차 고르기, 후보 점수·발굴 단계·그 뒤 정답) ·
 * 라인업의 신인 비율·후보 점수 분포 · 선정/정답 연결(같은 집안 ⚠️ · 다른 페스티벌과 겹친 팀 · 페스티벌 사이 이동).
 * 주소의 <이름>은 페스티벌 키(burock_main 등) 또는 표시 이름(부산록페 루키즈 등) 둘 다 받는다.
 * 자료: festival_profiles.json (scripts/festival_profiles.py)
 */
import { appState } from '../state.js';
import { queryCandidates, queryDiscoveryStages } from '../db.js';
import { loadFestivalProfiles } from '../db_venue.js';
import {
  avatarHtml, escapeHtml, fmtInt, fmtNum, gradeBadgeHtml, INFO_TIPS, infoTip, naCell, playButtonHtml, stageBadgeHtml,
} from '../ui.js';
import { editionRowHtml, festivalKindLabel, pctText } from './festivals.js';
import { entityCellHtml } from '../components/entity_cell.js';
import { festivalQuestions } from '../insight_text.js';
import { easyText } from '../easy_terms.js';
import { placeQaHtml } from '../components/place_qa.js';

const SCORE_BANDS = [[6, '6점 이상'], [4, '4~6점'], [0, '4점 미만']];

export function findFestival(fp, name) {
  const all = fp?.festivals || {};
  if (all[name]) return [name, all[name]];
  return Object.entries(all).find(([, f]) => f.label === name) || null;
}

function lineupSummary(teams, candByKey) {
  const scored = teams.map(t => candByKey.get(t.team_key)).filter(Boolean);
  const bands = SCORE_BANDS.map(([lo, label], i) => {
    const hi = i === 0 ? Infinity : SCORE_BANDS[i - 1][0];
    return { label, n: scored.filter(c => c.score >= lo && c.score < hi).length };
  });
  return { inTop: scored.length, bands };
}

function lineupTableHtml(year, e, ctx) {
  const teams = Array.isArray(e.teams) ? e.teams : [];
  if (!teams.length) return naCell('이 회차 라인업 기록이 없습니다', { block: true });
  const winnerByKey = new Map((e.later_winners || []).map(w => [w.team_key, w]));
  const sum = lineupSummary(teams, ctx.candByKey);
  const rows = teams
    .map(t => ({ ...t, cand: ctx.candByKey.get(t.team_key) || null, stage: ctx.stageByTeam.get(t.team_key), win: winnerByKey.get(t.team_key) || null }))
    .sort((a, b) => (b.cand?.score ?? -1) - (a.cand?.score ?? -1) || String(a.name).localeCompare(String(b.name)));
  return `
    <div class="fest-lineup-summary small">
      <span>라인업 <strong>${fmtInt(teams.length)}</strong>팀</span>
      <span>이 페스티벌 새 팀 <strong>${pctText(e.new_to_festival_share)}</strong></span>
      <span>첫 페스티벌(신인) <strong>${pctText(e.first_festival_share)}</strong></span>
      <span>지금 후보 상위 300 <strong>${fmtInt(sum.inTop)}</strong>팀 (${sum.bands.map(b => `${b.label} ${fmtInt(b.n)}`).join(' · ')})</span>
    </div>
    <div class="table-wrap">
      <table class="data-table stack-table fest-lineup-table" aria-label="${escapeHtml(year)} 라인업">
        <thead><tr><th>팀</th><th class="num">지금 후보 점수${infoTip('종합 점수', INFO_TIPS.score, { compact: true })}</th><th class="col-fit">발굴 단계${infoTip('발굴 단계', INFO_TIPS.status_stage, { compact: true })}</th><th>그 뒤 수상·선정${infoTip('그 뒤 수상·선정', INFO_TIPS.festival_after_outcome, { compact: true })}</th></tr></thead>
        <tbody>${rows.map(r => `
          <tr>
            <td data-label="팀" class="col-name">${entityCellHtml({
              avatar: avatarHtml(r.team_key, r.name || r.team_key, 28, { shape: 'circle' }),
              name: `<a href="#/team/${encodeURIComponent(r.team_key)}"><strong>${escapeHtml(r.name || r.team_key)}</strong></a>`,
              title: r.name || r.team_key,
              actions: playButtonHtml(r.team_key, r.name || r.team_key, { variant: 'icon' }),
            })}</td>
            <td class="num" data-label="후보 점수">${r.cand ? `${fmtNum(r.cand.score, 2)} <span class="small muted num-suffix">#${fmtInt(r.cand.rank)}</span>` : naCell('지금 후보 상위 300팀 밖이거나 신인이 아닙니다', { label: '—' })}</td>
            <td class="col-fit" data-label="발굴 단계">${r.stage !== undefined && r.stage !== null ? stageBadgeHtml(r.stage, { short: true }) : naCell('발굴 단계를 계산하지 않은 팀입니다', { label: '—' })}</td>
            <td data-label="그 뒤 수상·선정">${r.win ? `${gradeBadgeHtml(r.win.grade)} <span class="small">${escapeHtml(r.win.outcome || '')} · ${fmtInt(r.win.lead_months)}개월 뒤</span>` : (e.upcoming ? '<span class="small muted">아직 안 열림</span>' : '<span class="small muted">없음</span>')}</td>
          </tr>`).join('')}</tbody>
      </table>
    </div>`;
}

/**
 * @param {HTMLElement} host
 * @param {string} name 키 또는 표시 이름
 */
export async function renderFestivalPage(host, name) {
  const asOf = appState.dataEnd || appState.cfg.as_of || '2026-11-28';
  const [fp, candRows, stageData] = await Promise.all([
    loadFestivalProfiles(),
    queryCandidates({ limit: 300 }).catch(() => []),
    queryDiscoveryStages({ as_of: asOf }).catch(() => null),
  ]);
  const back = '<div class="team-topbar"><a class="btn btn-sm" href="#/festivals">← 페스티벌 목록</a></div>';
  if (!fp?.festivals) {
    host.innerHTML = `${back}<section class="block">${naCell('페스티벌 프로필(festival_profiles.json)이 아직 없습니다', { block: true })}</section>`;
    return;
  }
  const hit = findFestival(fp, name);
  if (!hit) {
    host.innerHTML = `${back}<section class="block"><h1 class="place-title">${escapeHtml(name)}</h1>
      <p class="muted">이 페스티벌은 우리 기록에 없습니다. <a href="#/festivals">페스티벌 목록</a>에서 골라 주세요.</p></section>`;
    return;
  }
  const [key, f] = hit;
  const labels = Object.fromEntries(Object.entries(fp.festivals).map(([k, x]) => [k, x.label || k]));
  const eds = Object.entries(f.editions || {}).sort((a, b) => b[0].localeCompare(a[0]));
  const ctx = {
    candByKey: new Map(candRows.map((r, i) => [r.team_key, { score: Number(r.score), rank: i + 1 }])),
    stageByTeam: new Map((stageData?.rows || []).map(r => [r.team_key, r.stage])),
  };
  const sameHouse = f.same_house?.is_outcome || (f.same_house?.outcome_programs || []).length;
  const flows = (fp.flows || []).filter(fl => fl.from === key || fl.to === key);
  const overlaps = Array.isArray(f.overlaps) ? f.overlaps : [];
  let year = eds[0]?.[0] || '';

  const yearButtons = () => eds.map(([y, e]) => `<button type="button" class="cf-preset-btn${y === year ? ' is-active' : ''}" data-fest-year="${escapeHtml(y)}" aria-pressed="${y === year}">${escapeHtml(y)} <span class="cf-preset-cnt">${fmtInt(e.lineup)}</span></button>`).join('');

  // 공연장·도시와 같은 블록 순서: 머리 → 질문 3개 → 숫자 줄 → 회차 → 라인업 → 나머지 (docs/ux_simplify_2026-11-28.md ⑩)
  const flowsOut = (fp.flows || []).filter(fl => fl.from === key).map(fl => ({ toLabel: labels[fl.to] || fl.to, teams: Number(fl.teams) || 0 }));
  const qaHtml = placeQaHtml(festivalQuestions(f, { flowsOut }), `${f.label || key} 요약 질문`);
  const done = eds.filter(([, e]) => !e.upcoming);
  const [lastYear, last] = done[0] || ['', null];
  const winnersTotal = done.reduce((n, [, e]) => n + (Number(e.later_winners_total) || 0), 0);
  const kpi = (label, value, sub) => `<div class="venue-kpi-card"><span class="venue-kpi-lbl">${escapeHtml(label)}</span><strong class="venue-kpi-val mono">${value}</strong><span class="venue-kpi-sub">${sub}</span></div>`;
  const kpiHtml = `
      <div class="city-kpis">
        ${kpi('회차', `${fmtInt(eds.length)}개`, done.length < eds.length ? `예정 ${fmtInt(eds.length - done.length)}개 포함` : '우리 기록 기준')}
        ${kpi('누적 출연', `${fmtInt(f.teams_total || 0)}팀`, '모든 회차 합 (겹치면 1팀)')}
        ${kpi('최근 회차 라인업', last ? `${fmtInt(last.lineup || 0)}팀` : '—', lastYear ? `${escapeHtml(lastYear)}년` : '끝난 회차 없음')}
        ${kpi('첫 페스티벌 신인', last ? escapeHtml(pctText(last.first_festival_share)) : '—', last ? `${escapeHtml(lastYear)}년 ${fmtInt(last.first_festival || 0)}팀` : '')}
        ${kpi('그 뒤 수상·선정', `${fmtInt(winnersTotal)}팀`, '끝난 회차 합계')}
      </div>`;
  const editionsHtml = `
    <section class="block">
      <div class="block-head"><h2>회차</h2><span class="block-meta">새 팀 = 앞선 회차에 없던 팀 · 첫 페스티벌 = 우리 데이터의 첫 페스티벌 출연</span></div>
      <div class="table-wrap">
        <table class="data-table stack-table fest-table">
          <thead><tr><th>회차</th><th class="num">라인업</th><th class="num">새 팀${infoTip('새 팀', INFO_TIPS.festival_new_teams, { compact: true })}</th><th class="num">첫 페스티벌${infoTip('첫 페스티벌', INFO_TIPS.festival_first_fest, { compact: true })}</th><th>그 뒤 수상·선정${infoTip('그 뒤 수상·선정', INFO_TIPS.festival_after_outcome, { compact: true })}</th></tr></thead>
          <tbody>${eds.map(([y, e]) => editionRowHtml(y, e)).join('')}</tbody>
        </table>
      </div>
    </section>`;

  host.innerHTML = `
    ${back}
    <section class="place-head">
      <div class="place-head-row">
        <h1 class="place-title">${escapeHtml(f.label || key)}</h1>
        <span class="place-badge">${festivalKindLabel(f.kind)}</span>
      </div>
      <p class="small muted">회차 ${fmtInt(eds.length)}개 · 누적 ${fmtInt(f.teams_total || 0)}팀${fp.as_of ? ` · 기준 ${escapeHtml(fp.as_of)}` : ''}</p>
      ${sameHouse ? `<p class="fest-same-house">⚠️ 같은 주최 — ${escapeHtml(easyText(f.same_house?.note) || '수상·선정 프로그램과 같은 행사라 그 수상·선정은 \'그 뒤 수상·선정\'에서 뺐습니다')}</p>` : ''}
      ${qaHtml}
      ${kpiHtml}
    </section>
    ${editionsHtml}
    <section class="block" id="festLineupBlock">
      <div class="block-head"><h2>라인업</h2><span class="block-meta">회차를 고르면 그 회차 출연 팀 · 지금 후보 점수 순</span></div>
      <div class="city-picker" role="group" aria-label="회차 고르기" id="festYearPicker">${yearButtons()}</div>
      <div id="festLineupBody">${year ? lineupTableHtml(year, f.editions[year], ctx) : ''}</div>
    </section>
    <div class="city-grid">
      <section class="block"><div class="block-head"><h3>다른 페스티벌과 겹친 팀</h3><span class="block-meta">어느 쪽에 먼저 섰나</span></div>
        ${overlaps.length ? `<ul class="city-list">${overlaps.map(o => `<li><a href="#/festival/${encodeURIComponent(o.festival)}">${escapeHtml(o.label || labels[o.festival] || o.festival)}</a> <strong>${fmtInt(o.teams)}팀</strong> <span class="small muted">· 여기 먼저 ${fmtInt(o.this_first)} · 거기 먼저 ${fmtInt(o.other_first)}${o.same_day ? ` · 같은 날 ${fmtInt(o.same_day)}` : ''}</span></li>`).join('')}</ul>` : '<p class="small muted" style="margin:0;">겹친 팀이 없습니다.</p>'}
      </section>
      <section class="block"><div class="block-head"><h3>페스티벌 사이 이동</h3><span class="block-meta">팀 수 · 걸린 기간 중앙값</span></div>
        ${flows.length ? `<ul class="city-list">${flows.map(fl => `<li>${escapeHtml(labels[fl.from] || fl.from)} → ${escapeHtml(labels[fl.to] || fl.to)} <strong>${fmtInt(fl.teams)}팀</strong>${fl.median_months !== null && fl.median_months !== undefined ? ` <span class="small muted">· ${fl.median_months}개월</span>` : ''}</li>`).join('')}</ul>` : '<p class="small muted" style="margin:0;">이 페스티벌이 들어간 이동 기록이 없습니다.</p>'}
      </section>
    </div>
    <p class="small muted place-evidence">근거: 그 뒤 수상·선정 = 회차 날짜보다 뒤·기준일 이하의 큰 수상·선정(같은 주최가 주는 상은 뺌) · 등급 규칙은 <a href="#/verify/grades">검증 › 정답 등급</a></p>`;

  host.querySelector('#festYearPicker')?.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-fest-year]');
    if (!btn || btn.dataset.festYear === year) return;
    year = btn.dataset.festYear;
    host.querySelector('#festYearPicker').innerHTML = yearButtons();
    host.querySelector('#festLineupBody').innerHTML = lineupTableHtml(year, f.editions[year], ctx);
    host.querySelector(`[data-fest-year="${CSS.escape(year)}"]`)?.focus();
  });
}
