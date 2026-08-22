from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3

from dnd_5e.errors import FacadeError
from dnd_5e.formulas import FormulaCatalog
from dnd_5e.messaging.protocol import character_controls
from dnd_5e.state.audiences import read_audiences
from dnd_5e.state.encoding import canonical_json
from dnd_5e.state.types import (
    CampaignSummary,
    DerivedValueMap,
    FormulaCalculationRequest,
    FormulaCalculationUpdate,
    IdempotencyConflict,
    InvalidStateRequest,
    READY_TO_PLAY,
    RevisionConflict,
)


def _derived_entity_id(character_id: str, formula_id: str) -> str:
    digest = hashlib.sha256(
        f"{character_id}\0{formula_id}".encode("utf-8")
    ).hexdigest()
    return f"character-derived-value:{digest}"


def read_derived_values(connection: sqlite3.Connection) -> DerivedValueMap:
    derived_values: DerivedValueMap = {}
    rows = connection.execute(
        """
        SELECT payload_json
        FROM entities
        WHERE entity_type = 'character_derived_value'
        ORDER BY entity_id
        """
    ).fetchall()
    for (payload_json,) in rows:
        try:
            calculation: object = json.loads(payload_json)
        except (TypeError, json.JSONDecodeError) as error:
            raise sqlite3.DatabaseError("角色派生数据损坏") from error
        if not isinstance(calculation, dict):
            raise sqlite3.DatabaseError("角色派生数据损坏")
        character_id = calculation.get("character_id")
        formula = calculation.get("formula")
        if (
            not isinstance(character_id, str)
            or not isinstance(formula, dict)
            or not isinstance(formula.get("id"), str)
        ):
            raise sqlite3.DatabaseError("角色派生数据损坏")
        formula_id = formula["id"]
        character_values = derived_values.setdefault(character_id, {})
        if formula_id in character_values:
            raise sqlite3.DatabaseError("角色派生数据稳定标识重复")
        character_values[formula_id] = calculation
    return derived_values


def _summary_payload(summary: CampaignSummary) -> dict[str, object]:
    return {
        "audiences": summary.audiences,
        "campaign_id": summary.campaign_id,
        "campaign_status": summary.campaign_status,
        "created_at": summary.created_at,
        "derived_values": summary.derived_values,
        "initial_config": summary.initial_config,
        "revision": summary.revision,
    }


def _update_from_result(
    result_json: str,
    *,
    event_id: str,
    request: FormulaCalculationRequest,
) -> FormulaCalculationUpdate:
    try:
        result: object = json.loads(result_json)
    except json.JSONDecodeError as error:
        raise sqlite3.DatabaseError("公式幂等请求结果损坏") from error
    if not isinstance(result, dict):
        raise sqlite3.DatabaseError("公式幂等请求结果损坏")
    raw_summary = result.get("summary")
    calculation = result.get("calculation")
    if not isinstance(raw_summary, dict) or not isinstance(calculation, dict):
        raise sqlite3.DatabaseError("公式幂等请求结果损坏")
    campaign_id = raw_summary.get("campaign_id")
    created_at = raw_summary.get("created_at")
    revision = raw_summary.get("revision")
    initial_config = raw_summary.get("initial_config")
    audiences = raw_summary.get("audiences")
    derived_values = raw_summary.get("derived_values")
    if (
        not isinstance(campaign_id, str)
        or not isinstance(created_at, str)
        or type(revision) is not int
        or raw_summary.get("campaign_status") != READY_TO_PLAY
        or not isinstance(initial_config, dict)
        or not isinstance(audiences, dict)
        or not isinstance(derived_values, dict)
        or calculation != request.calculation
    ):
        raise sqlite3.DatabaseError("公式幂等请求结果损坏")
    return FormulaCalculationUpdate(
        summary=CampaignSummary(
            campaign_id=campaign_id,
            created_at=created_at,
            revision=revision,
            campaign_status=READY_TO_PLAY,
            initial_config=initial_config,
            audiences=audiences,
            derived_values=derived_values,
        ),
        event_id=event_id,
        request=request,
        calculation=calculation,
        replayed=True,
    )


