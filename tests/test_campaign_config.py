from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
import uuid

from tests.facade_support import run_configure_fault, run_facade


class CampaignConfigFacadeTests(unittest.TestCase):
    def test_configure_updates_difficulty_and_open_restores_the_result(self) -> None:
        initial_config = {
            "advancement": "xp",
            "difficulty": "standard",
            "roll_policy": "players",
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "campaign"
            create_result = run_facade(
                "create",
                str(workspace),
                "--initial-config",
                json.dumps(initial_config),
            )
            created = json.loads(create_result.stdout)

            configure_result = run_facade(
                "configure",
                str(workspace),
                "--expected-revision",
                "1",
                "--idempotency-key",
                "difficulty-session-zero-v1",
                "--difficulty",
                "challenging",
            )
            configured = (
                json.loads(configure_result.stdout)
                if configure_result.stdout
                else None
            )
            open_result = run_facade("open", str(workspace))
            opened = json.loads(open_result.stdout) if open_result.stdout else None
            event_id_is_uuid = False
            if isinstance(configured, dict):
                transaction = configured.get("transaction")
                if isinstance(transaction, dict) and isinstance(
                    transaction.get("event_id"), str
                ):
                    event_id = transaction["event_id"]
                    event_id_is_uuid = str(uuid.UUID(event_id)) == event_id

            expected_config = {**initial_config, "difficulty": "challenging"}
            self.assertEqual(
                {
                    "create_returncode": 0,
                    "configure_returncode": 0,
                    "configure_ok": True,
                    "configure_operation": "configure",
                    "configure_campaign_id": created["campaign_id"],
                    "configure_revision": 2,
                    "configure_config": expected_config,
                    "transaction": {
                        "audience_id": "dm",
                        "expected_changes": {"difficulty": "challenging"},
                        "idempotency_key": "difficulty-session-zero-v1",
                        "replayed": False,
                        "source": "dnd-5e-campaign-start",
                    },
                    "event_id_is_uuid": True,
                    "open_returncode": 0,
                    "open_campaign_id": created["campaign_id"],
                    "open_revision": 2,
                    "open_config": expected_config,
                },
                {
                    "create_returncode": create_result.returncode,
                    "configure_returncode": configure_result.returncode,
                    "configure_ok": (
                        configured.get("ok") if isinstance(configured, dict) else None
                    ),
                    "configure_operation": (
                        configured.get("operation")
                        if isinstance(configured, dict)
                        else None
                    ),
                    "configure_campaign_id": (
                        configured.get("campaign_id")
                        if isinstance(configured, dict)
                        else None
                    ),
                    "configure_revision": (
                        configured.get("revision")
                        if isinstance(configured, dict)
                        else None
                    ),
                    "configure_config": (
                        configured.get("initial_config")
                        if isinstance(configured, dict)
                        else None
                    ),
                    "transaction": (
                        {
                            "audience_id": configured["transaction"].get(
                                "audience_id"
                            ),
                            "expected_changes": configured["transaction"].get(
                                "expected_changes"
                            ),
                            "idempotency_key": configured["transaction"].get(
                                "idempotency_key"
                            ),
                            "replayed": configured["transaction"].get("replayed"),
                            "source": configured["transaction"].get("source"),
                        }
                        if isinstance(configured, dict)
                        and isinstance(configured.get("transaction"), dict)
                        else None
                    ),
                    "event_id_is_uuid": event_id_is_uuid,
                    "open_returncode": open_result.returncode,
                    "open_campaign_id": (
                        opened.get("campaign_id")
                        if isinstance(opened, dict)
                        else None
                    ),
                    "open_revision": (
                        opened.get("revision") if isinstance(opened, dict) else None
                    ),
                    "open_config": (
                        opened.get("initial_config")
                        if isinstance(opened, dict)
                        else None
                    ),
                },
                msg=configure_result.stderr or open_result.stderr,
            )

    def test_configure_retries_the_same_idempotency_key_without_new_commit(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "campaign"
            create_result = run_facade(
                "create",
                str(workspace),
                "--initial-config",
                json.dumps({"difficulty": "standard"}),
            )
            self.assertEqual(0, create_result.returncode, msg=create_result.stderr)
            request = (
                "configure",
                str(workspace),
                "--expected-revision",
                "1",
                "--idempotency-key",
                "retryable-difficulty-request",
                "--difficulty",
                "challenging",
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
                    "same_config": True,
                    "open_returncode": 0,
                    "open_revision": 2,
                    "open_difficulty": "challenging",
                },
                {
                    "first_returncode": first_result.returncode,
                    "first_revision": (
                        first.get("revision") if isinstance(first, dict) else None
                    ),
                    "first_replayed": (
                        first.get("transaction", {}).get("replayed")
                        if isinstance(first, dict)
                        and isinstance(first.get("transaction"), dict)
                        else None
                    ),
                    "retry_returncode": retry_result.returncode,
                    "retry_revision": (
                        retry.get("revision") if isinstance(retry, dict) else None
                    ),
                    "retry_replayed": (
                        retry.get("transaction", {}).get("replayed")
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
                    "same_config": (
                        isinstance(first, dict)
                        and isinstance(retry, dict)
                        and first.get("initial_config") == retry.get("initial_config")
                    ),
                    "open_returncode": open_result.returncode,
                    "open_revision": (
                        opened.get("revision") if isinstance(opened, dict) else None
                    ),
                    "open_difficulty": (
                        opened.get("initial_config", {}).get("difficulty")
                        if isinstance(opened, dict)
                        and isinstance(opened.get("initial_config"), dict)
                        else None
                    ),
                },
                msg=retry_result.stderr or open_result.stderr,
            )

    def test_configure_rejects_a_stale_revision_with_reconciliation_details(
        self,
    ) -> None:
        initial_config = {
            "advancement": "xp",
            "difficulty": "standard",
            "roll_policy": "players",
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "campaign"
            create_result = run_facade(
                "create",
                str(workspace),
                "--initial-config",
                json.dumps(initial_config),
            )
            self.assertEqual(0, create_result.returncode, msg=create_result.stderr)
            first_result = run_facade(
                "configure",
                str(workspace),
                "--expected-revision",
                "1",
                "--idempotency-key",
                "accepted-difficulty-request",
                "--difficulty",
                "challenging",
            )
            self.assertEqual(0, first_result.returncode, msg=first_result.stderr)

            stale_result = run_facade(
                "configure",
                str(workspace),
                "--expected-revision",
                "1",
                "--idempotency-key",
                "stale-difficulty-request",
                "--difficulty",
                "deadly",
            )
            error_payload = json.loads(stale_result.stderr) if stale_result.stderr else None
            open_result = run_facade("open", str(workspace))
            opened = json.loads(open_result.stdout) if open_result.stdout else None
            current_config = {**initial_config, "difficulty": "challenging"}

            self.assertEqual(
                {
                    "stale_returncode": 2,
                    "stale_error": {
                        "ok": False,
                        "error": {
                            "code": "revision_conflict",
                            "message": (
                                "状态变更请求基于过期修订，必须先重新打开战役并重新对账。"
                            ),
                            "details": {
                                "expected_revision": 1,
                                "current_revision": 2,
                                "current_config": current_config,
                            },
                        },
                    },
                    "stale_stdout": "",
                    "open_returncode": 0,
                    "open_revision": 2,
                    "open_config": current_config,
                },
                {
                    "stale_returncode": stale_result.returncode,
                    "stale_error": error_payload,
                    "stale_stdout": stale_result.stdout,
                    "open_returncode": open_result.returncode,
                    "open_revision": (
                        opened.get("revision") if isinstance(opened, dict) else None
                    ),
                    "open_config": (
                        opened.get("initial_config")
                        if isinstance(opened, dict)
                        else None
                    ),
                },
                msg=stale_result.stderr or open_result.stderr,
            )

    def test_configure_recovers_before_state_after_a_precommit_crash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "campaign"
            create_result = run_facade(
                "create",
                str(workspace),
                "--initial-config",
                json.dumps({"difficulty": "standard"}),
            )
            self.assertEqual(0, create_result.returncode, msg=create_result.stderr)
            crashed = run_configure_fault(
                workspace,
                failure_point="before_commit",
                failure_mode="crash",
                idempotency_key="crash-recovery-request",
            )
            recovered_result = run_facade("open", str(workspace))
            recovered = (
                json.loads(recovered_result.stdout)
                if recovered_result.stdout
                else None
            )
            retry_result = run_facade(
                "configure",
                str(workspace),
                "--expected-revision",
                "1",
                "--idempotency-key",
                "crash-recovery-request",
                "--difficulty",
                "challenging",
            )
            retried = json.loads(retry_result.stdout) if retry_result.stdout else None
            final_open_result = run_facade("open", str(workspace))
            final_opened = (
                json.loads(final_open_result.stdout)
                if final_open_result.stdout
                else None
            )

            self.assertEqual(
                {
                    "crash_returncode": 86,
                    "crash_stdout": "",
                    "crash_stderr": "",
                    "recovered_returncode": 0,
                    "recovered_revision": 1,
                    "recovered_difficulty": "standard",
                    "retry_returncode": 0,
                    "retry_revision": 2,
                    "retry_replayed": False,
                    "final_open_returncode": 0,
                    "final_revision": 2,
                    "final_difficulty": "challenging",
                },
                {
                    "crash_returncode": crashed.returncode,
                    "crash_stdout": crashed.stdout,
                    "crash_stderr": crashed.stderr,
                    "recovered_returncode": recovered_result.returncode,
                    "recovered_revision": (
                        recovered.get("revision")
                        if isinstance(recovered, dict)
                        else None
                    ),
                    "recovered_difficulty": (
                        recovered.get("initial_config", {}).get("difficulty")
                        if isinstance(recovered, dict)
                        and isinstance(recovered.get("initial_config"), dict)
                        else None
                    ),
                    "retry_returncode": retry_result.returncode,
                    "retry_revision": (
                        retried.get("revision")
                        if isinstance(retried, dict)
                        else None
                    ),
                    "retry_replayed": (
                        retried.get("transaction", {}).get("replayed")
                        if isinstance(retried, dict)
                        and isinstance(retried.get("transaction"), dict)
                        else None
                    ),
                    "final_open_returncode": final_open_result.returncode,
                    "final_revision": (
                        final_opened.get("revision")
                        if isinstance(final_opened, dict)
                        else None
                    ),
                    "final_difficulty": (
                        final_opened.get("initial_config", {}).get("difficulty")
                        if isinstance(final_opened, dict)
                        and isinstance(final_opened.get("initial_config"), dict)
                        else None
                    ),
                },
                msg=(
                    crashed.stderr
                    or recovered_result.stderr
                    or retry_result.stderr
                    or final_open_result.stderr
                ),
            )


if __name__ == "__main__":
    unittest.main()
