/**
 * 4-4 공연장 목록 탭 — 검색 · 도시 · 체급 막대(눌러서 고르기) · 유형 · 예정 공연 있음 · 정렬(발굴 주목도 기본),
 * 좌표가 있는 곳은 SVG 점 지도(외부 지도 타일 없음), 카드마다 최근 12개월 월별 공연 막대 12개.
 * 자료: venue_profiles.json (scripts/venue_profiles.py)
 */
import { appState } from '../state.js';
import { loadVenueProfiles } from '../db.js';
import {
  escapeHtml, fmtInt, fmtNum, INFO_TIPS, infoTip, naCell,
} from '../ui.js';

const TIERS = ['S', 'M', 'L', 'XL', '?'];
const TIER_LABEL = { S: 'S', M: 'M', L: 'L', XL: 'XL', '?': '모름' };
const CARDS_FIRST = 24;
const MONTH_SCALE_MIN = 8; // 월별 막대 눈금 최소(공연일)
const SORTS = {
  discovery: { label: '발굴 주목도', fn: v => v.discovery?.score ?? -1 },
  nights12: { label: '최근 12개월 공연', fn: v => v.discovery?.nights_12m ?? sumLast12(v) },
  share: { label: '첫 출연 비율', fn: v => v.first_timer_share_1y ?? -1 },
  winners: { label: '나중에 상 받은 팀', fn: v => v.later_winners_total ?? 0 },
  name: { label: '이름', fn: v => v.name },
};
const st = { q: '', city: '', tiers: new Set(), upcoming: false, sort: 'discovery', limit: CARDS_FIRST };

function tierKey(v) {
  const t = String(v.tier || '').toUpperCase();
  return TIERS.includes(t) ? t : '?';
}

function lastMonths(asOf, n = 12) {
  const [y, m] = String(asOf).split('-').map(Number);
  const out = [];
  for (let i = n - 1; i >= 0; i -= 1) {
    const d = new Date(Date.UTC(y, m - 1 - i, 1));
    out.push(d.toISOString().slice(0, 7));
  }
  return out;
}

function sumLast12(v) {
  return lastMonths(appState.dataEnd || '2026-11-28').reduce((s, ym) => s + (Number(v.monthly?.[ym]) || 0), 0);
}

function filtered(all) {
  const q = st.q.trim().toLowerCase();
  return all.filter(v => (!q || v.name.toLowerCase().includes(q))
    && (!st.city || v.city === st.city)
    && (!st.tiers.size || st.tiers.has(tierKey(v)))
    && (!st.upcoming || Number(v.upcoming_nights) > 0));
}

function tierBarsHtml(list) {
  const counts = Object.fromEntries(TIERS.map(t => [t, 0]));
  for (const v of list) counts[tierKey(v)] += 1;
  const max = Math.max(1, ...Object.values(counts));
  return `<div class="vl-tier-bars" role="group" aria-label="체급으로 고르기">
    ${TIERS.map(t => `
      <button type="button" class="vl-tier-btn${st.tiers.has(t) ? ' is-active' : ''}" data-vl-tier="${t}" aria-pressed="${st.tiers.has(t)}">
        <span class="vl-tier-name">${TIER_LABEL[t]}</span>
        <span class="vl-tier-track"><span class="vl-tier-fill" style="width:${((counts[t] / max) * 100).toFixed(0)}%"></span></span>
        <span class="vl-tier-cnt">${fmtInt(counts[t])}</span>
      </button>`).join('')}
  </div>`;
}

function filtersHtml(all) {
  const cities = [...new Set(all.map(v => v.city).filter(Boolean))]
    .map(c => [c, all.filter(v => v.city === c).length])
    .sort((a, b) => b[1] - a[1]);
  return `
    <div class="vl-filters">
      <input type="search" class="input vl-search" data-vl-q value="${escapeHtml(st.q)}" placeholder="공연장 이름 검색" aria-label="공연장 이름 검색">
      <select class="select" data-vl-city aria-label="도시">
        <option value="">모든 도시 (${fmtInt(all.length)})</option>
        ${cities.map(([c, n]) => `<option value="${escapeHtml(c)}"${st.city === c ? ' selected' : ''}>${escapeHtml(c)} (${fmtInt(n)})</option>`).join('')}
      </select>
      <select class="select" disabled aria-label="유형" title="공연장 유형(클럽·라이브홀·카페·소극장) 자료를 아직 모으는 중입니다"><option>유형: 자료 준비 중</option></select>
      <label class="vl-check"><input type="checkbox" data-vl-upcoming${st.upcoming ? ' checked' : ''}> 예정 공연 있음</label>
      <select class="select" data-vl-sort aria-label="정렬">
        ${Object.entries(SORTS).map(([k, s]) => `<option value="${k}"${st.sort === k ? ' selected' : ''}>정렬: ${s.label}</option>`).join('')}
      </select>
    </div>
    ${tierBarsHtml(all.filter(v => (!st.city || v.city === st.city)))}`;
}

