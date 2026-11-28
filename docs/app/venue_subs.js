/**
 * 5-5 공연장 구독 — '내 목록' 한 칸(mine_store.js)에 저장. 막혀 있으면 이 탭 안에서만 기억한다.
 * 구독한 공연장의 소식(여기 처음 선 신인·큰 공연장 첫 무대·새 공연)은 alerts.json 근거의 공연장 이름으로 고른다.
 */
import { readMineSection, writeMineSection } from './mine_store.js';

const MAX_SUBS = 30;
// 저장은 '내 목록' 한 칸(mine_store.js 의 venues) — 옛 키 cd_venue_subs_v1 은 처음 읽을 때 옮겨짐

export function listVenueSubs() {
  return readMineSection('venues').filter(v => typeof v === 'string' && v.trim()).slice(0, MAX_SUBS);
}

function persist(list) {
  return writeMineSection('venues', list.slice(0, MAX_SUBS));
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
