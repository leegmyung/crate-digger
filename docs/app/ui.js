import { appState, isWatched } from './state.js';

export const SOURCE_LABELS = {
  indistreet: '인디스트릿',
  sangsangmadang_live: '상상마당 라이브',
  sangsangmadang: '상상마당 라이브',
  band_discovery: '상상마당 밴드 디스커버리',
  burock_rookies: '부산록페 루키즈',
  busanrock: '부산록페 루키즈',
  dmz_lineup: 'DMZ 피스트레인',
  gb_creation: '경북 음악창작소',
  muse_sejong: '세종 뮤즈세종',
  yoojaeha_finalist: '유재하 본선',
  rhythmer: '리드머',
  poclanos: '포크라노스',
  izm: '이즘(IZM)',
  overtone: '오버톤',
  k_indie_chart: 'K-인디차트',
  melon_indie: '멜론 인디',
  visla: 'VISLA',
  instagram: '인스타그램',
};

export const PROFILE_LABELS = {
  newcomer: '신인 확인',
  established: '기존 활동',
  famous: '유명 팀',
  unknown: '수집 전',
};

export function escapeHtml(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

export function fmtInt(n) {
  if (n === null || n === undefined || Number.isNaN(Number(n))) return '-';
  return Number(n).toLocaleString('ko-KR');
}

export function fmtNum(n, digits = 1) {
  if (n === null || n === undefined || Number.isNaN(Number(n))) return '-';
  return Number(n).toFixed(digits);
}

export function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

export function formatSignalDate(dateStr, branch) {
  if (!dateStr) return '-';
  if (branch === '선정·지원' && dateStr.endsWith('-12-31')) {
    return `${dateStr.slice(0, 4)} 선정`;
  }
  const asOf = appState.cfg.as_of || appState.dataEnd || '2026-11-27';
  if (dateStr > asOf) return `${dateStr} (예정)`;
  return dateStr;
}

export function clampDateDisplay(dateStr) {
  if (!dateStr) return '-';
  const asOf = appState.cfg.as_of || appState.dataEnd || '2026-11-27';
  if (dateStr.endsWith('-12-31') && dateStr > asOf) return `${dateStr.slice(0, 4)} 선정`;
  return dateStr > asOf ? asOf : dateStr;
}

export function renderActionBanner({ title, lead, todo, buttonsHtml = '' }) {
  return `
    <div class="action-banner">
      <div>
        <h1 class="action-banner-title">${escapeHtml(title)}</h1>
        <p class="action-banner-lead">${lead}</p>
        ${todo ? `<p class="action-banner-todo">할 일: ${todo}</p>` : ''}
      </div>
      ${buttonsHtml ? `<div class="action-banner-btns">${buttonsHtml}</div>` : ''}
    </div>
  `;
}

export function scorePartsLine(r) {
  const parts = [];
  if (Number(r.pts_branch) > 0) parts.push(`갈래 ${r.n_branch}개(+${fmtNum(r.pts_branch, 1)})`);
  if (Number(r.pts_stage) > 0) parts.push(`선정 단계 ${r.best_stage}(+${fmtNum(r.pts_stage, 1)})`);
  if (Number(r.pts_venues) > 0) parts.push(`공연장 ${r.venues}곳(+${fmtNum(r.pts_venues, 1)})`);
  if (Number(r.pts_recent) > 0) parts.push(`최근 6개월 ${r.recent180}건(+${fmtNum(r.pts_recent, 1)})`);
  if (Number(r.pts_winner) > 0) parts.push(`수상 팀과 같은 무대(+${fmtNum(r.pts_winner, 1)})`);
  if (Number(r.pts_outlets) > 0) parts.push(`매체 ${r.outlets}곳(+${fmtNum(r.pts_outlets, 1)})`);
  if (Number(r.pts_peer) > 0) parts.push(`선정 팀과 같은 무대(+${fmtNum(r.pts_peer, 1)})`);
  if (Number(r.pts_dmz) > 0) parts.push(`DMZ(+${fmtNum(r.pts_dmz, 1)})`);
  if (Number(r.pts_gigs) > 0) parts.push(`1년 공연 ${r.gigs_1y}일(+${fmtNum(r.pts_gigs, 2)})`);
  return parts.length ? parts.join(' · ') : '가중치 0 또는 신호 없음';
}

export function plainWhyLine(r) {
  const parts = [];
  if (Number(r.venues) >= 2 && Number(r.pts_venues) > 0) parts.push(`공연장 ${r.venues}곳`);
  if (Number(r.best_stage) >= 1 && Number(r.pts_stage) > 0) parts.push(`선정 ${r.best_stage}단계`);
  if (Number(r.peer_winner) > 0 && Number(r.pts_winner) > 0) parts.push('수상 팀과 같은 무대');
  if (Number(r.recent180) >= 2 && Number(r.pts_recent) > 0) parts.push(`최근 6개월 ${r.recent180}건`);
  if (Number(r.outlets) >= 1 && Number(r.pts_outlets) > 0) parts.push(`매체 ${r.outlets}곳 주목`);
  if (Number(r.n_branch) >= 2 && parts.length < 3) parts.push(`${r.n_branch}개 갈래 동시 활동`);
  if (!parts.length) return scorePartsLine(r);
  return parts.slice(0, 3).join(' · ');
}

export function renderScoreBar(r, maxScore) {
  const denom = Math.max(1, maxScore);
  const segs = [
    { key: '갈래', v: Number(r.pts_branch) || 0, color: 'var(--seg-branch)' },
    { key: '선정 단계', v: Number(r.pts_stage) || 0, color: 'var(--seg-stage)' },
    { key: '공연장 수', v: Number(r.pts_venues) || 0, color: 'var(--seg-venues)' },
    { key: '최근 6개월 활동', v: Number(r.pts_recent) || 0, color: 'var(--seg-recent)' },
    { key: '수상 팀과 같은 무대', v: Number(r.pts_winner) || 0, color: 'var(--seg-winner)' },
    { key: '큐레이션', v: Number(r.pts_outlets) || 0, color: 'var(--seg-outlets)' },
    { key: '선정 팀과 같은 무대', v: Number(r.pts_peer) || 0, color: 'var(--seg-peer)' },
    { key: 'DMZ', v: Number(r.pts_dmz) || 0, color: 'var(--seg-dmz)' },
    { key: '1년 공연', v: Number(r.pts_gigs) || 0, color: 'var(--seg-gigs)' },
  ];
  const html = segs
    .filter(s => s.v > 0)
    .map(s => {
      const w = Math.max(2, (s.v / denom) * 100);
      return `<span class="score-seg" style="width:${w.toFixed(1)}%;background:${s.color}"></span>`;
    })
    .join('');
  const title = segs.filter(s => s.v > 0).map(s => `${s.key} +${s.v.toFixed(2)}`).join(' / ');
  return `<div class="score-bar-track" title="${escapeHtml(title)}">${html}</div>`;
}

export function josa(word, consonantForm, vowelForm) {
  const s = String(word || '').trim().replace(/[)\]}>"'`.,!?]+$/g, '');
  if (!s) return `${word}${vowelForm}`;
  const last = s[s.length - 1];
  const code = last.charCodeAt(0);
  if (code >= 0xac00 && code <= 0xd7a3) {
    return `${word}${(code - 0xac00) % 28 !== 0 ? consonantForm : vowelForm}`;
  }
  if (/[013678]/.test(last)) return `${word}${consonantForm}`;
  if (/[2459]/.test(last)) return `${word}${vowelForm}`;
  if (/[lmnrLMNR]/.test(last)) return `${word}${consonantForm}`;
  return `${word}${vowelForm}`;
}

