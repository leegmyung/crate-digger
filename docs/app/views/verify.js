/**
 * 정보 구조 v2 '검증' 묶음 (#/verify/<쪽>)
 * 7개 검증 화면(백테스트 · 출처 성적표 · 정답 등급·같은 집안 · 신호별 적중률 · 리드타임·연차 · 데이터 품질 · SQL)을
 * 하나의 상단 탭 줄로 통합한다. quality.js 와 sql.js 도 renderVerifyNavHtml()을 같이 쓴다.
 */
import { appState, hasCustomWeights, setExportContext } from '../state.js';
import { loadSourceRoles, queryOutcomeGradeSummary } from '../db.js';
import {
  escapeHtml, fmtInt, renderActionBanner, renderOutcomeGradeGuideHtml,
  SOURCE_LABELS, TERMS,
} from '../ui.js';

export const VERIFY_PAGES = [
  { id: 'backtest', label: '점수 신뢰도·백테스트', href: '#/verify/backtest' },
  { id: 'scorecard', label: '출처 성적표', href: '#/verify/scorecard' },
  { id: 'grades', label: '정답 등급·같은 집안', href: '#/verify/grades' },
  { id: 'signals', label: '신호별 적중률', href: '#/verify/signals' },
  { id: 'evidence', label: '리드타임·연차', href: '#/verify/evidence' },
  { id: 'quality', label: '데이터 품질', href: '#/verify/quality' },
  { id: 'sql', label: 'SQL', href: '#/verify/sql' },
];

const TAB_LOADERS = {
  backtest: () => import('./backtest.js').then(m => m.renderBacktestView),
  scorecard: () => import('./scorecard.js').then(m => m.renderScorecardView),
  signals: () => import('./signals.js').then(m => m.renderSignalsView),
  evidence: () => import('./evidence.js').then(m => m.renderEvidenceView),
};

/** 검증 묶음 공통 상단 탭 줄 — verify.js · quality.js · sql.js 공용 */
export function renderVerifyNavHtml(activeId) {
  const customW = hasCustomWeights();
  const healthOk = appState.dataHealth ? appState.dataHealth.ok : true;
  return `
    <div class="verify-nav-wrap">
      <nav class="verify-nav-tabs" role="tablist" aria-label="검증 하위 화면">
        ${VERIFY_PAGES.map(p => {
          const active = p.id === activeId;
          const badge = p.id === 'backtest' && customW
            ? '<span class="verify-tab-badge">수정됨</span>'
            : (p.id === 'quality' && !healthOk ? '<span class="verify-tab-dot" title="수집 점검 필요" aria-label="수집 점검 필요"></span>' : '');
          return `
            <a
              class="verify-tab${active ? ' is-active' : ''}"
              role="tab"
              aria-selected="${active ? 'true' : 'false'}"
              href="${p.href}"
              data-verify-nav="${p.id}"
            >
              <span>${escapeHtml(p.label)}</span>${badge}
            </a>
          `;
        }).join('')}
      </nav>
    </div>
  `;
}

function formatHouseSource(raw) {
  const s = String(raw || '').trim();
  if (!s) return '—';
  const idx = s.indexOf(':');
  if (idx < 0) return SOURCE_LABELS[s] || appState.programLabels?.get(s) || s;
  const branch = s.slice(0, idx);
  const key = s.slice(idx + 1);
  const label = appState.programLabels?.get(key) || SOURCE_LABELS[key] || key;
  return `${branch} · ${label}`;
}

function formatHouseOutcome(key, sourceRoles) {
  const k = String(key || '').trim();
  const fromRoles = sourceRoles?.outcomes?.[k]?.label || sourceRoles?.outcomes?.[k]?.name;
  return appState.programLabels?.get(k) || fromRoles || SOURCE_LABELS[k] || k;
}

