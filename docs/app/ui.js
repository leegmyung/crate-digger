import { appState, exportTableToCsv, isWatched } from './state.js';

export const TERMS = {
  outcome: '수상·선정',
  outcomeTeam: '수상·선정 팀',
  priorOutcome: '수상·선정 이력',
  outcomeWithTech: '수상·선정(정답)',
  source: '출처',
  outlet: '매체',
  pending: '검증 대기',
  unscored: '참고',
};

export const SOURCE_LABELS = {
  indistreet: '인디스트릿',
  indiego: '인디고',
  sangsangmadang_live: '상상마당 라이브',
  sangsangmadang: '상상마당 라이브',
  band_discovery: '상상마당 밴드 디스커버리',
  burock_rookies: '부산록페 루키즈',
  busanrock: '부산록페 루키즈',
  dmz_lineup: 'DMZ 피스트레인',
  gb_creation: '경북 음악창작소',
  muse_sejong: '세종 뮤즈세종',
  yoojaeha_finalist: '유재하 본선',
  superrookie: '슈퍼루키챌린지',
  musicy: '음악취향Y',
  rhythmer: '리드머',
  poclanos: '포크라노스',
  izm: '이즘(IZM)',
  overtone: '오버톤',
  weiv: 'weiv',
  hiphople: '힙합엘이',
  trackzero: '멜론 트랙제로',
  k_indie_chart: 'K-인디차트',
  melon_indie: '멜론 인디',
  melon: '멜론 신보',
  genie: '지니 신보',
  bugs: '벅스 신보',
  flo: '플로 신보',
  visla: 'VISLA',
  instagram: '인스타그램',
  spotify: '스포티파이 협업',
  youtube: '유튜브 무대 반응',
};

export const ROLE_META = {
  discovery: {
    label: '발굴',
    fullLabel: '발굴 (점수 반영)',
    timelineLabel: '발굴',
    title: '발굴 출처: 후보 점수 계산에 반영됩니다.',
  },
  context: {
    label: '맥락',
    fullLabel: '맥락 (약하게)',
    timelineLabel: '맥락',
    title: '맥락 매체: 팀 참고용이며 후보 점수에는 약하게만 반영됩니다.',
  },
  pending: {
    label: '검증 대기',
    fullLabel: '검증 대기',
    timelineLabel: '참고',
    unscoredTitle: '점수에 안 쓰는 출처 — 검증 대기',
    title: '점수에 안 쓰는 출처 — 검증 대기: 수집 기간이 짧거나 검토 중이라 점수에 반영하지 않습니다.',
  },
  excluded: {
    label: '제외',
    fullLabel: '제외',
    timelineLabel: '참고',
    unscoredTitle: '점수에 안 쓰는 출처 — 제외',
    title: '점수에 안 쓰는 출처 — 제외: 과거 검증에서 변별력이 없어 점수에서 제외됩니다.',
  },
};

export const GRADE_META = {
  S: { label: 'S', title: `S등급 ${TERMS.outcome}` },
  A: { label: 'A', title: `A등급 ${TERMS.outcome}` },
  B: { label: 'B', title: `B등급 ${TERMS.outcome}` },
};

export function isLoweredOutcomeResult(result, sourceRoles = null) {
  const val = String(result || '').trim().toLowerCase();
  if (!val) return false;
  const list = Array.isArray(sourceRoles?.outcome_rules?.lower_results)
    ? sourceRoles.outcome_rules.lower_results.map(x => String(x || '').trim().toLowerCase())
    : ['nominee', 'shortlist'];
  return list.includes(val);
}

/** source_roles.json에서 신호 행의 역할·사유 항목을 조회한다. */
export function lookupSourceRoleMeta(sourceRoles, branch, source, program = '') {
  const sigs = sourceRoles?.signals;
  if (!sigs || typeof sigs !== 'object') return null;
  const b = String(branch || '').trim();
  const s = String(source || '').trim();
  const p = String(program || '').trim();
  if (b === '선정·지원' && p && sigs[`${b}:${p}`]) return sigs[`${b}:${p}`];
  if (b && s && sigs[`${b}:${s}`]) return sigs[`${b}:${s}`];
  if (b && p && sigs[`${b}:${p}`]) return sigs[`${b}:${p}`];
  return null;
}

