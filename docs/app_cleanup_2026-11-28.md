# 앱 미사용 코드·CSS·중복 함수 점검 보고 (2026-11-28)

- **점검 범위**: `docs/app/**/*.js` (88개), `docs/app/style.css` + `docs/app/css/*.css` (15개), 참조 대조 `docs/*.html` (6개) · `tests/**/*.mjs` (28개)
- **기준 시점**: 2026-11-28 17:35 (HEAD `09f76de` + 워킹트리 기준, 기존 파일 수정 없음)
- **요약**
  - **미사용 JS 파일**: **1개** (`docs/app/views/placeholder.js`)
  - **완전 미사용 `export` (외부 0 · 내부 0 · 테스트 0)**: **12개** (즉시 정리 후보)
  - **내부 전용 `export` (외부 0 · 테스트 0, 내부에서만 호출)**: **50개** (`export` 키워드만 제거 가능)
  - **미사용 CSS 클래스**: **118개** (`css/discover.css` 2개 + `style.css` 116개; 동적 조합 클래스 70개는 검증 후 제외)
  - **중복 함수 묶음**: **9개 묶음** (특히 `esc`/`escapeHtml` 7곳, `num`/`toNumOrNull` 4곳, `endId` 3곳, 최근 N개월 `YYYY-MM` 생성 4곳)

---

## 1. 어디서도 `import` 안 되는 JS 파일 · `export`

### 1-1. 미사용 JS 파일 (1개)

`docs/dashboard.html` → `docs/app/app.js` 정적·동적 import 그래프 도달 가능성 검사 결과, 도달 불가 파일은 1개입니다.

| 파일 | 줄 수 | 근거 (grep 결과) | 비고 |
|---|---:|---|---|
| `docs/app/views/placeholder.js` | 52 | `docs/`·`tests/` 전체에서 `placeholder.js`, `renderPlaceholderView` 참조 **0건** | 초기 임시 화면 잔재, 삭제 가능 |

### 1-2. 완전 미사용 `export` (외부 0건 · 내부 0건 · 테스트 0건, 12개)

선언 줄 외 `docs/`·`tests/` 전체에서 참조가 **0건**인 죽은 함수입니다.

| 파일 | 줄 | 심볼 | 근거 (전체 grep 결과) |
|---|---:|---|---|
| `docs/app/components/team_peek.js` | 261 | `updateTeamPeekKeys` | 선언 줄 1건 외 `docs/`·`tests/` 0건 |
| `docs/app/components/team_peek.js` | 266 | `isTeamPeekOpen` | 선언 줄 1건 외 `docs/`·`tests/` 0건 |
| `docs/app/state.js` | 829 | `getWatchStatus` | 선언 줄 1건 외 `docs/`·`tests/` 0건 |
| `docs/app/state.js` | 899 | `exportWatchlistCsv` | 선언 줄 1건 외 `docs/`·`tests/` 0건 (`views/watchlist.js`는 `setExportContext` 사용) |
| `docs/app/state.js` | 919 | `getPreferredPlatform` | 선언 줄 1건 외 `docs/`·`tests/` 0건 |
| `docs/app/state.js` | 927 | `setPreferredPlatform` | 선언 줄 1건 외 `docs/`·`tests/` 0건 |
| `docs/app/ui.js` | 1236 | `nextStageConditionText` | 선언 줄 1건 외 `docs/`·`tests/` 0건 |
| `docs/app/ui.js` | 1374 | `getGeneralTodayAlerts` | 선언 줄 1건 외 `docs/`·`tests/` 0건 |
| `docs/app/views/placeholder.js` | 49 | `renderPlaceholderView` | 선언 줄 1건 외 `docs/`·`tests/` 0건 (파일 전체 미사용) |
| `docs/app/views/team_head.js` | 91 | `renderTeamTocHtml` | 선언 줄 1건 외 `docs/`·`tests/` 0건 (팀 머리 단순화 후 잔재) |
| `docs/app/views/team_head.js` | 100 | `wireTeamToc` | 선언 줄 1건 외 `docs/`·`tests/` 0건 (팀 머리 단순화 후 잔재) |
| `docs/app/views/today_alerts.js` | 161 | `renderAlertsCardHtml` | 선언 줄 1건 외 `docs/`·`tests/` 0건 |

