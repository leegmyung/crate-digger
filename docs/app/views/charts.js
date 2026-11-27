/**
 * 차트 #/charts/<종류>[/<장르·도시>] (정보 구조 v2 묶음 F) — 정의가 고정된 순위표.
 * 전체 · 장르별 · 도시별 · 떠오르는 팀 · 갓 데뷔(갓 데뷔는 candidates.js 의 갓 데뷔 화면이 이 탭 줄을 씀).
 * 차트는 내 필터·가중치와 상관없이 기본 정의로 계산하고, 지난주(기준일 − 7일) 같은 정의 순위와 비교해 ▲▼.
 * 조건을 바꾸고 싶으면 '이 조건으로 발굴에서 열기'.
 */
import { appState, cloneDefaults } from '../state.js';
import {
  buildParams, ensureTeamCitiesLoaded, fillTemplate, getSqlTemplate, queryDiscoveryStages,
  queryRisingPreset, runRawSql,
} from '../db.js';
import { loadCityProfiles } from '../db_venue.js';
import { isoMinusDays } from '../components/team_metrics.js';
import {
  escapeHtml, fmtInt, fmtNum, genreConfidenceBadgeHtml, INFO_TIPS, infoTip, naCell, plainWhyLine,
  stageBadgeHtml,
} from '../ui.js';

const CHART_SIZE = 50;
const POOL = 300; // 도시 차트는 전체 상위 300 안에서 고른다
const WEEK = 7;

const DEFINITIONS = {
  all: "전체 = 신인 후보 점수(v2) 순위 — 기준일 전 3년 신호 · 신인 3년 이내 · 유명 팀과 이미 정답 받은 팀 제외 · 기본 가중치(공연장 수는 최근 2년). 내 필터·가중치와 상관없이 고정.",
  genre: "장르별 = '전체'와 같은 정의에서 대표 장르가 이 장르인 팀(추정 장르 포함 — 이름 옆 '추정' 꼬리표).",
  city: "도시별 = '전체' 정의의 상위 300팀 중 활동 도시(공연 날짜가 가장 많은 도시)가 이 도시인 팀.",
  rising: '떠오르는 = 유명 제외 · 공연장 체급 M 이하 · 멜론 팬 1만 이하 · 최근 30일 남의 언급이 그 전 30일보다 많은 팀, 증가 폭 순 (rising_preset.sql).',
  debut: '갓 데뷔 = 기준일 전 12개월 안에 첫 발매했고 그 전 신호가 없던 백지 신인만 따로 매긴 순위 (debut_candidates.sql).',
};
const TAB_LABELS = { all: '전체', genre: '장르별', city: '도시별', rising: '떠오르는', debut: '갓 데뷔' };

/** 차트 탭 줄 + 정의 상자 (갓 데뷔 화면도 같이 씀) */
export function renderChartTabsHtml(kind, param = '') {
  const href = k => (k === 'all' ? '#/charts' : `#/charts/${k}`);
  return `
    <div class="chart-head">
      <h1 class="discover-title">차트</h1>
      <nav class="chart-tabs" aria-label="차트 종류">
        ${Object.keys(TAB_LABELS).map(k => `<a class="chart-tab${k === kind ? ' is-active' : ''}" href="${href(k)}"${k === kind ? ' aria-current="page"' : ''}>${TAB_LABELS[k]}${k === kind && param ? ` · ${escapeHtml(param)}` : ''}</a>`).join('')}
      </nav>
      <p class="chart-def"><strong>이 차트의 정의</strong> ${escapeHtml(DEFINITIONS[kind] || '')}${infoTip('종합 점수', INFO_TIPS.score, { compact: true })}</p>
    </div>`;
}

async function candidateChart(asOf, genre = '') {
  const tpl = await getSqlTemplate('candidates');
  if (!tpl) return [];
  const cfg = { ...cloneDefaults(), as_of: asOf, limit: POOL };
  const res = await runRawSql(fillTemplate(tpl, buildParams({ as_of: asOf, genre, limit: POOL }, cfg)));
  return res.rows;
}

async function chartRows(kind, param, asOf) {
  if (kind === 'rising') return queryRisingPreset({ as_of: asOf });
  if (kind === 'genre') return candidateChart(asOf, param);
  const rows = await candidateChart(asOf);
  if (kind === 'city') return rows.filter(r => appState.teamCitiesByTeam.get(r.team_key)?.home_city === param);
  return rows;
}

function deltaHtml(cur, prevPos) {
  if (prevPos === undefined) return '<span class="rank-delta is-up" title="지난주 이 차트에 없던 팀">NEW</span>';
  const d = prevPos - cur;
  if (d > 0) return `<span class="rank-delta is-up" title="지난주 ${prevPos}위">▲${fmtInt(d)}</span>`;
  if (d < 0) return `<span class="rank-delta is-down" title="지난주 ${prevPos}위">▼${fmtInt(-d)}</span>`;
  return '<span class="rank-delta is-flat" title="지난주와 같은 순위">–</span>';
}

function pickerHtml(kind, param, cities) {
  if (kind === 'genre') {
    const genres = appState.validGenres.filter(g => g && g !== '미분류');
    return `<label class="chart-picker">장르 <select class="select" data-chart-pick="genre">${genres.map(g => `<option value="${escapeHtml(g)}"${g === param ? ' selected' : ''}>${escapeHtml(g)}</option>`).join('')}</select></label>`;
  }
  if (kind === 'city') {
    return `<label class="chart-picker">도시 <select class="select" data-chart-pick="city">${cities.map(c => `<option value="${escapeHtml(c)}"${c === param ? ' selected' : ''}>${escapeHtml(c)}</option>`).join('')}</select></label>`;
  }
  return '';
}

