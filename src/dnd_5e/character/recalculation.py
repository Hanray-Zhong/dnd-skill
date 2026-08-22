from __future__ import annotations

from pathlib import Path
import sqlite3
import uuid

from dnd_5e.errors import FacadeError
from dnd_5e.formulas import FormulaCatalog
from dnd_5e.state.formulas import commit_formula_calculation
from dnd_5e.state.types import (
    FormulaCalculationRequest,
    FormulaCalculationUpdate,
    IdempotencyConflict,
    InvalidStateRequest,
    READY_TO_PLAY,
    RevisionConflict,
)
from dnd_5e.workspace import _created_at, _load_existing_campaign


def recalculate_character_derived_value(
    workspace: Path,
    *,
    expected_revision: int,
    idempotency_key: str,
    character_id: str,
    formula_id: str,
    inputs: dict[str, object],
    modifiers: list[dict[str, object]],
) -> FormulaCalculationUpdate:
    if (
        expected_revision < 1
        or not idempotency_key.strip()
        or not character_id.strip()
        or not formula_id.strip()
    ):
        raise FacadeError(
            "invalid_state_request",
            "重算请求必须包含有效修订号、幂等键、角色和公式标识。",
        )
    _, database_path, summary = _load_existing_campaign(workspace)
    if summary.campaign_status != READY_TO_PLAY:
        raise FacadeError(
            "campaign_not_ready",
            "战役尚未完成 Session Zero，不能重算角色派生数据。",
        )
    catalog = FormulaCatalog()
    calculation = catalog.calculate(
        formula_id=formula_id,
        character_id=character_id,
        inputs=inputs,
        modifiers=modifiers,
    )
    request = FormulaCalculationRequest(
        expected_revision=expected_revision,
        idempotency_key=idempotency_key,
        character_id=character_id,
        formula_id=formula_id,
        inputs=inputs,
        modifiers=modifiers,
        calculation=calculation,
        source="dnd-5e-character",
        audience_id="dm",
    )
    try:
        return commit_formula_calculation(
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
            "该幂等键已用于不同的状态变更请求。",
        ) from error
    except InvalidStateRequest as error:
        raise FacadeError("invalid_state_request", str(error)) from error
    except (OSError, sqlite3.Error) as error:
        raise FacadeError(
            "state_commit_failed",
            "状态事务写入失败，未提交任何部分状态。",
        ) from error
