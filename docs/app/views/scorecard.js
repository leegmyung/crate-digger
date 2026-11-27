import { appState, setExportContext, syncHash } from '../state.js';
import { loadSourceReview, loadSourceRoles, querySourceScorecard } from '../db.js';
import {
  escapeHtml, fmtInt, fmtNum, formatSourceKey, josa,
  renderActionBanner, renderTableCsvBtn, roleBadgeHtml,
  triggerTableCsvExport, updateSortHeaders,
  wireTableKeyboardNav, wireTableRowHoverPreview,
} from '../ui.js';

const DEFAULT_SCORECARD_CUTOFFS = ['2024-07-01', '2025-01-01', '2025-07-01'];
const DEFAULT_SINCE = '2024-01-01';

const ROLE_ORDER = { discovery: 0, context: 1, excluded: 2, pending: 3 };
const ROLE_LABEL_KO = { discovery: '발굴', context: '맥락', excluded: '제외', pending: '검증 대기' };

function sortScorecardRows(rows, col, dir, activeFilter) {
  const m = dir === 'asc' ? 1 : -1;
  const numVal = (v) => (v === null || v === undefined || v === '' ? null : Number(v));
  return [...rows].sort((a, b) => {
    if (col === 'winners_seen' && dir === 'desc' && activeFilter === 'all') {
      const aPend = a.role === 'pending' ? 1 : 0;
      const bPend = b.role === 'pending' ? 1 : 0;
      if (aPend !== bPend) return aPend - bPend;
    }
    if (col === 'label') {
      return String(a.label || '').localeCompare(String(b.label || ''), 'ko') * m;
    }
    if (col === 'role') {
      const rc = ((ROLE_ORDER[a.role] ?? 9) - (ROLE_ORDER[b.role] ?? 9)) * m;
      if (rc !== 0) return rc;
      return (Number(b.winners_seen) || 0) - (Number(a.winners_seen) || 0);
    }
    if (col === 'signal_rows') {
      return ((Number(a.signal_rows) || 0) - (Number(b.signal_rows) || 0)) * m;
    }
    if (col === 'teams') {
      const av = Number(a.teams) || 0;
      const bv = Number(b.teams) || 0;
      if (av !== bv) return (av - bv) * m;
      return ((Number(a.hits) || 0) - (Number(b.hits) || 0)) * m;
    }
    if (col === 'rate' || col === 'median_lead_months') {
      const av = numVal(a[col]);
      const bv = numVal(b[col]);
      if (av === null && bv === null) return (Number(b.signal_rows) || 0) - (Number(a.signal_rows) || 0);
      if (av === null) return 1;
      if (bv === null) return -1;
      if (av !== bv) return (av - bv) * m;
      return (Number(b.winners_seen) || 0) - (Number(a.winners_seen) || 0);
    }
    if (col === 'first_to_see') {
      const av = Number(a.first_to_see) || 0;
      const bv = Number(b.first_to_see) || 0;
      if (av !== bv) return (av - bv) * m;
      return ((Number(a.only_source) || 0) - (Number(b.only_source) || 0)) * m;
    }
    // default: winners_seen
    const wCmp = ((Number(a.winners_seen) || 0) - (Number(b.winners_seen) || 0)) * m;
    if (wCmp !== 0) return wCmp;
    const rCmp = (Number(b.rate) || -1) - (Number(a.rate) || -1);
    if (rCmp !== 0) return rCmp;
    const roleCmp = (ROLE_ORDER[a.role] ?? 9) - (ROLE_ORDER[b.role] ?? 9);
    if (roleCmp !== 0) return roleCmp;
    return (Number(b.signal_rows) || 0) - (Number(a.signal_rows) || 0);
  });
}

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
  const [{ cutoffs, since, totalWinners, rows }, sourceRoles] = await Promise.all([
    querySourceScorecard({
      cutoffs: DEFAULT_SCORECARD_CUTOFFS,
      since: DEFAULT_SINCE,
      horizonMonths,
    }),
    loadSourceRoles(),
    loadSourceReview().catch(() => null),
  ]);

  const reviewJson = appState.sourceReviewJson;
  const reviewSuggestions = Array.isArray(reviewJson?.suggestions) ? reviewJson.suggestions : [];
  const suggestionBySrc = new Map();
  for (const s of reviewSuggestions) {
    if (s?.src) suggestionBySrc.set(s.src, s);
  }

  const enriched = rows.map(r => {
    const info = formatSourceKey(r.src);
    const mismatch = detectRoleMismatch(r);
    const roleMeta = sourceRoles?.signals?.[r.src] || null;
    const roleReason = roleMeta?.reason || '';
    const reviewSuggestion = suggestionBySrc.get(r.src) || null;
    return {
      ...r,
      branch: info.branch,
      code: info.code,
      label: info.label,
      mismatch,
      roleReason,
      reviewSuggestion,
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

  const rowBySrc = new Map(enriched.map(r => [r.src, r]));

  const validFilters = new Set(['all', 'discovery', 'context', 'excluded', 'pending']);
  if (mismatches.length > 0) validFilters.add('mismatch');
  if (!validFilters.has(appState.scFilter)) appState.scFilter = 'all';

  let expandedSrc = null;
  let lastScCsvSpec = null;

  function renderReviewSuggestionsBox() {
    if (!reviewSuggestions.length) return '';
    const dateMeta = reviewJson?.data_end ? `기준 ${reviewJson.data_end}` : '';
    return `
      <aside class="sc-review-box" id="scReviewBox" aria-label="출처 재분류 제안">
        <div class="sc-review-head">
          <strong>재분류 제안 ${fmtInt(reviewSuggestions.length)}건</strong>
          ${dateMeta ? `<span class="small muted">${escapeHtml(dateMeta)}</span>` : ''}
        </div>
        <ul class="sc-review-list">
          ${reviewSuggestions.map(s => {
            const info = formatSourceKey(s.src);
            const sugText = String(s.suggestion || '').replace(/discovery/g, '발굴').replace(/context/g, '맥락').replace(/excluded/g, '제외');
            return `
              <li>
                <span class="sc-review-src">
                  <strong>${escapeHtml(info.label)}</strong>
                  ${info.branch ? `<span class="sc-branch-tag">${escapeHtml(info.branch)}</span>` : ''}
                  ${roleBadgeHtml(s.role)}
                </span>
                <span class="sc-review-sug">→ ${escapeHtml(sugText)}</span>
                ${s.reason ? `<span class="small muted">· ${escapeHtml(s.reason)}</span>` : ''}
              </li>
            `;
          }).join('')}
        </ul>
      </aside>
    `;
  }

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
        <div class="stat-val">${baseRate !== null ? `${fmtNum(baseRate, 2)}%` : '—'}</div>
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

    ${renderReviewSuggestionsBox()}

    <section class="block">
      <div class="block-head">
        <div>
          <h2>출처별 포착 실적</h2>
          <span class="block-meta">기준일 ${escapeHtml(cutoffs.join(' · '))} · 수상 팀 ${escapeHtml(since)}~ (${fmtInt(totalWinners)}팀)</span>
        </div>
        <div class="block-head-actions">
          <span class="table-kb-hint">↑↓ 이동 · Enter/→ 사유 펼치기</span>
          ${renderTableCsvBtn('btnScCsv', 'CSV 내려받기')}
        </div>
      </div>

      <div class="inline-filter-bar" role="group" aria-label="출처 역할 필터">
        <div class="chip-group">
          ${chips.map(ch => `
            <button type="button" class="chip-btn ${appState.scFilter === ch.id ? 'active' : ''}" data-sc-filter="${ch.id}" aria-pressed="${appState.scFilter === ch.id ? 'true' : 'false'}">
              ${escapeHtml(ch.label)}
            </button>
          `).join('')}
        </div>
      </div>

      <div class="table-wrap table-sticky">
        <table class="data-table sc-table" id="scTable">
          <thead>
            <tr>
              <th class="sortable" data-sc-sort="label">출처</th>
              <th class="nowrap sortable" data-sc-sort="role">현재 역할</th>
              <th class="num nowrap sortable" data-sc-sort="signal_rows">신호 수</th>
              <th class="num nowrap sortable" data-sc-sort="teams">적중 / 후보</th>
              <th class="num nowrap sortable" data-sc-sort="rate">적중률 (배수)</th>
              <th class="num nowrap sortable" data-sc-sort="winners_seen">수상 팀 포착</th>
              <th class="num nowrap sortable" data-sc-sort="first_to_see">가장 먼저 / 유일</th>
              <th class="num nowrap sortable" data-sc-sort="median_lead_months">선행 개월</th>
            </tr>
          </thead>
          <tbody id="scTbody"></tbody>
        </table>
      </div>

      <details class="info-fold" style="margin:10px 0 0 0;">
        <summary>ⓘ 성적표 계산 · 재분류 검토 기준</summary>
        <div class="info-fold-body">
          <ul class="sc-info-list">
            <li><strong>적중률 (배수)</strong>: 기준일(${escapeHtml(cutoffs.join(', '))}) 전 3년 안에 이 출처 신호가 있던 신인 후보 중, 기준일 뒤 ${horizonMonths}개월 안에 센 정답을 받은 비율과 전체 후보 기준 적중률(${baseRate !== null ? fmtNum(baseRate, 2) + '%' : '—'}) 대비 배수입니다.</li>
            <li><strong>수상 팀 포착 · 가장 먼저 / 유일</strong>: ${escapeHtml(since)} 이후 첫 정답을 받은 팀(${fmtInt(totalWinners)}팀) 중 정답 전에 이 출처에 나온 팀 수, 모든 출처 가운데 가장 먼저 잡은 팀 수, 이 출처만 잡은 팀 수입니다.</li>
            <li><strong>재분류 검토 표시</strong>: 후보 20팀 이상인 출처 중 <em>발굴</em>인데 1.0배 미만이거나, <em>맥락·제외</em>인데 1.5배 이상이거나, <em>검증 대기</em>에서 표본 30팀 이상·적중이 생기면 자동으로 표시합니다.</li>
          </ul>
        </div>
      </details>
    </section>
  `;

  function paint(focusSrc = null) {
    const activeFilter = appState.scFilter || 'all';
    const scSort = appState.scSort || { col: 'winners_seen', dir: 'desc' };

    let list = enriched;
    if (activeFilter === 'mismatch') {
      list = enriched.filter(r => r.mismatch.flag);
    } else if (activeFilter !== 'all') {
      list = enriched.filter(r => r.role === activeFilter);
    }

    const sorted = sortScorecardRows(list, scSort.col, scSort.dir, activeFilter);

    root.querySelectorAll('[data-sc-filter]').forEach(btn => {
      const on = btn.dataset.scFilter === activeFilter;
      btn.classList.toggle('active', on);
      btn.setAttribute('aria-pressed', on ? 'true' : 'false');
    });

    updateSortHeaders(root.querySelector('#scTable'), scSort.col, scSort.dir, 'scSort');

    lastScCsvSpec = {
      filename: `crate_digger_source_scorecard_${appState.dataEnd || 'export'}.csv`,
      headers: ['출처', '갈래', '현재 역할', '신호 수', '적중 / 후보', '적중률 (배수)', '수상 팀 포착', '가장 먼저 / 유일', '선행 개월'],
      rows: sorted.map(r => {
        const isPending = r.role === 'pending' && Number(r.teams) === 0;
        const roleLabel = ROLE_LABEL_KO[r.role] || r.role || '';
        if (isPending) {
          const sinceTxt = r.since_date ? `${String(r.since_date).slice(0, 10)}~` : '최근 수집 시작';
          return [r.label, r.branch || '', roleLabel, r.signal_rows ?? 0, `기록 쌓이는 중 (${sinceTxt})`, '', '', '', ''];
        }
        const teams = Number(r.teams) || 0;
        const hits = Number(r.hits) || 0;
        const rateTxt = r.rate !== null && r.rate !== undefined ? `${fmtNum(r.rate, 2)}%` : '—';
        const liftTxt = r.lift !== null && r.lift !== undefined ? `${fmtNum(r.lift, 1)}배` : '—';
        const leadTxt = r.median_lead_months !== null && r.median_lead_months !== undefined
          ? `${fmtNum(r.median_lead_months, 1)}개월`
          : '—';
        return [
          r.label,
          r.branch || '',
          roleLabel,
          r.signal_rows ?? 0,
          teams > 0 ? `${hits} / ${teams}팀` : '—',
          `${rateTxt} (${liftTxt})`,
          `${r.winners_seen ?? 0}팀`,
          `${r.first_to_see ?? 0} / ${r.only_source ?? 0}`,
          leadTxt,
        ];
      }),
    };

    setExportContext({
      csvLabel: `출처 성적표 CSV 내려받기 (${fmtInt(sorted.length)}곳)`,
      csvFilename: lastScCsvSpec.filename,
      csvHeaders: lastScCsvSpec.headers,
      csvRows: lastScCsvSpec.rows,
    });

    const tbody = root.querySelector('#scTbody');
    if (!sorted.length) {
      tbody.innerHTML = `<tr><td colspan="8" class="muted small" style="text-align:center;padding:18px;">해당 조건의 출처가 없습니다.</td></tr>`;
      return;
    }

    tbody.innerHTML = sorted.map(r => {
      const isPending = r.role === 'pending' && Number(r.teams) === 0;
      const isMuted = r.role === 'excluded' || r.role === 'pending';
      const hasDetail = Boolean(r.roleReason || r.reviewSuggestion);
      const isOpen = expandedSrc === r.src && hasDetail;
      const rowCls = [
        hasDetail ? 'clickable' : '',
        isMuted ? 'is-muted-row' : '',
        r.mismatch.flag ? 'is-mismatch-row' : '',
      ].filter(Boolean).join(' ');

      const flagHtml = r.mismatch.flag
        ? `<span class="reclassify-badge" title="${escapeHtml(r.mismatch.reason)}">재분류 검토</span>`
        : '';

      const expandBtnHtml = hasDetail
        ? `<button type="button" class="cand-expand-btn sc-reason-btn" data-sc-toggle="${escapeHtml(r.src)}" aria-expanded="${isOpen ? 'true' : 'false'}" aria-label="${escapeHtml(r.label)} 분류 사유 ${isOpen ? '접기' : '보기'}" title="${escapeHtml(r.roleReason || '분류 사유 보기')}">${isOpen ? '▾' : '▸'}</button>`
        : '<span class="sc-expand-spacer" aria-hidden="true"></span>';

      const detailRowHtml = isOpen
        ? `<tr class="sc-reason-row">
             <td colspan="8" class="sc-reason-cell">
               ${r.roleReason ? `<span class="sc-reason-item"><strong>분류 사유</strong> ${escapeHtml(r.roleReason)}</span>` : ''}
               ${r.reviewSuggestion ? `<span class="sc-reason-item sc-reason-sug"><strong>재분류 제안</strong> ${escapeHtml(r.reviewSuggestion.suggestion || '')}${r.reviewSuggestion.reason ? ` (${escapeHtml(r.reviewSuggestion.reason)})` : ''}</span>` : ''}
             </td>
           </tr>`
        : '';

      if (isPending) {
        const sinceTxt = r.since_date ? `${String(r.since_date).slice(0, 10)}~` : '최근 수집 시작';
        return `
          <tr class="${rowCls}" tabindex="0" data-nav-row="1" data-sc-src="${escapeHtml(r.src)}">
            <td>
              <div class="sc-src-cell">
                ${expandBtnHtml}
                <strong class="sc-src-name cell-truncate" title="${escapeHtml(r.label)}">${escapeHtml(r.label)}</strong>
                <span class="sc-branch-tag">${escapeHtml(r.branch)}</span>
                ${flagHtml}
              </div>
            </td>
            <td class="nowrap">${roleBadgeHtml(r.role, { title: r.roleReason })}</td>
            <td class="num">${fmtInt(r.signal_rows)}</td>
            <td colspan="5" class="sc-pending-cell">
              <span class="sc-pending-pill">기록 쌓이는 중 (${escapeHtml(sinceTxt)})</span>
            </td>
          </tr>
          ${detailRowHtml}
        `;
      }

      const teams = Number(r.teams) || 0;
      const hits = Number(r.hits) || 0;
      const rateStr = r.rate !== null && r.rate !== undefined ? `${fmtNum(r.rate, 2)}%` : '—';
      const liftVal = r.lift !== null && r.lift !== undefined ? Number(r.lift) : null;
      const liftStr = liftVal !== null ? `${fmtNum(liftVal, 1)}배` : '—';
      const liftCls = liftVal !== null ? (liftVal >= 1.5 ? 'sc-lift-high' : (liftVal < 1.0 ? 'sc-lift-low' : '')) : '';
      const leadStr = r.median_lead_months !== null && r.median_lead_months !== undefined
        ? `${fmtNum(r.median_lead_months, 1)}개월`
        : '—';
      const thinNote = teams > 0 && teams < 20 ? ' <span class="muted small">(표본 적음)</span>' : '';

      return `
        <tr class="${rowCls}" tabindex="0" data-nav-row="1" data-sc-src="${escapeHtml(r.src)}">
          <td>
            <div class="sc-src-cell">
              ${expandBtnHtml}
              <strong class="sc-src-name cell-truncate" title="${escapeHtml(r.label)}">${escapeHtml(r.label)}</strong>
              <span class="sc-branch-tag">${escapeHtml(r.branch)}</span>
              ${flagHtml}
            </div>
          </td>
          <td class="nowrap">${roleBadgeHtml(r.role, { title: r.roleReason })}</td>
          <td class="num">${fmtInt(r.signal_rows)}</td>
          <td class="num nowrap">${teams > 0 ? `${fmtInt(hits)} / ${fmtInt(teams)}팀${thinNote}` : '—'}</td>
          <td class="num nowrap"><span class="${liftCls}"><strong>${rateStr}</strong> <span class="muted">(${liftStr})</span></span></td>
          <td class="num nowrap"><strong>${fmtInt(r.winners_seen)}팀</strong></td>
          <td class="num nowrap">${fmtInt(r.first_to_see)} / ${fmtInt(r.only_source)}</td>
          <td class="num nowrap">${leadStr}</td>
        </tr>
        ${detailRowHtml}
      `;
    }).join('');

    if (focusSrc) {
      const targetRow = [...tbody.querySelectorAll('tr[data-sc-src]')].find(el => el.dataset.scSrc === focusSrc);
      if (targetRow) targetRow.focus({ preventScroll: true });
    }
  }

  root.querySelector('#btnScCsv')?.addEventListener('click', () => {
    if (lastScCsvSpec) triggerTableCsvExport(lastScCsvSpec);
  });

  root.querySelectorAll('[data-sc-filter]').forEach(btn => {
    btn.addEventListener('click', () => {
      appState.scFilter = btn.dataset.scFilter || 'all';
      syncHash(true);
      paint();
    });
  });

  root.querySelectorAll('th[data-sc-sort]').forEach(th => {
    th.setAttribute('tabindex', '0');
    const onSort = () => {
      const col = th.dataset.scSort;
      if (appState.scSort.col === col) {
        appState.scSort.dir = appState.scSort.dir === 'desc' ? 'asc' : 'desc';
      } else {
        appState.scSort.col = col;
        appState.scSort.dir = (col === 'label' || col === 'role') ? 'asc' : 'desc';
      }
      syncHash(true);
      paint();
    };
    th.addEventListener('click', onSort);
    th.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        onSort();
      }
    });
  });

  const tbodyEl = root.querySelector('#scTbody');
  const toggleSrcDetail = (src, keepFocus = false) => {
    const r = rowBySrc.get(src);
    if (!r || (!r.roleReason && !r.reviewSuggestion)) return;
    expandedSrc = (expandedSrc === src) ? null : src;
    paint(keepFocus ? src : null);
  };

  tbodyEl.addEventListener('click', (e) => {
    const toggleBtn = e.target.closest('[data-sc-toggle]');
    if (toggleBtn) {
      e.stopPropagation();
      toggleSrcDetail(toggleBtn.dataset.scToggle, false);
      return;
    }
    if (e.target.closest('button') || e.target.closest('a')) return;
    const tr = e.target.closest('tr[data-sc-src]');
    if (tr && tr.dataset.scSrc) toggleSrcDetail(tr.dataset.scSrc, false);
  });

  wireTableKeyboardNav(tbodyEl, {
    onActivate: (tr) => {
      if (tr.dataset.scSrc) toggleSrcDetail(tr.dataset.scSrc, true);
    },
    onToggleExpand: (tr, key) => {
      const src = tr.dataset.scSrc;
      if (!src) return;
      const r = rowBySrc.get(src);
      if (!r || (!r.roleReason && !r.reviewSuggestion)) return;
      if (key === 'ArrowLeft') {
        if (expandedSrc === src) {
          expandedSrc = null;
          paint(src);
        }
      } else if (expandedSrc !== src) {
        expandedSrc = src;
        paint(src);
      }
    },
  });

  wireTableRowHoverPreview(tbodyEl, (tr) => {
    const r = rowBySrc.get(tr.dataset.scSrc);
    if (!r) return '';
    const roleLabel = ROLE_LABEL_KO[r.role] || r.role || '—';
    const rateStr = r.rate !== null && r.rate !== undefined ? `${fmtNum(r.rate, 2)}%` : '—';
    const liftStr = r.lift !== null && r.lift !== undefined ? `${fmtNum(r.lift, 1)}배` : '—';
    const leadStr = r.median_lead_months !== null && r.median_lead_months !== undefined
      ? `${fmtNum(r.median_lead_months, 1)}개월`
      : '—';
    return `
      <div class="rhp-head">
        <strong>${escapeHtml(r.label)}</strong>
        <span class="rhp-score">${escapeHtml(roleLabel)}</span>
      </div>
      <div class="rhp-meta">${escapeHtml([r.branch || '', `신호 ${fmtInt(r.signal_rows)}건`, `적중률 ${rateStr} (${liftStr})`].filter(Boolean).join(' · '))}</div>
      <div class="rhp-lines">
        <div class="rhp-line"><span class="rhp-lbl">포착 실적</span>수상 ${fmtInt(r.winners_seen)}팀 · 최초 ${fmtInt(r.first_to_see)} · 선행 ${escapeHtml(leadStr)}</div>
        ${r.roleReason ? `<div class="rhp-line"><span class="rhp-lbl">분류 사유</span>${escapeHtml(r.roleReason)}</div>` : ''}
        ${r.reviewSuggestion ? `<div class="rhp-line"><span class="rhp-lbl">재분류 제안</span>${escapeHtml(r.reviewSuggestion.suggestion || '')}${r.reviewSuggestion.reason ? ` (${escapeHtml(r.reviewSuggestion.reason)})` : ''}</div>` : ''}
      </div>
      <div class="rhp-foot">${(r.roleReason || r.reviewSuggestion) ? '클릭 또는 Enter로 사유 펼치기 · ↑↓ 행 이동' : '↑↓ 키로 출처 행 이동'}</div>
    `;
  });

  paint();
}
