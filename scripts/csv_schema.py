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
    "bbc_sound_of", "tiny_desk", "museon_final", "indiestance",
    # 유재하음악경연대회는 2026-11-26 후보 신호로 옮김 (SELECTION_PROGRAMS의 yoojaeha_finalist)
    "burock_main",          # 부산국제록페스티벌 본무대 출연 (루키즈 후보는 SAME_PROGRAM으로 적중 제외)
    "mucon",                # 뮤콘(MU:CON) 쇼케이스 공모 선정 (정답 2등급: 다른 경연을 거친 팀이 모임)
    # 메이저 매체 소개 = '주목받기 시작함' (정답 2등급). 협찬 기사는 넣지 않는다.
    "media_izm", "media_bandwagon", "media_nme", "media_esquire",
}
RESULTS = {"selected", "winner", "finalist", "shortlist", "longlist", "nominee", "featured"}

# 후보 신호용 선정·지원 프로그램 코드 (작고 이른 단계). 정답 코드(PROGRAMS)와 겹치면 안 된다.
SELECTION_SOURCES = {
    "mapoindie", "kocca", "gwmf", "seoulbusking", "gcon", "ebs", "contest",
    "rollinghall", "senggi", "liveclubday", "tumblbug", "manual",
    "busanrock", "sejong", "gbsound", "yjh",
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
    "yoojaeha_finalist",        # 유재하음악경연대회 본선 10팀 (상 등급은 note에, 점수 가중치로만)
}
STAGES = {"applied", "document", "challenger", "lineup", "showcase", "selected", "final"}

# 같은 프로그램 규칙: 앞 단계를 후보로 쓴 팀은 같은 프로그램의 정답 결과를 적중으로 세지 않는다.
SAME_PROGRAM = {
    "hello_rookie_applicant": frozenset({"hello_rookie", "hello_rookie_year"}),
    "museon_document": frozenset({"museon_final"}),
    "indiestance_prelim": frozenset({"indiestance"}),
    "burock_rookies": frozenset({"burock_main"}),     # 루키즈 1~3위는 다음 해 본무대 기회를 받으므로
}

# 연결된 정답 프로그램이 없다고 확인한 후보 프로그램. 새 후보 프로그램을 추가하면
# SAME_PROGRAM 또는 여기 중 한쪽에 반드시 넣는다 (tests/test_validate_csv.py가 검사).
NO_LINKED_OUTCOME = frozenset({
    "indiscovery", "our_musician", "gw_creation", "seoul_busking", "regional_contest", "cmyk",
    "senggi_curation", "liveclubday", "tumblbug_debut", "muse_sejong", "gb_creation", "yoojaeha_finalist",
})


def excluded_outcomes(selection_program):
    """이 후보 프로그램에서 나온 팀에게 적중으로 세면 안 되는 정답 프로그램 코드."""
    return set(SAME_PROGRAM.get(selection_program, frozenset()))

COLLECTED_AT = F("collected_at", "datetime_tz", True)
COLLECTOR = F("collector", "code", True, COLLECTORS)

ARTIST_SOURCES = {"melon", "bugs", "genie", "flo", "manual"}

TABLES = {
    "raw_artist_profile": {      # 플랫폼 아티스트 페이지 1곳 × 1팀 = 1행 (1.5단계 신인 판별 · 2단계 이름 맞추기 기준)
        "fields": [
            COLLECTED_AT, F("source", "code", True, ARTIST_SOURCES), COLLECTOR,
            F("artist_source_id", required=True),
            F("artist_text", required=True),
            F("debut_date", "date_partial"),
            F("debut_title"),
            F("activity_type"),        # 솔로 / 그룹 ...
            F("agency_text"),          # 소속사
            F("genre"),                # 여러 개면 |
            F("nationality"),
            F("fan_count", "int0"),    # 그날의 팬(좋아요) 수 — 3단계 반응 지표로도 씀
            F("album_count", "int0"),  # 플랫폼에 올라온 앨범 수 (신인 기준: 5개 이하)
            F("first_release_date", "date_partial"),  # 앨범 목록의 가장 오래된 발매일 (데뷔일이 빈 팀 보완)
            F("youtube_url", "url"),   # 아티스트 페이지에 걸린 유튜브 채널 (3단계 유튜브 지표 대상)
            F("url", "url", True),
            F("artist_key"),
        ],
        "key": ("source", "artist_source_id"),
    },
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
            F("label_text"),       # 기획사·레이블
            F("track_count", "int_pos"),
            F("release_url", "url", True),
            F("distributor_text"), # 유통사(발매사). 1.5단계 신인·인디 판별용
            F("artist_key"),       # scripts/normalize.py artist_key — 플랫폼 간 같은 팀 묶기
            F("title_key"),        # scripts/normalize.py title_key — 동시 입점(platforms_seen) 집계
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
