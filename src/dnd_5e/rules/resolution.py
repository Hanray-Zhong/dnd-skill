from __future__ import annotations

from typing import Any, cast

from dnd_5e.errors import FacadeError


_EXCEPTION_KEYS = {
    "id",
    "specific_rule_id",
    "general_rule_id",
    "scope",
    "general_value",
    "specific_value",
    "general_evidence",
    "specific_evidence",
    "review_status",
    "review_evidence",
}


def _invalid_library() -> FacadeError:
    return FacadeError(
        "invalid_rules_library",
        "规则章节库缺失、损坏或内容哈希不一致。",
    )


def validate_rule_exceptions(
    manifest: dict[str, Any],
    index_items: tuple[dict[str, object], ...],
) -> tuple[dict[str, object], ...]:
    raw_items = manifest.get("items")
    if manifest.get("format") != "dnd-rules-exceptions-v1" or not isinstance(
        raw_items, list
    ):
        raise _invalid_library()
    rules_by_id = {str(item["id"]): item for item in index_items}
    exceptions: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    seen_pairs: set[tuple[str, str]] = set()
    for raw_item in raw_items:
        if not isinstance(raw_item, dict) or set(raw_item) != _EXCEPTION_KEYS:
            raise _invalid_library()
        if not all(
            isinstance(raw_item[key], str) and raw_item[key].strip()
            for key in _EXCEPTION_KEYS
        ):
            raise _invalid_library()
        exception_id = str(raw_item["id"])
        specific_id = str(raw_item["specific_rule_id"])
        general_id = str(raw_item["general_rule_id"])
        specific = rules_by_id.get(specific_id)
        general = rules_by_id.get(general_id)
        pair = (specific_id, general_id)
        if (
            exception_id in seen_ids
            or pair in seen_pairs
            or specific is None
            or general is None
            or specific_id == general_id
            or specific.get("category") == "semantic_section"
            or general.get("rule_status") != "default"
            or raw_item.get("review_status") != "verified"
            or raw_item["general_value"] == raw_item["specific_value"]
            or str(raw_item["general_value"])
            not in str(raw_item["general_evidence"])
            or str(raw_item["specific_value"])
            not in str(raw_item["specific_evidence"])
        ):
            raise _invalid_library()
        references = specific.get("cross_references")
        if not isinstance(references, list) or general_id not in cast(
            list[object], references
        ):
            raise _invalid_library()
        seen_ids.add(exception_id)
        seen_pairs.add(pair)
        exceptions.append(dict(raw_item))
    exceptions.sort(key=lambda item: str(item["id"]))
    return tuple(exceptions)


def _rule_body(rule: dict[str, object]) -> str:
    markdown = rule.get("conclusion_markdown")
    if not isinstance(markdown, str) or not markdown.startswith("---\n"):
        raise _invalid_library()
    _, separator, body = markdown.partition("\n---\n\n")
    if not separator or not body:
        raise _invalid_library()
    return body


def build_specific_exception_decision(
    *,
    entity: dict[str, object],
    general_rule: dict[str, object],
    exception: dict[str, object],
) -> dict[str, object]:
    entity_id = entity.get("id")
    general_rule_id = general_rule.get("id")
    if (
        not isinstance(entity_id, str)
        or not isinstance(general_rule_id, str)
        or exception.get("specific_rule_id") != entity_id
        or exception.get("general_rule_id") != general_rule_id
        or str(exception["specific_evidence"]) not in _rule_body(entity)
        or str(exception["general_evidence"]) not in _rule_body(general_rule)
    ):
        raise _invalid_library()
    conflict = {
        key: exception[key]
        for key in (
            "scope",
            "general_value",
            "specific_value",
            "general_evidence",
            "specific_evidence",
        )
    }
    return {
        "decision": "specific_entity_overrides_general_rule",
        "reason": "三宝书具体实体说明优先于一般默认规则。",
        "exception_id": exception["id"],
        "applied_rule_id": entity_id,
        "overridden_rule_ids": [general_rule_id],
        "conflict": conflict,
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