export function roleBadgeHtml(role, opts = {}) {
  const key = ROLE_META[role] ? role : 'pending';
  const m = ROLE_META[key];
  const isTimeline = opts.context === 'timeline';
  const isUnscored = key === 'pending' || key === 'excluded';
  const txt = isTimeline ? m.timelineLabel : (opts.full ? m.fullLabel : m.label);
  const unscoredCls = isTimeline && isUnscored ? ' is-unscored' : '';
  const compactCls = opts.compact ? ' is-compact' : '';
  let tip;
  if (isTimeline && isUnscored) {
    tip = opts.title ? `${m.unscoredTitle} (${opts.title})` : m.unscoredTitle;
  } else {
    tip = opts.title ? `${m.fullLabel} — ${opts.title}` : m.title;
  }
  return `<span class="role-badge is-${key}${unscoredCls}${compactCls}" title="${escapeHtml(tip)}">${escapeHtml(txt)}</span>`;
}

export function gradeBadgeHtml(grade, opts = {}) {
  const g = String(grade || '').trim().toUpperCase();
  const m = GRADE_META[g];
  if (!m) return '';
  const weightTxt = opts.weight !== undefined && opts.weight !== null ? ` (가중치 ${opts.weight})` : '';
  const tip = `${m.title}${weightTxt}${opts.isNominee ? ' · 후보(한 등급 아래)' : ''}`;
  const nomineeTag = opts.isNominee
    ? '<span class="outcome-nominee-tag" title="상 후보·최종 후보 — 프로그램 기본 등급보다 한 단계 낮춰 집계">후보</span>'
    : '';
  return `<span class="grade-badge grade-${g}" title="${escapeHtml(tip)}">${g}</span>${nomineeTag}`;
}

/** '공연:indistreet' / '선정·지원:band_discovery' → { branch, code, label } */
export function formatSourceKey(src) {
  const raw = String(src || '');
  const idx = raw.indexOf(':');
  const branch = idx >= 0 ? raw.slice(0, idx) : '';
  const code = idx >= 0 ? raw.slice(idx + 1) : raw;
  let label = (branch === '선정·지원' && appState.programLabels.get(code))
    || SOURCE_LABELS[code]
    || appState.programLabels.get(code)
    || code;
  if (code === 'instagram') {
    if (branch === '공연') label = '인스타그램 (공연장 라인업)';
    else if (branch === '큐레이션') label = '인스타그램 (매거진)';
  }
  return { branch, code, label };
}

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

const KO_WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토'];

/** '2026-12-03' → '12/03(목)' */
export function formatKoreanShortDate(dateStr) {
  const m = String(dateStr || '').match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!m) return String(dateStr || '-');
  const d = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3])));
  const wd = KO_WEEKDAYS[d.getUTCDay()] || '';
  return `${m[2]}/${m[3]}(${wd})`;
}

