from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from dnd_5e.rules.library import RulesLibrary
from tests.facade_support import run_rules_builder
from tests.test_rules_build import (
    _rewrite_source_and_hash,
    _synthetic_fixture,
    _write_synthetic_baseline,
)


class TableEntityBuildTests(unittest.TestCase):
    def test_named_table_rows_become_queryable_leaf_entities(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            baseline_path, reference_root = _write_synthetic_baseline(root)
            fixture = _synthetic_fixture()
            table = fixture["pages"][0]["blocks"][4]
            table["headers"] = ["名称", "价格", "重量"]
            table["rows"] = [
                ["特殊物品 Special Items", "", ""],
                ["星刃 Starblade", "15 gp", "1d8 光耀"],
                ["玻璃匠工具 glassblower’s", "tools 30 gp", "5 磅"],
                ["水袋 waterskin", "2 sp 5", "磅（盛满）"],
            ]
            _rewrite_source_and_hash(baseline_path, reference_root, fixture)
            baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
            baseline["sources"][0]["table_entities"] = [
                {
                    "parent_title": "星光术 Starlight",
                    "category": "equipment",
                    "title_column": 0,
                    "minimum_populated_cells": 3,
                }
            ]
            baseline_path.write_text(
                json.dumps(baseline, ensure_ascii=False, sort_keys=True),
                encoding="utf-8",
            )
            output = root / "library"

            result = run_rules_builder(
                "build",
                "--baseline",
                str(baseline_path),
                "--reference-root",
                str(reference_root),
                "--output",
                str(output),
            )

            self.assertEqual(0, result.returncode, msg=result.stderr)
            rules = RulesLibrary(output).query(kind="topic", value="星刃")
            self.assertEqual(1, len(rules))
            self.assertEqual("equipment", rules[0]["category"])
            self.assertEqual([{"label": "1", "pdf_page": 1}], rules[0]["pages"])
            chapter_path = rules[0]["chapter_path"]
            if not isinstance(chapter_path, list):
                self.fail("表格实体查询结果缺少章节路径")
            self.assertNotIn("特殊物品 Special Items", chapter_path)
            conclusion = rules[0]["conclusion_markdown"]
            references = rules[0]["cross_references"]
            if not isinstance(conclusion, str) or not isinstance(references, list):
                self.fail("表格实体查询结果缺少正文或交叉引用")
            self.assertIn("| 星刃 Starblade | 15 gp | 1d8 光耀 |", conclusion)
            self.assertEqual(1, len(references))
            tools = RulesLibrary(output).query(
                kind="alias",
                value="glassblower’s tools",
            )
            self.assertEqual("玻璃匠工具 glassblower’s tools", tools[0]["title"])
            waterskin = RulesLibrary(output).query(kind="alias", value="waterskin")
            waterskin_markdown = waterskin[0]["conclusion_markdown"]
            if not isinstance(waterskin_markdown, str):
                self.fail("水袋表格实体缺少正文")
            self.assertIn("| 水袋 waterskin | 2 sp | 5 磅（盛满） |", waterskin_markdown)


if __name__ == "__main__":
    unittest.main()
