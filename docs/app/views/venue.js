import { appState, navigateTo, setExportContext } from '../state.js';
import { loadVenueProfiles, queryVenueRecentShows } from '../db.js';
import {
  avatarHtml, escapeHtml, fmtInt, fmtNum, formatKoreanShortDate, gradeBadgeHtml,
  INFO_TIPS, infoTip, renderActionBanner, renderTableCsvBtn, spotifyButtonHtml,
  triggerTableCsvExport, wireAvatarFallbacks, wireSpotifyButtons,
} from '../ui.js';

const TIER_META = {
  S: { label: '체급 S', title: '소형 클럽 · 소규모 무대' },
  M: { label: '체급 M', title: '중소형 공연장' },
  L: { label: '체급 L', title: '중대형 홀' },
  XL: { label: '체급 XL', title: '대형 홀·아레나' },
};

function renderTierBadge(tier) {
  const key = String(tier || '').trim().toUpperCase();
  if (!key) return '';
  const meta = TIER_META[key] || { label: `체급 ${key}`, title: `공연장 체급 ${key}` };
  return `<span class="venue-tier-badge is-tier-${escapeHtml(key.toLowerCase())}" title="${escapeHtml(meta.title)}">${escapeHtml(meta.label)}</span>`;
}

function buildMonthlyWindow(monthlyObj, anchorDate) {
  const entries = Object.entries(monthlyObj || {})
    .filter(([ym, cnt]) => /^\d{4}-\d{2}$/.test(ym) && Number(cnt) > 0)
    .sort((a, b) => a[0].localeCompare(b[0]));

  const fallbackYm = /^\d{4}-\d{2}/.test(String(anchorDate || ''))
    ? String(anchorDate).slice(0, 7)
    : '2026-11';
  const latestDataYm = entries.length ? entries[entries.length - 1][0] : fallbackYm;

  const makeMonths = (endYmStr) => {
    const [ey, em] = endYmStr.split('-').map(Number);
    const out = [];
    for (let i = 11; i >= 0; i--) {
      const d = new Date(Date.UTC(ey, em - 1 - i, 1));
      const y = d.getUTCFullYear();
      const m = d.getUTCMonth() + 1;
      const ym = `${y}-${String(m).padStart(2, '0')}`;
      out.push({
        ym,
        shortLabel: (i === 11 || m === 1) ? `${String(y).slice(2)}.${m}` : `${m}`,
        count: Number(monthlyObj?.[ym] || 0),
      });
    }
    return out;
  };

  let months = makeMonths(fallbackYm);
  const sumDefault = months.reduce((acc, m) => acc + m.count, 0);
  if (sumDefault === 0 && entries.length && latestDataYm !== fallbackYm) {
    months = makeMonths(latestDataYm);
  }
  const maxCount = Math.max(1, ...months.map(m => m.count));
  const totalInWindow = months.reduce((acc, m) => acc + m.count, 0);
  return {
    months,
    maxCount,
    totalInWindow,
    rangeLabel: `${months[0].ym} ~ ${months[months.length - 1].ym}`,
  };
}

