from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from tests.facade_support import run_configure_fault, run_facade


class CampaignConfigRecoveryFacadeTests(unittest.TestCase):
    def test_configure_recovers_after_state_after_a_postcommit_crash(self) -> None:
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
                failure_point="after_commit",
                failure_mode="crash",
                idempotency_key="postcommit-crash-request",
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
                "postcommit-crash-request",
                "--difficulty",
                "challenging",
            )
            retried = json.loads(retry_result.stdout) if retry_result.stdout else None

            self.assertEqual(
                {
                    "crash_returncode": 86,
                    "crash_stdout": "",
                    "crash_stderr": "",
                    "recovered_returncode": 0,
                    "recovered_revision": 2,
                    "recovered_difficulty": "challenging",
                    "retry_returncode": 0,
                    "retry_revision": 2,
                    "retry_replayed": True,
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
                },
                msg=crashed.stderr or recovered_result.stderr or retry_result.stderr,
            )


if __name__ == "__main__":
    unittest.main()
