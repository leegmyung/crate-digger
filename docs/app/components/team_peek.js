/**
 * 팀 미리보기 패널 — 발굴·차트에서 행을 누르면 오른쪽에 반쯤 열린다(960px 이하는 아래 시트).
 * 목록을 보면서 팀 요약을 확인: 고정 머리(사진·이름·단계·순위·장르/추정) · 4칸 상태 막대(team_pulse 부품) ·
 * 점수 근거 요약 3줄 · 다음 공연 · '팀 페이지 열기' · 관심 추가.
 * Esc·바깥 클릭으로 닫기, ↑↓로 목록의 다음·이전 팀, 주소에 ?peek=<키> (history.replaceState — 뒤로 가기 기록은 안 늘림).
 */
import { appState } from '../state.js';
import {
  ensureTeamCitiesLoaded, queryDiscoveryStages, queryRankChange, queryTeamDetail,
} from '../db.js';
import { queryScenePeerWinners, renderTeamStatusBarsHtml } from '../views/team_pulse.js';
import {
  avatarHtml, escapeHtml, fmtInt, fmtNum, formatNextGigText, genreConfidenceBadgeHtml,
  playButtonHtml, stageBadgeHtml, watchButtonHtml, wireAvatarFallbacks,
} from '../ui.js';

const PANEL_ID = 'teamPeek';
const SCORE_LINES = 3;
let state = { key: '', keys: [], container: null, onChange: null, token: 0, returnFocus: null };
let listenersOn = false;

/** 주소의 ?peek=<키> */
export function peekKeyFromHash() {
  const q = String(window.location.hash || '').split('?')[1] || '';
  return (new URLSearchParams(q).get('peek') || '').slice(0, 120);
}

function setPeekParam(key) {
  const h = window.location.hash || '#/';
  const [path, q = ''] = h.split('?');
  const p = new URLSearchParams(q);
  if (key) p.set('peek', key);
  else p.delete('peek');
  const qs = p.toString();
  const next = qs ? `${path}?${qs}` : path;
  if (next !== h) window.history.replaceState(null, '', next);
}

/** 점수 항목 중 큰 순 3줄 (팀 상세 '점수 근거' 탭과 같은 항목 이름) */
function scoreLines(s) {
  if (!s) return [];
  const items = [
    [`갈래 ${fmtInt(s.n_branch)}개`, s.pts_branch],
    [`선정 최고 단계 ${fmtInt(s.best_stage)}`, s.pts_stage],
    [`서로 다른 공연장 ${fmtInt(s.venues)}곳(최근 2년)`, s.pts_venues],
    [`최근 6개월 활동 ${fmtInt(s.recent180)}건`, s.pts_recent],
    ['이미 상 받은 팀과 같은 무대', s.pts_winner],
    [`발굴 매체 ${fmtInt(s.outlets)}곳`, s.pts_outlets],
    [`맥락 매체 ${fmtInt(s.context_outlets ?? 0)}곳`, s.pts_context],
    ['선정 팀과 같은 무대', s.pts_peer],
    [`최근 1년 공연 ${fmtInt(s.gigs_1y)}일`, s.pts_gigs],
  ];
  return items.filter(([, v]) => Number(v) > 0).sort((a, b) => Number(b[1]) - Number(a[1])).slice(0, SCORE_LINES);
}

function nextGig(timeline, asOf) {
  const g = (timeline || [])
    .filter(t => t.branch === '공연' && String(t.signal_date || '').slice(0, 10) > asOf)
    .sort((a, b) => String(a.signal_date).localeCompare(String(b.signal_date)))[0];
  return g ? { signal_date: String(g.signal_date).slice(0, 10), venue: String(g.venue || '공연장 미정') } : null;
}

function panelEl() {
  return state.container?.querySelector(`#${PANEL_ID}`) || null;
}

function ensurePanel(container) {
  if (container.querySelector(`#${PANEL_ID}`)) return;
  container.insertAdjacentHTML('beforeend', `
    <div class="peek-backdrop" id="teamPeekBackdrop" hidden></div>
    <aside class="team-peek" id="${PANEL_ID}" role="dialog" aria-modal="false" aria-label="팀 미리보기" hidden>
      <div class="peek-body" id="teamPeekBody"></div>
    </aside>`);
}

function highlightRow(key) {
  state.container?.querySelectorAll('tr[data-team-key]').forEach(tr => {
    tr.classList.toggle('is-peeked', tr.dataset.teamKey === key);
  });
}

