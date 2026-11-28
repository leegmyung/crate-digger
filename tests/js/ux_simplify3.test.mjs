// 쉬운 화면 3차 — 도시·페스티벌도 공연장과 같은 질문 3개 · 같은 질문 상자 (docs/ux_simplify_2026-11-28.md ⑩) (node --test)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { cityQuestions, festivalQuestions } from '../../docs/app/insight_text.js';
import { placeQaHtml } from '../../docs/app/components/place_qa.js';

const CITY = {
  teams_1y: 439, first_stage_teams_1y: 190, later_winners_total: 25,
  later_winners: [{ team_key: 'a', name: '팀A', outcome: '부산록페 루키즈', outcome_date: '2026-08-01', lead_months: 9 }],
  top_candidates: [{ team_key: 'p', name: '포져군단', rank: 2, score: 7.2 }],
};
const FLOW = { teams: 120, reached: 30, median_months: 14 };

test('도시 질문 3개: 신인을 세우나 · 어디까지 갔나(수상·서울 이동) · 지금 볼 팀', () => {
  const qs = cityQuestions(CITY, { seoulFlow: FLOW });
  assert.equal(qs.length, 3);
  assert.match(qs[0].q, /도시/);
  assert.match(qs[0].a, /신인을 자주 세우는 곳/);
  assert.match(qs[0].a, /43%/);
  assert.match(qs[1].q, /어디까지 갔나/);
  assert.match(qs[1].a, /25팀/);
  assert.match(qs[1].a, /팀A/);
  assert.match(qs[1].a, /서울 무대 30팀\(25%\)/);
  assert.match(qs[2].a, /포져군단/);
});

test('도시: 서울은 서울 이동 문장 없이, 자료 없으면 자리 유지', () => {
  assert.doesNotMatch(cityQuestions(CITY, { seoulFlow: null })[1].a, /서울 무대/);
  const empty = cityQuestions({}, {});
  assert.equal(empty.length, 3);
  assert.match(empty[0].a, /기록이 없/);
  assert.deepEqual(cityQuestions(null), []);
});

const FEST = {
  editions: {
    2026: { date: '2026-08-01', upcoming: false, lineup: 40, first_festival: 18, first_festival_share: 0.45, later_winners_total: 2,
      later_winners: [{ name: '팀B', outcome: '헬로루키', outcome_date: '2026-10-01' }],
      top_candidates: [{ team_key: 'c', name: '칩 포스트 갱', rank: 1, score: 7.58 }] },
    2025: { date: '2025-08-01', upcoming: false, lineup: 30, first_festival: 3, first_festival_share: 0.1, later_winners_total: 5, later_winners: [] },
    2027: { date: '2027-08-01', upcoming: true, lineup: 5 },
  },
};

test('페스티벌 질문 3개: 가장 최근 끝난 회차 기준 첫 페스티벌 비율 · 그 뒤 수상·선정 합계 · 지금 볼 팀', () => {
  const qs = festivalQuestions(FEST, { flowsOut: [{ toLabel: '부산록페 본무대', teams: 12 }] });
  assert.equal(qs.length, 3);
  assert.match(qs[0].a, /2026년/);
  assert.match(qs[0].a, /40팀 중 18팀\(45%\)/);
  assert.match(qs[0].a, /신인을 자주 세우는 곳/);
  assert.match(qs[1].a, /7팀/);          // 회차 합계 2 + 5 (아직 안 열린 회차 빼고)
  assert.match(qs[1].a, /팀B/);
  assert.match(qs[1].a, /부산록페 본무대\(12팀\)/);
  assert.match(qs[2].a, /칩 포스트 갱/);
  assert.deepEqual(festivalQuestions(null), []);
  assert.equal(festivalQuestions({ editions: {} }).length, 3);
});

test('질문 상자: 3칸, 가운데(어디까지 갔나)가 💡 강조, 글자는 이스케이프', () => {
  const html = placeQaHtml([{ q: '가?', a: '<b>x</b>' }, { q: '나?', a: '둘' }, { q: '다?', a: '셋' }], '요약 질문');
  assert.equal((html.match(/class="venue-qa-item/g) || []).length, 3);
  assert.match(html, /venue-qa-item is-lead"><p class="venue-qa-q">💡 나\?/);
  assert.match(html, /&lt;b&gt;x&lt;\/b&gt;/);
  assert.match(html, /aria-label="요약 질문"/);
  assert.equal(placeQaHtml([]), '');
});