### 1-3. 외부 참조 0건이지만 파일 내부에서만 쓰이는 `export` (50개)

다른 JS/HTML/테스트에서 import되지 않으나 같은 파일 내부에서 사용 중입니다. 함수 삭제는 불가하며 `export` 키워드만 제거(비공개화)할 수 있습니다.

| 파일 | 심볼 (줄 번호) |
|---|---|
| `docs/app/components/cand_filters.js` | `CAND_PRESETS` (13) |
| `docs/app/components/heat_scale.js` | `HEAT_BOUNDS` (8) |
| `docs/app/components/mini_player.js` | `playTeam` (127), `closePlayer` (152) |
| `docs/app/components/team_peek.js` | `openTeamPeek` (218), `stepTeamPeek` (253), `closeTeamPeek` (271), `peekKeysFrom` (285) |
| `docs/app/components/venue_flow.js` | `TIER_COLUMNS` (7) |
| `docs/app/db.js` | `isVideosLoaded` (39), `pickWeeklyPrevSnapshot` (397), `formatRunLabel` (621), `queryPendingGigs1y` (998), `ensureVenueTiersLoaded` (1172) |
| `docs/app/db_peer.js` | `MIN_PEERS` (10) |
| `docs/app/db_saved.js` | `querySavedMatches` (43) |
| `docs/app/easy_terms.js` | `EASY_ALERT_TYPE_LABELS` (32) |
| `docs/app/home_picks.js` | `WEEKLY_PICKS` (11) |
| `docs/app/search_index.js` | `searchVenues` (192), `searchCities` (211), `searchFestivals` (220) |
| `docs/app/state.js` | `PRESET_CUTOFFS` (4), `CHART_KINDS` (32), `LEGACY_ROUTES` (35), `VERIFY_TABS` (49) |
| `docs/app/ui.js` | `GRADE_META` (87), `formatLastCheckedShort` (542), `NEWCOMER_UNVERIFIED_TIP` (1225), `isNewcomerUnverified` (1289), `ALERT_TYPE_LABELS` (1306), `alertDedupKey` (1317) |
| `docs/app/views/cand_saved.js` | `renderSavedRowHtml` (54) |
| `docs/app/views/candidates_heatmap.js` | `HEAT_COLUMNS` (15), `sortHeatRows` (63) |
| `docs/app/views/city_page.js` | `recentMonths` (40), `mapVenues` (67) |
| `docs/app/views/festival_page.js` | `findFestival` (18) |
| `docs/app/views/graph_panel.js` | `KIND_LABELS` (8), `TYPE_LABELS` (19), `nodeSignalRole` (34) |
| `docs/app/views/graph_scene_panel.js` | `sceneRoleText` (12) |
| `docs/app/views/team_tabs.js` | `TEAM_TAB_DEFS` (7) |
| `docs/app/views/today_alerts.js` | `alertTeamHref` (18), `alertStars` (36), `evidenceItems` (54), `starsMini` (68), `renderSpikeSentencesHtml` (224) |
| `docs/app/views/venues_list.js` | `setVenueListMode` (30), `renderVenueListTab` (232) |
| `docs/app/views/verify.js` | `VERIFY_PAGES` (13) |

### 1-4. 참고: `tests/`에서만 `import`하는 `export` (27개 — 삭제 금지)

앱 코드 내부에서는 외부 참조가 없지만 단위 테스트가 직접 `import`하고 있어 `export`를 유지해야 합니다.
- `chart_png.js`: `pngFileName` (17), `pngSize` (23) — `tests/js/team_print.test.mjs`
- `compare_list.js`: `parseCompareKeys` (16, 내부 호출 0) — `tests/js/compare_list.test.mjs`
- `components/region_map.js`: `CITY_TO_SIDO` (10), `METRICS` (22), `project` (53), `ringsPath` (58), `pointInRings` (85), `sidoOfVenue` (105), `colorLevel` (146), `fitViewBox` (157), `venuesInSido` (168), `zoomBbox` (210), `regionMapHtml` (283) — `tests/js/region_map.test.mjs`
- `key_aliases.js`: `remapKeyList` (32), `remapWatchItems` (46) — `tests/js/key_aliases.test.mjs`
- `list_more.js`: `LIST_FIRST` (6), `moreLabel` (13) — `tests/js/list_more.test.mjs`
- `mine_store.js`: `LEGACY_MINE_KEYS` (11), `buildMineFromLegacy` (56), `resetMineMemory` (121) — `tests/js/ux_mine_store.test.mjs`
- `player_pick.js`: `parseSpotifyRef` (23), `parseYoutubeRef` (38) — `tests/js/player_pick.test.mjs`
- `state.js`: `ROUTES` (7) — `tests/e2e/route_check.mjs`; `legacyToNew` (364) — `tests/js/ux_simplify2.test.mjs`
- `views/graph_panel.js`: `describeLink` (46) — `tests/js/graph_panel.test.mjs`
- `views/graph_scene_model.js`: `roleOf` (15) — `tests/js/graph_scene.test.mjs`
- `views/today_alerts.js`: `alertDateText` (97) — `tests/js/ui_review_fixes2.test.mjs`
- `views/venue_tables.js`: `venueTeamRowHtml` (44) — `tests/js/ui_review_fixes.test.mjs`

