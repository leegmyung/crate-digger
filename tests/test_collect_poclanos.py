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


if __name__ == "__main__":
    unittest.main()
