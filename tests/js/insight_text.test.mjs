// 자동 문장: 사건 뒤 요약 · 팀 이상치 · 알림 규칙 미리보기 — 순수 함수 검사 (node --test)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  eventAfterSentence, eventsSummarySentence, timelineAnomaly, alertForecastText, venueSubForecastText,
} from '../../docs/app/insight_text.js';

const ev = (o) => ({
  kind: 'selection', kind_label: '선정', date: '2026-05-01', stars: 3,
  gigs_before: 1, gigs_after: 4, mentions_before: 0, mentions_after: 3, after_days: 28, ...o,
});

test('사건 하나: "선정 뒤 28일 공연 1→4건 · 언급 0→3건"', () => {
  assert.equal(eventAfterSentence(ev()), '선정 뒤 28일 공연 1→4건 · 언급 0→3건');
});

test('사건 하나: 진행 중이면 며칠째인지, 숫자가 없거나 표 대상이 아니면 빈 문자열', () => {
  assert.equal(eventAfterSentence(ev({ after_days: 12 })), '선정 뒤 12일(진행 중) 공연 1→4건 · 언급 0→3건');
  assert.equal(eventAfterSentence(ev({ gigs_before: null, mentions_before: null })), '');
  assert.equal(eventAfterSentence(ev({ kind: 'first_mention' })), '');
  assert.equal(eventAfterSentence(ev({ mentions_before: null, mentions_after: null })), '선정 뒤 28일 공연 1→4건');
});

test('여러 사건 요약: 끝난 창만 평균, 기준일 뒤 사건은 뺌', () => {
  const evs = [
    ev(),                                                              // 공연 +3, 언급 +3
    ev({ kind: 'big_venue_first', kind_label: '큰 공연장 첫 출연', gigs_before: 2, gigs_after: 3, mentions_before: 1, mentions_after: 0 }), // +1, -1
    ev({ after_days: 10 }),                                            // 진행 중 → 뺌
    ev({ date: '2026-12-30' }),                                        // 기준일 뒤 → 뺌
  ];
  assert.equal(eventsSummarySentence(evs, '2026-11-28'),
    '큰 사건 2건 뒤 28일 평균: 공연 +2.0건 · 언급 +1.0건 (사건 전 28일 대비) — 가장 크게 늘어난 건 선정(2026-05-01) 공연 1→4건');
});

test('여러 사건 요약: 대상 사건이 없으면 빈 문자열', () => {
  assert.equal(eventsSummarySentence([], '2026-11-28'), '');
  assert.equal(eventsSummarySentence([ev({ after_days: 3 })], '2026-11-28'), '');
});

function sig(date) { return { signal_date: date }; }
function daysAgo(asOf, n) {
  return new Date(Date.parse(`${asOf}T00:00:00Z`) - n * 86400000).toISOString().slice(0, 10);
}
const AS_OF = '2026-11-28';

test('이상치: 최근 4주가 평소 4주 평균의 2배 이상이면 "평소의 n배"', () => {
  // 지난 24주(4주 창 6개)마다 1건 → 평균 1, 최근 4주 4건
  const past = [1, 2, 3, 4, 5, 6].map(w => sig(daysAgo(AS_OF, w * 28 + 3)));
  const recent = [2, 5, 9, 14].map(d => sig(daysAgo(AS_OF, d)));
  const a = timelineAnomaly([...past, ...recent], AS_OF);
  assert.equal(a.kind, 'up');
  assert.equal(a.text, '최근 4주 신호 4건 — 평소(지난 24주의 4주 평균 1.0건)의 4.0배');
});

test('이상치: 평소 없다가 3건 이상이면 "처음", 평소 많다가 0건이면 "조용"', () => {
  const first = timelineAnomaly([1, 2, 3].map(d => sig(daysAgo(AS_OF, d))), AS_OF);
  assert.equal(first.kind, 'first');
  assert.equal(first.text, '최근 4주 신호 3건 — 지난 24주엔 없던 움직임');
  const busy = [];
  for (let w = 1; w <= 6; w++) for (let k = 0; k < 4; k++) busy.push(sig(daysAgo(AS_OF, w * 28 + k)));
  const quiet = timelineAnomaly(busy, AS_OF);
  assert.equal(quiet.kind, 'quiet');
  assert.equal(quiet.text, '최근 4주 신호 0건 — 평소(4주 평균 4.0건)보다 조용함');
});

test('이상치: 평범하면 null, 기준일 뒤 신호는 세지 않음', () => {
  assert.equal(timelineAnomaly([], AS_OF), null);
  assert.equal(timelineAnomaly([sig(daysAgo(AS_OF, 1))], AS_OF), null);
  assert.equal(timelineAnomaly([1, 2, 3].map(d => sig(daysAgo(AS_OF, -d))), AS_OF), null);
});

test('알림 규칙 미리보기: 주별 새 팀 수 → 평균과 지금 맞는 팀 수', () => {
  assert.equal(alertForecastText({ total: 37, weekly: [3, 1, 0, 2] }),
    '지금 이 조건에 맞는 팀 37팀 · 최근 4주 새로 걸린 팀 2·0·1·3 (오래된 주 → 지난주) → 이 규칙이면 한 주 평균 1.5건 알림');
  assert.equal(alertForecastText({ total: 5, weekly: [0, 0, 0, 0] }),
    '지금 이 조건에 맞는 팀 5팀 · 최근 4주 새로 걸린 팀 없음 → 알림이 거의 안 올 조건 (조건을 넓혀 보세요)');
  assert.equal(alertForecastText({ total: 0, weekly: [] }), '지금 이 조건에 맞는 팀이 없습니다 — 저장해도 알림이 오지 않아요');
});

test('알림 규칙 미리보기: 표 한도(limit)에 닿으면 "n팀 이상"', () => {
  assert.match(alertForecastText({ total: 100, weekly: [1], cap: 100 }), /^지금 이 조건에 맞는 팀 100팀 이상\(후보 표 한도\) · /);
  assert.match(alertForecastText({ total: 99, weekly: [1], cap: 100 }), /^지금 이 조건에 맞는 팀 99팀 · /);
});

test('공연장 구독 미리보기: 종류별 건수(많은 순) → 한 줄, 없으면 조용하다고', () => {
  const labels = { new_gig: '새 공연', big_venue_first: '큰 공연장 첫 출연', blank_first_mention: '백지 신인 첫 언급' };
  assert.equal(venueSubForecastText({ new_gig: 5, big_venue_first: 1 }, labels),
    '담으면 이번 주 알림 기준 6건 (새 공연 5 · 큰 공연장 첫 출연 1)');
  assert.equal(venueSubForecastText({}, labels), '이번 주 알림 중 이 공연장 관련은 없어요 — 담아도 조용할 수 있어요');
  assert.equal(venueSubForecastText({ odd_type: 2 }, labels), '담으면 이번 주 알림 기준 2건 (odd_type 2)');
});
