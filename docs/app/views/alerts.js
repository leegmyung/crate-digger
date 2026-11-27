/**
 * 정보 구조 v2 '알림 센터' (#/alerts)
 * - 탭 2개: [받은 알림] [알림 규칙]
 * - 받은 알림: alerts.json 전체 · 종류 필터 · 기간(전체/7/14/30일) · 관심 팀·구독 공연장만 전환 ·
 *              별 많은 순 / 종류별 묶음 보기 · 줄마다 근거 펼침
 * - 알림 규칙: 저장 필터 알림(새로 맞는 팀 미리보기) · 공연장 구독 · 관심 팀 연동 안내
 */
import { appState, getWatchlist, setExportContext } from '../state.js';
import { loadAlertsJson } from '../db.js';
import { loadEventStars } from '../db_team_extras.js';
import { querySavedNewMatches } from '../db_saved.js';
import { applySavedFilter, listSavedFilters } from '../saved_filters.js';
import { alertsForSubscribedVenues, listVenueSubs, toggleVenueSub } from '../venue_subs.js';
import { isoMinusDays } from '../components/team_metrics.js';
import {
  alertMatchesVenueSub, alertRowHtml, safeAlertType, sortAlerts, spikeSentence,
} from './today_alerts.js';
import { renderEvidenceFooterHtml, summarizeFilterSpec } from './mine.js';
import {
  escapeHtml, fmtInt, formatAlertBaselineNote, renderActionBanner, renderEmptyState,
} from '../ui.js';

const PAGE_SIZE = 40;
const GROUP_INITIAL = 6;
const PERIOD_OPTIONS = [
  { id: 'all', label: '전체 기간', days: 0 },
  { id: '7', label: '최근 7일', days: 7 },
  { id: '14', label: '최근 14일', days: 14 },
  { id: '30', label: '최근 30일', days: 30 },
];

function parseAlertsHashParams() {
  const raw = window.location.hash || '';
  const qIdx = raw.indexOf('?');
  const p = new URLSearchParams(qIdx >= 0 ? raw.slice(qIdx + 1) : '');
  const tab = p.get('tab') === 'rules' ? 'rules' : 'feed';
  const mine = p.get('mine') === '1';
  const type = p.get('type') || 'all';
  return { tab, mine, type };
}

function syncAlertsSubHash(tab, mineOnly) {
  const p = new URLSearchParams();
  if (tab === 'rules') p.set('tab', 'rules');
  if (tab === 'feed' && mineOnly) p.set('mine', '1');
  const qs = p.toString();
  const next = qs ? `#/alerts?${qs}` : '#/alerts';
  if (window.location.hash !== next) {
    try {
      window.history.replaceState(null, '', next);
    } catch (_) {
      // ignore history errors in restricted frames
    }
  }
}

function matchesPeriod(alert, days, asOf) {
  if (!days || days <= 0) return true;
  const cut = isoMinusDays(asOf, days);
  if (!cut) return true;
  const d = String(alert.date || alert.found_on || '').slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(d)) return true;
  return d >= cut;
}

