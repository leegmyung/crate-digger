/**
 * 5-5 공연장 구독 — 브라우저 저장(localStorage). 막혀 있으면 이 탭 안에서만 기억한다.
 * 구독한 공연장의 소식(여기 처음 선 신인·큰 공연장 첫 무대·새 공연)은 alerts.json 근거의 공연장 이름으로 고른다.
 */
const KEY = 'cd_venue_subs_v1';
const MAX_SUBS = 30;
let memory = [];
let writeBlocked = false;

export function listVenueSubs() {
  if (writeBlocked) return [...memory];
  try {
    const raw = window.localStorage.getItem(KEY);
    if (raw) {
      const arr = JSON.parse(raw);
      if (Array.isArray(arr)) memory = arr.filter(v => typeof v === 'string' && v.trim()).slice(0, MAX_SUBS);
    }
  } catch (_) {
    // 막혔거나 깨짐 → 메모리 값
  }
  return [...memory];
}

function persist(list) {
  memory = list.slice(0, MAX_SUBS);
  try {
    window.localStorage.setItem(KEY, JSON.stringify(memory));
    return true;
  } catch (_) {
    writeBlocked = true;
    return false;
  }
}

export function isVenueSubscribed(venue) {
  return listVenueSubs().includes(venue);
}

/** @returns {{ subscribed: boolean, persisted: boolean }} */
export function toggleVenueSub(venue) {
  const v = String(venue || '').trim();
  const list = listVenueSubs();
  const on = !list.includes(v);
  const persisted = persist(on ? [...list, v] : list.filter(x => x !== v));
  window.dispatchEvent(new CustomEvent('app:venue-subs'));
  return { subscribed: on, persisted };
}

/** 구독 공연장 소식으로 보는 알림 종류 */
const SUB_TYPES = new Set(['big_venue_first', 'new_gig', 'blank_first_mention', 'peer_winner']);

/**
 * alerts.json 에서 구독 공연장이 근거에 있는 알림. 공연장별 묶음.
 * @returns {Map<string, object[]>}
 */
export function alertsForSubscribedVenues(alertsData, subs = listVenueSubs()) {
  const out = new Map();
  if (!alertsData || !Array.isArray(alertsData.alerts) || !subs.length) return out;
  const set = new Set(subs);
  for (const a of alertsData.alerts) {
    if (!SUB_TYPES.has(a.type)) continue;
    const venues = new Set((a.evidence || []).map(e => String(e?.venue || '').trim()).filter(v => set.has(v)));
    for (const v of venues) {
      if (!out.has(v)) out.set(v, []);
      out.get(v).push(a);
    }
  }
  return out;
}
