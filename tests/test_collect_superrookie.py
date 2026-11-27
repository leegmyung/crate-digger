"""슈퍼루키챌린지 수집기 변환 로직 — 네트워크 없이, 루트노트·포크라노스 실제 글에서 잘라 온 조각으로."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import collect_superrookie as sr  # noqa: E402

AT = "2026-11-27T18:00:00+09:00"


def post(pid, date, title, html, link="https://routenote.com/kr/blog/x/"):
    return {"id": pid, "date": date, "link": link, "title": {"rendered": title}, "content": {"rendered": html}}


FEAT_POST = post(1663, "2025-03-13T10:00:00", "🎤 힙합의 새로운 물결이 온다! Super Rookie Challenge – “Season 15 Round 1 Cypher” 발매!",
                 "<p>🎤 Track 1. “얼음” (feat. YUNILI, huka, 천하은, DNYDK, gillass, Klama) – Cypher A팀</p>"
                 "<p>🎤 Track 2. “The Name” (feat. Keylight, ETHN, RUSH, 이규진, 최유담, 18crew, 서록) – Cypher B팀</p>"
                 "<p>✅ Special Guest: 가리온, NWV</p><p>✅ Host: MC SAM, DJ IT</p>")
TOP4_POST = post(1703, "2025-03-25T10:00:00", "🎉우승자 공개, 🔥슈퍼 루키 챌린지 시즌15 Round 1 TOP4!",
                 "<p>지난 3월 14일 Round 1 공연이 마무리되었는데요!</p><p>🎉 ‘Round 1 위너 발표’, 축하드립니다!</p>"
                 "<p>출처 입력</p><p>huka (@molehouse_huka)</p><p>서록 (@its_the_log)</p><p>천하은 (@ten_2zero)</p>"
                 "<p>최유담 (@choiyudam_)</p><p>멋진 무대와 에너지로 관객의 마음을 사로잡은 4팀!</p>"
                 "<p>🎤 루트노트 아티스트</p><p>Outlaw The Artist (@outlawtheartist)</p>",
                 link="https://routenote.com/kr/blog/top4/")
LINEUP_POST = post(1912, "2025-08-19T10:00:00", "[공연] ⚡슈퍼루키챌린지 시즌 16 라운드 1– 홍대 힙합 공연 & 티켓 예매",
                   "<p>​✅ 라인업 공개! (Round 1)</p><p>ENZO @lessgo_enzo</p><p>18crew @jungsin18 @nagisa_kyo</p>"
                   "<p>Seomalone (서말론) @seomalone</p><p>서록 @its_the_log</p>"
                   "<p>✅ Special Guest: Deepflow @deepflow39 huka @molehouse_huka</p>"
                   "<p>✅ Host MC: SAM @sammeesossa DJ: DJ IT @djit_1004</p>")
EN_POST = post(2297, "2026-03-24T10:00:00", "Super Rookie Challenge – Season 17 Round 1 Cypher – 16 Rising MCs",
               "<p>“Gossip” brings together 10 MCs — DICTO, Klama, Artifex, Poeta, JIJI, X33D, Youngchan Song, "
               "CHLALSDUD, Taeyoung, and Jegal Jin — who trade razor-sharp punchlines.</p>"
               "<p>On the flip side, “Be Me” features 6 artists — HRDN, DIGI, JSN .Paak, M’ewn, Haus, and Ruud — who turn the lens inward.</p>"
               "<p>Sounds Like: Changmo, Sik-K, pH-1</p>", link="https://routenote.com/radar/x/")
VOCAL_POST = post(5112, "2026-10-15T10:00:00", "Super Rookie Challenge – Overload Review – Seven R&amp;B Voices",
                  "<p>‘Overload’ is the double-title cypher from Round 1 of Super Rookie Challenge’s first Vocal Season. "
                  "Seven singers share the track: blushii, CHOIJIJI, Paper Cup, YUL2, KEVIN PARK, Xinssy and Minjeong.</p>",
                  link="https://routenote.com/radar/y/")
KO_SENTENCE = post(2142, "2026-03-24T10:00:00", "[Hip-Hop] Super Rookie Challenge (슈퍼루키챌린지) 〈Season 17 Round 1 Cypher〉 발매!",
                   "<p>첫 번째 트랙 “Gossip”에는 DICTO, Klama, X33D(씨드), 제갈진(Jegal Jin) — 4명의 래퍼가 참여했습니다.</p>")
RECRUIT_POST = post(1873, "2025-07-23T10:00:00", "📢 Super Rookie Challenge Season 16 참가자 모집 중❗",
                    "<p>지원 기간: 2025. 08. 07. – 2025. 09. 01.</p>")
POCLANOS = post(58818, "2024-09-12T12:00:32", "Season 14 Round 1 Cypher",
                "<p>01. Super Rookie Challenge – MY ZONE(feat. CLADI, X33D(씨드), 류시형, 기적의 삼총사, 재림, JA!L, Kima Escobar)</p>"
                "<p>Lyrics by CLADI, X33D(씨드), 류시형</p>"
                "<p>02. Super Rookie Challenge – who’s the next up?(feat. NWV, OneAve, DNYDK, Shane, SAM)</p>",
                link="https://poclanos.com/album/season-14-round-1-cypher/")


class RoundTest(unittest.TestCase):
    def test_round_from_title_or_body(self):
        self.assertEqual(sr.parse_round("Season 15 Round 1 Cypher"), "S15 R1")
        self.assertEqual(sr.parse_round("슈퍼루키챌린지 시즌 16 라운드 1– 홍대"), "S16 R1")
        self.assertEqual(sr.parse_round("시즌15 Round 1 TOP4!"), "S15 R1")
        self.assertEqual(sr.parse_round("Round 1 of Super Rookie Challenge’s first Vocal Season"), "Vocal S1 R1")
        self.assertIsNone(sr.parse_round("참가자 모집 중"))


class ExtractTest(unittest.TestCase):
    def test_feat_tracks(self):
        rows = sr.post_rows(FEAT_POST, "routenote", AT)
        names = [r["artist_text"] for r in rows]
        self.assertEqual(len(names), 13)
        self.assertIn("천하은", names)
        self.assertNotIn("가리온", names)                        # 스페셜 게스트는 참가자가 아님
        self.assertEqual({r["stage"] for r in rows}, {"lineup"})
        self.assertEqual({r["round"] for r in rows}, {"S15 R1"})
        self.assertEqual(rows[0]["announced_at"], "2025-03-13")

    def test_top4_handles_are_selected(self):
        rows = sr.post_rows(TOP4_POST, "routenote", AT)
        self.assertEqual([r["artist_text"] for r in rows], ["huka", "서록", "천하은", "최유담"])
        self.assertEqual({r["stage"] for r in rows}, {"selected"})

    def test_lineup_handle_lines_stop_at_guest(self):
        rows = sr.post_rows(LINEUP_POST, "routenote", AT)
        self.assertEqual([r["artist_text"] for r in rows], ["ENZO", "18crew", "Seomalone (서말론)", "서록"])
        self.assertEqual(rows[0]["round"], "S16 R1")

    def test_english_and_korean_sentences(self):
        en = [r["artist_text"] for r in sr.post_rows(EN_POST, "routenote", AT)]
        self.assertEqual(len(en), 16)
        self.assertIn("Jegal Jin", en)
        self.assertIn("JSN .Paak", en)
        self.assertNotIn("Changmo", en)                          # 'Sounds Like' 비교 대상은 빼기
        ko = [r["artist_text"] for r in sr.post_rows(KO_SENTENCE, "routenote", AT)]
        self.assertEqual(ko, ["DICTO", "Klama", "X33D(씨드)", "제갈진(Jegal Jin)"])

    def test_vocal_season(self):
        rows = sr.post_rows(VOCAL_POST, "routenote", AT)
        self.assertEqual(len(rows), 7)
        self.assertEqual(rows[-1]["artist_text"], "Minjeong")
        self.assertEqual(rows[0]["round"], "Vocal S1 R1")

    def test_recruit_post_has_no_rows(self):
        self.assertEqual(sr.post_rows(RECRUIT_POST, "routenote", AT), [])

    def test_poclanos_credits(self):
        rows = sr.post_rows(POCLANOS, "poclanos", AT)
        self.assertEqual(len(rows), 12)                           # Lyrics by 줄은 중복이라 안 셈
        self.assertEqual(rows[0]["source"], "poclanos")
        self.assertEqual(rows[0]["round"], "S14 R1")
        self.assertEqual(set(rows[0]), set(sr.COLUMNS))
        self.assertEqual(rows[0]["program"], "superrookie")


class DedupeStateTest(unittest.TestCase):
    def test_dedupe_same_round_stage_artist(self):
        rows = sr.post_rows(FEAT_POST, "routenote", AT) + sr.post_rows(FEAT_POST, "routenote", AT)
        self.assertEqual(len(sr.dedupe(rows)), 13)

    def test_prefer_korean_blog_post_for_same_round(self):
        # 같은 라운드를 영어 글(RADAR)과 한국어 글(블로그)이 둘 다 다루면 한국어 글만 쓴다 (표기가 달라 중복이 생김)
        rows = sr.rows_from_posts([EN_POST, KO_SENTENCE], "routenote", AT)
        self.assertEqual([r["artist_text"] for r in rows], ["DICTO", "Klama", "X33D(씨드)", "제갈진(Jegal Jin)"])

    def test_dedupe_same_person_with_alias(self):
        a = sr.post_rows(KO_SENTENCE, "routenote", AT)
        b = [dict(r, artist_text="X33D") for r in a[:1]]
        self.assertEqual(len(sr.dedupe(a + b)), 4)                # X33D 와 X33D(씨드)는 같은 사람

    def test_state_new_posts_only(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.json"
            st = sr.load_state(p)
            self.assertEqual(sr.new_posts([FEAT_POST, TOP4_POST], st, "routenote"), [FEAT_POST, TOP4_POST])
            st = sr.mark_seen(st, "routenote", [FEAT_POST["link"]], "2026-11-27")
            sr.save_state(p, st)
            again = sr.load_state(p)
        self.assertEqual(sr.new_posts([FEAT_POST, TOP4_POST], again, "routenote"), [TOP4_POST])
        self.assertEqual(again["last_run"], "2026-11-27")


if __name__ == "__main__":
    unittest.main()
