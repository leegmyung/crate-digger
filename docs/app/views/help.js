// 사용 안내 #/help — 새 정보 구조(docs/app_structure_v2.md)를 처음 보는 사람이 헤매지 않게.
// 메뉴별 한 줄 · 자주 쓰는 흐름 3개 · 단축키 · 꼬리표 뜻. 데이터는 읽지 않는 정적 화면.
const MENUS = [
  ['홈', '#/home', '이번 주 브리핑 — 새 수상·선정·새 선정·언급 전 신인 첫 언급 같은 알림 요약과 저장 필터에 새로 들어온 팀.'],
  ['발굴', '#/discover', '조건(장르·지역·첫 발매·단계·신호)으로 후보를 거르는 곳. 표 ↔ 색 지도 전환, 조건 저장.'],
  ['차트', '#/charts', '정의가 정해진 순위표 — 지금은 갓 데뷔(첫 발매 뒤 언급)부터. 전체·장르·도시·떠오르는은 준비 중.'],
  ['공연장', '#/venues', '이번 달 공연·씬 묶음, 공연장 목록(크기·종류), 공연장마다 출연 팀·전후 흐름.'],
  ['도시', '#/cities', '서울 밖까지 — 도시별 공연장·첫 무대 신인·이 도시에서 뜨는 후보.'],
  ['페스티벌', '#/festivals', '펜타포트·부산록페·DMZ 등 라인업과 그 뒤 수상·선정 연결.'],
  ['알림', '#/alerts', '받은 알림과 알림 규칙을 모을 곳(준비 중) — 지금은 홈의 알림 요약을 보세요.'],
  ['내 목록', '#/mine', '관심 팀(상태: 지켜보는 중·들어봄·보류)·구독 공연장·저장한 필터.'],
  ['검증 (고급)', '#/verify/backtest', '점수가 맞는지 — 백테스트·출처 성적표·신호 원본·데이터 품질·SQL. 각 화면의 "근거:" 줄이 여기로 이어져요.'],
];

const FLOWS = [
  {
    title: '이번 주 새 신인 보기',
    steps: [
      ['홈', '#/home', '에서 이번 주 알림 요약을 훑고'],
      ['차트 → 갓 데뷔', '#/charts/debut', '에서 첫 발매 뒤 처음 언급된 팀을 본 다음'],
      ['팀 이름', null, '을 누르면 팀 페이지(개요 탭)가 열려요.'],
    ],
  },
  {
    title: '조건 저장해 알림 받기',
    steps: [
      ['발굴', '#/discover', '에서 조건을 걸고(예: 첫 발매 24개월 · 서울 밖)'],
      ['☆ 이 조건 담기', null, '를 누르면'],
      ['홈', '#/home', '의 "저장 필터에 새로 들어온 팀"과 내 목록에 다음부터 새 팀이 떠요.'],
    ],
  },
  {
    title: '팀 근거 확인',
    steps: [
      ['팀 페이지', null, '의 탭에서 점수(항목 막대·같은 단계 비교) · 사건(별점·전후 28일) · 공연을 보고'],
      ['탭 아래 "근거:" 줄', null, '을 누르면 검증 화면(백테스트·출처 성적표·신호 원본)으로 가요.'],
      ['정보가 틀려요 ↗', null, '로 잘못된 팀 정보를 제보할 수 있어요(공개 이슈 — 연락처는 적지 마세요).'],
    ],
  },
];

const KEYS = [
  ['/', '어디서든 위쪽 검색창 열기 (팀·공연장·도시·페스티벌)'],
  ['↑ ↓', '검색 결과에서 위아래로 고르기'],
  ['Enter', '고른 결과 열기 (아무것도 안 골랐으면 첫 결과)'],
  ['Esc', '검색 결과 닫기 · 휴대폰 메뉴 닫기'],
  ['← →', '팀 페이지 탭 사이 이동 (탭에 초점이 있을 때)'],
];

const TAGS = [
  ['신인 미확인', 'tag-pill tag-unverified', '첫 발매일을 아직 못 찾아, 수집을 시작한 직후 처음 보인 팀이 진짜 신인인지 확실하지 않음.'],
  ['추정', 'genre-inferred-tag', '장르를 플랫폼 정보가 아니라 같이 나온 팀·출처로 미루어 짐작함.'],
  ['리뷰', 'genre-inferred-tag', '장르를 웹진 리뷰(음악취향Y·overtone·VISLA)가 곡·앨범에 붙인 장르로 정함. 팀 장르와 다를 수 있어 약하게 표시.'],
  ['추정 (근거 약함)', 'genre-inferred-tag genre-tag-low', '같은 무대에 장르를 아는 팀이 1팀뿐이라 그 장르로 짐작함. 맞는 비율이 절반 정도라 참고로만.'],
  ['휴면', 'tag-pill tag-dormant', '최근 180일 신호 0건이고 최근 1년 공연도 0건 — 활동을 쉬는 것으로 보임.'],
  ['참고', 'tag-pill', '점수에 안 쓰는 출처(검증 대기·제외) 신호거나, 점수에 넣지 않는 화면 정보(사건 별점·공연장 크기 상승 등).'],
];

function link(label, href) {
  return href ? `<a href="${href}">${label}</a>` : `<strong>${label}</strong>`;
}

export async function renderHelpView(root) {
  root.innerHTML = `
    <section class="help-view">
      <h1 class="view-title">사용 안내</h1>
      <p class="muted">Gigle Research는 국내 인디 신인을 일찍 찾기 위한 앱이에요. 매일 21시에 데이터가 새로 들어옵니다.
        위쪽 검색창(<kbd>/</kbd>)으로 팀·공연장·도시·페스티벌을 바로 찾을 수 있어요.</p>

      <section class="block help-block" aria-labelledby="helpMenus">
        <h2 id="helpMenus">메뉴</h2>
        <dl class="help-menus">
          ${MENUS.map(([label, href, desc]) => `<dt>${link(label, href)}</dt><dd>${desc}</dd>`).join('')}
        </dl>
      </section>

      <section class="block help-block" aria-labelledby="helpFlows">
        <h2 id="helpFlows">자주 쓰는 흐름</h2>
        <ol class="help-flows">
          ${FLOWS.map(f => `<li><h3>${f.title}</h3><p>${f.steps.map(([l, h, t]) => `${link(l, h)}${t}`).join(' ')}</p></li>`).join('')}
        </ol>
      </section>

      <section class="block help-block" aria-labelledby="helpKeys">
        <h2 id="helpKeys">단축키</h2>
        <table class="help-keys">
          <tbody>${KEYS.map(([k, d]) => `<tr><th scope="row"><kbd>${k}</kbd></th><td>${d}</td></tr>`).join('')}</tbody>
        </table>
      </section>

      <section class="block help-block" aria-labelledby="helpTags">
        <h2 id="helpTags">꼬리표 뜻</h2>
        <dl class="help-tags">
          ${TAGS.map(([label, cls, desc]) => `<dt><span class="${cls}">${label}</span></dt><dd>${desc}</dd>`).join('')}
        </dl>
      </section>

      <p class="muted small">더 자세히: <a href="https://github.com/leegmyung/crate-digger/blob/main/docs/glossary.md" target="_blank" rel="noopener noreferrer">용어 정리</a> ·
        <a href="https://github.com/leegmyung/crate-digger/blob/main/docs/methods.md" target="_blank" rel="noopener noreferrer">방법론</a> ·
        <a href="https://github.com/leegmyung/crate-digger/blob/main/docs/app_structure_v2.md" target="_blank" rel="noopener noreferrer">화면 구조</a></p>
    </section>`;
}
