from __future__ import annotations

import json
from pathlib import Path
import subprocess
from typing import Any

from tests.facade_support import run_rules_builder
from tests.test_rules_build import (
    _rewrite_source_and_hash,
    _write_synthetic_baseline,
)


def run_synthetic_library_build(
    root: Path,
    *,
    fixture: dict[str, Any] | None = None,
    rule_exceptions: list[dict[str, str]] | None = None,
) -> tuple[Path, subprocess.CompletedProcess[str]]:
    baseline, reference_root = _write_synthetic_baseline(root)
    if fixture is not None:
        _rewrite_source_and_hash(baseline, reference_root, fixture)
    if rule_exceptions is not None:
        baseline_payload = json.loads(baseline.read_text(encoding="utf-8"))
        baseline_payload["rule_exceptions"] = rule_exceptions
        baseline.write_text(
            json.dumps(baseline_payload, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
    library = root / "library"
    result = run_rules_builder(
        "build",
        "--baseline",
        str(baseline),
        "--reference-root",
        str(reference_root),
        "--output",
        str(library),
    )
    return library, result


def build_synthetic_library(
    root: Path,
    *,
    fixture: dict[str, Any] | None = None,
    rule_exceptions: list[dict[str, str]] | None = None,
) -> Path:
    library, result = run_synthetic_library_build(
        root,
        fixture=fixture,
        rule_exceptions=rule_exceptions,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return library
