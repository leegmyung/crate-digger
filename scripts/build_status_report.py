"""진행 점검표 자동 생성 → docs/status_report.html (정적 한 장, 스크립트 없음, 화이트/다크 자동)

    python3 scripts/build_status_report.py

공개 파일만 읽는다(비공개 records·data/raw 안 봄): docs/data/collect.json, docs/data/source_review.json,
docs/lab/data/(meta.json·signals·teams·outcomes·links·videos·images·snapshots/index.json), docs/sql/README.md,
docs/score_tuning.md, docs/artist_xref.md, config/source_roles.json, docs/log/*.md.
숫자는 모두 이 파일들에서 계산하거나 그대로 옮긴다. 문서 형식이 바뀌어 읽지 못하면 '확인 필요'로 표시한다.
"""
from __future__ import annotations

import csv
import html
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "status_report.html"
STALE_DAYS = 2            # 마지막 성공이 이틀보다 오래되면 '오래됨' (매일 21시 실행이 하루 빠져도 경고는 다음 날부터)
# '급감' 판정은 앱(docs/app/db.js isRunDropped)과 같은 규칙: 매일 전체를 다시 받는 표만, 직전 20행 이상인데 30% 미만으로 줄면
DROP_TABLES = {"raw_kr_gig", "raw_press", "raw_kr_release"}   # 증분·수동 표(프로필·정답 등)는 줄어도 정상이라 제외
DROP_MIN_PREV = 20
DROP_RATIO = 0.3
PENDING_REVIEW_DAYS = 90  # 검증 대기 출처는 기록 시작 90일 뒤 재평가 (scripts/source_review.py 와 같은 기준)
LOG_DAYS = 7
REPO_BLOB = "https://github.com/leegmyung/crate-digger/blob/main/"
STATE_KO = {"ok": "정상", "warn": "주의", "bad": "이상", "check": "확인 필요"}


# ---------- 읽기 ----------