function headHtml(key, d) {
  const name = d.profile?.display_name || d.scored?.display_name || key;
  const genre = d.scored?.primary_genre || d.profile?.primary_genre || '';
  const idx = state.keys.indexOf(key);
  const delta = d.weekChange > 0 ? ` <span class="rank-delta is-up">▲${fmtInt(d.weekChange)}</span>`
    : d.weekChange < 0 ? ` <span class="rank-delta is-down">▼${fmtInt(-d.weekChange)}</span>` : '';
  return `
    <div class="peek-head">
      <div class="peek-head-main">
        ${avatarHtml(key, name, 48, { shape: 'rounded', genre })}
        <div class="peek-title">
          <strong class="peek-name">${escapeHtml(name)}</strong>
          <div class="peek-facts">
            ${d.stage !== null && d.stage !== undefined ? stageBadgeHtml(d.stage, { short: true }) : ''}
            ${d.rank ? `<span class="peek-fact">#${fmtInt(d.rank)}${delta}</span>` : '<span class="peek-fact muted">300위 밖</span>'}
            ${genre && genre !== '미분류' ? `<span class="peek-fact">${escapeHtml(genre)}${genreConfidenceBadgeHtml(key)}</span>` : ''}
            ${d.city ? `<span class="peek-fact">${escapeHtml(d.city)}</span>` : ''}
          </div>
        </div>
        <button type="button" class="btn btn-sm peek-close" data-peek-close="1" aria-label="미리보기 닫기">닫기</button>
      </div>
      ${state.keys.length > 1 ? `<div class="peek-nav small muted">
        <button type="button" class="btn btn-sm" data-peek-step="-1" ${idx <= 0 ? 'disabled' : ''} aria-label="이전 팀">↑ 이전</button>
        <span>${idx >= 0 ? `${fmtInt(idx + 1)} / ${fmtInt(state.keys.length)}` : ''}</span>
        <button type="button" class="btn btn-sm" data-peek-step="1" ${idx < 0 || idx >= state.keys.length - 1 ? 'disabled' : ''} aria-label="다음 팀">다음 ↓</button>
      </div>` : ''}
    </div>`;
}

async function load(key) {
  const asOf = appState.cfg.as_of || appState.dataEnd || '2026-11-27';
  const [detail, stageData, rankData, sceneWinners] = await Promise.all([
    queryTeamDetail(key),
    queryDiscoveryStages({ as_of: asOf }).catch(() => null),
    queryRankChange({ as_of: asOf }).catch(() => null),
    queryScenePeerWinners(key, asOf),
    ensureTeamCitiesLoaded().catch(() => null),
  ]);
  const stageInfo = stageData?.byTeam?.get(key) || null;
  const rc = rankData?.byTeam?.get(key) || null;
  return {
    ...detail,
    asOf,
    stageInfo,
    stage: stageInfo ? stageInfo.stage : null,
    rank: rc?.rank ?? null,
    weekChange: rc?.week_change ?? 0,
    city: appState.teamCitiesByTeam.get(key)?.home_city || '',
    sceneWinners,
  };
}

async function render(key) {
  const body = state.container?.querySelector('#teamPeekBody');
  if (!body) return;
  const token = ++state.token;
  body.innerHTML = `<div class="peek-loading small muted">${escapeHtml(key)} 불러오는 중…</div>`;
  let d;
  try {
    d = await load(key);
  } catch (_) {
    if (token === state.token) body.innerHTML = '<p class="small muted" style="padding:16px;">이 팀을 불러오지 못했습니다.</p>';
    return;
  }
  if (token !== state.token || !body.isConnected) return;
  if (!d.profile && !d.scored && !(d.timeline || []).length) {
    body.innerHTML = `${headHtml(key, d)}<p class="small muted peek-section">현재 데이터에 이 팀 기록이 없습니다.</p>`;
    return;
  }
  const lines = scoreLines(d.scored);
  const gig = nextGig(d.timeline, d.asOf);
  const name = d.profile?.display_name || d.scored?.display_name || key;
  body.innerHTML = `
    ${headHtml(key, d)}
    <div class="peek-scroll">
      <section class="peek-section">${renderTeamStatusBarsHtml({ stageInfo: d.stageInfo, scored: d.scored, timeline: d.timeline, sceneWinners: d.sceneWinners, asOf: d.asOf })}</section>
      <section class="peek-section">
        <h3 class="peek-h">점수 근거${d.scored ? ` <span class="small muted">합계 ${fmtNum(Number(d.scored.score), 2)}점</span>` : ''}</h3>
        ${lines.length ? `<ol class="peek-lines">${lines.map(([lbl, v]) => `<li><span>${escapeHtml(lbl)}</span><span class="mono">+${fmtNum(Number(v), 2)}</span></li>`).join('')}</ol>` : '<p class="small muted">지금 조건의 점수 후보가 아닙니다.</p>'}
      </section>
      <section class="peek-section">
        <h3 class="peek-h">다음 공연</h3>
        ${gig ? `<p>${gig.venue !== '공연장 미정' ? `<a href="#/venue/${encodeURIComponent(gig.venue)}">${escapeHtml(formatNextGigText(gig))}</a>` : escapeHtml(formatNextGigText(gig))}</p>` : '<p class="small muted">잡힌 공연 기록이 없습니다.</p>'}
      </section>
    </div>
    <div class="peek-actions">
      <a class="btn btn-primary" href="#/team/${encodeURIComponent(key)}">팀 페이지 열기 →</a>
      ${playButtonHtml(key, name, { variant: 'sm' })}
      ${watchButtonHtml(key, name, false)}
    </div>`;
  wireAvatarFallbacks(body);
}

function onKey(e) {
  const panel = panelEl();
  if (!panel || panel.hidden) return;
  if (e.key === 'Escape') {
    e.preventDefault();
    closeTeamPeek();
    return;
  }
  const tag = (e.target?.tagName || '').toLowerCase();
  if (tag === 'input' || tag === 'select' || tag === 'textarea') return;
  if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
    e.preventDefault();
    e.stopPropagation();
    stepTeamPeek(e.key === 'ArrowDown' ? 1 : -1);
  }
}

/** 바깥 클릭으로 닫기 — 표 줄을 누르면 닫지 않고 그 팀으로 바뀐다(줄 클릭 처리기가 연다) */
function onDocClick(e) {
  const panel = panelEl();
  if (!panel || panel.hidden || !panel.isConnected) return;
  if (e.target.closest('#teamPeek') || e.target.closest('tr[data-team-key]')) return;
  // 정렬 머리줄·필터 버튼·입력 같은 조작은 미리보기를 닫지 않는다(빈 곳을 눌렀을 때만 닫음)
  if (e.target.closest('button, a, input, select, textarea, label, summary, th, [role="button"], [role="tab"]')) return;
  if (!e.target.isConnected) return; // 클릭으로 다시 그려져 떨어져 나간 요소
  closeTeamPeek();
}

function onClick(e) {
  if (e.target.closest('[data-peek-close]') || e.target.id === 'teamPeekBackdrop') {
    closeTeamPeek();
    return;
  }
  const step = e.target.closest('[data-peek-step]');
  if (step) stepTeamPeek(Number(step.dataset.peekStep));
}

/**
 * @param {string} key 팀 키
 * @param {{ container: HTMLElement, keys?: string[], onChange?: (key: string) => void }} opts
 */
export function openTeamPeek(key, opts) {
  if (!key || !opts?.container) return;
  ensurePanel(opts.container);
  const first = !state.key || state.container !== opts.container;
  state = {
    ...state,
    key,
    keys: Array.isArray(opts.keys) ? opts.keys : state.keys,
    container: opts.container,
    onChange: opts.onChange || null,
    returnFocus: first ? document.activeElement : state.returnFocus,
  };
  const panel = panelEl();
  const backdrop = opts.container.querySelector('#teamPeekBackdrop');
  if (panel) panel.hidden = false;
  if (backdrop) backdrop.hidden = false;
  if (!listenersOn) {
    document.addEventListener('keydown', onKey, true); // 표의 ↑↓ 이동보다 먼저
    document.addEventListener('click', onDocClick);
    listenersOn = true;
  }
  if (panel && !panel.dataset.wired) {
    panel.dataset.wired = '1';
    panel.addEventListener('click', onClick);
    backdrop?.addEventListener('click', onClick);
  }
  setPeekParam(key);
  highlightRow(key);
  state.container.querySelector(`tr[data-team-key="${CSS.escape(key)}"]`)?.scrollIntoView({ block: 'nearest' });
  render(key).then(() => {
    if (first) panelEl()?.querySelector('[data-peek-close]')?.focus();
  });
  if (state.onChange) state.onChange(key);
}

export function stepTeamPeek(delta) {
  const i = state.keys.indexOf(state.key);
  const next = state.keys[i + delta];
  if (i < 0 || !next) return;
  openTeamPeek(next, { container: state.container, keys: state.keys, onChange: state.onChange });
}

/** 목록이 다시 그려졌을 때(정렬·필터) 순서만 바꾸고 강조를 다시 건다 */
export function updateTeamPeekKeys(keys) {
  state.keys = Array.isArray(keys) ? keys : [];
  if (state.key) highlightRow(state.key);
}

export function isTeamPeekOpen() {
  const panel = panelEl();
  return Boolean(panel && !panel.hidden && panel.isConnected);
}

export function closeTeamPeek() {
  const panel = panelEl();
  const backdrop = state.container?.querySelector('#teamPeekBackdrop');
  if (panel) panel.hidden = true;
  if (backdrop) backdrop.hidden = true;
  highlightRow('');
  setPeekParam('');
  state.token += 1;
  const back = state.returnFocus;
  state = { ...state, key: '', returnFocus: null };
  if (back && back.isConnected && typeof back.focus === 'function') back.focus();
}

/** 화면에 보이는 표 줄의 팀 키 순서(↑↓ 이동 순서) — 숨은 표·미리보기 안 줄은 뺀다 */
export function peekKeysFrom(container) {
  const seen = new Set();
  for (const tr of container.querySelectorAll('tr[data-team-key]')) {
    if (tr.offsetParent === null || tr.closest('#teamPeek')) continue;
    seen.add(tr.dataset.teamKey);
  }
  return [...seen];
}

/** 표에 미리보기 연결: 줄 클릭(링크·버튼 제외)·Enter → 미리보기. 처음 열 때 주소의 ?peek= 도 연다 */
export function attachTeamPeek(container, { initialKey = '' } = {}) {
  const open = key => openTeamPeek(key, { container, keys: peekKeysFrom(container) });
  if (initialKey) open(initialKey);
  return open;
}
