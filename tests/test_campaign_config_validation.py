from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from tests.facade_support import run_facade


class CampaignConfigValidationFacadeTests(unittest.TestCase):
    def test_configure_rejects_reusing_an_idempotency_key_for_another_request(
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
            first_result = run_facade(
                "configure",
                str(workspace),
                "--expected-revision",
                "1",
                "--idempotency-key",
                "single-use-request-key",
                "--difficulty",
                "challenging",
            )
            self.assertEqual(0, first_result.returncode, msg=first_result.stderr)

            conflicting_result = run_facade(
                "configure",
                str(workspace),
                "--expected-revision",
                "1",
                "--idempotency-key",
                "single-use-request-key",
                "--difficulty",
                "deadly",
            )
            error_payload = (
                json.loads(conflicting_result.stderr)
                if conflicting_result.stderr
                else None
            )
            open_result = run_facade("open", str(workspace))
            opened = json.loads(open_result.stdout) if open_result.stdout else None

            self.assertEqual(
                {
                    "returncode": 2,
                    "error": {
                        "ok": False,
                        "error": {
                            "code": "idempotency_conflict",
                            "message": "该幂等键已用于不同的状态变更请求。",
                        },
                    },
                    "stdout": "",
                    "open_returncode": 0,
                    "open_revision": 2,
                    "open_difficulty": "challenging",
                },
                {
                    "returncode": conflicting_result.returncode,
                    "error": error_payload,
                    "stdout": conflicting_result.stdout,
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
                msg=conflicting_result.stderr or open_result.stderr,
            )


if __name__ == "__main__":
    unittest.main()
