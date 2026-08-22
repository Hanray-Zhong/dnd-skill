from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from tests.facade_support import run_facade
from tests.rules_support import build_synthetic_library, run_synthetic_library_build
from tests.test_rules_build import _synthetic_fixture


def _verified_rule_exception() -> dict[str, str]:
    return {
        "id": "syn-starlight-overrides-general",
        "specific_rule_alias": "星光术",
        "general_rule_alias": "自有规则",
        "scope": "星光术对有遮蔽目标的影响",
        "general_value": "受到星光术影响",
        "specific_value": "不受影响",
        "general_evidence": "一般规则：有遮蔽的目标会受到星光术影响。",
        "specific_evidence": "跨页部分保留例外：有遮蔽的目标不受影响。",
        "review_status": "verified",
        "review_evidence": "Issue #5 合成验收",
    }


class RulesQueryFacadeTests(unittest.TestCase):
    def test_alias_query_loads_only_the_matching_generated_asset(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            fixture = _synthetic_fixture()
            fixture["pages"][0]["blocks"][2]["references"] = []
            library = build_synthetic_library(root, fixture=fixture)
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
            library = build_synthetic_library(root)
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

    def test_general_default_rule_is_returned_without_an_exception(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            library = build_synthetic_library(root)
            index = json.loads((library / "index.json").read_text(encoding="utf-8"))
            general_rule_id = next(
                item["id"]
                for item in index["items"]
                if item["category"] == "semantic_section"
            )

            result = run_facade(
                "rules-query",
                "--library",
                str(library),
                "--id",
                general_rule_id,
            )
            payload = json.loads(result.stdout) if result.stdout else None

            self.assertEqual(0, result.returncode, msg=result.stderr)
            assert isinstance(payload, dict)
            self.assertEqual([general_rule_id], [rule["id"] for rule in payload["rules"]])
            self.assertEqual("default", payload["rules"][0]["rule_status"])
            self.assertNotIn("general_rules", payload)
            self.assertNotIn("resolution", payload)

    def test_representative_entities_are_queryable_by_name_and_stable_id(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            fixture = _synthetic_fixture()
            fixture["pages"][1]["blocks"].extend(
                [
                    {
                        "kind": "heading",
                        "level": 2,
                        "title": "暮影兽 Gloambeast",
                        "category": "monster",
                        "aliases": ["暮影兽", "Gloambeast"],
                    },
                    {"kind": "paragraph", "text": "暮影兽具有可追溯的自有资料板。"},
                    {
                        "kind": "heading",
                        "level": 2,
                        "title": "星辉棱镜 Starlight Prism",
                        "category": "magic_item",
                        "aliases": ["星辉棱镜", "Starlight Prism"],
                    },
                    {"kind": "paragraph", "text": "星辉棱镜是一件自有测试物品。"},
                ]
            )
            library = build_synthetic_library(root, fixture=fixture)

            for alias, category in (
                ("星光术", "spell"),
                ("目眩", "condition"),
                ("暮影兽", "monster"),
                ("星辉棱镜", "magic_item"),
            ):
                with self.subTest(alias=alias):
                    by_name = run_facade(
                        "rules-query",
                        "--library",
                        str(library),
                        "--alias",
                        alias,
                    )
                    self.assertEqual(0, by_name.returncode, msg=by_name.stderr)
                    name_payload = json.loads(by_name.stdout)
                    entity = name_payload["rules"][0]
                    self.assertEqual(category, entity["category"])
                    self.assertEqual("syn", entity["source"]["id"])
                    self.assertIn("cross_references", entity)

                    by_id = run_facade(
                        "rules-query",
                        "--library",
                        str(library),
                        "--id",
                        entity["id"],
                    )
                    self.assertEqual(0, by_id.returncode, msg=by_id.stderr)
                    id_payload = json.loads(by_id.stdout)
                    self.assertEqual(entity, id_payload["rules"][0])

    def test_specific_entity_exception_overrides_its_general_rule(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            fixture = _synthetic_fixture()
            fixture["pages"][0]["blocks"][1]["text"] = (
                "一般规则：有遮蔽的目标会受到星光术影响。"
            )
            fixture["pages"][1]["blocks"][0]["text"] = (
                "跨页部分保留例外：有遮蔽的目标不受影响。"
            )
            fixture["pages"][0]["blocks"][2]["references"].append("自有规则")
            exception = _verified_rule_exception()
            library = build_synthetic_library(
                root,
                fixture=fixture,
                rule_exceptions=[exception],
            )
            index = json.loads((library / "index.json").read_text(encoding="utf-8"))
            general_rule = next(
                item
                for item in index["items"]
                if item["category"] == "semantic_section"
            )
            entity = next(
                item for item in index["items"] if item["category"] == "spell"
            )
            self.assertIn(general_rule["id"], entity["cross_references"])
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

            result = run_facade(
                "rules-query",
                "--library",
                str(library),
                "--alias",
                "星光术",
                "--general-rule-id",
                general_rule["id"],
            )
            payload = json.loads(result.stdout) if result.stdout else None
            rules = payload.get("rules", []) if isinstance(payload, dict) else []
            general_rules = (
                payload.get("general_rules", []) if isinstance(payload, dict) else []
            )

            self.assertEqual(0, result.returncode, msg=result.stderr)
            assert isinstance(payload, dict)
            self.assertEqual(entity["id"], rules[0]["id"])
            self.assertEqual("spell", rules[0]["category"])
            self.assertEqual("syn", rules[0]["source"]["id"])
            self.assertIn(general_rule["id"], rules[0]["cross_references"])
            self.assertEqual([general_rule["id"]], [rule["id"] for rule in general_rules])
            self.assertEqual(
                {
                    "decision": "specific_entity_overrides_general_rule",
                    "reason": "三宝书具体实体说明优先于一般默认规则。",
                    "applied_rule_id": entity["id"],
                    "overridden_rule_ids": [general_rule["id"]],
                    "exception_id": exception["id"],
                    "conflict": conflict,
                    "precedence": [
                        {
                            "rank": 3,
                            "kind": "specific_entity",
                            "rule_id": entity["id"],
                        },
                        {
                            "rank": 5,
                            "kind": "general_default",
                            "rule_id": general_rule["id"],
                        },
                    ],
                },
                payload["resolution"],
            )

    def test_cross_reference_alone_does_not_authorize_an_override(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            fixture = _synthetic_fixture()
            fixture["pages"][0]["blocks"][2]["references"].append("自有规则")
            library = build_synthetic_library(root, fixture=fixture)
            index = json.loads((library / "index.json").read_text(encoding="utf-8"))
            general_rule_id = next(
                item["id"]
                for item in index["items"]
                if item["category"] == "semantic_section"
            )

            result = run_facade(
                "rules-query",
                "--library",
                str(library),
                "--alias",
                "星光术",
                "--general-rule-id",
                general_rule_id,
            )
            error = json.loads(result.stderr) if result.stderr else None

            self.assertEqual(2, result.returncode)
            assert isinstance(error, dict)
            self.assertEqual("rule_exception_not_found", error["error"]["code"])

    def test_specific_entity_resolution_rejects_frontmatter_as_conflict_evidence(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            fixture = _synthetic_fixture()
            fixture["pages"][0]["blocks"][1]["text"] = (
                "一般规则：有遮蔽的目标会受到星光术影响。"
            )
            fixture["pages"][1]["blocks"][0]["text"] = (
                "跨页部分保留例外：有遮蔽的目标不受影响。"
            )
            fixture["pages"][0]["blocks"][2]["references"].append("自有规则")
            exception = _verified_rule_exception()
            exception["general_value"] = "default"
            exception["specific_value"] = "spell"
            exception["general_evidence"] = '"rule_status":"default"'
            exception["specific_evidence"] = '"category":"spell"'

            library, result = run_synthetic_library_build(
                root,
                fixture=fixture,
                rule_exceptions=[exception],
            )
            error = json.loads(result.stderr) if result.stderr else None

            self.assertEqual(2, result.returncode)
            assert isinstance(error, dict)
            self.assertEqual("unverified_rule_exception", error["error"]["code"])
            self.assertFalse(library.exists())

    def test_specific_entity_resolution_rejects_a_missing_rule_reference(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            fixture = _synthetic_fixture()
            fixture["pages"][0]["blocks"][1]["text"] = (
                "一般规则：有遮蔽的目标会受到星光术影响。"
            )
            fixture["pages"][1]["blocks"][0]["text"] = (
                "跨页部分保留例外：有遮蔽的目标不受影响。"
            )

            library, result = run_synthetic_library_build(
                root,
                fixture=fixture,
                rule_exceptions=[_verified_rule_exception()],
            )
            error = json.loads(result.stderr) if result.stderr else None

            self.assertEqual(2, result.returncode)
            assert isinstance(error, dict)
            self.assertEqual("broken_rule_exception_reference", error["error"]["code"])
            self.assertFalse(library.exists())


if __name__ == "__main__":
    unittest.main()
