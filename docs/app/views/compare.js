/**
 * 팀 나란히 비교 #/compare?teams=a,b,c — Chartmetric '비교'처럼 2~4팀을 열로 세워 같은 줄끼리 본다.
 * 줄: 단계 · 핵심 숫자 4개(팀 머리와 같은 정의) · 신호 갈래 · 점수 근거 · 최근 4주 움직임 · 큰 사건 · 첫 발매·장르·지역.
 * 숫자 줄은 가장 큰 값에 ■. 팀 고르기는 발굴·차트·미리보기·팀 페이지의 '＋ 비교'와 이 화면의 팀 찾기.
 */
import { appState } from '../state.js';
import {
  ensureTeamCitiesLoaded, queryDiscoveryStages, queryRankChange, queryTeamDetail,
} from '../db.js';
import { loadEventStars } from '../db_team_extras.js';
import { COMPARE_MAX, compareHash, getCompareList, setCompareList } from '../compare_list.js';
import { rememberCompareName } from '../components/compare_tray.js';
import { keyStatTiles } from '../team_keystats.js';
import { eventsSummarySentence, timelineAnomaly } from '../insight_text.js';
import { searchTeams } from '../search_index.js';
import {
  avatarHtml, escapeHtml, fmtInt, genreConfidenceBadgeHtml, naCell, plainWhyLine, playButtonHtml,
  renderEmptyState, stageBadgeHtml, wireAvatarFallbacks,
} from '../ui.js';

const TOP_EVENTS = 3;
const SEARCH_LIMIT = 6;

async function loadTeam(key, ctx) {
  const d = await queryTeamDetail(key).catch(() => null);
  if (!d || (!d.profile && !d.scored && !(d.timeline || []).length)) return { key, missing: true };
  const name = d.scored?.display_name || d.profile?.display_name || key;
  rememberCompareName(key, name);
  const rc = ctx.rank?.byTeam?.get(key) || null;
  const events = ctx.events?.get(key) || [];
  return {
    key,
    name,
    d,
    stage: ctx.stages?.byTeam?.get(key) || null,
    rc,
    tiles: keyStatTiles({ scored: d.scored, rank: rc?.rank ?? null, weekChange: rc?.week_change ?? 0, videos: d.videos || [] }),
    anomaly: timelineAnomaly(d.timeline || [], ctx.asOf),
    eventsLine: eventsSummarySentence(events, ctx.asOf),
    topEvents: events.filter(e => e.date <= ctx.asOf)
      .sort((a, b) => (b.stars - a.stars) || b.date.localeCompare(a.date)).slice(0, TOP_EVENTS),
    city: appState.teamCitiesByTeam.get(key)?.home_city || rc?.home_city || '',
  };
}

function numOf(v) {
  if (v === null || v === undefined) return null;
  const n = Number(String(v).split('/')[0]);
  return Number.isFinite(n) ? n : null;
}

/** 숫자 줄: 가장 큰 값(2팀 이상이 값을 가지고 모두 같지 않을 때만) */
function bestIndex(values) {
  const nums = values.map(numOf);
  const have = nums.filter(n => n !== null);
  if (have.length < 2) return -1;
  const max = Math.max(...have);
  if (have.every(n => n === max)) return -1;
  return nums.indexOf(max);
}

function rowHtml(label, cells, opts = {}) {
  const best = opts.values ? bestIndex(opts.values) : -1;
  return `<tr>
    <th scope="row" class="cmp-label">${escapeHtml(label)}</th>
    ${cells.map((c, i) => `<td class="${i === best ? 'is-best' : ''}">${c}${i === best ? '<span class="cmp-best" title="이 줄에서 가장 큼">■<span class="sr-visually-hidden"> 가장 큼</span></span>' : ''}</td>`).join('')}
  </tr>`;
}

function headCell(t) {
  if (t.missing) {
    return `<th scope="col" class="cmp-team">
      <span class="small muted">'${escapeHtml(t.key)}' 기록 없음</span>
      <span class="cmp-head-btns"><button type="button" class="btn btn-sm" data-cmp-remove="${escapeHtml(t.key)}">빼기</button></span></th>`;
  }
  const genre = t.d.scored?.primary_genre || t.d.profile?.primary_genre || '';
  return `<th scope="col" class="cmp-team">
    ${avatarHtml(t.key, t.name, 56, { shape: 'rounded', genre })}
    <a class="cmp-name" href="#/team/${encodeURIComponent(t.key)}">${escapeHtml(t.name)}</a>
    <span class="cmp-head-btns">
      ${playButtonHtml(t.key, t.name, { variant: 'icon' })}
      <button type="button" class="btn btn-sm" data-cmp-remove="${escapeHtml(t.key)}" aria-label="${escapeHtml(t.name)} 비교에서 빼기">빼기</button>
    </span>
  </th>`;
}