def commit_formula_calculation(
    database_path: Path,
    *,
    request: FormulaCalculationRequest,
    event_id: str,
    committed_at: str,
) -> FormulaCalculationUpdate:
    formula = request.calculation.get("formula")
    calculation_modifiers = request.calculation.get("modifiers")
    if (
        request.expected_revision < 1
        or not request.idempotency_key.strip()
        or not request.character_id.strip()
        or not request.formula_id.strip()
        or request.source != "dnd-5e-character"
        or request.audience_id != "dm"
        or request.calculation.get("character_id") != request.character_id
        or not isinstance(formula, dict)
        or formula.get("id") != request.formula_id
        or request.calculation.get("inputs") != request.inputs
        or not isinstance(calculation_modifiers, dict)
        or calculation_modifiers.get("applied") is None
    ):
        raise InvalidStateRequest("公式状态请求字段无效")
    try:
        verified_calculation = FormulaCatalog().calculate(
            formula_id=request.formula_id,
            character_id=request.character_id,
            inputs=request.inputs,
            modifiers=request.modifiers,
        )
    except FacadeError as error:
        raise InvalidStateRequest("公式状态请求无法由固定目录复算") from error
    if verified_calculation != request.calculation:
        raise InvalidStateRequest("公式状态请求结果与固定目录复算不一致")
    request_json = canonical_json(
        {
            "audience_id": request.audience_id,
            "character_id": request.character_id,
            "expected_revision": request.expected_revision,
            "formula_id": request.formula_id,
            "inputs": request.inputs,
            "modifiers": request.modifiers,
            "operation": "recalculate_character_derived_value",
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
                update = _update_from_result(
                    str(stored_result),
                    event_id=str(stored_event_id),
                    request=request,
                )
                connection.rollback()
                return update

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
            if (
                not isinstance(initial_config, dict)
                or payload.get("campaign_status") != READY_TO_PLAY
            ):
                raise InvalidStateRequest("战役尚未完成 Session Zero")
            controls = character_controls(initial_config)
            if not any(
                request.character_id in character_ids
                for character_ids in controls.values()
            ):
                raise InvalidStateRequest("角色不在已确认玩家名册中")
            audiences = read_audiences(connection)
            if request.audience_id not in audiences:
                raise InvalidStateRequest("公式事件受众不存在")
            current = CampaignSummary(
                campaign_id=str(campaign_id),
                created_at=str(created_at),
                revision=int(current_revision),
                campaign_status=READY_TO_PLAY,
                initial_config=initial_config,
                audiences=audiences,
                derived_values=read_derived_values(connection),
            )
            if current.revision != request.expected_revision:
                raise RevisionConflict(current)

            new_revision = current.revision + 1
            updated_derived_values = {
                character_id: dict(formulas)
                for character_id, formulas in current.derived_values.items()
            }
            updated_derived_values.setdefault(request.character_id, {})[
                request.formula_id
            ] = request.calculation
            summary = CampaignSummary(
                campaign_id=current.campaign_id,
                created_at=current.created_at,
                revision=new_revision,
                campaign_status=READY_TO_PLAY,
                initial_config=current.initial_config,
                audiences=current.audiences,
                derived_values=updated_derived_values,
            )
            result_json = canonical_json(
                {
                    "calculation": request.calculation,
                    "summary": _summary_payload(summary),
                }
            )
            event_payload = canonical_json(
                {
                    "calculation": request.calculation,
                    "expected_revision": request.expected_revision,
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
                """
                INSERT INTO entities VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(entity_id) DO UPDATE SET
                    entity_type = excluded.entity_type,
                    schema_version = excluded.schema_version,
                    revision = excluded.revision,
                    payload_json = excluded.payload_json
                """,
                (
                    _derived_entity_id(request.character_id, request.formula_id),
                    "character_derived_value",
                    1,
                    new_revision,
                    canonical_json(request.calculation),
                ),
            )
            connection.execute(
                "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    event_id,
                    new_revision,
                    1,
                    "character_derived_value_recalculated",
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

    return FormulaCalculationUpdate(
        summary=summary,
        event_id=event_id,
        request=request,
        calculation=request.calculation,
        replayed=False,
    )
