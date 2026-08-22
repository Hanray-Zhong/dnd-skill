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
                "roll_policy": "player_rolls",
                "absence_policies": {
                    "aria": {"mode": "narrative_exit"},
                },
                "pvp_preferences": {"violence": "allow"},
            },
            {
                "player_id": "bob",
                "display_name": "鲍勃",
                "character_ids": ["borin"],
                "confirmed": True,
                "preferences": {},
                "roll_policy": "script_rolls",
                "absence_policies": {
                    "borin": {
                        "mode": "delegate",
                        "delegate_player_id": "alice",
                    },
                },
                "pvp_preferences": {"violence": "ask"},
            },
            {
                "player_id": "cara",
                "display_name": "卡拉",
                "character_ids": ["cinder"],
                "confirmed": True,
                "preferences": {},
                "roll_policy": "player_rolls",
                "absence_policies": {
                    "cinder": {"mode": "agent_custody"},
                },
                "pvp_preferences": {"violence": "allow"},
            },
            {
                "player_id": "dan",
                "display_name": "丹",
                "character_ids": ["dorian"],
                "confirmed": True,
                "preferences": {},
                "roll_policy": "script_rolls",
                "absence_policies": {
                    "dorian": {"mode": "narrative_exit"},
                },
                "pvp_preferences": {"violence": "forbid"},
            },
        ]
        configuration: dict[str, object] = {
            "players": players,
            "safety": {
                "boundaries": [],
                "confirmed_by": ["alice", "bob", "cara", "dan"],
            },
            "pvp_categories": ["violence"],
            "difficulty": "standard",
            "advancement": "xp",
            "private_roll_policy": "dice_engine",
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
                    "absence_modes": (
                        {
                            character_id: policy.get("mode")
                            for character_id, policy in absence_policies.items()
                            if isinstance(character_id, str)
                            and isinstance(policy, dict)
                        }
                        if isinstance(
                            absence_policies := player.get("absence_policies"),
                            dict,
                        )
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
                            "absence_modes": {"aria": "narrative_exit"},
                        },
                        "bob": {
                            "roll_policy": "script_rolls",
                            "absence_modes": {"borin": "delegate"},
                        },
                        "cara": {
                            "roll_policy": "player_rolls",
                            "absence_modes": {"cinder": "agent_custody"},
                        },
                        "dan": {
                            "roll_policy": "script_rolls",
                            "absence_modes": {"dorian": "narrative_exit"},
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

    def test_one_player_can_set_distinct_absence_policies_per_character(
        self,
    ) -> None:
        configuration: dict[str, object] = {
            "players": [
                {
                    "player_id": "alice",
                    "display_name": "艾莉丝",
                    "character_ids": ["aria", "ember"],
                    "confirmed": True,
                    "preferences": {},
                    "roll_policy": "player_rolls",
                    "absence_policies": {
                        "aria": {"mode": "narrative_exit"},
                        "ember": {"mode": "agent_custody"},
                    },
                    "pvp_preferences": {"violence": "forbid"},
                }
            ],
            "safety": {"boundaries": [], "confirmed_by": ["alice"]},
            "difficulty": "standard",
            "advancement": "xp",
            "private_roll_policy": "dice_engine",
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
                "per-character-absence-v1",
                "--configuration",
                json.dumps(configuration, ensure_ascii=False),
            )
            payload = json.loads(result.stdout) if result.stdout else None
            completed_players = (
                payload["initial_config"].get("players")
                if isinstance(payload, dict)
                and isinstance(payload.get("initial_config"), dict)
                else None
            )
            completed_player = (
                completed_players[0]
                if isinstance(completed_players, list)
                and completed_players
                and isinstance(completed_players[0], dict)
                else None
            )

            self.assertEqual(
                {
                    "returncode": 0,
                    "status": "ready_to_play",
                    "absence_policies": {
                        "aria": {"mode": "narrative_exit"},
                        "ember": {"mode": "agent_custody"},
                    },
                    "has_player_level_absence_policy": False,
                },
                {
                    "returncode": result.returncode,
                    "status": (
                        payload.get("campaign_status")
                        if isinstance(payload, dict)
                        else None
                    ),
                    "absence_policies": (
                        completed_player.get("absence_policies")
                        if isinstance(completed_player, dict)
                        else None
                    ),
                    "has_player_level_absence_policy": (
                        "absence_policy" in completed_player
                        if isinstance(completed_player, dict)
                        else None
                    ),
                },
                msg=result.stderr,
            )
