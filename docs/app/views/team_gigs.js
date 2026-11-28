/**
 * 팀 상세 3-6 '공연' 블록 — 최근 12개월 공연 수 · 공연장 체급 분포 · 자주 선 공연장 3 · 지역 분포 ·
 * 라인업 역할(단독/헤드라이너/서포트) · 다가오는 공연. 보조 파일이 없으면 그 칸만 '자료 없음'.
 */
import { gigSummary, lineupSplit } from '../components/team_metrics.js';
import {
  escapeHtml, fmtInt, formatNextGigText, INFO_TIPS, infoTip, naCell, renderNoRecordLine,
} from '../ui.js';

const UPCOMING_MAX = 5;
const TIER_ORDER = [['S', 'S'], ['M', 'M'], ['L', 'L'], ['XL', 'XL'], ['unknown', '모름']];

function pct(n, total) {
  return total > 0 ? Math.round((n / total) * 100) : 0;
}

/** 쌓은 막대(색은 --ramp-*, 모름은 --na-bg) + 범례 */
function stackHtml(parts, total, ariaLabel) {
  const segs = parts.filter(p => p.n > 0);
  const bar = segs.map(p => `<span class="gig-stack-seg ${p.cls}" style="width:${((p.n / total) * 100).toFixed(1)}%" title="${escapeHtml(`${p.label} ${p.n}회 (${pct(p.n, total)}%)`)}"></span>`).join('');
  const legend = parts.map(p => `<span class="gig-legend-item"><span class="gig-legend-dot ${p.cls}"></span>${escapeHtml(p.label)} ${fmtInt(p.n)}</span>`).join('');
  return `<div class="gig-stack" role="img" aria-label="${escapeHtml(ariaLabel)}">${bar}</div><div class="gig-legend">${legend}</div>`;
}

function cellHtml(title, bodyHtml) {
  return `<div class="gig-cell"><div class="gig-cell-title">${escapeHtml(title)}</div>${bodyHtml}</div>`;
}

function countCell(s) {
  const fest = s.festivals12 > 0 ? `<div class="small muted">페스티벌 ${fmtInt(s.festivals12)}회는 따로</div>` : '';
  return cellHtml('최근 12개월 공연', `<div class="gig-big">${fmtInt(s.total12)}<span class="gig-big-unit">회</span></div>${fest}`);
}

function tierCell(s) {
  if (!s.tierCounts) return cellHtml('공연장 크기', naCell('공연장 크기 자료(venue_tiers.csv)가 아직 없습니다', { block: true }));
  if (!s.total12) return cellHtml('공연장 크기', renderNoRecordLine('최근 12개월 공연 없음'));
  const parts = TIER_ORDER.map(([k, label], i) => ({
    label, n: s.tierCounts[k], cls: k === 'unknown' ? 'is-unknown' : `lv${i + 1}`,
  }));
  const unknownPct = pct(s.tierCounts.unknown, s.total12);
  return cellHtml('공연장 크기', `${stackHtml(parts, s.total12, '공연장 크기 분포')}<div class="small muted">크기 모름 ${unknownPct}%</div>`);
}

function venuesCell(s) {
  if (!s.topVenues.length) return cellHtml('자주 선 공연장', renderNoRecordLine('공연장 기록 없음'));
  const items = s.topVenues.map(v => `<li><a class="inline-venue-link" href="#/venue/${encodeURIComponent(v.venue)}">${escapeHtml(v.venue)}</a> <span class="muted">${fmtInt(v.n)}회</span></li>`).join('');
  return cellHtml('자주 선 공연장', `<ol class="gig-venue-list">${items}</ol>`);
}