def _json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _csv(path: Path) -> List[dict]:
    try:
        with open(path, encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except OSError:
        return []


def _text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def parse_auc(text: str) -> Optional[Dict[str, str]]:
    m = re.search(r"평균 AUC[^\n]*?고른 가중치 ([0-9.]+) · v0 ([0-9.]+) · 공연 수만 ([0-9.]+)", text)
    return {"v2": m.group(1), "v0": m.group(2), "gigs": m.group(3)} if m else None


def parse_link_rate(text: str) -> Optional[dict]:
    m = re.search(r"정답 팀 중 신호[^|]*\|\s*([0-9,]+) / ([0-9,]+)팀 \(([0-9.]+)%\)", text)
    if not m:
        return None
    return {"linked": int(m.group(1).replace(",", "")), "total": int(m.group(2).replace(",", "")), "pct": m.group(3)}


def _days_since(day: str, today: str) -> Optional[int]:
    try:
        return (date.fromisoformat(today) - date.fromisoformat(day[:10])).days
    except ValueError:
        return None


def _stage(name: str, state: str, last: str = "", detail: str = "") -> dict:
    return {"name": name, "state": state, "last": last, "detail": detail}


def _stale(state: str, last: str, today: str) -> str:
    days = _days_since(last, today) if last else None
    if days is None:
        return "check"
    return "bad" if days > STALE_DAYS else state


# ---------- 단계별 상태 ----------

def _collect_stages(collect: Optional[dict], today: str) -> List[dict]:
    runs = (collect or {}).get("runs") or []
    good = [r for r in runs if (r.get("rows") or 0) > 0]
    if not good:
        return [_stage("수집", "check", detail="수집 기록 없음"), _stage("형식 검사", "check", detail="수집 기록 없음")]
    last = max(r["date"] for r in good)
    todays = [r for r in runs if r.get("date") == last]
    drops = [f"{r['source']} {r['prev_rows']}→{r['rows']}" for r in todays
             if r.get("table") in DROP_TABLES and (r.get("prev_rows") or 0) >= DROP_MIN_PREV
             and (r.get("rows") or 0) < r["prev_rows"] * DROP_RATIO]
    detail = f"{last} 수집 {len(todays)}건 · {sum(r.get('rows') or 0 for r in todays):,}행"
    if drops:
        detail += " · 급감: " + ", ".join(drops)
    collect_state = _stale("warn" if drops else "ok", last, today)
    ok = sum(1 for r in todays if r.get("file_ok"))
    bad_files = [r["source"] for r in todays if not r.get("file_ok")]
    check_detail = f"{last} 파일 {ok}/{len(todays)} 통과" + (f" · 실패: {', '.join(bad_files)}" if bad_files else "")
    check_state = _stale("ok" if not bad_files else "warn", last, today)
    return [_stage("수집", collect_state, last, detail), _stage("형식 검사", check_state, last, check_detail)]


def collect_report(root: Path = ROOT, today: Optional[str] = None) -> dict:
    today = today or date.today().isoformat()
    lab = root / "docs" / "lab" / "data"
    collect = _json(root / "docs" / "data" / "collect.json")
    meta = _json(lab / "meta.json") or {}
    review = _json(root / "docs" / "data" / "source_review.json") or {}
    roles = (_json(root / "config" / "source_roles.json") or {}).get("signals", {})
    signals, teams, outcomes = _csv(lab / "signals.csv"), _csv(lab / "teams.csv"), _csv(lab / "outcomes.csv")
    meta_time = str(meta.get("generated_at") or "")[:16].replace("T", " ")

    stages = _collect_stages(collect, today)
    if meta:
        stages.append(_stage("이름·공연장 묶기", _stale("ok" if meta.get("uses_artist_xref") else "warn", meta_time, today),
                             meta_time, "아티스트 연결표 사용" if meta.get("uses_artist_xref") else "연결표 없이 괄호 별칭만"))
    else:
        stages.append(_stage("이름·공연장 묶기", "check", detail="랩 메타 파일 없음"))
    with_profile = sum(1 for t in teams if (t.get("profile_status") or "unknown") != "unknown")
    stages.append(_stage("프로필 보강", _stale("ok" if with_profile else "warn", meta_time, today) if teams else "check",
                         meta_time, f"프로필 보유 {with_profile:,}팀 / {len(teams):,}팀" if teams else "팀 표 없음"))
    m = re.search(r"자동 생성[^\n]*?(\d{4}-\d{2}-\d{2} \d{2}:\d{2}) 기준", _text(root / "docs" / "sql" / "README.md"))
    stages.append(_stage("분석 SQL", _stale("ok", m.group(1), today), m.group(1), "SQL 결과 문서 갱신") if m
                  else _stage("분석 SQL", "check", detail="SQL 결과 문서의 생성 시각을 못 읽음"))
    snaps = (_json(lab / "snapshots" / "index.json") or {}).get("dates") or []
    stages.append(_stage("점수", _stale("ok", snaps[0], today), snaps[0], f"점수 스냅샷 {len(snaps)}개") if snaps
                  else _stage("점수", "check", detail="점수 스냅샷 없음"))
    n_sig = (meta.get("rows") or {}).get("signals") or 0
    stages.append(_stage("앱", _stale("ok" if n_sig else "warn", meta_time, today), meta_time,
                         f"랩 데이터 신호 {n_sig:,}행 · 데이터 끝 {meta.get('data_end', '')}") if meta
                  else _stage("앱", "check", detail="랩 데이터 없음"))

    branches: Dict[str, dict] = {}
    by_branch = defaultdict(list)
    for s in signals:
        by_branch[s.get("branch") or ""].append(s)
    for b, rows in sorted(by_branch.items(), key=lambda x: -len(x[1])):
        branches[b] = {"rows": len(rows), "teams": len({r["team_key"] for r in rows})}
    counted = [o for o in outcomes if str(o.get("counted", "")).lower() == "true"]
    scale = {"branches": branches,
             "outcomes": {"rows": len(outcomes), "counted": len(counted),
                          "by_grade": dict(sorted(Counter(o.get("grade") or "?" for o in counted).items()))},
             "profiles": dict(Counter(t.get("profile_status") or "unknown" for t in teams)),
             "links": len(_csv(lab / "links.csv")), "videos": len(_csv(lab / "videos.csv")),
             "images": len(_csv(lab / "images.csv"))}

    runs = (collect or {}).get("runs") or []
    validation = {"file_ok": (sum(1 for r in runs if r.get("file_ok")), len(runs)),
                  "auc": parse_auc(_text(root / "docs" / "score_tuning.md")),
                  "link_rate": parse_link_rate(_text(root / "docs" / "artist_xref.md")),
                  "suggestions": review.get("suggestions") or [], "sources": review.get("sources") or [],
                  "review_cutoffs": review.get("cutoffs") or []}

    first_seen: Dict[str, str] = {}
    for s in signals:
        key = f"{s.get('branch')}:{s.get('program') if s.get('branch') == '선정·지원' else s.get('source')}"
        d = (s.get("signal_date") or "")[:10]
        if d and (key not in first_seen or d < first_seen[key]):
            first_seen[key] = d
    pending = []
    for src, v in roles.items():
        if v.get("role") != "pending":
            continue
        since = first_seen.get(src, "")
        review_on = (date.fromisoformat(since) + timedelta(days=PENDING_REVIEW_DAYS)).isoformat() if since else ""
        pending.append({"src": src, "since": since, "review_on": review_on, "reason": v.get("reason", "")})
    pending.sort(key=lambda p: (p["review_on"] or "9999", p["src"]))

    logs = sorted((root / "docs" / "log").glob("????-??-??.md"), reverse=True)[:LOG_DAYS] if (root / "docs" / "log").is_dir() else []
    return {"today": today, "generated": datetime.now().astimezone().isoformat(timespec="minutes"),
            "stages": stages, "scale": scale, "validation": validation, "pending": pending,
            "logs": [{"name": p.name, "url": f"{REPO_BLOB}docs/log/{p.name}"} for p in logs]}


# ---------- HTML ----------

def _e(v) -> str:
    return html.escape("" if v is None else str(v))


def _table(head: List[str], rows: List[List[str]]) -> str:
    th = "".join(f"<th>{_e(h)}</th>" for h in head)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows) \
        or f'<tr><td colspan="{len(head)}" class="muted">없음</td></tr>'
    return f'<div class="tbl"><table><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></div>'


