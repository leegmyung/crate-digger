/**
 * 화면 아래 고정 미니 플레이어 — 어느 화면에서든 '▶ 듣기'(data-play-team)를 누르면 여기서 재생.
 * #viewRoot 바깥(body 끝)에 한 번만 만들기 때문에 다른 페이지로 옮겨도 소리가 이어진다 (Chartmetric·스트리밍 서비스처럼).
 * 무엇을 틀지는 player_pick.js (players.csv → 스포티파이 아티스트 → 무대 영상).
 */
import { appState } from '../state.js';
import { ensureVideosLoaded } from '../db.js';
import { embedSrc, playOptionsFor } from '../player_pick.js';
import {
  avatarHtml, escapeHtml, playButtonHtml, spotifyIdOf, swapAvatarToInitial, wireAvatarFallbacks,
} from '../ui.js';

const MAX_TABS = 4;
const KIND_LABEL = { spotify: '스포티파이', youtube: '유튜브' };
const TYPE_LABEL = { artist: '인기곡', track: '대표곡', album: '앨범', playlist: '재생 목록', video: '영상' };

let host = null;
let current = null;   // { teamKey, name, options, index, expanded }
let markRaf = 0;
let slotFillQueued = false;
const IDLE_FILL_MS = 2500;

function optionsFor(teamKey) {
  return playOptionsFor({
    players: appState.playersByTeam?.get(teamKey) || [],
    spotifyArtistId: spotifyIdOf(teamKey),
    videos: appState.videosByTeam?.get(teamKey) || [],
  });
}

function tabLabel(opt, all) {
  const sameKind = all.filter(o => o.kind === opt.kind && o.type === opt.type);
  const n = sameKind.length > 1 ? ` ${sameKind.indexOf(opt) + 1}` : '';
  return `${KIND_LABEL[opt.kind] || opt.kind} ${TYPE_LABEL[opt.type] || ''}${n}`.trim();
}

function frameHtml(opt) {
  const src = embedSrc(opt, { autoplay: true });
  if (!src) return '<p class="mp-empty">재생할 수 없는 항목입니다.</p>';
  const cls = opt.kind === 'youtube' ? 'mp-frame mp-frame-video' : 'mp-frame mp-frame-audio';
  return `<iframe class="${cls}" src="${escapeHtml(src)}" title="${escapeHtml(`${current.name} ${KIND_LABEL[opt.kind] || ''} 플레이어`)}"
    allow="autoplay; clipboard-write; encrypted-media; fullscreen; picture-in-picture" allowfullscreen referrerpolicy="strict-origin-when-cross-origin"></iframe>`;
}

function render() {
  if (!host) return;
  if (!current) {
    host.hidden = true;
    host.innerHTML = '';
    document.body.classList.remove('has-mini-player');
    scheduleMark();
    return;
  }
  const { teamKey, name, options, index, expanded } = current;
  const opt = options[index];
  const tabs = options.slice(0, MAX_TABS);
  const sub = opt
    ? [tabLabel(opt, options), opt.title && opt.title !== '인기곡' ? opt.title : ''].filter(Boolean).join(' · ')
    : '들을 거리를 찾는 중…';
  host.hidden = false;
  host.classList.toggle('is-expanded', Boolean(expanded && opt?.kind === 'youtube'));
  host.innerHTML = `
    <div class="mp-inner">
      <a class="mp-team" href="#/team/${encodeURIComponent(teamKey)}" title="${escapeHtml(name)} 팀 페이지로">
        ${avatarHtml(teamKey, name, 40, { shape: 'rounded' })}
        <span class="mp-text">
          <strong class="mp-name">${escapeHtml(name)}</strong>
          <span class="mp-sub">${escapeHtml(sub)}</span>
        </span>
      </a>
      <div class="mp-stage">${opt ? frameHtml(opt) : ''}</div>
      <div class="mp-side">
        ${tabs.length > 1 ? `<div class="mp-tabs" role="group" aria-label="다른 곡·영상">
          ${tabs.map((o, i) => `<button type="button" class="mp-tab${i === index ? ' is-active' : ''}" data-mp-index="${i}" aria-pressed="${i === index}">${escapeHtml(tabLabel(o, options))}</button>`).join('')}
        </div>` : ''}
        <div class="mp-ctrl">
          ${opt?.kind === 'youtube' ? `<button type="button" class="btn btn-sm mp-expand" data-mp-expand aria-pressed="${Boolean(expanded)}">${expanded ? '작게' : '크게'}</button>` : ''}
          <button type="button" class="btn btn-sm mp-close" data-mp-close aria-label="플레이어 닫기">닫기</button>
        </div>
      </div>
    </div>`;
  document.body.classList.add('has-mini-player');
  wireAvatarFallbacks(host);
  scheduleMark();
}

