/**
 * 자동 문장 — Chartmetric '이벤트 분석기 요약'·'주목할 만한 통찰력'·'알림 예측'을 우리 데이터로.
 * 순수 함수 (tests/js/insight_text.test.mjs). 그리기는 views/team_events.js · views/team.js · views/cand_saved.js.
 */

const WINDOW_DAYS = 28;
/** 전후 28일을 세는 사건 (event_stars.py 와 같은 묶음) */
const WINDOW_KINDS = new Set(['selection', 'big_venue_first', 'magazine', 'outcome', 'first_seoul_gig']);
const PAST_WINDOWS = 6;          // 이상치 기준: 지난 6개 4주 창(24주)
const MIN_SPIKE = 3;             // 최근 4주 이 건수 이상일 때만 '늘었다'고 말함
const SPIKE_RATIO = 2;           // 평소의 2배 이상
const MIN_BUSY_BASELINE = 3;     // 평소 4주 평균이 이 이상인데 0건이면 '조용함'
const DAY_MS = 86400000;

function isNum(v) {
  return typeof v === 'number' && Number.isFinite(v);
}

function signed(x) {
  const s = Math.abs(x).toFixed(1);
  return x < 0 ? `−${s}` : `+${s}`;
}

function pairText(label, before, after) {
  return isNum(before) && isNum(after) ? `${label} ${before}→${after}건` : '';
}

function isComplete(ev) {
  return !isNum(ev.after_days) || ev.after_days >= WINDOW_DAYS;
}

/**
 * 사건 하나 → "선정 뒤 28일 공연 1→4건 · 언급 0→3건". 대상이 아니거나 숫자가 없으면 ''.
 * @param {{ kind: string, kind_label: string, gigs_before: number|null, gigs_after: number|null,
 *           mentions_before: number|null, mentions_after: number|null, after_days: number|null }} ev
 */
export function eventAfterSentence(ev) {
  if (!ev || !WINDOW_KINDS.has(ev.kind)) return '';
  const parts = [pairText('공연', ev.gigs_before, ev.gigs_after), pairText('언급', ev.mentions_before, ev.mentions_after)].filter(Boolean);
  if (!parts.length) return '';
  const span = isComplete(ev) ? `${WINDOW_DAYS}일` : `${ev.after_days}일(진행 중)`;
  return `${ev.kind_label || ev.kind} 뒤 ${span} ${parts.join(' · ')}`;
}

/**
 * 팀의 큰 사건들 → "큰 사건 n건 뒤 28일 평균: 공연 +a건 · 언급 +b건 (사건 전 28일 대비) — 가장 크게 늘어난 건 …".
 * 28일이 다 지난 사건만, 기준일 이전 사건만 센다. 없으면 ''.
 * @param {object[]} events
 * @param {string} asOf YYYY-MM-DD
 */
export function eventsSummarySentence(events, asOf) {
  const done = (events || []).filter(e => WINDOW_KINDS.has(e.kind) && String(e.date) <= asOf && isComplete(e)
    && isNum(e.gigs_before) && isNum(e.gigs_after));
  if (!done.length) return '';
  const avg = arr => arr.reduce((s, x) => s + x, 0) / arr.length;
  const gigDiffs = done.map(e => e.gigs_after - e.gigs_before);
  const menEvents = done.filter(e => isNum(e.mentions_before) && isNum(e.mentions_after));
  const menTxt = menEvents.length ? ` · 언급 ${signed(avg(menEvents.map(e => e.mentions_after - e.mentions_before)))}건` : '';
  const best = done.reduce((b, e) => (e.gigs_after - e.gigs_before > b.gigs_after - b.gigs_before ? e : b), done[0]);
  const bestTxt = best.gigs_after > best.gigs_before
    ? ` — 가장 크게 늘어난 건 ${best.kind_label || best.kind}(${best.date}) 공연 ${best.gigs_before}→${best.gigs_after}건`
    : '';
  return `큰 사건 ${done.length}건 뒤 ${WINDOW_DAYS}일 평균: 공연 ${signed(avg(gigDiffs))}건${menTxt} (사건 전 ${WINDOW_DAYS}일 대비)${bestTxt}`;
}

