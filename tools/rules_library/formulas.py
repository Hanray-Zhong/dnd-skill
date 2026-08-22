from __future__ import annotations

import hashlib
import json

from tools.rules_library.baseline import FormulaSpec
from tools.rules_library.errors import BuildError
from tools.rules_library.models import DraftAsset
from tools.rules_library.text import lookup_key


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _resolve_formula_rule(
    alias: str,
    evidence: str,
    index_items: list[dict[str, object]],
    body_by_id: dict[str, str],
) -> dict[str, object]:
    normalized_alias = lookup_key(alias)
    matches: list[dict[str, object]] = []
    for item in index_items:
        aliases = item.get("aliases")
        if not isinstance(aliases, list):
            raise AssertionError("规则索引缺少已验证别名。")
        if any(
            isinstance(candidate, str) and lookup_key(candidate) == normalized_alias
            for candidate in aliases
        ) and evidence in body_by_id.get(str(item["id"]), ""):
            matches.append(item)
    if len(matches) != 1:
        raise BuildError(
            "unresolved_formula_source",
            f"公式声明无法唯一定位规则来源。别名：{alias}；匹配数：{len(matches)}。",
        )
    return matches[0]


def formula_records(
    specs: tuple[FormulaSpec, ...],
    index_items: list[dict[str, object]],
    drafts: list[DraftAsset],
) -> list[dict[str, object]]:
    if len(index_items) != len(drafts):
        raise AssertionError("规则索引与提取草稿数量不一致。")
    body_by_id = {
        str(item["id"]): "\n\n".join(draft.body_parts).strip()
        for item, draft in zip(index_items, drafts, strict=True)
    }
    records: list[dict[str, object]] = []
    for spec in specs:
        source_rule = _resolve_formula_rule(
            spec.source_rule_alias,
            spec.source_evidence,
            index_items,
            body_by_id,
        )
        rounding_rule = _resolve_formula_rule(
            spec.rounding_rule_alias,
            spec.rounding_evidence,
            index_items,
            body_by_id,
        )
        source_rule_id = str(source_rule["id"])
        rounding_rule_id = str(rounding_rule["id"])
        if (
            source_rule.get("category") != "semantic_section"
            or rounding_rule.get("category") != "semantic_section"
            or source_rule.get("extraction_status") != "verified"
            or rounding_rule.get("extraction_status") != "verified"
            or source_rule.get("rule_status") != "default"
            or rounding_rule.get("rule_status") != "default"
        ):
            raise BuildError(
                "unverified_formula_source",
                "公式声明无法由已验证规则正文复核。",
            )
        records.append(
            {
                "id": spec.formula_id,
                "version": spec.version,
                "title": spec.title,
                "input": {
                    "id": spec.input_id,
                    "unit": spec.input_unit,
                    "type": "integer",
                    "minimum": spec.input_minimum,
                    "maximum": spec.input_maximum,
                },
                "expression": {
                    "kind": "subtract_divide",
                    "subtract": spec.subtract,
                    "divisor": spec.divisor,
                },
                "modifiers": {
                    "target_input": spec.input_id,
                    "allowed_operations": list(spec.modifier_operations),
                    "priority_order": list(spec.priority_order),
                },
                "result": {
                    "unit": spec.result_unit,
                    "rounding": spec.rounding,
                    "rounding_rule_id": rounding_rule_id,
                    "rounding_evidence": spec.rounding_evidence,
                },
                "source": {
                    "rule_id": source_rule_id,
                    "content_sha256": source_rule["content_sha256"],
                    "pages": source_rule["pages"],
                    "source": source_rule["source"],
                    "evidence": spec.source_evidence,
                },
            }
        )
    records.sort(key=lambda record: str(record["id"]))
    return records


def formula_catalog_payload(
    catalog_version: str,
    formulas: list[dict[str, object]],
) -> dict[str, object]:
    identity = {
        "format": "dnd-formula-catalog-v1",
        "catalog_version": catalog_version,
        "formula_count": len(formulas),
        "formulas": formulas,
    }
    return {
        **identity,
        "catalog_sha256": hashlib.sha256(_canonical_json(identity)).hexdigest(),
    }
