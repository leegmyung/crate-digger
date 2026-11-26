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
PRESS_SOURCES = {"musicy", "rhythmer", "liak", "izm", "weiv", "youtube", "rss", "manual"}
OUTCOME_SOURCES = {"manual", "aside"}

RELEASE_TYPES = {"single", "EP", "LP", "OST", "compilation"}

# 공증(정답) 프로그램 코드. 후보·점수에는 쓰지 않는다.
PROGRAMS = {
    "hello_rookie", "hello_rookie_year", "cj_tuneup", "penta_superrookie", "kma_rookie",
    "opcd", "izm_rookie", "musicy_rookie", "rhythmer_award", "gg_indiestance",
    "bbc_sound_of", "tiny_desk",
}
RESULTS = {"selected", "winner", "finalist", "shortlist", "longlist", "nominee"}

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
        "key": ("source", "release_url"),
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
        ],
        "key": ("url", "artist_text"),
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