/**
 * 최근 4주 신호 수를 지난 24주의 4주 평균과 비교 → 눈에 띄면 { kind: 'up'|'first'|'quiet', text }, 아니면 null.
 * @param {Array<{ signal_date: string }>} timeline
 * @param {string} asOf YYYY-MM-DD
 */
export function timelineAnomaly(timeline, asOf) {
  const end = Date.parse(`${asOf}T00:00:00Z`);
  if (!Number.isFinite(end)) return null;
  const counts = new Array(PAST_WINDOWS + 1).fill(0);   // 0 = 최근 4주, 1~6 = 그 앞 창
  for (const s of timeline || []) {
    const t = Date.parse(`${String(s?.signal_date || '').slice(0, 10)}T00:00:00Z`);
    if (!Number.isFinite(t) || t > end) continue;
    const w = Math.floor((end - t) / DAY_MS / WINDOW_DAYS);
    if (w <= PAST_WINDOWS) counts[w] += 1;
  }
  const recent = counts[0];
  const base = counts.slice(1).reduce((s, x) => s + x, 0) / PAST_WINDOWS;
  const weeks = PAST_WINDOWS * 4;
  if (recent >= MIN_SPIKE && base === 0) {
    return { kind: 'first', text: `최근 4주 신호 ${recent}건 — 지난 ${weeks}주엔 없던 움직임` };
  }
  if (recent >= MIN_SPIKE && base > 0 && recent >= SPIKE_RATIO * base) {
    return { kind: 'up', text: `최근 4주 신호 ${recent}건 — 평소(지난 ${weeks}주의 4주 평균 ${base.toFixed(1)}건)의 ${(recent / base).toFixed(1)}배` };
  }
  if (recent === 0 && base >= MIN_BUSY_BASELINE) {
    return { kind: 'quiet', text: `최근 4주 신호 0건 — 평소(4주 평균 ${base.toFixed(1)}건)보다 조용함` };
  }
  return null;
}

/**
 * 저장 필터(알림 규칙) 미리보기 문장.
 * @param {{ total: number, weekly: number[], cap?: number }} p weekly = 주마다 새로 걸린 팀 수, [지난주, 2주 전, 3주 전, 4주 전];
 *   cap = 후보 표 한도(limit) — total 이 여기 닿으면 실제로는 더 많을 수 있어 '이상'으로 적음
 */
export function alertForecastText({ total, weekly, cap = 0 }) {
  if (!total) return '지금 이 조건에 맞는 팀이 없습니다 — 저장해도 알림이 오지 않아요';
  const w = (weekly || []).filter(isNum);
  const capped = cap > 0 && total >= cap;
  const head = `지금 이 조건에 맞는 팀 ${total}팀${capped ? ' 이상(후보 표 한도)' : ''}`;
  if (!w.length) return head;
  const sum = w.reduce((s, x) => s + x, 0);
  if (!sum) return `${head} · 최근 ${w.length}주 새로 걸린 팀 없음 → 알림이 거의 안 올 조건 (조건을 넓혀 보세요)`;
  const oldToNew = [...w].reverse().join('·');
  return `${head} · 최근 ${w.length}주 새로 걸린 팀 ${oldToNew} (오래된 주 → 지난주) → 이 규칙이면 한 주 평균 ${(sum / w.length).toFixed(1)}건 알림`;
}

/**
 * 공연장 구독 미리보기 — 이번 주 알림 중 이 공연장이 근거인 것의 종류별 건수.
 * @param {Record<string, number>} counts 종류 → 건수
 * @param {Record<string, string>} labels 종류 → 이름 (alerts.json types)
 */
export function venueSubForecastText(counts, labels = {}) {
  const entries = Object.entries(counts || {}).filter(([, n]) => isNum(n) && n > 0).sort((a, b) => b[1] - a[1]);
  const total = entries.reduce((s, [, n]) => s + n, 0);
  if (!total) return '이번 주 알림 중 이 공연장 관련은 없어요 — 담아도 조용할 수 있어요';
  return `담으면 이번 주 알림 기준 ${total}건 (${entries.map(([k, n]) => `${labels[k] || k} ${n}`).join(' · ')})`;
}

