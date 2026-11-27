import {
  ALL_BRANCHES, appState, getActiveFilterSummary, navigateTo,
  setExportContext, syncHash,
} from '../state.js';
import {
  buildNextGigByTeam, getSnapshotDiff, queryCandidates, queryUpcomingGigs,
} from '../db.js';
import {
  avatarHtml, escapeHtml, fmtInt, fmtNum, formatNextGigText, plainWhyLine,
  renderActionBanner, renderEmptyState, spotifyButtonHtml, watchButtonHtml,
  wireAvatarFallbacks, wireSpotifyButtons, youtubeQuickInfo,
} from '../ui.js';

const VALID_SORT_COLS = new Set(['score', 'display_name', 'next_gig_sort']);

function sortRows(rows, col, dir) {
  const safeCol = VALID_SORT_COLS.has(col) ? col : 'score';
  const mult = dir === 'asc' ? 1 : -1;
  return [...rows].sort((a, b) => {
    if (safeCol === 'next_gig_sort') {
      const da = a.next_gig?.signal_date || '9999-12-31';
      const db = b.next_gig?.signal_date || '9999-12-31';
      if (da !== db) return da.localeCompare(db) * mult;
      return (Number(b.score) || 0) - (Number(a.score) || 0);
    }
    const va = a[safeCol];
    const vb = b[safeCol];
    if (va === vb) return 0;
    if (va === null || va === undefined) return 1;
    if (vb === null || vb === undefined) return -1;
    if (typeof va === 'number' && typeof vb === 'number') return (va - vb) * mult;
    return String(va).localeCompare(String(vb), 'ko') * mult;
  });
}

function renderRowListenControl(r) {
  const sp = spotifyButtonHtml(r.team_key, true, {
    iconOnly: true,
    mode: 'table-row',
    teamName: r.display_name || r.team_key,
  });
  if (sp) return sp;

  const yt = youtubeQuickInfo(r.team_key);
  if (yt && yt.kind === 'channel') {
    return `<a class="btn btn-icon btn-yt-mini" href="${escapeHtml(yt.url)}" target="_blank" rel="noopener noreferrer" title="유튜브 공식 채널" aria-label="${escapeHtml(r.display_name || r.team_key)} 유튜브 공식 채널">YT</a>`;
  }
  if (yt && yt.kind === 'video') {
    return `<a class="btn btn-icon btn-yt-mini" href="#/team/${encodeURIComponent(r.team_key)}" title="최근 무대 영상 ${yt.count}개" aria-label="${escapeHtml(r.display_name || r.team_key)} 무대 영상">영상</a>`;
  }
  return '';
}