function renderVenueMonthlyBarsHtml(monthlyObj, anchorDate, noteText = '') {
  const { months, maxCount, totalInWindow, rangeLabel } = buildMonthlyWindow(monthlyObj, anchorDate);
  return `
    <div class="venue-monthly-wrap">
      <div class="venue-card-head">
        <h2>월별 공연 날짜</h2>
        <span class="block-meta">${escapeHtml(rangeLabel)} · ${fmtInt(totalInWindow)}일</span>
      </div>
      ${totalInWindow > 0 ? `
        <div class="monthly-bars-grid venue-monthly-grid" role="img" aria-label="월별 공연 날짜 막대 그래프">
          ${months.map(m => {
            const pct = m.count > 0 ? Math.max(10, Math.round((m.count / maxCount) * 100)) : 0;
            const tip = m.count > 0 ? `${m.ym}: ${m.count}일 공연` : `${m.ym}: 기록 없음`;
            return `
              <div class="monthly-bar-col" title="${escapeHtml(tip)}">
                <span class="monthly-bar-cnt">${m.count > 0 ? fmtInt(m.count) : ''}</span>
                <div class="monthly-bar-track">
                  ${m.count > 0
                    ? `<div class="venue-monthly-fill" style="height:${pct}%"></div>`
                    : '<div class="monthly-bar-zero"></div>'}
                </div>
                <span class="monthly-bar-lbl">${escapeHtml(m.shortLabel)}</span>
              </div>
            `;
          }).join('')}
        </div>
      ` : '<p class="muted small" style="margin:8px 0 0 0;">월별 공연 날짜 기록이 아직 없습니다.</p>'}
      ${noteText ? `<p class="venue-card-note">${escapeHtml(noteText)}</p>` : ''}
    </div>
  `;
}

function renderFirstTimerCardHtml(profile, noteText = '') {
  const teams1y = Number(profile.teams_1y || 0);
  const firstTimers = Number(profile.first_timers_1y || 0);
  const share = (profile.first_timer_share_1y !== null && profile.first_timer_share_1y !== undefined)
    ? Number(profile.first_timer_share_1y)
    : null;
  const pctNum = share !== null && Number.isFinite(share) ? Math.max(0, Math.min(100, share * 100)) : null;

  let badgeCls = 'is-neutral';
  let badgeTxt = '기록 없음';
  let descTxt = '최근 1년 출연 팀이 없어 첫 출연 비율을 계산하지 않았습니다.';

  if (pctNum !== null && teams1y > 0) {
    if (pctNum >= 40) {
      badgeCls = 'is-high';
      badgeTxt = '신인 첫 무대 비중 높음';
      descTxt = '데이터상 처음 포착된 무대가 이 공연장인 팀이 많습니다. 극초기 신인을 가장 먼저 만날 수 있는 등용문 성격의 무대입니다.';
    } else if (pctNum >= 20) {
      badgeCls = 'is-mid';
      badgeTxt = '신인·기성 혼합 무대';
      descTxt = '처음 무대에 오르는 신인과 이미 다른 무대를 거친 팀이 고르게 섞여 출연하는 공연장입니다.';
    } else {
      badgeCls = 'is-low';
      badgeTxt = '경험 팀 중심 무대';
      descTxt = '대부분 다른 공연장에서 활동한 뒤 오르는 무대입니다. 신인의 첫 데뷔보다는 다음 단계로 올라서는 구간에 가깝습니다.';
    }
  }

  return `
    <div class="venue-first-timer-wrap">
      <div class="venue-card-head">
        <h2>첫 출연 비율${infoTip('첫 출연 비율', INFO_TIPS.first_timer_share)}</h2>
        <span class="venue-stage-tag ${badgeCls}">${escapeHtml(badgeTxt)}</span>
      </div>
      ${pctNum !== null && teams1y > 0 ? `
        <div class="venue-share-readout">
          <strong class="venue-share-pct mono">${pctNum.toFixed(0)}%</strong>
          <span class="venue-share-sub">최근 1년 출연 ${fmtInt(teams1y)}팀 중 <strong>${fmtInt(firstTimers)}팀</strong>의 첫 공연</span>
        </div>
        <div class="venue-share-bar" role="img" aria-label="첫 출연 비율 ${pctNum.toFixed(0)}%">
          <div class="venue-share-fill ${badgeCls}" style="width:${pctNum.toFixed(1)}%"></div>
        </div>
      ` : ''}
      <p class="venue-share-desc">${escapeHtml(descTxt)}</p>
      ${noteText ? `<p class="venue-card-note">${escapeHtml(noteText)}</p>` : ''}
    </div>
  `;
}

