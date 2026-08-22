from __future__ import annotations

from pathlib import Path
import sqlite3
import uuid

from dnd_5e.errors import FacadeError
from dnd_5e.state.messages import record_message
from dnd_5e.state.types import (
    IdempotencyConflict,
    InvalidStateRequest,
    MessageRecordRequest,
    READY_TO_PLAY,
    RevisionConflict,
)
from dnd_5e.workspace import (
    _created_at,
    _invalid_state_store,
    _load_existing_campaign,
)


def _character_controls(
    configuration: dict[str, object],
) -> dict[str, set[str]]:
    players = configuration.get("players")
    if not isinstance(players, list):
        return {}
    controls: dict[str, set[str]] = {}
    for player in players:
        if not isinstance(player, dict):
            continue
        player_id = player.get("player_id")
        character_ids = player.get("character_ids")
        if not isinstance(player_id, str) or not isinstance(character_ids, list):
            continue
        controls[player_id] = {
            character_id
            for character_id in character_ids
            if isinstance(character_id, str)
        }
    return controls


def _classify(text: str) -> tuple[str, str, bool]:
    if text.startswith("“") and text.endswith("”") and len(text) > 2:
        return "character_dialogue", text[1:-1], True
    if text.startswith("*") and text.endswith("*") and len(text) > 2:
        return "character_action", text[1:-1], True
    inner_prefix = "（内心："
    if (
        text.startswith(inner_prefix)
        and text.endswith("）")
        and len(text) > len(inner_prefix) + 1
    ):
        return "character_inner", text[len(inner_prefix) : -1], True
    if text.startswith("//") and len(text) > 2:
        return "ooc", text[2:], True
    if text.startswith("【") and text.endswith("】") and len(text) > 2:
        return "system", text[1:-1], True
    return "ooc", text, False


def _output_layers(
    message: dict[str, object],
    *,
    persisted: bool,
) -> dict[str, object]:
    message_type = message["type"]
    speaker_id = message["speaker_id"]
    character_id = message["character_id"]
    content = message["content"]
    input_reference = message["input_reference"]
    output_audience = (
        f"player:{speaker_id}"
        if message_type == "character_inner"
        else "table"
    )
    narrative_items: list[dict[str, object]] = []
    prompt_items: list[dict[str, object]] = []
    if message_type == "character_dialogue":
        narrative_items.append(
            {
                "kind": "character_dialogue",
                "character_id": character_id,
                "content": content,
            }
        )
    elif message_type == "character_action":
        prompt_items.append(
            {
                "kind": "action_resolution_required",
                "character_id": character_id,
                "content": content,
            }
        )
    elif message_type == "character_inner":
        narrative_items.append(
            {
                "kind": "character_inner",
                "character_id": character_id,
                "content": content,
            }
        )
    elif message_type == "system":
        prompt_items.append(
            {
                "kind": "system_message",
                "content": content,
            }
        )
    else:
        prompt_items.append(
            {
                "kind": "ooc_message",
                "speaker_id": speaker_id,
                "content": content,
            }
        )
    return {
        "scene_narrative": {
            "audience_id": output_audience,
            "items": narrative_items,
        },
        "table_prompt": {
            "audience_id": output_audience,
            "items": prompt_items,
        },
        "audit_record": {
            "audience_id": "dm",
            "items": [
                {
                    "kind": "message_classified",
                    "input_reference": input_reference,
                    "message_type": message_type,
                    "persisted": persisted,
                }
            ],
        },
    }


