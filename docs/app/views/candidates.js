import { appState, navigateTo, syncHash } from '../state.js';
import { queryCandidates } from '../db.js';
import {
  clampDateDisplay, escapeHtml, fmtInt, fmtNum,
  renderActionBanner, renderEmptyState, renderScoreBar, watchButtonHtml,
} from '../ui.js';

function sortRows(rows, col, dir) {
  const mult = dir === 'asc' ? 1 : -1;
  return [...rows].sort((a, b) => {
    const va = a[col];
    const vb = b[col];
    if (va === vb) return 0;
    if (va === null || va === undefined) return 1;
    if (vb === null || vb === undefined) return -1;
    if (typeof va === 'number' && typeof vb === 'number') return (va - vb) * mult;
    return String(va).localeCompare(String(vb), 'ko') * mult;
  });
}

export async function renderCandidatesView(root) {
  const rows = await queryCandidates();
  const c = appState.cfg;
  const maxScore = Math.max(1, ...rows.map(r => Number(r.score) || 0));
  let visibleCount = 20;

  const topName = rows[0] ? `${rows[0].display_name} (${fmtNum(rows[0].score, 2)}점)` : '없음';
  const bannerHtml = renderActionBanner({
    title: '후보 탐색',
    lead: `조건에 맞는 상위 <strong>${fmtInt(rows.length)}팀</strong> 중 1위는 ${escapeHtml(topName)}입니다.`,
    todo: '열 머리를 눌러 정렬하거나, 팀 줄을 눌러 아티스트 정보·선례·타임라인을 확인하세요.',
  });

  root.innerHTML = `
    ${bannerHtml}

    <details class="info-fold">
      <summary>ⓘ 신인 기준·점수 구성 안내</summary>
      <div class="info-fold-body">
        '신인 추정'은 우리 데이터에 처음 등장한 지 <strong>${c.newcomer_years}년</strong> 이내라는 기준이라 오래 활동한 팀이 섞일 수 있습니다. 프로필(멜론 등)이 채워질수록 정확해집니다.
        점수 구성 막대는 0점보다 큰 항목만 표시합니다 (갈래 · 선정 단계 · 공연장 수 · 최근 6개월 활동 · 수상 팀과 같은 무대 · 큐레이션 매체 등).
      </div>
    </details>

    <div class="toolbar">
      <div class="toolbar-group">
        <input type="search" id="candFilterInput" class="input" style="width:200px;" placeholder="표 안에서 이름 필터...">
        <label class="f-check small">
          <input type="checkbox" id="candOnlyNoOutcome" ${c.only_no_outcome ? 'checked' : ''}>
          <span>기정답 제외</span>
        </label>
      </div>
      <div class="toolbar-group">
        <span class="small muted" id="candCountText"></span>
        <select id="candLimitSel" class="select" aria-label="조회 상한">
          <option value="50" ${c.limit === 50 ? 'selected' : ''}>조회 50팀</option>
          <option value="100" ${c.limit === 100 ? 'selected' : ''}>조회 100팀</option>
          <option value="200" ${c.limit === 200 ? 'selected' : ''}>조회 200팀</option>
        </select>
      </div>
    </div>

    <div class="block" style="padding:0;overflow:hidden;">
      <div class="table-wrap">
        <table class="data-table" id="candTable">
          <thead>
            <tr>
              <th class="num">#</th>
              <th class="sortable" data-sort="display_name">팀</th>
              <th class="num sortable" data-sort="score">점수</th>
              <th>구성</th>
              <th class="num sortable" data-sort="n_branch">갈래</th>
              <th class="num sortable" data-sort="gigs_1y">1년 공연</th>
              <th class="nowrap sortable" data-sort="first_seen">첫 등장</th>
              <th class="nowrap sortable" data-sort="last_seen">최근 신호</th>
              <th class="nowrap">관심</th>
            </tr>
          </thead>
          <tbody id="candTbody"></tbody>
        </table>
      </div>
      <div class="more-row" id="candMoreRow" hidden></div>
    </div>
  `;

  function paintTable() {
    const q = (root.querySelector('#candFilterInput')?.value || '').trim().toLowerCase();
    let list = q
      ? rows.filter(r =>
          String(r.display_name || '').toLowerCase().includes(q) ||
          String(r.team_key || '').toLowerCase().includes(q) ||
          String(r.primary_genre || '').toLowerCase().includes(q))
      : rows;
    list = sortRows(list, appState.candSort.col, appState.candSort.dir);

    const shown = list.slice(0, visibleCount);
    root.querySelector('#candCountText').textContent = `${fmtInt(shown.length)} / ${fmtInt(list.length)}팀`;

    root.querySelectorAll('th.sortable').forEach(th => {
      const col = th.dataset.sort;
      const baseLabel = th.dataset.label || th.textContent.replace(/ [▲▼]$/, '');
      th.dataset.label = baseLabel;
      th.textContent = col === appState.candSort.col
        ? `${baseLabel} ${appState.candSort.dir === 'asc' ? '▲' : '▼'}`
        : baseLabel;
    });

    const tbody = root.querySelector('#candTbody');
    if (!shown.length) {
      tbody.innerHTML = `<tr><td colspan="9" style="padding:0;border:none;">${renderEmptyState({
        title: '조건에 맞는 후보 팀이 없습니다',
        message: '검색어 또는 필터 조건을 줄여 보거나 초기화해 보세요.',
        showReset: true,
      })}</td></tr>`;
      root.querySelector('#candMoreRow').hidden = true;
      return;
    }

    tbody.innerHTML = shown.map((r, idx) => {
      const sub = [];
      if (r.primary_genre) sub.push(r.primary_genre);
      if (r.had_outcome) sub.push('기정답');
      const subHtml = sub.length ? `<div class="muted small">${escapeHtml(sub.join(' · '))}</div>` : '';
      return `
        <tr class="clickable" tabindex="0" data-team-key="${escapeHtml(r.team_key)}">
          <td class="num muted">${idx + 1}</td>
          <td><strong>${escapeHtml(r.display_name || r.team_key)}</strong>${subHtml}</td>
          <td class="num"><strong>${fmtNum(r.score, 2)}</strong></td>
          <td>${renderScoreBar(r, maxScore)}</td>
          <td class="num">${fmtInt(r.n_branch)}</td>
          <td class="num">${fmtInt(r.gigs_1y)}</td>
          <td class="nowrap mono muted">${escapeHtml(r.first_seen || '-')}</td>
          <td class="nowrap mono muted">${escapeHtml(clampDateDisplay(r.last_seen))}</td>
          <td class="nowrap">${watchButtonHtml(r.team_key, r.display_name || r.team_key, true)}</td>
        </tr>
      `;
    }).join('');

    const moreRow = root.querySelector('#candMoreRow');
    const rem = list.length - shown.length;
    if (rem > 0) {
      moreRow.hidden = false;
      moreRow.innerHTML = `
        <span>${fmtInt(shown.length)} / ${fmtInt(list.length)}팀 표시</span>
        <button type="button" class="btn btn-sm" id="btnCandMore">${fmtInt(Math.min(20, rem))}팀 더 보기</button>
      `;
      moreRow.querySelector('#btnCandMore').addEventListener('click', () => {
        visibleCount += 20;
        paintTable();
      });
    } else {
      moreRow.hidden = true;
    }
  }

  paintTable();

  root.querySelector('#candFilterInput').addEventListener('input', () => {
    visibleCount = 20;
    paintTable();
  });

  root.querySelector('#candOnlyNoOutcome').addEventListener('change', (e) => {
    appState.cfg.only_no_outcome = e.target.checked;
    syncHash(true);
    window.dispatchEvent(new CustomEvent('app:recompute'));
  });

  root.querySelector('#candLimitSel').addEventListener('change', (e) => {
    appState.cfg.limit = Number(e.target.value) || 100;
    syncHash(true);
    window.dispatchEvent(new CustomEvent('app:recompute'));
  });

  root.querySelectorAll('th.sortable').forEach(th => {
    th.setAttribute('tabindex', '0');
    const onSort = () => {
      const col = th.dataset.sort;
      if (appState.candSort.col === col) {
        appState.candSort.dir = appState.candSort.dir === 'desc' ? 'asc' : 'desc';
      } else {
        appState.candSort.col = col;
        appState.candSort.dir = (col === 'display_name') ? 'asc' : 'desc';
      }
      paintTable();
    };
    th.addEventListener('click', onSort);
    th.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        onSort();
      }
    });
  });

  const tbodyEl = root.querySelector('#candTbody');
  tbodyEl.addEventListener('click', (e) => {
    if (e.target.closest('button[data-watch-key]') || e.target.closest('button[data-action]')) return;
    const tr = e.target.closest('tr.clickable');
    if (tr && tr.dataset.teamKey) {
      navigateTo('team', tr.dataset.teamKey);
    }
  });
  tbodyEl.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    if (e.target.closest('button')) return;
    const tr = e.target.closest('tr.clickable');
    if (tr && tr.dataset.teamKey) {
      e.preventDefault();
      navigateTo('team', tr.dataset.teamKey);
    }
  });
}
