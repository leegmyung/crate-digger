// 시·도 지도(components/region_map.js) 순수 함수 — 도시→시·도, 시·도 합계, 색 단계, 투영·경로, 확대 범위 (node --test)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  CITY_TO_SIDO, METRICS, aggregateBySido, colorLevel, fitViewBox, pointInRings, project, ringsPath,
  alignMatrix, boundaryPaths, zoomBbox, sidoOfCity, sidoOfVenue, sumRecentMonths, venuesInSido, regionMapHtml,
} from '../../docs/app/components/region_map.js';

const square = (x, y, s) => [[x, y], [x + s, y], [x + s, y + s], [x, y + s], [x, y]];
const geo = {
  regions: [
    { code: 'KR-11', name: '서울', full: '서울특별시', bbox: [126.8, 37.4, 127.1, 37.7], rings: [square(126.8, 37.4, 0.3)] },
    { code: 'KR-41', name: '경기', full: '경기도', bbox: [126.5, 37.0, 127.5, 38.0], rings: [square(126.5, 37.0, 1.0), square(126.8, 37.4, 0.3)] },
    { code: 'KR-49', name: '제주', full: '제주특별자치도', bbox: [126.2, 33.2, 126.9, 33.6], rings: [square(126.2, 33.2, 0.7)] },
  ],
};

test('도시 이름 → 시·도: 광역시는 그대로, 시는 도로, 모르면 null', () => {
  assert.equal(CITY_TO_SIDO['서울'], '서울');
  assert.equal(CITY_TO_SIDO['춘천'], '강원');
  assert.equal(CITY_TO_SIDO['거제'], '경남');
  assert.equal(CITY_TO_SIDO['서귀포'], '제주');
  assert.equal(sidoOfVenue({ city: '안양' }, geo), '경기');
  assert.equal(sidoOfVenue({ city: '', lat: 33.4, lon: 126.5 }, geo), '제주');  // 도시 모르면 좌표로
  assert.equal(sidoOfVenue({ city: '' }, geo), null);
});

test('도시 이름 끝의 시·군은 떼고 찾는다 (구례군·광양시 → 전남)', () => {
  assert.equal(sidoOfCity('구례군'), '전남');
  assert.equal(sidoOfCity('광양'), '전남');
  assert.equal(sidoOfCity('수원시'), '경기');
  assert.equal(sidoOfCity('없는곳'), null);
  const { bySido, unknown } = aggregateBySido({ 구례군: { venues_with_gigs: 1, monthly: {} } }, '2026-11-28');
  assert.equal(bySido['전남'].venues, 1);
  assert.deepEqual(unknown, []);
});

test('좌표 → 시·도: 구멍(경기 안의 서울)은 짝·홀 규칙으로 뺀다', () => {
  assert.equal(pointInRings(126.95, 37.55, geo.regions[0].rings), true);
  assert.equal(pointInRings(126.95, 37.55, geo.regions[1].rings), false);
  assert.equal(pointInRings(127.3, 37.2, geo.regions[1].rings), true);
  assert.equal(sidoOfVenue({ lat: 37.55, lon: 126.95 }, geo), '서울');
});

test('최근 12개월 합: 기준 달 포함 뒤로 n달', () => {
  const monthly = { '2025-11': 100, '2025-12': 1, '2026-06': 2, '2026-11': 3, '2026-12': 50 };
  assert.equal(sumRecentMonths(monthly, '2026-11-28', 12), 6);
});

test('시·도 합계: 같은 시·도의 도시를 더하고, 모르는 도시는 따로', () => {
  const cities = {
    서울: { venues_with_gigs: 154, teams_1y: 3518, monthly: { '2026-11': 10, '2026-01': 5 } },
    안양: { venues_with_gigs: 1, teams_1y: 62, monthly: { '2026-10': 2 } },
    수원: { venues_with_gigs: 4, teams_1y: 9, monthly: {} },
    어딘가: { venues_with_gigs: 2, teams_1y: 1, monthly: {} },
  };
  const { bySido, unknown } = aggregateBySido(cities, '2026-11-28');
  assert.deepEqual(bySido['서울'], { venues: 154, nights: 15, teams: 3518, cities: ['서울'] });
  assert.deepEqual(bySido['경기'], { venues: 5, nights: 2, teams: 71, cities: ['안양', '수원'] });
  assert.deepEqual(unknown, ['어딘가']);
  assert.deepEqual(Object.keys(METRICS), ['venues', 'nights', 'teams']);
});

test('색 단계: 0은 0(기록 없음), 최댓값은 5, 로그 눈금이라 작은 값도 보인다', () => {
  assert.equal(colorLevel(0, 154), 0);
  assert.equal(colorLevel(154, 154), 5);
  assert.equal(colorLevel(1, 154), 1);
  assert.ok(colorLevel(21, 154) >= 3);
  assert.equal(colorLevel(5, 0), 0);
});

