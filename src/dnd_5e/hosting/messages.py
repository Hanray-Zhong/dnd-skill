from __future__ import annotations

from pathlib import Path
import sqlite3
import uuid

from dnd_5e.errors import FacadeError
from dnd_5e.messaging.protocol import (
    AmbiguousAction,
    CHARACTER_MESSAGE_TYPES,
    ClassifiedMessage,
    MessageScene,
    TablePromptKind,
    character_controls,
    classify_message,
    message_audience_id,
    message_policy,
)
from dnd_5e.state.messages import read_message_scene, record_message
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


_MESSAGE_SOURCE = "dnd-5e"


def _output_layers(
    classification: ClassifiedMessage,
    *,
    speaker_id: str,
    character_id: str | None,
    scene: MessageScene,
    input_reference: str,
    audience_id: str,
    revision: int,
    transaction: dict[str, object] | None,
) -> dict[str, object]:
    policy = message_policy(classification.message_type)
    prompt_items: list[dict[str, object]] = []
    if policy.prompt_kind == TablePromptKind.ACTION_RESOLUTION_REQUIRED:
        prompt_items.append(
            {
                "kind": policy.prompt_kind.value,
                "character_id": character_id,
                "content": classification.content,
            }
        )
    elif (
        policy.prompt_kind
        == TablePromptKind.SYSTEM_MESSAGE_VALIDATION_REQUIRED
    ):
        prompt_items.append(
            {
                "kind": policy.prompt_kind.value,
                "speaker_id": speaker_id,
                "content": classification.content,
            }
        )

    event_id: str | None = None
    state_changes: dict[str, object] = {}
    if transaction is not None:
        stored_event_id = transaction.get("event_id")
        expected_revision = transaction.get("expected_revision")
        if isinstance(stored_event_id, str):
            event_id = stored_event_id
        if type(expected_revision) is int:
            state_changes["revision"] = {
                "before": expected_revision,
                "after": revision,
            }

    return {
        "scene_narrative": {
            "audience_id": audience_id,
            "scene_id": scene.scene_id,
            "status": scene.narrative_projection.value,
            "items": [],
        },
        "table_prompt": {
            "audience_id": audience_id,
            "scene_id": scene.scene_id,
            "status": policy.prompt_status,
            "items": prompt_items,
        },
        "audit_record": {
            "audience_id": "dm",
            "scene_id": scene.scene_id,
            "items": [
                {
                    "character_id": character_id,
                    "event_id": event_id,
                    "kind": "message_classified",
                    "input_reference": input_reference,
                    "message_type": classification.message_type.value,
                    "persisted": policy.persisted,
                    "revision": revision,
                    "scene_id": scene.scene_id,
                    "source": _MESSAGE_SOURCE,
                    "speaker_id": speaker_id,
                    "state_changes": state_changes,
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
    try:
        classification = classify_message(text)
    except AmbiguousAction as error:
        raise FacadeError(
            "ambiguous_action",
            "角色行动标记不完整，必须先澄清而不能修改战役状态。",
            {
                "input_reference": input_reference,
                "scene_id": scene_id,
                "speaker_id": speaker_id,
            },
        ) from error
    if not classification.content.strip():
        raise FacadeError("invalid_message", "消息正文不能为空。")

    controls = character_controls(summary.initial_config)
    if speaker_id not in controls:
        raise FacadeError(
            "unknown_speaker",
            "发言者不在稳定玩家名册中。",
            {"speaker_id": speaker_id},
        )
    try:
        scene = read_message_scene(database_path, scene_id=scene_id)
    except InvalidStateRequest as error:
        raise FacadeError(
            "invalid_message_context",
            "目标场景不存在或消息交互上下文无效。",
            {"scene_id": scene_id},
        ) from error
    except (OSError, sqlite3.Error, TypeError, ValueError) as error:
        raise _invalid_state_store() from error
    if speaker_id not in scene.participant_player_ids:
        raise FacadeError(
            "scene_access_forbidden",
            "发言者不属于目标场景的交互参与者。",
            {"scene_id": scene_id, "speaker_id": speaker_id},
        )
    if classification.message_type in CHARACTER_MESSAGE_TYPES:
        scene_characters = scene.character_controls.get(speaker_id, frozenset())
        if (
            character_id is None
            or character_id not in controls[speaker_id]
            or character_id not in scene_characters
        ):
            raise FacadeError(
                "character_control_forbidden",
                "发言者无权控制该角色。",
                {
                    "character_id": character_id,
                    "input_reference": input_reference,
                    "message_type": classification.message_type.value,
                    "scene_id": scene_id,
                    "speaker_id": speaker_id,
                },
            )
    elif character_id is not None:
        raise FacadeError(
            "invalid_message",
            "OOC 与待验证系统消息不能声明角色控制。",
        )

    policy = message_policy(classification.message_type)
    audience_id = message_audience_id(
        classification.message_type,
        speaker_id,
        scene,
    )
    transaction: dict[str, object] | None = None
    if policy.persisted:
        if expected_revision is None or expected_revision < 1:
            raise FacadeError(
                "invalid_state_request",
                "需要落盘的消息必须包含有效前置修订号。",
            )
        if character_id is None:
            raise AssertionError("持久消息必须具有已经授权的角色")
        request = MessageRecordRequest(
            expected_revision=expected_revision,
            idempotency_key=f"message:{input_reference}",
            input_reference=input_reference,
            speaker_id=speaker_id,
            character_id=character_id,
            scene_id=scene.scene_id,
            message_type=classification.message_type,
            raw_text=text,
            content=classification.content,
            source=_MESSAGE_SOURCE,
            audience_id=audience_id,
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

    message: dict[str, object] = {
        "type": classification.message_type.value,
        "speaker_id": speaker_id,
        "character_id": character_id,
        "scene_id": scene_id,
        "input_reference": input_reference,
        "content": classification.content,
        "explicit": classification.explicit,
        "audience_id": audience_id,
    }
    return {
        "ok": True,
        "operation": "message",
        "campaign_id": summary.campaign_id,
        "revision": summary.revision,
        "message": message,
        "output_layers": _output_layers(
            classification,
            speaker_id=speaker_id,
            character_id=character_id,
            scene=scene,
            input_reference=input_reference,
            audience_id=audience_id,
            revision=summary.revision,
            transaction=transaction,
        ),
        "transaction": transaction,
    }
