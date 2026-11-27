import { appState, registerChart, syncHash } from '../state.js';
import { querySignalHits } from '../db.js';
import {
  cssVar, escapeHtml, fmtInt, fmtNum,
  renderActionBanner, signalWhiskerPlugin,
} from '../ui.js';

export async function renderSignalsView(root) {
  const cutoffs = [...new Set([...appState.cfg.cutoffs, ...appState.knownCutoffs])].sort();
  if (!cutoffs.includes(appState.cfg.signal_cutoff)) {
    appState.cfg.signal_cutoff = appState.cfg.cutoffs[appState.cfg.cutoffs.length - 1] || '2025-01-01';
  }

  const { cutoff, rows } = await querySignalHits(appState.cfg.signal_cutoff);
  const baselineRow = rows.find(r => String(r.program || '').startsWith('(기준선)'));
  const baseRate = baselineRow ? Number(baselineRow.rate) : null;
  const bestProg = rows.find(r => !String(r.program || '').startsWith('(기준선)') && Number(r.teams) >= 10);

  const leadParts = [];
  if (baselineRow) {
    leadParts.push(`기준일 ${cutoff} 후보 ${fmtInt(baselineRow.teams)}팀의 기본 정답 비율은 <strong>${fmtNum(baselineRow.rate, 1)}%</strong>(${fmtInt(baselineRow.hits)}팀)입니다.`);
  }
  if (bestProg) {
    leadParts.push(`표본 10팀 이상 중 가장 높은 프로그램은 <strong>${escapeHtml(bestProg.label)}</strong>(${fmtNum(bestProg.rate, 1)}%, ${fmtNum(bestProg.lift, 1)}배)입니다.`);
  }

  const bannerHtml = renderActionBanner({
    title: '신호별 적중률',
    lead: leadParts.join(' ') || '조건에 해당하는 신호 적중률 데이터가 없습니다.',
    todo: '신뢰구간 폭이 넓거나 표본이 10팀 미만(흐린 줄)인 프로그램은 아직 참고용으로만 보고, 기준일을 바꿔 일관성을 확인하세요.',
    buttonsHtml: '<a class="btn" href="#/evidence">리드타임·중간→최종 근거 보기</a>',
  });

  root.innerHTML = `
    ${bannerHtml}
    <div class="toolbar">
      <div class="toolbar-group">
        <label for="sigCutoffSel" class="small muted">기준일</label>
        <select id="sigCutoffSel" class="select">
          ${cutoffs.map(d => `<option value="${d}" ${d === cutoff ? 'selected' : ''}>${d}</option>`).join('')}
        </select>
        <span class="small muted">신호 기간 ${appState.cfg.lookback_years}년 · 관찰 ${appState.cfg.horizon_months}개월</span>
      </div>
    </div>

    <section class="block">
      <div class="block-head">
        <h2>선정·지원 프로그램별 정답 비율과 윌슨 95% 신뢰구간</h2>
        <span class="block-meta">n &lt; 10 흐리게 표시</span>
      </div>
      ${rows.length ? `
        <div class="chart-box chart-box-tall"><canvas id="sigHitsChart"></canvas></div>
        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>프로그램</th>
                <th class="num">후보 팀</th>
                <th class="num">정답 팀</th>
                <th class="num">적중률</th>
                <th class="nowrap">95% 신뢰구간</th>
                <th class="num">기준선 대비</th>
              </tr>
            </thead>
            <tbody>
              ${rows.map(r => {
                const isBase = String(r.program || '').startsWith('(기준선)');
                const lowN = !isBase && Number(r.teams) < 10;
                const cls = isBase ? 'baseline-row' : (lowN ? 'low-n' : '');
                const liftTxt = r.lift !== null && r.lift !== undefined ? `${fmtNum(r.lift, 1)}배` : '-';
                return `
                  <tr class="${cls}">
                    <td>${escapeHtml(r.label || r.program)}${lowN ? ' <span class="muted small">(표본 적음)</span>' : ''}</td>
                    <td class="num">${fmtInt(r.teams)}</td>
                    <td class="num">${fmtInt(r.hits)}</td>
                    <td class="num"><strong>${fmtNum(r.rate, 1)}%</strong></td>
                    <td class="nowrap mono muted">${fmtNum(r.ci_low, 1)}% ~ ${fmtNum(r.ci_high, 1)}%</td>
                    <td class="num">${liftTxt}</td>
                  </tr>
                `;
              }).join('')}
            </tbody>
          </table>
        </div>
      ` : '<p class="muted small" style="margin:0;">표시할 프로그램 데이터가 없습니다.</p>'}
    </section>
  `;

  if (rows.length && window.Chart) {
    const cv = root.querySelector('#sigHitsChart');
    const inkMuted = cssVar('--ink-muted');
    const lineColor = cssVar('--line');
    const maxVal = Math.max(15, ...rows.map(r => Number(r.ci_high) || Number(r.rate) || 0));

    registerChart(new window.Chart(cv.getContext('2d'), {
      type: 'bar',
      data: {
        labels: rows.map(r => r.label || r.program),
        datasets: [{
          label: '적중률 (%)',
          data: rows.map(r => Number(r.rate) || 0),
          backgroundColor: rows.map(r => {
            if (String(r.program || '').startsWith('(기준선)')) return cssVar('--bar-branch');
            if (Number(r.teams) < 10) return cssVar('--bar-gigs');
            return cssVar('--bar-score');
          }),
          borderRadius: 2,
          barThickness: 16,
        }],
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: it => {
                const r = rows[it.dataIndex];
                const lift = r.lift !== null && r.lift !== undefined ? `, 기준선 대비 ${fmtNum(r.lift, 1)}배` : '';
                return `${fmtInt(r.hits)} / ${fmtInt(r.teams)}팀 (${fmtNum(r.rate, 1)}%, 95% CI ${fmtNum(r.ci_low, 1)}~${fmtNum(r.ci_high, 1)}%${lift})`;
              },
            },
          },
          signalWhisker: {
            rows,
            baseline: baseRate,
            baselineColor: cssVar('--bar-ref'),
            whiskerColor: cssVar('--ink'),
          },
        },
        scales: {
          x: {
            beginAtZero: true,
            suggestedMax: Math.min(100, Math.ceil(maxVal / 5) * 5 + 5),
            ticks: { color: inkMuted, callback: v => `${v}%` },
            grid: { color: lineColor },
          },
          y: { ticks: { color: inkMuted }, grid: { display: false } },
        },
      },
      plugins: [signalWhiskerPlugin],
    }));
  }

  root.querySelector('#sigCutoffSel')?.addEventListener('change', e => {
    appState.cfg.signal_cutoff = e.target.value;
    syncHash(true);
    window.dispatchEvent(new CustomEvent('app:recompute'));
  });
}
