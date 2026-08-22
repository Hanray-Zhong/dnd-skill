from __future__ import annotations

from collections import Counter
import hashlib
import json
from typing import Any

from tools.rules_library.errors import BuildError
from tools.rules_library.models import DraftAsset, ExtractedSource


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _asset_inventory_item(asset: DraftAsset) -> dict[str, object]:
    body = "\n\n".join(asset.body_parts).strip()
    item: dict[str, object] = {
        "title": asset.title,
        "category": asset.category,
        "aliases": list(asset.aliases),
        "chapter_path": list(asset.chapter_path),
        "rule_status": asset.rule_status,
        "activation_condition": asset.activation_condition,
        "explicit_references": list(asset.explicit_references),
        "pages": asset.pages,
        "page_labels": asset.page_labels,
        "extraction_status": asset.extraction_status,
        "body_sha256": _sha256(body.encode("utf-8")),
    }
    if asset.parent_order is not None:
        item["parent_order"] = asset.parent_order
    return item


def extraction_snapshot(extracted: ExtractedSource) -> dict[str, object]:
    inventory = [_asset_inventory_item(asset) for asset in extracted.assets]
    return {
        "asset_count": len(extracted.assets),
        "category_counts": dict(
            sorted(Counter(asset.category for asset in extracted.assets).items())
        ),
        "text_characters": extracted.total_text_characters,
        "structure_counts": dict(sorted(extracted.structure_counts.items())),
        "parser_versions": dict(sorted(extracted.parser_versions.items())),
        "asset_inventory_sha256": _sha256(_canonical_json(inventory)),
    }


def _expected_mapping(extracted: ExtractedSource) -> dict[str, Any]:
    expected = extracted.source.options.get("expected", {})
    if not isinstance(expected, dict):
        raise BuildError("invalid_baseline", "规则基线清单无效。")
    return expected


def _validate_exact_snapshot(
    extracted: ExtractedSource,
    expected: dict[str, Any],
) -> None:
    snapshot = extraction_snapshot(extracted)
    exact_keys = {
        "asset_count",
        "category_counts",
        "text_characters",
        "structure_counts",
        "parser_versions",
        "asset_inventory_sha256",
    }
    if extracted.source.source_format == "pdf" and not exact_keys.issubset(expected):
        raise BuildError(
            "invalid_baseline",
            "PDF 固定来源缺少精确提取快照。",
            extracted.source.source_id,
            extracted.source.relative_path,
        )
    for key in exact_keys.intersection(expected):
        if expected[key] != snapshot[key]:
            raise BuildError(
                "incomplete_source_coverage",
                "固定来源的精确提取快照不匹配。",
                extracted.source.source_id,
                extracted.source.relative_path,
            )


def validate_extraction(extracted: ExtractedSource) -> None:
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
    if any(not asset.body_parts or not asset.pages for asset in extracted.assets):
        raise BuildError(
            "incomplete_source_coverage",
            "固定来源存在没有正文或页码的规则资产。",
            extracted.source.source_id,
            extracted.source.relative_path,
        )
    expected = _expected_mapping(extracted)
    for key, actual in (
        ("page_count", extracted.page_count),
        ("outline_count", extracted.outline_count),
    ):
        configured = expected.get(key)
        if configured is not None and configured != actual:
            raise BuildError(
                "incomplete_source_coverage",
                "固定来源页数或目录与完整性约束不匹配。",
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
    _validate_exact_snapshot(extracted, expected)
