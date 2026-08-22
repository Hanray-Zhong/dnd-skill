from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from typing import cast
import uuid
from tests.facade_support import run_facade


def complete_configuration() -> dict[str, object]:
    return {
        "players": [
            {
                "player_id": "alice",
                "display_name": "艾莉丝",
                "character_ids": ["aria"],
                "confirmed": True,
                "roll_policy": "player_rolls",
                "absence_policy": {"mode": "narrative_exit"},
                "pvp_preferences": {
                    "violence": "allow",
                    "theft": "ask",
                },
                "preferences": {
                    "content": ["探索"],
                    "avoid": [],
                    "interaction": "balanced",
                    "hint_level": "standard",
                    "rules_detail": "standard",
                },
            },
            {
                "player_id": "bob",
                "display_name": "鲍勃",
                "character_ids": ["borin"],
                "confirmed": True,
                "roll_policy": "script_rolls",
                "absence_policy": {
                    "mode": "delegate",
                    "delegate_player_id": "alice",
                },
                "pvp_preferences": {
                    "violence": "ask",
                    "theft": "forbid",
                },
                "preferences": {
                    "content": ["社交"],
                    "avoid": ["蜘蛛"],
                    "interaction": "roleplay",
                    "hint_level": "direct",
                    "rules_detail": "brief",
                },
            },
        ],
        "safety": {
            "boundaries": ["不描写蜘蛛细节"],
            "confirmed_by": ["alice", "bob"],
        },
        "difficulty": "challenging",
        "advancement": "milestone",
        "private_roll_policy": "dice_engine",
        "pvp_categories": ["violence", "theft"],
    }

