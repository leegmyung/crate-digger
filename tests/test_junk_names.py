"""팀이 아닌 이름 모양 규칙 (scripts/junk_names.py, config/source_roles.json candidate_rules.name_patterns)."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import junk_names as jn  # noqa: E402


class RuleTest(unittest.TestCase):
    """실제 설정 파일 규칙으로: 주소는 늘 빼고, 도메인·@계정·계정 모양은 인스타에서만 나온 이름일 때만 뺀다."""

    @classmethod
    def setUpClass(cls):
        cls.rules = jn.load_name_rules()

    def reason(self, name, sources):
        return jn.junk_reason(name, set(sources), self.rules)

    def test_url_always_junk(self):
        self.assertTrue(self.reason("https.jester.co.kr", ["instagram"]))
        self.assertTrue(self.reason("https://example.com/x", ["indistreet"]))

    def test_handle_and_domain_only_when_instagram_only(self):
        self.assertTrue(self.reason("hivepark_kr", ["instagram"]))
        self.assertTrue(self.reason("naiite.grind", ["instagram"]))
        self.assertTrue(self.reason("ssmadang.co.kr", ["instagram"]))
        self.assertTrue(self.reason("@real1ight", ["instagram"]))
        self.assertFalse(self.reason("quinn_", ["indistreet", "instagram"]))     # 인디스트릿에도 있는 실제 이름
        self.assertFalse(self.reason("mong_gle", ["yjh"]))
        self.assertFalse(self.reason("DJ co.kr", ["trackzero", "visla"]))

    def test_real_names_kept(self):
        for name in ("0siggy", "250", "109", "pa de haan.", "포져군단", "Moon Go America", "PCR", "Mr.Hong"):
            self.assertFalse(self.reason(name, ["instagram"]), name)

    def test_rules_have_reasons(self):
        self.assertTrue(self.rules)
        for r in self.rules:
            self.assertTrue(r["reason"])


class NameSourcesTest(unittest.TestCase):
    def test_sources_per_key_from_raw_files(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "raw_kr_gig_2026-11-01_instagram.csv").write_text(
                "collected_at,source,artist_text\nx,instagram,hivepark_kr\nx,instagram,quinn_\n", encoding="utf-8")
            (d / "raw_kr_gig_2026-11-01_indistreet.csv").write_text(
                "collected_at,source,artist_text\nx,indistreet,quinn_\n", encoding="utf-8")
            (d / "raw_outcome_2026-11-01_manual.csv").write_text(
                "collected_at,source,artist_text\nx,manual,hivepark_kr\n", encoding="utf-8")   # 정답 표는 신호 출처가 아님
            (d / "raw_artist_profile_2026-11-01_melon.csv").write_text(
                "collected_at,source,artist_text\nx,melon,television.off\n", encoding="utf-8")  # 멜론 프로필이 있으면 실제 팀
            (d / "raw_kr_gig_2026-11-02_instagram.csv").write_text(
                "collected_at,source,artist_text\nx,instagram,television.off\n", encoding="utf-8")
            out = jn.name_sources(d, key_of=str.lower)
            self.assertEqual(out["television.off"]["sources"], {"instagram", "melon"})
            self.assertEqual(jn.junk_keys({"television.off": out["television.off"]}, jn.load_name_rules()), {})
        self.assertEqual(out["hivepark_kr"]["sources"], {"instagram"})
        self.assertEqual(out["quinn_"]["sources"], {"instagram", "indistreet"})
        self.assertEqual(out["hivepark_kr"]["names"], {"hivepark_kr"})

    def test_junk_keys(self):
        info = {"hivepark_kr": {"sources": {"instagram"}, "names": {"hivepark_kr"}},
                "quinn_": {"sources": {"instagram", "indistreet"}, "names": {"quinn_"}},
                "포져군단": {"sources": {"instagram"}, "names": {"포져군단"}}}
        info["televisionoff"] = {"sources": {"instagram"}, "names": {"television_off", "Television off"}}   # 프로필 이름이 정상
        out = jn.junk_keys(info, jn.load_name_rules())
        self.assertEqual(set(out), {"hivepark_kr"})          # 표기 중 하나라도 정상 이름이면 남김
        self.assertIn("인스타", out["hivepark_kr"])


if __name__ == "__main__":
    unittest.main()
