/**
 * 1-4: 공용 ⓘ 말풍선 부품 (InfoTip)
 * - 흰 상자(--surface) + 1px 선(--line-strong), 그림자 0, 최대 폭 320px
 * - 마우스 호버 · 키보드 Tab 초점 · 모바일 탭 모두 열림, Esc / 바깥 클릭으로 닫힘
 * - position: fixed 뷰포트 클램프로 어떤 컨테이너(표·overflow:hidden) 안에서도 화면 밖으로 넘치지 않음
 */

function esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

export const INFO_TIPS = {
  score: {
    what: '여러 출처에서 포착된 신인 신호(갈래 수·선정 최고 단계·공연장 다양성·발굴 매체·수상 팀과 같은 무대)를 가중 합산한 종합 점수입니다.',
    period: '기본 최근 3년(필터에서 기간 변경 가능)',
    compare: '현재 필터 조건에 해당하는 신인 후보끼리 비교',
    bands: [
      ['발굴 출처', '점수에 직접 반영되는 공연·선정·매체 기록'],
      ['맥락 출처', '참고용으로 약하게만 반영'],
      ['검증 대기·제외', '점수에 반영하지 않음'],
    ],
  },
  score_breakdown: {
    what: '이 팀의 종합 점수가 어떤 신호 항목에서 몇 점씩 만들어졌는지 항목별로 보여 줍니다.',
    period: '현재 선택된 기준일과 조회 기간(기본 3년)',
    compare: '가중치 설정(기본 v2) 기준',
    bands: [
      ['갈래 수', '공연·선정·발매·큐레이션 중 겹친 갈래 수'],
      ['선정 최고 단계', '루키·지원 사업 진출 단계(0~4)'],
      ['수상 팀과 같은 무대', '이미 수상·선정된 팀과 함께 선 무대'],
    ],
  },
  discovery_stage: {
    what: '팀이 인디 씬에서 포착되어 수상·선정에 이르기까지의 진행 단계입니다.',
    period: '누적 신호 및 수상·선정 기록 기준',
    compare: '전체 수집 팀 공통 5단계 기준',
    bands: [
      ['0단계 백지', '발매는 있으나 아직 외부 신호 없음'],
      ['1단계 첫 신호', '한 갈래에서 첫 외부 활동 포착'],
      ['2단계 여러 갈래', '두 갈래 이상 또는 다수 공연장·매체 확장'],
      ['3단계 선정', '루키·지원 사업 선정 또는 최종 후보'],
      ['4단계 졸업', '주요 수상·선정 달성(기본 목록에서 숨김)'],
    ],
  },
  recent_activity: {
    what: '최근 90일 동안 다른 곳(공연장·매체·선정)에서 언급된 횟수가 직전 90일보다 얼마나 늘었는지 같은 단계 안에서 백분위로 보여 줍니다.',
    period: '최근 90일 vs 직전 90일',
    compare: '같은 발굴 단계에 속한 팀들과 상대 비교',
    bands: [
      ['▲ 상승', '직전 90일 대비 언급 증가(상위 구간)'],
      ['• 유지', '직전 90일과 비슷한 활동 수준'],
      ['▼ 둔화', '직전 90일 대비 언급 감소'],
    ],
  },
  first_timer_share: {
    what: '최근 1년 이 공연장에 선 팀 중 우리 데이터상 첫 공연 기록이 바로 이 무대였던 팀의 비율입니다.',
    period: '기준일 직전 1년',
    compare: '이 공연장 전체 출연 팀 대비 비율',
    bands: [
      ['40% 이상', '신인이 처음 서는 등용문 성격이 강함'],
      ['20~39%', '신인과 기성 팀이 고르게 섞여 출연'],
      ['20% 미만', '다른 무대를 거친 팀 중심의 공연장'],
    ],
  },
  genre_inferred: {
    what: '같은 무대에 선 팀들과 자주 선 공연장 성향을 바탕으로 추정한 장르입니다.',
    period: '누적 공연·매체 기록 기준',
    compare: '공식 장르가 비어 있는 팀 대상 추정',
  },
  rank_change: {
    what: '기준일 순위가 지난달(30일 전) 스냅샷보다 몇 칸 올랐는지(▲) 내렸는지(▼) 보여 줍니다. 지난달 스냅샷이 아직 없으면 지난주(7일 전)와 비교하며, 점수가 그대로인 동점 이동은 숨깁니다.',
    period: '지난달(또는 지난주) 스냅샷 대비',
    compare: '상위 300팀 스냅샷 기준 (300위 밖 진입은 구간 표시)',
  },
  genre_rank: {
    what: '같은 대표 장르 안에서 이 팀의 현재 순위와 전체 팀 수입니다. 장르가 비어 있거나 미분류인 팀은 장르 미정으로 표시합니다.',
    period: '기준일 스냅샷(또는 현재 후보) 기준',
    compare: '같은 대표 장르 팀 무리 안에서 비교',
  },
  preset_debut12: {
    what: '첫 발매일이 기준일로부터 12개월 이내인 갓 데뷔 신인만 추립니다.',
    period: '첫 발매 후 12개월 이내',
    compare: '프로필 첫 발매일(teams.first_release) 기준',
  },
  preset_blank: {
    what: '첫 발매 기록은 있으나 아직 외부 공연·선정·매체 언급이 없는 0단계(백지) 신인만 보여 줍니다.',
    period: '기준일 누적 기록 기준',
    compare: '발굴 단계 0(백지)',
  },
  preset_selected: {
    what: '루키·지원 사업 선정 또는 최종 후보 단계(3단계)에 오른 팀만 추립니다.',
    period: '기준일 누적 기록 기준',
    compare: '발굴 단계 3(선정)',
  },
  preset_regional: {
    what: '주요 활동 도시가 서울 외 지역으로 집계된 지방 씬 후보 팀만 보여 줍니다.',
    period: '누적 공연 도시 집계(team_cities) 기준',
    compare: '활동 도시 ≠ 서울',
  },
  status_stage: {
    what: '남의 언급이 몇 갈래에서 나왔는지, 선정·수상까지 갔는지로 나눈 발굴 단계입니다. 백지 → 첫 신호 → 여러 갈래 → 선정·중간 정답 → 졸업.',
    period: '기준일까지 누적',
    compare: 'discovery_stage.sql 과 같은 정의',
  },
  status_activity: {
    what: '최근 6개월(180일) 동안 쌓인 신호 수로 본 활동 정도입니다. 0건 조용함 · 1~2건 가끔 · 3~9건 꾸준함 · 10건 이상 활발. 막대는 20건이면 가득 찹니다(로그 눈금).',
    period: '기준일 전 180일',
    compare: '제외 처리된 신호는 세지 않음',
  },
  status_branches: {
    what: '발매 · 공연 · 선정·지원 · 큐레이션 4갈래 중 몇 갈래에서 신호가 나왔는지입니다. 여러 갈래에서 동시에 보일수록 우연이 아닐 가능성이 큽니다.',
    period: '점수 계산 기간(기본 3년)',
    compare: '4갈래 중 개수',
  },
  status_scene: {
    what: '같은 날 같은 공연장에 함께 선 팀 가운데, 그 공연 전에 이미 수상·선정 정답을 받은 팀이 몇 팀인지 셉니다. 막대는 10팀이면 가득 찹니다(로그 눈금).',
    period: '기준일까지 누적',
    compare: 'features.sql 의 peer_winner 와 같은 정의(같은 날 · 같은 공연장)',
  },
  change_row: {
    what: '고른 기간(7일·30일) 동안 새로 생긴 신호·공연 수와 순위 변화입니다. 큰 숫자 = 이번 기간, 작은 글씨 = 직전 같은 길이 기간과의 차이, 회색 = 기준 기간.',
    period: '기준일 끝 7일 또는 30일',
    compare: '순위는 상위 300 스냅샷(지난주·지난달) 대비',
  },
  peer_compare: {
    what: '종합 점수가 비슷한 처지의 팀들 사이에서 상위 몇 %인지입니다. 기본은 같은 발굴 단계 팀 전체, 전환하면 같은 단계 + 같은 장르(프로필·매체 장르가 있는 팀만, 추정 장르 제외). 등급: 상위 10% 탁월 · 30% 좋음 · 70% 보통 · 그 아래 아래.',
    period: '기준일 시점 점수 후보군(신인 · 유명 팀 제외)',
    compare: '이웃이 30팀보다 적으면 등급 대신 \'비교할 팀이 적음\' (peer_compare.sql)',
  },
  event_stars: {
    what: '활동 중 \'사건\'(첫 언급·매체 첫 소개·선정·큰 공연장 첫 출연·처음 서울 공연·정답)에 별 1~5개를 매겼습니다. 같은 사건이라도 그때 작은 팀일수록 별이 높습니다(그때 발굴 단계로 조정: 백지 +2 · 첫 신호 +1 · 선정 −1 · 졸업 −2). 점수에는 넣지 않는 화면용입니다.',
    period: '사건 전후 28일 (사건 당일 제외, 뒤쪽은 기준일까지)',
    compare: 'scripts/event_stars.py — 공연 = 서로 다른 공연 날짜 수, 언급 = 큐레이션·선정 언급 수',
  },
  gig_block: {
    what: '최근 12개월 공연을 공연장 체급(S ~150명 · M ~400명 · L ~1,000명 · XL 그 이상)·도시·라인업 역할로 나눠 봅니다. 같은 날 같은 공연장에 13팀 이상이면 페스티벌로 따로 셉니다. 라인업 역할은 단독(출연 1팀)과 제목에 이름이 걸린 단 한 팀(헤드라이너)만 확실히 가리고, 나머지는 서포트 또는 역할 모름입니다.',
    period: '기준일 전 12개월 (라인업 역할은 lineup_roles.csv 기간)',
    compare: '체급 = config/venue_capacity.json, 라인업 = docs/lineup_roles.md',
  },
  heatmap: {
    what: '칸 진하기는 같은 발굴 단계(장르를 알면 같은 장르까지) 이웃 팀들 사이에서 이 팀이 어디쯤인지입니다. 상위 10% = 5단계, 30% = 4, 70% = 3, 90% = 2, 나머지 = 1. 칸 숫자는 실제 값입니다.',
    period: '기준일 누적 기록 (최근 언급은 최근 90일)',
    compare: '이웃 비교(peer_compare.sql). 최근 언급·지역 수와 이웃 비교에 없는 팀은 지금 표 안에서 비교',
    ranges: [
      ['5단계', '이웃 상위 10% 안'],
      ['1단계', '이웃 하위 10%'],
      ['회색', '기록 없음 (0과 다름)'],
    ],
  },
  preset_rising: {
    what: '유명 팀 제외 × 공연장 체급 M 이하 × 멜론 팬 10,000 이하 × 최근 30일 외부 언급이 직전 30일보다 늘어난 팀을 증가 폭(growth) 순으로 보여 줍니다.',
    period: '최근 30일 vs 직전 30일',
    compare: 'docs/lab/sql/rising_preset.sql (한국판 Rising 조건)',
  },
};