/** { signal_date, venue } → '12/03(목) Club FF' */
export function formatNextGigText(gig) {
  if (!gig || !gig.signal_date) return '';
  const dt = formatKoreanShortDate(gig.signal_date);
  const v = String(gig.venue || '').trim();
  return v && v !== '공연장 미정' ? `${dt} ${v}` : dt;
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
  if (Number(r.pts_outlets) > 0) parts.push(`발굴 매체 ${r.outlets}곳(+${fmtNum(r.pts_outlets, 1)})`);
  if (Number(r.pts_context) > 0) parts.push(`맥락 매체 ${r.context_outlets ?? 0}곳(+${fmtNum(r.pts_context, 1)})`);
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
  if (Number(r.context_outlets) >= 1 && Number(r.pts_context) > 0) parts.push(`맥락 매체 ${r.context_outlets}곳`);
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
    { key: '발굴 매체', v: Number(r.pts_outlets) || 0, color: 'var(--seg-outlets)' },
    { key: '맥락 매체', v: Number(r.pts_context) || 0, color: 'var(--seg-context)' },
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

/** 팀 사진: 스포티파이 사진 → 없으면 이름 첫 글자(+장르색 모노그램). size = px. */
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
  lines.push(`[Gigle Research 주간 브리핑 · ${dataEnd || latestDate} 기준]`);
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

const RESULT_KO = {
  nominee: '후보',
  shortlist: '최종 후보',
  winner: '수상',
  selected: '선정',
};

function buildDynamicGradeGroups(sourceRoles, gradeRows) {
  const cfgOutcomes = (sourceRoles && typeof sourceRoles.outcomes === 'object') ? sourceRoles.outcomes : {};
  const byGrade = new Map();
  const ensure = (grade, weight) => {
    const g = String(grade || '').trim().toUpperCase();
    if (!g) return null;
    if (!byGrade.has(g)) {
      byGrade.set(g, {
        grade: g,
        weight: Number(weight) || 0,
        basePrograms: new Map(),
        countedRows: 0,
        totalRows: 0,
        loweredRows: 0,
      });
    }
    const entry = byGrade.get(g);
    if (Number(weight) > entry.weight) entry.weight = Number(weight);
    return entry;
  };

  for (const [prog, meta] of Object.entries(cfgOutcomes)) {
    if (prog.startsWith('_') || !meta || typeof meta !== 'object') continue;
    const entry = ensure(meta.grade, meta.weight);
    if (entry) entry.basePrograms.set(prog, meta.label || prog);
  }

  const lowerSet = new Set(
    (Array.isArray(sourceRoles?.outcome_rules?.lower_results) ? sourceRoles.outcome_rules.lower_results : [])
      .map(v => String(v || '').trim().toLowerCase())
      .filter(Boolean)
  );

  for (const r of (Array.isArray(gradeRows) ? gradeRows : [])) {
    const entry = ensure(r.grade, r.weight);
    if (!entry) continue;
    const counted = Number(r.counted_rows) || 0;
    const total = Number(r.total_rows) || 0;
    entry.countedRows += counted;
    entry.totalRows += total;
    const resKey = String(r.result || '').trim().toLowerCase();
    if (resKey && lowerSet.has(resKey)) {
      entry.loweredRows += counted;
    }
    // Only add program to basePrograms if not defined anywhere in source_roles.json
    const cfgDef = cfgOutcomes[r.program];
    if (!cfgDef && r.program) {
      entry.basePrograms.set(r.program, r.program_label || r.program);
    }
  }

  return [...byGrade.values()].sort(
    (a, b) => (b.weight - a.weight) || a.grade.localeCompare(b.grade)
  );
}

/**
 * outcomes.csv 집계(gradeRows) + source_roles.json(outcomes, outcome_rules)을 동적으로 읽어
 * 하드코딩 없는 정답 등급표·정리 규칙 HTML을 만든다.
 */
export function renderOutcomeGradeGuideHtml({ sourceRoles = null, gradeRows = [] } = {}) {
  const groups = buildDynamicGradeGroups(sourceRoles, gradeRows);
  if (!groups.length) return '';

  const rules = sourceRoles?.outcome_rules || null;
  const lowerResults = Array.isArray(rules?.lower_results) ? rules.lower_results : [];
  const lowerLabels = lowerResults.map(r => RESULT_KO[String(r).toLowerCase()] || String(r));
  const excludedObj = (rules && typeof rules.excluded_teams === 'object' && rules.excluded_teams)
    ? rules.excluded_teams
    : {};
  const excludedEntries = Object.entries(excludedObj).filter(([k]) => !k.startsWith('_'));

  // Group excluded teams by shared base reason (text before first ' (' if present)
  const reasonBuckets = new Map();
  for (const [team, reason] of excludedEntries) {
    const raw = String(reason || '').trim();
    const base = raw.includes(' (') ? raw.slice(0, raw.indexOf(' (')).trim() : (raw || '정답 집계 제외');
    if (!reasonBuckets.has(base)) reasonBuckets.set(base, []);
    reasonBuckets.get(base).push(team);
  }

  const gradeTableRows = groups.map(g => {
    const progs = [...g.basePrograms.values()];
    const countTxt = g.totalRows > 0
      ? `${fmtInt(g.countedRows)}건${g.loweredRows > 0 ? ` <span class="muted">(후보 ${fmtInt(g.loweredRows)})</span>` : ''}`
      : '—';
    return `
      <tr>
        <td class="nowrap">${gradeBadgeHtml(g.grade, { weight: g.weight })}</td>
        <td class="num nowrap mono">${fmtInt(g.weight)}</td>
        <td>${progs.length ? escapeHtml(progs.join(' · ')) : '<span class="muted">—</span>'}</td>
        <td class="num nowrap">${countTxt}</td>
      </tr>
    `;
  }).join('');

  const rulesLines = [];
  if (lowerResults.length) {
    rulesLines.push(
      `<li><strong>후보 등급 하향</strong>: 결과가 <strong>${escapeHtml(lowerLabels.join('·'))}</strong>(<code>${escapeHtml(lowerResults.join(', '))}</code>)인 기록은 프로그램 기본 등급보다 한 단계 아래로 집계합니다(최하 등급은 유지, 수상·최종 선정은 기본 등급).</li>`
    );
  }
  if (excludedEntries.length) {
    const bucketItems = [...reasonBuckets.entries()].map(([baseReason, teams]) => {
      const sortedTeams = [...teams].sort((a, b) => a.localeCompare(b, 'ko'));
      return `${escapeHtml(baseReason)} (<strong>${fmtInt(sortedTeams.length)}팀</strong>: ${escapeHtml(sortedTeams.join(', '))})`;
    }).join(' / ');
    rulesLines.push(
      `<li><strong>정답 제외 팀 (${fmtInt(excludedEntries.length)}팀)</strong>: ${bucketItems}</li>`
    );
  }

  return `
    <div class="grade-guide-wrap">
      <div class="table-wrap">
        <table class="data-table grade-guide-table">
          <thead>
            <tr>
              <th class="nowrap">등급</th>
              <th class="num nowrap">가중치</th>
              <th>기본 프로그램</th>
              <th class="num nowrap">집계 정답</th>
            </tr>
          </thead>
          <tbody>${gradeTableRows}</tbody>
        </table>
      </div>
      ${rulesLines.length ? `<ul class="sc-info-list" style="margin-top:10px;">${rulesLines.join('')}</ul>` : ''}
    </div>
  `;
}

export function renderCompactGradeSummary({ sourceRoles = null, gradeRows = [] } = {}) {
  const groups = buildDynamicGradeGroups(sourceRoles, gradeRows);
  if (!groups.length) return '';
  const parts = groups.map(g => {
    const progs = [...g.basePrograms.values()].slice(0, 3).join('·');
    const more = g.basePrograms.size > 3 ? ` 외 ${g.basePrograms.size - 3}` : '';
    return `<strong>${escapeHtml(g.grade)}</strong>(가중치 ${fmtInt(g.weight)}${progs ? ` · ${escapeHtml(progs)}${more}` : ''})`;
  });
  const lowerResults = Array.isArray(sourceRoles?.outcome_rules?.lower_results)
    ? sourceRoles.outcome_rules.lower_results
    : [];
  const lowerNote = lowerResults.length ? ' · 후보는 한 등급 아래' : '';
  return `등급: ${parts.join(' / ')}${lowerNote}.`;
}

// ---------- Lazy External Library Loaders (Chart.js / D3) ----------

const scriptLoadPromises = new Map();

function loadExternalScript(url) {
  if (scriptLoadPromises.has(url)) return scriptLoadPromises.get(url);
  const p = new Promise((resolve) => {
    const existing = document.querySelector(`script[src="${url}"]`);
    if (existing) {
      if (existing.dataset.loaded === '1') { resolve(true); return; }
      existing.addEventListener('load', () => resolve(true), { once: true });
      existing.addEventListener('error', () => resolve(false), { once: true });
      return;
    }
    const s = document.createElement('script');
    s.src = url;
    s.async = true;
    s.addEventListener('load', () => {
      s.dataset.loaded = '1';
      resolve(true);
    }, { once: true });
    s.addEventListener('error', () => resolve(false), { once: true });
    document.head.appendChild(s);
  });
  scriptLoadPromises.set(url, p);
  return p;
}

const CHART_JS_URL = 'https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js';
const D3_JS_URL = 'https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/d3.min.js';

export async function ensureChartJs() {
  if (window.Chart) return window.Chart;
  await loadExternalScript(CHART_JS_URL);
  if (window.Chart) {
    const ink = cssVar('--ink') || '#18181b';
    const inkMuted = cssVar('--ink-muted') || '#6b7280';
    const line = cssVar('--line') || '#e4e4e7';
    const surface = cssVar('--surface') || '#ffffff';
    window.Chart.defaults.color = inkMuted || ink;
    window.Chart.defaults.borderColor = line;
    if (window.Chart.defaults.plugins?.tooltip) {
      window.Chart.defaults.plugins.tooltip.backgroundColor = surface;
      window.Chart.defaults.plugins.tooltip.titleColor = ink;
      window.Chart.defaults.plugins.tooltip.bodyColor = ink;
      window.Chart.defaults.plugins.tooltip.borderColor = line;
      window.Chart.defaults.plugins.tooltip.borderWidth = 1;
    }
  }
  return window.Chart || null;
}

export async function ensureD3() {
  if (window.d3) return window.d3;
  await loadExternalScript(D3_JS_URL);
  return window.d3 || null;
}

// ---------- Shared Table Usability Helpers (Sort, Keyboard, Hover Preview, CSV) ----------

/**
 * 정렬 가능한 표 머리줄(th)에 일관된 정렬 방향 표시(▲/▼/↕)와 aria-sort를 반영한다.
 * attrName: 'sort' → data-sort, 'debutSort' → data-debut-sort 등.
 */
export function updateSortHeaders(tableEl, activeCol, dir, attrName = 'sort') {
  if (!tableEl) return;
  const dataAttr = attrName.replace(/[A-Z]/g, m => `-${m.toLowerCase()}`);
  tableEl.querySelectorAll(`th[data-${dataAttr}]`).forEach(th => {
    const col = th.dataset[attrName];
    const baseLabel = th.dataset.sortLabel || th.textContent.replace(/\s*[▲▼↕]\s*$/, '').trim();
    th.dataset.sortLabel = baseLabel;
    const isActive = col === activeCol;
    const arrow = isActive ? (dir === 'asc' ? '▲' : '▼') : '↕';
    th.classList.add('sortable');
    th.classList.toggle('is-sorted', isActive);
    th.setAttribute('aria-sort', isActive ? (dir === 'asc' ? 'ascending' : 'descending') : 'none');
    th.setAttribute('tabindex', '0');
    th.innerHTML = `<span class="th-sort-inner"><span class="th-sort-lbl">${escapeHtml(baseLabel)}</span><span class="sort-ind" aria-hidden="true">${arrow}</span></span>`;
  });
}

/**
 * 표 행 키보드 탐색(↑/↓/Home/End 이동, Enter 상세 실행, →/← 펼침 토글)을 일관되게 연결한다.
 */
export function wireTableKeyboardNav(tbodyEl, {
  rowSelector = 'tr[data-nav-row]',
  onActivate = null,
  onToggleExpand = null,
} = {}) {
  if (!tbodyEl || tbodyEl.dataset.kbNavWired === '1') return;
  tbodyEl.dataset.kbNavWired = '1';
  tbodyEl.addEventListener('keydown', (e) => {
    const tag = e.target?.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
    const tr = e.target.closest(rowSelector);
    if (!tr || !tbodyEl.contains(tr)) return;

    if (e.key === 'ArrowDown' || e.key === 'ArrowUp' || e.key === 'Home' || e.key === 'End') {
      const rows = [...tbodyEl.querySelectorAll(rowSelector)];
      if (!rows.length) return;
      const idx = rows.indexOf(tr);
      let nextIdx = idx;
      if (e.key === 'ArrowDown') nextIdx = Math.min(rows.length - 1, idx + 1);
      else if (e.key === 'ArrowUp') nextIdx = Math.max(0, idx - 1);
      else if (e.key === 'Home') nextIdx = 0;
      else if (e.key === 'End') nextIdx = rows.length - 1;
      e.preventDefault();
      const target = rows[nextIdx];
      if (target) {
        target.focus({ preventScroll: false });
        target.scrollIntoView({ block: 'nearest' });
      }
      return;
    }

    if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
      if (e.target.closest('button') || e.target.closest('a')) return;
      if (onToggleExpand) {
        e.preventDefault();
        onToggleExpand(tr, e.key);
      }
      return;
    }

    if (e.key === 'Enter' || e.key === ' ') {
      if (e.target.closest('button') || e.target.closest('a')) return;
      if (onActivate) {
        e.preventDefault();
        onActivate(tr);
      }
    }
  });
}