def handle_message(
    workspace: Path,
    *,
    speaker_id: str,
    scene_id: str,
    input_reference: str,
    text: str,
    character_id: str | None = None,
    expected_revision: int | None = None,
) -> dict[str, object]:
    if not all(
        value.strip()
        for value in (speaker_id, scene_id, input_reference, text)
    ):
        raise FacadeError(
            "invalid_message",
            "消息必须包含发言者、目标场景、原始输入引用和正文。",
        )
    _, database_path, summary = _load_existing_campaign(workspace)
    if summary.campaign_status != READY_TO_PLAY:
        raise FacadeError(
            "campaign_not_ready",
            "战役必须先完成 Session Zero 才能处理玩家消息。",
        )
    if text.startswith("*") != text.endswith("*"):
        raise FacadeError(
            "ambiguous_action",
            "角色行动标记不完整，必须先澄清而不能修改战役状态。",
            {
                "input_reference": input_reference,
                "scene_id": scene_id,
                "speaker_id": speaker_id,
            },
        )
    controls = _character_controls(summary.initial_config)
    message_type, content, explicit = _classify(text)
    if message_type == "system":
        if speaker_id != "system":
            raise FacadeError(
                "forged_system_message",
                "玩家文本不能伪造桌务或系统结果。",
                {
                    "input_reference": input_reference,
                    "message_type": message_type,
                    "scene_id": scene_id,
                    "speaker_id": speaker_id,
                },
            )
    elif speaker_id not in controls:
        raise FacadeError(
            "unknown_speaker",
            "发言者不在稳定玩家名册中。",
            {"speaker_id": speaker_id},
        )

    persisted = message_type in {
        "character_dialogue",
        "character_action",
        "character_inner",
        "system",
    }
    if message_type.startswith("character_") and (
        character_id is None or character_id not in controls[speaker_id]
    ):
        raise FacadeError(
            "character_control_forbidden",
            "发言者无权控制该角色。",
            {
                "character_id": character_id,
                "input_reference": input_reference,
                "message_type": message_type,
                "scene_id": scene_id,
                "speaker_id": speaker_id,
            },
        )

    message: dict[str, object] = {
        "type": message_type,
        "speaker_id": speaker_id,
        "character_id": character_id,
        "scene_id": scene_id,
        "input_reference": input_reference,
        "content": content,
        "explicit": explicit,
    }
    output_layers = _output_layers(message, persisted=persisted)
    transaction: dict[str, object] | None = None
    if persisted:
        if expected_revision is None or expected_revision < 1:
            raise FacadeError(
                "invalid_state_request",
                "需要落盘的消息必须包含有效前置修订号。",
            )
        message_audience = (
            f"player:{speaker_id}"
            if message_type == "character_inner"
            else "table"
        )
        request = MessageRecordRequest(
            expected_revision=expected_revision,
            idempotency_key=f"message:{input_reference}",
            input_reference=input_reference,
            speaker_id=speaker_id,
            character_id=character_id,
            scene_id=scene_id,
            message_type=message_type,
            raw_text=text,
            content=content,
            source="dnd-5e",
            audience_id=message_audience,
        )
        try:
            record = record_message(
                database_path,
                request=request,
                event_id=str(uuid.uuid4()),
                committed_at=_created_at(),
            )
        except RevisionConflict as error:
            raise FacadeError(
                "revision_conflict",
                "状态变更请求基于过期修订，必须先重新打开战役并重新对账。",
                {
                    "expected_revision": expected_revision,
                    "current_revision": error.current.revision,
                },
            ) from error
        except IdempotencyConflict as error:
            raise FacadeError(
                "idempotency_conflict",
                "该原始输入引用已用于不同的消息。",
            ) from error
        except InvalidStateRequest as error:
            raise FacadeError(
                "invalid_state_request",
                "消息状态变更请求无效。",
            ) from error
        except (OSError, sqlite3.Error) as error:
            raise FacadeError(
                "state_commit_failed",
                "消息状态事务写入失败，未提交任何部分状态。",
            ) from error
        except (TypeError, ValueError) as error:
            raise _invalid_state_store() from error
        summary = record.summary
        transaction = {
            "audience_id": request.audience_id,
            "event_id": record.event_id,
            "event_type": "message_recorded",
            "expected_revision": request.expected_revision,
            "input_reference": request.input_reference,
            "replayed": record.replayed,
            "source": request.source,
        }
    return {
        "ok": True,
        "operation": "message",
        "campaign_id": summary.campaign_id,
        "revision": summary.revision,
        "message": message,
        "output_layers": output_layers,
        "transaction": transaction,
    }