const SPOTIFY_ARTIST = /^https:\/\/open\.spotify\.com\/artist\/([A-Za-z0-9]{22})/;

/** 팀의 스포티파이 아티스트 id (links.csv), 없으면 null. */
export function spotifyIdOf(teamKey) {
  const url = appState.linksByTeam.get(teamKey)?.get('spotify') || '';
  const m = url.match(SPOTIFY_ARTIST);
  return m ? m[1] : null;
}

export function spotifyUrlOf(teamKey) {
  const id = spotifyIdOf(teamKey);
  return id ? `https://open.spotify.com/artist/${id}` : null;
}

export function avatarSourceOf(teamKey) {
  return appState.imageMetaByTeam.get(teamKey)?.source || null;
}

/**
 * 유튜브 연결 우선순위 (사용자 결정: 스포티파이·유튜브 두 플랫폼만):
 * 1) 공식 채널 (links.csv) → 2) 최근 무대 영상 (videos.csv) → 3) null
 */
export function youtubeQuickInfo(teamKey) {
  const yt = appState.linksByTeam.get(teamKey)?.get('youtube');
  if (yt && yt.startsWith('https://www.youtube.com/')) {
    return { kind: 'channel', label: '유튜브 채널', url: yt };
  }
  const vids = appState.videosByTeam.get(teamKey) || [];
  if (vids.length) {
    const sorted = [...vids].sort((a, b) => String(b.published_at || '').localeCompare(String(a.published_at || '')));
    const v = sorted[0];
    if (v && /^[A-Za-z0-9_-]{11}$/.test(v.video_id)) {
      return {
        kind: 'video',
        label: '무대 영상',
        videoId: v.video_id,
        url: `https://www.youtube.com/watch?v=${v.video_id}`,
        count: vids.length,
      };
    }
  }
  return null;
}

