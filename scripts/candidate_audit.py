"""후보 점검 — 점수 v2 상위 후보 중 '인디 신인 발굴 대상'이 아닌 팀을 근거와 함께 찾는다 (제안만, 규칙 적용 안 함).

    .venv/bin/python scripts/candidate_audit.py     # → data/raw/review/candidate_audit_<날짜>.csv (비공개), docs/candidate_audit.md

유형: a 기획사 아이돌·오디션 / b 기성인데 프로필이 없어 신인으로 잡힘 / c 팀이 아닌 이름 / d 같은 팀이 두 이름 /
      e 데이터 오류(멜론 번호가 이름 속 숫자로 잘못 들어감)
근거(모두 저장소 데이터): 팀 표 소속사, 멜론 검색 결과(번호·팬 수·장르), 공개 기사 제목('정규 N집'), 연결표 별칭·플랫폼 번호.
멜론 번호 기준은 이미 받은 멜론 프로필 308개로 확인: 번호 250만 미만은 첫 발매 2019년 이전이 88~100%.
"""
from __future__ import annotations

import csv
import glob
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
DOC = ROOT / "docs" / "candidate_audit.md"
TOP_N = 300
OLD_MELON_ID = 2_500_000     # 이보다 작은 멜론 번호 = 2019년 이전 등록 추정 (프로필 308개 실측, 위 설명)
MIN_MELON_ID = 1_000         # 이보다 작은 번호는 실제 아티스트 번호가 아님 (검색 결과 파싱 오류)
FAME_FANS = 10_000           # ref.settings fame_fans 와 같은 기준 (멜론 팬 1만 이상 = 유명)
ALBUM_EST = 2                # 기사 제목에 '정규 2집' 이상 → 신인 기준(발매 3년 이내)을 넘었을 가능성
AGENCIES = ("하이브", "hybe", "빅히트", "어도어", "쏘스뮤직", "빌리프랩", "플레디스", "koz", "sm엔터", "에스엠엔터", "jyp",
            "yg엔터", "스타쉽", "큐브엔터", "카카오엔터", "울림", "fnc", "젤리피쉬", "rbw", "위에화", "티오피미디어",
            "브랜뉴뮤직", "알비더블유", "더블랙레이블", "피네이션", "mnh", "wm엔터")   # 대형·중형 아이돌 기획사 (소문자 비교)
NONTEAM = [(re.compile(r"(프로덕션|엔터테인먼트|레코드|레이블|컴퍼니|스튜디오)$"), "기획·제작사 이름"),
           (re.compile(r"(페스티벌|라이브클럽|공연장|밴드 오디션)"), "행사·공연장 이름"),
           (re.compile(r"^@|^[a-z0-9_]+\.[a-z0-9_.]+$"), "인스타 계정명 모양"),   # 소문자만 (대문자 약자 I.M.F 는 아님)
           (re.compile(r"[가-힣]\s*(&|＆|\+)\s*[가-힣]|[가-힣]\s+[xX×]\s+[가-힣]"), "두 팀 합동 표기")]
HANGUL = re.compile(r"[가-힣]")


def valid_melon_id(mid: str) -> bool:
    return str(mid or "").isdigit() and int(mid) >= MIN_MELON_ID


def old_melon_id(mid: str) -> bool:
    return valid_melon_id(mid) and int(mid) < OLD_MELON_ID


def parse_desc(desc: str) -> dict:
    fans = re.search(r"팬 ([\d,]+)", desc or "")
    genres = re.search(r"음악장르 (.*?) 곡재생", desc or "")
    kind = re.search(r"((?:남성|여성|혼성)/(?:솔로|그룹))", desc or "")
    return {"fans": int(fans.group(1).replace(",", "")) if fans else None,
            "genres": [g.strip() for g in genres.group(1).split(",")] if genres else [],
            "kind": kind.group(1) if kind else ""}


