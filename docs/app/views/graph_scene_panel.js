// 씬 네트워크(graph_scene.js)의 칩·옆 패널·말풍선·검색 목록 HTML. 디자인은 팀 관계망과 같은 css/graph.css(.rg-*)
import {
  avatarHtml, escapeHtml, fmtInt, fmtNum, formatNextGigText, playButtonHtml, TERMS,
} from '../ui.js';

const NEIGHBOR_MAX = 10;
const MEMBER_MAX = 12;
const TOP_COMMUNITIES = 5;
const TOP_TEAMS = 6;

/** 팀 상태 꼬리표: 'A등급 수상·선정' · '후보 12위' · '후보' */
export function sceneRoleText(n) {
  if (n.had_outcome) return n.outcome_grade ? `${n.outcome_grade}등급 ${TERMS.outcome}` : TERMS.outcomeTeam;
  return n.cand_rank ? `후보 ${fmtInt(n.cand_rank)}위` : '후보';
}

function commLabel(c) {
  return `묶음 ${fmtInt(c.id)}${c.topVenues?.[0] ? ` · ${c.topVenues[0]}` : ''}`;
}

/** 위 칩 줄: 씬 묶음(고르면 그 묶음만 밝게) + 역할(누르면 숨김) */
export function sceneChipsHtml({ communities, colorOf, activeCommId, counts, hiddenRoles }) {
  const comm = (communities || []).slice(0, 8).map((c) => {
    const on = activeCommId === c.id;
    return `<button type="button" class="rg-chip sn-comm${on ? ' is-on' : ''}" data-sn-comm="${c.id}" aria-pressed="${on}" style="--c:${escapeHtml(colorOf(c))}"
      title="씬 묶음 ${fmtInt(c.id)} (${fmtInt(c.count)}팀) ${on ? '강조 풀기' : '만 밝게'}"><i class="rg-dot" aria-hidden="true"></i>${escapeHtml(commLabel(c))}<span class="rg-chip-n">${fmtInt(c.count)}</span></button>`;
  }).join('');
  const roles = [['cand', '신인 후보'], ['winner', TERMS.outcomeTeam]].map(([key, label]) => {
    const on = !hiddenRoles.has(key);
    return `<button type="button" class="rg-chip sn-role${on ? '' : ' is-off'}" data-sn-role="${key}" aria-pressed="${on}"
      title="${escapeHtml(label)} ${on ? '숨기기' : '보이기'}"><i class="sn-role-mark is-${key}" aria-hidden="true"></i>${escapeHtml(label)}<span class="rg-chip-n">${fmtInt(counts.get(key) || 0)}</span></button>`;
  }).join('');
  return `${comm}<span class="sn-chip-gap" aria-hidden="true"></span>${roles}`;
}

/** 마우스 올렸을 때 말풍선 */
export function sceneTooltipHtml(n) {
  const comm = n.communityId !== null && n.communityId !== undefined ? `묶음 ${n.communityId}` : '작은 씬';
  return `<div class="gt-head"><strong>${escapeHtml(n.display_name)}</strong></div>
    <div class="gt-sub">${escapeHtml(sceneRoleText(n))} · ${fmtNum(n.score, 1)}점 · ${escapeHtml(comm)} · 연결 ${fmtInt(n.degree)}</div>`;
}

/** 검색 결과 목록 */
export function searchMenuHtml(hits, total, colorOf) {
  if (!hits.length) return `<div class="scene-search-empty">지금 그림(${fmtInt(total)}팀)에 맞는 팀이 없습니다</div>`;
  return hits.map(n => `
    <button type="button" class="scene-search-opt" data-sn-pick="${escapeHtml(n.id)}">
      <span class="scene-search-opt-left"><i class="rg-dot" style="--c:${escapeHtml(colorOf(n))}" aria-hidden="true"></i><strong>${escapeHtml(n.display_name)}</strong></span>
      <span class="small muted">${escapeHtml(sceneRoleText(n))} · ${fmtNum(n.score, 1)}점</span>
    </button>`).join('');
}

