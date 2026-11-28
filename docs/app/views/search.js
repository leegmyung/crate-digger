// 검색 결과 화면 #/search?q= — 팀·공연장·도시·페스티벌을 종류별로 묶어 보여 준다 (정보 구조 v2 묶음 B).
// 색인·맞추기 규칙은 위쪽 검색 드롭다운과 같은 search_index.js 를 쓴다.
import { appState, navigateTo } from '../state.js';
import {
  avatarHtml, escapeHtml, playButtonHtml, STAGE_META, wireAvatarFallbacks,
} from '../ui.js';
import {
  TIER_KO, loadSearchIndex, searchAll, cityHash, festivalHash, searchPageHash,
} from '../search_index.js';

const PAGE_LIMIT = 20;          // 종류마다 처음 보여 줄 개수 (더 보기로 전부)
const ALL_LIMIT = 500;
const REPORT_URL = 'https://github.com/leegmyung/crate-digger/issues/new?template=identity.yml';
const DEBOUNCE_MS = 200;

function teamRow({ t, rank, st, lastSeen }) {
  const stageLbl = st ? (STAGE_META[Number(st.stage)]?.label || st.stage_label || '') : '';
  const stageCls = st ? `stage-s${st.stage}` : '';
  return `
    <li class="sr-row">
      <a class="sr-link" href="#/team/${encodeURIComponent(t.team_key)}" data-team-key="${escapeHtml(t.team_key)}">
        ${avatarHtml(t.team_key, t.display_name || t.team_key, 28, { shape: 'rounded', genre: t.primary_genre })}
        <span class="sr-name">${escapeHtml(t.display_name || t.team_key)}</span>
        ${stageLbl ? `<span class="f-search-stage ${stageCls}">${escapeHtml(stageLbl)}</span>` : ''}
        <span class="sr-meta">
          ${rank ? `<span>#${rank}</span>` : ''}
          ${t.primary_genre ? `<span>${escapeHtml(t.primary_genre)}</span>` : ''}
          ${lastSeen ? `<span>최근 신호 ${escapeHtml(lastSeen)}</span>` : ''}
        </span>
      </a>
      ${playButtonHtml(t.team_key, t.display_name || t.team_key, { variant: 'icon' })}
    </li>`;
}

function venueRow({ v }) {
  const tier = v.tier ? `${v.tier}(${TIER_KO[v.tier] || v.tier})` : '체급 모름';
  return `
    <li class="sr-row">
      <a class="sr-link" href="#/venue/${encodeURIComponent(v.name)}">
        <span class="f-search-venue-ico" aria-hidden="true">${escapeHtml((v.city || v.name).slice(0, 2))}</span>
        <span class="sr-name">${escapeHtml(v.name)}</span>
        <span class="sr-meta">
          ${v.city ? `<span>${escapeHtml(v.city)}</span>` : ''}
          <span>${escapeHtml(tier)}</span>
          ${v.nights ? `<span>공연 ${v.nights}일</span>` : ''}
          ${v.last_night ? `<span>마지막 ${escapeHtml(v.last_night)}</span>` : ''}
        </span>
      </a>
    </li>`;
}

function cityRow({ c }) {
  return `
    <li class="sr-row">
      <a class="sr-link" href="${escapeHtml(cityHash(c.name))}">
        <span class="f-search-venue-ico" aria-hidden="true">${escapeHtml(c.name.slice(0, 2))}</span>
        <span class="sr-name">${escapeHtml(c.name)}</span>
        <span class="sr-meta">
          <span>공연장 ${c.venues}</span><span>공연 ${c.nights}일</span>
          <span>최근 1년 첫 무대 ${c.firstStage1y}팀</span>
          ${c.upcoming ? `<span>예정 ${c.upcoming}일</span>` : ''}
        </span>
      </a>
    </li>`;
}

function festivalRow({ f }) {
  const span = f.years.length ? `${f.years[0]}${f.years.length > 1 ? `~${f.years[f.years.length - 1]}` : ''}` : '';
  return `
    <li class="sr-row">
      <a class="sr-link" href="${escapeHtml(festivalHash(f.key))}">
        <span class="f-search-venue-ico" aria-hidden="true">축</span>
        <span class="sr-name">${escapeHtml(f.label)}</span>
        <span class="sr-meta">
          ${span ? `<span>${escapeHtml(span)}</span>` : ''}<span>${f.teams}팀</span>
          <span>${f.kind === 'outcome' ? '정답 행사' : '신호 행사'}</span>
        </span>
      </a>
    </li>`;
}

const GROUPS = [
  { key: 'teams', label: '팀', row: teamRow },
  { key: 'venues', label: '공연장', row: venueRow },
  { key: 'cities', label: '도시', row: cityRow },
  { key: 'festivals', label: '페스티벌', row: festivalRow },
];

function groupHtml(group, res, expanded) {
  const { total, items } = res;
  if (!total) return '';
  const shown = expanded ? items : items.slice(0, PAGE_LIMIT);
  const more = total > shown.length
    ? `<button type="button" class="btn btn-sm sr-more" data-expand="${group.key}">${group.label} ${total}개 모두 보기</button>`
    : '';
  return `
    <section class="block sr-group" aria-labelledby="srh-${group.key}">
      <h2 class="sr-group-title" id="srh-${group.key}">${group.label} <span class="sr-count">${total}</span></h2>
      <ul class="sr-list">${shown.map(group.row).join('')}</ul>
      ${more}
    </section>`;
}

function browseHtml(idx) {
  const cities = (idx.cities || []).map(c => `<a class="btn btn-sm" href="${escapeHtml(cityHash(c.name))}">${escapeHtml(c.name)}</a>`).join(' ');
  const fests = (idx.festivals || []).map(f => `<a class="btn btn-sm" href="${escapeHtml(festivalHash(f.key))}">${escapeHtml(f.label)}</a>`).join(' ');
  return `
    <p class="muted">팀·공연장·도시·페스티벌 이름(한글·영문 별칭 포함)을 넣어 주세요. 위쪽 검색창은 <kbd>/</kbd> 로도 열려요.</p>
    ${cities ? `<section class="block"><h2 class="sr-group-title">도시</h2><div class="sr-chips">${cities}</div></section>` : ''}
    ${fests ? `<section class="block"><h2 class="sr-group-title">페스티벌</h2><div class="sr-chips">${fests}</div></section>` : ''}`;
}

export async function renderSearchView(root) {
  const expanded = new Set();
  root.innerHTML = `
    <section class="search-view">
      <h1 class="view-title">검색</h1>
      <form class="sr-form" role="search" onsubmit="return false">
        <label class="sr-visually-hidden" for="srInput">검색어</label>
        <input type="search" id="srInput" class="f-search-input sr-input" autocomplete="off"
          placeholder="팀·공연장·도시·페스티벌 이름" value="${escapeHtml(appState.searchQuery || '')}">
      </form>
      <div id="srResults" aria-live="polite"><p class="muted">불러오는 중…</p></div>
    </section>`;
  const input = root.querySelector('#srInput');
  const out = root.querySelector('#srResults');
  const idx = await loadSearchIndex();
  if (!root.isConnected) return;

  function paint() {
    const q = (appState.searchQuery || '').trim();
    if (!q) {
      out.innerHTML = browseHtml(idx);
      return;
    }
    const limits = Object.fromEntries(GROUPS.map(g => [g.key, ALL_LIMIT]));
    const res = searchAll(q, idx, limits);
    const total = GROUPS.reduce((n, g) => n + res[g.key].total, 0);
    if (!total) {
      out.innerHTML = `
        <section class="block">
          <p>"${escapeHtml(q)}" — 아직 우리 기록에 없는 이름이에요.</p>
          <p class="muted">철자·띄어쓰기를 바꿔 보거나, 우리 기록에 빠진 팀이면
            <a href="${REPORT_URL}" target="_blank" rel="noopener noreferrer">제보하기(이슈 양식)</a>로 알려 주세요.</p>
        </section>`;
      return;
    }
    const summary = GROUPS.filter(g => res[g.key].total).map(g => `${g.label} ${res[g.key].total}`).join(' · ');
    out.innerHTML = `<p class="muted sr-summary">"${escapeHtml(q)}" — ${escapeHtml(summary)}</p>`
      + GROUPS.map(g => groupHtml(g, res[g.key], expanded.has(g.key))).join('');
    wireAvatarFallbacks(out);
  }

  let timer = null;
  input.addEventListener('input', () => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      appState.searchQuery = input.value.trim().slice(0, 100);
      expanded.clear();
      try {
        window.history.replaceState(null, '', appState.searchQuery ? searchPageHash(appState.searchQuery) : '#/search');
      } catch (_) { /* 주소를 못 바꿔도 결과는 보여 줌 */ }
      paint();
    }, DEBOUNCE_MS);
  });
  out.addEventListener('click', e => {
    const more = e.target.closest('[data-expand]');
    if (more) {
      expanded.add(more.dataset.expand);
      paint();
      return;
    }
    const teamLink = e.target.closest('a[data-team-key]');
    if (teamLink && !e.metaKey && !e.ctrlKey) {
      e.preventDefault();
      navigateTo('team', teamLink.dataset.teamKey);
    }
  });
  paint();
  if (!appState.searchQuery) input.focus();
}