export async function renderCandidatesView(root) {
  const asOf = appState.cfg.as_of || appState.dataEnd || '2026-11-27';
  const [rawRows, upcomingRaw] = await Promise.all([
    queryCandidates(),
    queryUpcomingGigs({ asOf }),
  ]);

  const c = appState.cfg;
  const nextGigByTeam = buildNextGigByTeam(upcomingRaw);
  const diff = getSnapshotDiff(rawRows);
  const newSet = new Set(diff.newEntrants.map(t => t.team_key));
  const riserMap = new Map(diff.risers.map(t => [t.team_key, t]));

  const rows = rawRows.map(r => {
    const ng = nextGigByTeam.get(r.team_key) || null;
    const riser = riserMap.get(r.team_key) || null;
    return {
      ...r,
      why_line: plainWhyLine(r),
      next_gig: ng,
      next_gig_text: ng ? formatNextGigText(ng) : '',
      is_new: newSet.has(r.team_key),
      riser,
    };
  });

  if (!VALID_SORT_COLS.has(appState.candSort.col)) {
    appState.candSort.col = 'score';
    appState.candSort.dir = 'desc';
  }

  const newCount = rows.filter(r => r.is_new).length;
  const riserCount = rows.filter(r => Boolean(r.riser)).length;
  const upcomingCount = rows.filter(r => Boolean(r.next_gig)).length;
  const filterSummary = getActiveFilterSummary(c);

  let moveFilter = ''; // '' | 'new' | 'riser' | 'upcoming'
  let visibleCount = 20;

  const topName = rows[0] ? `${rows[0].display_name} (${fmtNum(rows[0].score, 2)}점)` : '없음';
  const bannerHtml = renderActionBanner({
    title: '후보 목록',
    lead: rows.length
      ? `신인 후보 상위 <strong>${fmtInt(rows.length)}팀</strong> 중 1위는 <strong>${escapeHtml(topName)}</strong>이며, 예정 공연이 잡힌 팀은 <strong>${fmtInt(upcomingCount)}팀</strong>입니다.`
      : '현재 조건에 맞는 신인 후보가 없습니다.',
  });

  const genreOpts = ['<option value="">전체 장르</option>']
    .concat(appState.validGenres.map(g => `<option value="${escapeHtml(g)}" ${c.genre === g ? 'selected' : ''}>${escapeHtml(g)}</option>`))
    .join('');

  const branchChips = ALL_BRANCHES.map(b => {
    const active = c.branches.includes(b);
    return `<button type="button" class="chip-btn ${active ? 'active' : ''}" data-branch-chip="${escapeHtml(b)}" aria-pressed="${active ? 'true' : 'false'}">${escapeHtml(b)}</button>`;
  }).join('');

  root.innerHTML = `
    ${bannerHtml}

    <section class="inline-filter-bar" aria-label="후보 목록 필터">
      <div class="inline-filter-row">
        <input type="search" id="candFilterInput" class="input cand-search-input" placeholder="팀 이름·장르·이유 검색..." aria-label="표 안에서 팀 검색">

        <select id="candGenreSel" class="select" aria-label="장르 필터">${genreOpts}</select>

        <select id="candPeriodSel" class="select" aria-label="최근 활동 기간">
          <option value="0" ${Number(c.period_days) === 0 ? 'selected' : ''}>전체 기간 (3년)</option>
          <option value="30" ${Number(c.period_days) === 30 ? 'selected' : ''}>최근 30일</option>
          <option value="90" ${Number(c.period_days) === 90 ? 'selected' : ''}>최근 90일</option>
          <option value="180" ${Number(c.period_days) === 180 ? 'selected' : ''}>최근 180일</option>
          <option value="365" ${Number(c.period_days) === 365 ? 'selected' : ''}>최근 365일</option>
        </select>

        <div class="chip-group" role="group" aria-label="신호 갈래 선택">${branchChips}</div>

        <div class="chip-group chip-group-move" role="group" aria-label="이번 주 변동 필터">
          <button type="button" class="chip-btn" data-move-chip="new" aria-pressed="false">새로 들어옴${newCount ? ` ${fmtInt(newCount)}` : ''}</button>
          <button type="button" class="chip-btn" data-move-chip="riser" aria-pressed="false">상승${riserCount ? ` ${fmtInt(riserCount)}` : ''}</button>
          <button type="button" class="chip-btn" data-move-chip="upcoming" aria-pressed="false">예정 공연${upcomingCount ? ` ${fmtInt(upcomingCount)}` : ''}</button>
        </div>

        ${filterSummary.count > 0 ? '<button type="button" class="btn btn-sm" data-action="reset-filters">초기화</button>' : ''}

        <span class="small muted inline-filter-count" id="candCountText"></span>
      </div>

      <details class="inline-more-filters">
        <summary>세부 기준 · 안내 (${c.newcomer_years}년 이내 · ${c.exclude_famous ? '유명 팀 제외' : '유명 팀 포함'} · 상위 ${c.limit}팀)</summary>
        <div class="inline-more-body">
          <div class="inline-more-controls">
            <label class="f-item-inline small">
              <span>신인 기준(년)</span>
              <input type="number" id="candNewcomerInp" class="input input-num" min="1" max="15" value="${c.newcomer_years}">
            </label>
            <label class="f-check small">
              <input type="checkbox" id="candExcludeFamous" ${c.exclude_famous ? 'checked' : ''}>
              <span>유명 팀 제외</span>
            </label>
            <label class="f-check small">
              <input type="checkbox" id="candOnlyNoOutcome" ${c.only_no_outcome ? 'checked' : ''}>
              <span>이미 상 받은 팀 제외</span>
            </label>
            <label class="f-item-inline small">
              <span>조회 상한</span>
              <select id="candLimitSel" class="select" aria-label="조회 상한">
                <option value="50" ${c.limit === 50 ? 'selected' : ''}>50팀</option>
                <option value="100" ${c.limit === 100 ? 'selected' : ''}>100팀</option>
                <option value="200" ${c.limit === 200 ? 'selected' : ''}>200팀</option>
              </select>
            </label>
          </div>
          <p class="small muted" style="margin:8px 0 0 0;">
            '신인 추정'은 우리 데이터 첫 등장 후 <strong>${c.newcomer_years}년</strong> 이내 기준입니다. 팀을 누르면 상세 점수 근거와 무대 영상을 볼 수 있습니다.
          </p>
        </div>
      </details>
    </section>

    <div class="block" style="padding:0;overflow:hidden;">
      <div class="table-wrap">
        <table class="data-table cand-table" id="candTable">
          <thead>
            <tr>
              <th class="num">#</th>
              <th class="sortable" data-sort="display_name">팀</th>
              <th>주목 이유</th>
              <th class="nowrap sortable" data-sort="next_gig_sort">다음 공연</th>
              <th class="num sortable" data-sort="score">점수</th>
              <th class="nowrap">듣기</th>
              <th class="nowrap">관심</th>
            </tr>
          </thead>
          <tbody id="candTbody"></tbody>
        </table>
      </div>
      <div class="more-row" id="candMoreRow" hidden></div>
    </div>
    <p class="photo-credit" id="candPhotoCredit" hidden>아티스트 사진 출처: Spotify</p>
  `;

  function paintTable() {
    const q = (root.querySelector('#candFilterInput')?.value || '').trim().toLowerCase();
    let list = rows;
    if (moveFilter === 'new') list = list.filter(r => r.is_new);
    else if (moveFilter === 'riser') list = list.filter(r => Boolean(r.riser));
    else if (moveFilter === 'upcoming') list = list.filter(r => Boolean(r.next_gig));

    if (q) {
      list = list.filter(r =>
        String(r.display_name || '').toLowerCase().includes(q) ||
        String(r.team_key || '').toLowerCase().includes(q) ||
        String(r.primary_genre || '').toLowerCase().includes(q) ||
        String(r.why_line || '').toLowerCase().includes(q) ||
        String(r.next_gig_text || '').toLowerCase().includes(q)
      );
    }

    list = sortRows(list, appState.candSort.col, appState.candSort.dir);

    root.querySelectorAll('[data-move-chip]').forEach(btn => {
      const active = btn.dataset.moveChip === moveFilter;
      btn.classList.toggle('active', active);
      btn.setAttribute('aria-pressed', active ? 'true' : 'false');
    });

    // Register current filtered & sorted rows with unified Export menu
    setExportContext({
      csvLabel: `후보 목록 CSV 내려받기 (${fmtInt(list.length)}팀)`,
      csvFilename: `crate_digger_candidates_${appState.dataEnd || 'export'}.csv`,
      csvHeaders: ['rank', 'team_key', 'display_name', 'genre', 'score', 'why', 'next_gig', 'n_branch', 'gigs_1y', 'venues', 'last_seen'],
      csvRows: list.map((r, idx) => [
        idx + 1,
        r.team_key,
        r.display_name || r.team_key,
        r.primary_genre || '',
        r.score ?? '',
        r.why_line || '',
        r.next_gig_text || '',
        r.n_branch ?? 0,
        r.gigs_1y ?? 0,
        r.venues ?? 0,
        r.last_seen || '',
      ]),
    });

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
      tbody.innerHTML = `<tr><td colspan="7" style="padding:0;border:none;">${renderEmptyState({
        title: '조건에 맞는 후보 팀이 없습니다',
        message: '검색어 또는 변동 필터를 해제하거나 조건을 초기화해 보세요.',
        showReset: true,
      })}</td></tr>`;
      root.querySelector('#candMoreRow').hidden = true;
      root.querySelector('#candPhotoCredit').hidden = true;
      return;
    }

    const hasAnyImg = shown.some(r => appState.imagesByTeam.has(r.team_key));
    root.querySelector('#candPhotoCredit').hidden = !hasAnyImg;

    tbody.innerHTML = shown.map((r, idx) => {
      const subParts = [];
      if (r.primary_genre) subParts.push(escapeHtml(r.primary_genre));
      if (r.had_outcome) subParts.push('기정답');

      let moveBadge = '';
      if (r.is_new) {
        moveBadge = '<span class="delta-badge is-new">신규</span>';
      } else if (r.riser) {
        let txt = '상승';
        if (r.riser.rank_gain > 0) txt = `+${r.riser.rank_gain}`;
        else if (r.riser.score_gain >= 0.05) txt = `+${fmtNum(r.riser.score_gain, 1)}`;
        moveBadge = `<span class="delta-badge is-up" title="지난주 대비 상승">${escapeHtml(txt)}</span>`;
      }

      const nextGigCell = r.next_gig_text
        ? `<span class="next-gig-chip">${escapeHtml(r.next_gig_text)}${r.next_gig.count > 1 ? ` 외 ${r.next_gig.count - 1}` : ''}</span>`
        : '<span class="muted">—</span>';

      return `
        <tr class="clickable" tabindex="0" data-team-key="${escapeHtml(r.team_key)}">
          <td class="num muted">${idx + 1}</td>
          <td>
            <div class="row-team-cell">
              ${avatarHtml(r.team_key, r.display_name, 28, { shape: 'circle', genre: r.primary_genre })}
              <div class="row-team-text">
                <div class="row-team-name">
                  <span class="cand-mobile-rank">#${idx + 1}</span>
                  <strong>${escapeHtml(r.display_name || r.team_key)}</strong>
                  ${moveBadge}
                </div>
                ${subParts.length ? `<div class="muted small">${subParts.join(' · ')}</div>` : ''}
                <div class="cand-mobile-meta">
                  <span class="cand-mobile-why">${escapeHtml(r.why_line)}</span>
                  ${r.next_gig_text ? `<span class="next-gig-chip">${escapeHtml(r.next_gig_text)}</span>` : ''}
                </div>
              </div>
            </div>
          </td>
          <td class="why-cell">${escapeHtml(r.why_line)}</td>
          <td class="nowrap next-gig-col">${nextGigCell}</td>
          <td class="num"><strong>${fmtNum(r.score, 2)}</strong></td>
          <td class="nowrap cand-listen-col">${renderRowListenControl(r)}</td>
          <td class="nowrap">${watchButtonHtml(r.team_key, r.display_name || r.team_key, true, true)}</td>
        </tr>
      `;
    }).join('');

    wireAvatarFallbacks(tbody);
    wireSpotifyButtons(tbody);

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

  root.querySelectorAll('[data-move-chip]').forEach(btn => {
    btn.addEventListener('click', () => {
      const target = btn.dataset.moveChip;
      moveFilter = (moveFilter === target) ? '' : target;
      visibleCount = 20;
      paintTable();
    });
  });

  const triggerRecompute = () => {
    syncHash(true);
    window.dispatchEvent(new CustomEvent('app:recompute'));
  };

  root.querySelector('#candGenreSel').addEventListener('change', (e) => {
    appState.cfg.genre = e.target.value || '';
    triggerRecompute();
  });

  root.querySelector('#candPeriodSel').addEventListener('change', (e) => {
    appState.cfg.period_days = Number(e.target.value) || 0;
    triggerRecompute();
  });

  root.querySelectorAll('[data-branch-chip]').forEach(btn => {
    btn.addEventListener('click', () => {
      const b = btn.dataset.branchChip;
      const cur = new Set(appState.cfg.branches);
      if (cur.has(b)) {
        if (cur.size <= 1) return;
        cur.delete(b);
      } else {
        cur.add(b);
      }
      appState.cfg.branches = ALL_BRANCHES.filter(x => cur.has(x));
      triggerRecompute();
    });
  });

  root.querySelector('#candNewcomerInp').addEventListener('change', (e) => {
    appState.cfg.newcomer_years = Math.max(1, Math.min(15, Math.round(Number(e.target.value) || 3)));
    triggerRecompute();
  });

  root.querySelector('#candExcludeFamous').addEventListener('change', (e) => {
    appState.cfg.exclude_famous = e.target.checked;
    triggerRecompute();
  });

  root.querySelector('#candOnlyNoOutcome').addEventListener('change', (e) => {
    appState.cfg.only_no_outcome = e.target.checked;
    triggerRecompute();
  });

  root.querySelector('#candLimitSel').addEventListener('change', (e) => {
    appState.cfg.limit = Number(e.target.value) || 100;
    triggerRecompute();
  });

  root.querySelectorAll('th.sortable').forEach(th => {
    th.setAttribute('tabindex', '0');
    const onSort = () => {
      const col = th.dataset.sort;
      if (appState.candSort.col === col) {
        appState.candSort.dir = appState.candSort.dir === 'desc' ? 'asc' : 'desc';
      } else {
        appState.candSort.col = col;
        appState.candSort.dir = (col === 'display_name' || col === 'next_gig_sort') ? 'asc' : 'desc';
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
    if (e.target.closest('button') || e.target.closest('a')) return;
    const tr = e.target.closest('tr.clickable');
    if (tr && tr.dataset.teamKey) {
      navigateTo('team', tr.dataset.teamKey);
    }
  });
  tbodyEl.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    if (e.target.closest('button') || e.target.closest('a')) return;
    const tr = e.target.closest('tr.clickable');
    if (tr && tr.dataset.teamKey) {
      e.preventDefault();
      navigateTo('team', tr.dataset.teamKey);
    }
  });
}