export async function renderAlertsView(root) {
  const [alertsData, eventStarsMap] = await Promise.all([
    loadAlertsJson().catch(() => null),
    loadEventStars().catch(() => null),
  ]);

  const initial = parseAlertsHashParams();
  const allAlerts = Array.isArray(alertsData?.alerts) ? alertsData.alerts : [];
  const typesMap = alertsData?.types && typeof alertsData.types === 'object' ? alertsData.types : {};
  const asOf = alertsData?.as_of || appState.dataEnd || '2026-11-28';

  const state = {
    tab: initial.tab,
    type: initial.type === 'all' || (initial.type in typesMap) ? initial.type : 'all',
    period: 'all',
    mineOnly: initial.mine,
    layout: 'flat', // 'flat' (별 많은 순) | 'grouped' (종류별 묶음)
    shownLimit: PAGE_SIZE,
    expandedGroups: new Set(),
  };

  const typeOrder = [
    ...Object.keys(typesMap),
    ...[...new Set(allAlerts.map(a => a.type))].filter(t => !(t in typesMap)),
  ];

  function getWatchAndSubSets() {
    const watchKeys = new Set(getWatchlist().map(w => w.team_key));
    const subVenues = new Set(listVenueSubs());
    return { watchKeys, subVenues };
  }

  function isMineAlert(a, watchKeys, subVenues) {
    return watchKeys.has(a.team_key) || alertMatchesVenueSub(a, subVenues);
  }

  function buildFiltered(watchKeys, subVenues) {
    const periodObj = PERIOD_OPTIONS.find(o => o.id === state.period) || PERIOD_OPTIONS[0];
    return allAlerts.filter(a => {
      if (state.type !== 'all' && a.type !== state.type) return false;
      if (!matchesPeriod(a, periodObj.days, asOf)) return false;
      if (state.mineOnly && !isMineAlert(a, watchKeys, subVenues)) return false;
      return true;
    });
  }

  async function fillRulePreviews() {
    const host = root.querySelector('#alertsRulesSavedList');
    if (!host) return;
    const saved = listSavedFilters();
    if (!saved.length) return;
    const to = appState.dataEnd || asOf;
    const results = await Promise.all(saved.map(it => querySavedNewMatches(it.spec, to).catch(() => null)));
    if (!host.isConnected) return;
    saved.forEach((it, idx) => {
      const slot = host.querySelector(`[data-rule-preview="${CSS.escape(it.id)}"]`);
      if (!slot) return;
      const res = results[idx];
      if (!res) {
        slot.textContent = '매칭 수 계산 실패';
        return;
      }
      const n = res.added.length;
      slot.innerHTML = `<span class="today-saved-count${n ? ' is-up' : ''}">${n ? `지난 7일 새로 ${fmtInt(n)}팀` : '지난 7일 새 팀 없음'}</span> <span class="small muted">· 현재 ${fmtInt(res.total)}팀</span>`;
    });
  }

  function paint() {
    const { watchKeys, subVenues } = getWatchAndSubSets();
    const savedFilters = listSavedFilters();
    const venueSubs = listVenueSubs();
    const rulesCount = savedFilters.length + venueSubs.length;

    const periodObj = PERIOD_OPTIONS.find(o => o.id === state.period) || PERIOD_OPTIONS[0];
    const baseByPeriodAndMine = allAlerts.filter(a => {
      if (!matchesPeriod(a, periodObj.days, asOf)) return false;
      if (state.mineOnly && !isMineAlert(a, watchKeys, subVenues)) return false;
      return true;
    });

    const typeCounts = new Map();
    for (const a of baseByPeriodAndMine) {
      typeCounts.set(a.type, (typeCounts.get(a.type) || 0) + 1);
    }

    const mineTotal = allAlerts.filter(a => isMineAlert(a, watchKeys, subVenues)).length;
    const filtered = buildFiltered(watchKeys, subVenues);
    const sorted = sortAlerts(filtered, eventStarsMap);

    setExportContext({
      csvLabel: sorted.length ? `알림 CSV 내려받기 (${fmtInt(sorted.length)}건)` : '',
      csvFilename: `crate_digger_alerts_${asOf}.csv`,
      csvHeaders: ['종류', '별점', '팀', '내용', '사건일', '발견일', '중요도'],
      csvRows: sorted.map(({ a, stars }) => [
        typesMap[a.type] || a.type_label || a.type,
        stars ?? '',
        a.name || a.team_key,
        a.text || '',
        a.date || '',
        a.found_on || '',
        a.importance ?? '',
      ]),
    });

    const periodText = alertsData?.snapshots?.before && alertsData?.as_of
      ? `${alertsData.snapshots.before} → ${alertsData.as_of}`
      : `기준 ${asOf}`;
    const foundTotal = Object.values(alertsData?.counts_found || {}).reduce((s, n) => s + (Number(n) || 0), 0) || allAlerts.length;
    const baselineNote = formatAlertBaselineNote(alertsData);

    const bannerHtml = renderActionBanner({
      title: '알림 센터',
      lead: alertsData
        ? `기준 <strong>${escapeHtml(periodText)}</strong> · 보인 <strong>${fmtInt(allAlerts.length)}건</strong> (찾은 ${fmtInt(foundTotal)}건)${mineTotal > 0 ? ` · 내 관심·구독 관련 <strong>${fmtInt(mineTotal)}건</strong>` : ''}`
        : '알림 자료(alerts.json)를 불러오지 못했습니다.',
      buttonsHtml: '<a class="btn btn-sm" href="#/mine?tab=watch">내 목록 보기 →</a>',
    });

    const tabsHtml = `
      <nav class="v2-tabs alerts-tabs" role="tablist" aria-label="알림 센터 탭">
        <button type="button" role="tab" class="v2-tab${state.tab === 'feed' ? ' is-active' : ''}" aria-selected="${state.tab === 'feed'}" data-alerts-tab="feed">
          <span>받은 알림</span>
          <span class="v2-tab-count">${fmtInt(allAlerts.length)}</span>
        </button>
        <button type="button" role="tab" class="v2-tab${state.tab === 'rules' ? ' is-active' : ''}" aria-selected="${state.tab === 'rules'}" data-alerts-tab="rules">
          <span>알림 규칙</span>
          <span class="v2-tab-count">${fmtInt(rulesCount)}</span>
        </button>
      </nav>
    `;

    let panelHtml = '';
    if (state.tab === 'feed') {
      if (!alertsData) {
        panelHtml = renderEmptyState({
          title: '알림 자료를 불러오지 못했습니다',
          message: '잠시 뒤 다시 시도하거나 데이터 품질 화면에서 수집 상태를 확인해 보세요.',
          showReset: false,
          actionLabel: '데이터 품질 보기',
          actionHref: '#/verify/quality',
        });
      } else {
        const typeButtons = [
          `<button type="button" class="alerts-chip${state.type === 'all' ? ' is-active' : ''}" data-alert-type="all" aria-pressed="${state.type === 'all'}">전체 <span class="alerts-chip-n">${fmtInt(baseByPeriodAndMine.length)}</span></button>`,
          ...typeOrder
            .filter(t => allAlerts.some(a => a.type === t))
            .map(t => {
              const cnt = typeCounts.get(t) || 0;
              const active = state.type === t;
              return `<button type="button" class="alerts-chip${active ? ' is-active' : ''}" data-alert-type="${escapeHtml(t)}" aria-pressed="${active}">${escapeHtml(typesMap[t] || t)} <span class="alerts-chip-n">${fmtInt(cnt)}</span></button>`;
            }),
        ].join('');

        const periodButtons = PERIOD_OPTIONS.map(o => `
          <button type="button" class="btn btn-sm${state.period === o.id ? ' btn-active' : ''}" data-alert-period="${o.id}" aria-pressed="${state.period === o.id}">${escapeHtml(o.label)}</button>
        `).join('');

        const toolbarHtml = `
          <section class="block alerts-toolbar" aria-label="알림 필터">
            <div class="alerts-toolbar-row">
              <div class="alerts-filter-group">
                <span class="alerts-filter-lbl">기간</span>
                <div class="alerts-seg" role="group" aria-label="기간 선택">${periodButtons}</div>
              </div>
              <div class="alerts-filter-group">
                <button
                  type="button"
                  class="btn btn-sm${state.mineOnly ? ' btn-active' : ''}"
                  id="btnAlertsMineOnly"
                  aria-pressed="${state.mineOnly}"
                >관심 팀·구독 공연장만 (${fmtInt(mineTotal)})</button>
                <div class="alerts-seg" role="group" aria-label="보기 방식">
                  <button type="button" class="btn btn-sm${state.layout === 'flat' ? ' btn-active' : ''}" data-alert-layout="flat" aria-pressed="${state.layout === 'flat'}">별 많은 순</button>
                  <button type="button" class="btn btn-sm${state.layout === 'grouped' ? ' btn-active' : ''}" data-alert-layout="grouped" aria-pressed="${state.layout === 'grouped'}">종류별 묶음</button>
                </div>
              </div>
            </div>
            <div class="alerts-type-chips" role="group" aria-label="알림 종류">${typeButtons}</div>
            ${state.period !== 'all' ? `<p class="small muted alerts-period-note">사건일 기준 ${escapeHtml(isoMinusDays(asOf, periodObj.days))} 이후 알림만 표시합니다.</p>` : ''}
          </section>
        `;

        let feedBodyHtml = '';
        if (!sorted.length) {
          if (state.mineOnly && watchKeys.size === 0 && subVenues.size === 0) {
            feedBodyHtml = renderEmptyState({
              title: '아직 관심 팀이나 구독 공연장이 없습니다',
              message: '발굴 화면에서 팀에 ☆ 관심을 누르거나 공연장을 구독하면 관련 알림만 모아 볼 수 있습니다.',
              showReset: false,
              actionLabel: '발굴에서 팀 둘러보기',
              actionHref: '#/discover',
            });
          } else {
            feedBodyHtml = renderEmptyState({
              title: '조건에 맞는 알림이 없습니다',
              message: '종류·기간·관심만 필터를 넓히거나 초기화해 전체 알림을 확인해 보세요.',
              showReset: false,
              actionLabel: '알림 필터 초기화',
              actionAttrs: 'id="btnResetAlertFilters"',
            });
          }
        } else if (state.layout === 'grouped' && state.type === 'all') {
          const byType = new Map();
          for (const item of sorted) {
            const t = item.a.type;
            if (!byType.has(t)) byType.set(t, []);
            byType.get(t).push(item);
          }
          const groupsHtml = typeOrder
            .filter(t => byType.has(t))
            .map(t => {
              const items = byType.get(t);
              const expanded = state.expandedGroups.has(t);
              const visible = expanded ? items : items.slice(0, GROUP_INITIAL);
              const more = items.length - visible.length;
              const isOpen = t !== 'new_gig' || state.mineOnly || items.length <= 12;
              const foundN = alertsData.counts_found?.[t];
              const capMeta = foundN !== undefined && !state.mineOnly && state.period === 'all'
                ? `보인 ${fmtInt(items.length)} / 찾은 ${fmtInt(foundN)}`
                : `${fmtInt(items.length)}건`;
              return `
                <details class="alert-group"${isOpen ? ' open' : ''}>
                  <summary>
                    <span class="alert-kind-chip alert-kind-${safeAlertType(t)}">${escapeHtml(typesMap[t] || t)}</span>
                    <span class="alert-group-count small muted">${capMeta}</span>
                  </summary>
                  <ul class="today-alerts-list">
                    ${visible.map(item => alertRowHtml(
                      t === 'spike' ? { ...item, a: { ...item.a, text: spikeSentence(item.a) } } : item,
                      {
                        isWatch: watchKeys.has(item.a.team_key),
                        isSubVenue: alertMatchesVenueSub(item.a, subVenues),
                      },
                    )).join('')}
                  </ul>
                  ${more > 0 ? `<button type="button" class="btn btn-sm alert-group-more" data-alerts-group-more="${escapeHtml(t)}">${fmtInt(more)}건 더 보기</button>` : ''}
                </details>
              `;
            }).join('');
          feedBodyHtml = `
            <section class="block alerts-feed-block" aria-label="받은 알림 목록">
              <div class="block-head">
                <h2>종류별 알림</h2>
                <span class="block-meta">${fmtInt(sorted.length)}건 · 별 많은 순</span>
              </div>
              <div class="alert-groups">${groupsHtml}</div>
              <p class="today-alerts-foot muted small">줄을 누르면 근거(날짜·공연장·출처)가 펼쳐집니다${baselineNote ? ` · ${escapeHtml(baselineNote)}` : ''}</p>
            </section>
          `;
        } else {
          const visible = sorted.slice(0, state.shownLimit);
          const remaining = sorted.length - visible.length;
          const activeLabel = state.type === 'all' ? '전체 알림' : (typesMap[state.type] || state.type);
          feedBodyHtml = `
            <section class="block alerts-feed-block" aria-label="받은 알림 목록">
              <div class="block-head">
                <h2>${escapeHtml(activeLabel)}</h2>
                <span class="block-meta">표시 ${fmtInt(visible.length)} / ${fmtInt(sorted.length)}건 · 별 많은 순 → 중요도 순</span>
              </div>
              <ul class="today-alerts-list">
                ${visible.map(item => alertRowHtml(
                  item.a.type === 'spike' ? { ...item, a: { ...item.a, text: spikeSentence(item.a) } } : item,
                  {
                    isWatch: watchKeys.has(item.a.team_key),
                    isSubVenue: alertMatchesVenueSub(item.a, subVenues),
                    typeLabel: state.type === 'all' ? (typesMap[item.a.type] || item.a.type_label || item.a.type) : '',
                  },
                )).join('')}
              </ul>
              ${remaining > 0 ? `
                <div class="more-row" style="margin-top:12px;">
                  <span>${fmtInt(visible.length)} / ${fmtInt(sorted.length)}건 표시 중</span>
                  <button type="button" class="btn btn-sm" id="btnMoreAlertsFeed">${fmtInt(Math.min(PAGE_SIZE, remaining))}건 더 보기</button>
                </div>
              ` : ''}
              <p class="today-alerts-foot muted small">줄을 누르면 근거(날짜·공연장·출처)가 펼쳐집니다${baselineNote ? ` · ${escapeHtml(baselineNote)}` : ''}</p>
            </section>
          `;
        }

        panelHtml = `${toolbarHtml}${feedBodyHtml}`;
      }
    } else {
      // [알림 규칙] 탭
      const byVenue = alertsForSubscribedVenues(alertsData, venueSubs);
      const savedHtml = savedFilters.length
        ? `
          <ul class="alerts-rules-list" id="alertsRulesSavedList">
            ${savedFilters.map(it => {
              const tags = summarizeFilterSpec(it.spec);
              return `
                <li class="alerts-rule-item">
                  <div class="alerts-rule-main">
                    <div class="alerts-rule-head">
                      <strong>${escapeHtml(it.name)}</strong>
                      <span class="alerts-rule-preview" data-rule-preview="${escapeHtml(it.id)}"><span class="small muted">계산 중…</span></span>
                    </div>
                    <div class="mine-filter-tags">
                      ${tags.map(t => `<span class="mine-cond-tag">${escapeHtml(t)}</span>`).join('')}
                    </div>
                  </div>
                  <div class="alerts-rule-actions">
                    <button type="button" class="btn btn-sm" data-rule-apply="${escapeHtml(it.id)}">발굴에서 열기</button>
                  </div>
                </li>
              `;
            }).join('')}
          </ul>
        `
        : renderEmptyState({
            title: '저장한 필터 알림이 없습니다',
            message: '발굴 화면에서 조건을 고르고 "+ 이 필터 저장"을 누르면 매주 새로 맞는 팀을 알려 줍니다.',
            showReset: false,
            actionLabel: '발굴에서 필터 저장',
            actionHref: '#/discover',
          });

      const venueRulesHtml = venueSubs.length
        ? `
          <ul class="alerts-rules-list">
            ${venueSubs.map(v => {
              const list = byVenue.get(v) || [];
              return `
                <li class="alerts-rule-item">
                  <div class="alerts-rule-main">
                    <div class="alerts-rule-head">
                      <a class="inline-venue-link" href="#/venue/${encodeURIComponent(v)}"><strong>${escapeHtml(v)}</strong></a>
                      <span class="small muted">${list.length ? `이번 주 소식 ${fmtInt(list.length)}건` : '이번 주 소식 없음'}</span>
                    </div>
                    <p class="small muted" style="margin:2px 0 0;">큰 공연장 첫 출연 · 새 공연 · 백지 신인 첫 언급 · 같은 무대 수상 팀 알림을 모읍니다.</p>
                  </div>
                  <div class="alerts-rule-actions">
                    <button type="button" class="btn btn-sm" data-rule-unsub="${escapeHtml(v)}">구독 해제</button>
                  </div>
                </li>
              `;
            }).join('')}
          </ul>
        `
        : renderEmptyState({
            title: '구독 중인 공연장이 없습니다',
            message: '공연장 페이지에서 구독을 켜면 해당 무대의 신인·새 공연 알림을 받아 봅니다.',
            showReset: false,
            actionLabel: '공연장 둘러보기',
            actionHref: '#/venues',
          });

      panelHtml = `
        <section class="block alerts-rules-block" aria-label="저장 필터 알림 규칙">
          <div class="block-head">
            <div>
              <h2>저장 필터 알림</h2>
              <span class="block-meta">${fmtInt(savedFilters.length)}개 활성 · 매주 기준일 대비 새로 맞은 팀 확인</span>
            </div>
            <a class="home-more-link" href="#/mine?tab=filters">내 목록에서 관리 →</a>
          </div>
          ${savedHtml}
        </section>

        <section class="block alerts-rules-block" aria-label="공연장 구독 알림 규칙">
          <div class="block-head">
            <div>
              <h2>구독 공연장 알림</h2>
              <span class="block-meta">${fmtInt(venueSubs.length)}곳 구독 중</span>
            </div>
            <a class="home-more-link" href="#/mine?tab=venues">내 목록에서 관리 →</a>
          </div>
          ${venueRulesHtml}
        </section>

        <section class="block alerts-rules-note" aria-label="관심 팀 알림 안내">
          <div class="block-head">
            <div>
              <h2>관심 팀 알림</h2>
              <span class="block-meta">현재 ${fmtInt(watchKeys.size)}팀 관심 등록됨</span>
            </div>
            <a class="home-more-link" href="#/mine?tab=watch">관심 팀 관리 →</a>
          </div>
          <p class="small muted" style="margin:0;">
            관심 팀(☆)으로 담아 둔 팀의 새 정답·선정·단계 상승·공연 알림은 별도 규칙 없이 자동으로 모입니다.
            팀별 개별 조건 알림은 준비 중입니다.
          </p>
          ${watchKeys.size > 0 ? `<div style="margin-top:10px;"><button type="button" class="btn btn-sm" id="btnJumpMineAlerts">내 관심·구독 알림만 보기 (${fmtInt(mineTotal)}건)</button></div>` : ''}
        </section>
      `;
    }

    root.innerHTML = `
      <div class="alerts-page" id="alertsPageRoot">
        ${bannerHtml}
        ${tabsHtml}
        ${panelHtml}
        ${renderEvidenceFooterHtml({ extraNote: `알림 기준 ${asOf}` })}
      </div>
    `;

    // Wire tab switching
    root.querySelectorAll('[data-alerts-tab]').forEach(btn => {
      btn.addEventListener('click', () => {
        const next = btn.dataset.alertsTab === 'rules' ? 'rules' : 'feed';
        if (state.tab === next) return;
        state.tab = next;
        syncAlertsSubHash(state.tab, state.mineOnly);
        paint();
      });
    });

    // Wire feed controls
    root.querySelectorAll('[data-alert-type]').forEach(btn => {
      btn.addEventListener('click', () => {
        state.type = btn.dataset.alertType || 'all';
        state.shownLimit = PAGE_SIZE;
        paint();
      });
    });
    root.querySelectorAll('[data-alert-period]').forEach(btn => {
      btn.addEventListener('click', () => {
        state.period = btn.dataset.alertPeriod || 'all';
        state.shownLimit = PAGE_SIZE;
        paint();
      });
    });
    root.querySelector('#btnAlertsMineOnly')?.addEventListener('click', () => {
      state.mineOnly = !state.mineOnly;
      state.shownLimit = PAGE_SIZE;
      syncAlertsSubHash(state.tab, state.mineOnly);
      paint();
    });
    root.querySelectorAll('[data-alert-layout]').forEach(btn => {
      btn.addEventListener('click', () => {
        state.layout = btn.dataset.alertLayout === 'grouped' ? 'grouped' : 'flat';
        paint();
      });
    });
    root.querySelector('#btnMoreAlertsFeed')?.addEventListener('click', () => {
      state.shownLimit += PAGE_SIZE;
      paint();
    });
    root.querySelectorAll('[data-alerts-group-more]').forEach(btn => {
      btn.addEventListener('click', () => {
        state.expandedGroups.add(btn.dataset.alertsGroupMore);
        paint();
      });
    });
    root.querySelector('#btnResetAlertFilters')?.addEventListener('click', () => {
      state.type = 'all';
      state.period = 'all';
      state.mineOnly = false;
      state.shownLimit = PAGE_SIZE;
      syncAlertsSubHash(state.tab, false);
      paint();
    });

    // Wire rules actions
    root.querySelectorAll('[data-rule-apply]').forEach(btn => {
      btn.addEventListener('click', () => {
        const it = listSavedFilters().find(x => x.id === btn.dataset.ruleApply);
        if (it) applySavedFilter(it);
      });
    });
    root.querySelectorAll('[data-rule-unsub]').forEach(btn => {
      btn.addEventListener('click', () => {
        toggleVenueSub(btn.dataset.ruleUnsub);
        paint();
      });
    });
    root.querySelector('#btnJumpMineAlerts')?.addEventListener('click', () => {
      state.tab = 'feed';
      state.mineOnly = true;
      syncAlertsSubHash('feed', true);
      paint();
    });

    if (state.tab === 'rules') {
      fillRulePreviews();
    }
  }

  paint();

  const onExternalChange = () => {
    const host = root.querySelector('#alertsPageRoot');
    if (!host || !host.isConnected) {
      window.removeEventListener('app:watchlist', onExternalChange);
      window.removeEventListener('app:venue-subs', onExternalChange);
      return;
    }
    paint();
  };
  window.addEventListener('app:watchlist', onExternalChange);
  window.addEventListener('app:venue-subs', onExternalChange);
}
