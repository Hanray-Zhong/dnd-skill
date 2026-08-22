from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from typing import Any

from tests.facade_support import run_rules_builder


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _directory_sha256(directory: Path) -> str:
    hasher = hashlib.sha256()
    for path in sorted(item for item in directory.rglob("*") if item.is_file()):
        relative_path = path.relative_to(directory).as_posix()
        content = path.read_bytes()
        hasher.update(relative_path.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(content)
    return hasher.hexdigest()


def _synthetic_fixture() -> dict[str, Any]:
    return {
        "format": "dnd-rules-extraction-fixture-v1",
        "pages": [
            {
                "number": 1,
                "label": "1",
                "blocks": [
                    {
                        "kind": "heading",
                        "level": 1,
                        "title": "第一章：自有规则",
                        "category": "semantic_section",
                        "aliases": ["自有规则"],
                    },
                    {
                        "kind": "paragraph",
                        "text": "本章内容由测试作者原创，并明确说明适用范围。",
                    },
                    {
                        "kind": "heading",
                        "level": 2,
                        "title": "星光术 Starlight",
                        "category": "spell",
                        "aliases": ["星光术", "Starlight"],
                        "references": ["目眩 Dazzled"],
                    },
                    {
                        "kind": "paragraph",
                        "text": "当目标位于星光中时，它进入目眩状态；本主题在下一页继续。",
                    },
                    {
                        "kind": "table",
                        "headers": ["等级", "范围"],
                        "rows": [["1", "10 尺"], ["2", "20 尺"]],
                    },
                    {
                        "kind": "sidebar",
                        "title": "限定词",
                        "text": "只有明确处于星光中的目标才适用。",
                    },
                ],
            },
            {
                "number": 2,
                "label": "2",
                "blocks": [
                    {
                        "kind": "paragraph",
                        "text": "跨页部分保留例外：有遮蔽的目标不受影响。",
                    },
                    {
                        "kind": "footnote",
                        "label": "fixture-note",
                        "text": "该脚注同样是自有测试文本。",
                    },
                    {
                        "kind": "heading",
                        "level": 2,
                        "title": "目眩 Dazzled",
                        "category": "condition",
                        "aliases": ["目眩", "Dazzled"],
                    },
                    {
                        "kind": "paragraph",
                        "text": "目眩生物无法从强光中获得额外信息。",
                    },
                ],
            },
        ],
    }


def _write_synthetic_baseline(root: Path) -> tuple[Path, Path]:
    reference_root = root / "references"
    reference_root.mkdir()
    fixture_content = json.dumps(
        _synthetic_fixture(),
        ensure_ascii=False,
        sort_keys=True,
    ).encode("utf-8")
    (reference_root / "synthetic.json").write_bytes(fixture_content)
    baseline = root / "baseline.json"
    baseline.write_text(
        json.dumps(
            {
                "format": "dnd-rules-baseline-v1",
                "library_version": "synthetic-v1",
                "sources": [
                    {
                        "id": "syn",
                        "title": "自有测试规则",
                        "version": "1",
                        "path": "synthetic.json",
                        "sha256": _sha256(fixture_content),
                        "format": "fixture-json",
                        "expected": {
                            "page_count": 2,
                            "minimum_categories": {
                                "semantic_section": 1,
                                "spell": 1,
                                "condition": 1,
                            },
                        },
                        "coverage": {
                            "matrix_id": "PHB-03",
                            "owner": "dnd-5e-rules",
                            "collaborators": ["dnd-5e-session"],
                            "authoritative_state": "规则实体与激活状态",
                            "observable_result": "返回可追溯规则结论",
                            "failure_path": "缺失内容时拒绝权威裁定",
                            "acceptance_scenario": "按别名查询规则实体",
                        },
                        "rights": {
                            "status": "authorized",
                            "rights_holder": "测试作者",
                            "basis": "原创测试夹具",
                            "transformation_scope": "允许转换",
                            "distribution_scope": "允许公开分发",
                            "attribution": "无需署名",
                            "evidence": "tests/test_rules_build.py",
                        },
                    }
                ],
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return baseline, reference_root


def _rewrite_source_and_hash(
    baseline_path: Path,
    reference_root: Path,
    fixture: dict[str, Any],
) -> None:
    content = json.dumps(
        fixture,
        ensure_ascii=False,
        sort_keys=True,
    ).encode("utf-8")
    (reference_root / "synthetic.json").write_bytes(content)
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    baseline["sources"][0]["sha256"] = _sha256(content)
    baseline_path.write_text(
        json.dumps(baseline, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


class RulesLibraryBuildBoundaryTests(unittest.TestCase):
    def test_all_source_hashes_are_checked_before_content_is_parsed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            reference_root = root / "references"
            reference_root.mkdir()
            first_content = b"not valid fixture json"
            second_content = b"also not valid fixture json"
            (reference_root / "first.json").write_bytes(first_content)
            (reference_root / "second.json").write_bytes(second_content)
            baseline = root / "baseline.json"
            baseline.write_text(
                json.dumps(
                    {
                        "format": "dnd-rules-baseline-v1",
                        "library_version": "synthetic-v1",
                        "sources": [
                            {
                                "id": "first",
                                "title": "自有测试规则一",
                                "version": "1",
                                "path": "first.json",
                                "sha256": _sha256(first_content),
                                "format": "fixture-json",
                            },
                            {
                                "id": "second",
                                "title": "自有测试规则二",
                                "version": "1",
                                "path": "second.json",
                                "sha256": "0" * 64,
                                "format": "fixture-json",
                            },
                        ],
                    },
                    ensure_ascii=False,
                ),
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
            error = json.loads(result.stderr) if result.stderr else None

            self.assertEqual(
                {
                    "returncode": 2,
                    "stdout": "",
                    "error": {
                        "ok": False,
                        "error": {
                            "code": "source_hash_mismatch",
                            "message": "固定来源的 SHA-256 不匹配。",
                            "source_id": "second",
                            "source_path": "second.json",
                        },
                    },
                    "output_exists": False,
                    "has_traceback": False,
                },
                {
                    "returncode": result.returncode,
                    "stdout": result.stdout,
                    "error": error,
                    "output_exists": output.exists(),
                    "has_traceback": "Traceback" in result.stderr,
                },
            )

    def test_build_emits_a_deterministic_traceable_complete_library(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            baseline, reference_root = _write_synthetic_baseline(root)
            first_output = root / "first-library"
            second_output = root / "second-library"

            first = run_rules_builder(
                "build",
                "--baseline",
                str(baseline),
                "--reference-root",
                str(reference_root),
                "--output",
                str(first_output),
            )
            second = run_rules_builder(
                "build",
                "--baseline",
                str(baseline),
                "--reference-root",
                str(reference_root),
                "--output",
                str(second_output),
            )
            first_result = json.loads(first.stdout) if first.stdout else None
            manifest = json.loads(
                (first_output / "library.json").read_text(encoding="utf-8")
            ) if (first_output / "library.json").is_file() else None
            index = json.loads(
                (first_output / "index.json").read_text(encoding="utf-8")
            ) if (first_output / "index.json").is_file() else None
            coverage = json.loads(
                (first_output / "coverage.json").read_text(encoding="utf-8")
            ) if (first_output / "coverage.json").is_file() else None
            files = sorted(
                path.relative_to(first_output).as_posix()
                for path in first_output.rglob("*")
                if path.is_file()
            ) if first_output.exists() else []
            markdown = "\n".join(
                path.read_text(encoding="utf-8")
                for path in first_output.rglob("*.md")
            ) if first_output.exists() else ""
            serialized_output = "\n".join(
                path.read_text(encoding="utf-8")
                for path in first_output.rglob("*")
                if path.is_file()
            ) if first_output.exists() else ""

            self.assertEqual(0, first.returncode, msg=first.stderr)
            self.assertEqual(0, second.returncode, msg=second.stderr)
            assert isinstance(first_result, dict)
            assert isinstance(manifest, dict)
            assert isinstance(index, dict)
            assert isinstance(coverage, dict)
            self.assertEqual(3, first_result.get("asset_count"))
            self.assertEqual(
                {
                    "content_quality": "passed",
                    "local_preview": "available",
                    "public_release": "available",
                },
                manifest.get("distribution") if isinstance(manifest, dict) else None,
            )
            self.assertEqual(
                {"condition": 1, "semantic_section": 1, "spell": 1},
                manifest.get("category_counts") if isinstance(manifest, dict) else None,
            )
            self.assertEqual(3, len(index.get("items", [])))
            self.assertEqual(3, len(coverage.get("items", [])))
            self.assertTrue(
                all(
                    {
                        "id",
                        "title",
                        "category",
                        "aliases",
                        "activation_condition",
                        "rule_status",
                        "source",
                        "chapter_path",
                        "pages",
                        "cross_references",
                        "referenced_by",
                        "extraction_status",
                        "content_sha256",
                        "file_sha256",
                        "path",
                    }.issubset(item)
                    for item in index.get("items", [])
                )
            )
            self.assertIn("| 等级 | 范围 |", markdown)
            self.assertIn("> **限定词**", markdown)
            self.assertIn("[^fixture-note]: 该脚注同样是自有测试文本。", markdown)
            self.assertIn("跨页部分保留例外", markdown)
            self.assertNotIn(str(root), serialized_output)
            self.assertEqual(
                [
                    "blocked.json",
                    "coverage.json",
                    "entities/syn-condition-795496e53334.md",
                    "entities/syn-spell-959054de576b.md",
                    "exceptions.json",
                    "index.json",
                    "library.json",
                    "sections/syn-semantic-section-49abe87888b2.md",
                    "sources.json",
                ],
                files,
            )
            self.assertEqual(
                _directory_sha256(first_output),
                _directory_sha256(second_output),
            )

    def test_unreviewed_rule_content_blocks_the_build(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            baseline, reference_root = _write_synthetic_baseline(root)
            fixture = _synthetic_fixture()
            fixture["pages"][0]["blocks"][2]["rule_status"] = "review"
            _rewrite_source_and_hash(baseline, reference_root, fixture)
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
            error = json.loads(result.stderr) if result.stderr.startswith("{") else None

            self.assertEqual(
                {
                    "returncode": 2,
                    "code": "unreviewed_rule_content",
                    "source_id": "syn",
                    "output_exists": False,
                },
                {
                    "returncode": result.returncode,
                    "code": error.get("error", {}).get("code") if error else None,
                    "source_id": (
                        error.get("error", {}).get("source_id") if error else None
                    ),
                    "output_exists": output.exists(),
                },
                msg=result.stderr,
            )

    def test_public_build_requires_complete_source_rights(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            baseline, reference_root = _write_synthetic_baseline(root)
            baseline_payload = json.loads(baseline.read_text(encoding="utf-8"))
            baseline_payload["sources"][0]["rights"] = {
                "status": "not_reviewed",
                "rights_holder": None,
                "basis": None,
                "transformation_scope": None,
                "distribution_scope": None,
                "attribution": None,
                "evidence": None,
            }
            baseline.write_text(
                json.dumps(baseline_payload, ensure_ascii=False, sort_keys=True),
                encoding="utf-8",
            )
            output = root / "public-library"

            result = run_rules_builder(
                "build",
                "--publication",
                "public",
                "--baseline",
                str(baseline),
                "--reference-root",
                str(reference_root),
                "--output",
                str(output),
            )
            error = json.loads(result.stderr) if result.stderr.startswith("{") else None

            self.assertEqual(
                {
                    "returncode": 2,
                    "code": "public_release_blocked",
                    "output_exists": False,
                },
                {
                    "returncode": result.returncode,
                    "code": error.get("error", {}).get("code") if error else None,
                    "output_exists": output.exists(),
                },
                msg=result.stderr,
            )


if __name__ == "__main__":
    unittest.main()
