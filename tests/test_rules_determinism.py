from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from tests.facade_support import run_rules_builder
from tests.test_rules_build import (
    _rewrite_source_and_hash,
    _synthetic_fixture,
    _write_synthetic_baseline,
)


class RulesLibraryDeterminismTests(unittest.TestCase):
    def test_normalized_content_change_changes_library_and_asset_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            baseline, reference_root = _write_synthetic_baseline(root)
            before = root / "before"
            first = run_rules_builder(
                "build",
                "--baseline",
                str(baseline),
                "--reference-root",
                str(reference_root),
                "--output",
                str(before),
            )
            self.assertEqual(0, first.returncode, msg=first.stderr)

            fixture = _synthetic_fixture()
            fixture["pages"][0]["blocks"][3]["text"] = (
                "规范化规则变化后的自有测试结论。"
            )
            _rewrite_source_and_hash(baseline, reference_root, fixture)
            after = root / "after"
            second = run_rules_builder(
                "build",
                "--baseline",
                str(baseline),
                "--reference-root",
                str(reference_root),
                "--output",
                str(after),
            )
            self.assertEqual(0, second.returncode, msg=second.stderr)

            before_manifest = json.loads(
                (before / "library.json").read_text(encoding="utf-8")
            )
            after_manifest = json.loads(
                (after / "library.json").read_text(encoding="utf-8")
            )
            before_index = json.loads(
                (before / "index.json").read_text(encoding="utf-8")
            )
            after_index = json.loads(
                (after / "index.json").read_text(encoding="utf-8")
            )
            before_spell = next(
                item for item in before_index["items"] if item["category"] == "spell"
            )
            after_spell = next(
                item for item in after_index["items"] if item["category"] == "spell"
            )

            self.assertNotEqual(
                before_manifest["library_sha256"],
                after_manifest["library_sha256"],
            )
            self.assertNotEqual(
                before_spell["content_sha256"],
                after_spell["content_sha256"],
            )


if __name__ == "__main__":
    unittest.main()
