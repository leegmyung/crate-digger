import { appState, hasCustomWeights, syncHash } from '../state.js';
import { loadSourceRoles, queryOutcomeGradeSummary } from '../db.js';
import { renderOutcomeGradeGuideHtml } from '../ui.js';
import { renderBacktestView } from './backtest.js';
import { renderSignalsView } from './signals.js';
import { renderEvidenceView } from './evidence.js';
import { renderScorecardView } from './scorecard.js';

const TABS = [
  { id: 'backtest', label: '과거 검증 · 가중치' },
  { id: 'signals', label: '신호별 적중률' },
  { id: 'evidence', label: '리드타임 · 연차' },
  { id: 'scorecard', label: '출처 성적표' },
];

export async function renderVerifyView(root) {
  const activeTab = TABS.some(t => t.id === appState.verifyTab) ? appState.verifyTab : 'backtest';
  appState.verifyTab = activeTab;
  const customW = hasCustomWeights();

  const [sourceRoles, gradeRows] = await Promise.all([
    loadSourceRoles(),
    queryOutcomeGradeSummary(),
  ]);
  const gradeGuideHtml = renderOutcomeGradeGuideHtml({ sourceRoles, gradeRows });

  delete root.dataset.skelPending;
  root.innerHTML = `
    <div class="verify-shell-head">
      <div class="sub-tabs" role="tablist" aria-label="점수 신뢰도·검증 하위 탭">
        ${TABS.map(t => `
          <button type="button"
                  class="sub-tab-btn ${activeTab === t.id ? 'active' : ''}"
                  role="tab"
                  aria-selected="${activeTab === t.id ? 'true' : 'false'}"
                  data-verify-tab="${t.id}">
            ${t.label}${t.id === 'backtest' && customW ? ' · 수정됨' : ''}
          </button>
        `).join('')}
      </div>
    </div>
    <div id="verifySubRoot"></div>
    ${gradeGuideHtml ? `
      <details class="info-fold verify-grade-fold" id="verifyGradeFold" style="margin-top:16px;">
        <summary>ⓘ 정답 등급표 · 정리 규칙 (outcomes.csv · source_roles.json 기준)</summary>
        <div class="info-fold-body">
          ${gradeGuideHtml}
        </div>
      </details>
    ` : ''}
  `;

  root.querySelectorAll('[data-verify-tab]').forEach(btn => {
    btn.addEventListener('click', () => {
      const next = btn.dataset.verifyTab;
      if (next === appState.verifyTab) return;
      appState.verifyTab = next;
      syncHash(true);
      window.dispatchEvent(new CustomEvent('app:route'));
    });
  });

  const subRoot = root.querySelector('#verifySubRoot');
  if (activeTab === 'signals') {
    await renderSignalsView(subRoot);
  } else if (activeTab === 'evidence') {
    await renderEvidenceView(subRoot);
  } else if (activeTab === 'scorecard') {
    await renderScorecardView(subRoot);
  } else {
    await renderBacktestView(subRoot);
  }
}