function discoverHref(kind, param) {
  if (kind === 'genre') return `#/discover?genre=${encodeURIComponent(param)}`;
  if (kind === 'city') return `#/discover?hcity=${encodeURIComponent(param)}`;
  if (kind === 'rising') return '#/discover?preset=rising';
  return '#/discover';
}

function rowHtml(r, i, prevPos, stageByTeam, kind) {
  const stage = stageByTeam.get(r.team_key);
  const name = r.display_name || r.team_key;
  const genre = r.primary_genre ? `<span class="small muted">${escapeHtml(r.primary_genre)}</span>${genreConfidenceBadgeHtml(r.team_key)}` : '';
  const nums = kind === 'rising'
    ? `<td class="num" data-label="최근 30일">${fmtInt(r.recent_n)}건</td><td class="num" data-label="직전 30일">${fmtInt(r.prev_n)}건</td>`
    : `<td class="num" data-label="갈래">${fmtInt(r.n_branch)}</td><td class="num" data-label="공연장">${fmtInt(r.venues)}곳</td>`;
  const why = kind === 'rising'
    ? `${fmtInt(r.recent_branches)}개 갈래에서 언급`
    : plainWhyLine(r);
  return `
    <tr>
      <td class="num chart-rank" data-label="순위"><strong>${i + 1}</strong></td>
      <td class="nowrap" data-label="지난주 대비">${deltaHtml(i + 1, prevPos)}</td>
      <td data-label="팀"><a href="#/team/${encodeURIComponent(r.team_key)}"><strong>${escapeHtml(name)}</strong></a> ${genre}</td>
      <td data-label="단계">${stage !== undefined ? stageBadgeHtml(stage, { short: true }) : naCell('발굴 단계를 계산하지 않은 팀입니다', { label: '—' })}</td>
      <td class="num" data-label="점수">${r.score !== null && r.score !== undefined ? fmtNum(Number(r.score), 2) : '—'}</td>
      ${nums}
      <td class="chart-why" data-label="근거">${escapeHtml(why || '')}</td>
    </tr>`;
}

/** @param {HTMLElement} root */
export async function renderChartsView(root) {
  const kind = ['all', 'genre', 'city', 'rising'].includes(appState.chartKind) ? appState.chartKind : 'all';
  const asOf = appState.dataEnd || appState.cfg.as_of || '2026-11-28';
  const prevAsOf = isoMinusDays(asOf, WEEK);
  const [cp] = await Promise.all([loadCityProfiles(), ensureTeamCitiesLoaded().catch(() => null)]);
  const cities = cp?.cities
    ? Object.entries(cp.cities).sort((a, b) => (b[1].nights || 0) - (a[1].nights || 0)).map(([n]) => n)
    : [...new Set([...appState.teamCitiesByTeam.values()].map(v => v.home_city).filter(Boolean))];
  let param = appState.chartParam || '';
  if (kind === 'genre' && !param) param = appState.validGenres.find(g => g && g !== '미분류') || '';
  if (kind === 'city' && !param) param = cities[0] || '서울';

  const [rows, prevRows, stageData] = await Promise.all([
    chartRows(kind, param, asOf),
    chartRows(kind, param, prevAsOf).catch(() => []),
    queryDiscoveryStages({ as_of: asOf }).catch(() => null),
  ]);
  const top = rows.slice(0, CHART_SIZE);
  const prevPos = new Map(prevRows.slice(0, CHART_SIZE).map((r, i) => [r.team_key, i + 1]));
  const stageByTeam = new Map((stageData?.rows || []).map(r => [r.team_key, r.stage]));
  const numHeads = kind === 'rising' ? '<th class="num">최근 30일</th><th class="num">직전 30일</th>' : '<th class="num">갈래</th><th class="num">공연장(2년)</th>';

  root.innerHTML = `
    ${renderChartTabsHtml(kind, kind === 'genre' || kind === 'city' ? param : '')}
    <div class="chart-toolbar">
      ${pickerHtml(kind, param, cities)}
      <span class="small muted">기준 ${escapeHtml(asOf)} · ▲▼ = 지난주(${escapeHtml(prevAsOf || '')}) 같은 정의 순위와 비교 · 상위 ${fmtInt(CHART_SIZE)}팀</span>
      <a class="btn btn-sm" href="${discoverHref(kind, param)}">이 조건으로 발굴에서 열기 →</a>
    </div>
    <section class="block" style="padding:0;overflow:hidden;">
      ${top.length ? `
        <div class="table-wrap">
          <table class="data-table stack-table chart-table" aria-label="${escapeHtml(TAB_LABELS[kind])} 차트">
            <thead><tr><th class="num">#</th><th>지난주</th><th>팀</th><th>단계</th><th class="num">점수</th>${numHeads}<th>근거</th></tr></thead>
            <tbody>${top.map((r, i) => rowHtml(r, i, prevPos.get(r.team_key), stageByTeam, kind)).join('')}</tbody>
          </table>
        </div>` : `<div style="padding:16px;">${naCell(kind === 'city' && !appState.teamCitiesByTeam.size ? '팀별 활동 도시 자료(team_cities.csv)가 아직 없습니다' : '이 정의에 맞는 팀이 없습니다', { block: true })}</div>`}
    </section>
    <p class="small muted place-evidence">근거: 점수 정의는 <a href="#/verify/backtest">검증 › 점수 신뢰도</a> · 차트는 정의가 고정돼 필터를 바꿀 수 없습니다 — 바꾸려면 '발굴에서 열기'</p>`;

  root.querySelector('[data-chart-pick]')?.addEventListener('change', (e) => {
    const v = e.target.value;
    window.location.hash = `#/charts/${kind}/${encodeURIComponent(v)}`;
  });
}