// Single shared lightweight floating hover preview popover for tables
let hoverPreviewEl = null;
let hoverPreviewTimer = null;
let hoverPreviewRow = null;
let hoverPreviewGlobalWired = false;

function ensureHoverPreviewEl() {
  if (hoverPreviewEl && hoverPreviewEl.isConnected) return hoverPreviewEl;
  const el = document.createElement('div');
  el.id = 'rowHoverPreview';
  el.className = 'row-hover-preview';
  el.setAttribute('role', 'tooltip');
  el.setAttribute('aria-hidden', 'true');
  el.hidden = true;
  document.body.appendChild(el);
  hoverPreviewEl = el;
  if (!hoverPreviewGlobalWired) {
    hoverPreviewGlobalWired = true;
    window.addEventListener('scroll', hideRowHoverPreview, true);
    window.addEventListener('resize', hideRowHoverPreview);
    window.addEventListener('hashchange', hideRowHoverPreview);
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') hideRowHoverPreview();
    });
  }
  return el;
}

export function hideRowHoverPreview() {
  clearTimeout(hoverPreviewTimer);
  hoverPreviewTimer = null;
  hoverPreviewRow = null;
  if (hoverPreviewEl) {
    hoverPreviewEl.hidden = true;
    hoverPreviewEl.setAttribute('aria-hidden', 'true');
  }
}

