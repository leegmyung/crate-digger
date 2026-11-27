/**
 * 5-3 '오늘 알림' 카드 — 종류별 묶음 · 별점(사건 별점이 있으면) → 중요도 순 · 줄마다 근거 펼침 ·
 *     종류별 '보인 수/찾은 수'(alerts.json caps) · 오름 종류는 글자색.
 * 5-4 '평소와 다른 움직임' 문장 — alerts.json 의 spike 종류. 평소 주 1건 이하 팀은 배수 대신 '처음 n건'.
 * watchlist.js 의 관심 팀 주간 요약도 여기 함수를 같이 쓴다.
 */
import { appState } from '../state.js';
import { escapeHtml, fmtInt, formatAlertBaselineNote, SOURCE_LABELS } from '../ui.js';

const GROUP_FIRST = 5;
const COLLAPSED_TYPES = new Set(['new_gig']); // 수가 많아 접어 둠
const UP_TYPES = new Set(['stage_up', 'rank_jump', 'spike']);
/** 알림 종류 → event_stars.csv 사건 종류(같은 팀·같은 날이면 별점을 빌려 씀) */
const STAR_KINDS = {
  new_outcome: 'outcome', new_selection: 'selection', big_venue_first: 'big_venue_first', blank_first_mention: 'first_mention',
};

export function alertStars(a, eventStarsMap) {
  const kind = STAR_KINDS[a.type];
  if (!kind || !eventStarsMap) return null;
  const hit = (eventStarsMap.get(a.team_key) || []).find(e => e.kind === kind && e.date === a.date);
  return hit ? hit.stars : null;
}

export function sortAlerts(list, eventStarsMap) {
  return list
    .map(a => ({ a, stars: alertStars(a, eventStarsMap) }))
    .sort((x, y) => (y.stars ?? 0) - (x.stars ?? 0) || (Number(y.a.importance) || 0) - (Number(x.a.importance) || 0));
}

export function evidenceItems(a) {
  const ev = Array.isArray(a.evidence) ? a.evidence : [];
  return ev.slice(0, 6).map(e => {
    const prog = e.program ? (appState.programLabels?.get(e.program) || SOURCE_LABELS[e.program] || e.program) : '';
    const src = e.source ? (SOURCE_LABELS[e.source] || e.source) : '';
    const venueHtml = e.venue
      ? `<a class="inline-venue-link" href="#/venue/${encodeURIComponent(e.venue)}">${escapeHtml(e.venue)}</a>`
      : '';
    const rest = [prog || src, e.branch].filter(Boolean).map(escapeHtml).join(' · ');
    const body = [venueHtml, rest].filter(Boolean).join(' · ') || '출처 미상';
    return `<li><span class="mono">${escapeHtml(e.date || a.date || '')}</span> ${body}</li>`;
  }).join('');
}

export function starsMini(n) {
  if (!n) return '';
  return `<span class="alert-stars" role="img" aria-label="사건 별 ${n}개" title="사건 별점 ${n}">${'★'.repeat(n)}</span>`;
}

export function safeAlertType(type) {
  return /^[a-z0-9_]+$/.test(String(type || '')) ? String(type) : 'other';
}

export function alertRowHtml({ a, stars }, { isWatch = false, isSubVenue = false, typeLabel = '' } = {}) {
  const ev = evidenceItems(a);
  const textCls = UP_TYPES.has(a.type) ? ' is-up' : '';
  const chipHtml = typeLabel
    ? `<span class="alert-kind-chip alert-kind-${safeAlertType(a.type)}">${escapeHtml(typeLabel)}</span>`
    : '';
  const relBadge = isWatch
    ? '<span class="alert-rel-tag">관심</span>'
    : (isSubVenue ? '<span class="alert-rel-tag">구독 공연장</span>' : '');
  return `
    <li class="alert-row${isWatch ? ' is-watch' : ''}">
      <details>
        <summary>
          ${chipHtml}
          ${starsMini(stars)}
          <a class="today-alert-team" href="#/team/${encodeURIComponent(a.team_key)}"><strong>${escapeHtml(a.name || a.team_key)}</strong></a>
          ${relBadge}
          <span class="today-alert-text${textCls}">${escapeHtml(a.text)}</span>
          <span class="today-alert-meta mono">${escapeHtml(a.date || '')}</span>
        </summary>
        <div class="alert-evidence">
          ${ev ? `<ul>${ev}</ul>` : '<p class="small muted">근거 목록이 없습니다.</p>'}
          ${a.found_on ? `<p class="small muted">발견일 ${escapeHtml(a.found_on)}</p>` : ''}
        </div>
      </details>
    </li>`;
}

