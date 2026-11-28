// 쉬운 화면 2차 (docs/ux_simplify_2026-11-28.md ③④⑦⑩) — 발굴 프리셋 줄·필터 접기, 발굴↔차트 역할, '담기' 단추, 공연장 질문형 요약 (node --test)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  ROLE_LINES, presetChartNoteHtml, renderCandPanelHtml, renderCandResultsBarHtml, renderPresetRowHtml,
} from '../../docs/app/components/cand_filters.js';
import { legacyToNew } from '../../docs/app/state.js';
import { WATCH_LABELS, watchButtonHtml } from '../../docs/app/ui.js';
import { teamHeadActionsHtml } from '../../docs/app/views/team_head.js';
import { venueQuestions } from '../../docs/app/insight_text.js';

const count = (html, re) => (html.match(re) || []).length;

function baseState(over = {}) {
  return {
    cfg: { genre: '', branches: ['공연', '선정·지원', '발매', '큐레이션'], period_days: 0, newcomer_years: 3,
      exclude_famous: true, only_no_outcome: true, limit: 100 },
    candPreset: '', candReleaseMonths: 0, candStage: '', candRegion: '', candMove: '', candQuery: '',
    candCity: '', candTier: '', candGenreInf: '', candView: '', validGenres: ['록·밴드'],
    ...over,
  };
}
const COUNTS = {
  total: 100, genres: new Map([['록·밴드', 66]]), releaseMonths: { 6: 5, 12: 13, 18: 20, 24: 30, 36: 40 },
  stages: { 0: 84, 1: 10, 2: 50, 3: 13, 4: 9 }, branches: { 공연: 90, '선정·지원': 13, 발매: 80, 큐레이션: 40 },
  moves: { new: 3, riser: 5, upcoming: 23 }, hasCityData: true, nonSeoul: 9, cities: new Map([['부산', 4]]),
  hasLadder: true, tiers: { S: 10, M: 40, L: 80 }, presets: { debut12: 13, blank: 84, selected: 13, regional: 9, rising: 12 },
};