class SessionZeroFacadeTests(unittest.TestCase):
    def test_session_zero_completes_and_reopens_the_confirmed_table(self) -> None:
        configuration = complete_configuration()
        expected_configuration = {
            **configuration,
            "pvp_policy": {
                "violence": "ask",
                "theft": "forbid",
            },
        }
        expected_audiences = {
            "dm": {"audience_type": "dm", "members": []},
            "player:alice": {
                "audience_type": "player",
                "members": ["alice"],
            },
            "player:bob": {
                "audience_type": "player",
                "members": ["bob"],
            },
            "table": {
                "audience_type": "table",
                "members": ["alice", "bob"],
            },
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "campaign"
            create_result = run_facade("create", str(workspace))
            self.assertEqual(0, create_result.returncode, msg=create_result.stderr)

            complete_result = run_facade(
                "session-zero",
                str(workspace),
                "--expected-revision",
                "1",
                "--idempotency-key",
                "complete-session-zero-v1",
                "--configuration",
                json.dumps(configuration, ensure_ascii=False),
            )

            completed = (
                json.loads(complete_result.stdout) if complete_result.stdout else None
            )
            open_result = run_facade("open", str(workspace))
            opened = json.loads(open_result.stdout) if open_result.stdout else None
            event_id_is_uuid = False
            if isinstance(completed, dict) and isinstance(
                completed.get("transaction"), dict
            ):
                event_id = completed["transaction"].get("event_id")
                if isinstance(event_id, str):
                    event_id_is_uuid = str(uuid.UUID(event_id)) == event_id

            self.assertEqual(
                {
                    "complete_returncode": 0,
                    "operation": "session-zero",
                    "revision": 2,
                    "campaign_status": "ready_to_play",
                    "continuation": {
                        "allowed": True,
                        "next_step": "start_session",
                        "ready_to_play": True,
                    },
                    "configuration": expected_configuration,
                    "audiences": expected_audiences,
                    "transaction": {
                        "audience_id": "dm",
                        "idempotency_key": "complete-session-zero-v1",
                        "replayed": False,
                        "source": "dnd-5e-campaign-start",
                    },
                    "event_id_is_uuid": True,
                    "open_returncode": 0,
                    "open_revision": 2,
                    "open_status": "ready_to_play",
                    "open_configuration": expected_configuration,
                    "open_audiences": expected_audiences,
                },
                {
                    "complete_returncode": complete_result.returncode,
                    "operation": (
                        completed.get("operation")
                        if isinstance(completed, dict)
                        else None
                    ),
                    "revision": (
                        completed.get("revision")
                        if isinstance(completed, dict)
                        else None
                    ),
                    "campaign_status": (
                        completed.get("campaign_status")
                        if isinstance(completed, dict)
                        else None
                    ),
                    "continuation": (
                        completed.get("continuation")
                        if isinstance(completed, dict)
                        else None
                    ),
                    "configuration": (
                        completed.get("initial_config")
                        if isinstance(completed, dict)
                        else None
                    ),
                    "audiences": (
                        completed.get("audiences")
                        if isinstance(completed, dict)
                        else None
                    ),
                    "transaction": (
                        {
                            "audience_id": completed["transaction"].get(
                                "audience_id"
                            ),
                            "idempotency_key": completed["transaction"].get(
                                "idempotency_key"
                            ),
                            "replayed": completed["transaction"].get(
                                "replayed"
                            ),
                            "source": completed["transaction"].get("source"),
                        }
                        if isinstance(completed, dict)
                        and isinstance(completed.get("transaction"), dict)
                        else None
                    ),
                    "event_id_is_uuid": event_id_is_uuid,
                    "open_returncode": open_result.returncode,
                    "open_revision": (
                        opened.get("revision") if isinstance(opened, dict) else None
                    ),
                    "open_status": (
                        opened.get("campaign_status")
                        if isinstance(opened, dict)
                        else None
                    ),
                    "open_configuration": (
                        opened.get("initial_config")
                        if isinstance(opened, dict)
                        else None
                    ),
                    "open_audiences": (
                        opened.get("audiences")
                        if isinstance(opened, dict)
                        else None
                    ),
                },
                msg=complete_result.stderr or open_result.stderr,
            )

    def test_session_zero_expands_every_default_before_starting_play(self) -> None:
        configuration: dict[str, object] = {
            "players": [
                {
                    "player_id": "alice",
                    "display_name": "艾莉丝",
                    "character_ids": ["aria"],
                    "confirmed": True,
                    "preferences": {},
                },
                {
                    "player_id": "bob",
                    "display_name": "鲍勃",
                    "character_ids": ["borin"],
                    "confirmed": True,
                    "preferences": {},
                },
            ],
            "safety": {
                "boundaries": [],
                "confirmed_by": ["alice", "bob"],
            },
            "pvp_categories": ["violence"],
        }
        expected_players = [
            {
                **player,
                "absence_policy": {"mode": "narrative_exit"},
                "pvp_preferences": {"violence": "forbid"},
                "roll_policy": "player_rolls",
            }
            for player in cast(
                list[dict[str, object]],
                configuration["players"],
            )
        ]
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
                "default-session-zero-v1",
                "--configuration",
                json.dumps(configuration, ensure_ascii=False),
            )
            payload = json.loads(result.stdout) if result.stdout else None

            self.assertEqual(
                {
                    "returncode": 0,
                    "status": "ready_to_play",
                    "defaults": {
                        "advancement": "xp",
                        "difficulty": "standard",
                        "private_roll_policy": "dice_engine",
                    },
                    "players": expected_players,
                    "pvp_policy": {"violence": "forbid"},
                },
                {
                    "returncode": result.returncode,
                    "status": (
                        payload.get("campaign_status")
                        if isinstance(payload, dict)
                        else None
                    ),
                    "defaults": (
                        {
                            "advancement": payload["initial_config"].get(
                                "advancement"
                            ),
                            "difficulty": payload["initial_config"].get(
                                "difficulty"
                            ),
                            "private_roll_policy": payload[
                                "initial_config"
                            ].get("private_roll_policy"),
                        }
                        if isinstance(payload, dict)
                        and isinstance(payload.get("initial_config"), dict)
                        else None
                    ),
                    "players": (
                        payload["initial_config"].get("players")
                        if isinstance(payload, dict)
                        and isinstance(payload.get("initial_config"), dict)
                        else None
                    ),
                    "pvp_policy": (
                        payload["initial_config"].get("pvp_policy")
                        if isinstance(payload, dict)
                        and isinstance(payload.get("initial_config"), dict)
                        else None
                    ),
                },
                msg=result.stderr,
            )