function genreAvatarTone(genre) {
  const g = String(genre || '').toLowerCase();
  if (/록|밴드|메탈|펑크|rock|punk|metal/.test(g)) return 'av-rock';
  if (/팝|r&b|소울|발라드|pop|soul|rnb/.test(g)) return 'av-pop';
  if (/포크|어쿠스틱|인디|folk|acoustic/.test(g)) return 'av-folk';
  if (/힙합|랩|일렉|재즈|hip|rap|elec|jazz/.test(g)) return 'av-hiphop';
  return 'av-default';
}

/** 팀 사진: 스포티파이 → 유튜브 채널 썸네일 → 이름 첫 글자(+장르색 모노그램). size = px. */
export function avatarHtml(teamKey, displayName, size = 40, opts = {}) {
  const name = displayName || teamKey || '';
  const url = appState.imagesByTeam.get(teamKey);
  const shape = opts.shape === 'rounded' ? 'avatar-rounded' : 'avatar-circle';
  const tone = genreAvatarTone(opts.genre);
  const initial = escapeHtml(Array.from(name.trim())[0] || '?');
  const fontSize = Math.max(11, Math.round(size * 0.42));
  if (url) {
    return `<img class="avatar ${shape}" src="${escapeHtml(url)}" alt="${escapeHtml(name)}" width="${size}" height="${size}" style="width:${size}px;height:${size}px" loading="lazy" decoding="async" data-av-initial="${initial}" data-av-tone="${tone}" data-av-shape="${shape}" data-av-size="${size}">`;
  }
  return `<span class="avatar avatar-initial ${shape} ${tone}" aria-hidden="true" style="width:${size}px;height:${size}px;font-size:${fontSize}px">${initial}</span>`;
}

/** 이미지 로드 실패 시 깨짐 아이콘 대신 첫 글자 모노그램으로 즉시 치환한다. */
export function wireAvatarFallbacks(root) {
  if (!root) return;
  root.querySelectorAll('img.avatar[data-av-initial]').forEach(img => {
    const swapToInitial = () => {
      const size = Number(img.dataset.avSize) || 40;
      const span = document.createElement('span');
      span.className = `avatar avatar-initial ${img.dataset.avShape || 'avatar-circle'} ${img.dataset.avTone || 'av-default'}`;
      span.setAttribute('aria-hidden', 'true');
      span.style.width = `${size}px`;
      span.style.height = `${size}px`;
      span.style.fontSize = `${Math.max(11, Math.round(size * 0.42))}px`;
      span.textContent = img.dataset.avInitial || '?';
      img.replaceWith(span);
    };
    if (img.complete && img.naturalWidth === 0) {
      swapToInitial();
    } else {
      img.addEventListener('error', swapToInitial, { once: true });
    }
  });
}

