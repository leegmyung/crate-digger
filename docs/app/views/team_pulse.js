/**
 * 팀 상세 3-2 '4칸 상태 막대' + 3-3 '변화 줄'(7일/30일).
 * team.js 가 이미 커서 따로 둔다. 계산은 components/team_metrics.js(순수 함수).
 */
import { runRawSql, sqlStringLiteral } from '../db.js';
import {
  activityState, branchState, isoMinusDays, sceneState, stageRatio, windowCounts,
} from '../components/team_metrics.js';
import {
  escapeHtml, fmtInt, INFO_TIPS, infoTip, naCell, periodSwitch, STAGE_META, statusBar,
  wirePeriodSwitch,
} from '../ui.js';

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const ACTIVITY_DAYS = 180;
const PERIODS = [{ id: '7', label: '7일' }, { id: '30', label: '30일' }];
let changeDays = 7; // 이 세션 동안 기억

const sceneCache = new Map(); // `${team}|${asOf}` -> number|null

/**
 * 같은 날 같은 공연장에 선 팀 중, 그 공연 전에 이미 정답(수상·선정)을 받은 팀 수.
 * features.sql 의 gig·winner_first·peer_winner 와 같은 정의(기준일 전 것만).
 * @returns {Promise<number|null>} 실패하면 null(= 자료 없음)
 */
export async function queryScenePeerWinners(teamKey, asOf) {
  if (!teamKey || !DATE_RE.test(String(asOf || ''))) return null;
  const key = `${teamKey}|${asOf}`;
  if (sceneCache.has(key)) return sceneCache.get(key);
  const sql = `
    WITH gig AS (
      SELECT DISTINCT team_key, signal_date AS gig_date, venue FROM signals
      WHERE branch = '공연' AND COALESCE(venue, '') NOT IN ('', '공연장 미정')
        AND signal_date < DATE '${asOf}'
    ),
    winner_first AS (
      SELECT team_key, MIN(announced_date) AS first_outcome FROM outcomes
      WHERE counted AND announced_date < DATE '${asOf}' GROUP BY team_key
    )
    SELECT COUNT(DISTINCT b.team_key) AS n
    FROM gig a
    JOIN gig b ON b.gig_date = a.gig_date AND b.venue = a.venue AND b.team_key <> a.team_key
    JOIN winner_first wf ON wf.team_key = b.team_key AND wf.first_outcome <= a.gig_date
    WHERE a.team_key = ${sqlStringLiteral(teamKey)}`;
  let n = null;
  try {
    const res = await runRawSql(sql);
    const v = Number(res.rows[0]?.n);
    n = Number.isFinite(v) ? v : null;
  } catch (_) {
    n = null;
  }
  sceneCache.set(key, n);
  return n;
}

function countRecent(timeline, asOf, days) {
  const from = isoMinusDays(asOf, days);
  if (!from) return null;
  return (timeline || []).filter(s => {
    const d = String(s.signal_date || '').slice(0, 10);
    return s.role !== 'excluded' && d > from && d <= asOf;
  }).length;
}

function branchCount(scored, timeline, asOf) {
  if (scored && scored.n_branch !== null && scored.n_branch !== undefined) return Number(scored.n_branch);
  const set = new Set((timeline || [])
    .filter(s => s.role !== 'excluded' && String(s.signal_date || '').slice(0, 10) <= asOf && s.branch)
    .map(s => s.branch));
  return set.size;
}

/**
 * 3-2: 4칸 상태 막대 (375px 에선 2×2)
 * @param {{ stageInfo: object|null, scored: object|null, timeline: object[], sceneWinners: number|null, asOf: string }} ctx
 */
export function renderTeamStatusBarsHtml({ stageInfo, scored, timeline, sceneWinners, asOf }) {
  const stage = stageInfo ? Number(stageInfo.stage) : null;
  const stageMeta = stage !== null ? STAGE_META[stage] : null;
  const act = activityState(countRecent(timeline, asOf, ACTIVITY_DAYS));
  const br = branchState(branchCount(scored, timeline, asOf));
  const sc = sceneState(sceneWinners);
  const tip = (title, key) => infoTip(title, INFO_TIPS[key], { compact: true });
  const bars = [
    statusBar({
      title: '발굴 단계',
      stateLabel: stageMeta?.label || null,
      ratio: stageRatio(stage),
      lowLabel: '백지',
      highLabel: '졸업',
      infoTipHtml: tip('발굴 단계', 'status_stage'),
      naReason: '발굴 단계를 계산할 신호가 없습니다',
    }),
    statusBar({
      title: '최근 활동 (6개월)',
      stateLabel: act?.label || null,
      ratio: act?.ratio ?? null,
      lowLabel: '조용함',
      highLabel: '활발',
      infoTipHtml: tip('최근 활동', 'status_activity'),
      naReason: '활동 기록이 없습니다',
    }),
    statusBar({
      title: '신호 갈래',
      stateLabel: br?.label || null,
      ratio: br?.ratio ?? null,
      lowLabel: '1갈래',
      highLabel: '4갈래',
      infoTipHtml: tip('신호 갈래', 'status_branches'),
      naReason: '신호 기록이 없습니다',
    }),
    statusBar({
      title: '씬 연결',
      stateLabel: sc?.label || null,
      ratio: sc?.ratio ?? null,
      lowLabel: '연결 없음',
      highLabel: '수상 팀 10+',
      infoTipHtml: tip('씬 연결', 'status_scene'),
      naReason: '같은 무대 기록을 계산하지 못했습니다',
    }),
  ];
  const nextTxt = stageMeta?.next ? `<p class="team-pulse-next small muted">다음 단계: ${escapeHtml(stageMeta.next)}</p>` : '';
  return `<div class="team-status-grid">${bars.join('')}</div>${nextTxt}`;
}