function positionHoverPreview(el, anchorRect, pointerX) {
  const pad = 12;
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  el.style.left = '0px';
  el.style.top = '0px';
  el.hidden = false;
  const rect = el.getBoundingClientRect();

  let left = Number.isFinite(pointerX) ? pointerX + 14 : anchorRect.left + 24;
  if (left + rect.width + pad > vw) {
    left = Math.max(pad, vw - rect.width - pad);
  }
  let top = anchorRect.bottom + 8;
  if (top + rect.height + pad > vh) {
    top = Math.max(pad, anchorRect.top - rect.height - 8);
  }
  el.style.left = `${Math.round(left)}px`;
  el.style.top = `${Math.round(top)}px`;
  el.setAttribute('aria-hidden', 'false');
}

/**
 * 데스크톱 포인터 호버 시 모든 표에 일관된 행 미리보기 카드를 띄운다.
 * 버튼/링크 위에서는 방해되지 않게 숨기며, 모바일 터치에서는 동작하지 않는다.
 */
export function wireTableRowHoverPreview(tbodyEl, getPreviewHtml, { rowSelector = 'tr[data-nav-row]' } = {}) {
  if (!tbodyEl || typeof getPreviewHtml !== 'function') return;
  if (tbodyEl.dataset.hoverPreviewWired === '1') return;
  tbodyEl.dataset.hoverPreviewWired = '1';

  const supportsHover = typeof window !== 'undefined' &&
    window.matchMedia &&
    window.matchMedia('(hover: hover) and (pointer: fine)').matches;
  if (!supportsHover) return;

  tbodyEl.addEventListener('mouseover', (e) => {
    if (e.target.closest('button') || e.target.closest('a') || e.target.closest('select')) {
      hideRowHoverPreview();
      return;
    }
    const tr = e.target.closest(rowSelector);
    if (!tr || !tbodyEl.contains(tr)) {
      hideRowHoverPreview();
      return;
    }
    if (tr === hoverPreviewRow) return;
    clearTimeout(hoverPreviewTimer);
    hoverPreviewRow = tr;
    const pointerX = e.clientX;
    hoverPreviewTimer = setTimeout(() => {
      if (!tr.isConnected || hoverPreviewRow !== tr) return;
      const html = getPreviewHtml(tr);
      if (!html) {
        hideRowHoverPreview();
        return;
      }
      const el = ensureHoverPreviewEl();
      el.innerHTML = html;
      positionHoverPreview(el, tr.getBoundingClientRect(), pointerX);
    }, 220);
  });

  tbodyEl.addEventListener('mouseleave', hideRowHoverPreview);
  tbodyEl.addEventListener('mousedown', hideRowHoverPreview);
}