---

## 2. 어떤 JS·HTML에서도 안 쓰는 CSS 클래스 (118개)

- 전체 CSS 15개 파일(`style.css` + `css/*.css`)은 모두 `docs/dashboard.html` 또는 `@import url("css/tables.css")`로 로드됨(미사용 CSS 파일은 0개).
- 고유 클래스 1,433개를 `docs/**/*.js` · `docs/**/*.html`과 대조했으며, 템플릿 리터럴로 동적 생성되는 70개 클래스(`wa-seg-s${stage}`, `lv${level}`, `lv-${n}`, `is-${status}`, `is-${side}`, `is-${role}`, `grade-${g}`, `stage-${n}`, `alert-kind-${kind}`, `is-tier-${t}`, `tier-${t}`, `k-${kind}`, `t-${type}`, `cmp-anom-${k}`, `ks-plat-${p}`, `ks-src-${s}` 등)는 사용 중임을 확인하고 제외했습니다.

### 2-1. `docs/app/css/discover.css` (2개)

| 클래스 | 정의 줄 | 근거 (JS·HTML grep 결과) |
|---|---:|---|
| `.dp-presets` | 53, 57 | `docs/` 0건 (`tests/js/ux_simplify2.test.mjs:48`에서 제거됨을 단언) |
| `.cf-presets-list` | 57 | `docs/` 0건 (구 필터 프리셋 잔재) |

### 2-2. `docs/app/style.css` (116개, 기능 묶음별 정리)

모든 항목은 `docs/**/*.js` 및 `docs/**/*.html` 전체에서 단독 식별자 매칭 **0건**입니다.

