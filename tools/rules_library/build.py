from __future__ import annotations

from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any

from tools.rules_library.baseline import (
    SourceSpec,
    ValidatedSource,
    load_baseline,
    validate_sources,
)
from tools.rules_library.errors import BuildError
from tools.rules_library.coverage import coverage_record
from tools.rules_library.fixture_extractor import extract_fixture
from tools.rules_library.models import DraftAsset, ExtractedSource
from tools.rules_library.pdf_extractor import extract_pdf


BUILD_TOOL_VERSION = "rules-library-builder-v1"
NORMALIZER_VERSION = "semantic-markdown-v1"

def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()

def _write_json(path: Path, value: object) -> str:
    content = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        indent=2,
        sort_keys=True,
    ).encode("utf-8") + b"\n"
    path.write_bytes(content)
    return _sha256_bytes(content)


def _extract(validated: ValidatedSource) -> ExtractedSource:
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


def _expected_mapping(source: SourceSpec) -> dict[str, Any]:
    expected = source.options.get("expected", {})
    if not isinstance(expected, dict):
        raise BuildError("invalid_baseline", "规则基线清单无效。")
    return expected


def _validate_extraction(extracted: ExtractedSource) -> None:
    if any(
        "(cid:" in asset.title or any("(cid:" in part for part in asset.body_parts)
        for asset in extracted.assets
    ):
        raise BuildError(
            "unresolved_pdf_glyph",
            "固定来源 PDF 存在无法可靠恢复的字形。",
            extracted.source.source_id,
            extracted.source.relative_path,
        )
    if any(
        asset.rule_status == "review" or asset.extraction_status == "review"
        for asset in extracted.assets
    ):
        raise BuildError(
            "unreviewed_rule_content",
            "固定来源包含尚未复核的规则内容。",
            extracted.source.source_id,
            extracted.source.relative_path,
        )
    expected = _expected_mapping(extracted.source)
    expected_pages = expected.get("page_count")
    if expected_pages is not None and extracted.page_count != expected_pages:
        raise BuildError(
            "incomplete_source_coverage",
            "固定来源页数与完整性约束不匹配。",
            extracted.source.source_id,
            extracted.source.relative_path,
        )
    expected_outline = expected.get("outline_count")
    if expected_outline is not None and extracted.outline_count != expected_outline:
        raise BuildError(
            "incomplete_source_coverage",
            "固定来源目录与完整性约束不匹配。",
            extracted.source.source_id,
            extracted.source.relative_path,
        )
    minimum_categories = expected.get("minimum_categories", {})
    if not isinstance(minimum_categories, dict):
        raise BuildError("invalid_baseline", "规则基线清单无效。")
    counts = Counter(asset.category for asset in extracted.assets)
    for category, minimum in minimum_categories.items():
        if (
            not isinstance(category, str)
            or type(minimum) is not int
            or minimum < 0
            or counts[category] < minimum
        ):
            raise BuildError(
                "incomplete_source_coverage",
                "固定来源的语义章节或规则实体不完整。",
                extracted.source.source_id,
                extracted.source.relative_path,
            )
    minimum_characters = expected.get("minimum_text_characters")
    if minimum_characters is not None and (
        type(minimum_characters) is not int
        or extracted.total_text_characters < minimum_characters
    ):
        raise BuildError(
            "incomplete_source_coverage",
            "固定来源提取文本不完整。",
            extracted.source.source_id,
            extracted.source.relative_path,
        )


def _normalized_lookup(value: str) -> str:
    return re.sub(r"[\W_]+", "", value, flags=re.UNICODE).casefold()


def _reference_pattern(
    identities: list[tuple[DraftAsset, str]],
) -> tuple[re.Pattern[str] | None, dict[str, str]]:
    ignored_aliases = {
        "动作",
        "反应",
        "攻击",
        "伤害",
        "法术",
        "规则",
        "属性",
        "装备",
        "语言",
        "速度",
        "感官",
        "状态",
        "世界",
        "战斗",
        "移动",
        "目录",
        "前言",
        "简介",
    }
    target_sets: dict[str, set[str]] = {}
    display_aliases: dict[str, str] = {}
    for draft, asset_id in identities:
        for alias in draft.aliases:
            normalized = _normalized_lookup(alias)
            ascii_only = alias.isascii()
            if (
                not normalized
                or alias in ignored_aliases
                or len(alias) > 80
                or (ascii_only and len(normalized) < 5)
                or (not ascii_only and len(normalized) < 2)
            ):
                continue
            target_sets.setdefault(normalized, set()).add(asset_id)
            previous = display_aliases.get(normalized)
            if previous is None or len(alias) < len(previous):
                display_aliases[normalized] = alias
    targets = {
        normalized: next(iter(asset_ids))
        for normalized, asset_ids in target_sets.items()
        if len(asset_ids) == 1
    }
    aliases = sorted(
        (display_aliases[key] for key in targets),
        key=lambda alias: (-len(alias), alias.casefold()),
    )
    if not aliases:
        return None, targets
    return re.compile(
        "|".join(re.escape(alias) for alias in aliases),
        flags=re.IGNORECASE,
    ), targets