CSS = """
:root{--bg:#f6f7f9;--panel:#fff;--ink:#161a22;--muted:#5d6573;--line:#dde1e8;--accent:#6a4bd8;
--ok:#1f8a3b;--ok-bg:#e3f3e7;--warn:#a86b00;--warn-bg:#fbf0d9;--bad:#c0352b;--bad-bg:#fbe6e4;--chk:#6b7280;--chk-bg:#eceef1;
--f:"Noto Sans KR","Apple SD Gothic Neo","Malgun Gothic",system-ui,sans-serif}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#12151b;--panel:#1a1e26;--ink:#e9ecf2;--muted:#9aa3b2;
--line:#2c323d;--accent:#a58cff;--ok:#5cc777;--ok-bg:#173222;--warn:#e3b04b;--warn-bg:#362a12;--bad:#f07a70;--bad-bg:#3b1d1a;
--chk:#9aa3b2;--chk-bg:#262b34;color-scheme:dark}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--f);font-size:15px;line-height:1.6}
main{max-width:1080px;margin:0 auto;padding:32px 16px 56px;display:flex;flex-direction:column;gap:28px}
h1{margin:0;font-size:clamp(1.5rem,3vw,2rem)}h2{margin:0 0 10px;font-size:1.15rem}p{margin:0}a{color:var(--accent)}
.muted{color:var(--muted)}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,220px),1fr));gap:10px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 14px;display:flex;flex-direction:column;gap:4px}
.card .k{font-size:13px;color:var(--muted)}.card .v{font-size:1.4rem;font-weight:700;font-variant-numeric:tabular-nums}
.chip{display:inline-block;padding:1px 10px;border-radius:999px;font-size:12.5px;font-weight:600;white-space:nowrap}
.ok{color:var(--ok);background:var(--ok-bg)}.warn{color:var(--warn);background:var(--warn-bg)}.bad{color:var(--bad);background:var(--bad-bg)}
.check{color:var(--chk);background:var(--chk-bg)}
.tbl{overflow-x:auto;background:var(--panel);border:1px solid var(--line);border-radius:10px}
table{width:100%;border-collapse:collapse;font-size:14px}th,td{text-align:left;padding:8px 12px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:12.5px;color:var(--muted);font-weight:600}tr:last-child td{border-bottom:0}td.num{text-align:right;font-variant-numeric:tabular-nums}
ul{margin:0;padding-left:20px}footer{font-size:12.5px;color:var(--muted)}
"""