/**
 * 공용 ⓘ 말풍선 버튼 HTML을 반환한다.
 * @param {string} title - 말풍선 제목
 * @param {{ what?: string, period?: string, compare?: string, bands?: Array<[string, string]|{label:string, desc:string}> }} spec
 * @param {{ compact?: boolean, label?: string }} [opts]
 */
export function infoTip(title, spec = {}, opts = {}) {
  const payload = {
    title: String(title || '').trim(),
    what: spec?.what ? String(spec.what).trim() : '',
    period: spec?.period ? String(spec.period).trim() : '',
    compare: spec?.compare ? String(spec.compare).trim() : '',
    bands: Array.isArray(spec?.bands)
      ? spec.bands
          .map(b => (Array.isArray(b) ? [String(b[0] || ''), String(b[1] || '')] : [String(b?.label || ''), String(b?.desc || '')]))
          .filter(([k, v]) => k || v)
      : [],
  };
  const encoded = encodeURIComponent(JSON.stringify(payload));
  const aria = opts.label || `${payload.title || '지표'} 설명 보기`;
  const compactCls = opts.compact ? ' is-compact' : '';
  return `<span class="cd-infotip${compactCls}"><button type="button" class="cd-infotip-btn" aria-label="${esc(aria)}" aria-expanded="false" data-infotip="${esc(encoded)}"><span aria-hidden="true">i</span></button></span>`;
}

