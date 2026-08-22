from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from typing import Callable

from tests.facade_support import run_facade, run_rules_builder
from tests.rules_support import build_synthetic_library, verified_rule_exception
from tests.test_rules_build import (
    _rewrite_source_and_hash,
    _synthetic_fixture,
    _write_synthetic_baseline,
)


_IDENTITY_KEYS = (
    "build_tool_version",
    "normalizer_version",
    "parser_versions",
    "sources_sha256",
    "index_sha256",
    "coverage_sha256",
    "blocked_sha256",
    "exceptions_sha256",
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


def _write_json(path: Path, value: object) -> str:
    content = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        indent=2,
        sort_keys=True,
    ).encode("utf-8") + b"\n"
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def _refresh_library_identity(library: Path) -> None:
    manifest_path = library / "library.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    identity = {key: manifest[key] for key in _IDENTITY_KEYS if key in manifest}
    manifest["library_sha256"] = hashlib.sha256(
        _canonical_json(identity)
    ).hexdigest()
    _write_json(manifest_path, manifest)


def _expect_invalid_query(library: Path) -> None:
    result = run_facade(
        "rules-query",
        "--library",
        str(library),
        "--alias",
        "星光术",
    )
    error = json.loads(result.stderr) if result.stderr else None

    assert isinstance(error, dict)
    if result.returncode != 2 or error.get("error", {}).get("code") != (
        "invalid_rules_library"
    ):
        raise AssertionError(result.stdout or result.stderr)


class RulesQualityGateTests(unittest.TestCase):
    def test_missing_reviewed_leaf_fails_exact_inventory_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            baseline, reference_root = _write_synthetic_baseline(root)
            full_fixture = _synthetic_fixture()
            full_fixture["pages"][1]["blocks"].extend(
                [
                    {
                        "kind": "heading",
                        "level": 2,
                        "title": "第二项自有状态",
                        "category": "condition",
                        "aliases": ["第二状态"],
                    },
                    {"kind": "paragraph", "text": "该规则叶项必须完整生成。"},
                ]
            )
            _rewrite_source_and_hash(baseline, reference_root, full_fixture)
            baseline_payload = json.loads(baseline.read_text(encoding="utf-8"))
            baseline_payload["sources"][0]["expected"]["asset_count"] = 4
            baseline.write_text(
                json.dumps(baseline_payload, ensure_ascii=False, sort_keys=True),
                encoding="utf-8",
            )
            complete = run_rules_builder(
                "build",
                "--baseline",
                str(baseline),
                "--reference-root",
                str(reference_root),
                "--output",
                str(root / "complete"),
            )
            self.assertEqual(0, complete.returncode, msg=complete.stderr)

            incomplete_fixture = _synthetic_fixture()
            _rewrite_source_and_hash(baseline, reference_root, incomplete_fixture)
            incomplete = run_rules_builder(
                "build",
                "--baseline",
                str(baseline),
                "--reference-root",
                str(reference_root),
                "--output",
                str(root / "incomplete"),
            )
            error = json.loads(incomplete.stderr) if incomplete.stderr else None

            self.assertEqual(2, incomplete.returncode, msg=incomplete.stderr)
            assert isinstance(error, dict)
            self.assertEqual(
                "incomplete_source_coverage",
                error["error"]["code"],
            )

    def test_query_rejects_self_consistent_non_authoritative_libraries(self) -> None:
        mutators: dict[str, Callable[[Path], None]] = {
            "failed distribution": _mark_distribution_failed,
            "review item": _mark_item_for_review,
            "dangling reference": _add_dangling_reference,
            "blocked item": _add_blocked_item,
        }
        for label, mutate in mutators.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
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
                mutate(library)
                _expect_invalid_query(library)

    def test_runtime_rejects_an_exception_targeting_an_index_only_rule(self) -> None:
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
            library = build_synthetic_library(
                root,
                fixture=fixture,
                rule_exceptions=[verified_rule_exception()],
            )
            index_path = library / "index.json"
            index = json.loads(index_path.read_text(encoding="utf-8"))
            general_rule = next(
                item
                for item in index["items"]
                if item["category"] == "semantic_section"
            )
            general_rule["extraction_status"] = "index_only"
            index_hash = _write_json(index_path, index)
            manifest_path = library / "library.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["index_sha256"] = index_hash
            _write_json(manifest_path, manifest)
            _refresh_library_identity(library)

            _expect_invalid_query(library)


def _mark_distribution_failed(library: Path) -> None:
    manifest_path = library / "library.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["distribution"]["content_quality"] = "failed"
    _write_json(manifest_path, manifest)
    _refresh_library_identity(library)


def _mark_item_for_review(library: Path) -> None:
    index_path = library / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index["items"][0]["rule_status"] = "review"
    index_hash = _write_json(index_path, index)
    manifest_path = library / "library.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["index_sha256"] = index_hash
    _write_json(manifest_path, manifest)
    _refresh_library_identity(library)


def _add_dangling_reference(library: Path) -> None:
    index_path = library / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index["items"][0]["cross_references"].append("missing-asset")
    index_hash = _write_json(index_path, index)
    manifest_path = library / "library.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["index_sha256"] = index_hash
    _write_json(manifest_path, manifest)
    _refresh_library_identity(library)


def _add_blocked_item(library: Path) -> None:
    blocked_hash = _write_json(
        library / "blocked.json",
        {
            "format": "dnd-rules-blocked-v1",
            "items": [{"source_id": "syn", "reason": "尚未复核"}],
        },
    )
    manifest_path = library / "library.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["blocked_sha256"] = blocked_hash
    _write_json(manifest_path, manifest)
    _refresh_library_identity(library)


if __name__ == "__main__":
    unittest.main()