test('투영·경로: 북쪽이 위(y 작음), 동쪽이 오른쪽, 닫힌 경로', () => {
  const a = project(127, 37.5);
  const b = project(128, 36.5);
  assert.ok(b[0] > a[0]);
  assert.ok(b[1] > a[1]);
  const d = ringsPath([square(127, 37, 1)]);
  assert.match(d, /^M[\d.-]+,[\d.-]+(L[\d.-]+,[\d.-]+)+Z$/);
});

test('확대 범위: 틀 비율에 맞춰 넓히고 여백을 둔다', () => {
  const vb = fitViewBox([126.8, 37.4, 127.1, 37.7], 4 / 3, 0.1);
  assert.ok(Math.abs(vb[2] / vb[3] - 4 / 3) < 1e-9);
  const [x0, y0] = project(126.8, 37.7);
  const [x1, y1] = project(127.1, 37.4);
  assert.ok(vb[0] < x0 && vb[1] < y0 && vb[0] + vb[2] > x1 && vb[1] + vb[3] > y1);
});

test('시·도 안 공연장: 좌표 있는 곳만, @계정은 뺀다', () => {
  const venues = [
    { name: '클럽A', city: '서울', lat: 37.55, lon: 126.92 },
    { name: '클럽B', city: '서울' },
    { name: '@기획', city: '서울', lat: 37.5, lon: 126.9 },
    { name: '수원홀', city: '수원', lat: 37.27, lon: 127.0 },
  ];
  assert.deepEqual(venuesInSido(venues, '서울', geo).map(v => v.name), ['클럽A']);
});

test('지도 HTML: 시·도마다 누를 수 있는 면 + 숫자 라벨, 고르는 단추 3개, 이름은 이스케이프', () => {
  const { bySido } = aggregateBySido({ 서울: { venues_with_gigs: 3, teams_1y: 1, monthly: {} } }, '2026-11-28');
  const html = regionMapHtml({ geo, bySido, metric: 'venues' });
  assert.equal((html.match(/data-sido="/g) || []).length, 3 * 2);  // 면 + 라벨
  assert.equal((html.match(/data-map-metric="/g) || []).length, 3);
  assert.match(html, /aria-pressed="true"[^>]*>공연장 수/);
  assert.match(html, /class="rm-label-num"[^>]*>3</);
  assert.ok(!/<script/i.test(regionMapHtml({ geo: { regions: [{ ...geo.regions[0], name: '<script>' }] }, bySido, metric: 'venues' })));
});

test('독도: 경북 색 점 + 이름 라벨, 누르면 경북으로', () => {
  const g = { ...geo, regions: [...geo.regions, { code: 'KR-47', name: '경북', full: '경상북도', bbox: [128, 35.5, 131.9, 37.5], rings: [square(128, 35.5, 1)] }],
    marks: [{ name: '독도', sido: '경북', lon: 131.867, lat: 37.241 }] };
  const { bySido } = aggregateBySido({ 포항: { venues_with_gigs: 4, teams_1y: 1, monthly: {} } }, '2026-11-28');
  const html = regionMapHtml({ geo: g, bySido, metric: 'venues' });
  assert.match(html, /<circle class="rm-mark lv-5" data-sido="경북"/);
  assert.match(html, /class="rm-mark-label"[^>]*>독도</);
});

test('다른 지도 위에 경계 깔기: 같은 투영이면 확대·이동 행렬 하나로 맞는다', () => {
  const k = Math.cos((36 * Math.PI) / 180);
  const toXY = (lon, lat) => [18 + (lon * k - 101.2) * 900, 342 - (lat - 37.4) * 900];  // venues_list 점 지도 같은 꼴
  const [a, , , d, e, f] = alignMatrix(toXY);
  for (const [lon, lat] of [[126.9, 37.55], [129.0, 35.1], [126.5, 33.4]]) {
    const [x, y] = project(lon, lat);
    const [ex, ey] = toXY(lon, lat);
    assert.ok(Math.abs(a * x + e - ex) < 1e-6 && Math.abs(d * y + f - ey) < 1e-6);
  }
  const paths = boundaryPaths(geo);
  assert.equal(paths.length, 3);
  assert.equal(paths[0].name, '서울');
  assert.match(paths[0].d, /^M/);
  assert.equal(boundaryPaths(geo), paths);  // 같은 자료면 다시 계산하지 않음
});

test('확대 범위: 가장 큰 땅 + 그 시·도 공연장 점 (멀리 떨어진 작은 섬은 빼서 본토가 작아지지 않게)', () => {
  const gb = { name: '경북', bbox: [128, 35.5, 131.9, 37.5],
    rings: [square(128, 35.5, 1.5), square(130.8, 37.4, 0.1), square(131.86, 37.24, 0.003)] };
  assert.deepEqual(zoomBbox(gb, []), [128, 35.5, 129.5, 37]);
  assert.deepEqual(zoomBbox(gb, [{ lon: 129.6, lat: 36.0 }]), [128, 35.5, 129.6, 37]);
});
