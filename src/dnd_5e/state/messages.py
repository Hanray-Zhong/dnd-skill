from __future__ import annotations

import json
from pathlib import Path
import sqlite3

from dnd_5e.state.audiences import read_audiences, validate_audiences
from dnd_5e.state.encoding import canonical_json
from dnd_5e.state.types import (
    CampaignSummary,
    IdempotencyConflict,
    InvalidStateRequest,
    MessageRecord,
    MessageRecordRequest,
    READY_TO_PLAY,
    RevisionConflict,
)


def _record_from_result(
    result_json: str,
    *,
    event_id: str,
    request: MessageRecordRequest,
) -> MessageRecord:
    result = json.loads(result_json)
    if not isinstance(result, dict):
        raise sqlite3.DatabaseError("消息幂等请求结果损坏")
    campaign_id = result.get("campaign_id")
    campaign_status = result.get("campaign_status")
    created_at = result.get("created_at")
    initial_config = result.get("initial_config")
    revision = result.get("revision")
    audiences = result.get("audiences")
    if (
        not isinstance(campaign_id, str)
        or campaign_status != READY_TO_PLAY
        or not isinstance(created_at, str)
        or not isinstance(initial_config, dict)
        or type(revision) is not int
        or not isinstance(audiences, dict)
    ):
        raise sqlite3.DatabaseError("消息幂等请求结果损坏")
    try:
        typed_audiences = validate_audiences(
            audiences,
            required_audience_id=request.audience_id,
        )
    except InvalidStateRequest as error:
        raise sqlite3.DatabaseError("消息幂等请求结果损坏") from error
    return MessageRecord(
        summary=CampaignSummary(
            campaign_id=campaign_id,
            created_at=created_at,
            revision=revision,
            campaign_status=campaign_status,
            initial_config=initial_config,
            audiences=typed_audiences,
        ),
        event_id=event_id,
        request=request,
        replayed=True,
    )


def record_message(
    database_path: Path,
    *,
    request: MessageRecordRequest,
    event_id: str,
    committed_at: str,
) -> MessageRecord:
    if (
        request.expected_revision < 1
        or not request.idempotency_key.strip()
        or not request.input_reference.strip()
        or not request.speaker_id.strip()
        or not request.scene_id.strip()
        or not request.message_type.strip()
        or not request.raw_text.strip()
        or not request.content.strip()
        or not request.source.strip()
        or not request.audience_id.strip()
    ):
        raise InvalidStateRequest("消息状态请求字段无效")
    request_json = canonical_json(
        {
            "audience_id": request.audience_id,
            "character_id": request.character_id,
            "content": request.content,
            "expected_revision": request.expected_revision,
            "input_reference": request.input_reference,
            "message_type": request.message_type,
            "operation": "record_message",
            "raw_text": request.raw_text,
            "scene_id": request.scene_id,
            "source": request.source,
            "speaker_id": request.speaker_id,
        }
    )
    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("BEGIN IMMEDIATE")
        try:
            existing = connection.execute(
                """
                SELECT request_json, event_id, result_json
                FROM state_requests
                WHERE idempotency_key = ?
                """,
                (request.idempotency_key,),
            ).fetchone()
            if existing is not None:
                stored_request, stored_event_id, stored_result = existing
                if stored_request != request_json:
                    raise IdempotencyConflict
                result = _record_from_result(
                    str(stored_result),
                    event_id=str(stored_event_id),
                    request=request,
                )
                connection.rollback()
                return result

            metadata = connection.execute(
                """
                SELECT metadata.campaign_id,
                       metadata.created_at,
                       metadata.current_revision,
                       campaign.payload_json
                FROM campaign_metadata AS metadata
                JOIN entities AS campaign
                  ON campaign.entity_id = metadata.campaign_id
                 AND campaign.entity_type = 'campaign'
                 AND campaign.revision = metadata.current_revision
                WHERE metadata.singleton = 1
                """
            ).fetchone()
            if metadata is None:
                raise sqlite3.DatabaseError(
                    "战役状态库缺少一致的 campaign 当前修订"
                )
            campaign_id, created_at, current_revision, campaign_payload = metadata
            payload = json.loads(campaign_payload)
            initial_config = (
                payload.get("initial_config") if isinstance(payload, dict) else None
            )
            campaign_status = (
                payload.get("campaign_status") if isinstance(payload, dict) else None
            )
            if (
                not isinstance(initial_config, dict)
                or campaign_status != READY_TO_PLAY
            ):
                raise sqlite3.DatabaseError("campaign 实体尚未进入可开团状态")
            typed_audiences = read_audiences(connection)
            if request.audience_id not in typed_audiences:
                raise InvalidStateRequest("消息事件受众不存在")
            current = CampaignSummary(
                campaign_id=str(campaign_id),
                created_at=str(created_at),
                revision=int(current_revision),
                campaign_status=campaign_status,
                initial_config=initial_config,
                audiences=typed_audiences,
            )
            if current.revision != request.expected_revision:
                raise RevisionConflict(current)

            new_revision = current.revision + 1
            event_payload = canonical_json(
                {
                    "character_id": request.character_id,
                    "content": request.content,
                    "input_reference": request.input_reference,
                    "message_type": request.message_type,
                    "raw_text": request.raw_text,
                    "scene_id": request.scene_id,
                    "speaker_id": request.speaker_id,
                }
            )
            summary = CampaignSummary(
                campaign_id=current.campaign_id,
                created_at=current.created_at,
                revision=new_revision,
                campaign_status=current.campaign_status,
                initial_config=current.initial_config,
                audiences=current.audiences,
            )
            result_json = canonical_json(
                {
                    "audiences": summary.audiences,
                    "campaign_id": summary.campaign_id,
                    "campaign_status": summary.campaign_status,
                    "created_at": summary.created_at,
                    "initial_config": summary.initial_config,
                    "revision": summary.revision,
                }
            )

            connection.execute(
                "INSERT INTO revisions VALUES (?, ?, ?)",
                (new_revision, committed_at, "dnd-5e-campaign-state"),
            )
            updated_rows = connection.execute(
                """
                UPDATE entities
                SET revision = ?
                WHERE entity_id = ?
                  AND entity_type = 'campaign'
                  AND revision = ?
                """,
                (new_revision, current.campaign_id, current.revision),
            ).rowcount
            if updated_rows != 1:
                raise sqlite3.DatabaseError("campaign 当前实体更新失败")
            connection.execute(
                "UPDATE campaign_metadata SET current_revision = ? WHERE singleton = 1",
                (new_revision,),
            )
            connection.execute(
                "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    event_id,
                    new_revision,
                    1,
                    "message_recorded",
                    request.source,
                    request.audience_id,
                    event_payload,
                ),
            )
            connection.execute(
                "INSERT INTO state_requests VALUES (?, ?, ?, ?, ?, ?)",
                (
                    request.idempotency_key,
                    request_json,
                    current.revision,
                    new_revision,
                    event_id,
                    result_json,
                ),
            )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise

    return MessageRecord(
        summary=summary,
        event_id=event_id,
        request=request,
        replayed=False,
    )