def _automatic_references(
    body: str,
    pattern: re.Pattern[str] | None,
    targets: dict[str, str],
) -> set[str]:
    if pattern is None:
        return set()
    return {
        targets[normalized]
        for match in pattern.finditer(body)
        if (normalized := _normalized_lookup(match.group(0))) in targets
    }


def _asset_id(asset: DraftAsset, used_ids: set[str]) -> str:
    category_slug = asset.category.replace("_", "-")
    identity = "\0".join(
        (asset.source.source_id, asset.category, "/".join(asset.chapter_path))
    )
    suffix = _sha256_bytes(identity.encode("utf-8"))[:12]
    candidate = f"{asset.source.source_id}-{category_slug}-{suffix}"
    if candidate not in used_ids:
        used_ids.add(candidate)
        return candidate
    occurrence = 2
    while f"{candidate}-{occurrence}" in used_ids:
        occurrence += 1
    unique_candidate = f"{candidate}-{occurrence}"
    used_ids.add(unique_candidate)
    return unique_candidate


def _rights(source: SourceSpec) -> dict[str, object]:
    rights = source.options.get("rights", {})
    if not isinstance(rights, dict):
        raise BuildError("invalid_baseline", "规则基线清单无效。")
    fields = (
        "status",
        "rights_holder",
        "basis",
        "transformation_scope",
        "distribution_scope",
        "attribution",
        "evidence",
    )
    return {field: rights.get(field) for field in fields}


