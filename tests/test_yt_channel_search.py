"""yt_channel_search.py — 유튜브 채널 검색(search.list type=channel) 결과에서 팀 채널 고르기 테스트. 네트워크 없이.
정답지: 2026-11-28 시험 10팀(상위 300, 유튜브 링크 없음)의 실제 검색 결과 채널 이름 — 눈으로 확인한 정답과 같아야 한다."""
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import collect_videos as cv  # noqa: E402
import yt_channel_search as ys  # noqa: E402


def res(*titles):
    return [{"id": f"UC{i:022d}", "title": t} for i, t in enumerate(titles)]


TRIAL = [   # (팀 이름들, 검색 결과 채널 이름, 정답 순번 또는 None, 최신 영상 제목 {순번: [...]})
    (["선셋 온 더 브릿지", "Sunset On The Bridge"],
     res("선셋온더브릿지", "Sunset On The Bridge - Topic", "sKithanN", "Cloud Kang ", "홍새벽"), 0, {}),
    (["포스트이너서클", "Post Inner Circle"],
     res("Post Inner Circle - Topic", "포스트이너서클 postinnercircle", "서원", "fck", "공상온도"), 1, {}),
    (["줄라이원츠모어", "JULYWANTSMORE"], res("Julywantsmore", "zZ", "Julywantsmore - Topic", "Soleil::", "2012s"), 0, {}),
    (["서울스핏", "SEOUL SPIT"], res("S.D.V RECORDS", "스핏뉴스 SPITNEWS", "슥슥이SSG", "hymoon", "JINIDANCE_official"), None, {}),
    (["스웰시티", "SWELL CITY"],
     res("SWELL CITY - Topic", "SWELL CITY (스웰시티)", "빅토르 [ Victor.L ]", "Live K-Indie Music", "Swedish House Mafia - Topic"), 1, {}),
    (["스키틀즈", "Skittles"],
     res("Skittles - Topic", "스키틀즈 SKITTLES", "스키틀즈skittles", "스키틀즈", "스키틀즈 캐티 Skittle C"), 1,
     {1: ["청춘박살 - 스키틀즈 SKITTLES (Live Session)", "[MV] 스키틀즈 (SKITTLES) - Unknown (Official Video)"],
      2: ["160924 이제훈 팬미팅 - 노래가 끝이 나고"], 3: []}),
    (["neverandno", "네버앤노"], res("neverandno(네버앤노) official", "neverandno - Topic", "uooy_drum&bass", "oyasumifilm"), 0, {}),
    (["웬즈데이오프", "Wednesday Off"], res("Wednesday Off - Topic", "Wednesday off", "GMJ51", "ride&live", "무비파티"), 1, {}),
    (["캐주얼리커넥티드", "CASUALLY CONNECTED"], res("CASUALLY CONNECTED"), 0, {}),
    (["파이프립스", "Pipe Lips"], res("Pipe Lips - Topic", "노마드 루이스", "지무비 : G Movie", "Arie Lips", "Cardi B - Topic"), None, {}),
]


class NameKeysTest(unittest.TestCase):
    def test_pieces(self):
        self.assertEqual(ys.channel_name_keys("SWELL CITY (스웰시티)"), ({"swellcity", "스웰시티"}, False))
        keys, topic = ys.channel_name_keys("Pipe Lips - Topic")
        self.assertEqual((keys, topic), ({"pipelips"}, True))
        self.assertIn("neverandno", ys.channel_name_keys("neverandno(네버앤노) official")[0])
        self.assertNotIn("스키틀즈", ys.channel_name_keys("스키틀즈 캐티 Skittle C")[0])


class ChooseTest(unittest.TestCase):
    def test_trial_ten_teams_match_hand_checked_answers(self):
        for names, results, want, latest in TRIAL:
            with self.subTest(team=names[0]):
                got = ys.choose_channel(names, results, lambda cid, lt=latest: lt.get(int(cid[2:]), []))
                self.assertEqual(got and got["id"], results[want]["id"] if want is not None else None)

    def test_topic_flag_and_official_preferred(self):
        names, results, _, _ = TRIAL[0]
        self.assertFalse(ys.choose_channel(names, results, lambda c: [])["topic"])

    def test_topic_only_with_release_title_overlap(self):
        # Topic(유튜브 자동 채널)은 동명 위험이 커서 우리 발매 기록의 곡 제목이 그 채널 영상 제목과 겹칠 때만
        names, results, _, _ = TRIAL[-1]
        latest = lambda c: ["Mr. Nobody", "Himizu"]     # noqa: E731
        got = ys.choose_channel(names, results, latest, our_titles=["Himizu"])
        self.assertEqual((got["id"], got["topic"], got["verified"]), (results[0]["id"], True, True))
        self.assertIsNone(ys.choose_channel(names, results, latest, our_titles=["다른 노래"]))
        self.assertIsNone(ys.choose_channel(names, results, latest))
        # 허재혁 - Topic: 발매 기록 없음 → 연결 안 함
        self.assertIsNone(ys.choose_channel(["허재혁"], res("허재혁 - Topic", "허재혁의 일상"), lambda c: ["잠수"]))

    def test_two_topic_channels_with_same_name_skip(self):
        self.assertIsNone(ys.choose_channel(["Pipe Lips"], res("Pipe Lips - Topic", "Pipe Lips - Topic"), lambda c: []))