let wired = false;
let popoverEl = null;
let activeTrigger = null;
let pinned = false;
let closeTimer = null;

function ensurePopover() {
  if (popoverEl && popoverEl.isConnected) return popoverEl;
  if (typeof document === 'undefined' || !document.body) return null;
  let el = document.getElementById('cdInfoTipPopover');
  if (!el) {
    el = document.createElement('div');
    el.id = 'cdInfoTipPopover';
    el.className = 'cd-infotip-pop';
    el.setAttribute('role', 'tooltip');
    el.hidden = true;
    document.body.appendChild(el);
  }
  el.addEventListener('mouseenter', () => {
    clearTimeout(closeTimer);
  });
  el.addEventListener('mouseleave', () => {
    if (!pinned) scheduleClose();
  });
  popoverEl = el;
  return el;
}

function renderPopoverContent(payload) {
  const rows = [];
  if (payload.period) {
    rows.push(`<div class="cd-it-meta-row"><span class="cd-it-meta-lbl">기간</span><span>${esc(payload.period)}</span></div>`);
  }
  if (payload.compare) {
    rows.push(`<div class="cd-it-meta-row"><span class="cd-it-meta-lbl">비교 기준</span><span>${esc(payload.compare)}</span></div>`);
  }
  const bandsHtml = payload.bands && payload.bands.length
    ? `<dl class="cd-it-bands">${payload.bands.map(([k, v]) => `<div class="cd-it-band-row"><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join('')}</dl>`
    : '';
  return `
    ${payload.title ? `<div class="cd-it-title">${esc(payload.title)}</div>` : ''}
    ${payload.what ? `<p class="cd-it-what">${esc(payload.what)}</p>` : ''}
    ${rows.length ? `<div class="cd-it-meta">${rows.join('')}</div>` : ''}
    ${bandsHtml}
  `;
}

function positionPopover(trigger, pop) {
  const rect = trigger.getBoundingClientRect();
  const vw = window.innerWidth || 1024;
  const vh = window.innerHeight || 768;
  const margin = 12;

  pop.style.left = '0px';
  pop.style.top = '0px';
  pop.style.visibility = 'hidden';
  pop.hidden = false;

  const pRect = pop.getBoundingClientRect();
  const pw = pRect.width || 280;
  const ph = pRect.height || 80;

  let left = rect.left + rect.width / 2 - pw / 2;
  if (left + pw > vw - margin) left = vw - pw - margin;
  if (left < margin) left = margin;

  let top = rect.bottom + 8;
  if (top + ph > vh - margin) {
    const above = rect.top - ph - 8;
    top = above >= margin ? above : Math.max(margin, vh - ph - margin);
  }

  pop.style.left = `${Math.round(left)}px`;
  pop.style.top = `${Math.round(top)}px`;
  pop.style.visibility = 'visible';
}

function parseTriggerPayload(trigger) {
  if (!trigger) return null;
  const raw = trigger.getAttribute('data-infotip');
  if (raw) {
    try {
      return JSON.parse(decodeURIComponent(raw));
    } catch (_) {
      return null;
    }
  }
  const naReason = trigger.getAttribute('data-na-reason');
  if (naReason) {
    return { title: '자료 없음', what: naReason };
  }
  return null;
}

export function closeInfoTip() {
  clearTimeout(closeTimer);
  if (activeTrigger) {
    if (activeTrigger.hasAttribute('aria-expanded')) {
      activeTrigger.setAttribute('aria-expanded', 'false');
    }
    activeTrigger.removeAttribute('aria-describedby');
  }
  activeTrigger = null;
  pinned = false;
  if (popoverEl) {
    popoverEl.hidden = true;
    popoverEl.innerHTML = '';
  }
}

function scheduleClose(delay = 140) {
  clearTimeout(closeTimer);
  closeTimer = setTimeout(() => {
    if (!pinned) closeInfoTip();
  }, delay);
}

function openInfoTip(trigger, shouldPin = false) {
  const payload = parseTriggerPayload(trigger);
  if (!payload) return;
  const pop = ensurePopover();
  if (!pop) return;
  clearTimeout(closeTimer);

  if (activeTrigger && activeTrigger !== trigger) {
    if (activeTrigger.hasAttribute('aria-expanded')) {
      activeTrigger.setAttribute('aria-expanded', 'false');
    }
    activeTrigger.removeAttribute('aria-describedby');
  }

  activeTrigger = trigger;
  if (shouldPin) pinned = true;
  if (trigger.hasAttribute('aria-expanded')) {
    trigger.setAttribute('aria-expanded', 'true');
  }
  trigger.setAttribute('aria-describedby', pop.id);
  pop.innerHTML = renderPopoverContent(payload);
  positionPopover(trigger, pop);
}

const TRIGGER_SEL = '.cd-infotip-btn[data-infotip], [data-na-reason]';

export function wireInfoTips() {
  if (wired || typeof document === 'undefined') return;
  wired = true;

  document.addEventListener('pointerenter', (e) => {
    if (e.pointerType === 'touch') return;
    const trigger = e.target?.closest?.(TRIGGER_SEL);
    if (!trigger) return;
    openInfoTip(trigger, false);
  }, true);

  document.addEventListener('pointerleave', (e) => {
    if (e.pointerType === 'touch') return;
    const trigger = e.target?.closest?.(TRIGGER_SEL);
    if (!trigger || trigger !== activeTrigger) return;
    if (!pinned) scheduleClose();
  }, true);

  document.addEventListener('focusin', (e) => {
    const trigger = e.target?.closest?.(TRIGGER_SEL);
    if (!trigger) return;
    openInfoTip(trigger, false);
  });

  document.addEventListener('focusout', (e) => {
    const trigger = e.target?.closest?.(TRIGGER_SEL);
    if (!trigger || trigger !== activeTrigger) return;
    if (!pinned) scheduleClose(80);
  });

  document.addEventListener('click', (e) => {
    const trigger = e.target?.closest?.(TRIGGER_SEL);
    if (trigger) {
      e.preventDefault();
      e.stopPropagation();
      if (activeTrigger === trigger && pinned && popoverEl && !popoverEl.hidden) {
        closeInfoTip();
      } else {
        openInfoTip(trigger, true);
      }
      return;
    }
    if (popoverEl && !popoverEl.hidden && !popoverEl.contains(e.target)) {
      closeInfoTip();
    }
  }, true);

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && popoverEl && !popoverEl.hidden) {
      const prev = activeTrigger;
      closeInfoTip();
      if (prev && typeof prev.focus === 'function') prev.focus();
    }
  });

  window.addEventListener('scroll', () => {
    if (activeTrigger && popoverEl && !popoverEl.hidden) {
      if (!activeTrigger.isConnected) {
        closeInfoTip();
      } else {
        positionPopover(activeTrigger, popoverEl);
      }
    }
  }, true);

  window.addEventListener('resize', () => {
    if (activeTrigger && popoverEl && !popoverEl.hidden) {
      positionPopover(activeTrigger, popoverEl);
    }
  });
}

if (typeof document !== 'undefined') {
  wireInfoTips();
}