def max_album_number(titles: List[str]) -> int:
    nums = [int(m) for t in titles for m in re.findall(r"(\d+)\s*집", t)]
    nums += [int(m) for t in titles for m in re.findall(r"(\d+)(?:st|nd|rd|th)\s*album", t, re.I)]
    return max(nums, default=0)


def nonteam_reason(name: str) -> str:
    n = (name or "").strip()
    return next((why for rx, why in NONTEAM if rx.search(n)), "")


def big_agency(agency: str) -> bool:
    a = (agency or "").lower().replace(" ", "")
    return bool(a) and any(k in a for k in AGENCIES)


def _one_edit(a: str, b: str) -> bool:
    if len(a) != len(b) or len(a) < 3:
        return False
    return sum(x != y for x, y in zip(a, b)) == 1


def find_duplicates(rows: List[dict], ids: Dict[str, dict], aliases: Dict[str, List[str]], cobilled: Set[Tuple[str, str]]) -> List[dict]:
    """같은 팀이 두 이름으로 갈라진 의심 쌍. 같은 날 같은 무대에 함께 선 쌍(cobilled)도 빼지 않는다 —
    한 공연에 철자만 다르게 두 번 적힌 경우가 있어서. 대신 근거에 그 사실을 적어 사람이 확인하게 한다."""
    from normalize import _squash
    keys = [r["team_key"] for r in rows]
    out = []
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            x, y = sorted((a, b))
            reason = ""
            for plat in ("melon", "spotify"):
                va, vb = (ids.get(a) or {}).get(plat), (ids.get(b) or {}).get(plat)
                if va and va == vb:
                    reason = f"같은 {'멜론' if plat == 'melon' else '스포티파이'} 번호 {va}"
            if not reason:
                ka = {_squash(s) for s in aliases.get(a, [])} | {a}
                kb = {_squash(s) for s in aliases.get(b, [])} | {b}
                if ka & kb:
                    reason = "연결표 별칭이 겹침"
            if not reason and HANGUL.search(a) and HANGUL.search(b) and _one_edit(a, b):
                reason = "한글 이름 한 글자 차이"
            if reason:
                if (x, y) in cobilled:
                    reason += " · 같은 공연에 두 이름이 함께 올라 있음 (두 번 적힌 같은 팀인지, 다른 팀인지 확인)"
                out.append({"a": x, "b": y, "reason": reason})
    return out


def classify_team(cand: dict, agency: str, melon_id: str, desc: str, titles: List[str]) -> List[dict]:
    out = []
    if big_agency(agency):
        out.append({"type": "a", "evidence": f"소속사 {agency}", "action": "제외 목록(config) 또는 기획사 차단 목록으로 후보에서 빼기"})
    if melon_id and not valid_melon_id(melon_id):
        out.append({"type": "e", "evidence": f"멜론 번호 {melon_id} — 이름 속 숫자가 번호로 잘못 들어감",
                    "action": "멜론 검색 결과 번호 파싱 수정 후 다시 검색 (collect_artists._search_js)"})
    if cand.get("profile_status") == "unknown":
        ev = []
        if old_melon_id(melon_id):
            ev.append(f"멜론 번호 {melon_id} (2019년 이전 등록 추정)")
        d = parse_desc(desc)
        if d["fans"] is not None and d["fans"] >= FAME_FANS:
            ev.append(f"멜론 팬 {d['fans']:,}")
        n = max_album_number(titles)
        if n >= ALBUM_EST:
            ev.append(f"기사 제목에 '{n}집'")
        if ev:
            out.append({"type": "b", "evidence": " · ".join(ev),
                        "action": "멜론 프로필을 먼저 받아 첫 발매일로 신인 판정 (보강 명단 맨 앞에), 또는 '번호 250만 미만 = 기성' 규칙"})
    why = nonteam_reason(cand.get("display_name", ""))
    if why:
        out.append({"type": "c", "evidence": why, "action": "팀이 아니면 연결표에서 제외 표시, 합동 표기는 팀별로 나누기"})
    return out


