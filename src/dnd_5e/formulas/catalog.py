from __future__ import annotations

from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
from typing import Any, cast

from dnd_5e.errors import FacadeError


_FORMULA_KEYS = {
    "id",
    "version",
    "title",
    "input",
    "expression",
    "modifiers",
    "result",
    "source",
}
_MODIFIER_KEYS = {
    "id",
    "operation",
    "priority",
    "source",
    "target",
    "unit",
    "value",
}
_LIBRARY_IDENTITY_KEYS = (
    "build_tool_version",
    "normalizer_version",
    "parser_versions",
    "sources_sha256",
    "index_sha256",
    "coverage_sha256",
    "blocked_sha256",
    "exceptions_sha256",
    "formulas_sha256",
    "asset_count",
    "category_counts",
    "distribution",
)


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _invalid_catalog() -> FacadeError:
    return FacadeError(
        "invalid_formula_catalog",
        "公式目录缺失、损坏或内容哈希不一致。",
    )


def default_formula_catalog_path() -> Path:
    packaged = Path(__file__).resolve().parents[1] / "rule_assets" / "formulas.json"
    if packaged.is_file():
        return packaged
    return Path(__file__).resolve().parents[3] / "build" / "rules-library" / "formulas.json"


def installed_formula_catalog_identity() -> dict[str, str]:
    path = default_formula_catalog_path()
    if not path.is_file():
        empty = {"catalog_version": "bootstrap-empty-v1", "formulas": []}
        return {
            "version": "bootstrap-empty-v1",
            "sha256": _sha256(_canonical_json(empty)),
        }
    catalog = FormulaCatalog(path)
    return {"version": catalog.version, "sha256": catalog.sha256}


