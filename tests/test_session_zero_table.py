from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from tests.facade_support import run_facade


class SessionZeroTableFacadeTests(unittest.TestCase):
    def test_four_players_confirm_distinct_roll_and_absence_policies(self) -> None:
        players: list[dict[str, object]] = [
            {
                "player_id": "alice",
                "display_name": "艾莉丝",
                "character_ids": ["aria"],
                "confirmed": True,
                "preferences": {},
                "pvp_preferences": {"violence": "allow"},
            },
            {
                "player_id": "bob",
                "display_name": "鲍勃",
                "character_ids": ["borin"],
                "confirmed": True,
                "preferences": {},
                "roll_policy": "script_rolls",
                "absence_policy": {
                    "mode": "delegate",
                    "delegate_player_id": "alice",
                },
                "pvp_preferences": {"violence": "ask"},
            },
            {
                "player_id": "cara",
                "display_name": "卡拉",
                "character_ids": ["cinder"],
                "confirmed": True,
                "preferences": {},
                "absence_policy": {"mode": "agent_custody"},
                "pvp_preferences": {"violence": "allow"},
            },
            {
                "player_id": "dan",
                "display_name": "丹",
                "character_ids": ["dorian"],
                "confirmed": True,
                "preferences": {},
                "roll_policy": "script_rolls",
            },
        ]
        configuration: dict[str, object] = {
            "players": players,
            "safety": {
                "boundaries": [],
                "confirmed_by": ["alice", "bob", "cara", "dan"],
            },
            "pvp_categories": ["violence"],
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "campaign"
            create_result = run_facade("create", str(workspace))
            self.assertEqual(0, create_result.returncode, msg=create_result.stderr)

            result = run_facade(
                "session-zero",
                str(workspace),
                "--expected-revision",
                "1",
                "--idempotency-key",
                "four-player-session-zero-v1",
                "--configuration",
                json.dumps(configuration, ensure_ascii=False),
            )
            payload = json.loads(result.stdout) if result.stdout else None
            completed_config = (
                payload.get("initial_config") if isinstance(payload, dict) else None
            )
            completed_players = (
                completed_config.get("players")
                if isinstance(completed_config, dict)
                else None
            )
            if not isinstance(completed_players, list):
                raise AssertionError("完成结果必须展示玩家名单")
            policies = {
                player["player_id"]: {
                    "roll_policy": player.get("roll_policy"),
                    "absence_mode": (
                        player["absence_policy"].get("mode")
                        if isinstance(player.get("absence_policy"), dict)
                        else None
                    ),
                }
                for player in completed_players
                if isinstance(player, dict)
            }

            self.assertEqual(
                {
                    "returncode": 0,
                    "status": "ready_to_play",
                    "pvp_policy": {"violence": "forbid"},
                    "audience_ids": [
                        "dm",
                        "player:alice",
                        "player:bob",
                        "player:cara",
                        "player:dan",
                        "table",
                    ],
                    "policies": {
                        "alice": {
                            "roll_policy": "player_rolls",
                            "absence_mode": "narrative_exit",
                        },
                        "bob": {
                            "roll_policy": "script_rolls",
                            "absence_mode": "delegate",
                        },
                        "cara": {
                            "roll_policy": "player_rolls",
                            "absence_mode": "agent_custody",
                        },
                        "dan": {
                            "roll_policy": "script_rolls",
                            "absence_mode": "narrative_exit",
                        },
                    },
                },
                {
                    "returncode": result.returncode,
                    "status": (
                        payload.get("campaign_status")
                        if isinstance(payload, dict)
                        else None
                    ),
                    "pvp_policy": (
                        completed_config.get("pvp_policy")
                        if isinstance(completed_config, dict)
                        else None
                    ),
                    "audience_ids": (
                        sorted(payload["audiences"])
                        if isinstance(payload, dict)
                        and isinstance(payload.get("audiences"), dict)
                        else None
                    ),
                    "policies": policies,
                },
                msg=result.stderr,
            )
