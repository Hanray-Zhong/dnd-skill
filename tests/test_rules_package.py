from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

from tests.facade_support import run_rules_builder
from tests.test_rules_build import _write_synthetic_baseline


class LocalPreviewPackageBoundaryTests(unittest.TestCase):
    def test_installed_preview_queries_rules_without_references_or_build_tools(self) -> None:
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
            wheels = root / "wheels"

            package = run_rules_builder(
                "preview-wheel",
                "--library",
                str(library),
                "--output-directory",
                str(wheels),
            )
            package_payload = json.loads(package.stdout) if package.stdout else None
            wheel_path = wheels / "dnd_5e_skill_suite-0.1.0-py3-none-any.whl"
            with (
                zipfile.ZipFile(wheel_path) if wheel_path.is_file() else _MissingZip()
            ) as wheel:
                entries = sorted(wheel.namelist())
                serialized = "\n".join(
                    wheel.read(name).decode("utf-8", errors="ignore")
                    for name in entries
                )

            shutil.rmtree(reference_root)
            installed = root / "installed"
            install = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "--no-deps",
                    "--target",
                    str(installed),
                    str(wheel_path),
                ],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )
            environment = os.environ.copy()
            environment["PYTHONPATH"] = str(installed)
            query = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "dnd_5e",
                    "rules-query",
                    "--alias",
                    "星光术",
                ],
                cwd=root,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            query_payload = json.loads(query.stdout) if query.stdout else None
            campaign = root / "campaign"
            create = subprocess.run(
                [sys.executable, "-m", "dnd_5e", "create", str(campaign)],
                cwd=root,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            campaign_manifest = json.loads(
                (campaign / "campaign.json").read_text(encoding="utf-8")
            ) if (campaign / "campaign.json").is_file() else None
            library_manifest = json.loads(
                (library / "library.json").read_text(encoding="utf-8")
            )

            forbidden_entries = [
                name
                for name in entries
                if name.startswith(("tools/", "tests/", "docs/reference/"))
                or name.endswith((".pdf", ".xlsx", ".tmp", ".pyc"))
                or "__pycache__" in name
            ]
            self.assertEqual(0, package.returncode, msg=package.stderr)
            self.assertEqual(
                {
                    "ok": True,
                    "wheel": wheel_path.name,
                    "library_version": "synthetic-v1",
                    "asset_count": 3,
                },
                package_payload,
            )
            self.assertEqual([], forbidden_entries)
            self.assertTrue(
                any(name.startswith("dnd_5e/rule_assets/entities/") for name in entries)
            )
            self.assertTrue(
                any(
                    name.endswith(".data/data/share/dnd-5e-skill-suite/skills/dnd-5e/SKILL.md")
                    for name in entries
                )
            )
            self.assertNotIn(str(root), serialized)
            self.assertEqual(0, install.returncode, msg=install.stderr)
            self.assertEqual(0, query.returncode, msg=query.stderr)
            assert isinstance(query_payload, dict)
            assert isinstance(campaign_manifest, dict)
            self.assertEqual(True, query_payload.get("ok"))
            self.assertEqual("星光术 Starlight", query_payload["rules"][0]["title"])
            self.assertEqual(0, create.returncode, msg=create.stderr)
            self.assertEqual(
                {
                    "version": library_manifest["library_version"],
                    "sha256": library_manifest["library_sha256"],
                },
                campaign_manifest["compatibility"]["rules_library"],
            )

    def test_preview_package_rejects_unlisted_cache_files(self) -> None:
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
            (library / "extraction-cache.tmp").write_text(
                "不得进入预览包\n",
                encoding="utf-8",
            )
            output = root / "wheels"

            result = run_rules_builder(
                "preview-wheel",
                "--library",
                str(library),
                "--output-directory",
                str(output),
            )
            error = json.loads(result.stderr) if result.stderr else None

            self.assertEqual(2, result.returncode)
            assert isinstance(error, dict)
            self.assertEqual("invalid_rules_library", error["error"]["code"])
            self.assertFalse(output.exists())


class _MissingZip:
    def __enter__(self) -> _MissingZip:
        return self

    def __exit__(self, *_arguments: object) -> None:
        return None

    def namelist(self) -> list[str]:
        return []

    def read(self, _name: str) -> bytes:
        return b""


if __name__ == "__main__":
    unittest.main()
