"""무대·라이브 세션 채널 출연 평가 → docs/live_sessions.md (계산만 — config·features.sql·랩 데이터는 바꾸지 않음)

config/video_channels.json 채널(EBS 스페이스 공감·딩고·it's Live·KBS Kpop·목캔디·난장 …)의 무대 영상(docs/lab/data/videos.csv,
kind=stage)은 지금 signals 에 들어가지 않는다. 그래서 '출연'을 임시 '큐레이션' 신호(출처 video_<채널>)로 만들어 메모리 안의
DuckDB 에만 더한 뒤, 출처 성적표(source_scorecard.sql)·데뷔 코호트(source_scorecard_debut.sql)·점수 v2 AUC 를 같은 계산식으로 잰다.

- 날짜 = 영상 업로드일(실제 출연·녹화일보다 늦을 수 있음 → '먼저 짚었다'를 덜 세는 쪽).
- 같은 집안: EBS 스페이스 공감 ↔ EBS 헬로루키(월간·올해의) — 정답 발표 전에 그 채널에 나온 팀의 헬로루키 정답은 적중으로 세지 않음.
- ⚠️ 지금 모은 무대 영상은 모두 2025-10 이후 업로드라, 점수 검증 기준일(2023-01-01 ~ 2025-07-01) 전에 신호가 하나도 없다.
  그래서 6개 기준일 교차 검증은 영향이 0일 수밖에 없고, 기준일 2026-01-01 하나로 '미리 보기'만 한다(교차 검증 아님).

실행: .venv/bin/python scripts/live_sessions.py [--data-dir 폴더] [--out 문서]
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lab_sql  # noqa: E402

OUT = lab_sql.ROOT / "docs" / "live_sessions.md"
CHANNELS = {   # videos.csv channel_title → 임시 출처 키
    "스페이스 공감": "video_ebs_space", "it's Live": "video_its_live", "딩고 뮤직 / dingo music": "video_dingo",
    "목캔디의 인디밴드 라이브": "video_mokcandy", "KBS Kpop": "video_kbs_kpop", "문화콘서트난장 Real K-Music": "video_nanjang",
    "ONSTAGE 온스테이지": "video_onstage", "온스테이지 ONSTAGE": "video_onstage", "Tiny Desk Korea": "video_tinydesk_kr",
}
LABELS = {"video_ebs_space": "EBS 스페이스 공감", "video_its_live": "it's Live", "video_dingo": "딩고 뮤직",
          "video_mokcandy": "목캔디의 인디밴드 라이브", "video_kbs_kpop": "KBS Kpop (스케치북·더 시즌즈)",
          "video_nanjang": "문화콘서트 난장", "video_onstage": "온스테이지", "video_tinydesk_kr": "Tiny Desk Korea"}
SAME_HOUSE = {"video_ebs_space": {"hello_rookie", "hello_rookie_year"}}   # 같은 방송사(EBS) — 스페이스 공감 ↔ 헬로루키
BACKTEST_LAST_CUTOFF = "2025-07-01"
EARLY_CUTOFF = "2026-01-01"
EARLY_HORIZON = 11            # 2026-01-01 → 데이터 끝(2026-11)까지


KEYWORDS = (("온스테이지", "video_onstage"), ("onstage", "video_onstage"), ("스페이스 공감", "video_ebs_space"),
            ("dingo", "video_dingo"), ("딩고", "video_dingo"), ("it's live", "video_its_live"), ("목캔디", "video_mokcandy"),
            ("난장", "video_nanjang"), ("tiny desk", "video_tinydesk_kr"), ("kbs kpop", "video_kbs_kpop"))


def channel_source(title: str) -> Optional[str]:
    """채널 이름 → 임시 출처 키. 정확히 같은 이름이 없으면 낱말로(백필로 들어올 채널의 API 이름을 미리 모름)."""
    if title in CHANNELS:
        return CHANNELS[title]
    low = (title or "").lower()
    return next((src for kw, src in KEYWORDS if kw in low), None)


def src_key(source: str) -> str:
    return f"큐레이션:{source}"


def video_signal_rows(videos: Iterable[dict], role: str = "discovery") -> List[dict]:
    """무대 영상(kind=stage, 알려진 채널) → 임시 신호 (같은 팀·채널·날짜는 한 줄)."""
    seen, out = set(), []
    for v in videos:
        src = channel_source(v.get("channel_title", ""))
        if v.get("kind") != "stage" or not src or not v.get("published_at"):
            continue
        key = (v["team_key"], src, v["published_at"][:10])
        if key in seen:
            continue
        seen.add(key)
        out.append({"team_key": key[0], "branch": "큐레이션", "source": src, "program": src, "stage_rank": None,
                    "signal_date": key[2], "venue": "", "role": role})
    return out


def same_house_tags(outcomes: Iterable[dict], signals: Sequence[dict]) -> Set[Tuple[str, str, date]]:
    """같은 집안 짝 채널에 정답 발표 '전에' 나온 팀의 짝 정답 → (팀, 프로그램, 발표일)."""
    first: Dict[Tuple[str, str], date] = {}
    for s in signals:
        if s["source"] in SAME_HOUSE:
            d = date.fromisoformat(s["signal_date"])
            k = (s["team_key"], s["source"])
            first[k] = min(first.get(k, d), d)
    tags = set()
    for o in outcomes:
        for src, programs in SAME_HOUSE.items():
            d0 = first.get((o["team_key"], src))
            if o["program"] in programs and d0 and d0 < o["announced_date"]:
                tags.add((o["team_key"], o["program"], o["announced_date"]))
    return tags


def channel_coverage(videos: Iterable[dict]) -> List[dict]:
    agg: Dict[str, dict] = defaultdict(lambda: {"videos": 0, "teams": set(), "dates": []})
    for v in videos:
        src = channel_source(v.get("channel_title", ""))
        if v.get("kind") == "stage" and src:
            a = agg[src]
            a["videos"] += 1
            a["teams"].add(v["team_key"])
            a["dates"].append(v["published_at"][:10])
    return [{"source": s, "videos": a["videos"], "teams": len(a["teams"]), "first": min(a["dates"]), "last": max(a["dates"])}
            for s, a in sorted(agg.items(), key=lambda kv: -kv[1]["videos"])]


# ---------- DuckDB (메모리 안에서만) ----------

def load_videos(data_dir: Path) -> List[dict]:
    with open(data_dir / "videos.csv", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def add_video_signals(con, rows: Sequence[dict]) -> int:
    """메모리 DuckDB 의 signals 에 임시 행을 더하고, 같은 집안 정답에 표시한다 (파일은 안 건드림)."""
    con.executemany("INSERT INTO signals (team_key, branch, source, program, stage_rank, signal_date, venue, role) "
                    "VALUES (?, ?, ?, ?, ?, CAST(? AS DATE), ?, ?)",
                    [(r["team_key"], r["branch"], r["source"], r["program"], r["stage_rank"], r["signal_date"], r["venue"],
                      r["role"]) for r in rows])
    outs = [{"team_key": t, "program": p, "announced_date": d} for t, p, d in
            con.execute("SELECT team_key, program, CAST(announced_date AS DATE) FROM outcomes WHERE announced_date IS NOT NULL").fetchall()]
    for t, p, d in same_house_tags(outs, rows):
        src = next(s for s, ps in SAME_HOUSE.items() if p in ps)
        con.execute("UPDATE outcomes SET same_house_sources = CASE WHEN COALESCE(same_house_sources, '') = '' THEN ? "
                    "ELSE same_house_sources || ';' || ? END, same_house_scored = true "
                    "WHERE team_key = ? AND program = ? AND CAST(announced_date AS DATE) = ?",
                    [src_key(src), src_key(src), t, p, d])
    return len(rows)


def early_scorecard(con) -> List[dict]:
    return lab_sql.query(con, "source_scorecard.sql", cutoffs=f"(DATE '{EARLY_CUTOFF}')",
                         horizon_months=str(EARLY_HORIZON), since=f"'{EARLY_CUTOFF}'")


def early_debut(con) -> List[dict]:
    return lab_sql.query(con, "source_scorecard_debut.sql", cutoffs=f"(DATE '{EARLY_CUTOFF}')",
                         mention_months="6", horizon_months=str(EARLY_HORIZON))


def early_auc(con) -> dict:
    import score_tune as st
    w2 = {k: float(lab_sql.DEFAULTS[k]) for k, _ in st.V0_WEIGHTS}
    data = {EARLY_CUTOFF: st.features(con, EARLY_CUTOFF)}
    return st.evaluate(data, w2)[EARLY_CUTOFF]


def signals_before(con, cutoff: str) -> int:
    return con.execute("SELECT COUNT(*) FROM signals WHERE source LIKE 'video_%' AND signal_date < CAST(? AS DATE)",
                       [cutoff]).fetchone()[0]


# ---------- 문서 ----------

def _f(v, nd=3) -> str:
    return "—" if v is None else (f"{v:.{nd}f}" if isinstance(v, float) else str(v))


def suggest(row: Optional[dict], cov: dict) -> Tuple[str, str]:
    """역할 제안 — 기록이 짧아 성적 판단 전이면 검증 대기(source_roles 규칙: 첫 기록이 가장 늦은 기준일보다 뒤)."""
    if cov["first"] > BACKTEST_LAST_CUTOFF:
        why = f"첫 업로드 {cov['first']} — 점수 검증 기준일(마지막 {BACKTEST_LAST_CUTOFF})보다 뒤라 성적을 잴 수 없음"
        if row and row.get("teams") and (row.get("lift") or 0) >= 1.5:
            why += f"; 2026-01-01 미리 보기에서는 배수 {row['lift']} (표본 작음)"
        return "pending (검증 대기)", why
    return "판정 필요", "기록이 기준일보다 앞섬 — 출처 성적표로 판정"


def render(cov: List[dict], sc: List[dict], debut: List[dict], auc_base: dict, auc_video: dict,
           n_rows: int, before_bt: int, sh_tags: int) -> str:
    sc_by = {r["src"]: r for r in sc}
    deb_by = {r.get("src"): r for r in debut}
    base_rate = next((r["base_rate"] for r in sc if r.get("base_rate") is not None), None)
    lines = ["# 무대·라이브 세션 채널 출연 — 나중 정답을 미리 알려 주나", "",
             "_자동 생성: `.venv/bin/python scripts/live_sessions.py` (계산만 — config·계산식·랩 데이터는 바꾸지 않음)_", "",
             "## 1. 지금 상태", "",
             f"- 무대 영상(`docs/lab/data/videos.csv`, kind=stage)은 **지금 signals에 들어가지 않습니다.** 앱에서 팀 상세의 영상으로만 보입니다. "
             f"그래서 '출연'을 **임시 큐레이션 신호**(출처 `video_<채널>`, 날짜 = 업로드일)로 만들어 메모리 안에서만 더했습니다 — {n_rows:,}행(같은 팀·채널·날짜는 한 줄).",
             "- 업로드일은 실제 출연·녹화일보다 늦을 수 있어, '정답보다 먼저 짚었다'를 덜 세는(보수적인) 쪽입니다.",
             f"- 같은 집안: EBS 스페이스 공감 ↔ EBS 헬로루키(월간·올해의). 정답 발표 전에 스페이스 공감에 나온 팀의 헬로루키 정답 {sh_tags}건을 적중에서 뺐습니다.",
             f"- ⚠️ **모든 무대 영상이 2025-10 이후 업로드입니다**(수집기가 최근 업로드만 훑음). 점수 검증 기준일(2023-01-01 ~ {BACKTEST_LAST_CUTOFF}) "
             f"전에 영상 신호가 **{before_bt}건**이라, 6개 기준일 교차 검증에는 영향이 0입니다. 더해도 숫자가 그대로인 것은 '효과 없음'이 아니라 '잴 수 없음'입니다.", "",
             "## 2. 채널별 수집 범위", "",
             "| 채널 | 무대 영상 | 팀 | 첫 업로드 | 마지막 업로드 |", "|---|---|---|---|---|"]
    for c in cov:
        lines.append(f"| {LABELS.get(c['source'], c['source'])} | {c['videos']:,} | {c['teams']:,} | {c['first']} | {c['last']} |")
    lines += ["", f"## 3. 미리 보기 — 기준일 {EARLY_CUTOFF} 하나 (교차 검증 아님)", "",
              f"기준일 전 3년 신호(영상은 2025-10-23 ~ 2025-12-31 업로드분)로 후보를 잡고, 기준일 뒤 {EARLY_HORIZON}개월(2026년 정답) 안에 정답을 받았는지 "
              "[출처 성적표](source_roles.md)와 같은 계산식(`source_scorecard.sql`)으로 쟀습니다. 비교를 위해 기존 주요 출처도 같은 기준일로 함께 적습니다.", "",
              f"기준선(후보 전체 적중률): {_f(base_rate, 2)}%", "",
              "| 출처 | 후보 팀 | 적중 | 적중률 | 배수 | 먼저 잡은 수상 팀 (가장 먼저 / 유일) | 선행 개월 | 데뷔 코호트 언급 팀 (적중) |",
              "|---|---|---|---|---|---|---|---|"]
    show = [src_key(c["source"]) for c in cov] + ["공연:indistreet", "공연:sangsangmadang", "큐레이션:musicy", "큐레이션:izm", "큐레이션:visla"]
    for s in show:
        r = sc_by.get(s, {})
        d = deb_by.get(s, {})
        name = LABELS.get(s.split(":", 1)[1], s)
        deb = f"{d.get('mentioned', d.get('teams', '—'))} ({d.get('hits', '—')})" if d else "—"
        lines.append(f"| {name} | {r.get('teams', 0)} | {r.get('hits', 0)} | {_f(r.get('rate'), 2)} | {_f(r.get('lift'), 1)} | "
                     f"{r.get('winners_seen', 0)} ({r.get('first_to_see', 0)} / {r.get('only_source', 0)}) | {_f(r.get('median_lead_months'), 1)} | {deb} |")
    lines += ["", "- 기준일이 하나뿐이고 영상 기간이 두 달 남짓이라 **표본이 아주 작습니다** — 방향만 보는 숫자입니다.",
              "- '먼저 잡은 수상 팀'은 2026-01-01 이후 첫 정답을 받은 팀 중 정답 전에 그 출처에 나온 팀(가장 먼저·유일)입니다.", "",
              f"**점수 v2에 더했을 때 (기준일 {EARLY_CUTOFF}, 영상 출연을 발굴 큐레이션 신호로 흉내)**: 등급 가중 AUC {_f(auc_base['auc'])} → {_f(auc_video['auc'])}, "
              f"상위 20 적중 {auc_base['hits20']} → {auc_video['hits20']}, 상위 50 적중 {auc_base['hits50']} → {auc_video['hits50']} "
              f"(후보 {auc_base['n']:,}팀 · 정답 {auc_base['pos']}팀). 6개 기준일 교차 검증(`score_tune`)은 1절 이유로 그대로입니다.", ""]
    vids = [sc_by.get(src_key(c["source"]), {}) for c in cov]
    seen, first = sum(r.get("winners_seen", 0) or 0 for r in vids), sum(r.get("first_to_see", 0) or 0 for r in vids)
    lines += [f"**읽는 법:** 영상 채널들은 2026년 정답 팀을 정답 전에 모두 {seen}번 다뤘지만 그중 '가장 먼저' 짚은 것은 {first}번입니다 — "
              "대부분 공연·매체 같은 다른 출처가 먼저 짚은 뒤 출연했습니다(무대 영상은 어느 정도 알려진 뒤 섭외되는 경우가 많음). "
              f"점수에 더하면 AUC는 {'내려가고' if (auc_video['auc'] or 0) < (auc_base['auc'] or 0) else '오르고'} 상위 적중은 "
              f"{auc_video['hits50'] - auc_base['hits50']:+d}팀이라, 지금 숫자로는 '발굴' 근거가 없습니다(표본 작음).", ""]
    lines += ["## 4. 채널별 역할 제안", "",
              "| 채널 | 제안 | 근거 |", "|---|---|---|"]
    for c in cov:
        role, why = suggest(sc_by.get(src_key(c["source"])), c)
        extra = " · 같은 집안(헬로루키) 짝으로 등록 필요" if c["source"] in SAME_HOUSE else ""
        if c["source"] == "video_kbs_kpop":
            extra += " · 대부분 아이돌 무대라 인디 신인 발굴보다 '이미 알려진 팀' 맥락에 가까울 것으로 예상(재평가 때 확인)"
        lines.append(f"| {LABELS.get(c['source'], c['source'])} | {role} | {why}{extra} |")
    lines += ["", "## 5. 요청 (코디네이터)", "",
              "1. `config/source_roles.json` signals에 영상 출처를 **pending**으로 등록할지 결정 — 지금은 signals에 안 들어가므로, "
              "넣으려면 `export_lab_data`가 무대 영상을 `큐레이션:video_<채널>` 신호로 내보내야 합니다(같은 집안 짝 `큐레이션:video_ebs_space` ↔ hello_rookie·hello_rookie_year 추가).",
              "2. **과거 업로드 백필**: 수집기의 채널별 `max_pages`를 늘려 2021~2025 업로드를 모으면(업로드 목록 50개당 API 1단위라 비용이 작음) "
              "6개 기준일로 바로 성적을 잴 수 있습니다. 이번 평가에서 가장 큰 한계입니다.",
              "3. 그 전까지는 점수에 넣지 않고(features.sql 변경 없음), 팀 상세의 '무대 영상' 정보로만 씁니다.", "",
              "## 6. 한계", "",
              "- 영상은 우리 팀 목록의 이름과 맞는 것만 모았습니다(수집기가 우리 팀 이름으로 제목을 맞춤). 그래서 우리 데이터에 없는 팀의 출연은 처음부터 빠집니다.",
              "- 업로드일 ≠ 출연일, 한 팀이 여러 번 출연하면 신호도 여러 번입니다(출처 성적표는 팀 단위라 영향 작음).",
              "- KBS Kpop은 업로드가 아주 많은 채널이라 일부(최근 쪽)만 훑었습니다."]
    return "\n".join(lines) + "\n"


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="무대·라이브 세션 채널 출연 평가 → docs/live_sessions.md")
    ap.add_argument("--data-dir", type=Path, default=lab_sql.DATA_DIR)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)
    videos = load_videos(args.data_dir)
    rows = video_signal_rows(videos, role="discovery")
    base = lab_sql.connect(args.data_dir)
    auc_base = early_auc(base)
    con = lab_sql.connect(args.data_dir)
    n = add_video_signals(con, rows)
    sh = con.execute("SELECT COUNT(*) FROM outcomes WHERE same_house_sources LIKE '%video_ebs_space%'").fetchone()[0]
    text = render(channel_coverage(videos), early_scorecard(con), early_debut(con), auc_base, early_auc(con), n,
                  signals_before(con, BACKTEST_LAST_CUTOFF), sh)
    args.out.write_text(text, encoding="utf-8")
    print(f"✅ → {args.out} (영상 신호 {n:,}행, 기준일 전 {signals_before(con, BACKTEST_LAST_CUTOFF)}건)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