function teamRow(n, colorOf, meta) {
  return `<li><button type="button" class="rg-nb" data-sn-jump="${escapeHtml(n.id)}">
    <i class="rg-dot" style="--c:${escapeHtml(colorOf(n))}" aria-hidden="true"></i>
    <span class="rg-nb-name">${escapeHtml(n.display_name)}${n.had_outcome ? ' <em class="sn-win-tag">수상</em>' : ''}</span>
    <span class="rg-nb-meta">${escapeHtml(meta)}</span>
  </button></li>`;
}

const GRIP = '<div class="rg-p-grip" aria-hidden="true"></div>';
const CLOSE = '<button type="button" class="rg-p-close" data-sn-close aria-label="선택 닫기">✕</button>';

const HOW_TO_READ = `
  <div class="rg-p-guide">
    <h4>읽는 법</h4>
    <ul>
      <li><i class="rg-key-size" aria-hidden="true"></i>동그라미 크기 = 오늘 점수</li>
      <li><i class="rg-key-color" aria-hidden="true"></i>색 = 씬 묶음 (자주 같이 서는 팀끼리)</li>
      <li><i class="sn-role-mark is-winner" aria-hidden="true"></i>굵은 테두리 = ${escapeHtml(TERMS.outcomeTeam)}</li>
      <li><i class="rg-key-line" aria-hidden="true"></i>선 굵기 = 같은 무대에 함께 선 횟수</li>
    </ul>
    <p class="rg-p-tip">마우스를 올리면 함께 선 팀만 밝게 · 누르면 자세히 · 두 번 누르면 팀 페이지 · 휠·두 손가락으로 확대</p>
  </div>`;

function summaryHtml({ stats, communities, topTeams, colorOf }) {
  const comms = (communities || []).slice(0, TOP_COMMUNITIES).map(c => `
    <li><button type="button" class="rg-nb" data-sn-comm-pick="${c.id}">
      <i class="rg-dot" style="--c:${escapeHtml(colorOf(c))}" aria-hidden="true"></i>
      <span class="rg-nb-name">${escapeHtml(commLabel(c))}</span><span class="rg-nb-meta">${fmtInt(c.count)}팀</span>
    </button></li>`).join('');
  const teams = (topTeams || []).slice(0, TOP_TEAMS).map(n => teamRow(n, colorOf, `${fmtNum(n.score, 1)}점`)).join('');
  return `
    <div class="rg-p-head sn-p-summary">
      <span class="rg-p-icon sn-p-icon" aria-hidden="true">씬</span>
      <div class="rg-p-title">
        <span class="rg-pill"><i class="rg-dot" aria-hidden="true"></i>${escapeHtml(stats.genre || '전체 장르')}</span>
        <h3>${fmtInt(stats.teams)}팀 · 연결 ${fmtInt(stats.links)}</h3>
        <p class="rg-p-sub">신인 후보 ${fmtInt(stats.cand)} · ${escapeHtml(TERMS.outcome)} ${fmtInt(stats.winners)}</p>
      </div>
    </div>
    ${comms ? `<div class="rg-p-nbs"><h4>큰 씬 묶음</h4><ul class="rg-nb-list">${comms}</ul></div>` : ''}
    ${teams ? `<div class="rg-p-nbs"><h4>점수 높은 팀</h4><ul class="rg-nb-list">${teams}</ul></div>` : ''}
    ${HOW_TO_READ}`;
}