/** '▶ 듣기' 버튼: 누르면 같은 자리에 스포티파이 공식 임베드 플레이어를 만든다(wireSpotifyButtons로 연결). */
export function spotifyButtonHtml(teamKey, small = false, opts = {}) {
  const id = spotifyIdOf(teamKey);
  if (!id) return '';
  const iconOnly = Boolean(opts.iconOnly);
  const mode = opts.mode ? `data-spotify-mode="${escapeHtml(opts.mode)}"` : '';
  const nameAttr = opts.teamName ? `data-spotify-name="${escapeHtml(opts.teamName)}"` : '';
  const slotAttr = opts.slotId ? `data-spotify-slot="${escapeHtml(opts.slotId)}"` : '';
  const cls = iconOnly
    ? 'btn btn-icon spotify-play'
    : `btn ${small ? 'btn-sm' : 'btn-primary'} spotify-play`;
  const label = iconOnly ? '▶' : '▶ 듣기';
  return `<button type="button" class="${cls}" data-spotify-id="${id}" ${mode} ${nameAttr} ${slotAttr}
            aria-label="${escapeHtml(opts.teamName || teamKey)} 스포티파이 미리 듣기" title="스포티파이로 미리 듣기">${label}</button>`;
}

function buildSpotifyEmbedBox(id, teamName, onClose) {
  const box = document.createElement('div');
  box.className = 'spotify-embed-box';
  if (teamName) {
    const head = document.createElement('div');
    head.className = 'spotify-embed-head';
    head.innerHTML = `<span class="small"><strong>${escapeHtml(teamName)}</strong> · Spotify 미리 듣기</span>`;
    const closeBtn = document.createElement('button');
    closeBtn.type = 'button';
    closeBtn.className = 'btn btn-sm';
    closeBtn.textContent = '닫기';
    closeBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      onClose();
    });
    head.appendChild(closeBtn);
    box.appendChild(head);
  }
  const frame = document.createElement('iframe');
  frame.className = 'spotify-embed';
  frame.src = `https://open.spotify.com/embed/artist/${id}?utm_source=generator&theme=0`;
  frame.height = '152';
  frame.loading = 'lazy';
  frame.title = `${teamName || ''} 스포티파이 미리 듣기`.trim();
  frame.allow = 'autoplay; clipboard-write; encrypted-media; fullscreen; picture-in-picture';
  box.appendChild(frame);
  return box;
}

/**
 * root 안의 '▶ 듣기' 버튼마다 클릭 시 플레이어 생성 (단일 활성 슬롯 + 토글 닫기 지원).
 * - data-spotify-slot="<id>": 지정된 공유 슬롯에 표시 (5장 카드 그리드 높이 균형 유지)
 * - data-spotify-mode="table-row": 표 행 바로 아래 확장 tr에 표시
 * - 기본: 가장 가까운 [data-player-slot] 또는 target
 */
