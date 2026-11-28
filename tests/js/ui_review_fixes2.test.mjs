// 화면 점검 2차(docs/ui_review_2026-11-28.md 2절) — 알림 날짜·홈 성적 줄·팀 머리 숫자 말풍선·도시·페스티벌 말풍선 (node --test)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { alertDateText } from '../../docs/app/views/today_alerts.js';
import { renderKeyStatsHtml } from '../../docs/app/views/team_head.js';
import { fairnessShort } from '../../docs/app/score_fairness.js';
import { INFO_TIPS } from '../../docs/app/components/infotip.js';

test('옛 발표일 알림은 "발표 날짜 · 기록 추가 날짜"로 (이번 주 새 정답으로 오해하지 않게)', () => {
  assert.equal(alertDateText({ date: '2022-05-24', found_on: '2026-11-28' }), '발표 2022-05-24 · 기록 추가 11-28');
  assert.equal(alertDateText({ date: '2026-11-25', found_on: '2026-11-28' }), '2026-11-25');   // 최근이면 날짜만
  assert.equal(alertDateText({ date: '2026-11-25' }), '2026-11-25');
  assert.equal(alertDateText({}), '');
});

test('팀 머리 핵심 숫자 4칸에 ⓘ 말풍선', () => {
  const html = renderKeyStatsHtml({ scored: { score: 3.2, gigs_1y: 5, venues: 2, outlets: 1 }, rc: { rank: 9 }, videos: [], links: null, displayName: '팀' });
  assert.equal((html.match(/class="cd-infotip[ "]/g) || []).length, 4);
});

test('홈 근거 줄 성적 한 줄: 지금 판과 같은 기준 판', () => {
  const s = fairnessShort({ base: { auc_v2: 0.8271, auc_cv: 0.8093 }, D_untargeted_debut: { auc_v2: 0.7881, auc_cv: 0.7831 } });
  assert.equal(s, '점수 성적 AUC 0.827 · 같은 기준 0.788 (교차 검증 0.783)');
  assert.equal(fairnessShort(null), '');
});

test('검증 메뉴의 출처 코드도 읽는 이름으로 (busan·yjh·sejong·dmz·gbsound·manual·routenote)', async () => {
  const { SOURCE_LABELS } = await import('../../docs/app/ui.js');
  for (const code of ['busan', 'yjh', 'sejong', 'dmz', 'gbsound', 'manual', 'routenote']) {
    assert.ok(SOURCE_LABELS[code] && !/^[a-z_]+$/.test(SOURCE_LABELS[code]), code);
  }
});

test('도시·페스티벌 숫자 말풍선이 있음', () => {
  for (const k of ['city_summary', 'festival_new_teams', 'festival_first_fest', 'festival_after_outcome']) {
    assert.ok(INFO_TIPS[k]?.what, k);
  }
});