/** 지금 재생 중인 팀의 '▶ 듣기' 버튼을 ■ 로 바꿔 보여 준다 (화면이 새로 그려져도). */
function markButtons() {
  markRaf = 0;
  const playing = current?.teamKey || '';
  document.querySelectorAll('[data-play-team]').forEach(btn => {
    const on = btn.dataset.playTeam === playing;
    if (btn.classList.contains('is-playing') === on) return;
    btn.classList.toggle('is-playing', on);
    btn.setAttribute('aria-pressed', String(on));
    const icon = btn.querySelector('[aria-hidden="true"]');
    if (icon) icon.textContent = on ? '■' : '▶';
  });
}

function scheduleMark() {
  if (!markRaf) markRaf = requestAnimationFrame(markButtons);
}

function toast(msg) {
  window.dispatchEvent(new CustomEvent('app:toast', { detail: msg }));
}

/**
 * 팀 하나를 재생. 같은 팀을 다시 누르면 닫는다.
 * @param {string} teamKey
 * @param {string} [name]
 */
export async function playTeam(teamKey, name = '') {
  if (!teamKey) return;
  if (current?.teamKey === teamKey) {
    closePlayer();
    return;
  }
  current = { teamKey, name: name || teamKey, options: optionsFor(teamKey), index: 0, expanded: false };
  render();
  // 무대 영상 표를 아직 안 받았으면 받아서 고를 거리를 늘린다 (재생 중인 것은 그대로)
  await ensureVideosLoaded().catch(() => null);
  if (current?.teamKey !== teamKey) return;
  const more = optionsFor(teamKey);
  if (!more.length) {
    current = null;
    render();
    toast('이 팀은 아직 바로 들을 거리가 없어요');
    return;
  }
  if (more.length === current.options.length) return;
  const keepId = current.options[current.index]?.id;
  const keepIndex = keepId ? Math.max(0, more.findIndex(o => o.id === keepId)) : 0;
  current = { ...current, options: more, index: keepIndex };
  render();
}

export function closePlayer() {
  current = null;
  render();
}

function onDocClick(e) {
  const btn = e.target.closest?.('[data-play-team]');
  if (btn) {
    // 표 행·카드의 '눌러서 이동'보다 먼저 받는다
    e.preventDefault();
    e.stopPropagation();
    playTeam(btn.dataset.playTeam, btn.dataset.playName || '');
    return;
  }
  if (!host || !current || !host.contains(e.target)) return;
  const tab = e.target.closest('[data-mp-index]');
  if (tab) {
    const i = Number(tab.dataset.mpIndex);
    if (Number.isInteger(i) && i !== current.index && current.options[i]) {
      current = { ...current, index: i };
      render();
    }
    return;
  }
  if (e.target.closest('[data-mp-expand]')) {
    current = { ...current, expanded: !current.expanded };
    render();
    return;
  }
  if (e.target.closest('[data-mp-close]')) closePlayer();
}

/** 영상 표를 받은 뒤: 자리만 잡아 둔 곳을 '▶ 듣기' 버튼으로 바꾸거나(들을 거리 있음) 지운다. */
function fillPlaySlots() {
  document.querySelectorAll('[data-play-slot]').forEach(slot => {
    const html = playButtonHtml(slot.dataset.playSlot, slot.dataset.playName || '', { variant: slot.dataset.playVariant || 'sm' });
    if (html) slot.insertAdjacentHTML('afterend', html);
    slot.remove();
  });
  scheduleMark();
}

/** 화면에 빈 자리가 있으면, 화면을 다 그린 뒤 한가할 때 영상 표를 받아 채운다 (첫 화면 속도는 그대로). */
function scheduleSlotFill() {
  if (appState.videosLoaded) {
    if (document.querySelector('[data-play-slot]')) fillPlaySlots();
    return;
  }
  if (slotFillQueued || !document.querySelector('[data-play-slot]')) return;
  slotFillQueued = true;
  const run = () => ensureVideosLoaded().catch(() => null).finally(() => { slotFillQueued = false; });
  if (typeof requestIdleCallback === 'function') requestIdleCallback(run, { timeout: IDLE_FILL_MS });
  else setTimeout(run, IDLE_FILL_MS);
}

/** 한 번만 부른다 (app.js boot). */
export function initMiniPlayer() {
  if (host) return;
  host = document.createElement('section');
  host.id = 'miniPlayer';
  host.className = 'mini-player';
  host.setAttribute('aria-label', '바로 듣기 플레이어');
  host.hidden = true;
  document.body.appendChild(host);
  window.addEventListener('app:videos-loaded', fillPlaySlots);
  document.addEventListener('click', onDocClick, true);
  // 어느 화면이든 팀 사진 주소가 깨지면 머리글자로 (오류 이벤트는 위로 안 올라오므로 capture 로 받음)
  document.addEventListener('error', (e) => {
    const t = e.target;
    if (t instanceof HTMLImageElement && t.classList.contains('avatar')) swapAvatarToInitial(t);
  }, true);
  const root = document.getElementById('viewRoot');
  if (root && typeof MutationObserver !== 'undefined') {
    new MutationObserver(() => {
      if (current) scheduleMark();
      scheduleSlotFill();
    }).observe(root, { childList: true, subtree: true });
  }
}