export function wireSpotifyButtons(root, defaultTarget = null) {
  if (!root) return;
  let activeBtn = null;
  let activeCleanup = null;

  const resetBtnLabel = (btn) => {
    if (!btn) return;
    btn.classList.remove('btn-active', 'is-playing');
    btn.textContent = btn.classList.contains('btn-icon') ? '▶' : '▶ 듣기';
  };

  const closeActive = () => {
    if (activeCleanup) {
      activeCleanup();
      activeCleanup = null;
    }
    if (activeBtn) {
      resetBtnLabel(activeBtn);
      activeBtn = null;
    }
  };

  root.querySelectorAll('.spotify-play[data-spotify-id]').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      const id = btn.dataset.spotifyId;
      if (!/^[A-Za-z0-9]{22}$/.test(id)) return;

      const wasSame = activeBtn === btn;
      closeActive();
      if (wasSame) return;

      const teamName = btn.dataset.spotifyName || '';
      const mode = btn.dataset.spotifyMode || '';
      const slotId = btn.dataset.spotifySlot || '';

      btn.classList.add('btn-active', 'is-playing');
      btn.textContent = btn.classList.contains('btn-icon') ? '■' : '■ 닫기';
      activeBtn = btn;

      if (mode === 'table-row') {
        const tr = btn.closest('tr');
        if (tr && tr.parentElement) {
          const colCount = tr.children.length || 8;
          const expTr = document.createElement('tr');
          expTr.className = 'player-expand-row';
          const td = document.createElement('td');
          td.colSpan = colCount;
          td.appendChild(buildSpotifyEmbedBox(id, teamName, closeActive));
          expTr.appendChild(td);
          tr.insertAdjacentElement('afterend', expTr);
          activeCleanup = () => expTr.remove();
          return;
        }
      }

      let host = slotId ? root.querySelector(`#${CSS.escape(slotId)}`) : defaultTarget;
      for (let el = btn.parentElement; !host && el && el !== root.parentElement; el = el.parentElement) {
        host = el.querySelector(':scope > [data-player-slot]');
      }
      host = host || btn.parentElement;
      host.innerHTML = '';
      const box = buildSpotifyEmbedBox(id, teamName, closeActive);
      host.appendChild(box);
      activeCleanup = () => { host.innerHTML = ''; };
    });
  });
}

export function watchButtonHtml(teamKey, displayName, small = true, reveal = false) {
  const on = isWatched(teamKey);
  const cls = `btn ${small ? 'btn-sm' : ''} ${on ? 'btn-active' : ''} ${reveal ? 'watch-reveal' : ''}`.trim();
  const label = on ? '관심 중' : '관심 추가';
  if (reveal) {
    return `<button type="button" class="${cls}" data-watch-key="${escapeHtml(teamKey)}" data-watch-name="${escapeHtml(displayName)}" aria-label="${escapeHtml(displayName)} ${label}"><span class="watch-lbl-full">${label}</span><span class="watch-lbl-short" aria-hidden="true">${on ? '★' : '☆'}</span></button>`;
  }
  return `<button type="button" class="${cls}" data-watch-key="${escapeHtml(teamKey)}" data-watch-name="${escapeHtml(displayName)}">${on ? '★ 관심 중' : '☆ 관심 추가'}</button>`;
}

export function buildWeeklySummaryText({
  dataEnd = appState.dataEnd,
  prevDate = '',
  latestDate = '',
  newEntrants = [],
  risers = [],
  signalStats = { total: 0, byBranch: {} },
  newVideos7d = 0,
  top5 = [],
  health = appState.dataHealth,
}) {
  const lines = [];
  lines.push(`[Crate Digger 주간 브리핑 · ${dataEnd || latestDate} 기준]`);
  const topRiser = risers[0];
  const riserNote = topRiser
    ? ` (최대 ${topRiser.display_name} #${topRiser.rank_prev}→#${topRiser.rank_now}${topRiser.score_gain > 0 ? `, +${fmtNum(topRiser.score_gain, 2)}점` : ''})`
    : '';
  const periodTxt = prevDate && latestDate ? `${prevDate}→${latestDate} ` : '';
  lines.push(`- ${periodTxt}변화: 새 후보 ${fmtInt(newEntrants.length)}팀 · 상승 ${fmtInt(risers.length)}팀${riserNote}`);
  const brParts = Object.entries(signalStats.byBranch || {})
    .filter(([, n]) => n > 0)
    .map(([b, n]) => `${b} ${fmtInt(n)}`);
  lines.push(`- 최근 7일 활동: 새 신호 ${fmtInt(signalStats.total)}건${brParts.length ? `(${brParts.join(' · ')})` : ''} · 새 무대 영상 ${fmtInt(newVideos7d)}개`);
  if (top5.length) {
    const t5 = top5.map((r, i) => `${i + 1}. ${r.display_name || r.team_key}(${fmtNum(r.score, 2)})`).join(' · ');
    lines.push(`- 이번 주 상위 5팀: ${t5}`);
  }
  lines.push(`- 수집 상태: ${health?.summaryLabel || '정상'}`);
  if (typeof window !== 'undefined' && window.location?.href) {
    lines.push(`- 링크: ${window.location.href}`);
  }
  return lines.join('\n');
}

