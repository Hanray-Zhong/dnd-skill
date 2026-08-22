from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
import uuid

from tests.facade_support import run_facade
from tests.test_session_zero import complete_configuration


def create_ready_campaign(workspace: Path) -> None:
    created = run_facade("create", str(workspace))
    if created.returncode != 0:
        raise AssertionError(created.stderr)
    completed = run_facade(
        "session-zero",
        str(workspace),
        "--expected-revision",
        "1",
        "--idempotency-key",
        "message-tests-session-zero-v1",
        "--configuration",
        json.dumps(complete_configuration(), ensure_ascii=False),
    )
    if completed.returncode != 0:
        raise AssertionError(completed.stderr)


class MessageFacadeTests(unittest.TestCase):
    def test_unmarked_player_text_is_non_persistent_ooc(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "campaign"
            create_ready_campaign(workspace)

            result = run_facade(
                "message",
                str(workspace),
                "--speaker",
                "alice",
                "--scene",
                "table",
                "--input-reference",
                "message-ooc-1",
                "--text",
                "先暂停一下",
            )
            opened = run_facade("open", str(workspace))
            payload = json.loads(result.stdout) if result.stdout else None
            reopened = json.loads(opened.stdout) if opened.stdout else None

            self.assertEqual(
                {
                    "returncode": 0,
                    "operation": "message",
                    "revision": 2,
                    "message": {
                        "type": "ooc",
                        "speaker_id": "alice",
                        "character_id": None,
                        "scene_id": "table",
                        "input_reference": "message-ooc-1",
                        "content": "先暂停一下",
                        "explicit": False,
                        "audience_id": "table",
                    },
                    "output_layers": {
                        "scene_narrative": {
                            "audience_id": "table",
                            "scene_id": "table",
                            "status": "no_scene_change",
                            "items": [],
                        },
                        "table_prompt": {
                            "audience_id": "table",
                            "scene_id": "table",
                            "status": "none",
                            "items": [],
                        },
                        "audit_record": {
                            "audience_id": "dm",
                            "scene_id": "table",
                            "items": [
                                {
                                    "character_id": None,
                                    "event_id": None,
                                    "kind": "message_classified",
                                    "input_reference": "message-ooc-1",
                                    "message_type": "ooc",
                                    "persisted": False,
                                    "revision": 2,
                                    "scene_id": "table",
                                    "source": "dnd-5e",
                                    "speaker_id": "alice",
                                    "state_changes": {},
                                }
                            ],
                        },
                    },
                    "transaction": None,
                    "open_revision": 2,
                },
                {
                    "returncode": result.returncode,
                    "operation": (
                        payload.get("operation")
                        if isinstance(payload, dict)
                        else None
                    ),
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
                    "output_layers": (
                        payload.get("output_layers")
                        if isinstance(payload, dict)
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

    def test_authorized_character_dialogue_is_recorded_for_the_table(self) -> None:
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
                "message-dialogue-1",
                "--expected-revision",
                "2",
                "--text",
                "“我们往北门走。”",
            )
            opened = run_facade("open", str(workspace))
            payload = json.loads(result.stdout) if result.stdout else None
            reopened = json.loads(opened.stdout) if opened.stdout else None
            transaction = (
                payload.get("transaction") if isinstance(payload, dict) else None
            )
            event_id = (
                transaction.get("event_id")
                if isinstance(transaction, dict)
                else None
            )
            event_id_is_uuid = (
                isinstance(event_id, str)
                and str(uuid.UUID(event_id)) == event_id
            )

            self.assertEqual(
                {
                    "returncode": 0,
                    "revision": 3,
                    "message": {
                        "type": "character_dialogue",
                        "speaker_id": "alice",
                        "character_id": "aria",
                        "scene_id": "table",
                        "input_reference": "message-dialogue-1",
                        "content": "我们往北门走。",
                        "explicit": True,
                        "audience_id": "table",
                    },
                    "output_layers": {
                        "scene_narrative": {
                            "audience_id": "table",
                            "scene_id": "table",
                            "status": "no_scene_change",
                            "items": [],
                        },
                        "table_prompt": {
                            "audience_id": "table",
                            "scene_id": "table",
                            "status": "none",
                            "items": [],
                        },
                        "audit_record": {
                            "audience_id": "dm",
                            "scene_id": "table",
                            "items": [
                                {
                                    "character_id": "aria",
                                    "event_id": event_id,
                                    "kind": "message_classified",
                                    "input_reference": "message-dialogue-1",
                                    "message_type": "character_dialogue",
                                    "persisted": True,
                                    "revision": 3,
                                    "scene_id": "table",
                                    "source": "dnd-5e",
                                    "speaker_id": "alice",
                                    "state_changes": {
                                        "revision": {
                                            "after": 3,
                                            "before": 2,
                                        }
                                    },
                                }
                            ],
                        },
                    },
                    "transaction": {
                        "audience_id": "table",
                        "event_type": "message_recorded",
                        "expected_revision": 2,
                        "input_reference": "message-dialogue-1",
                        "replayed": False,
                        "source": "dnd-5e",
                    },
                    "event_id_is_uuid": True,
                    "open_revision": 3,
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
                    "output_layers": (
                        payload.get("output_layers")
                        if isinstance(payload, dict)
                        else None
                    ),
                    "transaction": (
                        {
                            key: transaction.get(key)
                            for key in (
                                "audience_id",
                                "event_type",
                                "expected_revision",
                                "input_reference",
                                "replayed",
                                "source",
                            )
                        }
                        if isinstance(transaction, dict)
                        else None
                    ),
                    "event_id_is_uuid": event_id_is_uuid,
                    "open_revision": (
                        reopened.get("revision")
                        if isinstance(reopened, dict)
                        else None
                    ),
                },
                msg=result.stderr or opened.stderr,
            )

    def test_character_action_is_recorded_as_unresolved_table_work(self) -> None:
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
                "message-action-1",
                "--expected-revision",
                "2",
                "--text",
                "*我尝试撬开北门*",
            )
            payload = json.loads(result.stdout) if result.stdout else None

            self.assertEqual(
                {
                    "returncode": 0,
                    "revision": 3,
                    "message": {
                        "type": "character_action",
                        "speaker_id": "alice",
                        "character_id": "aria",
                        "scene_id": "table",
                        "input_reference": "message-action-1",
                        "content": "我尝试撬开北门",
                        "explicit": True,
                        "audience_id": "table",
                    },
                    "scene_narrative": {
                        "audience_id": "table",
                        "scene_id": "table",
                        "status": "no_scene_change",
                        "items": [],
                    },
                    "table_prompt": {
                        "audience_id": "table",
                        "scene_id": "table",
                        "status": "action_required",
                        "items": [
                            {
                                "kind": "action_resolution_required",
                                "character_id": "aria",
                                "content": "我尝试撬开北门",
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
                    "transaction_audience": (
                        payload["transaction"].get("audience_id")
                        if isinstance(payload, dict)
                        and isinstance(payload.get("transaction"), dict)
                        else None
                    ),
                },
                msg=result.stderr,
            )

    def test_double_slash_ooc_is_explicit_and_non_persistent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "campaign"
            create_ready_campaign(workspace)

            result = run_facade(
                "message",
                str(workspace),
                "--speaker",
                "bob",
                "--scene",
                "table",
                "--input-reference",
                "message-ooc-2",
                "--text",
                "//请保留 *",
            )
            payload = json.loads(result.stdout) if result.stdout else None

            self.assertEqual(
                {
                    "returncode": 0,
                    "revision": 2,
                    "message_type": "ooc",
                    "content": "请保留 *",
                    "explicit": True,
                    "transaction": None,
                },
                {
                    "returncode": result.returncode,
                    "revision": (
                        payload.get("revision")
                        if isinstance(payload, dict)
                        else None
                    ),
                    "message_type": (
                        payload["message"].get("type")
                        if isinstance(payload, dict)
                        and isinstance(payload.get("message"), dict)
                        else None
                    ),
                    "content": (
                        payload["message"].get("content")
                        if isinstance(payload, dict)
                        and isinstance(payload.get("message"), dict)
                        else None
                    ),
                    "explicit": (
                        payload["message"].get("explicit")
                        if isinstance(payload, dict)
                        and isinstance(payload.get("message"), dict)
                        else None
                    ),
                    "transaction": (
                        payload.get("transaction")
                        if isinstance(payload, dict)
                        else None
                    ),
                },
                msg=result.stderr,
            )


if __name__ == "__main__":
    unittest.main()