def _render_markdown(metadata: dict[str, object], title: str, body: str) -> bytes:
    frontmatter = json.dumps(
        metadata,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return f"---\n{frontmatter}\n---\n\n# {title}\n\n{body}\n".encode("utf-8")


def _build_into(
    staging: Path,
    extracted_sources: tuple[ExtractedSource, ...],
) -> dict[str, object]:
    (staging / "sections").mkdir()
    (staging / "entities").mkdir()
    drafts = [asset for source in extracted_sources for asset in source.assets]
    used_ids: set[str] = set()
    identities = [(draft, _asset_id(draft, used_ids)) for draft in drafts]

    alias_index: dict[str, list[str]] = {}
    for draft, asset_id in identities:
        for alias in draft.aliases:
            normalized = _normalized_lookup(alias)
            if normalized:
                alias_index.setdefault(normalized, []).append(asset_id)
    automatic_pattern, automatic_targets = _reference_pattern(identities)

    index_items: list[dict[str, object]] = []
    coverage_items: list[dict[str, object]] = []
    for draft, asset_id in identities:
        cross_references: list[str] = []
        for reference in draft.explicit_references:
            matches = alias_index.get(_normalized_lookup(reference), [])
            if len(matches) != 1:
                raise BuildError(
                    "broken_cross_reference",
                    "规则资产交叉引用无法唯一解析。",
                    draft.source.source_id,
                    draft.source.relative_path,
                )
            if matches[0] != asset_id:
                cross_references.append(matches[0])
        body = "\n\n".join(draft.body_parts).strip()
        cross_references.extend(
            _automatic_references(body, automatic_pattern, automatic_targets)
        )
        cross_references = [
            reference for reference in cross_references if reference != asset_id
        ]
        content_sha256 = _sha256_bytes(body.encode("utf-8"))
        asset_directory = (
            "sections" if draft.category == "semantic_section" else "entities"
        )
        relative_path = f"{asset_directory}/{asset_id}.md"
        source_metadata: dict[str, object] = {
            "id": draft.source.source_id,
            "title": draft.source.title,
            "version": draft.source.version,
            "sha256": draft.source.sha256,
        }
        metadata: dict[str, object] = {
            "id": asset_id,
            "title": draft.title,
            "category": draft.category,
            "aliases": list(draft.aliases),
            "activation_condition": draft.activation_condition,
            "rule_status": draft.rule_status,
            "source": source_metadata,
            "chapter_path": list(draft.chapter_path),
            "pages": [
                {"pdf_page": page, "label": label}
                for page, label in zip(draft.pages, draft.page_labels, strict=True)
            ],
            "cross_references": sorted(set(cross_references)),
            "extraction_status": draft.extraction_status,
            "content_sha256": content_sha256,
        }
        markdown = _render_markdown(metadata, draft.title, body)
        file_sha256 = _sha256_bytes(markdown)
        (staging / relative_path).write_bytes(markdown)
        index_items.append(
            {
                **metadata,
                "file_sha256": file_sha256,
                "path": relative_path,
            }
        )
        coverage_items.append(coverage_record(draft.source, draft, asset_id))

    asset_ids = {str(item["id"]) for item in index_items}
    referenced_by: dict[str, list[str]] = {asset_id: [] for asset_id in asset_ids}
    for item in index_items:
        source_id = str(item["id"])
        references = item["cross_references"]
        if not isinstance(references, list) or not all(
            isinstance(reference, str) and reference in asset_ids
            for reference in references
        ):
            raise BuildError("broken_cross_reference", "规则资产交叉引用目标不存在。")
        for target_id in references:
            referenced_by[target_id].append(source_id)
    for item in index_items:
        item["referenced_by"] = sorted(set(referenced_by[str(item["id"])]))

    index_items.sort(key=lambda item: str(item["id"]))
    coverage_items.sort(key=lambda item: str(item["asset_id"]))
    source_items: list[dict[str, object]] = []
    for extracted in extracted_sources:
        raw_visual_pages = extracted.source.options.get("visual_only_pages", [])
        if not isinstance(raw_visual_pages, list) or not all(
            type(page) is int and 1 <= page <= extracted.page_count
            for page in raw_visual_pages
        ):
            raise BuildError("invalid_baseline", "规则基线清单无效。")
        expected_visual_pages = set(raw_visual_pages)
        mapped_pages = {
            page for asset in extracted.assets for page in asset.pages
        }
        actual_visual_pages = set(range(1, extracted.page_count + 1)) - mapped_pages
        if actual_visual_pages != expected_visual_pages:
            raise BuildError(
                "unmapped_source_page",
                "固定来源存在未声明的空白规则页或视觉页声明已失效。",
                extracted.source.source_id,
                extracted.source.relative_path,
            )
        source_items.append(
            {
                "id": extracted.source.source_id,
                "title": extracted.source.title,
                "version": extracted.source.version,
                "sha256": extracted.source.sha256,
                "format": extracted.source.source_format,
                "page_count": extracted.page_count,
                "outline_count": extracted.outline_count,
                "total_text_characters": extracted.total_text_characters,
                "page_coverage": [
                    {
                        "pdf_page": page,
                        "label": extracted.page_labels[page - 1],
                        "status": (
                            "visual_only" if page in actual_visual_pages else "generated"
                        ),
                    }
                    for page in range(1, extracted.page_count + 1)
                ],
                "rights": _rights(extracted.source),
            }
        )
    index_hash = _write_json(
        staging / "index.json",
        {"format": "dnd-rules-index-v1", "items": index_items},
    )
    coverage_hash = _write_json(
        staging / "coverage.json",
        {"format": "dnd-rules-leaf-coverage-v1", "items": coverage_items},
    )
    sources_hash = _write_json(
        staging / "sources.json",
        {"format": "dnd-rules-sources-v1", "items": source_items},
    )
    blocked_hash = _write_json(
        staging / "blocked.json",
        {"format": "dnd-rules-blocked-v1", "items": []},
    )
    category_counts = dict(
        sorted(Counter(draft.category for draft in drafts).items())
    )
    public_ready = all(
        isinstance(item["rights"], dict)
        and item["rights"].get("status") == "authorized"
        for item in source_items
    )
    distribution = {
        "content_quality": "passed",
        "local_preview": "available",
        "public_release": "available" if public_ready else "blocked",
    }
    library_identity = {
        "build_tool_version": BUILD_TOOL_VERSION,
        "normalizer_version": NORMALIZER_VERSION,
        "sources_sha256": sources_hash,
        "index_sha256": index_hash,
        "coverage_sha256": coverage_hash,
        "blocked_sha256": blocked_hash,
        "asset_count": len(index_items),
        "category_counts": category_counts,
        "distribution": distribution,
    }
    library_sha256 = _sha256_bytes(_canonical_json(library_identity))
    return {
        "identity": library_identity,
        "asset_count": len(index_items),
        "library_sha256": library_sha256,
    }


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
    extracted_sources = tuple(_extract(source) for source in validated_sources)
    for extracted in extracted_sources:
        _validate_extraction(extracted)

    output_parent = output.parent.resolve(strict=False)
    output_parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".rules-library-", dir=output_parent))
    try:
        result = _build_into(staging, extracted_sources)
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
        _write_json(staging / "library.json", manifest)
        os.replace(staging, output)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return {
        "library_version": baseline.library_version,
        "library_sha256": result["library_sha256"],
        "asset_count": result["asset_count"],
    }
