"""스포티파이 하루 요청 예산 공유 + 429 뒤 그날 쉬기 → data/raw/state/spotify_budget.json (비공개)

같은 날 스포티파이를 쓰는 단계(collect_spotify·collect_spotify_collabs·collect_artist_images)가 요청 수를 함께 센다.
- 하루 총 요청이 DAILY_BUDGET 에 닿으면 남은 단계는 요청을 보내기 전에 멈춘다 (DailyBudgetExhausted).
- 오래 기다리라는 429(Retry-After > collect_spotify.MAX_RETRY_AFTER_SEC)를 받으면, 그 시간과 그날 끝 중 늦은 때까지
  '막힘'으로 적고 그동안 남은 단계는 요청을 하나도 보내지 않는다 (SpotifyBlocked). 우회(다른 키·주소)는 하지 않는다 — 약관.
두 예외 모두 collect_spotify.RateLimited 를 이어받아, 각 수집기의 기존 '멈추고 받은 데까지 저장' 처리가 그대로 작동한다.

쓰는 법: http = BudgetedHttp(collect_spotify.urllib_http) → SpotifyClient(..., http=http)
        단계 시작 전에 skip_message() 가 문자열이면 그 단계를 건너뛴다.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

import collect_spotify as cs

STATE = cs.RAW_DIR / "state" / "spotify_budget.json"
DAILY_BUDGET = 2500          # 하루 총 요청 상한 (세 단계 합) — 2026-11-27 협업 396번 + 발매 이력으로 429 → 여유 있게


class SpotifyBlocked(cs.RateLimited):
    pass


class DailyBudgetExhausted(cs.RateLimited):
    pass


def _now() -> datetime:
    return datetime.now(cs.KST)


def load(path: Path, today: str) -> dict:
    try:
        st = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        st = {}
    if st.get("date") != today:                      # 날이 바뀌면 사용량만 0으로 (막힘은 그 시각까지 유지)
        st = {"date": today, "used": 0, "blocked_until": st.get("blocked_until", ""), "reason": st.get("reason", "")}
    return st


def _save(path: Path, st: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")


def _blocked(st: dict, now: datetime) -> Optional[str]:
    until = st.get("blocked_until") or ""
    if until and now < datetime.fromisoformat(until):
        return f"스포티파이 쉼: {until[:16].replace('T', ' ')}까지 ({st.get('reason', '429')})"
    return None


def skip_message(path: Path = STATE, now: Optional[datetime] = None) -> Optional[str]:
    """단계 시작 전 확인: 막혀 있으면 '건너뜀' 문장, 아니면 None."""
    now = now or _now()
    msg = _blocked(load(path, now.date().isoformat()), now)
    return f"⏭ {msg} → 이 단계 건너뜀 (요청 안 보냄)" if msg else None


def _header(headers, name):
    return next((v for k, v in (headers or {}).items() if k.lower() == name.lower()), None)


class BudgetedHttp:
    """http 함수를 감싸 하루 예산을 세고, 오래 기다리라는 429를 받으면 막힘을 기록한다."""

    def __init__(self, http, path: Path = STATE, budget: int = DAILY_BUDGET, now: Callable[[], datetime] = _now):
        self._http, self._path, self._budget, self._now = http, path, budget, now

    def __call__(self, method, url, headers=None, data=None):
        now = self._now()
        st = load(self._path, now.date().isoformat())
        msg = _blocked(st, now)
        if msg:
            raise SpotifyBlocked(msg)
        if st["used"] >= self._budget:
            raise DailyBudgetExhausted(f"스포티파이 하루 요청 예산 {self._budget}번을 다 씀 (내일 이어서)")
        status, resp_headers, body = self._http(method, url, headers, data)
        st["used"] += 1
        if status == 429:
            wait = int(_header(resp_headers, "Retry-After") or 0)
            if wait > cs.MAX_RETRY_AFTER_SEC:
                end_of_day = datetime.combine(now.date() + timedelta(days=1), datetime.min.time(), tzinfo=now.tzinfo)
                st["blocked_until"] = max(now + timedelta(seconds=wait), end_of_day).isoformat(timespec="seconds")
                st["reason"] = f"429, {wait}초 뒤에 다시 하라고 함"
        _save(self._path, st)
        return status, resp_headers, body
