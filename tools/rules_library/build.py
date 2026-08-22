from __future__ import annotations

import os
from pathlib import Path
import shutil
import tempfile

from tools.rules_library.assemble import assemble_library, write_json
from tools.rules_library.baseline import ValidatedSource, load_baseline, validate_sources
from tools.rules_library.errors import BuildError
from tools.rules_library.fixture_extractor import extract_fixture
from tools.rules_library.models import ExtractedSource
from tools.rules_library.pdf_extractor import extract_pdf
from tools.rules_library.validation import validate_extraction


def extract_source(validated: ValidatedSource) -> ExtractedSource:
    if validated.spec.source_format == "fixture-json":
        return extract_fixture(validated.path, validated.spec)
    if validated.spec.source_format == "pdf":
        return extract_pdf(validated.path, validated.spec)
    raise BuildError(
        "unsupported_source_format",
        "固定来源格式不受构建器支持。",
        validated.spec.source_id,
        validated.spec.relative_path,
    )


def build_library(
    *,
    baseline_path: Path,
    reference_root: Path,
    output: Path,
    publication: str = "local-preview",
) -> dict[str, object]:
    baseline = load_baseline(baseline_path)
    validated_sources = validate_sources(baseline, reference_root)
    if output.exists():
        raise BuildError("output_not_empty", "规则章节库输出目录必须不存在。")
    extracted_sources = tuple(extract_source(source) for source in validated_sources)
    for extracted in extracted_sources:
        validate_extraction(extracted)

    output_parent = output.parent.resolve(strict=False)
    output_parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".rules-library-", dir=output_parent))
    try:
        result = assemble_library(staging, extracted_sources)
        identity = result["identity"]
        if not isinstance(identity, dict):
            raise AssertionError("构建结果缺少规则库身份")
        distribution = identity.get("distribution")
        if (
            publication == "public"
            and isinstance(distribution, dict)
            and distribution.get("public_release") != "available"
        ):
            raise BuildError(
                "public_release_blocked",
                "来源授权清单不完整，禁止生成公开发布物。",
            )
        manifest = {
            "format": "dnd-rules-library-v1",
            "library_version": baseline.library_version,
            **identity,
            "library_sha256": result["library_sha256"],
        }
        write_json(staging / "library.json", manifest)
        os.replace(staging, output)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return {
        "library_version": baseline.library_version,
        "library_sha256": result["library_sha256"],
        "asset_count": result["asset_count"],
    }