# ---------- 실행 ----------

def _evidence_maps():
    from artist_xref import canonical_key, load_xref
    idx = load_xref()
    melon: Dict[str, dict] = {}
    try:
        for n, v in json.loads((RAW / "state" / "outcome_melon_match.json").read_text(encoding="utf-8")).items():
            if v:
                melon.setdefault(canonical_key(n, idx), v)
    except (OSError, ValueError):
        pass
    titles: Dict[str, List[str]] = defaultdict(list)
    for f in glob.glob(str(RAW / "raw_press_*.csv")):
        with open(f, encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                titles[canonical_key(r.get("artist_text", ""), idx)].append(r.get("title", ""))
    return idx, melon, titles


def main() -> int:
    import lab_sql
    con = lab_sql.connect()
    meta = json.loads((lab_sql.DATA_DIR / "meta.json").read_text(encoding="utf-8"))
    as_of = meta.get("data_end") or date.today().isoformat()
    cands = lab_sql.query(con, "candidates.sql", as_of=f"'{as_of}'", limit=str(TOP_N))
    teams = {t["team_key"]: t for t in csv.DictReader(open(lab_sql.DATA_DIR / "teams.csv", encoding="utf-8"))}
    ids: Dict[str, dict] = defaultdict(dict)
    for r in csv.DictReader(open(lab_sql.DATA_DIR / "links.csv", encoding="utf-8")):
        m = re.search(r"artistId=(\d+)", r["url"]) if r["platform"] == "melon" else re.search(r"artist/(\w+)", r["url"]) if r["platform"] == "spotify" else None
        if m:
            ids[r["team_key"]][r["platform"]] = m.group(1)
    idx, melon, titles = _evidence_maps()
    aliases = {k: v.get("aliases", []) for k, v in idx["artists"].items()}
    findings = []
    for rank, c in enumerate(cands, 1):
        k = c["team_key"]
        m = melon.get(k) or {}
        mid = ids[k].get("melon") or m.get("id") or (idx["artists"].get(k) or {}).get("melon_id") or ""
        if mid and "melon" not in ids[k] and valid_melon_id(mid):
            ids[k]["melon"] = mid
        for f in classify_team(c, (teams.get(k) or {}).get("agency", ""), mid, m.get("desc", ""), titles.get(k, [])):
            findings.append({"rank": rank, "team_key": k, "display_name": c["display_name"], "score": c["score"], **f})
    gigs = defaultdict(set)
    for s in csv.DictReader(open(lab_sql.DATA_DIR / "signals.csv", encoding="utf-8")):
        if s["branch"] == "공연" and s.get("venue"):
            gigs[(s["signal_date"], s["venue"])].add(s["team_key"])
    cobilled = {tuple(sorted((a, b))) for t in gigs.values() for a in t for b in t if a < b}
    rank_of = {c["team_key"]: i for i, c in enumerate(cands, 1)}
    for p in find_duplicates(cands, ids, aliases, cobilled):
        findings.append({"rank": min(rank_of[p["a"]], rank_of[p["b"]]), "team_key": f"{p['a']} / {p['b']}",
                         "display_name": f"{p['a']} / {p['b']}", "score": "", "type": "d", "evidence": p["reason"],
                         "action": "같은 팀이면 연결표에 별칭으로 묶기 (사람 확인)"})
    findings.sort(key=lambda f: (f["type"], f["rank"]))
    out = RAW / "review" / f"candidate_audit_{as_of}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["type", "rank", "team_key", "display_name", "score", "evidence", "action"])
        w.writeheader()
        w.writerows(findings)
    counts = Counter(f["type"] for f in findings)
    print(f"✅ 후보 점검 {as_of} 상위 {len(cands)}팀 → {out.relative_to(ROOT)} 유형별 {dict(sorted(counts.items()))}")
    for f in findings:
        print(f"  {f['type']} {f['rank']:>3} {f['display_name']} · {f['evidence']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