export function summarizeWhyTeam({ scored, profile, timeline, precedents }) {
  const name = scored?.display_name || profile?.display_name || '';
  const lines = [];

  if (scored) {
    lines.push(
      `${josa(name, '은', '는')} 현재 설정 기준 ${fmtNum(scored.score, 2)}점입니다 (${scorePartsLine(scored)}).`
    );
  } else {
    lines.push(`${josa(name, '은', '는')} 현재 필터·신호 기간 기준 점수 산정 대상 밖이지만 기록된 신호 ${timeline.length}건이 있습니다.`);
  }

  if (timeline.length) {
    const first = profile?.first_seen || timeline[timeline.length - 1]?.signal_date || '-';
    const latest = timeline[0];
    const latestDate = formatSignalDate(latest.signal_date, latest.branch);
    const latestWhere = latest.program_label || latest.venue || SOURCE_LABELS[latest.source] || latest.source || '';
    lines.push(
      `우리 데이터 첫 등장은 ${first}이며, 총 ${timeline.length}건의 신호 중 가장 최근 기록은 ${latestDate} ${latest.branch}(${latestWhere})입니다.`
    );
  } else {
    lines.push('현재 기록된 세부 신호가 없습니다.');
  }

  if (precedents && precedents.length) {
    const top = precedents[0];
    const mTxt = top.months_signal_to_outcome !== null && top.months_signal_to_outcome !== undefined
      ? ` (첫 신호 후 약 ${top.months_signal_to_outcome}개월)`
      : '';
    lines.push(
      `비슷한 경로(${top.shared_list})를 밟은 과거 수상 팀으로 ${top.display_name}(${top.outcome_label}${mTxt}) 등 ${precedents.length}팀이 있습니다.`
    );
  } else {
    lines.push('아직 겹치는 선정·공연장·매체 경로를 가진 과거 수상 팀 선례는 충분하지 않습니다.');
  }

  return lines;
}

export function friendlySqlError(err) {
  const raw = String(err?.message || err || '알 수 없는 오류');
  if (raw.includes('Parser Error') || raw.includes('syntax error')) {
    return `SQL 문법 오류입니다. 쉼표·괄호·따옴표를 확인해 주세요. (${raw})`;
  }
  if (raw.includes('does not exist') || raw.includes('Catalog Error')) {
    return `표나 열 이름을 찾을 수 없습니다. 사용 가능한 표는 signals, teams, outcomes, programs, links, videos, images 입니다. (${raw})`;
  }
  if (raw.includes('Binder Error')) {
    return `열 이름이나 자료형이 맞지 않습니다. (${raw})`;
  }
  return raw;
}

export function renderEmptyState({
  title = '조건에 맞는 결과가 없습니다',
  message = '필터 조건을 줄여 보거나 초기화해 전체 목록을 확인해 보세요.',
  showReset = true,
} = {}) {
  return `
    <div class="empty-state" role="status">
      <p class="empty-state-title">${escapeHtml(title)}</p>
      <p class="empty-state-msg">${escapeHtml(message)}</p>
      ${showReset ? '<button type="button" class="btn btn-primary" data-action="reset-filters">필터 초기화</button>' : ''}
    </div>
  `;
}

export function renderViewSkeleton() {
  return `
    <div class="skeleton-wrap" aria-busy="true" aria-label="화면 불러오는 중">
      <div class="skel-banner">
        <div class="skel-line skel-w-30" style="height:22px;"></div>
        <div class="skel-line skel-w-70"></div>
        <div class="skel-line skel-w-50"></div>
      </div>
      <div class="skel-card">
        <div class="skel-line skel-w-40" style="height:18px;"></div>
        <div class="skel-line skel-w-90"></div>
        <div class="skel-line skel-w-80"></div>
        <div class="skel-line skel-w-90"></div>
        <div class="skel-line skel-w-70"></div>
      </div>
    </div>
  `;
}

