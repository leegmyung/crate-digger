/**
 * 팀 상세 3-4 '점수 근거' = 항목 막대(누르면 근거 목록 펼침) + 동료 비교 막대.
 * 동료 비교: docs/lab/sql/peer_compare.sql — 기본 '같은 발굴 단계', 전환하면 '같은 단계 + 같은 장르'
 * (장르 이웃은 profile·press 장르 팀만, 추정 장르는 제외 — SQL 규칙 그대로).
 */
import { queryPeerCompare } from '../db_peer.js';
import { isoMinusDays, peerGradeWord, topSharePct } from '../components/team_metrics.js';
import {
  escapeHtml, fmtInt, fmtNum, INFO_TIPS, infoTip, itemBar, peerBar, STAGE_META,
} from '../ui.js';

const EVIDENCE_MAX = 8;

/** 점수 항목: key → 이웃 백분위 칸(peer_compare.sql) */
function scoreItemDefs(s) {
  return [
    { key: 'branch', label: `갈래 수 (${fmtInt(s.n_branch)}개)`, pts: s.pts_branch, pct: 'branch_pct' },
    { key: 'stage', label: `선정 최고 단계 (${fmtInt(s.best_stage)})`, pts: s.pts_stage, pct: 'stage_pct' },
    { key: 'venues', label: `서로 다른 공연장 (${fmtInt(s.venues)}곳)`, pts: s.pts_venues, pct: 'venues_pct' },
    { key: 'recent', label: `최근 6개월 활동 (${fmtInt(s.recent180)}건)`, pts: s.pts_recent },
    { key: 'winner', label: '이미 상 받은 팀과 같은 무대', pts: s.pts_winner, pct: 'winner_pct' },
    { key: 'outlets', label: `발굴 매체 (${fmtInt(s.outlets)}곳)`, pts: s.pts_outlets, pct: 'outlets_pct' },
    { key: 'context', label: `맥락 매체 (${fmtInt(s.context_outlets ?? 0)}곳)`, pts: s.pts_context, pct: 'context_pct' },
    { key: 'collab', label: `협업(기성 아티스트 ${fmtInt(s.collab_est ?? 0)}명)`, pts: s.pts_collab },
    { key: 'peer', label: '선정 팀과 같은 무대', pts: s.pts_peer },
    { key: 'dmz', label: 'DMZ 출연', pts: s.pts_dmz },
    { key: 'gigs', label: `최근 1년 공연 (${fmtInt(s.gigs_1y)}일)`, pts: s.pts_gigs, pct: 'gigs_pct' },
  ].filter(it => Number(it.pts) > 0);
}

function pastSignals(timeline, asOf) {
  return (timeline || []).filter(t => {
    const d = String(t.signal_date || '').slice(0, 10);
    return d && d <= asOf && t.role !== 'excluded';
  });
}

function countLines(items, keyFn, unit) {
  const m = new Map();
  for (const it of items) {
    const k = keyFn(it);
    if (k) m.set(k, (m.get(k) || 0) + 1);
  }
  return [...m.entries()].sort((a, b) => b[1] - a[1]).map(([k, n]) => `${k} ${fmtInt(n)}${unit}`);
}

/** 항목별 근거 줄 — 글자만(HTML 아님) */
function evidenceLines(key, timeline, asOf, nameOf) {
  const sig = pastSignals(timeline, asOf);
  const line = t => `${String(t.signal_date).slice(0, 10)} · ${nameOf(t)}${t.venue ? ` — ${t.venue}` : ''}`;
  const since = days => {
    const from = isoMinusDays(asOf, days);
    return sig.filter(t => String(t.signal_date).slice(0, 10) > from);
  };
  const byKey = {
    branch: () => countLines(sig, t => t.branch, '건'),
    stage: () => sig.filter(t => t.branch === '선정·지원' && t.program !== 'dmz_lineup').map(line),
    venues: () => countLines(sig.filter(t => t.branch === '공연'), t => t.venue, '회'),
    recent: () => since(180).map(line),
    outlets: () => sig.filter(t => t.branch === '큐레이션' && t.role === 'discovery').map(line),
    context: () => sig.filter(t => t.branch === '큐레이션' && t.role === 'context').map(line),
    dmz: () => sig.filter(t => t.program === 'dmz_lineup').map(line),
    gigs: () => since(365).filter(t => t.branch === '공연').map(line),
  };
  return byKey[key] ? byKey[key]() : [];
}

function renderEvidence(key, ctx) {
  if (key === 'winner' || key === 'peer') {
    return '<p class="small muted">같은 날 같은 공연장에 선 팀은 위 관계망에서 볼 수 있습니다. <a href="#teamGraphSection" data-score-jump="teamGraphSection">관계망으로 ↑</a></p>';
  }
  if (key === 'collab') return '<p class="small muted">협업 근거 목록은 아직 화면에 없습니다.</p>';
  const lines = evidenceLines(key, ctx.timeline, ctx.asOf, ctx.nameOf);
  if (!lines.length) return '<p class="small muted">이 항목의 근거 신호를 찾지 못했습니다(점수 계산 기간 밖일 수 있음).</p>';
  const shown = lines.slice(0, EVIDENCE_MAX);
  const more = lines.length - shown.length;
  return `<ul class="score-evidence-list">${shown.map(l => `<li>${escapeHtml(l)}</li>`).join('')}</ul>${more > 0 ? `<p class="small muted">외 ${fmtInt(more)}건 — 아래 사건 기록에서 모두 볼 수 있습니다</p>` : ''}`;
}

