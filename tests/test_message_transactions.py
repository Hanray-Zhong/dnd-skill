from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from tests.facade_support import run_facade
from tests.test_message_facade import create_ready_campaign


def record_dialogue(
    workspace: Path,
    *,
    input_reference: str,
    text: str = "“我们往北门走。”",
    expected_revision: str = "2",
) -> subprocess.CompletedProcess[str]:
    return run_facade(
        "message",
        str(workspace),
        "--speaker",
        "alice",
        "--character",
        "aria",
        "--scene",
        "table",
        "--input-reference",
        input_reference,
        "--expected-revision",
        expected_revision,
        "--text",
        text,
    )


class MessageTransactionTests(unittest.TestCase):
    def test_retry_returns_the_original_event_without_a_second_revision(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "campaign"
            create_ready_campaign(workspace)

            first = record_dialogue(workspace, input_reference="message-retry-1")
            retry = record_dialogue(workspace, input_reference="message-retry-1")
            opened = run_facade("open", str(workspace))
            first_payload = json.loads(first.stdout) if first.stdout else None
            retry_payload = json.loads(retry.stdout) if retry.stdout else None
            reopened = json.loads(opened.stdout) if opened.stdout else None

            self.assertEqual(
                {
                    "returncodes": [0, 0],
                    "revisions": [3, 3, 3],
                    "same_event": True,
                    "replayed": [False, True],
                },
                {
                    "returncodes": [first.returncode, retry.returncode],
                    "revisions": [
                        first_payload.get("revision")
                        if isinstance(first_payload, dict)
                        else None,
                        retry_payload.get("revision")
                        if isinstance(retry_payload, dict)
                        else None,
                        reopened.get("revision")
                        if isinstance(reopened, dict)
                        else None,
                    ],
                    "same_event": (
                        first_payload["transaction"].get("event_id")
                        == retry_payload["transaction"].get("event_id")
                        if isinstance(first_payload, dict)
                        and isinstance(first_payload.get("transaction"), dict)
                        and isinstance(retry_payload, dict)
                        and isinstance(retry_payload.get("transaction"), dict)
                        else None
                    ),
                    "replayed": [
                        first_payload["transaction"].get("replayed")
                        if isinstance(first_payload, dict)
                        and isinstance(first_payload.get("transaction"), dict)
                        else None,
                        retry_payload["transaction"].get("replayed")
                        if isinstance(retry_payload, dict)
                        and isinstance(retry_payload.get("transaction"), dict)
                        else None,
                    ],
                },
                msg=first.stderr or retry.stderr or opened.stderr,
            )

    def test_input_reference_cannot_be_reused_for_different_content(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "campaign"
            create_ready_campaign(workspace)

            first = record_dialogue(workspace, input_reference="message-conflict-1")
            conflict = record_dialogue(
                workspace,
                input_reference="message-conflict-1",
                text="“我们改走南门。”",
            )
            opened = run_facade("open", str(workspace))
            error = json.loads(conflict.stderr) if conflict.stderr else None
            reopened = json.loads(opened.stdout) if opened.stdout else None

            self.assertEqual(
                {
                    "first_returncode": 0,
                    "conflict_returncode": 2,
                    "code": "idempotency_conflict",
                    "open_revision": 3,
                },
                {
                    "first_returncode": first.returncode,
                    "conflict_returncode": conflict.returncode,
                    "code": (
                        error["error"].get("code")
                        if isinstance(error, dict)
                        and isinstance(error.get("error"), dict)
                        else None
                    ),
                    "open_revision": (
                        reopened.get("revision")
                        if isinstance(reopened, dict)
                        else None
                    ),
                },
                msg=first.stderr or conflict.stdout or opened.stderr,
            )

    def test_stale_revision_is_rejected_without_recording_the_message(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "campaign"
            create_ready_campaign(workspace)

            result = record_dialogue(
                workspace,
                input_reference="message-stale-1",
                expected_revision="1",
            )
            opened = run_facade("open", str(workspace))
            error = json.loads(result.stderr) if result.stderr else None
            reopened = json.loads(opened.stdout) if opened.stdout else None

            self.assertEqual(
                {
                    "returncode": 2,
                    "code": "revision_conflict",
                    "details": {
                        "current_revision": 2,
                        "expected_revision": 1,
                    },
                    "open_revision": 2,
                },
                {
                    "returncode": result.returncode,
                    "code": (
                        error["error"].get("code")
                        if isinstance(error, dict)
                        and isinstance(error.get("error"), dict)
                        else None
                    ),
                    "details": (
                        error["error"].get("details")
                        if isinstance(error, dict)
                        and isinstance(error.get("error"), dict)
                        else None
                    ),
                    "open_revision": (
                        reopened.get("revision")
                        if isinstance(reopened, dict)
                        else None
                    ),
                },
                msg=result.stdout or opened.stderr,
            )


if __name__ == "__main__":
    unittest.main()