class FakeClient:
    def __init__(self, by_query, budget=10000):
        self.by_query, self.calls, self.quota = by_query, [], cv.Quota(budget)

    def get(self, endpoint, params, cost):
        self.quota.spend(cost)
        self.calls.append(endpoint)
        if endpoint == "search":
            return {"items": [{"snippet": {"channelId": r["id"], "channelTitle": r["title"]}}
                              for r in self.by_query.get(params["q"], [])]}
        return {"items": [{"snippet": {"title": t}} for t in getattr(self, "get_titles", [])]}


class RunTest(unittest.TestCase):
    def test_daily_cap_and_recheck_interval(self):
        targets = [{"team_key": f"t{i}", "display_name": f"팀이름{i}번", "rank": i + 1} for i in range(5)]
        client = FakeClient({"팀이름0번": res("팀이름0번")})
        state = ys.run(targets, {}, {}, client, date(2026, 11, 28), max_searches=2)
        self.assertEqual(state["t0"]["channel_id"], "UC" + "0" * 22)
        self.assertEqual(state["t1"], {"checked": "2026-11-28", "channel_id": "", "terms": ["팀이름1번"]})
        self.assertNotIn("t2", state)
        self.assertEqual(client.calls, ["search", "search"])
        again = FakeClient({})
        ys.run(targets, {}, state, again, date(2026, 12, 1), max_searches=10)
        self.assertEqual(again.calls.count("search"), 3)      # t0·t1 은 다시 안 찾음

    def test_skips_teams_beyond_top_rank_and_short_names(self):
        targets = [{"team_key": "far", "display_name": "먼팀이름", "rank": 400},
                   {"team_key": "short", "display_name": "모래", "rank": 3}]
        client = FakeClient({})
        self.assertEqual(ys.run(targets, {}, {}, client, date(2026, 11, 28)), {})
        self.assertEqual(client.calls, [])

    def test_release_titles_are_passed_for_topic_check(self):
        targets = [{"team_key": "pl", "display_name": "파이프립스", "rank": 1}]
        client = FakeClient({"파이프립스": res("Pipe Lips - Topic")})
        client.get_titles = ["Himizu"]
        state = ys.run(targets, {"pl": ["Pipe Lips"]}, {}, client, date(2026, 11, 28), releases={"pl": ["Himizu"]})
        self.assertEqual(state["pl"]["channel_id"], "UC" + "0" * 22)
        self.assertTrue(state["pl"]["verified"])

    def test_english_name_searched_when_korean_finds_nothing(self):
        targets = [{"team_key": "소여", "display_name": "소여밴드", "rank": 1}]
        client = FakeClient({"소여밴드": res("다른 채널"), "Sawyer": res("Sawyer")})
        state = ys.run(targets, {}, {}, client, date(2026, 11, 28), en_names={"소여": ["Sawyer"]})
        self.assertEqual(client.calls.count("search"), 2)
        self.assertEqual(state["소여"]["title"], "Sawyer")
        self.assertEqual(state["소여"]["terms"], ["소여밴드", "Sawyer"])

    def test_fresh_miss_retried_only_with_new_english_terms_within_cap(self):
        targets = [{"team_key": "소여", "display_name": "소여밴드", "rank": 1},
                   {"team_key": "b", "display_name": "비밴드이름", "rank": 2}]
        old = {"소여": {"checked": "2026-11-20", "channel_id": "", "terms": ["소여밴드"]}}
        client = FakeClient({"Sawyer": res("Sawyer")})
        state = ys.run(targets, {}, old, client, date(2026, 11, 28), max_searches=1, en_names={"소여": ["Sawyer"]})
        self.assertEqual(client.calls.count("search"), 1)          # 영문 1번만 (하루 상한 1)
        self.assertEqual(state["소여"]["title"], "Sawyer")
        self.assertNotIn("b", state)

    def test_aliases_are_used_for_matching(self):
        targets = [{"team_key": "sw", "display_name": "스웰시티", "rank": 1}]
        client = FakeClient({"스웰시티": res("SWELL CITY")})
        state = ys.run(targets, {"sw": ["스웰시티", "SWELL CITY"]}, {}, client, date(2026, 11, 28))
        self.assertEqual(state["sw"]["title"], "SWELL CITY")


if __name__ == "__main__":
    unittest.main()
