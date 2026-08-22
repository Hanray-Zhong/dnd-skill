from __future__ import annotations

from typing import cast

from dnd_5e.errors import FacadeError


_CONFLICT_KEYS = {
    "scope",
    "general_value",
    "specific_value",
    "general_evidence",
    "specific_evidence",
}


def _invalid_conflict() -> FacadeError:
    return FacadeError(
        "invalid_rule_conflict",
        "规则冲突必须提供有界范围、不同取值和两侧原文证据。",
    )


def _validated_conflict(conflict: dict[str, object]) -> dict[str, str]:
    if set(conflict) != _CONFLICT_KEYS:
        raise _invalid_conflict()
    normalized: dict[str, str] = {}
    for key in _CONFLICT_KEYS:
        value = conflict[key]
        if not isinstance(value, str) or not value.strip():
            raise _invalid_conflict()
        normalized[key] = value.strip()
    if normalized["general_value"] == normalized["specific_value"]:
        raise _invalid_conflict()
    if (
        normalized["general_value"] not in normalized["general_evidence"]
        or normalized["specific_value"] not in normalized["specific_evidence"]
    ):
        raise _invalid_conflict()
    return normalized


def build_specific_exception_decision(
    *,
    entity: dict[str, object],
    general_rule: dict[str, object],
    conflict: dict[str, object],
) -> dict[str, object]:
    validated_conflict = _validated_conflict(conflict)
    entity_id = entity.get("id")
    general_rule_id = general_rule.get("id")
    references = entity.get("cross_references")
    entity_markdown = entity.get("conclusion_markdown")
    general_markdown = general_rule.get("conclusion_markdown")
    if (
        not isinstance(entity_id, str)
        or not isinstance(general_rule_id, str)
        or not isinstance(references, list)
        or not all(isinstance(reference, str) for reference in references)
        or not isinstance(entity_markdown, str)
        or not isinstance(general_markdown, str)
    ):
        raise AssertionError("规则章节库返回了未经验证的实体结构。")
    if general_rule_id not in cast(list[str], references):
        raise FacadeError(
            "rule_scope_mismatch",
            "具体实体与指定一般规则之间没有可追溯关联。",
        )
    if (
        validated_conflict["specific_evidence"] not in entity_markdown
        or validated_conflict["general_evidence"] not in general_markdown
    ):
        raise FacadeError(
            "rule_conflict_unverified",
            "规则冲突证据无法在对应的固定规则文本中定位。",
        )
    return {
        "decision": "specific_entity_overrides_general_rule",
        "reason": "三宝书具体实体说明优先于一般默认规则。",
        "applied_rule_id": entity_id,
        "overridden_rule_ids": [general_rule_id],
        "conflict": validated_conflict,
        "precedence": [
            {
                "rank": 3,
                "kind": "specific_entity",
                "rule_id": entity_id,
            },
            {
                "rank": 5,
                "kind": "general_default",
                "rule_id": general_rule_id,
            },
        ],
    }