function groupHtml(type, label, items, alertsData, expanded) {
  const shownCap = alertsData.counts_shown?.[type];
  const found = alertsData.counts_found?.[type];
  const capTxt = (shownCap !== undefined && found !== undefined) ? `보인 ${fmtInt(shownCap)} / 찾은 ${fmtInt(found)}` : `${fmtInt(items.length)}건`;
  const isOpen = !COLLAPSED_TYPES.has(type);
  const visible = expanded ? items : items.slice(0, GROUP_FIRST);
  const more = items.length - visible.length;
  const safeType = /^[a-z0-9_]+$/.test(type) ? type : 'other';
  return `
    <details class="alert-group"${isOpen ? ' open' : ''}>
      <summary>
        <span class="alert-kind-chip alert-kind-${safeType}">${escapeHtml(label)}</span>
        <span class="alert-group-count small muted" title="보인 수 = 화면에 싣는 상한(caps) 안, 찾은 수 = 이번에 찾은 전체">${capTxt}</span>
      </summary>
      <ul class="today-alerts-list">${visible.map(x => alertRowHtml(x)).join('')}</ul>
      ${more > 0 ? `<button type="button" class="btn btn-sm alert-group-more" data-alert-more="${escapeHtml(type)}">${fmtInt(more)}건 더 보기</button>` : ''}
    </details>`;
}

/**
 * @param {object|null} alertsData alerts.json
 * @param {{ watchAlerts: object[], showAllWatch: boolean, eventStarsMap: Map|null, expandedTypes: Set<string> }} st
 */
export function renderAlertsCardHtml(alertsData, st) {
  const all = Array.isArray(alertsData?.alerts) ? alertsData.alerts : [];
  const head = (meta) => `
    <div class="block-head">
      <h2>오늘 알림</h2>
      <span class="block-meta">${escapeHtml(meta)}</span>
    </div>`;
  if (!alertsData) return '';
  if (!all.length) {
    return `<section class="block today-alerts-block" id="todayAlertsBlock">${head('')}<p class="muted small" style="margin:0;">이번 주 새 알림 없음</p></section>`;
  }
  const types = alertsData.types && typeof alertsData.types === 'object' ? alertsData.types : {};
  const byType = new Map();
  for (const a of all) {
    if (!byType.has(a.type)) byType.set(a.type, []);
    byType.get(a.type).push(a);
  }
  const order = [...Object.keys(types), ...[...byType.keys()].filter(t => !(t in types))];
  const groups = order.filter(t => byType.has(t))
    .map(t => groupHtml(t, types[t] || t, sortAlerts(byType.get(t), st.eventStarsMap), alertsData, st.expandedTypes.has(t)))
    .join('');

  const watchSorted = sortAlerts(st.watchAlerts, st.eventStarsMap);
  const visWatch = st.showAllWatch ? watchSorted.slice(0, 20) : watchSorted.slice(0, 6);
  const watchHtml = watchSorted.length ? `
    <div class="today-alerts-watch" aria-label="관심 목록 팀 알림">
      <div class="today-alerts-watch-head">
        <strong>관심 팀 알림</strong>
        <span class="small muted">${fmtInt(watchSorted.length)}건</span>
      </div>
      <ul class="today-alerts-list">${visWatch.map(x => alertRowHtml(x, { isWatch: true })).join('')}</ul>
      ${!st.showAllWatch && watchSorted.length > 6 ? `<div style="margin-top:8px;"><button type="button" class="btn btn-sm" id="btnMoreWatchAlerts">${fmtInt(Math.min(20, watchSorted.length) - 6)}건 더 보기</button></div>` : ''}
    </div>` : '';

  const foundTotal = Object.values(alertsData.counts_found || {}).reduce((s, n) => s + (Number(n) || 0), 0);
  const note = formatAlertBaselineNote(alertsData);
  return `
    <section class="block today-alerts-block" id="todayAlertsBlock" aria-label="오늘 알림">
      ${head(`보인 ${fmtInt(all.length)}건 · 찾은 ${fmtInt(foundTotal || all.length)}건`)}
      ${watchHtml}
      <div class="alert-groups">${groups}</div>
      <p class="today-alerts-foot muted small">줄을 누르면 근거(날짜·출처)가 펼쳐집니다 · 별은 사건 별점(작은 팀일수록 높음), 없으면 중요도 순${note ? ` · ${escapeHtml(note)}` : ''}</p>
    </section>`;
}