/** 위경도 → SVG 좌표(위도 36도 기준 경도 줄임). 고른 점들 범위에 맞춤 */
function mapHtml(list) {
  const hasNum = x => x !== null && x !== undefined && x !== '' && Number.isFinite(Number(x)); // Number(null) 은 0 이라 따로 거름
  const pts = list.filter(v => hasNum(v.lat) && hasNum(v.lon));
  if (!pts.length) return '<p class="small muted vl-map-empty">좌표가 있는 공연장이 없습니다.</p>';
  const W = 320;
  const H = 360;
  const PAD = 18;
  const k = Math.cos((36 * Math.PI) / 180);
  const xs = pts.map(v => Number(v.lon) * k);
  const ys = pts.map(v => Number(v.lat));
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const span = Math.max(x1 - x0, y1 - y0, 0.02);
  const scale = (Math.min(W, H) - PAD * 2) / span;
  const px = v => PAD + (Number(v.lon) * k - x0) * scale;
  const py = v => H - PAD - (Number(v.lat) - y0) * scale;
  const dots = pts
    .sort((a, b) => (a.discovery?.score ?? 0) - (b.discovery?.score ?? 0))
    .map(v => {
      const r = 3 + Math.min(6, Math.sqrt(Number(v.discovery?.nights_12m) || 0) / 2.2);
      return `<a href="#/venue/${encodeURIComponent(v.name)}" aria-label="${escapeHtml(v.name)}"><circle class="vl-dot tier-${tierKey(v) === '?' ? 'u' : tierKey(v).toLowerCase()}" cx="${px(v).toFixed(1)}" cy="${py(v).toFixed(1)}" r="${r.toFixed(1)}"><title>${escapeHtml(`${v.name} · ${v.city || ''} · 체급 ${TIER_LABEL[tierKey(v)]}${v.discovery?.score !== undefined ? ` · 주목도 ${fmtNum(v.discovery.score, 1)}` : ''}`)}</title></circle></a>`;
    }).join('');
  const noGeo = list.length - pts.length;
  return `
    <figure class="vl-map">
      <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="공연장 위치 점 지도 (${fmtInt(pts.length)}곳)">${dots}</svg>
      <figcaption class="small muted">점 = 공연장(크기 = 최근 12개월 공연일, 색 = 체급) · 지도 바탕 없이 좌표만${noGeo ? ` · 좌표 없는 ${fmtInt(noGeo)}곳 빠짐` : ''}</figcaption>
    </figure>`;
}

function monthBarsHtml(v, months) {
  const vals = months.map(ym => Number(v.monthly?.[ym]) || 0);
  const max = Math.max(MONTH_SCALE_MIN, ...vals); // 한 달 1~2회뿐인 곳이 꽉 찬 막대로 보이지 않게
  return `<div class="vl-months" role="img" aria-label="최근 12개월 월별 공연일 ${vals.join(', ')}">
    ${vals.map((n, i) => `<span class="vl-month" style="height:${Math.max(n ? 12 : 4, (n / max) * 100).toFixed(0)}%" title="${months[i]} ${n}일"></span>`).join('')}
  </div>`;
}