def _require_string(mapping: dict[str, Any], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise _invalid_catalog()
    return value


def _validate_formula(raw: object) -> dict[str, object]:
    if not isinstance(raw, dict) or set(raw) != _FORMULA_KEYS:
        raise _invalid_catalog()
    formula_id = _require_string(raw, "id")
    _require_string(raw, "version")
    _require_string(raw, "title")
    formula_input = raw.get("input")
    expression = raw.get("expression")
    modifiers = raw.get("modifiers")
    result = raw.get("result")
    source = raw.get("source")
    if (
        not isinstance(formula_input, dict)
        or set(formula_input) != {"id", "maximum", "minimum", "type", "unit"}
        or formula_input.get("type") != "integer"
        or type(formula_input.get("minimum")) is not int
        or type(formula_input.get("maximum")) is not int
        or formula_input["minimum"] > formula_input["maximum"]
        or not isinstance(expression, dict)
        or set(expression) != {"divisor", "kind", "subtract"}
        or expression.get("kind") != "subtract_divide"
        or type(expression.get("subtract")) is not int
        or type(expression.get("divisor")) is not int
        or expression["divisor"] <= 0
        or not isinstance(modifiers, dict)
        or set(modifiers)
        != {"allowed_operations", "priority_order", "target_input"}
        or modifiers.get("allowed_operations") != ["add", "override"]
        or not isinstance(modifiers.get("priority_order"), list)
        or not modifiers["priority_order"]
        or len(set(modifiers["priority_order"])) != len(modifiers["priority_order"])
        or not all(
            isinstance(priority, str) and priority
            for priority in modifiers["priority_order"]
        )
        or modifiers.get("target_input") != formula_input.get("id")
        or not isinstance(result, dict)
        or set(result)
        != {"rounding", "rounding_evidence", "rounding_rule_id", "unit"}
        or result.get("rounding") != "floor"
        or not isinstance(source, dict)
        or set(source)
        != {"content_sha256", "evidence", "pages", "rule_id", "source"}
    ):
        raise _invalid_catalog()
    for mapping, keys in (
        (formula_input, ("id", "unit")),
        (result, ("unit", "rounding_rule_id", "rounding_evidence")),
        (source, ("rule_id", "content_sha256", "evidence")),
    ):
        for key in keys:
            _require_string(mapping, key)
    if not isinstance(source.get("source"), dict) or not isinstance(
        source.get("pages"), list
    ):
        raise _invalid_catalog()
    return dict(raw)


class FormulaCatalog:
    def __init__(self, path: Path | None = None) -> None:
        requested = path or default_formula_catalog_path()
        try:
            if requested.is_symlink() or not requested.is_file():
                raise _invalid_catalog()
            content = requested.read_bytes()
            loaded: object = json.loads(content.decode("utf-8"))
            library_manifest: object = json.loads(
                (requested.parent / "library.json").read_text(encoding="utf-8")
            )
        except FacadeError:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise _invalid_catalog() from error
        if not isinstance(loaded, dict) or not isinstance(library_manifest, dict):
            raise _invalid_catalog()
        if (
            library_manifest.get("format") != "dnd-rules-library-v1"
            or library_manifest.get("formulas_sha256") != _sha256(content)
            or not all(key in library_manifest for key in _LIBRARY_IDENTITY_KEYS)
        ):
            raise _invalid_catalog()
        library_identity = {
            key: library_manifest[key] for key in _LIBRARY_IDENTITY_KEYS
        }
        if _sha256(_canonical_json(library_identity)) != library_manifest.get(
            "library_sha256"
        ):
            raise _invalid_catalog()
        identity = {
            key: loaded.get(key)
            for key in ("format", "catalog_version", "formula_count", "formulas")
        }
        raw_formulas = loaded.get("formulas")
        if (
            set(loaded) != {*identity, "catalog_sha256"}
            or loaded.get("format") != "dnd-formula-catalog-v1"
            or not isinstance(loaded.get("catalog_version"), str)
            or not isinstance(raw_formulas, list)
            or loaded.get("formula_count") != len(raw_formulas)
            or loaded.get("catalog_sha256") != _sha256(_canonical_json(identity))
        ):
            raise _invalid_catalog()
        formulas = tuple(_validate_formula(raw) for raw in raw_formulas)
        by_id = {str(formula["id"]): formula for formula in formulas}
        if len(by_id) != len(formulas):
            raise _invalid_catalog()
        self._version = str(loaded["catalog_version"])
        self._sha256 = str(loaded["catalog_sha256"])
        self._formulas = by_id

    @property
    def version(self) -> str:
        return self._version

    @property
    def sha256(self) -> str:
        return self._sha256

    def calculate(
        self,
        *,
        formula_id: str,
        character_id: str,
        inputs: dict[str, object],
        modifiers: list[dict[str, object]],
    ) -> dict[str, object]:
        formula = self._formulas.get(formula_id)
        if formula is None:
            raise FacadeError("formula_not_found", "公式目录中没有匹配公式。")
        formula_input = formula["input"]
        expression = formula["expression"]
        modifier_policy = formula["modifiers"]
        result_policy = formula["result"]
        source = formula["source"]
        assert isinstance(formula_input, dict)
        assert isinstance(expression, dict)
        assert isinstance(modifier_policy, dict)
        assert isinstance(result_policy, dict)
        assert isinstance(source, dict)
        input_id = str(formula_input["id"])
        if set(inputs) != {input_id} or not isinstance(inputs[input_id], dict):
            raise FacadeError(
                "undefined_formula_input",
                "公式输入缺失或包含未定义字段，计算未写入。",
                {
                    "expected_inputs": [input_id],
                    "provided_inputs": sorted(inputs),
                },
            )
        supplied_input = inputs[input_id]
        assert isinstance(supplied_input, dict)
        if set(supplied_input) != {"unit", "value"}:
            raise FacadeError(
                "undefined_formula_input",
                "公式输入缺失或包含未定义字段，计算未写入。",
                {
                    "expected_inputs": [input_id],
                    "provided_inputs": sorted(inputs),
                },
            )
        if supplied_input.get("unit") != formula_input["unit"]:
            raise FacadeError(
                "formula_unit_conflict",
                "公式输入或修正项单位与目录声明不一致，计算未写入。",
                {
                    "field": input_id,
                    "expected_unit": formula_input["unit"],
                    "provided_unit": supplied_input.get("unit"),
                },
            )
        input_value = supplied_input.get("value")
        minimum = cast(int, formula_input["minimum"])
        maximum = cast(int, formula_input["maximum"])
        if (
            type(input_value) is not int
            or input_value < minimum
            or input_value > maximum
        ):
            raise FacadeError(
                "invalid_formula_input",
                "公式输入超出目录声明范围，计算未写入。",
                {
                    "field": input_id,
                    "minimum": minimum,
                    "maximum": maximum,
                    "value": input_value,
                },
            )
        validated_modifiers = self._validate_modifiers(
            modifiers,
            input_id=input_id,
            unit=str(formula_input["unit"]),
            policy=modifier_policy,
        )
        applied, suppressed = self._resolve_modifiers(
            validated_modifiers,
            priority_order=modifier_policy["priority_order"],
        )
        current_value = input_value
        steps: list[dict[str, object]] = [
            {
                "operation": "input",
                "input_id": input_id,
                "unit": formula_input["unit"],
                "value": current_value,
            }
        ]
        for modifier in applied:
            before = current_value
            if modifier["operation"] == "override":
                current_value = cast(int, modifier["value"])
            else:
                current_value += cast(int, modifier["value"])
            steps.append(
                {
                    "operation": "modifier",
                    "modifier": modifier,
                    "before": before,
                    "after": current_value,
                }
            )
        if current_value < minimum or current_value > maximum:
            raise FacadeError(
                "invalid_formula_input",
                "公式输入超出目录声明范围，计算未写入。",
                {
                    "field": input_id,
                    "minimum": minimum,
                    "maximum": maximum,
                    "value": current_value,
                },
            )
        after_subtract = current_value - int(expression["subtract"])
        steps.append(
            {
                "operation": "subtract",
                "before": current_value,
                "value": expression["subtract"],
                "after": after_subtract,
            }
        )
        quotient = Fraction(after_subtract, int(expression["divisor"]))
        serialized_quotient = {
            "numerator": quotient.numerator,
            "denominator": quotient.denominator,
        }
        steps.append(
            {
                "operation": "divide",
                "before": after_subtract,
                "divisor": expression["divisor"],
                "quotient": serialized_quotient,
            }
        )
        value = math.floor(quotient)
        steps.append(
            {
                "operation": "round",
                "method": result_policy["rounding"],
                "before": serialized_quotient,
                "after": value,
            }
        )
        return {
            "character_id": character_id,
            "formula": {
                "id": formula["id"],
                "version": formula["version"],
                "catalog_version": self.version,
                "catalog_sha256": self.sha256,
                "source_rule_id": source["rule_id"],
                "rounding_rule_id": result_policy["rounding_rule_id"],
                "source": source["source"],
                "pages": source["pages"],
            },
            "inputs": inputs,
            "modifiers": {
                "priority_order": modifier_policy["priority_order"],
                "applied": applied,
                "suppressed": suppressed,
            },
            "steps": steps,
            "result": {"unit": result_policy["unit"], "value": value},
        }

    @staticmethod
    def _validate_modifiers(
        modifiers: list[dict[str, object]],
        *,
        input_id: str,
        unit: str,
        policy: dict[str, object],
    ) -> list[dict[str, object]]:
        allowed = policy["allowed_operations"]
        priorities = policy["priority_order"]
        assert isinstance(allowed, list)
        assert isinstance(priorities, list)
        validated: list[dict[str, object]] = []
        seen_ids: set[str] = set()
        for modifier in modifiers:
            modifier_id = modifier.get("id") if isinstance(modifier, dict) else None
            if (
                not isinstance(modifier, dict)
                or set(modifier) != _MODIFIER_KEYS
                or not isinstance(modifier_id, str)
                or not modifier_id
                or modifier_id in seen_ids
                or modifier.get("operation") not in allowed
                or modifier.get("priority") not in priorities
                or not isinstance(modifier.get("source"), str)
                or not modifier["source"]
                or modifier.get("target") != input_id
                or type(modifier.get("value")) is not int
            ):
                raise FacadeError(
                    "invalid_formula_modifier",
                    "公式修正项不符合目录声明，计算未写入。",
                )
            if modifier.get("unit") != unit:
                raise FacadeError(
                    "formula_unit_conflict",
                    "公式输入或修正项单位与目录声明不一致，计算未写入。",
                    {
                        "field": modifier_id,
                        "expected_unit": unit,
                        "provided_unit": modifier.get("unit"),
                    },
                )
            seen_ids.add(modifier_id)
            validated.append(dict(modifier))
        return validated

    @staticmethod
    def _resolve_modifiers(
        modifiers: list[dict[str, object]],
        *,
        priority_order: object,
    ) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        assert isinstance(priority_order, list)
        rank = {priority: index for index, priority in enumerate(priority_order)}
        overrides = [item for item in modifiers if item["operation"] == "override"]
        additions = [item for item in modifiers if item["operation"] == "add"]
        applied: list[dict[str, object]] = []
        suppressed: list[dict[str, object]] = []
        if overrides:
            highest_rank = min(rank[str(item["priority"])] for item in overrides)
            highest = sorted(
                (
                    item
                    for item in overrides
                    if rank[str(item["priority"])] == highest_rank
                ),
                key=lambda item: str(item["id"]),
            )
            if len({cast(int, item["value"]) for item in highest}) > 1:
                raise FacadeError(
                    "formula_priority_conflict",
                    "同优先级公式修正项互相冲突，计算未写入。",
                    {
                        "priority": highest[0]["priority"],
                        "modifier_ids": [item["id"] for item in highest],
                        "values": [item["value"] for item in highest],
                    },
                )
            applied.append(highest[0])
            suppressed.extend(highest[1:])
            suppressed.extend(item for item in overrides if item not in highest)
        additions.sort(
            key=lambda item: (rank[str(item["priority"])], str(item["id"]))
        )
        applied.extend(additions)
        suppressed.sort(
            key=lambda item: (rank[str(item["priority"])], str(item["id"]))
        )
        return applied, suppressed
