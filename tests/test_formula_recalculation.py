from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
import uuid

from tests.facade_support import run_facade


def _session_zero_configuration() -> dict[str, object]:
    return {
        "players": [
            {
                "player_id": "alice",
                "display_name": "艾莉丝",
                "character_ids": ["aria"],
                "confirmed": True,
                "preferences": {},
                "roll_policy": "player_rolls",
                "absence_policies": {"aria": {"mode": "narrative_exit"}},
                "pvp_preferences": {"violence": "forbid"},
            }
        ],
        "safety": {"boundaries": [], "confirmed_by": ["alice"]},
        "difficulty": "standard",
        "advancement": "xp",
        "private_roll_policy": "dice_engine",
        "pvp_categories": ["violence"],
    }


def _create_ready_campaign(workspace: Path) -> None:
    created = run_facade("create", str(workspace))
    if created.returncode != 0:
        raise AssertionError(created.stderr)
    session_zero = run_facade(
        "session-zero",
        str(workspace),
        "--expected-revision",
        "1",
        "--idempotency-key",
        "formula-session-zero",
        "--configuration",
        json.dumps(_session_zero_configuration(), ensure_ascii=False),
    )
    if session_zero.returncode != 0:
        raise AssertionError(session_zero.stderr)


class FormulaRecalculationFacadeTests(unittest.TestCase):
    def test_recalculate_is_deterministic_retryable_and_restored_on_open(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "campaign"
            created = run_facade("create", str(workspace))
            self.assertEqual(0, created.returncode, msg=created.stderr)
            session_zero = run_facade(
                "session-zero",
                str(workspace),
                "--expected-revision",
                "1",
                "--idempotency-key",
                "formula-session-zero",
                "--configuration",
                json.dumps(_session_zero_configuration(), ensure_ascii=False),
            )
            self.assertEqual(0, session_zero.returncode, msg=session_zero.stderr)
            inputs = {
                "ability_score": {"value": 15, "unit": "ability_score"}
            }
            modifiers: list[dict[str, object]] = []
            first_request = (
                "recalculate",
                str(workspace),
                "--expected-revision",
                "2",
                "--idempotency-key",
                "aria-strength-modifier-v1",
                "--character",
                "aria",
                "--formula",
                "ability-modifier",
                "--inputs",
                json.dumps(inputs),
                "--modifiers",
                json.dumps(modifiers),
            )

            first = run_facade(*first_request)
            first_payload = json.loads(first.stdout) if first.stdout else None
            retry = run_facade(*first_request)
            retry_payload = json.loads(retry.stdout) if retry.stdout else None
            opened = run_facade("open", str(workspace))
            opened_payload = json.loads(opened.stdout) if opened.stdout else None
            after_open = run_facade(
                "recalculate",
                str(workspace),
                "--expected-revision",
                "3",
                "--idempotency-key",
                "aria-strength-modifier-v2",
                "--character",
                "aria",
                "--formula",
                "ability-modifier",
                "--inputs",
                json.dumps(inputs),
                "--modifiers",
                json.dumps(modifiers),
            )
            after_open_payload = (
                json.loads(after_open.stdout) if after_open.stdout else None
            )

            self.assertEqual(0, first.returncode, msg=first.stderr)
            self.assertEqual(0, retry.returncode, msg=retry.stderr)
            self.assertEqual(0, opened.returncode, msg=opened.stderr)
            self.assertEqual(0, after_open.returncode, msg=after_open.stderr)
            assert isinstance(first_payload, dict)
            assert isinstance(retry_payload, dict)
            assert isinstance(opened_payload, dict)
            assert isinstance(after_open_payload, dict)
            calculation = first_payload["calculation"]
            self.assertEqual("recalculate", first_payload["operation"])
            self.assertEqual(3, first_payload["revision"])
            self.assertEqual("aria", calculation["character_id"])
            self.assertEqual(
                {
                    "id": "ability-modifier",
                    "version": "1",
                    "catalog_version": "core-cn-2014-formulas-v1",
                },
                {
                    key: calculation["formula"][key]
                    for key in ("id", "version", "catalog_version")
                },
            )
            self.assertEqual(
                "phb-cn-1.72-semantic-section-c9a5509d0dc2",
                calculation["formula"]["source_rule_id"],
            )
            self.assertEqual(
                {"unit": "ability_modifier", "value": 2},
                calculation["result"],
            )
            self.assertEqual(inputs, calculation["inputs"])
            self.assertEqual([], calculation["modifiers"]["applied"])
            self.assertEqual([], calculation["modifiers"]["suppressed"])
            self.assertEqual(
                [
                    "approved_table_rule",
                    "module_override",
                    "specific_exception",
                    "enabled_rule",
                    "default_rule",
                ],
                calculation["modifiers"]["priority_order"],
            )
            self.assertEqual(
                ["input", "subtract", "divide", "round"],
                [step["operation"] for step in calculation["steps"]],
            )
            self.assertEqual("floor", calculation["steps"][-1]["method"])
            self.assertEqual(
                "三宝书规则基线适用且输入为 1 至 30 的属性值。",
                calculation["formula"]["activation_condition"],
            )
            first_transaction = first_payload["transaction"]
            self.assertEqual(False, first_transaction["replayed"])
            self.assertEqual("dnd-5e-character", first_transaction["source"])
            self.assertEqual("dm", first_transaction["audience_id"])
            self.assertEqual(
                str(uuid.UUID(first_transaction["event_id"])),
                first_transaction["event_id"],
            )
            self.assertEqual(3, retry_payload["revision"])
            self.assertEqual(True, retry_payload["transaction"]["replayed"])
            self.assertEqual(
                first_transaction["event_id"],
                retry_payload["transaction"]["event_id"],
            )
            self.assertEqual(
                calculation,
                opened_payload["derived_values"]["aria"]["ability-modifier"],
            )
            self.assertEqual(3, opened_payload["revision"])
            self.assertEqual(4, after_open_payload["revision"])
            self.assertEqual(
                calculation["result"], after_open_payload["calculation"]["result"]
            )
            self.assertEqual(
                calculation["steps"], after_open_payload["calculation"]["steps"]
            )

    def test_unit_conflict_is_explained_without_writing_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "campaign"
            _create_ready_campaign(workspace)

            result = run_facade(
                "recalculate",
                str(workspace),
                "--expected-revision",
                "2",
                "--idempotency-key",
                "wrong-unit",
                "--character",
                "aria",
                "--formula",
                "ability-modifier",
                "--inputs",
                json.dumps(
                    {"ability_score": {"value": 15, "unit": "feet"}}
                ),
                "--modifiers",
                "[]",
            )
            error = json.loads(result.stderr) if result.stderr else None
            opened = run_facade("open", str(workspace))
            opened_payload = json.loads(opened.stdout) if opened.stdout else None

            self.assertEqual(2, result.returncode)
            self.assertEqual("", result.stdout)
            self.assertEqual(
                {
                    "ok": False,
                    "error": {
                        "code": "formula_unit_conflict",
                        "message": "公式输入或修正项单位与目录声明不一致，计算未写入。",
                        "details": {
                            "field": "ability_score",
                            "expected_unit": "ability_score",
                            "provided_unit": "feet",
                        },
                    },
                },
                error,
            )
            self.assertEqual(0, opened.returncode, msg=opened.stderr)
            assert isinstance(opened_payload, dict)
            self.assertEqual(2, opened_payload["revision"])
            self.assertNotIn("derived_values", opened_payload)

    def test_undefined_input_is_explained_without_writing_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "campaign"
            _create_ready_campaign(workspace)

            result = run_facade(
                "recalculate",
                str(workspace),
                "--expected-revision",
                "2",
                "--idempotency-key",
                "missing-input",
                "--character",
                "aria",
                "--formula",
                "ability-modifier",
                "--inputs",
                "{}",
                "--modifiers",
                "[]",
            )
            error = json.loads(result.stderr) if result.stderr else None
            opened = run_facade("open", str(workspace))
            opened_payload = json.loads(opened.stdout) if opened.stdout else None

            self.assertEqual(2, result.returncode)
            self.assertEqual(
                {
                    "ok": False,
                    "error": {
                        "code": "undefined_formula_input",
                        "message": "公式输入缺失或包含未定义字段，计算未写入。",
                        "details": {
                            "expected_inputs": ["ability_score"],
                            "provided_inputs": [],
                        },
                    },
                },
                error,
            )
            self.assertEqual(0, opened.returncode, msg=opened.stderr)
            assert isinstance(opened_payload, dict)
            self.assertEqual(2, opened_payload["revision"])
            self.assertNotIn("derived_values", opened_payload)

    def test_same_priority_override_conflict_never_writes_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "campaign"
            _create_ready_campaign(workspace)
            modifiers = [
                {
                    "id": "higher-module-override",
                    "operation": "override",
                    "priority": "module_override",
                    "source": "module:higher",
                    "target": "ability_score",
                    "unit": "ability_score",
                    "value": 18,
                },
                {
                    "id": "enabled-a",
                    "operation": "override",
                    "priority": "enabled_rule",
                    "source": "rule:a",
                    "target": "ability_score",
                    "unit": "ability_score",
                    "value": 16,
                },
                {
                    "id": "enabled-b",
                    "operation": "override",
                    "priority": "enabled_rule",
                    "source": "rule:b",
                    "target": "ability_score",
                    "unit": "ability_score",
                    "value": 18,
                },
            ]

            result = run_facade(
                "recalculate",
                str(workspace),
                "--expected-revision",
                "2",
                "--idempotency-key",
                "same-priority-conflict",
                "--character",
                "aria",
                "--formula",
                "ability-modifier",
                "--inputs",
                json.dumps(
                    {
                        "ability_score": {
                            "value": 15,
                            "unit": "ability_score",
                        }
                    }
                ),
                "--modifiers",
                json.dumps(modifiers),
            )
            error = json.loads(result.stderr) if result.stderr else None
            opened = run_facade("open", str(workspace))
            opened_payload = json.loads(opened.stdout) if opened.stdout else None

            self.assertEqual(2, result.returncode)
            self.assertEqual(
                {
                    "ok": False,
                    "error": {
                        "code": "formula_priority_conflict",
                        "message": "同优先级公式修正项互相冲突，计算未写入。",
                        "details": {
                            "priority": "enabled_rule",
                            "modifier_ids": ["enabled-a", "enabled-b"],
                            "values": [16, 18],
                        },
                    },
                },
                error,
            )
            self.assertEqual(0, opened.returncode, msg=opened.stderr)
            assert isinstance(opened_payload, dict)
            self.assertEqual(2, opened_payload["revision"])
            self.assertNotIn("derived_values", opened_payload)

    def test_untrusted_modifier_source_never_writes_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "campaign"
            _create_ready_campaign(workspace)
            modifier = {
                "id": "untrusted-bonus",
                "operation": "add",
                "priority": "approved_table_rule",
                "source": "character-build:test-fixture",
                "target": "ability_score",
                "unit": "ability_score",
                "value": 2,
            }

            result = run_facade(
                "recalculate",
                str(workspace),
                "--expected-revision",
                "2",
                "--idempotency-key",
                "untrusted-modifier-source",
                "--character",
                "aria",
                "--formula",
                "ability-modifier",
                "--inputs",
                json.dumps(
                    {
                        "ability_score": {
                            "value": 15,
                            "unit": "ability_score",
                        }
                    }
                ),
                "--modifiers",
                json.dumps([modifier]),
            )
            error = json.loads(result.stderr) if result.stderr else None
            opened = run_facade("open", str(workspace))
            opened_payload = json.loads(opened.stdout) if opened.stdout else None

            self.assertEqual(2, result.returncode)
            self.assertEqual(
                {
                    "ok": False,
                    "error": {
                        "code": "formula_modifier_unauthorized",
                        "message": "公式修正项缺少稳定且已生效的权威来源，计算未写入。",
                        "details": {
                            "modifier_ids": ["untrusted-bonus"],
                            "sources": ["character-build:test-fixture"],
                        },
                    },
                },
                error,
            )
            self.assertEqual(0, opened.returncode, msg=opened.stderr)
            assert isinstance(opened_payload, dict)
            self.assertEqual(2, opened_payload["revision"])
            self.assertNotIn("derived_values", opened_payload)


if __name__ == "__main__":
    unittest.main()