/**
 * 모든 표에서 동일한 이름·스타일의 인라인 CSV 내보내기 버튼 HTML을 반환한다.
 */
export function renderTableCsvBtn(id = '', label = 'CSV 내려받기') {
  const idAttr = id ? ` id="${escapeHtml(id)}"` : '';
  return `<button type="button" class="btn btn-sm table-csv-btn"${idAttr} data-table-csv>${escapeHtml(label)}</button>`;
}

export function triggerTableCsvExport({ filename, headers, rows } = {}) {
  if (!headers || !headers.length || !rows || !rows.length) {
    window.dispatchEvent(new CustomEvent('app:toast', { detail: '내려받을 행이 없습니다.' }));
    return false;
  }
  exportTableToCsv(filename || `crate_digger_${appState.dataEnd || 'export'}.csv`, headers, rows);
  window.dispatchEvent(new CustomEvent('app:toast', { detail: 'CSV 파일을 내려받았습니다.' }));
  return true;
}

// ---------- Discovery stage, recent activity, dormant & newcomer_check helpers ----------

export const STAGE_META = {
  0: {
    code: 0,
    short: '백지',
    label: '백지',
    next: '남의 언급 1갈래(공연·큐레이션·선정·지원)가 생기면 첫 신호 단계',
  },
  1: {
    code: 1,
    short: '첫 신호',
    label: '첫 신호',
    next: '다른 갈래 언급이 추가되어 2갈래 이상이면 여러 갈래 단계',
  },
  2: {
    code: 2,
    short: '여러 갈래',
    label: '여러 갈래',
    next: '선정 단계 3 이상(DMZ 제외) 또는 B등급 정답이면 선정·중간 정답 단계',
  },
  3: {
    code: 3,
    short: '선정',
    label: '선정·중간 정답',
    next: 'S·A등급 정답을 받으면 졸업 단계',
  },
  4: {
    code: 4,
    short: '졸업',
    label: '졸업',
    next: '최고 단계 도달 (S·A등급 정답 또는 유명 팀)',
  },
};