// ---------- ③ 발굴: 프리셋 줄 + 필터 접기 ----------
test('프리셋 줄: 자주 쓰는 조합 5개 + 팀 수, 저장한 조건도 같은 줄에', () => {
  const html = renderPresetRowHtml({ appState: baseState(), counts: COUNTS,
    saved: [{ id: 'f1', name: '부산 록', hash: '#/discover?genre=x' }], currentHash: '' });
  assert.equal(count(html, /data-cand-preset="/g), 5);
  assert.match(html, /갓 데뷔/);
  assert.match(html, />84</);
  assert.match(html, /data-saved-apply="f1"/);
  assert.match(html, /부산 록/);
});

test('프리셋 줄: 고른 프리셋은 눌린 상태(aria-pressed)', () => {
  const html = renderPresetRowHtml({ appState: baseState({ candStage: '0' }), counts: COUNTS, saved: [] });
  assert.match(html, /data-cand-preset="blank"[^>]*aria-pressed="true"/);
});

test('필터 패널에는 프리셋을 두 번 두지 않음 (프리셋 줄로 옮김)', () => {
  const html = renderCandPanelHtml({ appState: baseState(), counts: COUNTS });
  assert.doesNotMatch(html, /dp-presets/);
  assert.equal(count(html, /data-cand-preset="/g), 0);
  assert.match(html, /data-set-genre/);   // 조건 자체는 그대로
});

test('결과 위 줄: "+ 필터 추가" 단추가 패널을 여닫음 (기본 닫힘)', () => {
  const closed = renderCandResultsBarHtml({ appState: baseState(), panelOpen: false });
  assert.match(closed, /필터 추가/);
  assert.match(closed, /id="candMobileFilterToggle"[^>]*aria-expanded="false"/);
  const open = renderCandResultsBarHtml({ appState: baseState(), panelOpen: true });
  assert.match(open, /aria-expanded="true"/);
});

// ---------- ④ 발굴 ↔ 차트 역할 ----------
test('역할 문장: 발굴 = 조건으로 찾기, 차트 = 순위 보기', () => {
  assert.match(ROLE_LINES.discover, /조건/);
  assert.match(ROLE_LINES.charts, /순위/);
});

test('차트와 겹치는 프리셋(떠오르는·갓 데뷔)을 고르면 "차트에서 순위로 보기" 안내', () => {
  assert.match(presetChartNoteHtml('rising'), /href="#\/charts\/rising"/);
  assert.match(presetChartNoteHtml('rising'), /떠오르는/);
  assert.match(presetChartNoteHtml('debut12'), /href="#\/charts\/debut"/);
  assert.equal(presetChartNoteHtml('blank'), '');
  assert.equal(presetChartNoteHtml(''), '');
});

test('옛 주소: 발굴 안 갓 데뷔·떠오르는 순위 → 차트로 (조건 프리셋 주소는 그대로)', () => {
  assert.equal(legacyToNew('discover', 'ctab=debut'), '#/charts/debut');
  assert.equal(legacyToNew('discover/debut', ''), '#/charts/debut');
  assert.equal(legacyToNew('discover/rising', ''), '#/charts/rising');
  assert.equal(legacyToNew('debut', ''), '#/charts/debut');
  assert.equal(legacyToNew('rising', ''), '#/charts/rising');
  assert.equal(legacyToNew('discover', 'preset=rising'), null);
  assert.equal(legacyToNew('candidates', 'ctab=debut'), '#/charts/debut');
});

// ---------- ⑦ '담기' 단추 하나 ----------
test('팀 담기 단추: 이름이 "담기"로 통일 (관심 추가·관심 중 대신)', () => {
  const html = watchButtonHtml('x', '팀X', true);
  assert.match(html, /☆ 담기/);
  assert.doesNotMatch(html, /관심 추가|관심 중/);
  const rev = watchButtonHtml('x', '팀X', true, true);
  assert.match(rev, /watch-lbl-full">담기</);
  assert.equal(WATCH_LABELS.on, '담음');
  assert.equal(WATCH_LABELS.off, '담기');
});

// ---------- ②보탬: 팀 머리 단추 2개 + 더보기 ----------
test('팀 머리 단추: 앞 2개만 보이고 나머지는 ⋯ 더보기 안에', () => {
  const html = teamHeadActionsHtml({
    primary: ['<button class="btn">▶ 듣기</button>', '<button class="btn">☆ 담기</button>'],
    more: ['<a class="btn" href="#">유튜브</a>', '<button class="btn">비교</button>', '', '<button class="btn">인쇄</button>'],
  });
  const [front] = html.split('<details');
  const menu = html.split('ux-more-menu')[1] || '';
  assert.equal(count(front, /class="btn/g), 2);
  assert.match(html, /class="ux-more"/);
  assert.equal(count(menu, /class="btn/g), 3);
  assert.match(html, /aria-label="더보기/);
  assert.doesNotMatch(teamHeadActionsHtml({ primary: ['<b>a</b>'], more: [] }), /<details/);
});

// ---------- ⑩ 공연장 질문형 요약 ----------
const PROFILE = {
  tier: 'M', teams_1y: 372, first_timers_1y: 106, first_timer_share_1y: 0.2849, later_winners_total: 55,
  later_winners: [{ team_key: '구구', name: '구구', outcome: '인디스땅스 결선', outcome_date: '2026-10-17', lead_months: 18 }],
  after: [['A.O.R', 119], ['롤링홀', 92]],
  top_candidates: [{ team_key: '포져군단', name: '포져군단', rank: 2, score: 7.2 }],
};
const TIER_OF = new Map([['A.O.R', 'M'], ['롤링홀', 'L']]);

test('공연장 질문 3개: 신인을 세우나 · 어디까지 갔나 · 지금 볼 팀', () => {
  const qs = venueQuestions(PROFILE, { tierOf: TIER_OF });
  assert.equal(qs.length, 3);
  assert.match(qs[0].q, /신인/);
  assert.match(qs[0].a, /신인을 자주 세우는 곳/);
  assert.match(qs[0].a, /28%/);
  assert.match(qs[1].q, /어디까지 갔나/);
  assert.match(qs[1].a, /55팀/);
  assert.match(qs[1].a, /구구/);
  assert.match(qs[1].a, /롤링홀/);   // 다음 무대 중 가장 큰 곳
  assert.match(qs[2].a, /포져군단/);
});

test('공연장 질문: 자료가 없으면 "아직 모름"으로 같은 자리 유지, 프로필 없으면 빈 목록', () => {
  const qs = venueQuestions({ tier: 'S', teams_1y: 0, later_winners_total: 0, after: [], top_candidates: [] }, { tierOf: new Map() });
  assert.equal(qs.length, 3);
  assert.match(qs[0].a, /최근 1년 출연 기록이 없/);
  assert.match(qs[1].a, /아직/);
  assert.match(qs[2].a, /없/);
  assert.deepEqual(venueQuestions(null), []);
});

test('첫 무대 비율 구간: 10% 미만은 경력 팀 위주, 사이는 섞임', () => {
  const low = venueQuestions({ ...PROFILE, first_timer_share_1y: 0.05, first_timers_1y: 18 }, { tierOf: TIER_OF });
  assert.match(low[0].a, /경력 팀이 주로/);
  const mid = venueQuestions({ ...PROFILE, first_timer_share_1y: 0.15, first_timers_1y: 56 }, { tierOf: TIER_OF });
  assert.match(mid[0].a, /섞여/);
});
