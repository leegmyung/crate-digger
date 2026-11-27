import { appState, setExportContext } from '../state.js';
import { querySourceScorecard } from '../db.js';
import {
  escapeHtml, fmtInt, fmtNum, formatSourceKey, josa,
  renderActionBanner, roleBadgeHtml,
} from '../ui.js';

const DEFAULT_SCORECARD_CUTOFFS = ['2024-07-01', '2025-01-01', '2025-07-01'];
const DEFAULT_SINCE = '2024-01-01';

const ROLE_ORDER = { discovery: 0, context: 1, excluded: 2, pending: 3 };

function detectRoleMismatch(r) {
  const role = r.role || 'pending';
  const teams = Number(r.teams) || 0;
  const hits = Number(r.hits) || 0;
  const lift = r.lift !== null && r.lift !== undefined ? Number(r.lift) : null;

  if (role === 'discovery' && teams >= 20 && lift !== null && lift < 1.0) {
    return { flag: true, reason: '발굴 분류지만 적중률이 기준선(1.0배) 미만' };
  }
  if (role === 'context' && teams >= 20 && lift !== null && lift >= 1.5) {
    return { flag: true, reason: '맥락 분류지만 적중률이 기준선 1.5배 이상' };
  }
  if (role === 'excluded' && teams >= 20 && lift !== null && lift >= 1.5) {
    return { flag: true, reason: '제외 분류지만 적중률이 기준선 1.5배 이상' };
  }
  if (role === 'pending' && teams >= 30 && hits > 0) {
    return { flag: true, reason: '표본이 충분히 쌓여 역할 배정 검토 가능' };
  }
  return { flag: false, reason: '' };
}

function buildConclusionHtml({ rows, totalWinners, since, baseRate, mismatches }) {
  if (!rows.length) {
    return '출처 성적표 데이터를 불러오지 못했습니다.';
  }
  const sinceYear = String(since || DEFAULT_SINCE).slice(0, 4);
  const sortedByWin = [...rows]
    .filter(r => Number(r.winners_seen) > 0)
    .sort((a, b) => (Number(b.winners_seen) - Number(a.winners_seen)) || (Number(b.first_to_see) - Number(a.first_to_see)));
  const top = sortedByWin[0];

  const contextRows = rows.filter(r => r.role === 'context');
  const contextBelowBase = contextRows.filter(
    r => r.rate !== null && r.rate !== undefined && baseRate !== null && Number(r.rate) <= baseRate
  );
  const pendingCount = rows.filter(r => r.role === 'pending').length;

  const parts = [];
  if (top && totalWinners > 0) {
    const info = formatSourceKey(top.src);
    const firstTxt = Number(top.first_to_see) > 0 ? `(가장 먼저 ${fmtInt(top.first_to_see)}팀)` : '';
    parts.push(
      `${sinceYear}년 이후 수상 팀 <strong>${fmtInt(totalWinners)}팀</strong> 중 <strong>${fmtInt(top.winners_seen)}팀</strong>을 <strong>${escapeHtml(josa(info.label, '이', '가'))}</strong> 먼저 잡았고${firstTxt}`
    );
  } else if (totalWinners > 0) {
    parts.push(`${sinceYear}년 이후 수상 팀은 <strong>${fmtInt(totalWinners)}팀</strong>이며`);
  }

  const baseTxt = baseRate !== null && baseRate !== undefined ? `(${fmtNum(baseRate, 2)}%)` : '';
  if (contextBelowBase.length > 0) {
    parts.push(`기준선${baseTxt} 이하 출처 <strong>${fmtInt(contextBelowBase.length)}곳</strong>은 맥락으로 분류되어 있습니다.`);
  } else if (contextRows.length > 0) {
    parts.push(`참고용 매체 <strong>${fmtInt(contextRows.length)}곳</strong>은 맥락으로 분류되어 있습니다.`);
  } else {
    parts.push(`전체 후보 기준 적중률은 <strong>${baseRate !== null ? fmtNum(baseRate, 2) + '%' : '-'}</strong>입니다.`);
  }

  let sentence = parts.join(', ');
  if (mismatches.length > 0) {
    sentence += ` <strong class="sc-warn-inline">재분류 검토 ${fmtInt(mismatches.length)}곳</strong>이 있습니다.`;
  } else if (pendingCount > 0) {
    sentence += ` 검증 대기 ${fmtInt(pendingCount)}곳은 기록이 쌓이는 중입니다.`;
  }
  return sentence;
}

