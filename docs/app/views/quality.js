import { appState, registerChart, setExportContext } from '../state.js';
import { COLLECT_TABLE_LABELS, DROP_CHECK_TABLES, isRunDropped } from '../db.js';
import { cssVar, escapeHtml, fmtInt, renderActionBanner, SOURCE_LABELS } from '../ui.js';

function formatDeltaText(cur, prev) {
  if (prev === null || prev === undefined || prev === '') return '';
  const c = Number(cur);
  const p = Number(prev);
  if (!Number.isFinite(c) || !Number.isFinite(p)) return '';
  const diff = c - p;
  if (diff === 0) return ' (전일 동일)';
  return ` (${diff > 0 ? '+' : ''}${fmtInt(diff)})`;
}

export async function renderQualityView(root) {
  const meta = appState.meta || {};
  const rowsMeta = meta.rows || {};
  const prevMeta = (meta.prev_rows && typeof meta.prev_rows === 'object') ? meta.prev_rows : {};
  const dj = appState.dashboardJson || {};
  const sec = dj.sections || {};
  const qualityRows = sec.quality || [];
  const collRows = sec.collection || [];
  const gigsMonth = sec.gigs_by_month || [];
  const collectRuns = Array.isArray(appState.collectJson?.runs) ? appState.collectJson.runs : [];
  const hasAnyPrevRun = collectRuns.some(r => r.prev_rows !== null && r.prev_rows !== undefined);
  const health = appState.dataHealth;

  setExportContext({
    csvLabel: collRows.length ? `수집 현황 CSV 내려받기 (${fmtInt(collRows.length)}출처)` : '',
    csvFilename: `crate_digger_collection_${appState.dataEnd || 'export'}.csv`,
    csvHeaders: ['branch', 'source', 'rows', 'teams', 'first_date', 'last_date'],
    csvRows: collRows.map(c => [c.branch || '', SOURCE_LABELS[c.source] || c.source, c.rows ?? 0, c.teams ?? 0, c.first_date || '', c.last_date || '']),
  });

  const warnCount = qualityRows.filter(q => q.level === 'warn').length;
  const sigDelta = formatDeltaText(rowsMeta.signals, prevMeta.signals);
  const teamDelta = formatDeltaText(rowsMeta.teams, prevMeta.teams);
  const outDelta = formatDeltaText(rowsMeta.outcomes, prevMeta.outcomes);

  const bannerHtml = renderActionBanner({
    title: '데이터 수집·품질',
    lead: `마지막 수집 <strong>${escapeHtml(health.lastCollectedDate || meta.data_end || '-')}</strong> (${escapeHtml(health.summaryLabel)}) · 신호 ${fmtInt(rowsMeta.signals)}건 · 팀 ${fmtInt(rowsMeta.teams)}곳 · 점검 주의 ${fmtInt(warnCount)}건.`,
  });

  root.innerHTML = `
    ${bannerHtml}

    <div class="stat-row">
      <div class="stat-card">
        <div class="stat-label">자동 수집 상태</div>
        <div class="stat-val">${health.ok ? '정상' : '확인 필요'}</div>
        <div class="stat-sub">${escapeHtml(health.summaryLabel)}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">데이터 기준일</div>
        <div class="stat-val mono">${escapeHtml(meta.data_end || '-')}</div>
        <div class="stat-sub">생성 ${escapeHtml((meta.generated_at || '').slice(0, 16).replace('T', ' '))}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">신호 · 팀</div>
        <div class="stat-val">${fmtInt(rowsMeta.signals)}${sigDelta ? `<span class="small muted">${escapeHtml(sigDelta)}</span>` : ''}</div>
        <div class="stat-sub">고유 팀 ${fmtInt(rowsMeta.teams)}곳${escapeHtml(teamDelta)} · 사진 ${fmtInt(rowsMeta.images || 0)}팀</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">정답 기록</div>
        <div class="stat-val">${fmtInt(rowsMeta.outcomes)}${outDelta ? `<span class="small muted">${escapeHtml(outDelta)}</span>` : ''}</div>
        <div class="stat-sub">집계 대상 ${fmtInt(appState.outcomeRange.counted)}건 (${escapeHtml(appState.outcomeRange.min || '-')}~)</div>
      </div>
    </div>

    ${collectRuns.length ? `
      <section class="block">
        <div class="block-head">
          <h2>최근 자동 수집 실행 결과 (매일 21시)</h2>
          <span class="block-meta">${escapeHtml(health.lastCollectedDate || '')} · ${fmtInt(collectRuns.length)}개 실행</span>
        </div>
        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>날짜</th>
                <th>표 · 소스</th>
                <th class="num">수집 행 수</th>
                ${hasAnyPrevRun ? '<th class="num nowrap">직전 대비</th>' : ''}
                <th class="nowrap">상태</th>
              </tr>
            </thead>
            <tbody>
              ${collectRuns.map(r => {
                const isDailyFull = DROP_CHECK_TABLES.has(String(r.table || ''));
                const bad = r.file_ok === false || (isDailyFull && Number(r.rows) === 0);
                const dropped = !bad && isRunDropped(r);
                const tblLabel = COLLECT_TABLE_LABELS[String(r.table || '')] || '';
                let prevCell = '';
                if (hasAnyPrevRun) {
                  if (r.prev_rows === null || r.prev_rows === undefined) {
                    prevCell = '<td class="num muted">-</td>';
                  } else {
                    const diff = Number(r.rows) - Number(r.prev_rows);
                    const diffTxt = diff === 0 ? '0' : `${diff > 0 ? '+' : ''}${fmtInt(diff)}`;
                    prevCell = `<td class="num nowrap ${dropped ? 'sc-warn-inline' : 'muted'}">${escapeHtml(diffTxt)} <span class="small">(${fmtInt(r.prev_rows)}→${fmtInt(r.rows)})</span></td>`;
                  }
                }
                const statusBadge = bad
                  ? '<span class="badge-warn">확인 필요</span>'
                  : (dropped ? '<span class="badge-warn">급감</span>' : '<span class="badge-ok">정상</span>');
                return `
                  <tr>
                    <td class="nowrap mono muted">${escapeHtml(r.date || '-')}</td>
                    <td><strong>${escapeHtml(SOURCE_LABELS[r.source] || r.source)}</strong>${tblLabel ? ` <span class="small muted">${escapeHtml(tblLabel)}</span>` : ''}</td>
                    <td class="num">${fmtInt(r.rows)}</td>
                    ${prevCell}
                    <td class="nowrap">${statusBadge}</td>
                  </tr>
                `;
              }).join('')}
            </tbody>
          </table>
        </div>
      </section>
    ` : ''}

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
                  <td class="nowrap mono">${escapeHtml(q.value)}${q.level === 'warn' ? ' (주의)' : q.level === 'error' ? ' (오류)' : ''}</td>
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
      <section class="block" style="padding:0;overflow:hidden;">
        <div class="block-head" style="padding:16px 16px 10px 16px;margin:0;">
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
            <tbody id="qualCollTbody"></tbody>
          </table>
        </div>
        <div class="more-row" id="qualCollMore" hidden></div>
      </section>
    ` : ''}
  `;

  if (collRows.length) {
    let showAllColl = false;
    const renderColl = () => {
      const shown = showAllColl ? collRows : collRows.slice(0, 10);
      root.querySelector('#qualCollTbody').innerHTML = shown.map(c => `
        <tr>
          <td>${escapeHtml(c.branch || '-')}</td>
          <td><strong>${escapeHtml(SOURCE_LABELS[c.source] || c.source)}</strong></td>
          <td class="num">${fmtInt(c.rows)}</td>
          <td class="num">${fmtInt(c.teams)}</td>
          <td class="nowrap mono muted">${escapeHtml(c.first_date || '-')}</td>
          <td class="nowrap mono muted">${escapeHtml(c.last_date || '-')}</td>
        </tr>
      `).join('');
      const rem = collRows.length - shown.length;
      const more = root.querySelector('#qualCollMore');
      if (rem > 0) {
        more.hidden = false;
        more.innerHTML = `<span>${fmtInt(shown.length)} / ${fmtInt(collRows.length)}개 표시</span><button type="button" class="btn btn-sm" id="btnQualCollMore">${fmtInt(rem)}개 더 보기</button>`;
        more.querySelector('#btnQualCollMore').addEventListener('click', () => { showAllColl = true; renderColl(); });
      } else {
        more.hidden = true;
      }
    };
    renderColl();
  }

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