/** 5-4 spike 알림 한 건 → 문장(배수 또는 '처음 n건') */
export function spikeSentence(a) {
  const name = a.name || a.team_key;
  const n = Number(a.recent) || 0;
  const weeks = 12;
  if (a.ratio !== null && a.ratio !== undefined && Number.isFinite(Number(a.ratio))) {
    const avg = Number(a.past_weekly_avg);
    const avgTxt = Number.isFinite(avg) ? ` 주 ${avg.toFixed(1)}건` : '';
    return `${name}의 최근 1주 언급 ${fmtInt(n)}건 — 평소(지난 ${weeks}주 평균${avgTxt})의 ${Number(a.ratio).toFixed(1)}배`;
  }
  if (Number(a.past_weeks_total) === 0) return `${name} — 최근 1주 처음 언급 ${fmtInt(n)}건 (지난 ${weeks}주엔 없음)`;
  return `${name} — 최근 1주 언급 ${fmtInt(n)}건 (평소 주 1건 이하라 배수 대신 건수)`;
}

/**
 * @param {object[]} spikes spike 알림들
 * @param {{ title?: string, emptyText?: string }} [opts]
 */
export function renderSpikeSentencesHtml(spikes, opts = {}) {
  if (!spikes.length) return opts.emptyText ? `<p class="small muted">${escapeHtml(opts.emptyText)}</p>` : '';
  const items = [...spikes]
    .sort((x, y) => (Number(y.importance) || 0) - (Number(x.importance) || 0))
    .slice(0, 8)
    .map(a => `
      <li class="spike-row">
        <details>
          <summary><span class="spike-text">${escapeHtml(spikeSentence(a))}</span> <a class="inline-team-link" href="#/team/${encodeURIComponent(a.team_key)}">팀 보기 →</a></summary>
          <div class="alert-evidence">${evidenceItems(a) ? `<ul>${evidenceItems(a)}</ul>` : '<p class="small muted">근거 목록이 없습니다.</p>'}</div>
        </details>
      </li>`).join('');
  return `<ul class="spike-list">${items}</ul>`;
}

/**
 * 5-4 관심 목록 주간 요약 — alerts.json 을 관심 팀으로 좁혀 종류별 건수 · 위 5건 · 이상치 문장.
 * @param {object|null} alertsData
 * @param {Set<string>} watchKeys
 * @param {Map|null} eventStarsMap
 */
export function renderWatchWeeklySummaryHtml(alertsData, watchKeys, eventStarsMap) {
  const head = (meta) => `
    <div class="block-head">
      <h2>이번 주 관심 팀 요약</h2>
      <span class="block-meta">${escapeHtml(meta)}</span>
    </div>`;
  if (!alertsData || !Array.isArray(alertsData.alerts)) {
    return `<section class="block watch-weekly-block">${head('')}<p class="small muted" style="margin:0;">알림 자료(alerts.json)를 불러오지 못했습니다.</p></section>`;
  }
  const mine = alertsData.alerts.filter(a => watchKeys.has(a.team_key));
  const period = alertsData.snapshots?.before && alertsData.as_of ? `${alertsData.snapshots.before} → ${alertsData.as_of}` : (alertsData.as_of || '');
  if (!mine.length) {
    return `<section class="block watch-weekly-block">${head(period)}<p class="small muted" style="margin:0;">이번 주 관심 팀에 새 알림이 없습니다.</p></section>`;
  }
  const types = alertsData.types || {};
  const counts = new Map();
  for (const a of mine) counts.set(a.type, (counts.get(a.type) || 0) + 1);
  const teams = new Set(mine.map(a => a.team_key)).size;
  const countLine = [...counts.entries()]
    .sort((x, y) => y[1] - x[1])
    .map(([t, n]) => `${escapeHtml(types[t] || t)} ${fmtInt(n)}`)
    .join(' · ');
  const top = sortAlerts(mine.filter(a => a.type !== 'spike'), eventStarsMap).slice(0, 5);
  const spikes = mine.filter(a => a.type === 'spike');
  return `
    <section class="block watch-weekly-block" aria-label="이번 주 관심 팀 요약">
      ${head(period)}
      <p class="watch-weekly-lead">관심 팀 <strong>${fmtInt(teams)}팀</strong>에 알림 <strong>${fmtInt(mine.length)}건</strong> — ${countLine}</p>
      ${spikes.length ? `<div class="watch-weekly-sub"><strong class="small">평소와 다른 움직임</strong>${renderSpikeSentencesHtml(spikes)}</div>` : ''}
      ${top.length ? `<ul class="today-alerts-list">${top.map(x => alertRowHtml(x, { isWatch: true })).join('')}</ul>` : ''}
    </section>`;
}

