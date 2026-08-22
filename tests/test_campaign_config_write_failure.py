from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from tests.facade_support import run_configure_fault, run_facade


class CampaignConfigWriteFailureFacadeTests(unittest.TestCase):
    def test_configure_rolls_back_when_event_staging_reports_a_write_failure(
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

            failed = run_configure_fault(
                workspace,
                failure_point="after_event",
                failure_mode="write_error",
                idempotency_key="write-failure-request",
            )
            error_payload = json.loads(failed.stderr) if failed.stderr else None
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
                "write-failure-request",
                "--difficulty",
                "challenging",
            )
            retried = json.loads(retry_result.stdout) if retry_result.stdout else None

            self.assertEqual(
                {
                    "failure_returncode": 2,
                    "failure_error": {
                        "code": "state_commit_failed",
                        "message": "状态事务写入失败，未提交任何部分状态。",
                    },
                    "failure_stdout": "",
                    "recovered_returncode": 0,
                    "recovered_revision": 1,
                    "recovered_difficulty": "standard",
                    "retry_returncode": 0,
                    "retry_revision": 2,
                    "retry_replayed": False,
                },
                {
                    "failure_returncode": failed.returncode,
                    "failure_error": error_payload,
                    "failure_stdout": failed.stdout,
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
                msg=failed.stderr or recovered_result.stderr or retry_result.stderr,
            )


if __name__ == "__main__":
    unittest.main()