| 묶음 (추정 출처) | 클래스 (정의 줄 번호) | 개수 |
|---|---|---:|
| **구 상단 필터 서랍** | `.filter-bar-compact` (507, 1846), `.filter-toggle-btn` (516, 525), `.filter-toggle-caret` (520, 525), `.filter-summary-text` (529, 1850), `.filter-chip` (538), `.filter-clear-link` (549, 559), `.filter-drawer` (561), `.filter-bar` (566), `.f-item` (575, 584, 590, 597), `.is-changed` (584, 585, 597), `.f-item-inline` (585, 617), `.f-branches` (601) | 12 |
| **구 발굴 필터(`cf-*` → `disc-*` 교체)** | `.cf-shell` (6452, 6962), `.cf-presets-row` (6458, 6970), `.cf-presets-lbl` (6465, 6992), `.cf-presets-list` (6471, 6976), `.cf-preset-item` (6478), `.cf-add-btn` (6512, 6569, 6581), `.cf-count-btn` (6513, 6570, 6586, 6591), `.cf-mobile-bar` (6533, 6938), `.cf-bar` (6537, 6962, 6988), `.cf-left` (6547), `.cf-right` (6556), `.has-active` (6591), `.cf-inline-search` (6609, 6966), `.cf-popover` (6614, 6626, 6932, 6996), `.cf-pop-grid` (6630, 7004), `.cf-pop-title` (6636), `.cf-pop-foot` (6708), `.cf-mobile-toggle` (6943), `.cf-mobile-search` (6957), `.is-mobile-open` (6962), `.saved-lbl` (7766, `disc-saved-lbl`로 교체) | 21 |
| **구 홈/브리핑·픽 카드** | `.grid-5` (1205, 1805, 1898), `.grid-3` (1212, 1806), `.pick-card` (1227, 1287, 1293, 1294, 2287, 2296, 3133), `.pick-top` (1237), `.pick-rank` (1244), `.pick-score` (1250), `.pick-name` (1258, 2309, 2313), `.pick-why` (1266, 2322), `.pick-foot` (1273, 2330), `.pick-head` (2300, 2309, 2313, 3137), `.pick-next-gig` (2705), `.briefing-hero` (2104, 3086), `.briefing-hero-head` (2112), `.briefing-kicker` (2121), `.briefing-date-pill` (2128), `.briefing-title` (2149), `.briefing-narrative` (2156), `.briefing-kpis` (2174, 3090), `.kpi-chip` (2180, 3095), `.kpi-chip-accent` (2193), `.kpi-chip-lbl` (2198), `.kpi-chip-val` (2203), `.today-section` (2209), `.today-explore-strip` (4498, 4664), `.today-explore-card` (4505, 4518, 4669), `.today-explore-top` (4524, 4531), `.today-explore-count` (4537), `.today-explore-desc` (4548), `.today-explore-cta` (4555), `.today-alert-item` (5178, 5189, 5194, 5347), `.today-alert-main` (5198) | 31 |
| **구 플랫폼 드롭다운·인라인 플레이어·영상 그리드** | `.platform-menu-wrap` (1600, 1631, 1636), `.platform-main-btn` (1606), `.platform-caret-btn` (1611), `.platform-drop` (1618, 1631, 1636), `.platform-opt` (1641, 1652, 1653, 1658), `.is-search` (1658), `.platform-opt-tag` (1662), `.spotify-embed-box` (2409), `.spotify-embed-head` (2417), `.spotify-embed` (2425), `.player-expand-row` (2432, 3720, 3727), `.recent-videos-grid` (2439, 3081), `.video-card-body` (2445), `.video-card-team` (2449), `.video-play-btn` (2457, 2471, 2480) | 15 |
| **구 하위 탭·검증/변동 배지** | `.sub-tabs` (1668), `.sub-tab-btn` (1676, 1688, 1690, 3119, 8366), `.verify-shell-head` (2682), `.verify-grade-fold` (3961), `.cand-sub-tabs` (3986), `.venues-sub-tabs` (4379, 8360, 8366), `.chip-group-move` (2844, 3160), `.delta-badge` (2856, 2865, 2870), `.is-new` (2865) | 9 |
| **구 공연장 히어로·공연 목록** | `.venue-hero-top` (5412), `.venue-hero-title-row` (5418, 5425, 5903), `.venue-shows-list` (5807), `.venue-show-row` (5816, 5827, 5891), `.venue-show-date-col` (5831, 5896), `.venue-show-date` (5838), `.venue-show-lineup` (5842), `.venue-show-team` (5849, 5864, 5869) | 8 |
| **구 단계 필터·팀 단계 줄** | `.inline-stage-row` (4922), `.stage-filter-label` (4929), `.stage-filter-hint` (4936, 5094), `.is-stage-grad` (4940), `.team-stage-line` (5079, 5098), `.team-stage-next` (5089) | 6 |
| **기타 단발 잔재** | `.skel-banner` (1099), `.skel-w-80` (1148), `.skel-w-90` (1149), `.bar-legend` (1346), `.legend-item` (1355), `.swatch` (1361), `.kv-list` (1392, 1401, 1402), `.mini-list-actions` (2361), `.theme-seg-btn` (3120), `.monthly-bars-block` (3479, **주의: 아래 메모 참고**), `.gt-hint` (4318), `.city-note` (8285), `.fest-grid` (8304, 8311, 8337), `.fest-note` (8322) | 14 |

> **주의 메모 (`.monthly-bars-block`, `style.css:3479`)**: 어떤 JS에도 클래스가 붙어 있지 않지만, `style.css`에서 `--act-gig` / `--act-sel` / `--act-other` 막대 색 변수가 `.monthly-bars-block`에 선언돼 있을 수 있습니다. 삭제 전에 `views/team.js` 최근 12개월 활동 막대 색이 정상 표시되는지 확인하세요.

---

## 3. 같은 일을 하는 중복 함수 (9개 묶음)