function renderFlowColumnHtml(title, rows, emptyText) {
  const list = Array.isArray(rows) ? rows.filter(r => Array.isArray(r) && r[0]) : [];
  const maxCnt = Math.max(1, ...list.map(r => Number(r[1]) || 0));
  return `
    <div class="venue-flow-col">
      <h3 class="venue-flow-head">${escapeHtml(title)}</h3>
      ${list.length ? `
        <ul class="venue-flow-list">
          ${list.map(([vName, cnt]) => {
            const c = Number(cnt) || 0;
            const pct = Math.max(8, Math.round((c / maxCnt) * 100));
            return `
              <li>
                <a class="venue-flow-link" href="#/venue/${encodeURIComponent(String(vName))}">
                  <span class="venue-flow-name">${escapeHtml(String(vName))}</span>
                  <span class="venue-flow-bar-wrap" aria-hidden="true">
                    <span class="venue-flow-bar" style="width:${pct}%"></span>
                  </span>
                  <span class="venue-flow-cnt mono">${fmtInt(c)}팀</span>
                </a>
              </li>
            `;
          }).join('')}
        </ul>
      ` : `<p class="muted small" style="margin:0;">${escapeHtml(emptyText)}</p>`}
    </div>
  `;
}

function groupRecentShows(rows, asOf) {
  const byDate = new Map();
  for (const r of rows) {
    if (!byDate.has(r.signal_date)) {
      byDate.set(r.signal_date, {
        date: r.signal_date,
        isUpcoming: Boolean(asOf && r.signal_date > asOf),
        teams: [],
      });
    }
    byDate.get(r.signal_date).teams.push(r);
  }
  return [...byDate.values()].sort((a, b) => b.date.localeCompare(a.date));
}

