from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tests.facade_support import REPOSITORY_ROOT, run_facade


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
            crash_script = """
import os
from pathlib import Path
import sys

from dnd_5e.workspace import configure_campaign_difficulty


def interrupt_transaction(point: str) -> None:
    if point == "after_commit":
        os._exit(86)


configure_campaign_difficulty(
    Path(sys.argv[1]),
    expected_revision=1,
    idempotency_key="postcommit-crash-request",
    difficulty="challenging",
    failure_injector=interrupt_transaction,
)
"""
            environment = os.environ.copy()
            source_path = str(REPOSITORY_ROOT / "src")
            existing_python_path = environment.get("PYTHONPATH")
            environment["PYTHONPATH"] = (
                f"{source_path}{os.pathsep}{existing_python_path}"
                if existing_python_path
                else source_path
            )

            crashed = subprocess.run(
                [sys.executable, "-c", crash_script, str(workspace)],
                cwd=REPOSITORY_ROOT,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
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
