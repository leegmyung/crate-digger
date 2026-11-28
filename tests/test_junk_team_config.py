"""떠오르는 5에 섞인 계정·일반어 이름 정리 (2026-11-28 홈 점검) — 사람이 확인한 결정이 설정에 들어 있는지.

- service · PERMIT: 같은 인스타 글(기글링 서울 파티 홍보)에서 행사 계정(@ceilingservice · @permit_invites)의 끝말이 팀 이름으로 잡힘 → 팀 표에서 뺌
- heymeg10: 클럽 파티(갈락티크·Floor 2 Floor) DJ 개인 계정 → 팀 표에서 뺌
- HUQUEYMSAW: 인디스트릿 공연(2026-09-12 클럽샤프)에도 있는 실제 팀 → 그대로
- GongGongGoo009: 래퍼 공공구(한국힙합어워즈 2023 올해의 신인) — 실제 팀, 화면 이름만 한글(display=true, 팀 키는 그대로)
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import artist_xref as ax  # noqa: E402


class JunkTeamConfigTest(unittest.TestCase):
    roles = json.loads((ROOT / "config" / "source_roles.json").read_text(encoding="utf-8"))
    aliases = json.loads((ROOT / "config" / "artist_aliases.json").read_text(encoding="utf-8"))

    def test_account_words_excluded_from_team_table(self):
        excluded = self.roles["candidate_rules"]["excluded_teams"]
        for key in ("service", "permit", "heymeg10"):
            self.assertIn(key, excluded, key)
            self.assertTrue(excluded[key].strip(), key)
        self.assertNotIn("huqueymsaw", excluded)      # 실제 팀

    def test_event_accounts_marked_non_artist(self):
        handles = {e["handle"] for e in self.aliases["non_artist_handles"]}
        self.assertTrue({"ceilingservice", "permit_invites"} <= handles)

    def test_gonggonggoo_display_in_korean(self):
        entries = ax.load_manual_aliases(ROOT / "config" / "artist_aliases.json")   # 형식 검사도 통과해야
        e = next(x for x in entries if x["main"] == "공공구")
        self.assertIn("GongGongGoo009", e["aliases"])
        self.assertIs(e.get("display"), True)


if __name__ == "__main__":
    unittest.main()