function deltaHtml(cur, prev, days) {
  const d = cur - prev;
  if (d > 0) return `<span class="tc-delta is-up">▲${fmtInt(d)}</span> <span class="tc-delta-ref">직전 ${days}일보다</span>`;
  if (d < 0) return `<span class="tc-delta is-down">▼${fmtInt(-d)}</span> <span class="tc-delta-ref">직전 ${days}일보다</span>`;
  return `<span class="tc-delta is-flat">–</span> <span class="tc-delta-ref">직전 ${days}일과 같음</span>`;
}

function tile(title, bigHtml, deltaLine, baseTxt) {
  return `
    <div class="team-change-tile">
      <div class="tc-title">${escapeHtml(title)}</div>
      <div class="tc-big">${bigHtml}</div>
      <div class="tc-sub">${deltaLine}</div>
      <div class="tc-base">${escapeHtml(baseTxt)}</div>
    </div>`;
}

function rankTile(rc, days) {
  const useMonth = days >= 30;
  const refDate = rc ? (useMonth ? rc.month_date : rc.week_date) : null;
  const refWord = useMonth ? '지난달' : '지난주';
  if (!rc || rc.rank === null || rc.rank === undefined) {
    return tile('순위 변화', naCell('상위 300 스냅샷에 들지 않은 팀입니다', { label: '자료 없음' }), '', '상위 300 스냅샷 기준');
  }
  const big = `#${fmtInt(rc.rank)}`;
  if (!refDate) {
    return tile('순위 변화', big, naCell(`${refWord} 스냅샷이 아직 없습니다`, { label: '비교 자료 없음' }), `${refWord} 대비`);
  }
  const ch = useMonth ? rc.month_change : rc.week_change;
  const label = useMonth ? rc.month_label : rc.week_label;
  let sub;
  if (label === 'NEW') sub = '<span class="tc-delta is-up">NEW</span> <span class="tc-delta-ref">새로 상위 300 진입</span>';
  else if (ch > 0) sub = `<span class="tc-delta is-up">▲${fmtInt(ch)}</span> <span class="tc-delta-ref">계단 상승</span>`;
  else if (ch < 0) sub = `<span class="tc-delta is-down">▼${fmtInt(-ch)}</span> <span class="tc-delta-ref">계단 하락</span>`;
  else sub = '<span class="tc-delta is-flat">–</span> <span class="tc-delta-ref">그대로</span>';
  return tile('순위 변화', big, sub, `${refWord}(${refDate}) 대비`);
}

function renderChangeTilesHtml({ timeline, asOf, rc }, days) {
  const w = windowCounts(timeline, asOf, days);
  if (!w) return naCell('기준일을 알 수 없어 변화를 계산하지 못했습니다', { block: true });
  const base = `${w.from} ~ ${w.to}`;
  return [
    tile('새 신호', fmtInt(w.cur.signals), deltaHtml(w.cur.signals, w.prev.signals, days), base),
    tile('새 공연', fmtInt(w.cur.gigs), deltaHtml(w.cur.gigs, w.prev.gigs, days), base),
    tile('인스타 팔로워', naCell('인스타 팔로워는 이 팀에 아직 쌓인 기록이 없습니다', { label: '자료 없음' }), '', '수집이 쌓인 팀만 표시'),
    rankTile(rc, days),
  ].join('');
}

/**
 * 3-3: 변화 줄 (7일/30일 전환)
 * @param {{ timeline: object[], asOf: string, rc: object|null }} ctx
 */
export function renderChangeRowHtml(ctx) {
  return `
    <div class="team-change-head">
      <span class="team-change-title">변화${infoTip('변화 줄', INFO_TIPS.change_row, { compact: true })}</span>
      ${periodSwitch(PERIODS, { active: String(changeDays), name: 'teamChange', ariaLabel: '변화 기간' })}
    </div>
    <div class="team-change-row" id="teamChangeTiles">${renderChangeTilesHtml(ctx, changeDays)}</div>`;
}

export function wireChangeRow(root, ctx) {
  const host = root.querySelector('#teamPulseBlock');
  if (!host) return;
  wirePeriodSwitch(host, (val) => {
    const days = Number(val) === 30 ? 30 : 7;
    if (days === changeDays) return;
    changeDays = days;
    const tiles = host.querySelector('#teamChangeTiles');
    if (tiles) tiles.innerHTML = renderChangeTilesHtml(ctx, changeDays);
  });
}
