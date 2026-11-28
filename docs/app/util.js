/**
 * 의존성 없는 공용 순수 유틸 — DOM·appState를 불러오지 않아 Node 단위 테스트에서도 안전하게 import 가능.
 * ui.js에서도 다시 export 한다.
 */

export function escapeHtml(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/** 빈 값(null/undefined/'') 또는 유한하지 않은 값은 null, 그 외는 유한 숫자로 변환. */
export function toNumOrNull(v) {
  if (v === null || v === undefined || v === '') return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

/** 기준 날짜('YYYY-MM-DD' 또는 'YYYY-MM')까지 최근 n개월의 'YYYY-MM' 배열을 오래된 순으로 반환. */
export function recentMonths(endDateOrYm, n = 12) {
  const [ey, em] = String(endDateOrYm || '').split('-').map(Number);
  if (!Number.isFinite(ey) || !Number.isFinite(em) || em < 1 || em > 12) return [];
  const out = [];
  for (let i = n - 1; i >= 0; i--) {
    const d = new Date(Date.UTC(ey, em - 1 - i, 1));
    out.push(`${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}`);
  }
  return out;
}

/** 앱 공용 토스트 이벤트 발송 (app.js 리스너가 화면에 표시). */
export function emitToast(msg) {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent('app:toast', { detail: msg }));
}

/** Blob을 브라우저 파일 다운로드로 저장하고 임시 URL을 정리한다. */
export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