function communityHtml({ community, members, colorOf }) {
  const venues = (community.topVenues || []).map(v => `<a href="#/venue/${encodeURIComponent(v)}">${escapeHtml(v)}</a>`).join(' · ');
  const rows = (members || []).slice(0, MEMBER_MAX).map(n => teamRow(n, colorOf, `${fmtNum(n.score, 1)}점`)).join('');
  const more = members.length > MEMBER_MAX ? `<li class="rg-nb-more">외 ${fmtInt(members.length - MEMBER_MAX)}팀</li>` : '';
  return `${GRIP}
    <div class="rg-p-head">
      <span class="rg-p-icon sn-p-icon" style="--c:${escapeHtml(colorOf(community))}" aria-hidden="true">${fmtInt(community.id)}</span>
      <div class="rg-p-title">
        <span class="rg-pill" style="--c:${escapeHtml(colorOf(community))}"><i class="rg-dot" aria-hidden="true"></i>씬 묶음</span>
        <h3>씬 묶음 ${fmtInt(community.id)}</h3>
        <p class="rg-p-sub">자주 같은 무대에 서는 ${fmtInt(community.count)}팀</p>
      </div>
      ${CLOSE}
    </div>
    ${venues ? `<p class="rg-p-rel">주로 서는 곳: ${venues}</p>` : ''}
    <div class="rg-p-nbs"><h4>이 묶음 팀 <span>${fmtInt(members.length)}</span></h4><ul class="rg-nb-list">${rows}${more}</ul></div>`;
}

function teamHtml({ node, neighbors, colorOf, nextGig }) {
  const comm = node.communityId !== null && node.communityId !== undefined
    ? `씬 묶음 ${node.communityId}${node.communityVenues?.length ? ` (${node.communityVenues.slice(0, 2).join(' · ')})` : ''}`
    : '작은 씬';
  const sub = [node.primary_genre, `${fmtNum(node.score, 2)}점`, comm].filter(Boolean).join(' · ');
  const rows = neighbors.slice(0, NEIGHBOR_MAX).map(({ neighbor, weight }) => teamRow(neighbor, colorOf, `같은 무대 ${fmtInt(Math.round(weight))}번`)).join('');
  const more = neighbors.length > NEIGHBOR_MAX ? `<li class="rg-nb-more">외 ${fmtInt(neighbors.length - NEIGHBOR_MAX)}팀</li>` : '';
  const color = colorOf(node);
  return `${GRIP}
    <div class="rg-p-head">
      ${avatarHtml(node.team_key, node.display_name, 52, { shape: 'circle', genre: node.primary_genre })}
      <div class="rg-p-title">
        <span class="rg-pill" style="--c:${escapeHtml(color)}"><i class="rg-dot" aria-hidden="true"></i>${escapeHtml(sceneRoleText(node))}</span>
        <h3>${escapeHtml(node.display_name)}</h3>
        <p class="rg-p-sub">${escapeHtml(sub)}</p>
      </div>
      ${CLOSE}
    </div>
    <p class="rg-p-rel">최근 1년 공연 <b>${fmtInt(node.gigs_1y)}번</b> · 공연장 <b>${fmtInt(node.venues)}곳</b>${nextGig ? `<span class="rg-p-where">다음 공연 ${escapeHtml(formatNextGigText(nextGig))}</span>` : ''}</p>
    <div class="rg-p-actions">
      ${playButtonHtml(node.team_key, node.display_name, { variant: 'sm' })}
      <a class="btn btn-sm btn-primary" href="#/team/${encodeURIComponent(node.team_key)}">팀 페이지 →</a>
    </div>
    <div class="rg-p-nbs"><h4>같은 무대에 선 팀 <span>${fmtInt(neighbors.length)}</span></h4>
      ${rows ? `<ul class="rg-nb-list">${rows}${more}</ul>` : '<p class="rg-p-empty">지금 고른 팀 수 안에서는 같은 무대 연결이 없습니다.</p>'}
    </div>`;
}

/**
 * 옆 패널 (좁은 칸에서는 아래 시트). mode: 'summary' | 'community' | 'team'
 */
export function scenePanelHtml(p) {
  if (p.mode === 'team' && p.node) return teamHtml(p);
  if (p.mode === 'community' && p.community) return communityHtml(p);
  return summaryHtml(p);
}
