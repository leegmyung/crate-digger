"""장르 큰 갈래(bucket) 분류 테스트."""
import csv
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import genre  # noqa: E402


class BucketOfTest(unittest.TestCase):
    def test_platform_spellings_of_same_genre(self):
        for field in ("인디음악|록/메탈", "인디|락/메탈", "록|인디록", "indie|Rock", "모던록"):
            self.assertEqual(genre.bucket_of(field), "rock", field)
        for field in ("R&B/Soul|인디음악", "알앤비/소울|인디", "알앤비|소울|인디팝"):
            self.assertEqual(genre.bucket_of(field), "rnb", field)
        self.assertEqual(genre.bucket_of("랩/힙합|인디음악"), "hiphop")
        self.assertEqual(genre.bucket_of("Hip Hop|Jazz"), "hiphop")
        self.assertEqual(genre.bucket_of("인디음악|포크/블루스"), "folk")
        self.assertEqual(genre.bucket_of("포크/어쿠스틱|인디"), "folk")
        self.assertEqual(genre.bucket_of("인디 일렉트로닉"), "electronic")
        self.assertEqual(genre.bucket_of("일렉트로니카"), "electronic")
        self.assertEqual(genre.bucket_of("Jazz"), "jazz")
        self.assertEqual(genre.bucket_of("발라드|인디팝"), "pop")
        self.assertEqual(genre.bucket_of("Dance|Pop"), "pop")
        self.assertEqual(genre.bucket_of("뉴에이지"), "other")
        self.assertEqual(genre.bucket_of("Korean Traditional"), "other")

    def test_scene_tags_alone_are_not_a_genre(self):
        for field in ("인디", "인디음악", "indie", "인디|가요", "인디음악|국내드라마"):
            self.assertEqual(genre.bucket_of(field), "", field)

    def test_empty_and_unknown(self):
        self.assertEqual(genre.bucket_of(""), "")
        self.assertEqual(genre.bucket_of(None), "")
        self.assertEqual(genre.bucket_of("뭔지모를태그"), "")

    def test_priority_specific_beats_catch_all(self):
        # 발라드·인디팝은 거의 모든 곡에 붙는 넓은 이름이라 다른 갈래가 있으면 진다
        self.assertEqual(genre.bucket_of("인디음악|발라드|록/메탈"), "rock")
        self.assertEqual(genre.bucket_of("발라드|인디포크"), "folk")
        self.assertEqual(genre.bucket_of("인디팝|알앤비"), "rnb")
        # 힙합은 록과 같이 붙어도 힙합
        self.assertEqual(genre.bucket_of("인디음악|랩/힙합|록/메탈"), "hiphop")
        # 태그 순서는 결과에 영향 없음
        self.assertEqual(genre.bucket_of("인디팝|록"), genre.bucket_of("록|인디팝"))

    def test_keyword_fallback_for_unseen_tags(self):
        self.assertEqual(genre.bucket_of("슈게이즈"), "rock")
        self.assertEqual(genre.bucket_of("korean underground rap"), "hiphop")
        self.assertEqual(genre.bucket_of("시티팝"), "pop")

    def test_metal_and_hardcore_have_own_bucket(self):
        # 메탈·하드코어 갈래 (2026-11-27 상위 50 표본 검증: 메탈 계열 7팀이 '록·밴드'·빈칸에 묻힘)
        for field in ("메탈", "헤비메탈", "Metalcore", "하드코어", "hardcore punk", "korean metal", "뉴메탈"):
            self.assertEqual(genre.bucket_of(field), "metal", field)
        # 플랫폼의 합친 태그 '록/메탈'은 록인지 메탈인지 모르므로 그대로 록
        self.assertEqual(genre.bucket_of("인디음악|록/메탈"), "rock")
        self.assertEqual(genre.bucket_of("펑크"), "rock")
        self.assertEqual(genre.load_config()["buckets"]["metal"]["label"], "메탈·하드코어")

    def test_spacing_and_case_ignored(self):
        self.assertEqual(genre.bucket_of(" r&b/soul | INDIE "), "rnb")


class BucketsOfTest(unittest.TestCase):
    def test_all_buckets_in_priority_order_without_duplicates(self):
        self.assertEqual(genre.buckets_of("인디음악|록/메탈|포크/블루스"), ["folk", "rock"])
        self.assertEqual(genre.buckets_of("록|인디록|인디팝"), ["rock", "pop"])
        self.assertEqual(genre.buckets_of("인디|가요"), [])

    def test_unknown_tags_listed(self):
        self.assertEqual(genre.unknown_tags("인디|뭔지모를태그|록"), ["뭔지모를태그"])


class ConfigTest(unittest.TestCase):
    def test_config_is_consistent(self):
        cfg = genre.load_config()
        self.assertTrue(6 <= len(cfg["buckets"]) <= 10)
        self.assertEqual(sorted(cfg["priority"]), sorted(cfg["buckets"]))
        for key, b in cfg["buckets"].items():
            self.assertTrue(b["label"], key)
            self.assertIn("everynoise", b)
        seen = {}
        for key, b in cfg["buckets"].items():
            for tag in b["tags"]:
                self.assertNotIn(tag.lower(), seen, f"{tag} 가 {seen.get(tag.lower())}, {key} 두 곳에 있음")
                seen[tag.lower()] = key


class DistributionTest(unittest.TestCase):
    def test_counts_dedupe_reruns_and_report_coverage(self):
        with tempfile.TemporaryDirectory() as d:
            header = ["source", "source_id", "genre"]
            rows = [["bugs", "1", "인디|락/메탈"], ["bugs", "2", "인디"], ["bugs", "3", "발라드|인디"]]
            for name in ("raw_kr_release_2026-11-26_bugs.csv", "raw_kr_release_2026-11-26_bugs_2130.csv"):
                with open(Path(d) / name, "w", encoding="utf-8", newline="") as f:
                    w = csv.writer(f)
                    w.writerow(header)
                    w.writerows(rows)
            stats = genre.distribution(d)
        bugs = stats["release"]["bugs"]
        self.assertEqual(bugs["rows"], 3)
        self.assertEqual(bugs["mapped"], 2)
        self.assertEqual(bugs["buckets"], {"rock": 1, "pop": 1})


if __name__ == "__main__":
    unittest.main()
