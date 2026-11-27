import { appState, registerChart } from '../state.js';
import { cssVar, escapeHtml, fmtInt, fmtNum, renderActionBanner } from '../ui.js';

export async function renderEvidenceView(root) {
  const dj = appState.dashboardJson;
  const sec = dj?.sections || {};
  const leadSummary = (sec.lead_time_summary || [])[0] || {};
  const leadRows = sec.lead_time || [];
  const midRows = sec.mid_to_final || [];
  const careerRows = sec.career_at_outcome || [];
  const careerSum = (sec.career_summary || [])[0] || {};

  const pctPrior = leadSummary.outcome_teams
    ? Math.round((100 * leadSummary.with_prior_signal) / leadSummary.outcome_teams)
    : 0;

  const bannerHtml = renderActionBanner({
    title: '검증 근거 (리드타임 · 중간→최종 · 수상 연차)',
    lead: leadSummary.outcome_teams
      ? `정답 ${fmtInt(leadSummary.outcome_teams)}팀 중 <strong>${fmtInt(leadSummary.with_prior_signal)}팀(${pctPrior}%)</strong>에서 사전 신호가 잡혔고, 첫 신호부터 정답까지 중앙값은 <strong>${fmtNum(leadSummary.median_months, 1)}개월</strong>입니다.`
      : 'dashboard.json 요약 근거 데이터를 불러오지 못했습니다.',
    todo: '선행 포착 시점과 중간→최종 전환율을 확인한 뒤 점수 검증 화면에서 관찰 기간·가중치를 조정해 보세요.',
    buttonsHtml: '<a class="btn" href="#/backtest">점수 검증으로</a>',
  });

  if (!dj) {
    root.innerHTML = `${bannerHtml}<div class="notice">data/dashboard.json 파일이 없어 근거 요약을 표시할 수 없습니다.</div>`;
    return;
  }

  root.innerHTML = `
    ${bannerHtml}

    <section class="block">
      <div class="block-head">
        <h2>1. 얼마나 미리 포착했나 (선행 리드타임)</h2>
        <span class="block-meta">정답 ${fmtInt(leadSummary.outcome_teams)}팀 · 1년+ 선행 ${fmtInt(leadSummary.over_12m)}팀</span>
      </div>
      <div class="chart-box chart-box-sm"><canvas id="evLeadChart"></canvas></div>
      <div class="table-wrap">
        <table class="data-table">
          <thead>
            <tr><th>선행 구간</th><th class="num">팀 수</th><th class="num">평균 개월</th></tr>
          </thead>
          <tbody>
            ${leadRows.map(r => `
              <tr>
                <td>${escapeHtml(r.bucket)}</td>
                <td class="num"><strong>${fmtInt(r.teams)}팀</strong></td>
                <td class="num muted">${r.avg_months !== null && r.avg_months !== undefined ? `${fmtNum(r.avg_months, 1)}개월` : '-'}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    </section>

    <div class="grid-2">
      <section class="block" style="margin-bottom:0;">
        <div class="block-head">
          <h2>2. 중간 단계에서 최종 수상으로</h2>
          <span class="block-meta">중간 선정 이후 최종 정답 전환</span>
        </div>
        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr><th>중간 프로그램</th><th class="num">팀</th><th class="num">최종 수상</th><th class="num">전환율</th></tr>
            </thead>
            <tbody>
              ${midRows.map(r => `
                <tr class="${Number(r.teams) < 10 ? 'low-n' : ''}">
                  <td>${escapeHtml(r.program_label || r.program)}</td>
                  <td class="num">${fmtInt(r.teams)}</td>
                  <td class="num">${fmtInt(r.later_final)}</td>
                  <td class="num"><strong>${fmtNum(r.rate, 1)}%</strong></td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      </section>

      <section class="block" style="margin-bottom:0;">
        <div class="block-head">
          <h2>3. 수상 당시 활동 연차</h2>
          <span class="block-meta">중앙값 ${fmtNum(careerSum.median_years, 1)}년 · 3년 이내 ${fmtInt(careerSum.within_3y)}/${fmtInt(careerSum.teams)}팀</span>
        </div>
        <div class="chart-box chart-box-sm"><canvas id="evCareerChart"></canvas></div>
        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr><th>활동 연차 구간</th><th class="num">팀 수</th></tr>
            </thead>
            <tbody>
              ${careerRows.map(r => `
                <tr><td>${escapeHtml(r.bucket)}</td><td class="num"><strong>${fmtInt(r.teams)}팀</strong></td></tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  `;

  if (window.Chart) {
    const inkMuted = cssVar('--ink-muted');
    const lineColor = cssVar('--line');

    const leadCv = root.querySelector('#evLeadChart');
    if (leadCv && leadRows.length) {
      registerChart(new window.Chart(leadCv.getContext('2d'), {
        type: 'bar',
        data: {
          labels: leadRows.map(r => r.bucket),
          datasets: [{ label: '팀 수', data: leadRows.map(r => Number(r.teams) || 0), backgroundColor: cssVar('--bar-score'), borderRadius: 2 }],
        },
        options: {
          responsive: true, maintainAspectRatio: false, animation: false,
          plugins: { legend: { display: false } },
          scales: {
            x: { ticks: { color: inkMuted }, grid: { display: false } },
            y: { beginAtZero: true, ticks: { color: inkMuted, precision: 0 }, grid: { color: lineColor } },
          },
        },
      }));
    }

    const carCv = root.querySelector('#evCareerChart');
    if (carCv && careerRows.length) {
      registerChart(new window.Chart(carCv.getContext('2d'), {
        type: 'bar',
        data: {
          labels: careerRows.map(r => r.bucket),
          datasets: [{ label: '팀 수', data: careerRows.map(r => Number(r.teams) || 0), backgroundColor: cssVar('--bar-branch'), borderRadius: 2 }],
        },
        options: {
          responsive: true, maintainAspectRatio: false, animation: false,
          plugins: { legend: { display: false } },
          scales: {
            x: { ticks: { color: inkMuted }, grid: { display: false } },
            y: { beginAtZero: true, ticks: { color: inkMuted, precision: 0 }, grid: { color: lineColor } },
          },
        },
      }));
    }
  }
}