function cityCell(s, teamCity) {
  const lines = [];
  if (teamCity) {
    const parts = [`활동 도시 <strong>${escapeHtml(teamCity.home_city || '모름')}</strong>`];
    if (teamCity.cities) parts.push(`도시 ${fmtInt(teamCity.cities)}곳`);
    if (teamCity.first_city && teamCity.first_city !== teamCity.home_city) parts.push(`첫 무대 ${escapeHtml(teamCity.first_city)}`);
    lines.push(`<div>${parts.join(' · ')}</div>`);
  }
  if (s.cityCounts && s.cityCounts.length) {
    const chips = s.cityCounts.slice(0, 5).map(c => `<span class="gig-city-chip">${escapeHtml(c.city)} ${fmtInt(c.n)}</span>`).join('');
    const unk = s.cityUnknown ? `<span class="small muted">도시 모름 ${fmtInt(s.cityUnknown)}</span>` : '';
    lines.push(`<div class="gig-city-chips">${chips}${unk}</div>`);
  }
  if (!lines.length) return cellHtml('지역 분포', naCell('팀별 활동 지역 자료(team_cities.csv)가 아직 없습니다', { block: true }));
  return cellHtml('지역 분포', lines.join(''));
}

function lineupCell(lineupMap, teamKey) {
  if (!lineupMap) return cellHtml('라인업 역할', naCell('라인업 역할 자료(lineup_roles.csv)가 아직 없습니다', { block: true }));
  const sp = lineupSplit(lineupMap.get(teamKey));
  if (!sp) return cellHtml('라인업 역할', renderNoRecordLine('역할을 가릴 공연 기록 없음'));
  const parts = [
    { label: '단독', n: sp.solo, cls: 'lv5' },
    { label: '헤드라이너', n: sp.headline, cls: 'lv4' },
    { label: '서포트', n: sp.support, cls: 'lv2' },
    { label: '모름', n: sp.unknown, cls: 'is-unknown' },
  ];
  const lr = lineupMap.get(teamKey);
  const note = lr.support_to_headline ? '<div class="small muted">서포트 → 헤드라이너로 올라선 기록 있음</div>' : '';
  return cellHtml('라인업 역할', `${stackHtml(parts, sp.total, '라인업 역할 비율')}${note}`);
}

function upcomingCell(upcomingList) {
  if (!upcomingList.length) return cellHtml('다가오는 공연', renderNoRecordLine('예정된 공연 기록 없음'));
  const items = upcomingList.slice(0, UPCOMING_MAX).map(g => {
    const venueOk = g.venue && g.venue !== '공연장 미정';
    const txt = escapeHtml(formatNextGigText(g));
    return `<li>${venueOk ? `<a class="next-gig-pill next-gig-pill-link" href="#/venue/${encodeURIComponent(g.venue)}">${txt}</a>` : `<span class="next-gig-pill">${txt}</span>`}</li>`;
  }).join('');
  const more = upcomingList.length - UPCOMING_MAX;
  return cellHtml('다가오는 공연', `<ul class="gig-upcoming-list">${items}</ul>${more > 0 ? `<div class="small muted">외 ${fmtInt(more)}건</div>` : ''}`);
}

/**
 * @param {{ teamKey: string, asOf: string, gigActs: object[], venueMeta: {tiers: Map|null, cities: Map|null}|null,
 *           lineupMap: Map|null, teamCity: object|null, upcomingList: object[] }} ctx
 */
export function renderGigBlockHtml(ctx) {
  const s = gigSummary({
    gigActs: ctx.gigActs,
    asOf: ctx.asOf,
    tiers: ctx.venueMeta?.tiers || null,
    cities: ctx.venueMeta?.cities || null,
  });
  const head = `
    <div class="block-head">
      <h2>공연${infoTip('공연 블록', INFO_TIPS.gig_block)}</h2>
      <span class="block-meta">기준일 전 12개월</span>
    </div>`;
  if (!s) return `${head}${naCell('기준일을 알 수 없어 공연을 집계하지 못했습니다', { block: true })}`;
  return `${head}
    <div class="gig-grid">
      ${countCell(s)}
      ${tierCell(s)}
      ${venuesCell(s)}
      ${cityCell(s, ctx.teamCity)}
      ${lineupCell(ctx.lineupMap, ctx.teamKey)}
      ${upcomingCell(ctx.upcomingList)}
    </div>`;
}