export const STAGE_ORDER = [0, 1, 2, 3, 4];

export const NEWCOMER_UNVERIFIED_TIP = '첫 발매일 미확인 — 수집 시작 직후 처음 보여 신인인지 확실치 않음';

export function stageBadgeHtml(stage, { short = false, title = '' } = {}) {
  if (stage === null || stage === undefined || stage === '') return '';
  const meta = STAGE_META[Number(stage)];
  if (!meta) return '';
  const text = short ? meta.short : meta.label;
  const tip = title || `발굴 단계: ${meta.label} — ${meta.next}`;
  return `<span class="stage-badge stage-${meta.code}" title="${escapeHtml(tip)}">${escapeHtml(text)}</span>`;
}

export function nextStageConditionText(stage) {
  if (stage === null || stage === undefined || stage === '') return '';
  return STAGE_META[Number(stage)]?.next || '';
}

export function formatRecentActivityCell(st) {
  if (!st || st.momentum_pct === null || st.momentum_pct === undefined || !Number.isFinite(Number(st.momentum_pct))) {
    const tip = st && Number(st.stage) === 0
      ? '백지 단계 — 아직 남의 언급 없음'
      : '최근 활동 비교 데이터 없음';
    return {
      html: `<span class="muted" title="${escapeHtml(tip)}">—</span>`,
      text: '—',
      tooltip: tip,
    };
  }
  const pct = Math.round(Number(st.momentum_pct) * 100);
  const label = st.momentum_label || '보합';
  let arrow = '→';
  let cls = 'act-flat';
  if (label === '상승') {
    arrow = '▲';
    cls = 'act-up';
  } else if (label === '하락') {
    arrow = '▼';
    cls = 'act-down';
  }
  const stageLabel = STAGE_META[Number(st.stage)]?.label || st.stage_label || '';
  const rec = Number(st.recent_n) || 0;
  const prev = Number(st.prev_n) || 0;
  const tooltip = `${stageLabel ? `${stageLabel} 단계 안 ` : ''}백분위 ${pct}% (${label}) · 최근 90일 언급 ${fmtInt(rec)}건 대 그 전 90일 ${fmtInt(prev)}건`;
  return {
    html: `<span class="act-pill ${cls}" title="${escapeHtml(tooltip)}"><span class="act-arrow" aria-hidden="true">${arrow}</span><span class="mono">${pct}%</span></span>`,
    text: `${arrow} ${pct}% (최근 90일 ${rec}건 / 이전 90일 ${prev}건)`,
    tooltip,
  };
}

export function isDormantTeam(row) {
  if (!row || typeof row !== 'object') return false;
  if (row.recent180 === undefined || row.recent180 === null) return false;
  if (row.gigs_1y === undefined || row.gigs_1y === null) return false;
  return Number(row.recent180) === 0 && Number(row.gigs_1y) === 0;
}

export function dormantBadgeHtml(rowOrFlag) {
  const dormant = typeof rowOrFlag === 'boolean' ? rowOrFlag : isDormantTeam(rowOrFlag);
  if (!dormant) return '';
  return '<span class="tag-pill tag-dormant" title="최근 180일 신호 0건 · 최근 1년 공연 0건">휴면</span>';
}