function eventsCell(t) {
  if (!t.topEvents.length) return naCell('별점을 매길 사건이 아직 없습니다', { label: '—' });
  const items = t.topEvents.map(e => `<li><span class="cmp-stars" aria-label="별 ${e.stars}개">${'★'.repeat(e.stars)}</span> ${escapeHtml(e.kind_label)} <span class="muted small">${escapeHtml(e.date)}</span></li>`).join('');
  return `<ul class="cmp-events">${items}</ul>${t.eventsLine ? `<p class="small muted cmp-note">${escapeHtml(t.eventsLine)}</p>` : ''}`;
}

const NO_SCORE = () => naCell('후보 점수 계산에 들지 않은 팀입니다', { label: '—' });

function tableHtml(teams) {
  const ok = teams.filter(t => !t.missing);
  const cells = fn => teams.map(t => (t.missing ? '' : fn(t)));
  const rows = [
    rowHtml('발굴 단계', cells(x => (x.stage ? stageBadgeHtml(x.stage.stage, { short: true }) : naCell('발굴 단계를 계산하지 않은 팀입니다', { label: '—' })))),
  ];
  (ok[0]?.tiles || []).forEach((tile0, ti) => {
    rows.push(rowHtml(tile0.label, cells(x => {
      const tile = x.tiles[ti];
      const v = tile.value === null ? naCell(tile.tip, { label: '—' }) : `<strong class="cmp-num">${escapeHtml(tile.value)}</strong>`;
      return `${v}<span class="cmp-sub">${escapeHtml(tile.sub)}</span>`;
    }), { values: teams.map(t => (t.missing ? null : t.tiles[ti].value)) }));
  });
  rows.push(rowHtml('신호 갈래', cells(x => (x.d.scored ? `<strong class="cmp-num">${fmtInt(x.d.scored.n_branch)}/4</strong>` : NO_SCORE())),
    { values: teams.map(t => (t.missing ? null : t.d.scored?.n_branch ?? null)) }));
  rows.push(rowHtml('점수 근거', cells(x => (x.d.scored ? `<span class="small">${escapeHtml(plainWhyLine(x.d.scored))}</span>` : NO_SCORE()))));
  rows.push(rowHtml('최근 4주 움직임', cells(x => (x.anomaly
    ? `<span class="cmp-anom cmp-anom-${escapeHtml(x.anomaly.kind)}">${escapeHtml(x.anomaly.text)}</span>`
    : '<span class="small muted">평소 수준</span>'))));
  rows.push(rowHtml('큰 사건 (별 많은 순)', cells(eventsCell)));
  rows.push(rowHtml('첫 발매', cells(x => {
    const fr = x.d.profile?.first_release || appState.firstReleaseByTeam.get(x.key) || x.stage?.first_release || '';
    return /^\d{4}/.test(String(fr)) ? escapeHtml(String(fr).slice(0, 10)) : naCell('첫 발매 기록이 없습니다', { label: '—' });
  })));
  rows.push(rowHtml('장르', cells(x => {
    const g = x.d.scored?.primary_genre || x.d.profile?.primary_genre || '';
    return g && g !== '미분류' ? `${escapeHtml(g)}${genreConfidenceBadgeHtml(x.key)}` : naCell('장르를 아직 모릅니다', { label: '—' });
  })));
  rows.push(rowHtml('활동 지역', cells(x => (x.city ? escapeHtml(x.city) : naCell('공연 도시 기록이 없습니다', { label: '—' })))));
  return `
    <div class="table-wrap cmp-wrap">
      <table class="data-table cmp-table" aria-label="팀 나란히 비교">
        <thead><tr><th scope="col" class="cmp-label"><span class="sr-visually-hidden">항목</span></th>${teams.map(headCell).join('')}</tr></thead>
        <tbody>${rows.join('')}</tbody>
      </table>
    </div>`;
}

function pickerHtml(keys) {
  if (keys.length >= COMPARE_MAX) return `<p class="small muted cmp-picker">비교는 ${COMPARE_MAX}팀까지 — 하나를 빼면 더 담을 수 있어요.</p>`;
  return `
    <div class="cmp-picker">
      <label class="small" for="cmpSearch">팀 더하기</label>
      <input id="cmpSearch" type="search" class="input" placeholder="팀 이름으로 찾기" autocomplete="off" aria-controls="cmpSearchList">
      <ul id="cmpSearchList" class="cmp-search-list" aria-label="찾은 팀"></ul>
    </div>`;
}

