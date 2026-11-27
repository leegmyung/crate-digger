/**
 * 6-4: 위 가운데 넓은 검색 — 팀·공연장 혼합 자동완성, '/' 단축키, 한글·영문 별칭,
 * 키보드 위아래·Enter 이동, 375px 아이콘 → 펼침.
 */
import { appState, navigateTo } from '../state.js';
import {
  loadVenueProfiles, queryDiscoveryStages, queryTeamLastSeenMap,
} from '../db.js';
import {
  avatarHtml, escapeHtml, STAGE_META, wireAvatarFallbacks,
} from '../ui.js';

/** 주요 공연장 한글·영문 별칭 (venue_profiles.json aliases 필드가 없을 때도 양방향 매칭) */
const VENUE_ALIAS_PAIRS = [
  ['club ff', ['클럽 에프에프', '클럽에프에프', '에프에프', 'ff']],
  ['club bbang', ['클럽 빵', '클럽빵', '빵']],
  ['club victim', ['클럽 빅팀', '클럽빅팀', '빅팀']],
  ['club sharp', ['클럽 샤프', '클럽샤프', '샤프']],
  ['strange fruit', ['스트레인지 프룻', '스트레인지프룻', '스푸']],
  ['롤링홀', ['rolling hall', 'rollinghall']],
  ['상상마당', ['sangsangmadang', 'kt&g 상상마당', 'ktg']],
  ['웨스트브릿지', ['west bridge', 'westbridge']],
  ['벨로주', ['veloso', '벨로주 홍대', '벨로주 망원']],
  ['제비다방', ['jebidabang', '취한제비']],
  ['베이비돌', ['baby doll', 'babydoll']],
  ['채널1969', ['channel 1969', 'channel1969', '채널 1969']],
  ['언플러그드', ['unplugged', '카페 언플러그드', 'cafe unplugged']],
  ['프리버드', ['freebird', 'free bird']],
  ['네스트나다', ['nest nada', 'nestnada']],
  ['무신사 개러지', ['musinsa garage', 'musinsagarage', '개러지']],
  ['cj아지트', ['cj azit', 'cjazit', '광흥창']],
  ['a.o.r', ['aor', '에이오알']],
  ['bender', ['벤더', '클럽 벤더']],
  ['노들섬', ['nodeul', 'nodeul island']],
  ['스페이스 브릭', ['space brick', 'spacebrick']],
  ['예스24', ['yes24', '예스24 라이브홀', '예스24 원더로크홀']],
  ['언더스테이지', ['understage', '현대카드 언더스테이지']],
  ['살롱 문보우', ['salon moonbow', 'moonbow']],
  ['생기스튜디오', ['senggi', 'senggi studio']],
  ['오방가르드', ['ovantgarde', '부산 오방가르드']],
  ['얼라이브홀', ['alive hall', 'alivehall']],
  ['프리즘홀', ['prism hall', 'prismhall']],
  ['퍼플홀', ['purple hall', 'purplehall']],
  ['스틸페이스', ['steel face', 'steelface']],
  ['구름아래소극장', ['gureum', '구름아래']],
  ['고창석', []],
  ['인디팍', ['indiepark']],
  ['클럽 온에어', ['club on air', 'onair']],
  ['몽향라이브홀', ['monghyang']],
];

const TIER_KO = { S: '소형', M: '중형', L: '대형', XL: '초대형' };

function norm(s) {
  return String(s || '').toLowerCase().replace(/[\s._\-·()[\]]+/g, '');
}