export function isNewcomerUnverified(teamKey, profile = null) {
  const fromProfile = profile && Object.prototype.hasOwnProperty.call(profile, 'newcomer_check')
    ? profile.newcomer_check
    : undefined;
  const raw = fromProfile !== undefined && fromProfile !== null && String(fromProfile).trim() !== ''
    ? fromProfile
    : (teamKey && appState.newcomerCheckByTeam ? appState.newcomerCheckByTeam.get(teamKey) : '');
  return String(raw || '').trim().toLowerCase() === 'unverified';
}

export function newcomerUnverifiedBadgeHtml(teamKey, profile = null) {
  if (!isNewcomerUnverified(teamKey, profile)) return '';
  return `<span class="tag-pill tag-unverified" title="${escapeHtml(NEWCOMER_UNVERIFIED_TIP)}">신인 미확인</span>`;
}

// ---------- Alerts (docs/data/alerts.json) helpers ----------

export const ALERT_TYPE_LABELS = {
  new_outcome: '새 정답',
  new_selection: '새 선정·지원',
  blank_first_mention: '백지 신인 첫 언급',
  stage_up: '단계 상승',
  big_venue_first: '큰 공연장 첫 출연',
  peer_winner: '같은 무대 수상 팀',
  rank_jump: '순위 급상승',
  new_gig: '새 공연',
};

export function alertDedupKey(a) {
  if (!a) return '';
  return `${a.type || ''}::${a.team_key || ''}::${a.date || ''}::${a.text || ''}`;
}

export function alertKindChipHtml(alert, typesMap = null) {
  if (!alert) return '';
  const t = String(alert.type || '').trim();
  const safeType = /^[a-z0-9_]+$/.test(t) ? t : 'other';
  const label = alert.type_label || (typesMap && typesMap[t]) || ALERT_TYPE_LABELS[t] || t || '알림';
  return `<span class="alert-kind-chip alert-kind-${safeType}">${escapeHtml(label)}</span>`;
}

export function formatAlertEvidenceText(alert) {
  if (!alert || !Array.isArray(alert.evidence) || !alert.evidence.length) return '';
  const seen = new Set();
  const parts = [];
  for (const ev of alert.evidence) {
    if (!ev || typeof ev !== 'object') continue;
    const progLabel = ev.program ? (appState.programLabels?.get(ev.program) || SOURCE_LABELS[ev.program] || ev.program) : '';
    const srcLabel = ev.source ? (SOURCE_LABELS[ev.source] || ev.source) : '';
    const label = ev.venue || progLabel || srcLabel || ev.branch || '';
    const dt = ev.date && ev.date !== alert.date ? ev.date : '';
    const token = dt ? `${label} (${dt})` : label;
    if (!token || seen.has(token)) continue;
    seen.add(token);
    parts.push(token);
    if (parts.length >= 3) break;
  }
  return parts.join(' · ');
}

export function formatAlertBaselineNote(alertsData) {
  if (!alertsData) return '';
  const parts = [];
  if (alertsData.as_of) parts.push(`기준일 ${alertsData.as_of}`);
  const b = alertsData.baseline;
  if (b && typeof b === 'object') {
    if (b.since) parts.push(`비교 기준 ${b.since} 이후`);
    if (b.note) parts.push(b.note);
  }
  return parts.join(' · ');
}

export function getWatchlistAlerts(alertsData, watchlist = null) {
  if (!alertsData || !Array.isArray(alertsData.alerts) || !alertsData.alerts.length) return [];
  const list = Array.isArray(watchlist) ? watchlist : [];
  if (!list.length) return [];
  const keySet = new Set();
  for (const item of list) {
    if (typeof item === 'string' && item) keySet.add(item);
    else if (item && typeof item.team_key === 'string' && item.team_key) keySet.add(item.team_key);
  }
  if (!keySet.size) return [];
  return alertsData.alerts.filter(a => keySet.has(a.team_key));
}

export function getGeneralTodayAlerts(alertsData, { limit = 8, excludeKeys = null } = {}) {
  if (!alertsData || !Array.isArray(alertsData.alerts) || !alertsData.alerts.length) return [];
  const ex = excludeKeys instanceof Set ? excludeKeys : null;
  const out = [];
  for (const a of alertsData.alerts) {
    if (a.type === 'new_gig') continue;
    if (ex && ex.has(alertDedupKey(a))) continue;
    out.push(a);
    if (out.length >= limit) break;
  }
  return out;
}




