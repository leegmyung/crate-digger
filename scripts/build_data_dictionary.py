"""데이터 사전 만들기 → docs/data_dictionary.md

    python3 scripts/build_data_dictionary.py

표 구조(칸 이름·형식)는 코드에서 바로 읽는다: 원본 표 = scripts/csv_schema.py TABLES (+ 영상·협업 수집기 상수),
랩 데이터 = scripts/export_lab_data.py 의 *_FIELDS. 칸 설명은 아래 COLUMN_DOC 한 곳에 둔다.
칸이 새로 생기면 tests/test_build_data_dictionary.py 가 '설명 없는 칸'으로 실패 → COLUMN_DOC 에 설명을 넣고 다시 만든다.
출처 역할(발굴·맥락·검증 대기·제외)은 config/source_roles.json 에서 읽는다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect_spotify_collabs as cc  # noqa: E402
import collect_videos as cv  # noqa: E402
import csv_schema as cs  # noqa: E402
import export_lab_data as ex  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "data_dictionary.md"
ROLES_FILE = ROOT / "config" / "source_roles.json"
ROLE_KO = {"discovery": "발굴", "context": "맥락", "pending": "검증 대기", "excluded": "제외"}
KIND_KO = {"text": "글자", "code": "코드(정해진 값)", "date": "날짜 YYYY-MM-DD", "date_partial": "날짜(연·월만도 가능)",
           "datetime_tz": "날짜시각(시간대 포함)", "date_or_datetime": "날짜 또는 날짜시각", "time_hm": "시각 HH:MM",
           "url": "주소(URL)", "int0": "정수(0 이상)", "int_pos": "정수(1 이상)", "flag01": "0/1", "handle": "인스타 계정명"}

# 칸 설명 (단위 포함). '표.칸' 키가 있으면 그쪽이 우선.
COLUMN_DOC: Dict[str, str] = {
    "collected_at": "수집한 시각", "collector": "수집 방법 (script=스크립트, aside=브라우저 자동화, manual=손으로)",
    "source": "수집 출처 코드", "source_id": "출처 안의 번호", "artist_text": "출처에 적힌 아티스트 이름 그대로",
    "artist_source_id": "출처 안의 아티스트 번호", "artist_key": "정규화한 이름 키 (공백·기호 제거, 소문자)",
    "artist_url": "출처의 아티스트 페이지 주소", "url": "원문 주소", "title": "제목", "note": "메모",
    "debut_date": "데뷔일", "debut_title": "데뷔 곡·앨범", "activity_type": "활동 유형 (솔로·그룹 등)",
    "agency_text": "소속사", "agency": "소속사", "genre": "장르 (여러 개면 |)", "nationality": "국적",
    "fan_count": "플랫폼 팬(좋아요) 수, 명", "album_count": "플랫폼에 올라온 앨범 수(싱글 포함), 개",
    "first_release_date": "가장 오래된 발매일", "youtube_url": "아티스트 페이지에 걸린 유튜브 채널 주소",
    "released_at": "발매일", "title_key": "정규화한 제목 키 (여러 플랫폼 동시 발매 묶기)",
    "release_type": "발매 형태 (single·EP·LP 등)", "label_text": "기획사·레이블", "track_count": "수록곡 수, 곡",
    "release_url": "발매 페이지 주소", "distributor_text": "유통사",
    "gig_date": "공연 날짜", "gig_time": "공연 시작 시각", "venue_text": "공연장 (괄호 안 주소 포함)", "gig_url": "공연 페이지 주소",
    "outlet": "매체·계정 이름", "published_at": "게시일", "release_title": "다룬 곡·앨범 제목",
    "is_pick": "추천·선정 글이면 1", "pick_label": "추천 꼭지 이름 (venue_lineup = 공연장 라인업 공지 → 공연 갈래로 셈)",
    "artist_handle": "태그된 아티스트 인스타 계정", "is_sponsored": "협찬·광고 글이면 1 (신호에서 뺌)",
    "program": "프로그램 코드 (선정·지원 또는 정답)", "round": "회차", "stage": "단계 (응모·서류·선정·최종 등)",
    "announced_at": "발표일", "result": "결과 (선정·수상·후보 등)",
    "team_key": "팀 대표 키 (아티스트 연결표로 같은 팀의 여러 표기를 하나로)", "display_name": "화면에 보일 팀 이름",
    "branch": "신호 갈래 (공연·큐레이션·선정·지원·발매)", "stage_rank": "선정 단계 점수 0~4 (응모 0 … 최종 4)",
    "signal_date": "신호 날짜 (일부만 아는 날짜는 기간의 마지막 날 — 시점 누수 방지)",
    "venue": "공연장 대표 이름 (공연장 표기 묶기 적용)", "role": "출처 역할 (discovery 발굴 / context 맥락 / pending 검증 대기 / excluded 제외)",
    "first_seen": "우리 데이터에 처음 나온 날", "first_release": "프로필 첫 발매일 (없으면 빈 칸)",
    "profile_status": "팀 상태 (newcomer 신인 / established 기성 / famous 유명 / unknown 프로필 없음)",
    "primary_genre": "대표 장르", "program_label": "프로그램 한글 이름", "tier": "정답 단계 (final 최종 / mid 중간)",
    "result": "결과 (winner 수상 / nominee 후보 / shortlist 최종 후보 — 후보는 한 등급 아래)",
    "announced_date": "정답 발표일 (일부만 알면 기간의 첫날 — 보수적)", "counted": "센 정답인지 (기성 팀 연차 규칙 통과) true/false",
    "grade": "정답 등급 S·A·B", "weight": "정답 등급 가중치 (S=3·A=2·B=1)",
    "platform": "플랫폼 (spotify·melon·instagram·youtube 등)", "kind": "영상 종류 (stage 무대·official_live·official·search)",
    "video_id": "유튜브 영상 번호 (11자)", "channel_title": "채널 이름", "channel_id": "채널 번호",
    "source_channel_handle": "찾은 채널 계정 (@…)",
    "partner_key": "협업 상대의 팀 대표 키", "partner_name": "협업 상대 이름",
    "release_date": "협업곡 발매일 (일부만 알면 기간의 마지막 날)",
    "partner_established": "협업 당시 상대가 기성 아티스트였나 true/false (첫 발매 5년 이상 앞섬·앨범 15개 이상·유명·이미 수상)",
    "artist_name": "우리 팀 이름 (스포티파이 표기)", "artist_spotify_id": "우리 팀 스포티파이 번호",
    "partner_spotify_id": "상대 스포티파이 번호", "track_id": "곡 번호", "track_name": "곡 이름",
    "album_id": "앨범 번호", "album_name": "앨범 이름", "release_date_precision": "발매일 정밀도 (year·month·day)",
    "album_group": "앨범 구분 (album·single·appears_on 등)", "edge_count": "우리 팀들과의 협업 곡 수",
    "score": "그날 점수 (점수 v2)", "rank": "그날 순위", "label": "프로그램 한글 이름",
    "raw_collab.role": "협업 형태 (co_lead 공동 주인 / feat_on_own 우리 곡에 피처링 / guest_on_partner 상대 곡에 참여)",
    "collabs.role": "협업 형태 (co_lead / feat_on_own / guest_on_partner)",
    "programs.kind": "프로그램 종류 (signal 신호 / outcome 정답)",
    "images.source": "사진 출처 (spotify)", "images.url": "사진 주소 (i.scdn.co 만)",
    "links.url": "아티스트 페이지 주소",
}

LAB = "docs/lab/data"


def all_tables() -> List[dict]:
    """문서에 실을 모든 표: 이름·위치·공개 여부·출처·갱신 주기·칸."""
    raw_meta = {
        "raw_kr_gig": ("공연", "인디스트릿·인디고·상상마당 공연 목록"),
        "raw_press": ("큐레이션", "웹진(음악취향Y·IZM·리드머·weiv·VISLA·overtone)·인스타 매거진·공연장 라인업 공지"),
        "raw_kr_selection": ("선정·지원", "부산 루키즈·뮤즈 인 세종·경북 창작소·유재하 경연·밴드 디스커버리·DMZ"),
        "raw_kr_release": ("발매", "포크라노스·멜론·벅스·지니·FLO 신보"),
        "raw_outcome": ("정답", "신인상·주요 신인 프로그램 발표 (손으로 확인한 것 포함)"),
        "raw_artist_profile": ("프로필", "멜론·스포티파이·인스타 아티스트 페이지"),
    }
    out = []
    for name, spec in cs.TABLES.items():
        branch, origin = raw_meta.get(name, ("", ""))
        out.append({"name": name, "where": f"data/raw/{name}_<날짜>.csv", "public": False, "origin": origin,
                    "branch": branch, "cadence": "매일 21시", "columns": [f.name for f in spec["fields"]],
                    "kinds": {f.name: f.kind for f in spec["fields"]}, "key": spec.get("key")})
    out += [
        {"name": "raw_video", "where": "data/raw/raw_video_<날짜>.csv", "public": False, "origin": "유튜브 Data API (공식 채널·무대 채널)",
         "branch": "보조(팀 상세 영상)", "cadence": "매일 21시", "columns": list(cv.COLUMNS)},
        {"name": "raw_collab", "where": "data/raw/raw_collab_<날짜>.csv", "public": False, "origin": "스포티파이 Web API (피처링·공동 참여 곡)",
         "branch": "협업 (검증 대기)", "cadence": "매일 21시", "columns": list(cc.COLLAB_COLUMNS)},
        {"name": "raw_collab_partner", "where": "data/raw/raw_collab_partner_<날짜>.csv", "public": False,
         "origin": "스포티파이 Web API (협업 상대 프로필)", "branch": "협업 (검증 대기)", "cadence": "매일 21시",
         "columns": list(cc.PARTNER_COLUMNS)},
    ]
    lab = [("signals", ex.SIGNAL_FIELDS, "PostgreSQL core.v_signal (원본 4갈래를 한 표로, 팀·공연장 묶기 적용)", "신호"),
           ("teams", ex.TEAM_FIELDS, "팀별 첫 등장 + 멜론·스포티파이 프로필", "팀"),
           ("outcomes", ex.OUTCOME_FIELDS, "정답 + 등급 (config/source_roles.json)", "정답"),
           ("programs", ["program", "label", "kind"], "선정·지원·정답 프로그램 이름표", "참고"),
           ("links", ex.LINK_FIELDS, "플랫폼 아티스트 페이지 연결 (동명 없는 것만)", "보조"),
           ("images", ex.IMAGE_FIELDS, "아티스트 사진 주소 (스포티파이)", "보조"),
           ("videos", ex.VIDEO_FIELDS, "팀별 무대·공식 영상 (최대 6개)", "보조"),
           ("collabs", ex.COLLAB_FIELDS, "스포티파이 협업 (기성 파트너 판정 포함)", "협업 (검증 대기)"),
           ("snapshots", ["team_key", "score", "rank"], "날짜별 점수 상위 300팀 (snapshots/<날짜>.csv)", "점수 기록")]
    for name, cols, origin, branch in lab:
        where = f"{LAB}/snapshots/<날짜>.csv" if name == "snapshots" else f"{LAB}/{name}.csv"
        out.append({"name": name, "where": where, "public": True, "origin": origin, "branch": branch,
                    "cadence": "매일 21시 (export_lab_data.py)" if name != "snapshots" else "매일 21시 (lab_snapshot.py, 최근 것만 보관)",
                    "columns": list(cols)})
    return out


# 공개 JSON 파일: 맨 위 칸 설명
JSON_DOC: Dict[str, Dict[str, str]] = {
    f"{LAB}/meta.json": {"prev_rows": "직전 날짜의 표별 행 수 (앱의 '새로 붙은 수')", "generated_at": "만든 시각",
                         "data_end": "데이터 끝 날짜 (기준일)", "uses_artist_xref": "아티스트 연결표를 썼는지",
                         "rows": "표별 행 수"},
    f"{LAB}/source_roles.json": {"_설명": "분류 기준 설명", "default_role": "분류표에 없는 출처의 임시 역할",
                                 "signals": "출처별 역할·근거", "outcomes": "정답 등급·가중치"},
    "docs/data/board.json": {"updated": "갱신 날짜", "focus": "지금 집중하는 일", "steps": "파이프라인 단계 상태",
                             "gaps": "찾은 빈틈과 보완", "sources": "검토한 소스 목록", "pending_research": "조사할 것",
                             "decisions": "결정 사항"},
    "docs/data/collect.json": {"generated": "만든 시각", "runs": "날짜·소스별 수집 행 수와 형식 검사 결과",
                               "recent_releases": "최근 발매", "upcoming_gigs": "다가오는 공연",
                               "selections": "선정 명단", "cross_branch": "여러 갈래에 나온 팀"},
    "docs/data/dashboard.json": {"generated": "만든 시각", "window_from": "집계 시작일", "lookback_from": "신호 보는 시작일",
                                 "xref_active": "아티스트 연결표 사용 여부", "deltas": "직전 대비 변화",
                                 "errors": "계산 실패한 칸", "sections": "대시보드 구역별 숫자"},
    "docs/data/source_review.json": {"generated_at": "만든 시각", "data_end": "데이터 끝 날짜", "cutoffs": "성적표 기준일",
                                     "since": "수상 팀 셈 시작일", "horizon_months": "관찰 기간(개월)", "rules": "제안 규칙",
                                     "suggestions_changed_on": "제안 목록이 바뀐 날", "suggestions": "출처 재분류 제안",
                                     "sources": "출처별 성적 숫자"},
}


def _doc(table: str, col: str) -> Optional[str]:
    return COLUMN_DOC.get(f"{table}.{col}") or COLUMN_DOC.get(col)


def missing_descriptions(tables: Optional[List[dict]] = None, check_json: bool = True) -> List[str]:
    """설명이 없는 '표.칸' 목록. 실제 JSON 파일의 맨 위 칸도 확인한다."""
    out = [f"{t['name']}.{c}" for t in (tables if tables is not None else all_tables())
           for c in t["columns"] if not _doc(t["name"], c)]
    if check_json and tables is None:
        for rel, doc in JSON_DOC.items():
            path = ROOT / rel
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            out += [f"{rel}.{k}" for k in (data if isinstance(data, dict) else {}) if k not in doc]
    return out


def _roles() -> List[tuple]:
    try:
        cfg = json.loads(ROLES_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [(k, ROLE_KO.get(v.get("role"), v.get("role", "")), v.get("reason", "")) for k, v in cfg.get("signals", {}).items()]


def _table_md(t: dict) -> List[str]:
    lines = [f"### `{t['name']}`", "",
             f"- 위치: `{t['where']}` · {'공개' if t['public'] else '**비공개** (실제 수집 원본, 저장소에 안 올림 — 이름·칸만)'}",
             f"- 출처: {t['origin']} · 갈래/쓰임: {t['branch']} · 갱신: {t['cadence']}"]
    if t.get("key"):
        lines.append(f"- 같은 행 판단 칸: {', '.join(f'`{k}`' for k in t['key'])}")
    lines += ["", "| 칸 | 뜻·단위 | 형식 |", "|---|---|---|"]
    kinds = t.get("kinds", {})
    lines += [f"| `{c}` | {_doc(t['name'], c) or '(설명 없음)'} | {KIND_KO.get(kinds.get(c, ''), kinds.get(c, '')) or '—'} |"
              for c in t["columns"]]
    return lines + [""]


def render() -> str:
    tables = all_tables()
    lines = ["# 데이터 사전", "",
             "_자동 생성: `python3 scripts/build_data_dictionary.py` — 칸 이름은 코드(scripts/csv_schema.py, scripts/export_lab_data.py, "
             "수집기 상수)에서 읽고, 설명은 build_data_dictionary.COLUMN_DOC 에 있습니다. 칸이 바뀌면 테스트가 알려 줍니다._", "",
             "## 한눈에", "", "| 표 | 위치 | 공개 | 갈래/쓰임 | 갱신 |", "|---|---|---|---|---|"]
    lines += [f"| `{t['name']}` | `{t['where']}` | {'공개' if t['public'] else '비공개'} | {t['branch']} | {t['cadence']} |"
              for t in tables]
    lines += ["", "데이터 흐름: 수집기 → 원본 CSV(`data/raw/`, 비공개) → PostgreSQL(raw → core 뷰, 팀·공연장 묶기) → "
              "랩 데이터(`docs/lab/data/`, 공개) → 앱·SQL 결과·엑셀.", "",
              "## 1. 공개 랩 데이터 (`docs/lab/data/`)", ""]
    for t in tables:
        if t["public"]:
            lines += _table_md(t)
    lines += ["## 2. 원본 수집 표 (비공개)", "",
              "실제 수집 원본은 공개 저장소에 올리지 않습니다. 형식 규칙은 `scripts/csv_schema.py`·[csv_spec.md](csv_spec.md).", ""]
    for t in tables:
        if not t["public"]:
            lines += _table_md(t)
    lines += ["## 3. 공개 JSON 파일", ""]
    for rel, doc in JSON_DOC.items():
        lines += [f"### `{rel}`", "", "| 칸 | 뜻 |", "|---|---|"] + [f"| `{k}` | {v} |" for k, v in doc.items()] + [""]
    lines += ["## 4. 출처 역할 (`config/source_roles.json`)", "",
              "신호 출처마다 역할을 정해 점수에 쓸지 정합니다: **발굴**(점수에 씀) · **맥락**(약하게만) · **검증 대기**(모으기만) · "
              "**제외**(효과 없음). 기준은 [source_roles.md](source_roles.md).", "",
              "| 출처 (갈래:출처) | 역할 | 근거 |", "|---|---|---|"]
    lines += [f"| `{k}` | {r} | {reason} |" for k, r, reason in _roles()]
    return "\n".join(lines) + "\n"


def main() -> int:
    missing = missing_descriptions()
    if missing:
        print(f"⚠️ 설명 없는 칸 {len(missing)}개 (COLUMN_DOC 에 추가): {', '.join(missing)}", file=sys.stderr)
    OUT.write_text(render(), encoding="utf-8")
    print(f"✅ 데이터 사전 → {OUT.relative_to(ROOT)} (표 {len(all_tables())}개)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
