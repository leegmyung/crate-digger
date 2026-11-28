// 비슷한 팀 말풍선 — '둘러보기용, 예측력 확인 안 됨' 안내가 들어 있는지 (node --test)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { INFO_TIPS, infoTip } from '../../docs/app/components/infotip.js';

test('비슷한 팀 말풍선: 둘러보기용 · 예측력 확인 안 됨 한 줄', () => {
  const tip = INFO_TIPS.similar_teams;
  assert.ok(tip, 'INFO_TIPS.similar_teams 가 있어야 함');
  const text = [tip.what, tip.period, tip.compare].join(' ');
  assert.match(text, /둘러보기용 — 예측력 확인 안 됨/);
  assert.match(text, /같은 무대 40/);
});

test('비슷한 팀 말풍선 버튼 HTML 에 안내 문구가 실림', () => {
  const html = infoTip('비슷한 팀', INFO_TIPS.similar_teams, { compact: true });
  const encoded = html.match(/data-infotip="([^"]+)"/)[1];
  const payload = JSON.parse(decodeURIComponent(encoded.replace(/&#39;/g, "'").replace(/&quot;/g, '"').replace(/&amp;/g, '&')));
  assert.equal(payload.title, '비슷한 팀');
  assert.match(payload.what, /예측력 확인 안 됨/);
});