function scopeGroupLabel(peer, scope) {
  const stageLabel = STAGE_META[peer.stage]?.label || peer.stage_label || '';
  const base = scope === 'genre' && peer.primary_genre
    ? `같은 단계(${stageLabel}) · ${peer.primary_genre}`
    : `같은 발굴 단계(${stageLabel})`;
  return `${base} ${fmtInt(peer.peer_n)}팀 중`;
}

function renderPeerArea(peer, scope, error) {
  const tip = infoTip('동료 비교', INFO_TIPS.peer_compare, { compact: true });
  if (!peer) {
    const reason = error || (scope === 'genre'
      ? '같은 장르 이웃 비교 결과가 없습니다'
      : '이 팀은 점수 후보군(신인·유명 제외) 밖이라 이웃 비교가 없습니다');
    return peerBar({ label: '종합 점수', infoTipHtml: tip, naReason: reason });
  }
  const top = topSharePct(peer.top_share);
  return peerBar({
    label: '종합 점수',
    pct: top === null ? null : 100 - top,
    grade: peerGradeWord(peer.grade),
    groupLabel: scopeGroupLabel(peer, scope), // 오른쪽 값 칸이 '상위 x%'
    formatValue: v => (v <= 0 ? '낮음' : v >= 100 ? '높음' : fmtInt(v)),
    infoTipHtml: tip,
    naReason: '이웃 비교 값이 없습니다',
  });
}

function itemPeerNote(peer, it) {
  if (!peer || !it.pct || peer[it.pct] === null || peer[it.pct] === undefined) return '';
  const top = Math.max(1, Math.round((1 - peer[it.pct]) * 100));
  return `<span class="score-item-peer" title="같은 비교군 안에서 이 항목 점수의 위치">이웃 상위 ${top}%</span>`;
}

function renderItems(items, peer, ctx) {
  const max = Math.max(...items.map(it => Number(it.pts) || 0), 1);
  return items.map(it => `
    <details class="score-item" data-score-item="${escapeHtml(it.key)}">
      <summary>
        ${itemBar(it.label, Number(it.pts), max, { formatValue: v => `+${fmtNum(v, 2)}` })}
        ${itemPeerNote(peer, it)}
      </summary>
      <div class="score-evidence">${renderEvidence(it.key, ctx)}</div>
    </details>`).join('');
}

/**
 * @param {{ teamKey: string, scored: object|null, peer: object|null, peerError?: string, genreOk: boolean,
 *           timeline: object[], asOf: string, nameOf: (s: object) => string }} ctx
 * @param {'stage'|'genre'} [scope]
 */
export function renderScoreBodyHtml(ctx, scope = 'stage') {
  if (!ctx.scored) return '<p class="muted small" style="margin:0;">현재 필터·기간 조건 안의 점수가 없습니다.</p>';
  const items = scoreItemDefs(ctx.scored);
  const genreBtnAttr = ctx.genreOk ? '' : ' disabled title="장르가 비었거나 추정 장르라 같은 장르 이웃과 비교하지 않습니다"';
  return `
    <div class="score-peer">
      <div class="score-peer-head">
        <span class="score-peer-title">동료 비교</span>
        <div class="cf-view-switch" role="group" aria-label="비교 기준">
          <button type="button" class="cf-view-btn${scope === 'stage' ? ' is-active' : ''}" data-peer-scope="stage" aria-pressed="${scope === 'stage'}">같은 발굴 단계</button>
          <button type="button" class="cf-view-btn${scope === 'genre' ? ' is-active' : ''}" data-peer-scope="genre" aria-pressed="${scope === 'genre'}"${genreBtnAttr}>같은 장르 이웃</button>
        </div>
      </div>
      ${renderPeerArea(ctx.peer, scope, ctx.peerError)}
    </div>
    ${items.length
    ? `<div class="score-items" aria-label="점수 항목 (누르면 근거)">${renderItems(items, ctx.peer, ctx)}</div>
    <p class="small muted score-items-hint">막대를 누르면 그 항목의 근거 신호가 펼쳐집니다.</p>`
    : '<p class="small muted score-items-hint">점수에 더해진 항목이 없습니다.</p>'}`;
}

/** 비교 기준 전환 + 관계망 이동. ctx.peer 는 '같은 발굴 단계' 결과로 시작 */
export function wireScoreBlock(root, ctx) {
  const host = root.querySelector('#teamScoreBody');
  if (!host) return;
  const cache = { stage: { peer: ctx.peer, error: ctx.peerError || '' } };
  let scope = 'stage';
  host.addEventListener('click', async (e) => {
    const jump = e.target.closest('[data-score-jump]');
    if (jump) {
      e.preventDefault();
      root.querySelector(`#${jump.dataset.scoreJump}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      return;
    }
    const btn = e.target.closest('[data-peer-scope]');
    if (!btn || btn.disabled) return;
    const next = btn.dataset.peerScope === 'genre' ? 'genre' : 'stage';
    if (next === scope) return;
    scope = next;
    if (!cache[scope]) {
      const res = await queryPeerCompare({ as_of: ctx.asOf, team_key: ctx.teamKey, scope });
      cache[scope] = { peer: res.byTeam.get(ctx.teamKey) || null, error: res.error };
    }
    const openKeys = [...host.querySelectorAll('details.score-item[open]')].map(d => d.dataset.scoreItem);
    host.innerHTML = renderScoreBodyHtml({ ...ctx, peer: cache[scope].peer, peerError: cache[scope].error }, scope);
    for (const k of openKeys) host.querySelector(`details[data-score-item="${k}"]`)?.setAttribute('open', '');
    host.querySelector(`[data-peer-scope="${scope}"]`)?.focus();
  });
}
