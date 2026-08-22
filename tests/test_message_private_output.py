from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from tests.facade_support import run_facade
from tests.test_message_facade import create_ready_campaign


class MessagePrivateOutputTests(unittest.TestCase):
    def test_character_inner_thought_is_private_to_its_player(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "campaign"
            create_ready_campaign(workspace)

            result = run_facade(
                "message",
                str(workspace),
                "--speaker",
                "alice",
                "--character",
                "aria",
                "--scene",
                "scene-entrance",
                "--input-reference",
                "message-inner-1",
                "--expected-revision",
                "2",
                "--text",
                "（内心：这扇门后可能有埋伏。）",
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
                        "type": "character_inner",
                        "speaker_id": "alice",
                        "character_id": "aria",
                        "scene_id": "scene-entrance",
                        "input_reference": "message-inner-1",
                        "content": "这扇门后可能有埋伏。",
                        "explicit": True,
                    },
                    "scene_narrative": {
                        "audience_id": "player:alice",
                        "items": [
                            {
                                "kind": "character_inner",
                                "character_id": "aria",
                                "content": "这扇门后可能有埋伏。",
                            }
                        ],
                    },
                    "table_prompt_audience": "player:alice",
                    "audit_contains_content": False,
                    "transaction_audience": "player:alice",
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
                    "scene_narrative": (
                        outputs.get("scene_narrative")
                        if isinstance(outputs, dict)
                        else None
                    ),
                    "table_prompt_audience": (
                        outputs["table_prompt"].get("audience_id")
                        if isinstance(outputs, dict)
                        and isinstance(outputs.get("table_prompt"), dict)
                        else None
                    ),
                    "audit_contains_content": (
                        "content" in json.dumps(
                            outputs.get("audit_record"),
                            ensure_ascii=False,
                        )
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


if __name__ == "__main__":
    unittest.main()