// ---------- Shared Chart.js Plugins ----------

export const horizontalBaselinePlugin = {
  id: 'horizontalBaseline',
  afterDatasetsDraw(chart, _args, opts) {
    if (!opts || opts.value === null || opts.value === undefined) return;
    const { ctx, chartArea, scales } = chart;
    const y = scales.y.getPixelForValue(opts.value);
    if (y < chartArea.top || y > chartArea.bottom) return;
    ctx.save();
    ctx.strokeStyle = opts.color || '#111827';
    ctx.lineWidth = 1.5;
    ctx.setLineDash([5, 4]);
    ctx.beginPath();
    ctx.moveTo(chartArea.left, y);
    ctx.lineTo(chartArea.right, y);
    ctx.stroke();
    ctx.setLineDash([]);
    const lbl = opts.label || '';
    if (lbl) {
      ctx.font = '12px -apple-system, BlinkMacSystemFont, sans-serif';
      const padX = 5;
      const tw = ctx.measureText(lbl).width;
      const tx = chartArea.right - 4;
      const ty = Math.max(chartArea.top + 15, y - 6);
      ctx.fillStyle = opts.bgColor || '#ffffff';
      ctx.fillRect(tx - tw - padX, ty - 12, tw + padX * 2, 16);
      ctx.fillStyle = opts.color || '#111827';
      ctx.textAlign = 'right';
      ctx.fillText(lbl, tx, ty);
    }
    ctx.restore();
  },
};

export const signalWhiskerPlugin = {
  id: 'signalWhisker',
  afterDatasetsDraw(chart, _args, opts) {
    const { ctx, chartArea, scales } = chart;
    if (!opts) return;
    ctx.save();
    if (typeof opts.baseline === 'number') {
      const bx = scales.x.getPixelForValue(opts.baseline);
      if (bx >= chartArea.left && bx <= chartArea.right) {
        ctx.strokeStyle = opts.baselineColor || '#111827';
        ctx.lineWidth = 1.5;
        ctx.setLineDash([4, 4]);
        ctx.beginPath();
        ctx.moveTo(bx, chartArea.top);
        ctx.lineTo(bx, chartArea.bottom);
        ctx.stroke();
        ctx.setLineDash([]);
        const lbl = `기준선 ${opts.baseline.toFixed(1)}%`;
        ctx.font = '12px -apple-system, BlinkMacSystemFont, sans-serif';
        const tw = ctx.measureText(lbl).width;
        const tx = Math.min(chartArea.right - tw - 6, bx + 5);
        const ty = chartArea.top + 14;
        ctx.fillStyle = opts.bgColor || '#ffffff';
        ctx.fillRect(tx - 3, ty - 12, tw + 6, 15);
        ctx.fillStyle = opts.baselineColor || '#111827';
        ctx.textAlign = 'left';
        ctx.fillText(lbl, tx, ty);
      }
    }
    const meta = chart.getDatasetMeta(0);
    const rows = opts.rows || [];
    ctx.strokeStyle = opts.whiskerColor || '#525866';
    ctx.lineWidth = 1.5;
    for (let i = 0; i < rows.length; i++) {
      const el = meta.data[i];
      if (!el) continue;
      const r = rows[i];
      const xLow = scales.x.getPixelForValue(Number(r.ci_low) || 0);
      const xHigh = scales.x.getPixelForValue(Number(r.ci_high) || 0);
      const y = el.y;
      ctx.globalAlpha = Number(r.teams) < 10 ? 0.45 : 0.9;
      ctx.beginPath();
      ctx.moveTo(xLow, y);
      ctx.lineTo(xHigh, y);
      ctx.moveTo(xLow, y - 4);
      ctx.lineTo(xLow, y + 4);
      ctx.moveTo(xHigh, y - 4);
      ctx.lineTo(xHigh, y + 4);
      ctx.stroke();
    }
    ctx.restore();
  },
};
