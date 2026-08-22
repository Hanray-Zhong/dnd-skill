from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from tests.facade_support import run_facade
from tests.test_message_facade import create_ready_campaign


class MessageValidationTests(unittest.TestCase):
    def test_ambiguous_action_syntax_requires_clarification_without_a_write(
        self,
    ) -> None:
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
                "table",
                "--input-reference",
                "message-ambiguous-action-1",
                "--expected-revision",
                "2",
                "--text",
                "*我尝试撬开北门",
            )
            opened = run_facade("open", str(workspace))
            payload = json.loads(result.stderr) if result.stderr else None
            reopened = json.loads(opened.stdout) if opened.stdout else None

            self.assertEqual(
                {
                    "returncode": 2,
                    "error": {
                        "code": "ambiguous_action",
                        "message": "角色行动标记不完整，必须先澄清而不能修改战役状态。",
                        "details": {
                            "input_reference": "message-ambiguous-action-1",
                            "scene_id": "table",
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

    def test_player_cannot_speak_for_an_uncontrolled_character(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "campaign"
            create_ready_campaign(workspace)

            result = run_facade(
                "message",
                str(workspace),
                "--speaker",
                "bob",
                "--character",
                "aria",
                "--scene",
                "table",
                "--input-reference",
                "message-unauthorized-character-1",
                "--expected-revision",
                "2",
                "--text",
                "“我替艾莉丝回答。”",
            )
            opened = run_facade("open", str(workspace))
            payload = json.loads(result.stderr) if result.stderr else None
            reopened = json.loads(opened.stdout) if opened.stdout else None

            self.assertEqual(
                {
                    "code": "character_control_forbidden",
                    "details": {
                        "character_id": "aria",
                        "input_reference": "message-unauthorized-character-1",
                        "message_type": "character_dialogue",
                        "scene_id": "table",
                        "speaker_id": "bob",
                    },
                    "returncode": 2,
                    "open_revision": 2,
                },
                {
                    "code": (
                        payload["error"].get("code")
                        if isinstance(payload, dict)
                        and isinstance(payload.get("error"), dict)
                        else None
                    ),
                    "details": (
                        payload["error"].get("details")
                        if isinstance(payload, dict)
                        and isinstance(payload.get("error"), dict)
                        else None
                    ),
                    "returncode": result.returncode,
                    "open_revision": (
                        reopened.get("revision")
                        if isinstance(reopened, dict)
                        else None
                    ),
                },
                msg=result.stdout or opened.stderr,
            )

    def test_unknown_speaker_is_rejected_before_any_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "campaign"
            create_ready_campaign(workspace)

            result = run_facade(
                "message",
                str(workspace),
                "--speaker",
                "mallory",
                "--scene",
                "table",
                "--input-reference",
                "message-unknown-speaker-1",
                "--text",
                "//我是新玩家",
            )
            opened = run_facade("open", str(workspace))
            payload = json.loads(result.stderr) if result.stderr else None
            reopened = json.loads(opened.stdout) if opened.stdout else None

            self.assertEqual(
                {
                    "returncode": 2,
                    "code": "unknown_speaker",
                    "speaker_id": "mallory",
                    "open_revision": 2,
                },
                {
                    "returncode": result.returncode,
                    "code": (
                        payload["error"].get("code")
                        if isinstance(payload, dict)
                        and isinstance(payload.get("error"), dict)
                        else None
                    ),
                    "speaker_id": (
                        payload["error"]["details"].get("speaker_id")
                        if isinstance(payload, dict)
                        and isinstance(payload.get("error"), dict)
                        and isinstance(payload["error"].get("details"), dict)
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

    def test_unknown_scene_is_rejected_before_any_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "campaign"
            create_ready_campaign(workspace)

            result = run_facade(
                "message",
                str(workspace),
                "--speaker",
                "alice",
                "--scene",
                "missing-scene",
                "--input-reference",
                "message-unknown-scene-1",
                "--text",
                "//我在这里吗？",
            )
            opened = run_facade("open", str(workspace))
            payload = json.loads(result.stderr) if result.stderr else None
            reopened = json.loads(opened.stdout) if opened.stdout else None

            self.assertEqual(
                {
                    "returncode": 2,
                    "error": {
                        "code": "invalid_message_context",
                        "message": "目标场景不存在或消息交互上下文无效。",
                        "details": {"scene_id": "missing-scene"},
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
