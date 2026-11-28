/**
 * 6-4: 위 가운데 넓은 검색 — 팀·공연장 혼합 자동완성, '/' 단축키, 한글·영문 별칭,
 * 키보드 위아래·Enter 이동, 375px 아이콘 → 펼침.
 */
import { appState, navigateTo } from '../state.js';
import {
  TIER_KO, loadSearchIndex, searchAll, cityHash, festivalHash, searchPageHash,
} from '../search_index.js';
import {
  avatarHtml, escapeHtml, playButtonHtml, STAGE_META, wireAvatarFallbacks,
} from '../ui.js';

function isEditableTarget(el) {
  if (!el) return false;
  const tag = (el.tagName || '').toLowerCase();
  if (tag === 'input' || tag === 'textarea' || tag === 'select') return true;
  return Boolean(el.isContentEditable);
}

export function initGlobalSearch() {
  const inp = document.getElementById('gfTeamSearch');
  const drop = document.getElementById('gfTeamDrop');
  const topRow = document.querySelector('.top-row');
  const mobileOpenBtn = document.getElementById('mobileSearchBtn');
  const mobileCloseBtn = document.getElementById('mobileSearchClose');
  if (!inp || !drop) return;

  let searchIdx = null;        // search_index.js loadSearchIndex() 결과 (공연장·도시·페스티벌 + 팀 단계·마지막 신호)
  let enrichPromise = null;
  let activeIdx = -1;

  function ensureEnriched() {
    if (searchIdx) return Promise.resolve();
    if (enrichPromise) return enrichPromise;
    if (!appState.ready) return Promise.resolve();
    enrichPromise = loadSearchIndex().then(idx => { searchIdx = idx; }).finally(() => {
      enrichPromise = null;
      if (document.activeElement === inp && inp.value.trim()) {
        renderDrop();
      }
    });
    return enrichPromise;
  }

  function setMobileSearchOpen(open) {
    if (!topRow) return;
    topRow.classList.toggle('is-search-open', open);
    mobileOpenBtn?.setAttribute('aria-expanded', open ? 'true' : 'false');
    if (open) {
      setTimeout(() => inp.focus(), 10);
    } else {
      drop.hidden = true;
      activeIdx = -1;
    }
  }

  function getOptionButtons() {
    return [...drop.querySelectorAll('.f-search-opt')];
  }

  function setActiveIndex(idx) {
    const opts = getOptionButtons();
    if (!opts.length) {
      activeIdx = -1;
      inp.removeAttribute('aria-activedescendant');
      return;
    }
    const clamped = ((idx % opts.length) + opts.length) % opts.length;
    activeIdx = clamped;
    opts.forEach((btn, i) => {
      const on = i === clamped;
      btn.classList.toggle('is-focused', on);
      btn.setAttribute('aria-selected', on ? 'true' : 'false');
      if (on) {
        inp.setAttribute('aria-activedescendant', btn.id);
        btn.scrollIntoView({ block: 'nearest' });
      }
    });
  }

  function pickOption(btn) {
    if (!btn) return;
    const teamKey = btn.dataset.pickTeam;
    const venueName = btn.dataset.pickVenue;
    const hash = btn.dataset.pickHash;              // 도시·페스티벌·'모두 보기'
    drop.hidden = true;
    activeIdx = -1;
    if (!hash || !hash.startsWith('#/search')) inp.value = '';
    setMobileSearchOpen(false);
    if (teamKey) navigateTo('team', teamKey);
    else if (venueName) navigateTo('venue', venueName);
    else if (hash) window.location.hash = hash;
  }

  function renderDrop() {
    const rawQ = inp.value.trim();
    const qLow = rawQ.toLowerCase();
    activeIdx = -1;
    inp.removeAttribute('aria-activedescendant');

    if (!qLow) {
      drop.hidden = true;
      drop.innerHTML = '';
      return;
    }

    ensureEnriched();

    const res = searchAll(rawQ, searchIdx, { teams: 7, venues: 5, cities: 3, festivals: 3 });
    const teamHits = res.teams.items;
    const venueHits = res.venues.items;
    const cityHits = res.cities.items;
    const festHits = res.festivals.items;
    const totalHits = res.teams.total + res.venues.total + res.cities.total + res.festivals.total;

    if (!totalHits) {
      drop.innerHTML = `<div class="f-search-empty">아직 우리 기록에 없는 이름입니다.
        <a href="${escapeHtml(searchPageHash(rawQ))}">검색 결과 화면에서 다시 보기</a></div>`;
      drop.hidden = false;
      return;
    }

    let optSeq = 0;
    const sections = [];

    if (teamHits.length) {
      const itemsHtml = teamHits.map(({ t, rank, st, lastSeen }) => {
        const id = `gsOpt${optSeq++}`;
        const stageLbl = st ? (STAGE_META[Number(st.stage)]?.label || st.stage_label || '') : '';
        const stageCls = st !== null && st !== undefined ? `stage-s${st.stage}` : '';
        // ▶ 는 고르기(option) 버튼 옆 형제로 둔다 — 버튼 안에 버튼을 넣지 않게. 누르면 드롭다운은 그대로, 아래 플레이어에서 재생
        return `
          <div class="f-search-row" role="presentation">
          <button type="button" id="${id}" class="f-search-opt" role="option" aria-selected="false" data-pick-team="${escapeHtml(t.team_key)}">
            <span class="f-search-opt-left">
              ${avatarHtml(t.team_key, t.display_name || t.team_key, 24, { shape: 'rounded', genre: t.primary_genre })}
              <span class="f-search-opt-name">${escapeHtml(t.display_name || t.team_key)}</span>
              ${stageLbl ? `<span class="f-search-stage ${stageCls}">${escapeHtml(stageLbl)}</span>` : ''}
            </span>
            <span class="f-search-opt-meta">
              ${rank ? `<span class="f-search-rank">#${rank}</span>` : ''}
              ${lastSeen ? `<span class="f-search-date">${escapeHtml(lastSeen.slice(2))}</span>` : (t.primary_genre ? `<span class="f-search-date">${escapeHtml(t.primary_genre)}</span>` : '')}
            </span>
          </button>
          ${playButtonHtml(t.team_key, t.display_name || t.team_key, { variant: 'icon' }).replace('<button ', '<button tabindex="-1" ')}
          </div>
        `;
      }).join('');
      sections.push(`<div class="f-search-group-label" role="presentation">팀</div>${itemsHtml}`);
    }

    if (venueHits.length) {
      const itemsHtml = venueHits.map(({ v }) => {
        const id = `gsOpt${optSeq++}`;
        const mono = (v.city || v.name || '공').slice(0, 2);
        const tagParts = [v.tier ? `${v.tier}(${TIER_KO[v.tier] || v.tier})` : '', v.city].filter(Boolean).join(' · ');
        return `
          <button type="button" id="${id}" class="f-search-opt" role="option" aria-selected="false" data-pick-venue="${escapeHtml(v.name)}">
            <span class="f-search-opt-left">
              <span class="f-search-venue-ico" aria-hidden="true">${escapeHtml(mono)}</span>
              <span class="f-search-opt-name">${escapeHtml(v.name)}</span>
              ${tagParts ? `<span class="f-search-stage">${escapeHtml(tagParts)}</span>` : ''}
            </span>
            <span class="f-search-opt-meta">
              ${v.rank ? `<span class="f-search-rank">#${v.rank}</span>` : ''}
              ${v.last_night ? `<span class="f-search-date">${escapeHtml(v.last_night.slice(2))}</span>` : ''}
            </span>
          </button>
        `;
      }).join('');
      sections.push(`<div class="f-search-group-label" role="presentation">공연장</div>${itemsHtml}`);
    }

    if (cityHits.length || festHits.length) {
      const cityHtml = cityHits.map(({ c }) => {
        const id = `gsOpt${optSeq++}`;
        return `
          <button type="button" id="${id}" class="f-search-opt" role="option" aria-selected="false" data-pick-hash="${escapeHtml(cityHash(c.name))}">
            <span class="f-search-opt-left">
              <span class="f-search-venue-ico" aria-hidden="true">${escapeHtml(c.name.slice(0, 2))}</span>
              <span class="f-search-opt-name">${escapeHtml(c.name)}</span>
              <span class="f-search-stage">도시</span>
            </span>
            <span class="f-search-opt-meta"><span class="f-search-date">공연장 ${c.venues} · 1년 첫 무대 ${c.firstStage1y}팀</span></span>
          </button>`;
      }).join('');
      const festHtml = festHits.map(({ f }) => {
        const id = `gsOpt${optSeq++}`;
        const span = f.years.length ? `${f.years[0]}${f.years.length > 1 ? `~${f.years[f.years.length - 1]}` : ''}` : '';
        return `
          <button type="button" id="${id}" class="f-search-opt" role="option" aria-selected="false" data-pick-hash="${escapeHtml(festivalHash(f.key))}">
            <span class="f-search-opt-left">
              <span class="f-search-venue-ico" aria-hidden="true">축</span>
              <span class="f-search-opt-name">${escapeHtml(f.label)}</span>
              <span class="f-search-stage">페스티벌</span>
            </span>
            <span class="f-search-opt-meta"><span class="f-search-date">${escapeHtml(span)} · ${f.teams}팀</span></span>
          </button>`;
      }).join('');
      sections.push(`<div class="f-search-group-label" role="presentation">도시 · 페스티벌</div>${cityHtml}${festHtml}`);
    }

    const shown = teamHits.length + venueHits.length + cityHits.length + festHits.length;
    sections.push(`
      <button type="button" id="gsOpt${optSeq++}" class="f-search-opt f-search-all" role="option" aria-selected="false" data-pick-hash="${escapeHtml(searchPageHash(rawQ))}">
        <span class="f-search-opt-left"><span class="f-search-opt-name">모두 보기 →</span></span>
        <span class="f-search-opt-meta"><span class="f-search-date">${totalHits > shown ? `${totalHits}개 중 ${shown}개 표시` : `${totalHits}개`}</span></span>
      </button>`);

    drop.innerHTML = sections.join('');
    wireAvatarFallbacks(drop);
    drop.hidden = false;
  }

  inp.addEventListener('input', renderDrop);
  inp.addEventListener('focus', () => {
    ensureEnriched();
    if (inp.value.trim()) renderDrop();
  });

  inp.addEventListener('keydown', e => {
    if (e.key === 'ArrowDown') {
      if (drop.hidden) renderDrop();
      const opts = getOptionButtons();
      if (opts.length) {
        e.preventDefault();
        setActiveIndex(activeIdx < 0 ? 0 : activeIdx + 1);
      }
    } else if (e.key === 'ArrowUp') {
      const opts = getOptionButtons();
      if (opts.length) {
        e.preventDefault();
        setActiveIndex(activeIdx < 0 ? opts.length - 1 : activeIdx - 1);
      }
    } else if (e.key === 'Enter') {
      const opts = getOptionButtons();
      const target = activeIdx >= 0 ? opts[activeIdx] : opts[0];
      if (target) {
        e.preventDefault();
        pickOption(target);
      }
    } else if (e.key === 'Escape') {
      e.preventDefault();
      drop.hidden = true;
      activeIdx = -1;
      setMobileSearchOpen(false);
      inp.blur();
    }
  });

  drop.addEventListener('click', e => {
    const btn = e.target.closest('.f-search-opt');
    if (btn) pickOption(btn);
  });

  mobileOpenBtn?.addEventListener('click', () => {
    const willOpen = !topRow?.classList.contains('is-search-open');
    setMobileSearchOpen(willOpen);
  });
  mobileCloseBtn?.addEventListener('click', () => setMobileSearchOpen(false));

  document.addEventListener('click', e => {
    if (!e.target.closest('.f-search-wrap') && !e.target.closest('#mobileSearchBtn')) {
      drop.hidden = true;
      activeIdx = -1;
    }
  });

  // Global '/' shortcut to focus search
  document.addEventListener('keydown', e => {
    if (e.key !== '/' || e.ctrlKey || e.metaKey || e.altKey) return;
    if (isEditableTarget(e.target)) return;
    e.preventDefault();
    setMobileSearchOpen(true);
    inp.focus();
    inp.select();
  });
}
