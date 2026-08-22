from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from tests.facade_support import run_facade
from tests.test_session_zero import complete_configuration


class SessionZeroTransactionFacadeTests(unittest.TestCase):
    def test_session_zero_retries_without_a_second_commit(self) -> None:
        configuration = complete_configuration()
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "campaign"
            create_result = run_facade("create", str(workspace))
            self.assertEqual(0, create_result.returncode, msg=create_result.stderr)
            request = (
                "session-zero",
                str(workspace),
                "--expected-revision",
                "1",
                "--idempotency-key",
                "retry-session-zero-v1",
                "--configuration",
                json.dumps(configuration, ensure_ascii=False),
            )

            first_result = run_facade(*request)
            first = json.loads(first_result.stdout) if first_result.stdout else None
            retry_result = run_facade(*request)
            retry = json.loads(retry_result.stdout) if retry_result.stdout else None
            open_result = run_facade("open", str(workspace))
            opened = json.loads(open_result.stdout) if open_result.stdout else None

            self.assertEqual(
                {
                    "first_returncode": 0,
                    "first_revision": 2,
                    "first_replayed": False,
                    "retry_returncode": 0,
                    "retry_revision": 2,
                    "retry_replayed": True,
                    "same_event_id": True,
                    "same_configuration": True,
                    "open_revision": 2,
                    "open_status": "ready_to_play",
                },
                {
                    "first_returncode": first_result.returncode,
                    "first_revision": (
                        first.get("revision") if isinstance(first, dict) else None
                    ),
                    "first_replayed": (
                        first["transaction"].get("replayed")
                        if isinstance(first, dict)
                        and isinstance(first.get("transaction"), dict)
                        else None
                    ),
                    "retry_returncode": retry_result.returncode,
                    "retry_revision": (
                        retry.get("revision") if isinstance(retry, dict) else None
                    ),
                    "retry_replayed": (
                        retry["transaction"].get("replayed")
                        if isinstance(retry, dict)
                        and isinstance(retry.get("transaction"), dict)
                        else None
                    ),
                    "same_event_id": (
                        isinstance(first, dict)
                        and isinstance(retry, dict)
                        and isinstance(first.get("transaction"), dict)
                        and isinstance(retry.get("transaction"), dict)
                        and first["transaction"].get("event_id")
                        == retry["transaction"].get("event_id")
                    ),
                    "same_configuration": (
                        isinstance(first, dict)
                        and isinstance(retry, dict)
                        and first.get("initial_config")
                        == retry.get("initial_config")
                    ),
                    "open_revision": (
                        opened.get("revision") if isinstance(opened, dict) else None
                    ),
                    "open_status": (
                        opened.get("campaign_status")
                        if isinstance(opened, dict)
                        else None
                    ),
                },
                msg=first_result.stderr or retry_result.stderr or open_result.stderr,
            )

    def test_session_zero_rejects_a_stale_revision_with_current_configuration(
        self,
    ) -> None:
        initial_config = {"difficulty": "standard"}
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "campaign"
            create_result = run_facade(
                "create",
                str(workspace),
                "--initial-config",
                json.dumps(initial_config),
            )
            self.assertEqual(0, create_result.returncode, msg=create_result.stderr)
            configure_result = run_facade(
                "configure",
                str(workspace),
                "--expected-revision",
                "1",
                "--idempotency-key",
                "difficulty-before-session-zero",
                "--difficulty",
                "challenging",
            )
            self.assertEqual(0, configure_result.returncode, msg=configure_result.stderr)

            result = run_facade(
                "session-zero",
                str(workspace),
                "--expected-revision",
                "1",
                "--idempotency-key",
                "stale-session-zero-v1",
                "--configuration",
                json.dumps(complete_configuration(), ensure_ascii=False),
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
                            "code": "revision_conflict",
                            "message": (
                                "状态变更请求基于过期修订，必须先重新打开战役并重新对账。"
                            ),
                            "details": {
                                "expected_revision": 1,
                                "current_revision": 2,
                                "current_config": {"difficulty": "challenging"},
                            },
                        },
                    },
                    "open_revision": 2,
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

    def test_session_zero_preserves_existing_config_without_a_global_roll_policy(
        self,
    ) -> None:
        configuration = complete_configuration()
        configuration["difficulty"] = "challenging"
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "campaign"
            create_result = run_facade(
                "create",
                str(workspace),
                "--initial-config",
                json.dumps({"roll_policy": "players", "tone": "heroic"}),
            )
            self.assertEqual(0, create_result.returncode, msg=create_result.stderr)
            configure_result = run_facade(
                "configure",
                str(workspace),
                "--expected-revision",
                "1",
                "--idempotency-key",
                "preserved-difficulty",
                "--difficulty",
                "challenging",
            )
            self.assertEqual(0, configure_result.returncode, msg=configure_result.stderr)

            result = run_facade(
                "session-zero",
                str(workspace),
                "--expected-revision",
                "2",
                "--idempotency-key",
                "complete-after-configure-v1",
                "--configuration",
                json.dumps(configuration, ensure_ascii=False),
            )
            payload = json.loads(result.stdout) if result.stdout else None

            self.assertEqual(
                {
                    "returncode": 0,
                    "revision": 3,
                    "difficulty": "challenging",
                    "tone": "heroic",
                    "has_global_roll_policy": False,
                    "status": "ready_to_play",
                },
                {
                    "returncode": result.returncode,
                    "revision": (
                        payload.get("revision") if isinstance(payload, dict) else None
                    ),
                    "difficulty": (
                        payload["initial_config"].get("difficulty")
                        if isinstance(payload, dict)
                        and isinstance(payload.get("initial_config"), dict)
                        else None
                    ),
                    "tone": (
                        payload["initial_config"].get("tone")
                        if isinstance(payload, dict)
                        and isinstance(payload.get("initial_config"), dict)
                        else None
                    ),
                    "has_global_roll_policy": (
                        "roll_policy" in payload["initial_config"]
                        if isinstance(payload, dict)
                        and isinstance(payload.get("initial_config"), dict)
                        else None
                    ),
                    "status": (
                        payload.get("campaign_status")
                        if isinstance(payload, dict)
                        else None
                    ),
                },
                msg=result.stderr,
            )


if __name__ == "__main__":
    unittest.main()
