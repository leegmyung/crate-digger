import { appState, registerChart } from '../state.js';
import { cssVar, escapeHtml, fmtInt, renderActionBanner, SOURCE_LABELS } from '../ui.js';

export async function renderQualityView(root) {
  const meta = appState.meta || {};
  const rowsMeta = meta.rows || {};
  const dj = appState.dashboardJson || {};
  const sec = dj.sections || {};
  const qualityRows = sec.quality || [];
  const collRows = sec.collection || [];
  const gigsMonth = sec.gigs_by_month || [];

  const warnCount = qualityRows.filter(q => q.level === 'warn').length;
  const bannerHtml = renderActionBanner({
    title: '데이터 현황 · 품질',
    lead: `데이터 기준일은 <strong>${escapeHtml(meta.data_end || '-')}</strong>이며, 신호 ${fmtInt(rowsMeta.signals)}건 · 팀 ${fmtInt(rowsMeta.teams)}곳 · 정답 ${fmtInt(rowsMeta.outcomes)}건이 적재되어 있습니다.`,
    todo: warnCount > 0
      ? `품질 점검 항목 중 주의(${warnCount}건) 표시된 수집 공백을 확인하세요.`
      : '모든 수집 출처의 최신 날짜와 행 수를 확인해 공백이 없는지 점검하세요.',
  });

  root.innerHTML = `
    ${bannerHtml}

    <div class="stat-row">
      <div class="stat-card">
        <div class="stat-label">데이터 기준일</div>
        <div class="stat-val mono">${escapeHtml(meta.data_end || '-')}</div>
        <div class="stat-sub">생성 ${escapeHtml((meta.generated_at || '').slice(0, 16).replace('T', ' '))}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">신호 행 수</div>
        <div class="stat-val">${fmtInt(rowsMeta.signals)}</div>
        <div class="stat-sub">공연·선정·발매·큐레이션</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">고유 팀 수</div>
        <div class="stat-val">${fmtInt(rowsMeta.teams)}</div>
        <div class="stat-sub">artist_xref: ${meta.uses_artist_xref ? '연결됨' : '미연결'}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">정답 기록</div>
        <div class="stat-val">${fmtInt(rowsMeta.outcomes)}</div>
        <div class="stat-sub">집계 대상 ${fmtInt(appState.outcomeRange.counted)}건 (${escapeHtml(appState.outcomeRange.min || '-')}~)</div>
      </div>
    </div>

    ${qualityRows.length ? `
      <section class="block">
        <div class="block-head">
          <h2>품질 점검 항목</h2>
          <span class="block-meta">${fmtInt(qualityRows.length)}개 항목</span>
        </div>
        <div class="table-wrap">
          <table class="data-table">
            <thead><tr><th>항목</th><th class="nowrap">상태 / 값</th><th>설명</th></tr></thead>
            <tbody>
              ${qualityRows.map(q => `
                <tr>
                  <td><strong>${escapeHtml(q.item)}</strong></td>
                  <td class="nowrap mono">${escapeHtml(q.value)}${q.level === 'warn' ? ' (주의)' : ''}</td>
                  <td class="muted">${escapeHtml(q.note || '')}</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      </section>
    ` : ''}

    ${gigsMonth.length ? `
      <section class="block">
        <div class="block-head">
          <h2>월별 공연 수집량 추이</h2>
          <span class="block-meta">최근 ${fmtInt(gigsMonth.length)}개월</span>
        </div>
        <div class="chart-box chart-box-sm"><canvas id="qualGigsChart"></canvas></div>
      </section>
    ` : ''}

    ${collRows.length ? `
      <section class="block">
        <div class="block-head">
          <h2>출처별 수집 현황</h2>
          <span class="block-meta">${fmtInt(collRows.length)}개 출처</span>
        </div>
        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>갈래</th>
                <th>출처</th>
                <th class="num">행 수</th>
                <th class="num">팀 수</th>
                <th class="nowrap">첫 날짜</th>
                <th class="nowrap">마지막 날짜</th>
              </tr>
            </thead>
            <tbody>
              ${collRows.map(c => `
                <tr>
                  <td>${escapeHtml(c.branch || '-')}</td>
                  <td><strong>${escapeHtml(SOURCE_LABELS[c.source] || c.source)}</strong></td>
                  <td class="num">${fmtInt(c.rows)}</td>
                  <td class="num">${fmtInt(c.teams)}</td>
                  <td class="nowrap mono muted">${escapeHtml(c.first_date || '-')}</td>
                  <td class="nowrap mono muted">${escapeHtml(c.last_date || '-')}</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      </section>
    ` : ''}
  `;

  if (window.Chart && gigsMonth.length) {
    const cv = root.querySelector('#qualGigsChart');
    const inkMuted = cssVar('--ink-muted');
    const lineColor = cssVar('--line');
    registerChart(new window.Chart(cv.getContext('2d'), {
      type: 'bar',
      data: {
        labels: gigsMonth.map(g => g.month),
        datasets: [{ label: '공연 건수', data: gigsMonth.map(g => Number(g.gigs) || 0), backgroundColor: cssVar('--bar-score'), borderRadius: 2 }],
      },
      options: {
        responsive: true, maintainAspectRatio: false, animation: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { ticks: { color: inkMuted, maxTicksLimit: 12 }, grid: { display: false } },
          y: { beginAtZero: true, ticks: { color: inkMuted }, grid: { color: lineColor } },
        },
      },
    }));
  }
}
