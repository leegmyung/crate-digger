import { appState, navigateTo, setExportContext, VENUE_TABS } from '../state.js';
import {
  loadAlertsJson, loadVenueProfiles, queryCandidates, queryDiscoveryStages, queryVenueRecentShows,
} from '../db.js';
import { loadVenueLadder, queryVenueTeams } from '../db_venue.js';
import { buildVenueFlow } from '../components/venue_flow.js';
import { mountVenueTables } from './venue_tables.js';
import { alertsForSubscribedVenues, isVenueSubscribed, toggleVenueSub } from '../venue_subs.js';
import { venueSubForecastText } from '../insight_text.js';
import { confidenceLabel, venueStatusBadge, venueTypeLabel } from '../components/venue_info.js';
import {
  avatarHtml, escapeHtml, fmtInt, fmtNum, gradeBadgeHtml,
  INFO_TIPS, infoTip, renderActionBanner, spotifyButtonHtml,
  wireAvatarFallbacks, wireSpotifyButtons,
  routeBackLabel,
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

// 탭을 옮겨도(주소가 바뀌어 화면을 다시 그려도) 같은 질의를 다시 돌리지 않게
const venueTeamsCache = new Map();
function cachedVenueTeams(venue, asOf) {
  const key = `${venue}|${asOf}`;
  if (!venueTeamsCache.has(key)) {
    venueTeamsCache.set(key, queryVenueTeams(venue, asOf));
    if (venueTeamsCache.size > 12) venueTeamsCache.delete(venueTeamsCache.keys().next().value);
  }
  return venueTeamsCache.get(key);
}

export async function renderVenueView(root, venueName) {
  const cleanVenue = String(venueName || '').trim();
  if (!cleanVenue) {
    root.innerHTML = renderActionBanner({
      title: '공연장 상세',
      lead: '선택된 공연장이 없습니다.',
      todo: '공연장 목록에서 공연장을 고르면 체급·출연 팀·공연·전후 흐름을 탭으로 볼 수 있습니다.',
      buttonsHtml: '<a class="btn" href="#/venues">공연장 목록으로</a>',
    });
    return;
  }

  const asOf = appState.cfg.as_of || appState.dataEnd || '2026-11-27';
  const [profilesData, recentShowRows, ladder, venueTeams, candRows, stageData] = await Promise.all([
    loadVenueProfiles(),
    queryVenueRecentShows(cleanVenue, 1000).catch(() => []),
    loadVenueLadder(),
    cachedVenueTeams(cleanVenue, asOf),
    queryCandidates({ limit: 300 }).catch(() => []),
    queryDiscoveryStages({ as_of: asOf }).catch(() => null),
  ]);

  const effectiveAsOf = profilesData?.as_of || asOf;
  const hasProfilesFile = Boolean(profilesData && profilesData.venues);
  const profile = hasProfilesFile ? (profilesData.venues[cleanVenue] || null) : null;
  const notes = profilesData?.notes || {};
  const showGroups = groupRecentShows(recentShowRows, effectiveAsOf);

  // 이전 화면 이름(메뉴 이름) — 모르면 공연장 목록
  const backRoute = appState.prevRoute && routeBackLabel(appState.prevRoute) && appState.prevRoute !== 'venue' ? appState.prevRoute : 'venues';
  const backParam = backRoute === 'team' ? (appState.prevParam || '') : '';
  const backLabel = routeBackLabel(backRoute) || '공연장';

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

  let showAllWinners = false;

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

  // 4-1 머리 상자 보탬: 발굴 주목도 · 좌표 · 구독(5-5) · '정보가 틀려요'
  const reportUrl = 'https://github.com/leegmyung/crate-digger/issues/new?template=venue.yml'
    + `&title=${encodeURIComponent(`[공연장 정보] ${cleanVenue}`)}`
    + `&venue=${encodeURIComponent(cleanVenue)}`
    + `&page=${encodeURIComponent(window.location.href)}`;
  const subOn = isVenueSubscribed(cleanVenue);
  const actionsHtml = `
    <div class="venue-hero-actions">
      <button type="button" class="btn btn-sm${subOn ? ' btn-active' : ''}" id="btnVenueSub" aria-pressed="${subOn}" title="여기 처음 선 신인·큰 공연장 첫 무대·새 공연을 내 목록과 홈에서 알려 줍니다">${subOn ? '★ 구독 중' : '☆ 이 공연장 구독'}</button>
      <span class="small muted venue-sub-preview" id="venueSubPreview" aria-live="polite"></span>
      <a class="team-report-link" href="${escapeHtml(reportUrl)}" target="_blank" rel="noopener noreferrer" title="공개 저장소 이슈로 접수돼요 — 개인 연락처는 적지 마세요">정보가 틀려요 ↗</a>
    </div>`;
  const disc = profile?.discovery || null;
  const discoveryKpiHtml = `
    <div class="venue-kpi-card">
      <span class="venue-kpi-lbl">발굴 주목도${infoTip('발굴 주목도', INFO_TIPS.venue_discovery, { compact: true })}</span>
      <strong class="venue-kpi-val mono">${disc && disc.score !== null && disc.score !== undefined ? fmtNum(disc.score, 1) : '—'}</strong>
      <span class="venue-kpi-sub">${disc ? `0~100 · 최근 12개월 ${fmtInt(disc.nights_12m || 0)}일` : '최근 12개월 공연 없음'}</span>
    </div>`;
  const geoLine = (profile && profile.lat !== null && profile.lat !== undefined && profile.lon !== null && profile.lon !== undefined)
    ? `<a class="venue-geo-link" href="https://www.openstreetmap.org/?mlat=${Number(profile.lat)}&mlon=${Number(profile.lon)}#map=17/${Number(profile.lat)}/${Number(profile.lon)}" target="_blank" rel="noopener noreferrer">지도에서 보기 ↗</a> <span class="small muted">좌표 확실도 ${escapeHtml({ high: '높음(건물)', medium: '보통(도로)', low: '낮음(이름 검색)' }[profile.geo_confidence] || profile.geo_confidence || '모름')}</span>`
    : '<span class="small muted">좌표 없음</span>';

  // 수용 인원 출처·확인일·확실도 · 한/영 별칭 · '묶지 않음' 근거 (venue_profiles.json, config/venue_capacity·venues_kr·venue_aliases)
  const capSrc = String(profile?.capacity_source || '');
  const capConf = confidenceLabel(profile?.capacity_confidence);
  const capacityLineHtml = profile && Number(profile.capacity) > 0 ? `
    <p class="venue-hero-cap">수용 약 <strong>${fmtInt(profile.capacity)}명</strong>
      <span class="small muted">(${[
    capSrc ? (/^https?:\/\//.test(capSrc) ? `<a href="${escapeHtml(capSrc)}" target="_blank" rel="noopener noreferrer" title="${escapeHtml(profile.capacity_note || '')}">출처 ↗</a>` : escapeHtml(capSrc)) : '출처 미기록',
    capConf ? `확실도 ${escapeHtml(capConf)}` : '',
    profile.capacity_checked ? `확인 ${escapeHtml(profile.capacity_checked)}` : '',
  ].filter(Boolean).join(' · ')})</span></p>` : (profile ? '<p class="venue-hero-cap small muted">수용 인원 미확인</p>' : '');
  const aliases = Array.isArray(profile?.aliases) ? profile.aliases : [];
  const aliasLineHtml = aliases.length ? `<p class="venue-hero-alias small muted">다른 표기: ${aliases.map(a => escapeHtml(a)).join(' · ')}</p>` : '';
  const notMerged = Array.isArray(profile?.not_merged) ? profile.not_merged : [];
  const basisFoldHtml = profile && (profile.type_basis || aliases.length || notMerged.length || profile.capacity_note) ? `
    <details class="info-fold venue-basis-fold">
      <summary>ⓘ 종류·표기·수용 인원 근거</summary>
      <div class="info-fold-body small">
        ${profile.type_basis ? `<p><strong>종류</strong> ${escapeHtml(venueTypeLabel(profile))} — ${escapeHtml(profile.type_basis)}</p>` : '<p><strong>종류</strong> 유형 미정 (마스터 목록에 종류가 비어 있음)</p>'}
        ${aliases.length ? `<p><strong>한 곳으로 묶은 표기</strong> ${aliases.map(a => escapeHtml(a)).join(' · ')}</p>` : ''}
        ${notMerged.map(n => `<p><strong>묶지 않음</strong> ${escapeHtml((n.names || []).join(' / '))} — ${escapeHtml(n.reason || '')}</p>`).join('')}
        ${profile.capacity_note ? `<p><strong>수용 인원</strong> ${escapeHtml(profile.capacity_note)}</p>` : ''}
      </div>
    </details>` : '';

  // 4-3 전후 흐름 그림 (가로축 체급, 표본 작으면 문장)
  const tierOf = new Map(Object.entries(profilesData?.venues || {}).map(([n, v]) => [n, String(v?.tier || '').toUpperCase()]));
  const ladderVenue = ladder?.venues?.[cleanVenue] || null;
  const flow = profile ? buildVenueFlow({
    venue: cleanVenue,
    tier: String(profile.tier || '').toUpperCase(),
    before: profile.before || ladderVenue?.before || [],
    after: profile.after || ladderVenue?.after || [],
    sample: ladderVenue ? Number(ladderVenue.teams) : null,
    tierOf,
  }) : null;

  // ---------- 정보 구조 v2 묶음 D: 고정 머리 + 탭 4개(개요·출연 팀·공연·흐름) + 근거 줄 ----------
  const tab = VENUE_TABS.includes(appState.venueTab) ? appState.venueTab : 'overview';
  const tabHref = t => `#/venue/${encodeURIComponent(cleanVenue)}${t === 'overview' ? '' : `/${t}`}`;
  const TAB_LABELS = { overview: '개요', teams: `출연 팀 ${fmtInt(venueTeams.length)}`, gigs: '공연', flow: '흐름' };
  const tabsHtml = `
    <nav class="venue-tabs" aria-label="공연장 탭">
      ${VENUE_TABS.map(t => `<a class="venue-tab${t === tab ? ' is-active' : ''}" href="${tabHref(t)}"${t === tab ? ' aria-current="page"' : ''}>${TAB_LABELS[t]}</a>`).join('')}
    </nav>`;

  const sharePct = (profile?.first_timer_share_1y !== null && profile?.first_timer_share_1y !== undefined)
    ? `${Math.round(Number(profile.first_timer_share_1y) * 100)}%` : '—';
  const nights12 = profile?.discovery?.nights_12m;
  const metaParts = [];
  if (profile?.city) metaParts.push(String(profile.city));
  if (profile?.first_night && profile?.last_night) metaParts.push(`공연 기록 ${profile.first_night} ~ ${profile.last_night}`);
  if (profile) metaParts.push(`누적 ${fmtInt(profile.nights || 0)}일`);

  const headHtml = `
    <div class="venue-sticky">
      <div class="venue-sticky-row">
        <h1 class="venue-name">${escapeHtml(cleanVenue)}</h1>
        ${profile ? renderTierBadge(profile.tier) : '<span class="venue-prep-pill">프로필 준비 중</span>'}
        ${profile ? `<span class="venue-type-chip${profile.type ? '' : ' is-unknown'}" title="${escapeHtml(profile.type_basis || '종류 근거 없음')}">${escapeHtml(venueTypeLabel(profile))}</span>` : ''}
        ${profile ? venueStatusBadge(profile, escapeHtml) : ''}
        ${Number(profile?.upcoming_nights || 0) > 0 ? `<span class="venue-upcoming-pill">예정 ${fmtInt(profile.upcoming_nights)}일</span>` : ''}
      </div>
      ${tabsHtml}
    </div>
    <section class="venue-head">
      ${metaParts.length ? `<p class="venue-hero-meta">${escapeHtml(metaParts.join(' · '))}</p>` : ''}
      ${capacityLineHtml}
      ${aliasLineHtml}
      ${profile ? `<p class="venue-hero-geo">${geoLine}</p>` : ''}
      ${profile ? `
        <div class="venue-kpi-strip">
          <div class="venue-kpi-card">
            <span class="venue-kpi-lbl">최근 12개월 공연${infoTip('최근 12개월 공연', INFO_TIPS.venue_nights_12m, { compact: true })}</span>
            <strong class="venue-kpi-val mono">${nights12 !== undefined && nights12 !== null ? `${fmtInt(nights12)}일` : '—'}</strong>
            <span class="venue-kpi-sub">같은 날 = 1일 · 기준 ${escapeHtml(effectiveAsOf)}</span>
          </div>
          <div class="venue-kpi-card">
            <span class="venue-kpi-lbl">첫 무대 신인 비율${infoTip('첫 무대 신인 비율', INFO_TIPS.first_timer_share, { compact: true })}</span>
            <strong class="venue-kpi-val mono">${escapeHtml(sharePct)}</strong>
            <span class="venue-kpi-sub">최근 1년 ${fmtInt(profile.teams_1y || 0)}팀 중 ${fmtInt(profile.first_timers_1y || 0)}팀</span>
          </div>
          <div class="venue-kpi-card">
            <span class="venue-kpi-lbl">정답 전에 선 팀${infoTip('정답 전에 선 팀', INFO_TIPS.venue_pre_outcome, { compact: true })}</span>
            <strong class="venue-kpi-val mono">${fmtInt(profile.later_winners_total || 0)}팀</strong>
            <span class="venue-kpi-sub">수상·선정 전에 이곳</span>
          </div>
          ${discoveryKpiHtml}
        </div>` : `
        <p class="venue-hero-meta">${showGroups.length ? `수집된 공연 날짜 ${fmtInt(showGroups.length)}일 · 마지막 기록 ${escapeHtml(showGroups[0].date)}` : '이 공연장의 공연 기록이 아직 없습니다.'}</p>`}
      ${actionsHtml}
    </section>`;

  const prepNotice = profile ? '' : `
    <section class="block venue-prep-card" aria-label="공연장 프로필 준비 중 안내">
      <div class="venue-prep-body">
        <strong>${escapeHtml(hasProfilesFile ? '공연장 프로필 미집계' : '공연장 프로필 준비 중')}</strong>
        <p class="small muted" style="margin:4px 0 0 0;">${escapeHtml(hasProfilesFile
          ? `기준일(${effectiveAsOf})까지 집계된 프로필 목록에 '${cleanVenue}' 항목이 아직 없습니다. 출연 팀·공연 탭은 공연 기록으로 볼 수 있습니다.`
          : '공연장 프로필 파일이 아직 없습니다. 출연 팀·공연 탭은 공연 기록으로 볼 수 있습니다.')}</p>
      </div>
    </section>`;

  const upcoming = showGroups.filter(g => g.isUpcoming).sort((x, y) => x.date.localeCompare(y.date)).slice(0, 6);
  const upcomingHtml = `
    <section class="block">
      <div class="block-head"><h2>다가오는 공연</h2><span class="block-meta">${fmtInt(showGroups.filter(g => g.isUpcoming).length)}일</span></div>
      ${upcoming.length ? `<ul class="venue-upcoming-list">${upcoming.map(g => `
        <li><span class="mono">${escapeHtml(g.date)}</span> ${g.teams.map(t => `<span class="team-cell-inline">${avatarHtml(t.team_key, t.display_name, 18, { shape: 'circle' })}<a href="#/team/${encodeURIComponent(t.team_key)}">${escapeHtml(t.display_name)}</a></span>`).join(' · ')}</li>`).join('')}</ul>`
        : '<p class="muted small" style="margin:0;">잡힌 공연 기록이 없습니다.</p>'}
    </section>`;

  const flowHtml = profile ? `
    <section class="block" id="venueFlowBlock">
      <div class="block-head">
        <div>
          <h2>전후 공연장 흐름</h2>
          <span class="block-meta">${escapeHtml(notes.before_after || '이 공연장에 처음 선 팀들이 전후 1년에 거친 곳')}</span>
        </div>
      </div>
      ${flow ? `<div class="vf-wrap vf-${flow.kind}">${flow.html}</div>
      <p class="small muted vf-note">위 = 이곳 전에 선 곳(회색), 아래 = 이곳 뒤에 처음 선 곳(강조색), 굵기 = 팀 수 · 체급 상승은 점수에 넣지 않는 참고 자료입니다</p>` : ''}
      <details class="vf-list-fold"><summary class="small">목록으로 보기</summary>
      <div class="venue-flow-grid">
        ${renderFlowColumnHtml('이곳 전에 많이 선 곳', profile.before, '이전 1년 사이 함께 집계된 선행 공연장이 없습니다.')}
        ${renderFlowColumnHtml('이곳 뒤에 많이 선 곳', profile.after, '이후 1년 사이 함께 집계된 다음 공연장이 없습니다.')}
      </div>
      </details>
    </section>` : '<section class="block"><p class="muted small" style="margin:0;">공연장 프로필이 없어 전후 흐름을 그릴 수 없습니다.</p></section>';

  const bodyByTab = {
    overview: profile ? `
      <div class="venue-overview-grid">
        <section class="block venue-overview-card">${renderVenueMonthlyBarsHtml(profile.monthly, effectiveAsOf, notes.nights || '')}</section>
        <section class="block venue-overview-card">${renderFirstTimerCardHtml(profile, notes.first_timers_1y || '')}</section>
      </div>
      <div class="venue-roster-grid">
        <section class="block" id="venueWinnersBlock"></section>
        <section class="block" id="venueCandidatesBlock">${renderTopCandidatesInner()}</section>
      </div>
      ${upcomingHtml}` : `${prepNotice}${upcomingHtml}`,
    teams: '<section class="block" id="venueTeamsBlock"></section>',
    gigs: '<section class="block" id="venueRecentShowsBlock"></section>',
    flow: flowHtml,
  };

  // 근거 줄: 별칭·'묶지 않음' · 체급 근거(검증) · 점수와의 관계 · 틀림 제보
  const evidenceHtml = `
    <section class="venue-evidence" aria-label="근거">
      ${basisFoldHtml}
      <p class="small muted">체급·수용 인원은 공개 자료 확인값(출처·확실도는 머리에) · 데이터 수집 상태는 <a href="#/verify/quality">검증 › 데이터 품질</a> ·
        후보 점수의 '서로 다른 공연장'은 <strong>최근 2년</strong> 공연만 세고, 이 화면의 첫 무대 신인·흐름·발굴 주목도는 점수에 넣지 않는 참고 자료입니다 ·
        외부 서비스의 공연장 페이지와 달리 정답(수상·선정) 전에 선 팀을 따로 셉니다 ·
        <a href="${escapeHtml(reportUrl)}" target="_blank" rel="noopener noreferrer">정보가 틀려요 ↗</a></p>
    </section>`;

  root.innerHTML = `
    <div class="team-topbar">
      <button type="button" class="btn btn-sm" id="btnVenueBack">← ${escapeHtml(backLabel)}</button>
      <span class="small muted">기준일 ${escapeHtml(effectiveAsOf)}</span>
    </div>
    <div class="venue-page">
      ${headHtml}
      <div class="venue-tab-body" data-venue-tab="${tab}">${bodyByTab[tab]}</div>
      ${evidenceHtml}
    </div>
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

  paintWinners();
  // 4-2 출연 팀 표 + 공연 표
  const candByKey = new Map(candRows.map((r, i) => [r.team_key, { score: r.score, rank: i + 1 }]));
  const stageByTeam = new Map((stageData?.rows || []).map(r => [r.team_key, r.stage]));
  mountVenueTables(root, { venue: cleanVenue, asOf: effectiveAsOf, teams: venueTeams, showGroups, candByKey, stageByTeam, totalNights: profile ? Number(profile.nights) + Number(profile.upcoming_nights || 0) : null });
  // 5-5 공연장 구독 + 알림 미리보기(이번 주 알림 중 이 공연장 관련 건수)
  loadAlertsJson().then((ad) => {
    const el = root.querySelector('#venueSubPreview');
    if (!el || !ad) return;
    const counts = {};
    for (const a of alertsForSubscribedVenues(ad, [cleanVenue]).get(cleanVenue) || []) counts[a.type] = (counts[a.type] || 0) + 1;
    el.textContent = venueSubForecastText(counts, ad.types || {});
  }).catch(() => null);
  root.querySelector('#btnVenueSub')?.addEventListener('click', (e) => {
    const btn = e.currentTarget;
    const res = toggleVenueSub(cleanVenue);
    btn.classList.toggle('btn-active', res.subscribed);
    btn.setAttribute('aria-pressed', String(res.subscribed));
    btn.textContent = res.subscribed ? '★ 구독 중' : '☆ 이 공연장 구독';
    if (!res.persisted) btn.title = '브라우저 저장이 막혀 이 탭을 닫으면 구독이 사라집니다';
  });
  wireAvatarFallbacks(root);
  wireSpotifyButtons(root, '#venueCandPlayerSlot');

  root.querySelector('#btnVenueBack')?.addEventListener('click', () => {
    navigateTo(backRoute, backParam);
  });
}
