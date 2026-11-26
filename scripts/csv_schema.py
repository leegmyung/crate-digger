"""수집 CSV 형식 규칙 (사람용 설명은 docs/csv_spec.md).

검사기(validate_csv.py)와 이후 적재 스크립트가 이 파일 하나를 기준으로 삼는다.
칸을 바꾸면 docs/csv_spec.md 도 같이 고친다.
"""
from collections import namedtuple

Field = namedtuple("Field", "name kind required choices")


def F(name, kind="text", required=False, choices=None):
    return Field(name, kind, required, frozenset(choices) if choices else None)


COLLECTORS = {"aside", "script", "manual"}

RELEASE_SOURCES = {
    "poclanos", "muzeplatform", "vlending", "mirrorball",          # 유통사·셀프 유통
    "bugs", "flo", "genie", "melon", "bandcamp_kr",                # 음원 플랫폼
    "manual",
}
GIG_SOURCES = {"indiego", "indistreet", "manual"}
PRESS_SOURCES = {"musicy", "rhythmer", "liak", "izm", "weiv", "youtube", "rss", "manual",
                 "visla", "overtone", "instagram"}
OUTCOME_SOURCES = {"manual", "aside"}

RELEASE_TYPES = {"single", "EP", "LP", "OST", "compilation"}

# 공증(정답) 프로그램 코드. 후보·점수에는 쓰지 않는다.
PROGRAMS = {
    "hello_rookie", "hello_rookie_year", "cj_tuneup", "penta_superrookie", "kma_rookie",
    "opcd", "izm_rookie", "musicy_rookie", "rhythmer_award", "gg_indiestance",
    "bbc_sound_of", "tiny_desk", "museon_final", "indiestance", "yoojaeha",
    # 메이저 매체 소개 = '주목받기 시작함' (정답 2등급). 협찬 기사는 넣지 않는다.
    "media_izm", "media_bandwagon", "media_nme", "media_esquire",
}
RESULTS = {"selected", "winner", "finalist", "shortlist", "longlist", "nominee", "featured"}

# 후보 신호용 선정·지원 프로그램 코드 (작고 이른 단계). 정답 코드(PROGRAMS)와 겹치면 안 된다.
SELECTION_SOURCES = {
    "mapoindie", "kocca", "gwmf", "seoulbusking", "gcon", "ebs", "contest",
    "rollinghall", "senggi", "liveclubday", "tumblbug", "manual",
    "busanrock", "sejong", "gbsound",
}
SELECTION_PROGRAMS = {
    "indiscovery",              # 마포 인디스커버리
    "museon_document",          # 뮤즈온 서류통과 (최종은 정답 museon_final)
    "our_musician",             # KOCCA 우리 음악인 축제
    "gw_creation",              # 강원음악창작소 선정
    "seoul_busking",            # 서울 구석구석라이브
    "regional_contest",         # 지역 밴드 경연 본선
    "hello_rookie_applicant",   # 헬로루키 응모 (수상은 정답 hello_rookie*)
    "indiestance_prelim",       # 인디스땅스 예선 (결선은 정답 indiestance)
    "cmyk",                     # 롤링홀 CMYK
    "senggi_curation",          # 생기스튜디오 생기 큐레이션
    "liveclubday",              # 라이브클럽데이
    "tumblbug_debut",           # 텀블벅 첫 음반 펀딩
    "burock_rookies",           # 부산국제록페스티벌 루키즈 온 더 부락 (TOP15/10/3)
    "muse_sejong",              # 세종음악창작소 뮤즈세종
    "gb_creation",              # 경북음악창작소(054사운드빌) 음반 제작 지원
}
STAGES = {"applied", "document", "challenger", "lineup", "showcase", "selected", "final"}

# 같은 프로그램 규칙: 앞 단계를 후보로 쓴 팀은 같은 프로그램의 정답 결과를 적중으로 세지 않는다.
SAME_PROGRAM = {
    "hello_rookie_applicant": frozenset({"hello_rookie", "hello_rookie_year"}),
    "museon_document": frozenset({"museon_final"}),
    "indiestance_prelim": frozenset({"indiestance"}),
}


def excluded_outcomes(selection_program):
    """이 후보 프로그램에서 나온 팀에게 적중으로 세면 안 되는 정답 프로그램 코드."""
    return set(SAME_PROGRAM.get(selection_program, frozenset()))

COLLECTED_AT = F("collected_at", "datetime_tz", True)
COLLECTOR = F("collector", "code", True, COLLECTORS)

TABLES = {
    "raw_kr_release": {
        "fields": [
            COLLECTED_AT, F("source", "code", True, RELEASE_SOURCES), COLLECTOR,
            F("source_id"),
            F("released_at", "date_partial", True),
            F("artist_text", required=True),
            F("artist_source_id"),
            F("title", required=True),
            F("release_type", "code", False, RELEASE_TYPES),
            F("genre"),            # 여러 개면 | 로 구분
            F("label_text"),
            F("track_count", "int_pos"),
            F("release_url", "url", True),
        ],
        "key": ("source", "release_url", "artist_text"),   # 콜라보는 팀마다 1행
    },
    "raw_kr_gig": {
        "fields": [
            COLLECTED_AT, F("source", "code", True, GIG_SOURCES), COLLECTOR,
            F("source_id"),
            F("gig_date", "date", True),
            F("gig_time", "time_hm"),
            F("title"),
            F("venue_text"),
            F("artist_text", required=True),   # 공연 1건 × 출연 팀 1팀 = 1행
            F("artist_source_id"),
            F("gig_url", "url", True),
            F("artist_url", "url"),
        ],
        "key": ("source", "gig_url", "artist_text"),
    },
    "raw_press": {
        "fields": [
            COLLECTED_AT, F("source", "code", True, PRESS_SOURCES), COLLECTOR,
            F("outlet", required=True),
            F("published_at", "date_or_datetime", True),
            F("title", required=True),
            F("url", "url", True),
            F("artist_text", required=True),   # 기사 1건 × 언급 팀 1팀 = 1행
            F("release_title"),
            F("is_pick", "flag01", True),
            F("pick_label"),
            F("artist_handle", "handle"),      # 태그된 아티스트 인스타 계정 (이름 맞추기의 핵심 열쇠)
            F("is_sponsored", "flag01"),       # 협찬·광고 글이면 1 → 신호에서 제외
        ],
        "key": ("url", "artist_text"),
    },
    "raw_kr_selection": {
        "fields": [
            COLLECTED_AT, F("source", "code", True, SELECTION_SOURCES), COLLECTOR,
            F("program", "code", True, SELECTION_PROGRAMS),
            F("round", required=True),
            F("stage", "code", True, STAGES),
            F("announced_at", "date_partial", True),
            F("artist_text", required=True),
            F("url", "url", True),
            F("note"),
        ],
        "key": ("program", "round", "stage", "artist_text"),
    },
    "raw_outcome": {
        "fields": [
            COLLECTED_AT, F("source", "code", True, OUTCOME_SOURCES), COLLECTOR,
            F("program", "code", True, PROGRAMS),
            F("round", required=True),
            F("announced_at", "date_partial", True),
            F("result", "code", True, RESULTS),
            F("artist_text", required=True),
            F("url", "url", True),
            F("note"),
        ],
        "key": ("program", "round", "artist_text", "result"),
    },
}
