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
  if (Number(r.pts_peer) > 0) parts.push(`동료 선정(+${fmtNum(r.pts_peer, 1)})`);
  if (Number(r.pts_dmz) > 0) parts.push(`DMZ(+${fmtNum(r.pts_dmz, 1)})`);
  if (Number(r.pts_gigs) > 0) parts.push(`1년 공연 ${r.gigs_1y}일(+${fmtNum(r.pts_gigs, 2)})`);
  if (Number(r.pts_outlets) > 0) parts.push(`매체 ${r.outlets}곳(+${fmtNum(r.pts_outlets, 1)})`);
  return parts.length ? parts.join(' · ') : '가중치 0 또는 신호 없음';
}

export function renderScoreBar(r, maxScore) {
  const denom = Math.max(1, maxScore);
  const segs = [
    { key: '갈래', v: Number(r.pts_branch) || 0, color: 'var(--seg-branch)' },
    { key: '선정 단계', v: Number(r.pts_stage) || 0, color: 'var(--seg-stage)' },
    { key: '동료 선정', v: Number(r.pts_peer) || 0, color: 'var(--seg-peer)' },
    { key: 'DMZ', v: Number(r.pts_dmz) || 0, color: 'var(--seg-dmz)' },
    { key: '1년 공연', v: Number(r.pts_gigs) || 0, color: 'var(--seg-gigs)' },
    { key: '큐레이션', v: Number(r.pts_outlets) || 0, color: 'var(--seg-outlets)' },
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

export function watchButtonHtml(teamKey, displayName, small = true) {
  const on = isWatched(teamKey);
  const cls = `btn ${small ? 'btn-sm' : ''} ${on ? 'btn-active' : ''}`.trim();
  return `<button type="button" class="${cls}" data-watch-key="${escapeHtml(teamKey)}" data-watch-name="${escapeHtml(displayName)}">${on ? '관심 중' : '관심 추가'}</button>`;
}

export function summarizeWhyTeam({ scored, profile, timeline, precedents }) {
  const name = scored?.display_name || profile?.display_name || '';
  const lines = [];

  if (scored) {
    lines.push(
      `${name}은(는) 현재 설정 기준 ${fmtNum(scored.score, 2)}점입니다 (${scorePartsLine(scored)}).`
    );
  } else {
    lines.push(`${name}은(는) 현재 필터·신호 기간 기준 점수 산정 대상 밖이지만 기록된 신호 ${timeline.length}건이 있습니다.`);
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
    return `표나 열 이름을 찾을 수 없습니다. 사용 가능한 표는 signals, teams, outcomes, programs 입니다. (${raw})`;
  }
  if (raw.includes('Binder Error')) {
    return `열 이름이나 자료형이 맞지 않습니다. (${raw})`;
  }
  return raw;
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
      ctx.font = '11px -apple-system, BlinkMacSystemFont, sans-serif';
      const padX = 4;
      const tw = ctx.measureText(lbl).width;
      const tx = chartArea.right - 4;
      const ty = Math.max(chartArea.top + 14, y - 6);
      ctx.fillStyle = opts.bgColor || '#ffffff';
      ctx.fillRect(tx - tw - padX, ty - 11, tw + padX * 2, 14);
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
        ctx.fillStyle = opts.baselineColor || '#111827';
        ctx.font = '11px -apple-system, BlinkMacSystemFont, sans-serif';
        ctx.textAlign = 'left';
        ctx.fillText(`기준선 ${opts.baseline.toFixed(1)}%`, Math.min(chartArea.right - 85, bx + 4), chartArea.top + 12);
      }
    }
    const meta = chart.getDatasetMeta(0);
    const rows = opts.rows || [];
    ctx.strokeStyle = opts.whiskerColor || '#525866';
    ctx.lineWidth = 1.4;
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
