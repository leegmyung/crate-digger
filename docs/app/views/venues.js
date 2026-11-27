import { appState, registerChart } from '../state.js';
import { runRawSql, sqlStringLiteral } from '../db.js';
import { cssVar, escapeHtml, fmtInt, renderActionBanner } from '../ui.js';

export async function renderVenuesView(root) {
  const dj = appState.dashboardJson;
  const venues = dj?.sections?.top_venues || [];
  const topV = venues[0];

  const bannerHtml = renderActionBanner({
    title: '씬 지도 (공연장)',
    lead: topV
      ? `가장 많은 공연이 열린 곳은 <strong>${escapeHtml(topV.venue)}</strong>(${fmtInt(topV.gigs)}건, 출연 ${fmtInt(topV.teams)}팀, 후보 ${fmtInt(topV.candidate_teams)}팀)입니다.`
      : '공연장 요약 데이터를 불러오지 못했습니다.',
    todo: '아래 표에서 공연장 줄을 누르면 그 무대에 최근 오른 팀 목록을 바로 확인하고 팀 상세로 이동할 수 있습니다.',
  });

  if (!venues.length) {
    root.innerHTML = `${bannerHtml}<div class="notice">data/dashboard.json의 공연장 요약(top_venues)이 비어 있습니다.</div>`;
    return;
  }

  root.innerHTML = `
    ${bannerHtml}

    <section class="block">
      <div class="block-head">
        <h2>상위 공연장별 공연 수 · 후보 팀 출연</h2>
        <span class="block-meta">상위 ${fmtInt(venues.length)}개 공연장</span>
      </div>
      <div class="chart-box chart-box-tall"><canvas id="venuesChart"></canvas></div>
      <div class="table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>공연장</th>
              <th class="num">공연 건수</th>
              <th class="num">출연 팀</th>
              <th class="num">후보 팀</th>
              <th class="num">후보 비중</th>
            </tr>
          </thead>
          <tbody id="venuesTbody">
            ${venues.map(v => {
              const ratio = v.teams ? ((100 * v.candidate_teams) / v.teams).toFixed(1) : '0.0';
              return `
                <tr class="clickable" tabindex="0" data-venue="${escapeHtml(v.venue)}">
                  <td><strong>${escapeHtml(v.venue)}</strong></td>
                  <td class="num">${fmtInt(v.gigs)}</td>
                  <td class="num">${fmtInt(v.teams)}</td>
                  <td class="num"><strong>${fmtInt(v.candidate_teams)}팀</strong></td>
                  <td class="num muted">${ratio}%</td>
                </tr>
              `;
            }).join('')}
          </tbody>
        </table>
      </div>
    </section>

    <section class="block" id="venueDetailBox" hidden>
      <div class="block-head">
        <h3 id="venueDetailTitle">공연장 최근 라인업</h3>
        <span class="block-meta" id="venueDetailMeta"></span>
      </div>
      <div class="table-wrap" id="venueDetailBody"></div>
    </section>
  `;

  if (window.Chart) {
    const cv = root.querySelector('#venuesChart');
    const inkMuted = cssVar('--ink-muted');
    const lineColor = cssVar('--line');

    registerChart(new window.Chart(cv.getContext('2d'), {
      type: 'bar',
      data: {
        labels: venues.map(v => v.venue),
        datasets: [
          { label: '출연 팀', data: venues.map(v => Number(v.teams) || 0), backgroundColor: cssVar('--bar-gigs'), borderRadius: 2 },
          { label: '후보 팀', data: venues.map(v => Number(v.candidate_teams) || 0), backgroundColor: cssVar('--bar-score'), borderRadius: 2 },
        ],
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        plugins: {
          legend: { position: 'top', align: 'start', labels: { color: inkMuted, boxWidth: 12, font: { size: 12 } } },
        },
        scales: {
          x: { beginAtZero: true, ticks: { color: inkMuted }, grid: { color: lineColor } },
          y: { ticks: { color: inkMuted, font: { size: 11.5 } }, grid: { display: false } },
        },
      },
    }));
  }

  const venuesTbody = root.querySelector('#venuesTbody');
  const openVenueRow = async (tr) => {
    if (!tr) return;
    const venue = tr.dataset.venue;
    const box = root.querySelector('#venueDetailBox');
    const title = root.querySelector('#venueDetailTitle');
    const meta = root.querySelector('#venueDetailMeta');
    const body = root.querySelector('#venueDetailBody');

    box.hidden = false;
    title.textContent = `${venue} — 최근 출연 팀`;
    meta.textContent = '조회 중...';
    body.innerHTML = '';

    try {
      const { rows } = await runRawSql(`
        SELECT s.signal_date, s.team_key, COALESCE(t.display_name, s.team_key) AS display_name,
               COALESCE(t.primary_genre, '') AS primary_genre, s.source
        FROM signals s
        LEFT JOIN teams t USING (team_key)
        WHERE s.branch = '공연' AND s.venue = ${sqlStringLiteral(venue)}
        ORDER BY s.signal_date DESC
        LIMIT 30
      `);
      meta.textContent = `최근 ${fmtInt(rows.length)}건`;
      body.innerHTML = rows.length
        ? `<table class="data-table">
            <thead><tr><th class="nowrap">날짜</th><th>팀</th><th>장르</th><th>출처</th></tr></thead>
            <tbody>${rows.map(r => `
              <tr>
                <td class="nowrap mono muted">${escapeHtml(r.signal_date || '-')}</td>
                <td><a href="#/team/${encodeURIComponent(r.team_key)}"><strong>${escapeHtml(r.display_name)}</strong></a></td>
                <td class="muted">${escapeHtml(r.primary_genre || '-')}</td>
                <td class="muted">${escapeHtml(r.source || '-')}</td>
              </tr>
            `).join('')}</tbody>
          </table>`
        : '<p class="muted small" style="margin:0;">이 공연장 이름으로 직접 일치하는 신호 행이 없습니다.</p>';
      box.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    } catch (err) {
      meta.textContent = '오류';
      body.innerHTML = `<p class="muted small">${escapeHtml(err.message)}</p>`;
    }
  };

  venuesTbody.addEventListener('click', (e) => {
    openVenueRow(e.target.closest('tr.clickable'));
  });
  venuesTbody.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    const tr = e.target.closest('tr.clickable');
    if (tr) {
      e.preventDefault();
      openVenueRow(tr);
    }
  });
}
