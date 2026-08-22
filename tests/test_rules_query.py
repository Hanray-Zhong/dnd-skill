from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from tests.facade_support import run_facade, run_rules_builder
from tests.test_rules_build import (
    _rewrite_source_and_hash,
    _synthetic_fixture,
    _write_synthetic_baseline,
)


class RulesQueryFacadeTests(unittest.TestCase):
    def test_alias_query_loads_only_the_matching_generated_asset(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            baseline, reference_root = _write_synthetic_baseline(root)
            fixture = _synthetic_fixture()
            fixture["pages"][0]["blocks"][2]["references"] = []
            _rewrite_source_and_hash(baseline, reference_root, fixture)
            library = root / "library"
            build = run_rules_builder(
                "build",
                "--baseline",
                str(baseline),
                "--reference-root",
                str(reference_root),
                "--output",
                str(library),
            )
            self.assertEqual(0, build.returncode, msg=build.stderr)
            index = json.loads((library / "index.json").read_text(encoding="utf-8"))
            unrelated = next(
                item for item in index["items"] if item["category"] == "condition"
            )
            (library / unrelated["path"]).write_text(
                "这个无关实体已故意损坏。\n",
                encoding="utf-8",
            )

            result = run_facade(
                "rules-query",
                "--library",
                str(library),
                "--alias",
                "星光术",
            )
            payload = json.loads(result.stdout) if result.stdout else None
            rules = payload.get("rules", []) if isinstance(payload, dict) else []

            self.assertEqual(
                {
                    "returncode": 0,
                    "ok": True,
                    "query": {"kind": "alias", "value": "星光术"},
                    "library_version": "synthetic-v1",
                    "rule_count": 1,
                    "title": "星光术 Starlight",
                    "category": "spell",
                    "aliases": ["星光术 Starlight", "星光术", "Starlight"],
                    "activation_condition": "三宝书规则基线适用且没有更具体规则覆盖。",
                    "rule_status": "default",
                    "source_id": "syn",
                    "source_version": "1",
                    "source_pages": [
                        {"pdf_page": 1, "label": "1"},
                        {"pdf_page": 2, "label": "2"},
                    ],
                    "cross_reference_count": 1,
                    "referenced_by_count": 0,
                    "contains_table": True,
                    "contains_cross_page_exception": True,
                    "has_traceback": False,
                },
                {
                    "returncode": result.returncode,
                    "ok": payload.get("ok") if isinstance(payload, dict) else None,
                    "query": payload.get("query") if isinstance(payload, dict) else None,
                    "library_version": (
                        payload.get("library", {}).get("version")
                        if isinstance(payload, dict)
                        and isinstance(payload.get("library"), dict)
                        else None
                    ),
                    "rule_count": len(rules),
                    "title": rules[0].get("title") if rules else None,
                    "category": rules[0].get("category") if rules else None,
                    "aliases": rules[0].get("aliases") if rules else None,
                    "activation_condition": (
                        rules[0].get("activation_condition") if rules else None
                    ),
                    "rule_status": rules[0].get("rule_status") if rules else None,
                    "source_id": (
                        rules[0].get("source", {}).get("id")
                        if rules and isinstance(rules[0].get("source"), dict)
                        else None
                    ),
                    "source_version": (
                        rules[0].get("source", {}).get("version")
                        if rules and isinstance(rules[0].get("source"), dict)
                        else None
                    ),
                    "source_pages": rules[0].get("pages") if rules else None,
                    "cross_reference_count": (
                        len(rules[0].get("cross_references", [])) if rules else 0
                    ),
                    "referenced_by_count": (
                        len(rules[0].get("referenced_by", [])) if rules else 0
                    ),
                    "contains_table": (
                        "| 等级 | 范围 |" in rules[0].get("conclusion_markdown", "")
                        if rules
                        else False
                    ),
                    "contains_cross_page_exception": (
                        "跨页部分保留例外" in rules[0].get("conclusion_markdown", "")
                        if rules
                        else False
                    ),
                    "has_traceback": "Traceback" in result.stderr,
                },
                msg=result.stderr,
            )

    def test_stable_id_and_topic_queries_have_bounded_results(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            baseline, reference_root = _write_synthetic_baseline(root)
            library = root / "library"
            build = run_rules_builder(
                "build",
                "--baseline",
                str(baseline),
                "--reference-root",
                str(reference_root),
                "--output",
                str(library),
            )
            self.assertEqual(0, build.returncode, msg=build.stderr)
            index = json.loads((library / "index.json").read_text(encoding="utf-8"))
            spell_id = next(
                item["id"] for item in index["items"] if item["category"] == "spell"
            )

            by_id = run_facade(
                "rules-query",
                "--library",
                str(library),
                "--id",
                spell_id,
            )
            by_topic = run_facade(
                "rules-query",
                "--library",
                str(library),
                "--topic",
                "自有规则",
                "--limit",
                "2",
            )
            missing = run_facade(
                "rules-query",
                "--library",
                str(library),
                "--alias",
                "不存在的规则",
            )
            id_payload = json.loads(by_id.stdout) if by_id.stdout else None
            topic_payload = json.loads(by_topic.stdout) if by_topic.stdout else None
            missing_payload = json.loads(missing.stderr) if missing.stderr else None

            self.assertEqual(0, by_id.returncode, msg=by_id.stderr)
            assert isinstance(id_payload, dict)
            assert isinstance(topic_payload, dict)
            assert isinstance(missing_payload, dict)
            self.assertEqual({"kind": "id", "value": spell_id}, id_payload["query"])
            self.assertEqual([spell_id], [rule["id"] for rule in id_payload["rules"]])
            self.assertEqual(0, by_topic.returncode, msg=by_topic.stderr)
            self.assertEqual({"kind": "topic", "value": "自有规则"}, topic_payload["query"])
            self.assertEqual(2, len(topic_payload["rules"]))
            self.assertEqual(2, missing.returncode)
            self.assertEqual("rule_not_found", missing_payload["error"]["code"])


if __name__ == "__main__":
    unittest.main()
