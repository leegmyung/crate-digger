import { appState } from '../state.js';
import { runRawSql } from '../db.js';
import { escapeHtml, fmtInt, friendlySqlError, renderActionBanner } from '../ui.js';

let savedEditorText = '';

export async function renderSqlView(root) {
  const bannerHtml = renderActionBanner({
    title: 'SQL 직접 실행',
    lead: '브라우저 안 DuckDB-WASM에 올라온 표(<code>signals</code>, <code>teams</code>, <code>outcomes</code>, <code>programs</code>, <code>links</code>, <code>videos</code>, <code>images</code>)를 SQL로 직접 조회할 수 있습니다.',
    todo: '아래 선택 창에서 방금 돌아간 SQL을 불러와 조건을 고친 뒤 실행(Ctrl+Enter)해 보세요.',
  });

  const initialSql = savedEditorText ||
    appState.lastSql.backtest ||
    appState.lastSql.candidates ||
    'SELECT branch, COUNT(*) AS rows, COUNT(DISTINCT team_key) AS teams FROM signals GROUP BY branch ORDER BY rows DESC;';

  root.innerHTML = `
    ${bannerHtml}

    <div class="schema-box">
      <strong>사용 가능한 표</strong><br>
      <code class="mono">signals(team_key, branch, source, program, stage_rank, signal_date, venue, role)</code><br>
      <code class="mono">teams(team_key, display_name, first_seen, first_release, fan_count, album_count, profile_status, primary_genre, agency)</code><br>
      <code class="mono">outcomes(team_key, program, program_label, tier, announced_date, counted, grade, weight)</code><br>
      <code class="mono">programs(program, label, kind)</code> · <code class="mono">links(team_key, platform, url)</code> · <code class="mono">videos(team_key, video_id, title, channel_title, published_at, kind)</code> · <code class="mono">images(team_key, url, source)</code><br>
      공통 매크로: <code class="mono">lab_scored(cutoff, lookback_years, newcomer_years, exclude_famous, outcome_tier, horizon_months, genre, branches, w_branch, w_stage, w_peer, w_dmz, w_gigs, w_outlets, outlet_cap, w_recent, w_venues, w_winner, w_context)</code>
    </div>

    <div class="toolbar">
      <div class="toolbar-group">
        <select id="sqlPresetSel" class="select" aria-label="SQL 예시 선택">
          <option value="">예시 SQL 불러오기...</option>
          <option value="candidates">방금 돌린 지금 후보 SQL</option>
          <option value="backtest">방금 돌린 백테스트 SQL</option>
          <option value="signals">방금 돌린 신호별 적중률 SQL</option>
          <option value="scorecard">방금 돌린 출처 성적표 SQL</option>
          <option value="precedents">방금 돌린 선례 SQL</option>
          <option value="related">방금 돌린 관련 팀 SQL</option>
          <option value="features">공통 매크로 (features.sql)</option>
          <option value="sample">signals 20행 미리보기</option>
        </select>
      </div>
    </div>

    <textarea id="sqlEditor" class="sql-editor" spellcheck="false" aria-label="SQL 입력">${escapeHtml(initialSql)}</textarea>

    <div class="toolbar" style="margin-top:8px;">
      <div class="toolbar-group">
        <button type="button" class="btn btn-primary" id="btnRunSql">실행 (Ctrl+Enter)</button>
        <span class="small muted mono" id="sqlMeta"></span>
      </div>
    </div>

    <div id="sqlError" class="notice notice-err" hidden></div>
    <div class="block" id="sqlResultBlock" hidden style="padding:0;overflow:hidden;">
      <div class="table-wrap" id="sqlResultWrap"></div>
    </div>
  `;

  const editor = root.querySelector('#sqlEditor');
  const errEl = root.querySelector('#sqlError');
  const metaEl = root.querySelector('#sqlMeta');
  const resBlock = root.querySelector('#sqlResultBlock');
  const resWrap = root.querySelector('#sqlResultWrap');

  editor.addEventListener('input', () => { savedEditorText = editor.value; });

  async function exec() {
    const sql = editor.value.trim();
    savedEditorText = sql;
    errEl.hidden = true;
    if (!sql) {
      errEl.hidden = false;
      errEl.textContent = '실행할 SQL을 입력해 주세요.';
      return;
    }
    metaEl.textContent = '실행 중...';
    const t0 = performance.now();
    try {
      const { columns, rows } = await runRawSql(sql);
      const ms = (performance.now() - t0).toFixed(0);
      const cap = 500;
      const shown = rows.slice(0, cap);
      metaEl.textContent = rows.length > cap
        ? `${fmtInt(rows.length)}행 중 상위 ${cap}행 표시 (${ms}ms)`
        : `${fmtInt(rows.length)}행 (${ms}ms)`;
      resBlock.hidden = false;
      if (!columns.length) {
        resWrap.innerHTML = '<p class="muted small" style="padding:12px;margin:0;">실행 완료 (반환 행 없음)</p>';
        return;
      }
      const head = columns.map(c => `<th>${escapeHtml(c)}</th>`).join('');
      const body = shown.map(r => `<tr>${columns.map(c => {
        const v = r[c];
        return `<td class="${typeof v === 'number' ? 'num' : ''}">${v === null || v === undefined ? '<span class="muted">NULL</span>' : escapeHtml(v)}</td>`;
      }).join('')}</tr>`).join('');
      resWrap.innerHTML = `<table class="data-table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
    } catch (err) {
      metaEl.textContent = '오류';
      resBlock.hidden = true;
      errEl.hidden = false;
      errEl.textContent = friendlySqlError(err);
    }
  }

  root.querySelector('#sqlPresetSel')?.addEventListener('change', (e) => {
    const k = e.target.value;
    if (!k) return;
    if (k === 'candidates') editor.value = appState.lastSql.candidates || appState.sqlTemplates.candidates;
    else if (k === 'backtest') editor.value = appState.lastSql.backtest || appState.sqlTemplates.backtest;
    else if (k === 'signals') editor.value = appState.lastSql.signals || appState.sqlTemplates.signal_hits;
    else if (k === 'scorecard') editor.value = appState.lastSql.scorecard || appState.sqlTemplates.source_scorecard;
    else if (k === 'precedents') editor.value = appState.lastSql.precedents || appState.sqlTemplates.precedents;
    else if (k === 'related') editor.value = appState.lastSql.related || appState.sqlTemplates.related;
    else if (k === 'features') editor.value = appState.sqlTemplates.features;
    else if (k === 'sample') editor.value = 'SELECT * FROM signals ORDER BY signal_date DESC LIMIT 20;';
    savedEditorText = editor.value;
  });

  root.querySelector('#btnRunSql').addEventListener('click', exec);
  editor.addEventListener('keydown', e => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      exec();
    }
  });
}
