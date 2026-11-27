import {
  appState, DEFAULTS, getMatchingWeightPreset, PRESET_KS, registerChart,
  setExportContext, syncHash, WEIGHT_FIELDS, WEIGHT_KEYS, WEIGHT_PRESETS,
} from '../state.js';
import { loadScoreTuningSummary, queryBacktestAll } from '../db.js';
import {
  cssVar, ensureChartJs, escapeHtml, fmtInt, fmtNum,
  horizontalBaselinePlugin, renderActionBanner, renderTableCsvBtn,
  triggerTableCsvExport,
} from '../ui.js';

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

export async function renderBacktestView(root) {
  const c = appState.cfg;
  const [blocks, tuningSummary] = await Promise.all([
    queryBacktestAll(),
    loadScoreTuningSummary(),
    ensureChartJs().catch(() => null),
  ]);

  // Compute summary at compare_k (fallback to first k_list item)
  const validKs = c.k_list.length ? c.k_list : [20, 50, 100, 200];
  const compK = validKs.includes(c.compare_k) ? c.compare_k : validKs[0];
  c.compare_k = compK;

  // Build side-by-side summary rows across selected cutoffs at compK
  const summaryRows = blocks.map(blk => {
    const byKey = new Map(blk.rows.map(r => [`${Number(r.k)}|${r.method}`, r]));
    const rs = byKey.get(`${compK}|점수`);
    const rg = byKey.get(`${compK}|공연 수만`);
    const rb = byKey.get(`${compK}|갈래 수만`);
    const poolN = blk.rows.length ? Number(blk.rows[0].pool_n) : 0;
    const poolHits = blk.rows.length ? Number(blk.rows[0].pool_hits) : 0;
    return {
      cutoff: blk.cutoff,
      poolN,
      poolHits,
      scoreHits: Number(rs?.hits ?? 0),
      gigsHits: Number(rg?.hits ?? 0),
      branchHits: Number(rb?.hits ?? 0),
      randExp: Number(rs?.random_expected ?? 0),
      lift: rs?.lift ?? null,
    };
  });

  const totPoolN = summaryRows.reduce((a, r) => a + r.poolN, 0);
  const totPoolHits = summaryRows.reduce((a, r) => a + r.poolHits, 0);
  const totScoreHits = summaryRows.reduce((a, r) => a + r.scoreHits, 0);
  const totGigsHits = summaryRows.reduce((a, r) => a + r.gigsHits, 0);
  const totBranchHits = summaryRows.reduce((a, r) => a + r.branchHits, 0);
  const totRandExp = summaryRows.reduce((a, r) => a + r.randExp, 0);
  const totLift = totRandExp > 0 ? (totScoreHits / totRandExp) : null;

  const leadText = blocks.length
    ? `선택한 기준일 <strong>${blocks.length}개</strong> 합계(상위 ${compK}팀 기준): 점수 <strong>${fmtInt(totScoreHits)}팀</strong> · 갈래 수만 ${fmtInt(totBranchHits)}팀 · 공연 수만 ${fmtInt(totGigsHits)}팀 (무작위 기대 ${fmtNum(totRandExp, 2)}팀${totLift !== null ? `, ${fmtNum(totLift, 1)}배` : ''}).`
    : '기준일을 1개 이상 선택해 백테스트를 실행하세요.';

  const bannerHtml = renderActionBanner({
    title: '점수 검증 (백테스트)',
    lead: leadText,
    todo: '아래 가중치 슬라이더를 바꾸면 백테스트와 홈·발굴·차트·팀 페이지 점수가 함께 다시 계산됩니다.',
    buttonsHtml: '<button type="button" class="btn" id="btResetWeights">가중치·조건 기본값</button>',
  });

  // Honest warnings
  const warnings = [];
  const outOfRange = c.cutoffs.filter(d => d < '2022-01-01' || d > '2025-12-31');
  if (outOfRange.length) {
    warnings.push(`의미 있는 검증 범위(2022-01 ~ 2025-12) 밖의 기준일이 포함되어 있습니다: ${outOfRange.join(', ')}. (집계 정답 범위: ${appState.outcomeRange.min || '-'} ~ ${appState.outcomeRange.max || '-'})`);
  }
  const thinCutoffs = summaryRows.filter(r => r.cutoff <= '2023-12-31' || (r.poolN > 0 && r.poolN < 300));
  if (thinCutoffs.length) {
    warnings.push(`2023년 이전 구간(${thinCutoffs.map(r => `${r.cutoff}: 후보 ${fmtInt(r.poolN)}팀`).join(', ')})은 그 시점 신호 데이터가 얇아 변동 폭이 큽니다.`);
  }
  if (blocks.length && (totScoreHits < 5 || summaryRows.some(r => r.scoreHits < 5))) {
    warnings.push('표본 적음 — 기준일별 맞힌 팀이 5팀 미만인 구간이 있어 단일 기준일 결과는 우연일 수 있습니다. 합계 줄과 다른 K 구간을 함께 보세요.');
  }

  const slidersHtml = WEIGHT_FIELDS.map(f => `
    <div class="slider-row${f.muted ? ' slider-row-muted' : ''}"${f.muted ? ' title="협업 데이터가 쌓이면 점수에 반영됩니다"' : ''}>
      <div class="slider-label">
        <label for="bt_${f.key}">${f.label}</label>
        <span class="mono" id="btval_${f.key}">${f.isInt ? c[f.key] : Number(c[f.key]).toFixed(1)}</span>
      </div>
      <input type="range" id="bt_${f.key}" data-weight-key="${f.key}" min="${f.min}" max="${f.max}" step="${f.step}" value="${c[f.key]}">
    </div>
  `).join('');

  const cutoffChecksHtml = appState.knownCutoffs.map(d => `
    <label class="f-check">
      <input type="checkbox" name="bt_cutoff" value="${d}" ${c.cutoffs.includes(d) ? 'checked' : ''}>
      <span class="mono">${d}</span>
    </label>
  `).join('');

  const allKs = [...new Set([...PRESET_KS, ...c.k_list])].sort((a, b) => a - b);
  const kChecksHtml = allKs.map(k => `
    <label class="f-check">
      <input type="checkbox" name="bt_k" value="${k}" ${c.k_list.includes(k) ? 'checked' : ''}>
      <span>상위 ${k}</span>
    </label>
  `).join('');

  const btCsvSpec = blocks.length ? {
    filename: `crate_digger_backtest_top${compK}_${appState.dataEnd || 'export'}.csv`,
    headers: ['기준일', '후보', '이후 정답', '점수 맞힘', '공연 수만', '갈래 수만', '무작위 기대', '점수 배수'],
    rows: [
      ...summaryRows.map(r => [
        r.cutoff,
        r.poolN,
        r.poolHits,
        `${r.scoreHits}팀`,
        `${r.gigsHits}팀`,
        `${r.branchHits}팀`,
        `${fmtNum(r.randExp, 2)}팀`,
        r.lift !== null ? `${fmtNum(r.lift, 1)}배` : '—',
      ]),
      [
        `모든 기준일 합계 (${summaryRows.length}개)`,
        totPoolN,
        totPoolHits,
        `${totScoreHits}팀`,
        `${totGigsHits}팀`,
        `${totBranchHits}팀`,
        `${fmtNum(totRandExp, 2)}팀`,
        totLift !== null ? `${fmtNum(totLift, 1)}배` : '—',
      ],
    ],
  } : null;

  setExportContext({
    csvLabel: btCsvSpec ? `과거 검증 CSV 내려받기 (상위 ${compK}팀)` : '',
    csvFilename: btCsvSpec?.filename || '',
    csvHeaders: btCsvSpec?.headers || [],
    csvRows: btCsvSpec?.rows || [],
  });

  // Side-by-side table across cutoffs + total row
  const summaryTableHtml = blocks.length ? `
    <section class="block">
      <div class="block-head">
        <h2>기준일별 나란히 비교 (상위 ${compK}팀)</h2>
        <div class="block-head-actions">
          <div class="toolbar-group">
            <label for="btCompK" class="small muted">비교 구간</label>
            <select id="btCompK" class="select">
              ${validKs.map(k => `<option value="${k}" ${k === compK ? 'selected' : ''}>상위 ${k}팀</option>`).join('')}
            </select>
          </div>
          ${renderTableCsvBtn('btnBtCsv', 'CSV 내려받기')}
        </div>
      </div>
      <div class="chart-box chart-box-sm"><canvas id="btSummaryChart"></canvas></div>
      <div class="table-wrap table-sticky">
        <table class="data-table">
          <thead>
            <tr>
              <th class="nowrap">기준일</th>
              <th class="num">후보</th>
              <th class="num">이후 정답</th>
              <th class="num">점수 맞힘</th>
              <th class="num">공연 수만</th>
              <th class="num">갈래 수만</th>
              <th class="num">무작위 기대</th>
              <th class="num">점수 배수</th>
            </tr>
          </thead>
          <tbody>
            ${summaryRows.map(r => `
              <tr>
                <td class="nowrap mono">${escapeHtml(r.cutoff)}${r.cutoff <= '2023-12-31' ? ' <span class="muted small">(데이터 적음)</span>' : ''}</td>
                <td class="num">${fmtInt(r.poolN)}</td>
                <td class="num">${fmtInt(r.poolHits)}</td>
                <td class="num"><strong>${fmtInt(r.scoreHits)}팀</strong></td>
                <td class="num">${fmtInt(r.gigsHits)}팀</td>
                <td class="num">${fmtInt(r.branchHits)}팀</td>
                <td class="num muted">${fmtNum(r.randExp, 2)}팀</td>
                <td class="num">${r.lift !== null ? `${fmtNum(r.lift, 1)}배` : '—'}</td>
              </tr>
            `).join('')}
            <tr class="summary-row">
              <td class="nowrap">모든 기준일 합계 (${summaryRows.length}개)</td>
              <td class="num">${fmtInt(totPoolN)}</td>
              <td class="num">${fmtInt(totPoolHits)}</td>
              <td class="num">${fmtInt(totScoreHits)}팀</td>
              <td class="num">${fmtInt(totGigsHits)}팀</td>
              <td class="num">${fmtInt(totBranchHits)}팀</td>
              <td class="num">${fmtNum(totRandExp, 2)}팀</td>
              <td class="num">${totLift !== null ? `${fmtNum(totLift, 1)}배` : '—'}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  ` : '';

  const perCutoffHtml = blocks.map((blk, idx) => {
    const rows = blk.rows;
    const poolN = rows.length ? Number(rows[0].pool_n) : 0;
    const poolHits = rows.length ? Number(rows[0].pool_hits) : 0;
    const baseRate = poolN > 0 ? (100 * poolHits / poolN) : 0;
    const ks = [...new Set(rows.map(r => Number(r.k)))].sort((a, b) => a - b);
    const byKey = new Map(rows.map(r => [`${Number(r.k)}|${r.method}`, r]));

    const fmtCell = (r, bold = false) => {
      if (!r) return '<td class="num">-</td>';
      const liftStr = r.lift !== null && r.lift !== undefined ? `${fmtNum(r.lift, 1)}배` : '-';
      const s = `${fmtInt(r.hits)}팀 (${fmtNum(r.hit_rate, 1)}%, ${liftStr})`;
      return `<td class="num nowrap">${bold ? `<strong>${s}</strong>` : s}</td>`;
    };

    return `
      <section class="block">
        <div class="block-head">
          <h3>기준일 ${escapeHtml(blk.cutoff)} 상세</h3>
          <span class="block-meta">후보 ${fmtInt(poolN)}팀 · 이후 정답 ${fmtInt(poolHits)}팀 · 기준율 ${baseRate.toFixed(2)}%</span>
        </div>
        ${poolN === 0
          ? '<p class="muted small" style="margin:0;">현재 필터 조건에 해당하는 후보 팀이 없습니다.</p>'
          : `
            <div class="chart-box"><canvas id="btDetailChart_${idx}"></canvas></div>
            <div class="table-wrap">
              <table class="data-table">
                <thead>
                  <tr>
                    <th class="nowrap">구간</th>
                    <th class="num">점수 (맞힘 · 적중률 · 배수)</th>
                    <th class="num">갈래 수만</th>
                    <th class="num">공연 수만</th>
                    <th class="num">무작위 기대</th>
                  </tr>
                </thead>
                <tbody>
                  ${ks.map(k => {
                    const rs = byKey.get(`${k}|점수`);
                    const rb = byKey.get(`${k}|갈래 수만`);
                    const rg = byKey.get(`${k}|공연 수만`);
                    return `
                      <tr>
                        <td class="nowrap"><strong>상위 ${k}팀</strong></td>
                        ${fmtCell(rs, true)}
                        ${fmtCell(rb, false)}
                        ${fmtCell(rg, false)}
                        <td class="num nowrap muted">${fmtNum(rs?.random_expected, 2)}팀</td>
                      </tr>
                    `;
                  }).join('')}
                </tbody>
              </table>
            </div>
          `}
      </section>
    `;
  }).join('');

  root.innerHTML = `
    ${bannerHtml}
    ${warnings.map(w => `<div class="notice notice-warn">${escapeHtml(w)}</div>`).join('')}

    <section class="block">
      <div class="block-head">
        <h2>가중치 · 백테스트 조건</h2>
        <span class="block-meta">집계 정답 범위: ${escapeHtml(appState.outcomeRange.min || '-')} ~ ${escapeHtml(appState.outcomeRange.max || '-')} (${fmtInt(appState.outcomeRange.counted)}건)</span>
      </div>
      <div class="bt-controls">
        <div>
          <div class="small muted" style="font-weight:700;margin-bottom:6px;">점수 가중치 (전체 화면 공통 적용)</div>
          <div class="preset-bar" role="group" aria-label="점수 가중치 프리셋">
            <button type="button" class="btn btn-sm ${getMatchingWeightPreset(c) === 'v2' ? 'btn-active' : ''}" data-weight-preset="v2">v2 (기본, 정제 후 교차 검증)</button>
            <button type="button" class="btn btn-sm ${getMatchingWeightPreset(c) === 'v1' ? 'btn-active' : ''}" data-weight-preset="v1">v1</button>
            <button type="button" class="btn btn-sm ${getMatchingWeightPreset(c) === 'v0' ? 'btn-active' : ''}" data-weight-preset="v0">v0</button>
          </div>
          <p class="preset-note">
            기본값 v2는 출처 정제 뒤 기준일 빼기 교차 검증으로 고른 가중치입니다${tuningSummary?.aucLine ? ` (${escapeHtml(tuningSummary.aucLine)})` : ' (교차 검증 결과는 문서 참고)'}.
            고정 v2를 전체 기준일에 다시 채점한 수치는 고를 때 본 기준일이 섞여 과장되므로, 고를 때 뺀 기준일 교차 검증 수치를 기준으로 보세요.
            <a href="https://github.com/leegmyung/crate-digger/blob/main/docs/score_tuning.md" target="_blank" rel="noopener noreferrer">선정 과정 보기 ↗</a>
          </p>
          <div class="slider-grid">${slidersHtml}</div>
        </div>
        <div>
          <div class="small muted" style="font-weight:700;margin-bottom:6px;">기준일 · 관찰 조건</div>
          <div class="check-row" style="margin-bottom:8px;">${cutoffChecksHtml}</div>
          <div class="toolbar-group" style="margin-bottom:10px;">
            <input type="date" id="btAddCutoffInp" class="input" aria-label="기준일 추가">
            <button type="button" class="btn btn-sm" id="btAddCutoffBtn">기준일 추가</button>
          </div>
          <div class="toolbar-group" style="margin-bottom:10px;">
            <label class="small muted" for="btHorizon">관찰 기간</label>
            <select id="btHorizon" class="select">
              ${[6, 12, 18, 24, 36].map(m => `<option value="${m}" ${c.horizon_months === m ? 'selected' : ''}>${m}개월</option>`).join('')}
            </select>
            <label class="small muted" for="btTier">정답 종류</label>
            <select id="btTier" class="select">
              <option value="any" ${c.outcome_tier === 'any' ? 'selected' : ''}>전체</option>
              <option value="final" ${c.outcome_tier === 'final' ? 'selected' : ''}>최종만</option>
              <option value="mid" ${c.outcome_tier === 'mid' ? 'selected' : ''}>중간만</option>
            </select>
            <label class="small muted" for="btLookback">신호 기간(년)</label>
            <input type="number" id="btLookback" class="input input-num" min="1" max="15" value="${c.lookback_years}">
          </div>
          <div class="check-row">${kChecksHtml}</div>
        </div>
      </div>
    </section>

    ${summaryTableHtml}
    ${perCutoffHtml}
  `;

  root.querySelector('#btnBtCsv')?.addEventListener('click', () => {
    if (btCsvSpec) triggerTableCsvExport(btCsvSpec);
  });

  // Render charts
  if (window.Chart && blocks.length) {
    const inkMuted = cssVar('--ink-muted');
    const lineColor = cssVar('--line');

    // Summary chart across cutoffs + total
    const sumCanvas = root.querySelector('#btSummaryChart');
    if (sumCanvas) {
      const labels = [...summaryRows.map(r => r.cutoff), '합계'];
      registerChart(new window.Chart(sumCanvas.getContext('2d'), {
        type: 'bar',
        data: {
          labels,
          datasets: [
            { label: '점수', data: [...summaryRows.map(r => r.scoreHits), totScoreHits], backgroundColor: cssVar('--bar-score'), borderRadius: 2 },
            { label: '갈래 수만', data: [...summaryRows.map(r => r.branchHits), totBranchHits], backgroundColor: cssVar('--bar-branch'), borderRadius: 2 },
            { label: '공연 수만', data: [...summaryRows.map(r => r.gigsHits), totGigsHits], backgroundColor: cssVar('--bar-gigs'), borderRadius: 2 },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          animation: false,
          plugins: {
            legend: { position: 'top', align: 'start', labels: { color: inkMuted, boxWidth: 12, font: { size: 12 } } },
            tooltip: { callbacks: { label: it => `${it.dataset.label}: ${it.formattedValue}팀` } },
          },
          scales: {
            x: { ticks: { color: inkMuted, font: { size: 12 } }, grid: { display: false } },
            y: { beginAtZero: true, ticks: { color: inkMuted, precision: 0, callback: v => `${v}팀` }, grid: { color: lineColor } },
          },
        },
      }));
    }

    // Per-cutoff detail charts
    blocks.forEach((blk, idx) => {
      const cv = root.querySelector(`#btDetailChart_${idx}`);
      if (!cv) return;
      const rows = blk.rows;
      const poolN = Number(rows[0].pool_n);
      const poolHits = Number(rows[0].pool_hits);
      const baseRate = poolN > 0 ? (100 * poolHits / poolN) : 0;
      const ks = [...new Set(rows.map(r => Number(r.k)))].sort((a, b) => a - b);
      const byKey = new Map(rows.map(r => [`${Number(r.k)}|${r.method}`, r]));

      registerChart(new window.Chart(cv.getContext('2d'), {
        type: 'bar',
        data: {
          labels: ks.map(k => `상위 ${k}`),
          datasets: [
            { label: '점수', data: ks.map(k => Number(byKey.get(`${k}|점수`)?.hit_rate ?? 0)), backgroundColor: cssVar('--bar-score'), borderRadius: 2 },
            { label: '갈래 수만', data: ks.map(k => Number(byKey.get(`${k}|갈래 수만`)?.hit_rate ?? 0)), backgroundColor: cssVar('--bar-branch'), borderRadius: 2 },
            { label: '공연 수만', data: ks.map(k => Number(byKey.get(`${k}|공연 수만`)?.hit_rate ?? 0)), backgroundColor: cssVar('--bar-gigs'), borderRadius: 2 },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          animation: false,
          plugins: {
            legend: { position: 'top', align: 'start', labels: { color: inkMuted, boxWidth: 12, font: { size: 12 } } },
            tooltip: {
              callbacks: {
                label: it => {
                  const k = ks[it.dataIndex];
                  const m = it.dataset.label;
                  const r = byKey.get(`${k}|${m}`);
                  if (!r) return `${m}: ${it.formattedValue}%`;
                  const lift = r.lift !== null && r.lift !== undefined ? `, ${fmtNum(r.lift, 1)}배` : '';
                  return `${m}: ${fmtInt(r.hits)}팀 / ${k}팀 (${fmtNum(r.hit_rate, 1)}%${lift})`;
                },
              },
            },
            horizontalBaseline: {
              value: baseRate,
              color: cssVar('--bar-ref'),
              bgColor: cssVar('--bg'),
              label: `무작위 기대 ${baseRate.toFixed(1)}%`,
            },
          },
          scales: {
            x: { ticks: { color: inkMuted, font: { size: 12 } }, grid: { display: false } },
            y: { beginAtZero: true, ticks: { color: inkMuted, callback: v => `${v}%` }, grid: { color: lineColor } },
          },
        },
        plugins: [horizontalBaselinePlugin],
      }));
    });
  }

  // Wire controls
  const trigger = () => {
    syncHash(true);
    window.dispatchEvent(new CustomEvent('app:recompute'));
  };

  root.querySelectorAll('button[data-weight-preset]').forEach(btn => {
    btn.addEventListener('click', () => {
      const preset = WEIGHT_PRESETS[btn.dataset.weightPreset];
      if (!preset) return;
      for (const k of WEIGHT_KEYS) {
        appState.cfg[k] = preset[k];
      }
      trigger();
    });
  });

  root.querySelectorAll('input[data-weight-key]').forEach(inp => {
    inp.addEventListener('input', () => {
      const k = inp.dataset.weightKey;
      const v = Number(inp.value);
      appState.cfg[k] = v;
      const lbl = root.querySelector(`#btval_${k}`);
      if (lbl) lbl.textContent = k === 'outlet_cap' ? String(v) : v.toFixed(1);
      const matched = getMatchingWeightPreset(appState.cfg);
      root.querySelectorAll('button[data-weight-preset]').forEach(b => {
        b.classList.toggle('btn-active', b.dataset.weightPreset === matched);
      });
    });
    inp.addEventListener('change', trigger);
  });

  root.querySelectorAll('input[name="bt_cutoff"]').forEach(cb => {
    cb.addEventListener('change', () => {
      appState.cfg.cutoffs = [...root.querySelectorAll('input[name="bt_cutoff"]:checked')].map(el => el.value).sort();
      trigger();
    });
  });

  root.querySelector('#btAddCutoffBtn')?.addEventListener('click', () => {
    const val = root.querySelector('#btAddCutoffInp').value;
    if (!DATE_RE.test(val)) return;
    if (!appState.knownCutoffs.includes(val)) {
      appState.knownCutoffs.push(val);
      appState.knownCutoffs.sort();
    }
    if (!appState.cfg.cutoffs.includes(val)) {
      appState.cfg.cutoffs.push(val);
      appState.cfg.cutoffs.sort();
    }
    trigger();
  });

  root.querySelectorAll('input[name="bt_k"]').forEach(cb => {
    cb.addEventListener('change', () => {
      const ks = [...root.querySelectorAll('input[name="bt_k"]:checked')].map(el => Number(el.value)).sort((a, b) => a - b);
      if (ks.length) appState.cfg.k_list = ks;
      trigger();
    });
  });

  root.querySelector('#btHorizon')?.addEventListener('change', e => {
    appState.cfg.horizon_months = Number(e.target.value) || 24;
    trigger();
  });
  root.querySelector('#btTier')?.addEventListener('change', e => {
    appState.cfg.outcome_tier = e.target.value;
    trigger();
  });
  root.querySelector('#btLookback')?.addEventListener('change', e => {
    appState.cfg.lookback_years = Math.max(1, Math.min(15, Math.round(Number(e.target.value) || 3)));
    trigger();
  });
  root.querySelector('#btCompK')?.addEventListener('change', e => {
    appState.cfg.compare_k = Number(e.target.value) || 20;
    trigger();
  });

  root.querySelector('#btResetWeights')?.addEventListener('click', () => {
    for (const k of [...WEIGHT_KEYS, 'horizon_months', 'outcome_tier', 'lookback_years', 'compare_k']) {
      appState.cfg[k] = DEFAULTS[k];
    }
    appState.cfg.cutoffs = [...DEFAULTS.cutoffs];
    appState.cfg.k_list = [...DEFAULTS.k_list];
    trigger();
  });
}