function renderGradesView(subRoot, { sourceRoles, gradeRows }) {
  setExportContext({ csvLabel: '', csvFilename: '', csvHeaders: [], csvRows: [] });

  const gradeGuideHtml = renderOutcomeGradeGuideHtml({ sourceRoles, gradeRows });
  const sameHouseRaw = Array.isArray(sourceRoles?.same_house) ? sourceRoles.same_house : [];
  const sameHouseRules = sameHouseRaw.filter(x => x && !x._설명 && (Array.isArray(x.sources) || Array.isArray(x.outcomes)));
  const appliedCount = sameHouseRules.filter(x => x.apply !== false).length;

  const candExclObj = (sourceRoles?.candidate_rules && typeof sourceRoles.candidate_rules.excluded_teams === 'object')
    ? sourceRoles.candidate_rules.excluded_teams
    : {};
  const candExclEntries = Object.entries(candExclObj).filter(([k]) => !k.startsWith('_'));

  const bannerHtml = renderActionBanner({
    title: `${TERMS.outcomeWithTech} 등급 · 같은 집안 규칙`,
    lead: `정답 프로그램별 가중치(S·A·B), 후보 등급 하향, '같은 집안' 적중 제외 짝 <strong>${fmtInt(appliedCount)}건</strong>(표시만 ${fmtInt(sameHouseRules.length - appliedCount)}건), 후보 제외 항목 <strong>${fmtInt(candExclEntries.length)}건</strong>을 한곳에 공개합니다.`,
    todo: '검증 성적표와 백테스트는 이 규칙(docs/lab/data/source_roles.json · outcomes.csv)을 그대로 따릅니다.',
    buttonsHtml: `
      <a class="btn btn-sm" href="#/verify/backtest">백테스트 →</a>
      <a class="btn btn-sm" href="#/verify/scorecard">출처 성적표 →</a>
    `,
  });

  const sameHouseRowsHtml = sameHouseRules.length
    ? `
      <div class="table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>출처</th>
              <th>짝 정답</th>
              <th class="nowrap">적용</th>
              <th>이유</th>
            </tr>
          </thead>
          <tbody>
            ${sameHouseRules.map(rule => {
              const srcs = (rule.sources || []).map(formatHouseSource).join(', ');
              const outs = (rule.outcomes || []).map(k => formatHouseOutcome(k, sourceRoles)).join(', ');
              const applied = rule.apply !== false;
              return `
                <tr>
                  <td>${escapeHtml(srcs)}</td>
                  <td><strong>${escapeHtml(outs)}</strong></td>
                  <td class="nowrap">
                    <span class="same-house-badge ${applied ? 'is-applied' : 'is-note'}">${applied ? '제외 적용' : '표시만'}</span>
                  </td>
                  <td class="small muted">${escapeHtml(rule.reason || '')}</td>
                </tr>
              `;
            }).join('')}
          </tbody>
        </table>
      </div>
    `
    : '<p class="small muted" style="margin:0;">등록된 같은 집안 규칙이 없습니다.</p>';

  const candExclHtml = candExclEntries.length
    ? `
      <section class="block verify-grades-section">
        <div class="block-head">
          <div>
            <h2>3. 후보 제외 목록 (팀 아닌 계정·문구)</h2>
            <span class="block-meta">${fmtInt(candExclEntries.length)}건 · 매체·공연장·레이블·기사 제목 오인 항목 제외</span>
          </div>
        </div>
        <details class="info-fold">
          <summary>제외 목록 ${fmtInt(candExclEntries.length)}건 펼쳐 보기</summary>
          <div class="info-fold-body">
            <div class="table-wrap">
              <table class="data-table">
                <thead>
                  <tr>
                    <th>제외 키</th>
                    <th>사유</th>
                  </tr>
                </thead>
                <tbody>
                  ${candExclEntries
                    .sort((a, b) => a[0].localeCompare(b[0], 'ko'))
                    .map(([k, reason]) => `
                      <tr>
                        <td class="mono nowrap">${escapeHtml(k)}</td>
                        <td class="small muted">${escapeHtml(String(reason || ''))}</td>
                      </tr>
                    `).join('')}
                </tbody>
              </table>
            </div>
          </div>
        </details>
      </section>
    `
    : '';

  subRoot.innerHTML = `
    ${bannerHtml}
    <section class="block verify-grades-section">
      <div class="block-head">
        <div>
          <h2>1. ${TERMS.outcomeWithTech} 등급표 · 정리 규칙</h2>
          <span class="block-meta">outcomes.csv · source_roles.json 기준</span>
        </div>
      </div>
      ${gradeGuideHtml || '<p class="small muted" style="margin:0;">정답 등급 데이터를 불러오지 못했습니다.</p>'}
    </section>

    <section class="block verify-grades-section">
      <div class="block-head">
        <div>
          <h2>2. '같은 집안' 적중 제외 규칙</h2>
          <span class="block-meta">주최·매체가 같은 출처→정답 짝은 자기 예측 부풀림 방지를 위해 적중에서 뺌</span>
        </div>
      </div>
      ${sameHouseRowsHtml}
    </section>

    ${candExclHtml}
  `;
}

export async function renderVerifyView(root) {
  const validIds = new Set(['backtest', 'scorecard', 'grades', 'signals', 'evidence']);
  const activeTab = validIds.has(appState.verifyTab) ? appState.verifyTab : 'backtest';
  appState.verifyTab = activeTab;

  const [sourceRoles, gradeRows, renderSub] = await Promise.all([
    loadSourceRoles(),
    queryOutcomeGradeSummary(),
    activeTab === 'grades'
      ? Promise.resolve(null)
      : (TAB_LOADERS[activeTab] || TAB_LOADERS.backtest)(),
  ]);

  delete root.dataset.skelPending;
  root.innerHTML = `
    <div class="verify-page" id="verifyPageRoot">
      ${renderVerifyNavHtml(activeTab)}
      <div id="verifySubRoot"></div>
      <footer class="verify-foot-bar" aria-label="검증 참고 링크">
        <span class="small muted">검증 기준: outcomes.csv · source_roles.json (집계 범위 ${escapeHtml(appState.outcomeRange.min || '-')} ~ ${escapeHtml(appState.outcomeRange.max || '-')})</span>
        <div class="verify-foot-links">
          ${activeTab !== 'grades' ? '<a href="#/verify/grades">정답 등급·같은 집안 규칙 →</a>' : ''}
          <a href="#/verify/quality">데이터 품질 →</a>
          <a href="#/verify/sql">SQL 직접 실행 →</a>
        </div>
      </footer>
    </div>
  `;

  const subRoot = root.querySelector('#verifySubRoot');
  if (activeTab === 'grades') {
    renderGradesView(subRoot, { sourceRoles, gradeRows });
  } else {
    await renderSub(subRoot);
  }
}