export async function renderVenueView(root, venueName) {
  const cleanVenue = String(venueName || '').trim();
  if (!cleanVenue) {
    root.innerHTML = renderActionBanner({
      title: '공연장 상세',
      lead: '선택된 공연장이 없습니다.',
      todo: '공연장·씬 화면에서 공연장을 선택하면 체급·수상 선례·전후 흐름·최근 공연 목록을 볼 수 있습니다.',
      buttonsHtml: '<a class="btn" href="#/venues">공연장·씬으로</a>',
    });
    return;
  }

  const asOf = appState.cfg.as_of || appState.dataEnd || '2026-11-27';
  const [profilesData, recentShowRows] = await Promise.all([
    loadVenueProfiles(),
    queryVenueRecentShows(cleanVenue, 300).catch(() => []),
  ]);

  const effectiveAsOf = profilesData?.as_of || asOf;
  const hasProfilesFile = Boolean(profilesData && profilesData.venues);
  const profile = hasProfilesFile ? (profilesData.venues[cleanVenue] || null) : null;
  const notes = profilesData?.notes || {};
  const showGroups = groupRecentShows(recentShowRows, effectiveAsOf);

  const backLabels = {
    venues: '공연장·씬',
    team: '팀 상세',
    today: '이번 주 브리핑',
    candidates: '후보 목록',
    watchlist: '관심 목록',
  };
  const backRoute = appState.prevRoute && backLabels[appState.prevRoute] ? appState.prevRoute : 'venues';
  const backParam = backRoute === 'team' ? (appState.prevParam || '') : '';
  const backLabel = backLabels[backRoute] || '공연장·씬';

  const showsCsvSpec = showGroups.length ? {
    filename: `crate_digger_venue_${cleanVenue.replace(/[^a-zA-Z0-9가-힣_-]+/g, '_')}_${effectiveAsOf}.csv`,
    headers: ['공연 날짜', '구분', '출연 팀 수', '라인업'],
    rows: showGroups.map(g => [
      g.date,
      g.isUpcoming ? '예정' : '진행',
      g.teams.length,
      g.teams.map(t => t.display_name).join(' / '),
    ]),
  } : null;

  setExportContext({
    csvLabel: showsCsvSpec ? `${cleanVenue} 최근 공연 CSV 내려받기 (${fmtInt(showGroups.length)}일)` : '',
    csvFilename: showsCsvSpec?.filename || '',
    csvHeaders: showsCsvSpec?.headers || [],
    csvRows: showsCsvSpec?.rows || [],
  });

  let showLimit = 15;
  let showAllWinners = false;

  function renderRecentShowsInner() {
    const visible = showGroups.slice(0, showLimit);
    const remaining = showGroups.length - visible.length;
    return `
      <div class="block-head">
        <div>
          <h2>최근 공연 목록</h2>
          <span class="block-meta">수집된 공연 날짜 ${fmtInt(showGroups.length)}일 · 팀 이름을 누르면 팀 상세로 이동합니다</span>
        </div>
        ${showsCsvSpec ? `<div class="block-head-actions">${renderTableCsvBtn('btnVenueShowsCsv', 'CSV 내려받기')}</div>` : ''}
      </div>
      ${visible.length ? `
        <ul class="venue-shows-list">
          ${visible.map(g => `
            <li class="venue-show-row ${g.isUpcoming ? 'is-upcoming' : ''}">
              <div class="venue-show-date-col">
                <strong class="venue-show-date">${escapeHtml(formatKoreanShortDate(g.date))}</strong>
                <span class="small muted mono">${escapeHtml(g.date)}</span>
                ${g.isUpcoming ? '<span class="venue-upcoming-pill">예정</span>' : ''}
              </div>
              <div class="venue-show-lineup">
                ${g.teams.map(t => `
                  <a class="venue-show-team" href="#/team/${encodeURIComponent(t.team_key)}">
                    ${avatarHtml(t.team_key, t.display_name, 22, { shape: 'circle', genre: t.primary_genre })}
                    <span>${escapeHtml(t.display_name)}</span>
                  </a>
                `).join('')}
              </div>
            </li>
          `).join('')}
        </ul>
        ${remaining > 0
          ? `<div class="more-row" style="margin-top:10px;">
               <span>최근 ${fmtInt(visible.length)} / ${fmtInt(showGroups.length)}일</span>
               <button type="button" class="btn btn-sm" id="btnMoreVenueShows">${fmtInt(Math.min(20, remaining))}일 더 보기</button>
             </div>`
          : (showLimit > 15 && showGroups.length > 15
              ? `<div class="more-row" style="margin-top:10px;">
                   <span>전체 ${fmtInt(showGroups.length)}일 표시 중</span>
                   <button type="button" class="btn btn-sm" id="btnLessVenueShows">접기</button>
                 </div>`
              : '')}
      ` : '<p class="muted small" style="margin:0;">현재 데이터에 이 공연장의 공연 기록이 없습니다.</p>'}
    `;
  }

  function renderWinnersInner() {
    const winners = Array.isArray(profile?.later_winners) ? profile.later_winners : [];
    const total = Number(profile?.later_winners_total ?? winners.length);
    const visible = showAllWinners ? winners : winners.slice(0, 10);
    const remaining = winners.length - visible.length;
    return `
      <div class="block-head">
        <div>
          <h2>여기 섰다가 나중에 상 받은 팀</h2>
          <span class="block-meta">${escapeHtml(notes.later_winners || '센 정답 첫 발표일보다 먼저 이 공연장에 선 팀')}</span>
        </div>
        <span class="badge-new">총 ${fmtInt(total)}팀</span>
      </div>
      ${visible.length ? `
        <div class="table-wrap">
          <table class="data-table venue-winners-table">
            <thead>
              <tr>
                <th>팀</th>
                <th>첫 수상·선정</th>
                <th class="nowrap">이곳 첫 무대</th>
                <th class="num nowrap">선행 개월</th>
              </tr>
            </thead>
            <tbody>
              ${visible.map(w => {
                const leadTxt = (w.lead_months !== null && w.lead_months !== undefined)
                  ? `${fmtInt(w.lead_months)}개월`
                  : '—';
                return `
                  <tr>
                    <td>
                      <a class="row-team-cell" href="#/team/${encodeURIComponent(w.team_key)}">
                        ${avatarHtml(w.team_key, w.name || w.team_key, 24, { shape: 'circle' })}
                        <strong>${escapeHtml(w.name || w.team_key)}</strong>
                      </a>
                    </td>
                    <td>
                      <div class="venue-winner-outcome">
                        ${w.grade ? gradeBadgeHtml(w.grade) : ''}
                        <span>${escapeHtml(w.outcome || '-')}</span>
                        ${w.outcome_date ? `<span class="small muted mono">${escapeHtml(w.outcome_date)}</span>` : ''}
                      </div>
                    </td>
                    <td class="nowrap mono muted">${escapeHtml(w.first_here || '-')}</td>
                    <td class="num nowrap"><span class="venue-lead-pill">선행 ${escapeHtml(leadTxt)}</span></td>
                  </tr>
                `;
              }).join('')}
            </tbody>
          </table>
        </div>
        ${remaining > 0
          ? `<div class="more-row" style="margin-top:8px;">
               <span>${fmtInt(visible.length)} / ${fmtInt(winners.length)}팀 표시${total > winners.length ? ` (전체 ${fmtInt(total)}팀 중 최근·상위)` : ''}</span>
               <button type="button" class="btn btn-sm" id="btnMoreVenueWinners">${fmtInt(remaining)}팀 더 보기</button>
             </div>`
          : (total > winners.length
              ? `<p class="small muted" style="margin:8px 0 0 0;">전체 ${fmtInt(total)}팀 중 주요 ${fmtInt(winners.length)}팀을 표시합니다.</p>`
              : '')}
      ` : '<p class="muted small" style="margin:0;">이 공연장을 거친 뒤 주요 수상·선정에 오른 기록이 아직 없습니다.</p>'}
    `;
  }

  function renderTopCandidatesInner() {
    const cands = Array.isArray(profile?.top_candidates) ? profile.top_candidates : [];
    return `
      <div class="block-head">
        <div>
          <h2>지금 후보 상위 팀</h2>
          <span class="block-meta">${escapeHtml(notes.top_candidates || '최근 3년 이 공연장에 선 팀 중 최신 점수 순위 상위')}</span>
        </div>
        <span class="block-meta">${fmtInt(cands.length)}팀</span>
      </div>
      ${cands.length ? `
        <ul class="venue-cand-profile-list">
          ${cands.map(c => `
            <li class="venue-cand-profile-row">
              <a class="row-team-cell venue-cand-main" href="#/team/${encodeURIComponent(c.team_key)}">
                ${c.rank ? `<span class="rank-pill">#${fmtInt(c.rank)}</span>` : ''}
                ${avatarHtml(c.team_key, c.name || c.team_key, 26, { shape: 'circle' })}
                <div class="row-team-text">
                  <div class="row-team-name">
                    <strong>${escapeHtml(c.name || c.team_key)}</strong>
                    ${c.score !== null && c.score !== undefined ? `<span class="small muted mono">${fmtNum(c.score, 1)}점</span>` : ''}
                  </div>
                  ${c.last_here ? `<div class="small muted mono">마지막 출연 ${escapeHtml(c.last_here)}</div>` : ''}
                </div>
              </a>
              <div class="venue-cand-right">
                ${spotifyButtonHtml(c.team_key, true, { iconOnly: true, teamName: c.name || c.team_key, slotId: 'venueCandPlayerSlot' })}
              </div>
            </li>
          `).join('')}
        </ul>
        <div class="player-slot" id="venueCandPlayerSlot" data-player-slot></div>
      ` : '<p class="muted small" style="margin:0;">최근 3년 이 공연장에 선 현재 후보 순위권 팀이 없습니다.</p>'}
    `;
  }

  // Build Hero & Body depending on profile availability
  let mainSectionsHtml = '';
  if (!profile) {
    const noticeTitle = hasProfilesFile ? '공연장 프로필 미집계' : '공연장 프로필 준비 중';
    const noticeDesc = hasProfilesFile
      ? `기준일(${effectiveAsOf})까지 집계된 프로필 목록에 '${cleanVenue}' 항목이 아직 없습니다.`
      : '공연장 체급·수용 인원·월별 공연 추이·첫 출연 비율·수상 선례·전후 이동 흐름 데이터를 준비 중입니다. 집계 파일이 생성되면 이 화면에 자동으로 표시됩니다.';
    mainSectionsHtml = `
      <section class="action-banner venue-hero">
        <div class="venue-hero-top">
          <div class="venue-hero-title-row">
            <h1>${escapeHtml(cleanVenue)}</h1>
            <span class="venue-prep-pill">준비 중</span>
          </div>
          ${showGroups.length
            ? `<p class="action-lead">수집된 공연 날짜 <strong>${fmtInt(showGroups.length)}일</strong> · 마지막 기록 ${escapeHtml(showGroups[0].date)}</p>`
            : '<p class="action-lead">공연장 상세 프로필이 아직 준비되지 않았습니다.</p>'}
        </div>
      </section>

      <section class="block venue-prep-card" aria-label="공연장 프로필 준비 중 안내">
        <div class="venue-prep-body">
          <strong>${escapeHtml(noticeTitle)}</strong>
          <p class="small muted" style="margin:4px 0 0 0;">${escapeHtml(noticeDesc)}</p>
        </div>
      </section>

      <section class="block" id="venueRecentShowsBlock"></section>
    `;
  } else {
    const metaParts = [];
    if (profile.capacity !== null && profile.capacity !== undefined && Number(profile.capacity) > 0) {
      metaParts.push(`수용 약 ${fmtInt(profile.capacity)}명`);
    }
    const cityStr = String(profile.city || '').trim();
    if (cityStr) {
      metaParts.push(cityStr);
    }
    if (profile.first_night || profile.last_night) {
      const range = profile.first_night && profile.last_night
        ? `${profile.first_night} ~ ${profile.last_night}`
        : (profile.first_night || profile.last_night);
      metaParts.push(`공연 기간 ${range}`);
    }
    metaParts.push(`누적 ${fmtInt(profile.nights || 0)}일`);

    const sharePct = (profile.first_timer_share_1y !== null && profile.first_timer_share_1y !== undefined)
      ? `${(Number(profile.first_timer_share_1y) * 100).toFixed(0)}%`
      : '—';

    mainSectionsHtml = `
      <section class="action-banner venue-hero">
        <div class="venue-hero-top">
          <div class="venue-hero-title-row">
            <h1>${escapeHtml(cleanVenue)}</h1>
            ${renderTierBadge(profile.tier)}
            ${Number(profile.upcoming_nights || 0) > 0
              ? `<span class="venue-upcoming-pill">예정 ${fmtInt(profile.upcoming_nights)}일</span>`
              : ''}
          </div>
          <p class="venue-hero-meta">${escapeHtml(metaParts.join(' · '))}</p>
        </div>

        <div class="venue-kpi-strip">
          <div class="venue-kpi-card">
            <span class="venue-kpi-lbl">공연 날짜</span>
            <strong class="venue-kpi-val mono">${fmtInt(profile.nights || 0)}일</strong>
            <span class="venue-kpi-sub">${Number(profile.upcoming_nights || 0) > 0 ? `예정 ${fmtInt(profile.upcoming_nights)}일` : `기준 ${escapeHtml(effectiveAsOf)}`}</span>
          </div>
          <div class="venue-kpi-card">
            <span class="venue-kpi-lbl">최근 1년 출연</span>
            <strong class="venue-kpi-val mono">${fmtInt(profile.teams_1y || 0)}팀</strong>
            <span class="venue-kpi-sub">첫 출연 ${fmtInt(profile.first_timers_1y || 0)}팀</span>
          </div>
          <div class="venue-kpi-card">
            <span class="venue-kpi-lbl">첫 출연 비율</span>
            <strong class="venue-kpi-val mono">${escapeHtml(sharePct)}</strong>
            <span class="venue-kpi-sub">데이터상 첫 무대</span>
          </div>
          <div class="venue-kpi-card">
            <span class="venue-kpi-lbl">나중에 상 받은 팀</span>
            <strong class="venue-kpi-val mono">${fmtInt(profile.later_winners_total || 0)}팀</strong>
            <span class="venue-kpi-sub">수상 전 이곳 거쳐감</span>
          </div>
        </div>
      </section>

      <div class="venue-overview-grid">
        <section class="block venue-overview-card">
          ${renderVenueMonthlyBarsHtml(profile.monthly, effectiveAsOf, notes.nights || '')}
        </section>
        <section class="block venue-overview-card">
          ${renderFirstTimerCardHtml(profile, notes.first_timers_1y || '')}
        </section>
      </div>

      <section class="block" id="venueFlowBlock">
        <div class="block-head">
          <div>
            <h2>전후 공연장 흐름</h2>
            <span class="block-meta">${escapeHtml(notes.before_after || '이 공연장에 처음 선 팀들이 전후 1년에 거친 곳 (공연장 이름을 누르면 이동)')}</span>
          </div>
        </div>
        <div class="venue-flow-grid">
          ${renderFlowColumnHtml('이곳 전에 많이 선 곳', profile.before, '이전 1년 사이 함께 집계된 선행 공연장이 없습니다.')}
          ${renderFlowColumnHtml('이곳 뒤에 많이 선 곳', profile.after, '이후 1년 사이 함께 집계된 다음 공연장이 없습니다.')}
        </div>
      </section>

      <div class="venue-roster-grid">
        <section class="block" id="venueWinnersBlock"></section>
        <section class="block" id="venueCandidatesBlock">${renderTopCandidatesInner()}</section>
      </div>

      <section class="block" id="venueRecentShowsBlock"></section>
    `;
  }

  root.innerHTML = `
    <div class="team-topbar">
      <button type="button" class="btn btn-sm" id="btnVenueBack">← ${escapeHtml(backLabel)}</button>
      <span class="small muted">기준일 ${escapeHtml(effectiveAsOf)}</span>
    </div>
    ${mainSectionsHtml}
  `;

  function paintWinners() {
    const el = root.querySelector('#venueWinnersBlock');
    if (!el || !profile) return;
    el.innerHTML = renderWinnersInner();
    wireAvatarFallbacks(el);
    el.querySelector('#btnMoreVenueWinners')?.addEventListener('click', () => {
      showAllWinners = true;
      paintWinners();
    });
  }

  function paintRecentShows() {
    const el = root.querySelector('#venueRecentShowsBlock');
    if (!el) return;
    el.innerHTML = renderRecentShowsInner();
    wireAvatarFallbacks(el);
    el.querySelector('#btnVenueShowsCsv')?.addEventListener('click', () => {
      if (showsCsvSpec) triggerTableCsvExport(showsCsvSpec);
    });
    el.querySelector('#btnMoreVenueShows')?.addEventListener('click', () => {
      showLimit += 20;
      paintRecentShows();
    });
    el.querySelector('#btnLessVenueShows')?.addEventListener('click', () => {
      showLimit = 15;
      paintRecentShows();
    });
  }

  paintWinners();
  paintRecentShows();
  wireAvatarFallbacks(root);
  wireSpotifyButtons(root, '#venueCandPlayerSlot');

  root.querySelector('#btnVenueBack')?.addEventListener('click', () => {
    navigateTo(backRoute, backParam);
  });
}
