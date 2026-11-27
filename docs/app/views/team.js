import { appState } from '../state.js';
import { getTeamExternalLinks, queryTeamDetail } from '../db.js';
import {
  escapeHtml, fmtInt, fmtNum, formatSignalDate,
  PROFILE_LABELS, renderActionBanner, SOURCE_LABELS,
  summarizeWhyTeam, watchButtonHtml,
} from '../ui.js';

export async function renderTeamView(root, teamKey) {
  if (!teamKey) {
    root.innerHTML = renderActionBanner({
      title: '팀 상세',
      lead: '선택된 팀이 없습니다.',
      todo: '위쪽 팀 검색 창에서 팀 이름을 입력하거나 후보 탐색에서 팀을 선택하세요.',
      buttonsHtml: '<a class="btn" href="#/candidates">후보 탐색으로</a>',
    });
    return;
  }

  const data = await queryTeamDetail(teamKey);
  const { profile, scored, timeline, outcomes, precedents } = data;
  if (!profile && !scored && !timeline.length) {
    root.innerHTML = renderActionBanner({
      title: `팀을 찾을 수 없음: ${teamKey}`,
      lead: '현재 데이터에 해당 팀 키가 없습니다.',
      todo: '위쪽 팀 검색 창에서 정확한 팀 이름을 선택해 주세요.',
      buttonsHtml: '<a class="btn" href="#/candidates">후보 탐색으로</a>',
    });
    return;
  }

  const displayName = scored?.display_name || profile?.display_name || teamKey;
  const links = getTeamExternalLinks(teamKey, displayName);
  const whyLines = summarizeWhyTeam(data);

  const scoreStr = scored ? `${fmtNum(scored.score, 2)}점` : '점수 산정 대상 밖';
  const bannerHtml = renderActionBanner({
    title: displayName,
    lead: `현재 설정 점수 <strong>${scoreStr}</strong> · 신호 ${fmtInt(timeline.length)}건 · 과거 유사 선례 ${fmtInt(precedents.length)}팀`,
    todo: '아래 3줄 요약과 타임라인·출처를 확인하고, 계속 추적할 팀이면 관심 목록에 담아 두세요.',
    buttonsHtml: `
      ${watchButtonHtml(teamKey, displayName, false)}
      <a class="btn" href="#/candidates">후보 목록으로</a>
    `,
  });

  const scoreBoxHtml = scored ? `
    <dl class="kv-list">
      <dt>합계 점수</dt><dd><strong>${fmtNum(scored.score, 2)}점</strong></dd>
      <dt>갈래 수 (${fmtInt(scored.n_branch)}개)</dt><dd>+${fmtNum(scored.pts_branch, 2)}</dd>
      <dt>선정 최고 단계 (${fmtInt(scored.best_stage)})</dt><dd>+${fmtNum(scored.pts_stage, 2)}</dd>
      <dt>선정 팀과 같은 무대 (${scored.peer_selected ? '있음' : '없음'})</dt><dd>+${fmtNum(scored.pts_peer, 2)}</dd>
      <dt>DMZ 출연 (${scored.dmz ? '있음' : '없음'})</dt><dd>+${fmtNum(scored.pts_dmz, 2)}</dd>
      <dt>최근 1년 공연 (${fmtInt(scored.gigs_1y)}일)</dt><dd>+${fmtNum(scored.pts_gigs, 2)}</dd>
      <dt>큐레이션 매체 (${fmtInt(scored.outlets)}곳)</dt><dd>+${fmtNum(scored.pts_outlets, 2)}</dd>
    </dl>
  ` : '<p class="muted small" style="margin:0;">현재 신호 기간·갈래 설정 안에서 산정된 점수가 없습니다.</p>';

  const profStatus = PROFILE_LABELS[profile?.profile_status] || profile?.profile_status || '수집 전';
  const profileBoxHtml = `
    <dl class="kv-list">
      <dt>우리 데이터 첫 등장</dt><dd class="mono">${escapeHtml(profile?.first_seen || '-')}</dd>
      <dt>장르</dt><dd>${escapeHtml(profile?.primary_genre || '수집 전')}</dd>
      <dt>첫 발매일</dt><dd class="mono">${escapeHtml(profile?.first_release || '수집 전')}</dd>
      <dt>멜론 팬 수</dt><dd>${profile?.fan_count !== null && profile?.fan_count !== undefined && profile?.fan_count !== '' ? `${fmtInt(profile.fan_count)}명` : '수집 전'}</dd>
      <dt>앨범 수</dt><dd>${profile?.album_count !== null && profile?.album_count !== undefined && profile?.album_count !== '' ? `${fmtInt(profile.album_count)}장` : '수집 전'}</dd>
      <dt>프로필 상태</dt><dd>${escapeHtml(profStatus)}</dd>
      <dt>팀 키</dt><dd class="mono muted">${escapeHtml(teamKey)}</dd>
    </dl>
  `;

  const precHtml = precedents.length
    ? `
      <div class="table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>과거 수상 팀</th>
              <th>첫 정답</th>
              <th class="nowrap">발표일</th>
              <th>겹친 경로</th>
              <th class="num nowrap">첫 신호→정답</th>
            </tr>
          </thead>
          <tbody>
            ${precedents.map(p => `
              <tr>
                <td><a href="#/team/${encodeURIComponent(p.past_team)}"><strong>${escapeHtml(p.display_name || p.past_team)}</strong></a></td>
                <td>${escapeHtml(p.outcome_label || '-')}</td>
                <td class="nowrap mono muted">${escapeHtml(p.outcome_date || '-')}</td>
                <td>${escapeHtml(p.shared_list || '-')} <span class="muted small">(${fmtInt(p.shared_count)}개)</span></td>
                <td class="num nowrap">${p.months_signal_to_outcome !== null && p.months_signal_to_outcome !== undefined ? `${fmtInt(p.months_signal_to_outcome)}개월` : '-'}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
      <p class="muted small" style="margin:8px 0 0 0;">주의: 선례는 정답 전에 비슷한 선정·공연장·매체를 거쳤다는 참고 정보일 뿐, 수상을 예측하지 않습니다.</p>
    `
    : '<p class="muted small" style="margin:0;">겹치는 선정 프로그램·공연장·매체를 정답 전에 밟은 과거 수상 팀이 아직 없습니다.</p>';

  // Combine outcomes + signals into one chronological timeline
  const merged = [];
  for (const o of outcomes) {
    const tierKo = o.tier === 'final' ? '최종' : '중간';
    merged.push({
      sortDate: o.announced_date || '',
      dateDisp: o.announced_date || '-',
      branch: '정답',
      isOutcome: true,
      text: `${o.program_label || o.program} [${tierKo}]${o.counted ? '' : ' (집계 제외)'}`,
    });
  }
  for (const s of timeline) {
    const name = s.program_label || SOURCE_LABELS[s.program] || SOURCE_LABELS[s.source] || s.source || '';
    const detail = s.venue ? `${name} — ${s.venue}` : name;
    merged.push({
      sortDate: s.signal_date || '',
      dateDisp: formatSignalDate(s.signal_date, s.branch),
      branch: s.branch || '',
      isOutcome: false,
      text: detail,
    });
  }
  merged.sort((a, b) => (b.sortDate > a.sortDate ? 1 : b.sortDate < a.sortDate ? -1 : 0));

  const timelineHtml = merged.length
    ? `<ul class="timeline-list">${merged.map(m => `
        <li>
          <span class="timeline-date">${escapeHtml(m.dateDisp)}</span>
          <span class="timeline-branch ${m.isOutcome ? 'timeline-outcome' : ''}">${escapeHtml(m.branch)}</span>
          <span>${escapeHtml(m.text)}</span>
        </li>
      `).join('')}</ul>`
    : '<p class="muted small" style="margin:0;">기록된 신호가 없습니다.</p>';

  const linksHtml = links.length
    ? `<ul class="mini-list">${links.map(l => `
        <li>
          <div class="mini-list-main">
            <a href="${escapeHtml(l.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(l.title)}</a>
            <div class="mini-list-sub">${escapeHtml(l.source)}${l.date ? ` · ${escapeHtml(l.date)}` : ''}</div>
          </div>
        </li>
      `).join('')}</ul>`
    : '<p class="muted small" style="margin:0;">연결된 외부 기사·공연 링크가 아직 없습니다.</p>';

  root.innerHTML = `
    ${bannerHtml}

    <section class="block">
      <div class="block-head">
        <h2>왜 후보인가 (자동 요약)</h2>
        <span class="block-meta">기준일 ${escapeHtml(appState.cfg.as_of)}</span>
      </div>
      <ol class="why-list">
        ${whyLines.map(line => `<li>${escapeHtml(line)}</li>`).join('')}
      </ol>
    </section>

    <div class="grid-2">
      <section class="block" style="margin-bottom:0;">
        <div class="block-head"><h3>점수 구성</h3></div>
        ${scoreBoxHtml}
      </section>
      <section class="block" style="margin-bottom:0;">
        <div class="block-head"><h3>팀 프로필</h3></div>
        ${profileBoxHtml}
      </section>
    </div>

    <section class="block">
      <div class="block-head">
        <h2>비슷한 길을 밟은 과거 수상 팀</h2>
        <span class="block-meta">최대 5팀 (희귀 경로 가중)</span>
      </div>
      ${precHtml}
    </section>

    <div class="grid-2">
      <section class="block" style="margin-bottom:0;">
        <div class="block-head">
          <h3>신호 · 정답 타임라인</h3>
          <span class="block-meta">${fmtInt(merged.length)}건</span>
        </div>
        ${timelineHtml}
      </section>
      <section class="block" style="margin-bottom:0;">
        <div class="block-head">
          <h3>출처 링크</h3>
          <span class="block-meta">${fmtInt(links.length)}건</span>
        </div>
        ${linksHtml}
      </section>
    </div>
  `;
}