function extraVenueAliases(name) {
  const low = String(name || '').toLowerCase();
  const out = [];
  for (const [needle, aliases] of VENUE_ALIAS_PAIRS) {
    if (low.includes(needle)) {
      out.push(...aliases);
    } else if (aliases.some(a => {
      const al = a.toLowerCase();
      return al.length >= 3 ? low.includes(al) : low === al;
    })) {
      out.push(needle, ...aliases);
    }
  }
  return out;
}

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

  let venueIndex = null;       // [{ name, normName, searchKeys, city, tier, discovery, rank, last_night }]
  let stageByTeam = null;      // Map<team_key, { stage, stage_label }>
  let lastSeenByTeam = null;   // Map<team_key, isoDate>
  let enrichPromise = null;
  let activeIdx = -1;

  function ensureEnriched() {
    if (venueIndex && stageByTeam && lastSeenByTeam) return Promise.resolve();
    if (enrichPromise) return enrichPromise;
    if (!appState.ready) return Promise.resolve();

    const asOf = appState.cfg.as_of || appState.dataEnd || '2026-11-27';
    enrichPromise = Promise.all([
      loadVenueProfiles().catch(() => null),
      queryDiscoveryStages({ as_of: asOf }).catch(() => null),
      queryTeamLastSeenMap().catch(() => null),
    ]).then(([vp, stData, lsMap]) => {
      if (vp && vp.venues) {
        const list = Object.entries(vp.venues).map(([name, info]) => {
          const rawAliases = [
            ...(Array.isArray(info.aliases) ? info.aliases : []),
            ...extraVenueAliases(name),
          ];
          const searchKeys = [name, ...rawAliases].map(norm).filter(Boolean);
          return {
            name,
            lowName: name.toLowerCase(),
            normName: norm(name),
            searchKeys,
            city: String(info.city || ''),
            tier: String(info.tier || ''),
            discovery: Number(info.discovery) || 0,
            nights: Number(info.nights) || 0,
            last_night: String(info.last_night || '').slice(0, 10),
          };
        });
        list.sort((a, b) => (b.discovery - a.discovery) || (b.nights - a.nights));
        list.forEach((v, i) => { v.rank = i + 1; });
        venueIndex = list;
      } else {
        venueIndex = [];
      }
      stageByTeam = stData?.byTeam || new Map();
      lastSeenByTeam = lsMap || new Map();
    }).finally(() => {
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
    drop.hidden = true;
    activeIdx = -1;
    inp.value = '';
    setMobileSearchOpen(false);
    if (teamKey) navigateTo('team', teamKey);
    else if (venueName) navigateTo('venue', venueName);
  }

  function searchTeams(qLow, qNorm) {
    if (!appState.teamIndex.length) return [];
    const latestSnap = appState.snapshots?.latest || new Map();
    const matches = [];
    for (const t of appState.teamIndex) {
      const dn = String(t.display_name || '').toLowerCase();
      const tk = String(t.team_key || '').toLowerCase();
      const dnNorm = norm(t.display_name);
      const tkNorm = norm(t.team_key);
      let prio = -1;
      if (dn.startsWith(qLow) || tk.startsWith(qLow)) prio = 0;
      else if (dn.includes(qLow) || tk.includes(qLow)) prio = 1;
      else if (qNorm && (dnNorm.includes(qNorm) || tkNorm.includes(qNorm))) prio = 2;
      if (prio < 0) continue;

      const snap = latestSnap.get(t.team_key);
      const rank = snap?.rank ? Number(snap.rank) : null;
      const st = stageByTeam?.get(t.team_key) || null;
      const lastSeen = lastSeenByTeam?.get(t.team_key) || '';
      matches.push({ t, prio, rank, st, lastSeen });
    }
    matches.sort((a, b) => (
      (a.prio - b.prio)
      || ((a.rank ?? 99999) - (b.rank ?? 99999))
      || (b.lastSeen.localeCompare(a.lastSeen))
    ));
    return matches.slice(0, 7);
  }

  function searchVenues(qLow, qNorm) {
    if (!venueIndex || !venueIndex.length) return [];
    const matches = [];
    for (const v of venueIndex) {
      let prio = -1;
      if (v.lowName.startsWith(qLow)) prio = 0;
      else if (v.lowName.includes(qLow)) prio = 1;
      else if (qNorm && v.searchKeys.some(k => k.startsWith(qNorm))) prio = 1;
      else if (qNorm && v.searchKeys.some(k => k.includes(qNorm))) prio = 2;
      if (prio < 0) continue;
      matches.push({ v, prio });
    }
    matches.sort((a, b) => (a.prio - b.prio) || (a.v.rank - b.v.rank));
    return matches.slice(0, 5);
  }

  function renderDrop() {
    const rawQ = inp.value.trim();
    const qLow = rawQ.toLowerCase();
    const qNorm = norm(rawQ);
    activeIdx = -1;
    inp.removeAttribute('aria-activedescendant');

    if (!qLow) {
      drop.hidden = true;
      drop.innerHTML = '';
      return;
    }

    ensureEnriched();

    const teamHits = searchTeams(qLow, qNorm);
    const venueHits = searchVenues(qLow, qNorm);

    if (!teamHits.length && !venueHits.length) {
      drop.innerHTML = '<div class="f-search-empty">일치하는 팀이나 공연장이 없습니다.</div>';
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
        return `
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