// ---------- 공연장 질문형 요약 (docs/ux_simplify_2026-11-28.md ⑩) ----------
const TIER_RANK = { S: 1, M: 2, L: 3, XL: 4 };
const TIER_WORD = { S: '소형', M: '중형', L: '대형', XL: '초대형' };
const SHARE_OFTEN = 0.25;   // 첫 무대 신인 비율 이 이상 → '신인을 자주 세우는 곳'
const SHARE_RARE = 0.10;    // 이 미만 → '경력 팀이 주로'
const AFTER_SHOWN = 2;

function pct(x) {
  return `${Math.round(x * 100)}%`;
}

function earlyAnswer(p) {
  const teams = Number(p.teams_1y) || 0;
  if (!teams) return '최근 1년 출연 기록이 없어 아직 판단할 수 없어요';
  const share = Number(p.first_timer_share_1y);
  const firsts = Number(p.first_timers_1y) || 0;
  const tail = `최근 1년 ${teams}팀 중 ${firsts}팀(${isNum(share) ? pct(share) : '—'})이 여기서 첫 무대`;
  if (!isNum(share)) return tail;
  if (share >= SHARE_OFTEN) return `신인을 자주 세우는 곳 — ${tail}`;
  if (share < SHARE_RARE) return `경력 팀이 주로 서는 곳 — ${tail}`;
  return `신인과 경력 팀이 섞여 서는 곳 — ${tail}`;
}

function wentAnswer(p, tierOf) {
  const parts = [];
  const winners = Number(p.later_winners_total) || 0;
  const latest = [...(Array.isArray(p.later_winners) ? p.later_winners : [])]
    .sort((a, b) => String(b.outcome_date || '').localeCompare(String(a.outcome_date || '')))[0];
  if (winners) {
    parts.push(`나중에 수상·선정된 팀 ${winners}팀${latest ? ` (최근: ${latest.name || latest.team_key} — ${latest.outcome || '수상·선정'}${latest.outcome_date ? ` ${String(latest.outcome_date).slice(0, 7)}` : ''})` : ''}`);
  }
  const after = (Array.isArray(p.after) ? p.after : []).filter(a => Array.isArray(a) && a[0]);
  if (after.length) {
    const myRank = TIER_RANK[String(p.tier || '').toUpperCase()] || 0;
    const biggest = [...after].sort((a, b) => (TIER_RANK[tierOf.get(b[0])] || 0) - (TIER_RANK[tierOf.get(a[0])] || 0))[0];
    const bigTier = tierOf.get(biggest[0]);
    const top = after.slice(0, AFTER_SHOWN).map(([n, k]) => `${n}(${k}팀)`).join(' · ');
    const step = bigTier && (TIER_RANK[bigTier] || 0) > myRank ? ` · 가장 큰 다음 무대 ${biggest[0]}(${TIER_WORD[bigTier] || bigTier})` : '';
    parts.push(`다음으로 많이 선 곳 ${top}${step}`);
  }
  return parts.length ? parts.join(' · ') : '여기 선 뒤의 기록이 아직 모이지 않았어요';
}

function nowAnswer(p) {
  const cands = Array.isArray(p.top_candidates) ? p.top_candidates : [];
  if (!cands.length) return '최근 3년 여기 선 팀 중 지금 후보 순위권 팀은 없어요';
  const names = cands.slice(0, 3).map(c => `${c.name || c.team_key}${c.rank ? `(후보 ${c.rank}위)` : ''}`).join(' · ');
  return `여기 선 지금 후보 ${cands.length}팀 — ${names}`;
}

/**
 * 공연장 첫 화면 질문 3개와 답 (모든 공연장 같은 순서·같은 자리 — 자료가 없어도 답 자리를 비우지 않음).
 * @param {object|null} profile venue_profiles.json 한 공연장
 * @param {{ tierOf?: Map<string,string> }} [opts] 공연장 이름 → 체급(S·M·L·XL)
 * @returns {{ id: string, q: string, a: string }[]}
 */
export function venueQuestions(profile, { tierOf = new Map() } = {}) {
  if (!profile || typeof profile !== 'object') return [];
  return [
    { id: 'early', q: '신인을 일찍 세우는 곳인가?', a: earlyAnswer(profile) },
    { id: 'went', q: '여기서 공연한 신인이 어디까지 갔나?', a: wentAnswer(profile, tierOf) },
    { id: 'now', q: '지금 여기서 볼 만한 팀은?', a: nowAnswer(profile) },
  ];
}
