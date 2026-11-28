// 팀 한 장 요약(인쇄용) — 최근 사건 5개·공연 5개 고르기와 인쇄 HTML (node --test)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { printSheetHtml, recentEvents, recentGigs } from '../../docs/app/team_print.js';
import { pngFileName, pngSize } from '../../docs/app/chart_png.js';

const AS_OF = '2026-11-28';

test('공연: 같은 날·같은 곳은 한 번, 예정(최대 2) 먼저 그다음 최근 순, 모두 5개', () => {
  const tl = [
    { signal_date: '2026-12-05', branch: '공연', venue: '클럽A' },
    { signal_date: '2026-12-01', branch: '공연', venue: '클럽B' },
    { signal_date: '2026-12-20', branch: '공연', venue: '클럽C' },
    { signal_date: '2026-11-20', branch: '공연', venue: '클럽D' },
    { signal_date: '2026-11-20', branch: '공연', venue: '클럽D' },
    { signal_date: '2026-11-10', branch: '공연', venue: '클럽E' },
    { signal_date: '2026-10-01', branch: '공연', venue: '' },
    { signal_date: '2026-09-01', branch: '공연', venue: '클럽F' },
    { signal_date: '2026-11-25', branch: '큐레이션', venue: '' },
  ];
  const g = recentGigs(tl, AS_OF, 5);
  assert.deepEqual(g.map(x => [x.date, x.venue, x.upcoming]), [
    ['2026-12-01', '클럽B', true], ['2026-12-05', '클럽A', true],
    ['2026-11-20', '클럽D', false], ['2026-11-10', '클럽E', false], ['2026-10-01', '공연장 미정', false],
  ]);
});

test('사건: 사건 별점이 있으면 그것(기준일까지, 최근 순), 없으면 공연 뺀 신호·정답', () => {
  const events = [
    { date: '2026-05-01', kind_label: '선정', detail: '밴드 디스커버리', stars: 3 },
    { date: '2026-12-31', kind_label: '미래', detail: '', stars: 1 },
    { date: '2026-08-01', kind_label: '큰 공연장 첫 출연', detail: '롤링홀', stars: 4 },
  ];
  assert.deepEqual(recentEvents(events, [], AS_OF, 5).map(e => [e.date, e.label, e.stars]),
    [['2026-08-01', '큰 공연장 첫 출연', 4], ['2026-05-01', '선정', 3]]);
  const merged = [
    { sortDate: '2026-07-01', branch: '큐레이션', program: 'VISLA' },
    { sortDate: '2026-06-01', branch: '공연', program: '' },
    { sortDate: '2026-09-01', branch: '정답', program: '헬로루키', isOutcome: true },
  ];
  assert.deepEqual(recentEvents(null, merged, AS_OF, 5).map(e => [e.date, e.label]),
    [['2026-09-01', '정답 · 헬로루키'], ['2026-07-01', '큐레이션 · VISLA']]);
});

test('인쇄 HTML: 이름·단계·핵심 숫자·목록이 들어가고 글자는 이스케이프', () => {
  const html = printSheetHtml({
    name: '<팀>', asOf: AS_OF, url: 'https://example.org/#/team/x',
    photoHtml: '<img alt="">', factsHtml: '<span>사실</span>', keyStatsHtml: '<div class="team-keystats">숫자</div>',
    stageLabel: '여러 갈래', stageNext: '선정 받으면 다음 단계',
    events: [{ date: '2026-08-01', label: '선정', detail: 'A&B', stars: 3 }],
    gigs: [{ date: '2026-12-01', venue: '클럽B', upcoming: true }],
  });
  assert.match(html, /&lt;팀&gt;/);
  assert.match(html, /여러 갈래/);
  assert.match(html, /team-keystats/);
  assert.match(html, /A&amp;B/);
  assert.match(html, /예정/);
  assert.match(html, /★★★/);
  assert.doesNotMatch(html, /<팀>/);
});

test('PNG 파일 이름·크기', () => {
  assert.equal(pngFileName('포져군단 관계망', '2026-11-28'), '포져군단_관계망_2026-11-28.png');
  assert.equal(pngFileName('a/b:c?', ''), 'a_b_c.png');
  assert.deepEqual(pngSize({ width: 300, height: 150 }, 2), { width: 600, height: 300 });
  assert.deepEqual(pngSize({ width: 0, height: 0 }, 2, { width: 400, height: 200 }), { width: 800, height: 400 });
});
