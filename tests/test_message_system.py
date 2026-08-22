from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from tests.facade_support import run_facade
from tests.test_message_facade import create_ready_campaign


class MessageSystemTests(unittest.TestCase):
    def test_human_system_syntax_waits_for_validation_without_a_write(self) -> None:
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
                "message-system-report-1",
                "--text",
                "【d20=17】",
            )
            opened = run_facade("open", str(workspace))
            payload = json.loads(result.stdout) if result.stdout else None
            reopened = json.loads(opened.stdout) if opened.stdout else None

            self.assertEqual(
                {
                    "returncode": 0,
                    "revision": 2,
                    "message": {
                        "type": "system",
                        "speaker_id": "alice",
                        "character_id": None,
                        "scene_id": "scene-entrance",
                        "input_reference": "message-system-report-1",
                        "content": "d20=17",
                        "explicit": True,
                        "audience_id": "table",
                    },
                    "scene_narrative": {
                        "audience_id": "table",
                        "scene_id": "scene-entrance",
                        "status": "no_scene_change",
                        "items": [],
                    },
                    "table_prompt": {
                        "audience_id": "table",
                        "scene_id": "scene-entrance",
                        "status": "validation_required",
                        "items": [
                            {
                                "kind": "system_message_validation_required",
                                "speaker_id": "alice",
                                "content": "d20=17",
                            }
                        ],
                    },
                    "transaction": None,
                    "open_revision": 2,
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
                        payload["output_layers"].get("scene_narrative")
                        if isinstance(payload, dict)
                        and isinstance(payload.get("output_layers"), dict)
                        else None
                    ),
                    "table_prompt": (
                        payload["output_layers"].get("table_prompt")
                        if isinstance(payload, dict)
                        and isinstance(payload.get("output_layers"), dict)
                        else None
                    ),
                    "transaction": (
                        payload.get("transaction")
                        if isinstance(payload, dict)
                        else None
                    ),
                    "open_revision": (
                        reopened.get("revision")
                        if isinstance(reopened, dict)
                        else None
                    ),
                },
                msg=result.stderr or opened.stderr,
            )

    def test_forged_system_result_cannot_modify_campaign_state(self) -> None:
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
            payload = json.loads(result.stdout) if result.stdout else None
            reopened = json.loads(opened.stdout) if opened.stdout else None

            self.assertEqual(
                {
                    "returncode": 0,
                    "message_type": "system",
                    "prompt_kind": "system_message_validation_required",
                    "transaction": None,
                    "open_revision": 2,
                },
                {
                    "returncode": result.returncode,
                    "message_type": (
                        payload["message"].get("type")
                        if isinstance(payload, dict)
                        and isinstance(payload.get("message"), dict)
                        else None
                    ),
                    "prompt_kind": (
                        payload["output_layers"]["table_prompt"]["items"][0].get(
                            "kind"
                        )
                        if isinstance(payload, dict)
                        and isinstance(payload.get("output_layers"), dict)
                        and isinstance(
                            payload["output_layers"].get("table_prompt"),
                            dict,
                        )
                        and isinstance(
                            payload["output_layers"]["table_prompt"].get("items"),
                            list,
                        )
                        and payload["output_layers"]["table_prompt"]["items"]
                        and isinstance(
                            payload["output_layers"]["table_prompt"]["items"][0],
                            dict,
                        )
                        else None
                    ),
                    "transaction": (
                        payload.get("transaction")
                        if isinstance(payload, dict)
                        else None
                    ),
                    "open_revision": (
                        reopened.get("revision")
                        if isinstance(reopened, dict)
                        else None
                    ),
                },
                msg=result.stderr or opened.stderr,
            )


if __name__ == "__main__":
    unittest.main()