function setKeys(keys) {
  setCompareList(keys);
  appState.compareKeys = keys;
  const next = compareHash(keys);
  if (window.location.hash !== next) window.location.hash = next;
}

function wirePicker(root, keys) {
  const input = root.querySelector('#cmpSearch');
  const list = root.querySelector('#cmpSearchList');
  if (!input || !list) return;
  input.addEventListener('input', () => {
    const q = input.value.trim();
    if (!q) {
      list.innerHTML = '';
      return;
    }
    const hits = searchTeams(q, null, SEARCH_LIMIT + keys.length).items
      .filter(it => !keys.includes(it.t.team_key)).slice(0, SEARCH_LIMIT);
    list.innerHTML = hits.length
      ? hits.map(({ t, rank }) => `<li><button type="button" class="cmp-pick" data-cmp-add="${escapeHtml(t.team_key)}">${avatarHtml(t.team_key, t.display_name, 22, { shape: 'circle', genre: t.primary_genre })}<span>${escapeHtml(t.display_name)}</span>${rank ? `<span class="muted small">#${fmtInt(rank)}</span>` : ''}</button></li>`).join('')
      : '<li class="small muted">찾은 팀 없음</li>';
    wireAvatarFallbacks(list);
  });
  list.addEventListener('click', (e) => {
    const b = e.target.closest('[data-cmp-add]');
    if (b) setKeys([...keys, b.dataset.cmpAdd].slice(0, COMPARE_MAX));
  });
}

/** @param {HTMLElement} root */
export async function renderCompareView(root) {
  // 주소에 팀이 있으면 주소가 우선(공유 링크), 없으면 담아 둔 목록
  const fromUrl = [...(appState.compareKeys || [])];
  const keys = fromUrl.length ? fromUrl : getCompareList();
  if (fromUrl.length) setCompareList(keys);
  else if (keys.length) {
    appState.compareKeys = keys;
    window.history.replaceState(null, '', compareHash(keys));
  }
  const asOf = appState.cfg.as_of || appState.dataEnd || '2026-11-28';

  const header = `
    <div class="page-head">
      <h1 class="discover-title">팀 나란히 비교</h1>
      <p class="muted small">최대 ${COMPARE_MAX}팀을 같은 줄끼리 봅니다 · 숫자 줄은 가장 큰 값에 ■ · 기준 ${escapeHtml(asOf)} · 정의는 팀 페이지 머리 숫자·상태 카드와 같음</p>
    </div>`;

  if (!keys.length) {
    root.innerHTML = `${header}${renderEmptyState({
      message: "비교할 팀이 아직 없어요. 발굴·차트·미리보기·팀 페이지의 '＋ 비교'로 2~4팀을 담거나, 아래에서 찾아 더하세요.",
      showReset: false,
      actionLabel: '발굴에서 고르기',
      actionHref: '#/discover',
    })}${pickerHtml(keys)}`;
    wirePicker(root, keys);
    return;
  }

  const [stages, rank, events] = await Promise.all([
    queryDiscoveryStages({ as_of: asOf }).catch(() => null),
    queryRankChange({ as_of: asOf }).catch(() => null),
    loadEventStars().catch(() => null),
    ensureTeamCitiesLoaded().catch(() => null),
  ]);
  const ctx = { asOf, stages, rank, events };
  const teams = await Promise.all(keys.map(k => loadTeam(k, ctx)));

  root.innerHTML = `
    ${header}
    <div class="cmp-toolbar">
      ${pickerHtml(keys)}
      <button type="button" class="btn btn-sm" data-cmp-clear>모두 비우기</button>
    </div>
    ${teams.length < 2 ? '<p class="notice">한 팀만 담겼어요 — 한 팀 더 담으면 나란히 보입니다.</p>' : ''}
    ${tableHtml(teams)}
    <p class="small muted place-evidence">근거: 핵심 숫자는 후보 점수(lab_scored)·공연·매체·영상 기록, 큰 사건은 사건 별점(event_stars), 최근 4주 움직임은 신호 수를 지난 24주의 4주 평균과 비교한 것.</p>`;
  wireAvatarFallbacks(root);
  wirePicker(root, keys);
  root.querySelector('.cmp-wrap')?.addEventListener('click', (e) => {
    const rm = e.target.closest('[data-cmp-remove]');
    if (rm) setKeys(keys.filter(k => k !== rm.dataset.cmpRemove));
  });
  root.querySelector('[data-cmp-clear]')?.addEventListener('click', () => setKeys([]));
}