export async function renderScorecardView(root) {
  const horizonMonths = appState.cfg.horizon_months || 24;
  const { cutoffs, since, totalWinners, rows } = await querySourceScorecard({
    cutoffs: DEFAULT_SCORECARD_CUTOFFS,
    since: DEFAULT_SINCE,
    horizonMonths,
  });

  const enriched = rows.map(r => {
    const info = formatSourceKey(r.src);
    const mismatch = detectRoleMismatch(r);
    return {
      ...r,
      branch: info.branch,
      code: info.code,
      label: info.label,
      mismatch,
    };
  });

  const baseRate = enriched.length && enriched[0].base_rate !== null && enriched[0].base_rate !== undefined
    ? Number(enriched[0].base_rate)
    : null;
  const counts = {
    all: enriched.length,
    discovery: enriched.filter(r => r.role === 'discovery').length,
    context: enriched.filter(r => r.role === 'context').length,
    excluded: enriched.filter(r => r.role === 'excluded').length,
    pending: enriched.filter(r => r.role === 'pending').length,
  };
  const mismatches = enriched.filter(r => r.mismatch.flag);

  const conclusionHtml = buildConclusionHtml({
    rows: enriched,
    totalWinners,
    since,
    baseRate,
    mismatches,
  });

  setExportContext({
    csvLabel: `출처 성적표 CSV 내려받기 (${fmtInt(enriched.length)}곳)`,
    csvFilename: `crate_digger_source_scorecard_${appState.dataEnd || 'export'}.csv`,
    csvHeaders: [
      'src', 'label', 'branch', 'role', 'reclassify_review', 'signal_rows',
      'since_date', 'teams', 'hits', 'rate_pct', 'lift', 'base_rate_pct',
      'winners_seen', 'first_to_see', 'only_source', 'median_lead_months',
    ],
    csvRows: enriched.map(r => [
      r.src, r.label, r.branch, r.role, r.mismatch.flag ? r.mismatch.reason : '',
      r.signal_rows ?? 0, r.since_date || '', r.teams ?? 0, r.hits ?? 0,
      r.rate ?? '', r.lift ?? '', r.base_rate ?? '',
      r.winners_seen ?? 0, r.first_to_see ?? 0, r.only_source ?? 0, r.median_lead_months ?? '',
    ]),
  });

  let activeFilter = 'all';

  function renderTableBody() {
    let list = enriched;
    if (activeFilter === 'mismatch') {
      list = enriched.filter(r => r.mismatch.flag);
    } else if (activeFilter !== 'all') {
      list = enriched.filter(r => r.role === activeFilter);
    }

    // Keep SQL order (winners_seen desc, rate desc) inside active filter, with pending grouped cleanly at bottom when viewing 'all'
    const sorted = [...list].sort((a, b) => {
      if (activeFilter === 'all') {
        const aPend = a.role === 'pending' ? 1 : 0;
        const bPend = b.role === 'pending' ? 1 : 0;
        if (aPend !== bPend) return aPend - bPend;
      }
      const wCmp = (Number(b.winners_seen) || 0) - (Number(a.winners_seen) || 0);
      if (wCmp !== 0) return wCmp;
      const rCmp = (Number(b.rate) || -1) - (Number(a.rate) || -1);
      if (rCmp !== 0) return rCmp;
      const roleCmp = (ROLE_ORDER[a.role] ?? 9) - (ROLE_ORDER[b.role] ?? 9);
      if (roleCmp !== 0) return roleCmp;
      return (Number(b.signal_rows) || 0) - (Number(a.signal_rows) || 0);
    });

    if (!sorted.length) {
      return `<tr><td colspan="8" class="muted small" style="text-align:center;padding:18px;">해당 조건의 출처가 없습니다.</td></tr>`;
    }

    return sorted.map(r => {
      const isPending = r.role === 'pending' && Number(r.teams) === 0;
      const isMuted = r.role === 'excluded' || r.role === 'pending';
      const rowCls = [
        isMuted ? 'is-muted-row' : '',
        r.mismatch.flag ? 'is-mismatch-row' : '',
      ].filter(Boolean).join(' ');

      const flagHtml = r.mismatch.flag
        ? `<span class="reclassify-badge" title="${escapeHtml(r.mismatch.reason)}">재분류 검토</span>`
        : '';

      if (isPending) {
        const sinceTxt = r.since_date ? `${String(r.since_date).slice(0, 10)}~` : '최근 수집 시작';
        return `
          <tr class="${rowCls}">
            <td>
              <div class="sc-src-cell">
                <strong>${escapeHtml(r.label)}</strong>
                <span class="sc-branch-tag">${escapeHtml(r.branch)}</span>
                ${flagHtml}
              </div>
            </td>
            <td class="nowrap">${roleBadgeHtml(r.role)}</td>
            <td class="num">${fmtInt(r.signal_rows)}</td>
            <td colspan="5" class="sc-pending-cell">
              <span class="sc-pending-pill">기록 쌓이는 중 (${escapeHtml(sinceTxt)})</span>
            </td>
          </tr>
        `;
      }

      const teams = Number(r.teams) || 0;
      const hits = Number(r.hits) || 0;
      const rateStr = r.rate !== null && r.rate !== undefined ? `${fmtNum(r.rate, 2)}%` : '-';
      const liftVal = r.lift !== null && r.lift !== undefined ? Number(r.lift) : null;
      const liftStr = liftVal !== null ? `${fmtNum(liftVal, 1)}배` : '-';
      const liftCls = liftVal !== null ? (liftVal >= 1.5 ? 'sc-lift-high' : (liftVal < 1.0 ? 'sc-lift-low' : '')) : '';
      const leadStr = r.median_lead_months !== null && r.median_lead_months !== undefined
        ? `${fmtNum(r.median_lead_months, 1)}개월`
        : '-';
      const thinNote = teams > 0 && teams < 20 ? ' <span class="muted small">(표본 적음)</span>' : '';

      return `
        <tr class="${rowCls}">
          <td>
            <div class="sc-src-cell">
              <strong>${escapeHtml(r.label)}</strong>
              <span class="sc-branch-tag">${escapeHtml(r.branch)}</span>
              ${flagHtml}
            </div>
          </td>
          <td class="nowrap">${roleBadgeHtml(r.role)}</td>
          <td class="num">${fmtInt(r.signal_rows)}</td>
          <td class="num nowrap">${teams > 0 ? `${fmtInt(hits)} / ${fmtInt(teams)}팀${thinNote}` : '-'}</td>
          <td class="num nowrap"><span class="${liftCls}"><strong>${rateStr}</strong> <span class="muted">(${liftStr})</span></span></td>
          <td class="num nowrap"><strong>${fmtInt(r.winners_seen)}팀</strong></td>
          <td class="num nowrap">${fmtInt(r.first_to_see)} / ${fmtInt(r.only_source)}</td>
          <td class="num nowrap">${leadStr}</td>
        </tr>
      `;
    }).join('');
  }

  function paint() {
    const chips = [
      { id: 'all', label: `전체 ${counts.all}` },
      { id: 'discovery', label: `발굴 ${counts.discovery}` },
      { id: 'context', label: `맥락 ${counts.context}` },
      { id: 'excluded', label: `제외 ${counts.excluded}` },
      { id: 'pending', label: `검증 대기 ${counts.pending}` },
    ];
    if (mismatches.length > 0) {
      chips.push({ id: 'mismatch', label: `재분류 검토 ${mismatches.length}` });
    }

    root.innerHTML = `
      ${renderActionBanner({
        title: '출처 성적표',
        lead: conclusionHtml,
        todo: '적중률(기준선 대비 배수)과 수상 팀 선행 포착 실적을 보고 발굴·맥락·제외 역할이 성적과 어긋나지 않는지 월 단위로 점검하세요.',
      })}

      <div class="stat-row">
        <div class="stat-card">
          <div class="stat-label">전체 후보 기준 적중률</div>
          <div class="stat-val">${baseRate !== null ? `${fmtNum(baseRate, 2)}%` : '-'}</div>
          <div class="stat-sub">기준일 ${cutoffs.length}개 합산 · 관찰 ${horizonMonths}개월</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">발굴 출처 (점수 반영)</div>
          <div class="stat-val">${fmtInt(counts.discovery)}곳</div>
          <div class="stat-sub">기준선 이상 검증된 출처</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">맥락 · 제외 출처</div>
          <div class="stat-val">${fmtInt(counts.context)} · ${fmtInt(counts.excluded)}곳</div>
          <div class="stat-sub">맥락은 약하게, 제외는 점수 미반영</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">검증 대기 · 재분류 검토</div>
          <div class="stat-val">${fmtInt(counts.pending)} · ${fmtInt(mismatches.length)}곳</div>
          <div class="stat-sub">${mismatches.length > 0 ? '역할과 성적 차이 확인 필요' : '현재 역할과 성적 일치'}</div>
        </div>
      </div>

      <section class="block">
        <div class="block-head">
          <h2>출처별 포착 실적</h2>
          <span class="block-meta">기준일 ${escapeHtml(cutoffs.join(' · '))} · 수상 팀 ${escapeHtml(since)}~ (${fmtInt(totalWinners)}팀)</span>
        </div>

        <div class="inline-filter-bar" role="group" aria-label="출처 역할 필터">
          <div class="chip-group">
            ${chips.map(ch => `
              <button type="button" class="chip-btn ${activeFilter === ch.id ? 'active' : ''}" data-sc-filter="${ch.id}">
                ${escapeHtml(ch.label)}
              </button>
            `).join('')}
          </div>
        </div>

        <div class="table-wrap">
          <table class="data-table sc-table">
            <thead>
              <tr>
                <th>출처</th>
                <th class="nowrap">현재 역할</th>
                <th class="num nowrap">신호 수</th>
                <th class="num nowrap">적중 / 후보</th>
                <th class="num nowrap">적중률 (배수)</th>
                <th class="num nowrap">수상 팀 포착</th>
                <th class="num nowrap">가장 먼저 / 유일</th>
                <th class="num nowrap">선행 개월</th>
              </tr>
            </thead>
            <tbody>
              ${renderTableBody()}
            </tbody>
          </table>
        </div>

        <details class="info-fold" style="margin:10px 0 0 0;">
          <summary>ⓘ 성적표 계산 · 재분류 검토 기준</summary>
          <div class="info-fold-body">
            <ul class="sc-info-list">
              <li><strong>적중률 (배수)</strong>: 기준일(${escapeHtml(cutoffs.join(', '))}) 전 3년 안에 이 출처 신호가 있던 신인 후보 중, 기준일 뒤 ${horizonMonths}개월 안에 센 정답을 받은 비율과 전체 후보 기준 적중률(${baseRate !== null ? fmtNum(baseRate, 2) + '%' : '-'}) 대비 배수입니다.</li>
              <li><strong>수상 팀 포착 · 가장 먼저 / 유일</strong>: ${escapeHtml(since)} 이후 첫 정답을 받은 팀(${fmtInt(totalWinners)}팀) 중 정답 전에 이 출처에 나온 팀 수, 모든 출처 가운데 가장 먼저 잡은 팀 수, 이 출처만 잡은 팀 수입니다.</li>
              <li><strong>재분류 검토 표시</strong>: 후보 20팀 이상인 출처 중 <em>발굴</em>인데 1.0배 미만이거나, <em>맥락·제외</em>인데 1.5배 이상이거나, <em>검증 대기</em>에서 표본 30팀 이상·적중이 생기면 자동으로 표시합니다.</li>
            </ul>
          </div>
        </details>
      </section>
    `;

    root.querySelectorAll('[data-sc-filter]').forEach(btn => {
      btn.addEventListener('click', () => {
        activeFilter = btn.dataset.scFilter;
        paint();
      });
    });
  }

  paint();
}
