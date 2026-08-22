from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest

from tests.facade_support import run_facade


class CampaignConfigConcurrencyFacadeTests(unittest.TestCase):
    def test_configure_serializes_two_writers_from_the_same_revision(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "campaign"
            create_result = run_facade(
                "create",
                str(workspace),
                "--initial-config",
                json.dumps({"difficulty": "standard"}),
            )
            self.assertEqual(0, create_result.returncode, msg=create_result.stderr)
            start_barrier = threading.Barrier(2)

            def configure(
                idempotency_key: str,
                difficulty: str,
            ) -> subprocess.CompletedProcess[str]:
                start_barrier.wait()
                return run_facade(
                    "configure",
                    str(workspace),
                    "--expected-revision",
                    "1",
                    "--idempotency-key",
                    idempotency_key,
                    "--difficulty",
                    difficulty,
                )

            with ThreadPoolExecutor(max_workers=2) as executor:
                results = [
                    executor.submit(configure, "concurrent-standard", "challenging"),
                    executor.submit(configure, "concurrent-deadly", "deadly"),
                ]
                completed = [future.result() for future in results]

            successes = [result for result in completed if result.returncode == 0]
            conflicts = [result for result in completed if result.returncode == 2]
            success = json.loads(successes[0].stdout) if len(successes) == 1 else None
            conflict = json.loads(conflicts[0].stderr) if len(conflicts) == 1 else None
            open_result = run_facade("open", str(workspace))
            opened = json.loads(open_result.stdout) if open_result.stdout else None
            winning_config = (
                success.get("initial_config") if isinstance(success, dict) else None
            )

            self.assertEqual(
                {
                    "success_count": 1,
                    "conflict_count": 1,
                    "success_revision": 2,
                    "conflict_code": "revision_conflict",
                    "conflict_current_revision": 2,
                    "conflict_current_config": winning_config,
                    "open_returncode": 0,
                    "open_revision": 2,
                    "open_config": winning_config,
                },
                {
                    "success_count": len(successes),
                    "conflict_count": len(conflicts),
                    "success_revision": (
                        success.get("revision")
                        if isinstance(success, dict)
                        else None
                    ),
                    "conflict_code": (
                        conflict.get("error", {}).get("code")
                        if isinstance(conflict, dict)
                        and isinstance(conflict.get("error"), dict)
                        else None
                    ),
                    "conflict_current_revision": (
                        conflict.get("error", {}).get("details", {}).get(
                            "current_revision"
                        )
                        if isinstance(conflict, dict)
                        and isinstance(conflict.get("error"), dict)
                        and isinstance(conflict["error"].get("details"), dict)
                        else None
                    ),
                    "conflict_current_config": (
                        conflict.get("error", {}).get("details", {}).get(
                            "current_config"
                        )
                        if isinstance(conflict, dict)
                        and isinstance(conflict.get("error"), dict)
                        and isinstance(conflict["error"].get("details"), dict)
                        else None
                    ),
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
                msg="\n".join(result.stderr for result in completed if result.stderr),
            )


if __name__ == "__main__":
    unittest.main()
