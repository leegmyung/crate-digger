/**
 * 공연장 종류·별칭·확실도 표시 도우미 — 다른 모듈을 부르지 않는 순수 함수.
 * 자료: venue_profiles.json 의 type·type_label·type_basis·aliases·capacity_confidence (scripts/venue_profiles.py).
 */

export const UNKNOWN_TYPE = '__unknown__';
const UNKNOWN_LABEL = '유형 미정';
const CONFIDENCE = { high: '높음', mid: '보통', medium: '보통', low: '낮음' };

/** 공연장 종류 이름표(없으면 '유형 미정') */
export function venueTypeLabel(v) {
  if (!v || !v.type) return UNKNOWN_LABEL;
  return v.type_label || String(v.type);
}

/**
 * 운영 상태 배지 — 폐업·휴업·옮김만 표시(운영·확인 필요는 표시 안 함).
 * 자료: venue_profiles.json 의 status·status_label·status_note·moved_to (config/venues_kr.json).
 * @param {object} v 공연장 프로필
 * @param {(s: string) => string} esc HTML 이스케이프 함수
 */
export function venueStatusBadge(v, esc) {
  if (!v) return '';
  const note = v.status_note || '';
  if (v.status === 'closed' || v.status === 'paused') {
    const label = v.status_label || (v.status === 'closed' ? '폐업' : '휴업');
    return `<span class="venue-status-pill is-${v.status}" title="${esc(note)}">${esc(label)}</span>`;
  }
  if (v.moved_to) {
    return `<span class="venue-status-pill is-moved" title="${esc(`옮긴 곳: ${v.moved_to}${note ? ` — ${note}` : ''}`)}">이전</span>`;
  }
  return '';
}

/** 목록 '유형' 필터 선택지 — 많은 순, '유형 미정'은 맨 뒤 */
export function venueTypeOptions(list) {
  const counts = new Map();
  let unknown = 0;
  for (const v of list || []) {
    if (!v || !v.type) {
      unknown += 1;
      continue;
    }
    const cur = counts.get(v.type) || { value: v.type, label: venueTypeLabel(v), n: 0 };
    counts.set(v.type, { ...cur, n: cur.n + 1 });
  }
  const opts = [...counts.values()].sort((a, b) => b.n - a.n || a.label.localeCompare(b.label));
  return unknown ? [...opts, { value: UNKNOWN_TYPE, label: UNKNOWN_LABEL, n: unknown }] : opts;
}

const squash = s => String(s || '').toLowerCase().replace(/\s+/g, '');

/** 이름·별칭(한/영) 검색 — 대소문자·띄어쓰기 무시 */
export function matchesVenueQuery(v, query) {
  const q = squash(query);
  if (!q) return true;
  return [v?.name, ...(Array.isArray(v?.aliases) ? v.aliases : [])].some(n => squash(n).includes(q));
}

/** 수용 인원 확실도 낱말 */
export function confidenceLabel(c) {
  return CONFIDENCE[String(c || '').toLowerCase()] || '';
}

/** 공연장 이름 대신 인스타 계정('@계정')이 들어온 표기(기획사·레이블 계정 — 공연장 아님) */
export function isInstaAccountName(name) {
  return String(name || '').startsWith('@');
}