def render_html(rep: dict) -> str:
    st_rows = [[_e(s["name"]), f'<span class="chip {s["state"]}">{STATE_KO[s["state"]]}</span>', _e(s["last"] or "—"), _e(s["detail"])]
               for s in rep["stages"]]
    sc = rep["scale"]
    cards = [("신호 행", sum(b["rows"] for b in sc["branches"].values())), ("정답 행", sc["outcomes"]["rows"]),
             ("센 정답", sc["outcomes"]["counted"]), ("링크", sc["links"]), ("영상", sc["videos"]), ("사진", sc["images"])]
    card_html = "".join(f'<div class="card"><span class="k">{_e(k)}</span><span class="v">{v:,}</span></div>' for k, v in cards)
    br_rows = [[_e(b or "—"), f'<span>{v["rows"]:,}</span>', f'<span>{v["teams"]:,}</span>'] for b, v in sc["branches"].items()]
    grade_txt = " · ".join(f"{g} {n}" for g, n in sc["outcomes"]["by_grade"].items()) or "—"
    prof_txt = " · ".join(f"{k} {n:,}" for k, n in sorted(sc["profiles"].items(), key=lambda x: -x[1])) or "—"
    v = rep["validation"]
    ok, tot = v["file_ok"]
    auc = v["auc"]
    auc_txt = (f"교차 검증 평균 AUC: 점수 v2 {auc['v2']} · v0 {auc['v0']} · 공연 수만 {auc['gigs']}" if auc
               else '<span class="chip check">확인 필요</span> docs/score_tuning.md 형식을 못 읽음')
    lr = v["link_rate"]
    lr_txt = (f"정답 팀 중 신호와 이어진 팀: {lr['linked']:,} / {lr['total']:,}팀 ({lr['pct']}%)" if lr
              else '<span class="chip check">확인 필요</span> docs/artist_xref.md 형식을 못 읽음')
    sug_rows = [[_e(s.get("src")), _e(s.get("role")), _e(s.get("suggestion")), _e(s.get("reason"))] for s in v["suggestions"]]
    src_rows = [[_e(s.get("src")), _e(s.get("role")), f'{s.get("teams") or 0:,}', _e(s.get("rate")), _e(s.get("lift")), _e(s.get("only_source"))]
                for s in v["sources"] if s.get("teams")]
    pend_rows = [[_e(p["src"]), _e(p["since"] or "기록 없음"), _e(p["review_on"] or "—"), _e(p["reason"])] for p in rep["pending"]]
    logs = "".join(f'<li><a href="{_e(l["url"])}">{_e(l["name"])}</a></li>' for l in rep["logs"]) or '<li class="muted">없음</li>'
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>진행 점검표 · Crate Digger</title>
<style>{CSS}</style>
</head>
<body>
<main>
<header>
<p class="muted">Crate Digger · 진행 점검표 (자동 생성)</p>
<h1>파이프라인 점검표</h1>
<p class="muted">기준 {_e(rep['today'])} · 만든 시각 {_e(rep['generated'])} · 공개 파일만 읽어 계산 · <a href="index.html">진행판으로</a></p>
</header>
<section><h2>① 단계별 상태</h2>
{_table(["단계", "상태", "마지막 성공", "내용"], st_rows)}
<p class="muted">마지막 성공이 {STALE_DAYS}일보다 오래되면 '이상'. 매일 전체를 받는 표(공연·기사·발매)가 직전 {DROP_MIN_PREV}행 이상인데 {int(DROP_RATIO * 100)}% 미만으로 줄면 '급감'으로 '주의' (앱과 같은 규칙).</p></section>
<section><h2>② 데이터 규모</h2>
<div class="grid">{card_html}</div>
{_table(["갈래", "신호 행", "팀"], br_rows)}
<p class="muted">센 정답 등급: {_e(grade_txt)} · 팀 상태(프로필): {_e(prof_txt)}</p></section>
<section><h2>③ 검증</h2>
<ul><li>형식 검사: 수집 파일 {ok}/{tot} 통과</li><li>{auc_txt}</li><li>{lr_txt}</li>
<li>출처 재분류 제안 {len(v['suggestions'])}건 (성적표 기준일 {_e(', '.join(v['review_cutoffs']) or '—')})</li></ul>
{_table(["출처", "지금 역할", "제안", "근거"], sug_rows)}
{_table(["출처", "역할", "후보 팀", "적중률(%)", "배수", "유일 기여"], src_rows)}</section>
<section><h2>④ 검증 대기 출처와 재평가 날짜</h2>
{_table(["출처", "기록 시작", f"재평가 (시작 + {PENDING_REVIEW_DAYS}일)", "메모"], pend_rows)}</section>
<section><h2>⑤ 최근 {LOG_DAYS}일 일일 기록</h2><ul>{logs}</ul></section>
<footer>만들기: <code>python3 scripts/build_status_report.py</code> · 데이터: docs/data/collect.json · docs/data/source_review.json · docs/lab/data/ · config/source_roles.json</footer>
</main>
</body>
</html>
"""


def main() -> int:
    rep = collect_report()
    OUT.write_text(render_html(rep), encoding="utf-8")
    states = Counter(s["state"] for s in rep["stages"])
    print(f"✅ 진행 점검표 → {OUT.relative_to(ROOT)} (단계 상태 {dict(states)}, 재분류 제안 {len(rep['validation']['suggestions'])}건, "
          f"검증 대기 {len(rep['pending'])}개)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
