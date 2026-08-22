from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from tests.facade_support import run_facade
from tests.test_session_zero import complete_configuration


class SessionZeroValidationFacadeTests(unittest.TestCase):
    def assert_invalid_fields(
        self,
        configuration: dict[str, object],
        *,
        idempotency_key: str,
        invalid_fields: list[str],
    ) -> None:
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
                idempotency_key,
                "--configuration",
                json.dumps(configuration, ensure_ascii=False),
            )
            error_payload = json.loads(result.stderr) if result.stderr else None
            open_result = run_facade("open", str(workspace))
            opened = json.loads(open_result.stdout) if open_result.stdout else None

            self.assertEqual(
                {
                    "returncode": 2,
                    "error": {
                        "ok": False,
                        "error": {
                            "code": "invalid_session_zero",
                            "message": "Session Zero 配置包含不支持或无效的决策。",
                            "details": {"invalid_fields": invalid_fields},
                        },
                    },
                    "stdout": "",
                    "open_revision": 1,
                    "open_status": "awaiting_session_zero",
                },
                {
                    "returncode": result.returncode,
                    "error": error_payload,
                    "stdout": result.stdout,
                    "open_revision": (
                        opened.get("revision") if isinstance(opened, dict) else None
                    ),
                    "open_status": (
                        opened.get("campaign_status")
                        if isinstance(opened, dict)
                        else None
                    ),
                },
                msg=result.stderr or open_result.stderr,
            )

    def test_session_zero_rejects_invalid_policies_and_delegation(self) -> None:
        configuration = complete_configuration()
        configuration["advancement"] = "level_on_demand"
        configuration["private_roll_policy"] = "model_rolls"
        players = configuration["players"]
        if (
            not isinstance(players, list)
            or not isinstance(players[0], dict)
            or not isinstance(players[1], dict)
        ):
            raise AssertionError("测试配置必须包含两位玩家")
        players[0]["roll_policy"] = "model_rolls"
        players[0]["pvp_preferences"] = {
            "violence": "sometimes",
            "theft": "ask",
        }
        players[1]["absence_policies"] = {
            "borin": {
                "mode": "delegate",
                "delegate_player_id": "charlie",
            }
        }

        self.assert_invalid_fields(
            configuration,
            idempotency_key="invalid-policy-session-zero-v1",
            invalid_fields=[
                "advancement",
                "players[alice].pvp_preferences.violence",
                "players[alice].roll_policy",
                "players[bob].absence_policies.borin.delegate_player_id",
                "private_roll_policy",
            ],
        )

    def test_session_zero_rejects_invalid_required_values(self) -> None:
        configuration = complete_configuration()
        configuration["difficulty"] = ""
        configuration["pvp_categories"] = []
        safety = configuration["safety"]
        players = configuration["players"]
        if (
            not isinstance(safety, dict)
            or not isinstance(players, list)
            or not isinstance(players[0], dict)
        ):
            raise AssertionError("测试配置结构无效")
        safety["boundaries"] = "none"
        players[0]["display_name"] = ""
        players[0]["character_ids"] = "aria"
        del players[0]["absence_policies"]
        players[0]["preferences"] = "exploration"

        self.assert_invalid_fields(
            configuration,
            idempotency_key="invalid-required-session-zero-v1",
            invalid_fields=[
                "difficulty",
                "players[alice].character_ids",
                "players[alice].display_name",
                "players[alice].preferences",
                "pvp_categories",
                "safety.boundaries",
            ],
        )

    def test_session_zero_rejects_duplicate_player_ids(self) -> None:
        configuration = complete_configuration()
        players = configuration["players"]
        if not isinstance(players, list) or not isinstance(players[1], dict):
            raise AssertionError("测试配置必须包含第二位玩家")
        players[1]["player_id"] = "alice"

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
                "duplicate-player-session-zero-v1",
                "--configuration",
                json.dumps(configuration, ensure_ascii=False),
            )
            error_payload = json.loads(result.stderr) if result.stderr else None
            open_result = run_facade("open", str(workspace))
            opened = json.loads(open_result.stdout) if open_result.stdout else None

            self.assertEqual(
                {
                    "returncode": 2,
                    "error": {
                        "ok": False,
                        "error": {
                            "code": "session_zero_conflict",
                            "message": "Session Zero 配置包含重复的玩家稳定标识。",
                            "details": {"duplicate_player_ids": ["alice"]},
                        },
                    },
                    "open_revision": 1,
                    "open_status": "awaiting_session_zero",
                },
                {
                    "returncode": result.returncode,
                    "error": error_payload,
                    "open_revision": (
                        opened.get("revision") if isinstance(opened, dict) else None
                    ),
                    "open_status": (
                        opened.get("campaign_status")
                        if isinstance(opened, dict)
                        else None
                    ),
                },
                msg=result.stderr or open_result.stderr,
            )

    def test_session_zero_requires_stably_identified_players(self) -> None:
        empty_roster = complete_configuration()
        empty_roster["players"] = []
        safety = empty_roster["safety"]
        if not isinstance(safety, dict):
            raise AssertionError("测试配置必须包含安全边界")
        safety["confirmed_by"] = []
        self.assert_invalid_fields(
            empty_roster,
            idempotency_key="empty-roster-session-zero-v1",
            invalid_fields=["players"],
        )

        blank_id = complete_configuration()
        players = blank_id["players"]
        if not isinstance(players, list) or not isinstance(players[0], dict):
            raise AssertionError("测试配置必须包含第一位玩家")
        players[0]["player_id"] = " "
        if not isinstance(players[1], dict):
            raise AssertionError("测试配置必须包含第二位玩家")
        players[1]["absence_policies"] = {
            "borin": {"mode": "narrative_exit"}
        }
        self.assert_invalid_fields(
            blank_id,
            idempotency_key="blank-player-session-zero-v1",
            invalid_fields=["players[0].player_id"],
        )

    def test_session_zero_rejects_missing_player_and_safety_confirmations(self) -> None:
        configuration = complete_configuration()
        players = configuration["players"]
        if not isinstance(players, list) or not isinstance(players[1], dict):
            raise AssertionError("测试配置必须包含第二位玩家")
        players[1]["confirmed"] = False
        safety = configuration["safety"]
        if not isinstance(safety, dict):
            raise AssertionError("测试配置必须包含安全边界")
        safety["confirmed_by"] = ["alice"]

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
                "incomplete-session-zero-v1",
                "--configuration",
                json.dumps(configuration, ensure_ascii=False),
            )
            error_payload = json.loads(result.stderr) if result.stderr else None
            open_result = run_facade("open", str(workspace))
            opened = json.loads(open_result.stdout) if open_result.stdout else None

            self.assertEqual(
                {
                    "returncode": 2,
                    "error": {
                        "ok": False,
                        "error": {
                            "code": "session_zero_incomplete",
                            "message": "Session Zero 尚未获得全部必要确认，不能开团。",
                            "details": {
                                "missing_player_confirmations": ["bob"],
                                "missing_safety_confirmations": ["bob"],
                            },
                        },
                    },
                    "stdout": "",
                    "open_returncode": 0,
                    "open_revision": 1,
                    "open_status": "awaiting_session_zero",
                },
                {
                    "returncode": result.returncode,
                    "error": error_payload,
                    "stdout": result.stdout,
                    "open_returncode": open_result.returncode,
                    "open_revision": (
                        opened.get("revision") if isinstance(opened, dict) else None
                    ),
                    "open_status": (
                        opened.get("campaign_status")
                        if isinstance(opened, dict)
                        else None
                    ),
                },
                msg=result.stderr,
            )

    def test_session_zero_rejects_conflicting_character_control(self) -> None:
        configuration = complete_configuration()
        players = configuration["players"]
        if not isinstance(players, list) or not isinstance(players[1], dict):
            raise AssertionError("测试配置必须包含第二位玩家")
        players[1]["character_ids"] = ["aria"]
        players[1]["absence_policies"] = {
            "aria": {
                "mode": "delegate",
                "delegate_player_id": "alice",
            }
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
                "conflicting-session-zero-v1",
                "--configuration",
                json.dumps(configuration, ensure_ascii=False),
            )
            error_payload = json.loads(result.stderr) if result.stderr else None
            open_result = run_facade("open", str(workspace))
            opened = json.loads(open_result.stdout) if open_result.stdout else None

            self.assertEqual(
                {
                    "returncode": 2,
                    "error": {
                        "ok": False,
                        "error": {
                            "code": "session_zero_conflict",
                            "message": "Session Zero 配置存在互相冲突的角色控制关系。",
                            "details": {
                                "character_controls": {
                                    "aria": ["alice", "bob"],
                                }
                            },
                        },
                    },
                    "stdout": "",
                    "open_revision": 1,
                    "open_status": "awaiting_session_zero",
                },
                {
                    "returncode": result.returncode,
                    "error": error_payload,
                    "stdout": result.stdout,
                    "open_revision": (
                        opened.get("revision") if isinstance(opened, dict) else None
                    ),
                    "open_status": (
                        opened.get("campaign_status")
                        if isinstance(opened, dict)
                        else None
                    ),
                },
                msg=result.stderr or open_result.stderr,
            )

    def test_session_zero_reports_missing_required_configuration(self) -> None:
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
                "missing-session-zero-v1",
                "--configuration",
                "{}",
            )
            error_payload = json.loads(result.stderr) if result.stderr else None
            open_result = run_facade("open", str(workspace))
            opened = json.loads(open_result.stdout) if open_result.stdout else None

            self.assertEqual(
                {
                    "returncode": 2,
                    "error": {
                        "ok": False,
                        "error": {
                            "code": "invalid_session_zero",
                            "message": "Session Zero 配置缺少开团所需的必填决策。",
                            "details": {
                                "missing_fields": [
                                    "players",
                                    "safety",
                                    "pvp_categories",
                                ]
                            },
                        },
                    },
                    "stdout": "",
                    "open_revision": 1,
                    "open_status": "awaiting_session_zero",
                },
                {
                    "returncode": result.returncode,
                    "error": error_payload,
                    "stdout": result.stdout,
                    "open_revision": (
                        opened.get("revision") if isinstance(opened, dict) else None
                    ),
                    "open_status": (
                        opened.get("campaign_status")
                        if isinstance(opened, dict)
                        else None
                    ),
                },
                msg=result.stderr or open_result.stderr,
            )