export function alertMatchesVenueSub(a, subVenueSet) {
  if (!subVenueSet || !subVenueSet.size) return false;
  const ev = Array.isArray(a?.evidence) ? a.evidence : [];
  return ev.some(e => e?.venue && subVenueSet.has(String(e.venue).trim()));
}

/**
 * 정보 구조 v2 홈(#/home)용 간결 알림 요약 — 별점 → 중요도 순 상위 N줄 + '모두 보기 → #/alerts'.
 * @param {object|null} alertsData
 * @param {{ eventStarsMap: Map|null, watchKeys?: Set<string>, subVenues?: Set<string>, limit?: number }} opts
 */
export function renderHomeAlertsSummaryHtml(alertsData, {
  eventStarsMap = null,
  watchKeys = new Set(),
  subVenues = new Set(),
  limit = 5,
} = {}) {
  const all = Array.isArray(alertsData?.alerts) ? alertsData.alerts : [];
  if (!alertsData) return '';
  const foundTotal = Object.values(alertsData.counts_found || {}).reduce((s, n) => s + (Number(n) || 0), 0) || all.length;
  const head = `
    <div class="block-head">
      <div>
        <h2>알림 요약</h2>
        <span class="block-meta">별 많은 순 상위 ${fmtInt(Math.min(limit, all.length))}건 · 전체 ${fmtInt(all.length)}건 (찾은 ${fmtInt(foundTotal)}건)</span>
      </div>
      <a class="home-more-link" href="#/alerts">모두 보기 →</a>
    </div>`;
  if (!all.length) {
    return `<section class="block home-alerts-block" id="todayAlertsBlock" aria-label="알림 요약">${head}<p class="muted small" style="margin:0;">이번 주 새 알림이 없습니다.</p></section>`;
  }

  const types = alertsData.types && typeof alertsData.types === 'object' ? alertsData.types : {};
  const sorted = sortAlerts(all, eventStarsMap);
  const top = sorted.slice(0, limit);
  const watchCount = all.filter(a => watchKeys.has(a.team_key) || alertMatchesVenueSub(a, subVenues)).length;
  const note = formatAlertBaselineNote(alertsData);

  return `
    <section class="block home-alerts-block" id="todayAlertsBlock" aria-label="알림 요약">
      ${head}
      ${watchCount > 0 ? `<p class="home-alerts-mine-note small">관심 팀·구독 공연장 관련 알림 <strong>${fmtInt(watchCount)}건</strong>이 포함되어 있습니다 · <a href="#/alerts">알림 센터에서 모아 보기 →</a></p>` : ''}
      <ul class="today-alerts-list">
        ${top.map(item => alertRowHtml(item, {
          isWatch: watchKeys.has(item.a.team_key),
          isSubVenue: alertMatchesVenueSub(item.a, subVenues),
          typeLabel: types[item.a.type] || item.a.type_label || item.a.type,
        })).join('')}
      </ul>
      <p class="today-alerts-foot muted small">줄을 누르면 근거(날짜·출처)가 펼쳐집니다 · 별 많은 순 → 중요도 순${note ? ` · ${escapeHtml(note)}` : ''}</p>
    </section>`;
}

