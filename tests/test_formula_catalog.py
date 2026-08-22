from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from dnd_5e.errors import FacadeError
from dnd_5e.formulas import FormulaCatalog
from tests.facade_support import run_rules_builder
from tests.test_rules_build import (
    _rewrite_source_and_hash,
    _write_synthetic_baseline,
)


_PRIORITY_ORDER = [
    "approved_table_rule",
    "module_override",
    "specific_exception",
    "enabled_rule",
    "default_rule",
]


class FormulaCatalogBuildBoundaryTests(unittest.TestCase):
    def test_build_emits_a_traceable_versioned_formula_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            baseline, reference_root = _write_synthetic_baseline(root)
            fixture = json.loads(
                (reference_root / "synthetic.json").read_text(encoding="utf-8")
            )
            fixture["pages"][1]["blocks"].extend(
                [
                    {
                        "kind": "heading",
                        "level": 2,
                        "title": "属性调整值 Ability Modifier",
                        "category": "semantic_section",
                        "aliases": ["属性调整值", "Ability Modifier"],
                    },
                    {
                        "kind": "paragraph",
                        "text": "属性调整值等于属性值减去 10 后除以 2。",
                    },
                    {
                        "kind": "heading",
                        "level": 2,
                        "title": "向下取整 Round Down",
                        "category": "semantic_section",
                        "aliases": ["向下取整", "Round Down"],
                    },
                    {
                        "kind": "paragraph",
                        "text": "除法结果必须舍去所有小数。",
                    },
                ]
            )
            _rewrite_source_and_hash(baseline, reference_root, fixture)
            baseline_payload = json.loads(baseline.read_text(encoding="utf-8"))
            baseline_payload["formula_catalog"] = {
                "version": "synthetic-formulas-v1",
                "formulas": [
                    {
                        "id": "ability-modifier",
                        "version": "1",
                        "title": "属性调整值",
                        "activation_condition": "输入是 1 至 30 的已确认属性值。",
                        "input": {
                            "id": "ability_score",
                            "unit": "ability_score",
                            "minimum": 1,
                            "maximum": 30,
                        },
                        "result_unit": "ability_modifier",
                        "subtract": 10,
                        "divisor": 2,
                        "rounding": "floor",
                        "modifier_operations": ["add", "override"],
                        "priority_order": _PRIORITY_ORDER,
                        "source_rule_alias": "属性调整值",
                        "source_evidence": "属性值减去 10 后除以 2",
                        "rounding_rule_alias": "向下取整",
                        "rounding_evidence": "舍去所有小数",
                    }
                ],
            }
            baseline.write_text(
                json.dumps(baseline_payload, ensure_ascii=False, sort_keys=True),
                encoding="utf-8",
            )
            output = root / "library"

            result = run_rules_builder(
                "build",
                "--baseline",
                str(baseline),
                "--reference-root",
                str(reference_root),
                "--output",
                str(output),
            )
            formulas_path = output / "formulas.json"
            formulas = (
                json.loads(formulas_path.read_text(encoding="utf-8"))
                if formulas_path.is_file()
                else None
            )
            manifest = json.loads((output / "library.json").read_text(encoding="utf-8"))

            self.assertEqual(0, result.returncode, msg=result.stderr)
            assert isinstance(formulas, dict)
            formula = formulas["formulas"][0]
            self.assertEqual("dnd-formula-catalog-v1", formulas["format"])
            self.assertEqual("synthetic-formulas-v1", formulas["catalog_version"])
            self.assertEqual(1, formulas["formula_count"])
            self.assertEqual(
                hashlib.sha256(formulas_path.read_bytes()).hexdigest(),
                manifest["formulas_sha256"],
            )
            self.assertEqual("ability-modifier", formula["id"])
            self.assertEqual("1", formula["version"])
            self.assertEqual(
                "输入是 1 至 30 的已确认属性值。",
                formula["activation_condition"],
            )
            self.assertEqual(
                {
                    "id": "ability_score",
                    "maximum": 30,
                    "minimum": 1,
                    "type": "integer",
                    "unit": "ability_score",
                },
                formula["input"],
            )
            self.assertEqual(
                {"divisor": 2, "kind": "subtract_divide", "subtract": 10},
                formula["expression"],
            )
            self.assertEqual("ability_modifier", formula["result"]["unit"])
            self.assertEqual("floor", formula["result"]["rounding"])
            self.assertEqual(_PRIORITY_ORDER, formula["modifiers"]["priority_order"])
            self.assertEqual(
                ["add", "override"], formula["modifiers"]["allowed_operations"]
            )
            self.assertEqual("syn", formula["source"]["source"]["id"])
            self.assertEqual([{"label": "2", "pdf_page": 2}], formula["source"]["pages"])
            self.assertEqual(
                "属性值减去 10 后除以 2", formula["source"]["evidence"]
            )
            self.assertEqual(
                "舍去所有小数", formula["result"]["rounding_evidence"]
            )

    def test_runtime_rejects_a_self_consistent_catalog_detached_from_library(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        production_library = repository_root / "build" / "rules-library"
        with tempfile.TemporaryDirectory() as temporary_directory:
            library = Path(temporary_directory) / "library"
            library.mkdir()
            shutil.copy(production_library / "library.json", library / "library.json")
            shutil.copy(production_library / "formulas.json", library / "formulas.json")
            formulas_path = library / "formulas.json"
            formulas = json.loads(formulas_path.read_text(encoding="utf-8"))
            formulas["formulas"][0]["result"]["unit"] = "tampered_unit"
            identity = {
                key: formulas[key]
                for key in (
                    "format",
                    "catalog_version",
                    "formula_count",
                    "formulas",
                )
            }
            formulas["catalog_sha256"] = hashlib.sha256(
                json.dumps(
                    identity,
                    ensure_ascii=False,
                    allow_nan=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode("utf-8")
            ).hexdigest()
            formulas_path.write_text(
                json.dumps(formulas, ensure_ascii=False, indent=2, sort_keys=True)
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaises(FacadeError) as raised:
                FormulaCatalog(formulas_path)

            self.assertEqual("invalid_formula_catalog", raised.exception.code)


if __name__ == "__main__":
    unittest.main()
