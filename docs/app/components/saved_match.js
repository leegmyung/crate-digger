/**
 * 저장 필터(5-1·5-2) 규칙 — 다른 모듈을 부르지 않는 순수 함수.
 * 후보 목록 화면과 '이번 주 브리핑' 카드·저장 때 미리보기가 같은 규칙을 쓰게 여기 한 곳에 둔다.
 * (첫 발매 N개월 규칙은 cand_filters.js 가 다시 내보내 후보 목록도 같은 함수를 쓴다.)
 */
import { isoMinusDays } from './team_metrics.js';

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const NAME_MAX = 60;
const GRADUATED = 4;
const TIER_RANK = { S: 1, M: 2, L: 3, XL: 4 };

/** 기준일(asOf)에서 N개월 전 ISO 날짜(YYYY-MM-DD) */
export function subtractMonthsIso(asOf, months) {
  const base = DATE_RE.test(String(asOf || '')) ? String(asOf) : '2026-11-27';
  const [y, m, d] = base.split('-').map(Number);
  const dt = new Date(Date.UTC(y, m - 1 - Number(months || 0), d));
  return dt.toISOString().slice(0, 10);
}

/** 첫 발매일이 기준일 전 N개월 이내인지 (N=0 이면 조건 없음) */
export function matchesReleaseMonths(firstRelease, months, asOf) {
  const m = Number(months) || 0;
  if (m <= 0) return true;
  const fr = String(firstRelease || '').trim().slice(0, 10);
  if (!DATE_RE.test(fr)) return false;
  const cut = subtractMonthsIso(asOf, m);
  return fr >= cut && fr <= String(asOf || '9999-12-31');
}

/**
 * 화면 상태 → 저장 규격. 기준일(as_of)은 빼서 '언제 보든 그날 기준'으로 다시 계산한다.
 * '변화'(새로 들어옴·상승·예정 공연) 조건은 날짜마다 뜻이 달라 새로 맞는 팀 계산에서 뺀다(moveIgnored).
 */
export function specFromState(s) {
  const { as_of: _drop, ...cfg } = s.cfg || {};
  return {
    cfg: { ...cfg, branches: Array.isArray(cfg.branches) ? [...cfg.branches] : cfg.branches },
    stage: String(s.candStage || ''),
    rm: Number(s.candReleaseMonths) || 0,
    region: String(s.candRegion || ''),
    preset: String(s.candPreset || ''),
    query: String(s.candQuery || '').trim(),
    periodDays: Number(cfg.period_days) || 0,
    moveIgnored: Boolean(s.candMove),
    city: String(s.candCity || ''),
    tier: String(s.candTier || ''),
    genreInf: String(s.candGenreInf || ''),
    genre: String(cfg.genre || ''),
  };
}

/**
 * 후보 행에 저장 필터의 화면 쪽 조건(단계·첫 발매·지역·기간·검색어)을 건다. 원본은 바꾸지 않는다.
 * @param {object[]} rows 후보 SQL 결과(또는 단계 0·4 행)
 * @param {{ stage?: string, rm?: number, region?: string, query?: string, periodDays?: number,
 *           city?: string, tier?: string, genreInf?: string, genre?: string }} spec
 * @param {{ stageByTeam: Map, firstRelease: Map, homeCity: Map, maxTier?: Map, genreConf?: Map }} ctx
 *   city = 활동 도시 · tier = 가장 큰 무대 체급 상한(S·M·L, 체급 모르는 팀은 뺌) · genreInf 'exclude' = 장르를 골랐을 때 추정 장르 팀 빼기
 */
export function filterSavedRows(rows, spec, asOf, ctx) {
  const stage = String(spec.stage || '');
  const q = String(spec.query || '').trim().toLowerCase();
  const fromDate = spec.periodDays > 0 ? isoMinusDays(asOf, spec.periodDays) : null;
  return (rows || []).filter(r => {
    const st = ctx.stageByTeam.get(r.team_key);
    if (stage ? String(st) !== stage : st === GRADUATED) return false;
    if (spec.rm > 0 && !matchesReleaseMonths(ctx.firstRelease.get(r.team_key) || r.first_release, spec.rm, asOf)) return false;
    if (spec.region === 'non_seoul') {
      const city = ctx.homeCity.get(r.team_key) || '';
      if (!city || city === '서울') return false;
    }
    if (fromDate && !(r.last_seen && String(r.last_seen).slice(0, 10) >= fromDate)) return false;
    if (spec.city && (ctx.homeCity.get(r.team_key) || '') !== spec.city) return false;
    if (spec.tier) {
      const rank = TIER_RANK[ctx.maxTier?.get(r.team_key)];
      if (!rank || rank > TIER_RANK[spec.tier]) return false;
    }
    if (spec.genreInf === 'exclude' && spec.genre && ctx.genreConf?.get(r.team_key) === 'inferred') return false;
    if (q) {
      const hay = `${r.display_name || ''} ${r.team_key || ''} ${r.primary_genre || ''}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
}

/** 이번 결과에는 있고 지난 결과에는 없던 팀 */
export function newMatches(nowRows, prevRows) {
  const prev = new Set((prevRows || []).map(r => r.team_key));
  return (nowRows || []).filter(r => !prev.has(r.team_key));
}

/** 적용된 필터 꼬리표 글자들 → 저장 필터 문장 이름 */
export function savedFilterName(chipLabels) {
  const parts = (chipLabels || []).map(s => String(s).trim()).filter(Boolean);
  if (!parts.length) return '전체 후보 (기본 조건)';
  const name = parts.join(' · ');
  return name.length > NAME_MAX ? `${name.slice(0, NAME_MAX - 1)}…` : name;
}
