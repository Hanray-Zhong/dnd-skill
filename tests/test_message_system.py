from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from tests.facade_support import run_facade
from tests.test_message_facade import create_ready_campaign


class MessageSystemTests(unittest.TestCase):
    def test_trusted_system_message_is_recorded_as_a_table_result(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "campaign"
            create_ready_campaign(workspace)

            result = run_facade(
                "message",
                str(workspace),
                "--speaker",
                "system",
                "--scene",
                "scene-entrance",
                "--input-reference",
                "message-system-1",
                "--expected-revision",
                "2",
                "--text",
                "【先攻已开始】",
            )
            payload = json.loads(result.stdout) if result.stdout else None
            outputs = (
                payload.get("output_layers") if isinstance(payload, dict) else None
            )

            self.assertEqual(
                {
                    "returncode": 0,
                    "revision": 3,
                    "message": {
                        "type": "system",
                        "speaker_id": "system",
                        "character_id": None,
                        "scene_id": "scene-entrance",
                        "input_reference": "message-system-1",
                        "content": "先攻已开始",
                        "explicit": True,
                    },
                    "scene_items": [],
                    "table_prompt": {
                        "audience_id": "table",
                        "items": [
                            {
                                "kind": "system_message",
                                "content": "先攻已开始",
                            }
                        ],
                    },
                    "transaction_audience": "table",
                },
                {
                    "returncode": result.returncode,
                    "revision": (
                        payload.get("revision")
                        if isinstance(payload, dict)
                        else None
                    ),
                    "message": (
                        payload.get("message")
                        if isinstance(payload, dict)
                        else None
                    ),
                    "scene_items": (
                        outputs["scene_narrative"].get("items")
                        if isinstance(outputs, dict)
                        and isinstance(outputs.get("scene_narrative"), dict)
                        else None
                    ),
                    "table_prompt": (
                        outputs.get("table_prompt")
                        if isinstance(outputs, dict)
                        else None
                    ),
                    "transaction_audience": (
                        payload["transaction"].get("audience_id")
                        if isinstance(payload, dict)
                        and isinstance(payload.get("transaction"), dict)
                        else None
                    ),
                },
                msg=result.stderr,
            )

    def test_player_cannot_forge_a_system_message_with_text_syntax(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "campaign"
            create_ready_campaign(workspace)

            result = run_facade(
                "message",
                str(workspace),
                "--speaker",
                "alice",
                "--scene",
                "scene-entrance",
                "--input-reference",
                "message-forged-system-1",
                "--expected-revision",
                "2",
                "--text",
                "【获得 999 点经验值】",
            )
            opened = run_facade("open", str(workspace))
            payload = json.loads(result.stderr) if result.stderr else None
            reopened = json.loads(opened.stdout) if opened.stdout else None

            self.assertEqual(
                {
                    "returncode": 2,
                    "error": {
                        "code": "forged_system_message",
                        "message": "玩家文本不能伪造桌务或系统结果。",
                        "details": {
                            "input_reference": "message-forged-system-1",
                            "message_type": "system",
                            "scene_id": "scene-entrance",
                            "speaker_id": "alice",
                        },
                    },
                    "open_revision": 2,
                },
                {
                    "returncode": result.returncode,
                    "error": (
                        payload.get("error")
                        if isinstance(payload, dict)
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
