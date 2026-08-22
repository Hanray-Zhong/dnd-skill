from __future__ import annotations

import json
from pathlib import Path
import sqlite3

from dnd_5e.state.encoding import canonical_json
from dnd_5e.state.types import (
    AWAITING_SESSION_ZERO,
    CampaignSummary,
    IdempotencyConflict,
    READY_TO_PLAY,
    RevisionConflict,
    SessionZeroCompletion,
    SessionZeroRequest,
)


def _completion_from_result(
    result_json: str,
    *,
    event_id: str,
    request: SessionZeroRequest,
) -> SessionZeroCompletion:
    result = json.loads(result_json)
    if not isinstance(result, dict):
        raise sqlite3.DatabaseError("Session Zero 幂等请求结果损坏")
    campaign_id = result.get("campaign_id")
    campaign_status = result.get("campaign_status")
    created_at = result.get("created_at")
    configuration = result.get("initial_config")
    revision = result.get("revision")
    audiences = result.get("audiences")
    if (
        not isinstance(campaign_id, str)
        or campaign_status != READY_TO_PLAY
        or not isinstance(created_at, str)
        or not isinstance(configuration, dict)
        or type(revision) is not int
        or not isinstance(audiences, dict)
    ):
        raise sqlite3.DatabaseError("Session Zero 幂等请求结果损坏")
    typed_audiences: dict[str, dict[str, object]] = {}
    for audience_id, definition in audiences.items():
        if not isinstance(audience_id, str) or not isinstance(definition, dict):
            raise sqlite3.DatabaseError("Session Zero 幂等请求结果损坏")
        typed_audiences[audience_id] = definition
    return SessionZeroCompletion(
        summary=CampaignSummary(
            campaign_id=campaign_id,
            created_at=created_at,
            revision=revision,
            campaign_status=campaign_status,
            initial_config=configuration,
            audiences=typed_audiences,
        ),
        event_id=event_id,
        request=request,
        replayed=True,
    )


def commit_session_zero(
    database_path: Path,
    *,
    request: SessionZeroRequest,
    event_id: str,
    committed_at: str,
) -> SessionZeroCompletion:
    request_json = canonical_json(
        {
            "audience_id": request.audience_id,
            "audiences": request.audiences,
            "configuration": request.configuration,
            "expected_revision": request.expected_revision,
            "operation": "complete_session_zero",
            "source": request.source,
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
                completion = _completion_from_result(
                    str(stored_result),
                    event_id=str(stored_event_id),
                    request=request,
                )
                connection.rollback()
                return completion

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
                raise sqlite3.DatabaseError("战役状态库缺少一致的 campaign 当前修订")
            campaign_id, created_at, current_revision, campaign_payload = metadata
            current_payload = json.loads(campaign_payload)
            if (
                not isinstance(current_payload, dict)
                or current_payload.get("campaign_status") != AWAITING_SESSION_ZERO
                or not isinstance(current_payload.get("initial_config"), dict)
            ):
                raise sqlite3.DatabaseError("战役不处于可完成 Session Zero 的状态")
            current = CampaignSummary(
                campaign_id=str(campaign_id),
                created_at=str(created_at),
                revision=int(current_revision),
                campaign_status=AWAITING_SESSION_ZERO,
                initial_config=current_payload["initial_config"],
            )
            if current.revision != request.expected_revision:
                raise RevisionConflict(current)

            new_revision = current.revision + 1
            updated_payload = canonical_json(
                {
                    "campaign_status": READY_TO_PLAY,
                    "initial_config": request.configuration,
                }
            )
            event_payload = canonical_json(
                {
                    "audiences": request.audiences,
                    "campaign_id": current.campaign_id,
                    "campaign_status": READY_TO_PLAY,
                    "configuration": request.configuration,
                    "expected_revision": request.expected_revision,
                }
            )
            summary = CampaignSummary(
                campaign_id=current.campaign_id,
                created_at=current.created_at,
                revision=new_revision,
                campaign_status=READY_TO_PLAY,
                initial_config=request.configuration,
                audiences=request.audiences,
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
                SET revision = ?, payload_json = ?
                WHERE entity_id = ?
                  AND entity_type = 'campaign'
                  AND revision = ?
                """,
                (
                    new_revision,
                    updated_payload,
                    current.campaign_id,
                    current.revision,
                ),
            ).rowcount
            if updated_rows != 1:
                raise sqlite3.DatabaseError("campaign 当前实体更新失败")
            connection.execute(
                "UPDATE campaign_metadata SET current_revision = ? WHERE singleton = 1",
                (new_revision,),
            )
            for audience_id, definition in request.audiences.items():
                audience_type = definition.get("audience_type")
                members = definition.get("members")
                connection.execute(
                    """
                    INSERT INTO audiences VALUES (?, ?, ?)
                    ON CONFLICT(audience_id) DO UPDATE SET
                        audience_type = excluded.audience_type,
                        definition_json = excluded.definition_json
                    """,
                    (
                        audience_id,
                        audience_type,
                        canonical_json({"members": members}),
                    ),
                )
            connection.execute(
                "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    event_id,
                    new_revision,
                    1,
                    "session_zero_completed",
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

    return SessionZeroCompletion(
        summary=summary,
        event_id=event_id,
        request=request,
        replayed=False,
    )