| # | 역할 | 중복 위치 (파일:줄 · 함수명) | 근거 및 통합 제안 |
|---:|---|---|---|
| 1 | **HTML 이스케이프** | `ui.js:168` `escapeHtml` (정본)<br>`components/bars.js:7` `esc`<br>`components/controls.js:7` `esc`<br>`components/infotip.js:8` `esc`<br>`components/region_map.js:49` `esc`<br>`components/venue_flow.js:27` `esc`<br>`team_print.js:10` `esc` | 7곳에서 동일한 5문자(`& < > " '`) 치환을 재구현. 순수 유틸 파일(또는 `ui.js`) 하나로 통합 가능(단 `region_map`·`bars` 등 Node 단위테스트용 순수 모듈은 DOM 없는 작은 `html_esc.js`로 분리하면 `ui.js` 의존 없이 통합 가능) |
| 2 | **유한 숫자 변환 (`null` 허용)** | `db_peer.js:28` `toNumOrNull`<br>`db_team_extras.js:23` `num`<br>`team_keystats.js:18` `num`<br>`score_fairness.js:7` `num` (숫자형만 허용) | `db_peer.js`, `db_team_extras.js`, `team_keystats.js` 3곳은 `null/undefined/''` → `null`, 그 외 `Number.isFinite(Number(v))`로 완전히 동일 |
| 3 | **그래프 링크 끝점 ID 추출** | `views/graph.js:37` `endId`<br>`views/graph_model.js:134` `endId`<br>`views/graph_panel.js:31` `endId` | 3개 파일 모두 정확히 동일한 1줄 `const endId = v => (v && typeof v === 'object' ? v.id : v);`. `graph_model.js`에서 `export`해 공유 가능 |
| 4 | **최근 N개월 `YYYY-MM` 배열 생성** | `views/city_page.js:42` `recentMonths(asOf, n)`<br>`views/venues_list.js:62` `lastMonths(asOf, n = 12)`<br>`views/venue.js:45` `buildMonthlyWindow` 내부 `makeMonths`<br>`views/team.js:109` `renderMonthlyBarsHtml` 내부 루프 | 모두 `Date.UTC(y, m - 1 - i, 1)`로 최근 N개월 `YYYY-MM` 목록 생성. 공통 날짜 유틸 1개로 통일 가능 |
| 5 | **토스트 이벤트 발송** | `components/compare_tray.js:15` `toast(msg)`<br>`components/mini_player.js:118` `toast(msg)`<br>+ 인라인 `CustomEvent('app:toast', ...)` 5곳 (`chart_png.js:80`, `ui.js:1180,1184`, `views/venue.js:600`, `views/watchlist.js:406`) | 모두 `window.dispatchEvent(new CustomEvent('app:toast', { detail: msg }))` 호출. `ui.js`의 공용 `emitToast(msg)` 1개로 통합 가능 |
| 6 | **문자열 말줄임 (`…`)** | `components/venue_flow.js:31` `short(name, max = 9)`<br>`views/graph_model.js:234` `shortLabel(text, maxLen = 14)` | 둘 다 최대 길이를 넘으면 잘라 `…`를 붙임 (`short`는 `Array.from` 사용, `shortLabel`은 `.slice` 사용) |
| 7 | **유튜브 `youtube-nocookie` 임베드 URL** | `player_pick.js:116` `embedSrc`<br>`views/team.js:814-817` (인라인 정규식 + `iframe src`) | `team.js`가 `player_pick.js`의 `embedSrc({ kind: 'youtube', id }, { autoplay: true })` 대신 정규식과 임베드 URL을 별도 작성 |
| 8 | **Blob 파일 다운로드** | `chart_png.js:29` `download(blob, filename)`<br>`state.js:888-896` (`exportTableToCsv` 내부 인라인) | `URL.createObjectURL(blob)` → `<a download>` 클릭 → `revokeObjectURL` 패턴 동일 |
| 9 | **rAF 기반 버튼 상태 일괄 동기화** | `components/compare_tray.js:39-55` (`markButtons` + `scheduleMark`)<br>`components/mini_player.js:101-116` (`markButtons` + `scheduleMark`) | `MutationObserver` + `requestAnimationFrame`으로 `[data-*]` 버튼 토글 상태를 갱신하는 구조가 거의 동일 (도메인 속성은 달라 우선순위 낮음) |
