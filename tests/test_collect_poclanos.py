"""포크라노스 수집기의 변환 로직 테스트 (네트워크 없이 가상 데이터로)."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import collect_poclanos as cp  # noqa: E402
import validate_csv  # noqa: E402

DETAIL_HTML = """
<ul class="album-info">
 <li><span class="title-left">Artist</span> <a class="album-to-artist" href="#"><span>가상팀</span></a></li>
 <li><span class="title-left">Release</span><span>2026-11-26</span></li>
 <li class="genres"><span class="title-left">Genre</span> <span class="from-acf">Rock</span><span class="comma">,&nbsp;</span><span class="from-acf">indie</span></li>
 <li><span class="title-left">Label</span><span>가상 &amp; 레코드</span></li>
 <li><span class="title-left">Format</span><span>Mini Album</span></li>
</ul>
<ul class="album-tracklist">
 <li class="album-title"><span class="tno">1.</span><span class="title-one">하나</span></li>
 <li class="album-title"><span class="tno">2.</span><span class="title-one">둘</span></li>
 <li class="album-title"><span class="tno">3.</span><span class="title-one">셋</span></li>
</ul>
<div class="discography"><span class="tno">9.</span></div>
"""

API_ITEM = {
    "id": 90001,
    "date": "2026-11-26T12:00:51",
    "link": "https://example.com/poclanos/album/x/",
    "title": {"rendered": "첫차 &#8211; EP"},
    "_embedded": {"wp:term": [
        [{"taxonomy": "download_artist", "id": 8801, "name": "새벽정류장"}],
        [{"taxonomy": "download_category", "id": 4, "name": "Rock"},
         {"taxonomy": "download_category", "id": 2251, "name": "indie"}],
        [{"taxonomy": "download_color", "id": 1, "name": "07_파랑"}],
    ]},
}


class ParseDetailTest(unittest.TestCase):
    def test_reads_release_label_format_tracks(self):
        d = cp.parse_detail(DETAIL_HTML)
        self.assertEqual(d["released_at"], "2026-11-26")
        self.assertEqual(d["label_text"], "가상 & 레코드")
        self.assertEqual(d["release_type"], "EP")
        self.assertEqual(d["track_count"], "3")   # 관련 앨범 영역의 번호는 세지 않음

    def test_empty_page_gives_blanks(self):
        d = cp.parse_detail("<html></html>")
        self.assertEqual(d, {"released_at": "", "label_text": "", "release_type": "", "track_count": ""})

    def test_format_mapping(self):
        self.assertEqual(cp.map_format("Single"), "single")
        self.assertEqual(cp.map_format("EP"), "EP")
        self.assertEqual(cp.map_format("Full Album"), "LP")
        self.assertEqual(cp.map_format("O.S.T"), "OST")
        self.assertEqual(cp.map_format("Remix"), "")


class ToRowsTest(unittest.TestCase):
    def test_one_row_per_artist_with_detail(self):
        rows = cp.to_rows(API_ITEM, cp.parse_detail(DETAIL_HTML), "2026-11-26T15:00:00+09:00")
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["source"], "poclanos")
        self.assertEqual(r["collector"], "script")
        self.assertEqual(r["source_id"], "90001")
        self.assertEqual(r["title"], "첫차 – EP")            # HTML 특수문자 풀기
        self.assertEqual(r["artist_text"], "새벽정류장")
        self.assertEqual(r["artist_source_id"], "8801")
        self.assertEqual(r["genre"], "Rock|indie")
        self.assertEqual(r["released_at"], "2026-11-26")

    def test_falls_back_to_post_date_without_detail(self):
        rows = cp.to_rows(API_ITEM, cp.parse_detail(""), "2026-11-26T15:00:00+09:00")
        self.assertEqual(rows[0]["released_at"], "2026-11-26")
        self.assertEqual(rows[0]["release_type"], "")

    def test_multiple_artists_one_row_each(self):
        item = dict(API_ITEM)
        item["_embedded"] = {"wp:term": [[
            {"taxonomy": "download_artist", "id": 1, "name": "A"},
            {"taxonomy": "download_artist", "id": 2, "name": "B"},
        ]]}
        rows = cp.to_rows(item, cp.parse_detail(""), "2026-11-26T15:00:00+09:00")
        self.assertEqual([(r["artist_text"], r["artist_source_id"]) for r in rows], [("A", "1"), ("B", "2")])

    def test_rows_have_normalized_keys(self):
        r = cp.to_rows(API_ITEM, cp.parse_detail(DETAIL_HTML), "2026-11-26T15:00:00+09:00")[0]
        self.assertEqual((r["artist_key"], r["title_key"]), ("새벽정류장", "첫차ep"))

    def test_new_items_skip_seen_ids(self):
        items = [{"id": 1}, {"id": 2}, {"id": 3}]
        self.assertEqual([i["id"] for i in cp.new_items(items, {"2"})], [1, 3])

    def test_written_file_passes_validator(self):
        rows = cp.to_rows(API_ITEM, cp.parse_detail(DETAIL_HTML), "2026-11-26T15:00:00+09:00")
        with tempfile.TemporaryDirectory() as d:
            path = cp.write_csv(rows, Path(d), "2026-11-26")
            self.assertEqual(path.name, "raw_kr_release_2026-11-26_poclanos.csv")
            issues = [i for i in validate_csv.validate_file(path) if i.level == "error"]
        self.assertEqual(issues, [])


class BackfillTest(unittest.TestCase):
    """--since/--until 과거 되짚기: 쪽 수 제한 없이 before 조건으로 받고, 매일 수집 상태(seen)는 건드리지 않는다."""

    def setUp(self):
        self._get, self._state, self._delay = cp.http_get, cp.STATE, cp.REQUEST_DELAY_SEC
        cp.REQUEST_DELAY_SEC = 0

    def tearDown(self):
        cp.http_get, cp.STATE, cp.REQUEST_DELAY_SEC = self._get, self._state, self._delay

    def test_list_items_pages_past_daily_cap_with_before(self):
        urls = []
        def fake(url, retries=3):
            urls.append(url)
            page = int(__import__("re").search(r"[?&]page=(\d+)", url).group(1))
            n = cp.PER_PAGE if page <= cp.MAX_PAGES + 1 else 3
            return __import__("json").dumps([{"id": page * 1000 + i} for i in range(n)])
        cp.http_get = fake
        items = cp.list_items(cp.datetime(2021, 1, 1), until="2021-12-31", max_pages=None)
        self.assertEqual(len(items), cp.PER_PAGE * (cp.MAX_PAGES + 1) + 3)
        self.assertIn("before=2022-01-01T00%3A00%3A00", urls[0])

    def test_backfill_writes_file_and_keeps_daily_state(self):
        import json
        def fake(url, retries=3):
            if "wp-json" in url:
                return json.dumps([API_ITEM]) if "&page=1&" in url else "[]"
            return DETAIL_HTML
        cp.http_get = fake
        with tempfile.TemporaryDirectory() as d:
            cp.STATE = Path(d) / "seen.json"
            cp.STATE.write_text(json.dumps(["1", "2"]), encoding="utf-8")
            path, n_items, n_rows, failed = cp.collect(3, Path(d), since="2021-01-01", until="2021-12-31")
            self.assertEqual(json.loads(cp.STATE.read_text(encoding="utf-8")), ["1", "2"])
            self.assertTrue(path.name.startswith("raw_kr_release_"))
            self.assertIn("poclanos_backfill", path.name)
            self.assertEqual((n_items, n_rows), (1, 1))


class RequiredFieldsTest(unittest.TestCase):
    """팀 태그·제목이 없는 앨범은 행을 만들지 않는다 — 빈 필수 칸 1행 때문에 파일 전체가 형식 검사에서 빠지지 않게."""

    def test_item_without_artist_or_title_gives_no_rows(self):
        no_artist = dict(API_ITEM, _embedded={"wp:term": [[{"taxonomy": "download_category", "id": 4, "name": "Rock"}]]})
        no_title = dict(API_ITEM, title={"rendered": "  "})
        detail = cp.parse_detail(DETAIL_HTML)
        self.assertEqual(cp.to_rows(no_artist, detail, "2026-11-28T00:00:00+09:00"), [])
        self.assertEqual(cp.to_rows(no_title, detail, "2026-11-28T00:00:00+09:00"), [])
        self.assertEqual(len(cp.to_rows(API_ITEM, detail, "2026-11-28T00:00:00+09:00")), 1)


class YearOnlyReleaseTest(unittest.TestCase):
    """상세 페이지 발매일이 '2026'처럼 연도만이면(같은 해 글) 글 날짜로 채운다 — 연도만이면 시점 규칙이 12-31로 읽어 미래 신호가 됨."""

    def test_year_only_release_uses_post_date_when_same_year(self):
        detail = dict(cp.parse_detail(DETAIL_HTML), released_at="2026")
        self.assertEqual(cp.to_rows(API_ITEM, detail, "x")[0]["released_at"], "2026-11-26")
        detail = dict(detail, released_at="2026-11")
        self.assertEqual(cp.to_rows(API_ITEM, detail, "x")[0]["released_at"], "2026-11-26")

    def test_older_year_kept_for_reissue(self):
        detail = dict(cp.parse_detail(DETAIL_HTML), released_at="2006")
        self.assertEqual(cp.to_rows(API_ITEM, detail, "x")[0]["released_at"], "2006")


if __name__ == "__main__":
    unittest.main()