function cardHtml(v, months) {
  const share = v.first_timer_share_1y;
  const disc = v.discovery?.score;
  return `
    <li class="vl-card">
      <div class="vl-card-head">
        <a class="vl-card-name" href="#/venue/${encodeURIComponent(v.name)}">${escapeHtml(v.name)}</a>
        <span class="vl-card-disc" title="발굴 주목도 0~100">${disc !== undefined && disc !== null ? fmtNum(disc, 1) : '—'}</span>
      </div>
      <div class="vl-card-meta small muted">
        ${escapeHtml(v.city || '도시 모름')} · 체급 ${TIER_LABEL[tierKey(v)]}${v.capacity ? ` (~${fmtInt(v.capacity)}명)` : ''} · 유형 미정
        ${Number(v.upcoming_nights) > 0 ? `<span class="venue-upcoming-pill">예정 ${fmtInt(v.upcoming_nights)}일</span>` : ''}
      </div>
      ${monthBarsHtml(v, months)}
      <div class="vl-card-kpis small">
        <span>12개월 <strong>${fmtInt(v.discovery?.nights_12m ?? sumLast12(v))}</strong>일</span>
        <span>첫 출연 <strong>${share !== null && share !== undefined ? `${Math.round(share * 100)}%` : '—'}</strong></span>
        <span>정답 전 <strong>${fmtInt(v.later_winners_total || 0)}</strong>팀</span>
      </div>
    </li>`;
}

/** @param {HTMLElement} host */
export async function renderVenueListTab(host) {
  const vp = await loadVenueProfiles();
  if (!vp?.venues) {
    host.innerHTML = `<section class="block">${naCell('공연장 프로필(venue_profiles.json)이 아직 없습니다', { block: true })}</section>`;
    return;
  }
  const all = Object.entries(vp.venues).map(([name, v]) => ({ name, ...v }));
  const months = lastMonths(vp.as_of || appState.dataEnd || '2026-11-28');

  const paint = () => {
    const list = filtered(all).sort((a, b) => {
      const fn = SORTS[st.sort]?.fn || SORTS.discovery.fn;
      const va = fn(a);
      const vb = fn(b);
      return st.sort === 'name' ? String(va).localeCompare(String(vb)) : (vb - va) || a.name.localeCompare(b.name);
    });
    const shown = list.slice(0, st.limit);
    host.innerHTML = `
      <section class="block vl-block">
        <div class="block-head">
          <div><h2>공연장 목록${infoTip('발굴 주목도', INFO_TIPS.venue_discovery, { compact: true })}</h2>
          <span class="block-meta">${fmtInt(list.length)} / ${fmtInt(all.length)}곳 · 기준 ${escapeHtml(vp.as_of || '')}</span></div>
        </div>
        ${filtersHtml(all)}
        <div class="vl-body">
          ${mapHtml(list)}
          <div class="vl-cards-wrap">
            ${shown.length ? `<ul class="vl-cards">${shown.map(v => cardHtml(v, months)).join('')}</ul>` : '<p class="small muted">조건에 맞는 공연장이 없습니다.</p>'}
            ${list.length > shown.length ? `<div class="more-row"><span>${fmtInt(shown.length)} / ${fmtInt(list.length)}곳</span><button type="button" class="btn btn-sm" data-vl-more="1">24곳 더 보기</button></div>` : ''}
          </div>
        </div>
      </section>`;
  };

  host.addEventListener('click', (e) => {
    const tierBtn = e.target.closest('[data-vl-tier]');
    if (tierBtn) {
      const t = tierBtn.dataset.vlTier;
      if (st.tiers.has(t)) st.tiers.delete(t); else st.tiers.add(t);
      st.limit = CARDS_FIRST;
      paint();
      host.querySelector(`[data-vl-tier="${t}"]`)?.focus();
      return;
    }
    if (e.target.closest('[data-vl-more]')) { st.limit += CARDS_FIRST; paint(); }
  });
  host.addEventListener('change', (e) => {
    const el = e.target;
    if (el.matches('[data-vl-city]')) st.city = el.value;
    else if (el.matches('[data-vl-sort]')) st.sort = el.value;
    else if (el.matches('[data-vl-upcoming]')) st.upcoming = el.checked;
    else return;
    st.limit = CARDS_FIRST;
    paint();
  });
  let qTimer = null;
  host.addEventListener('input', (e) => {
    if (!e.target.matches('[data-vl-q]')) return;
    st.q = e.target.value;
    clearTimeout(qTimer);
    qTimer = setTimeout(() => {
      const pos = e.target.selectionStart;
      st.limit = CARDS_FIRST;
      paint();
      const inp = host.querySelector('[data-vl-q]');
      inp?.focus();
      inp?.setSelectionRange(pos, pos);
    }, 250);
  });
  paint();
}
