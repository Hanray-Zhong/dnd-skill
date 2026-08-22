from __future__ import annotations

import json
import unittest

from tests.facade_support import SKILL_IDS, run_facade


class SkillCatalogFacadeTests(unittest.TestCase):
    def test_list_skills_returns_the_exact_public_catalog(self) -> None:
        result = run_facade("list-skills")
        payload = json.loads(result.stdout) if result.stdout else None

        self.assertEqual(
            (
                0,
                {
                    "ok": True,
                    "skills": [
                        {
                            "id": skill_id,
                            "player_facade": skill_id == "dnd-5e",
                        }
                        for skill_id in SKILL_IDS
                    ],
                },
            ),
            (result.returncode, payload),
            msg=result.stderr,
        )


if __name__ == "__main__":
    unittest.main()
