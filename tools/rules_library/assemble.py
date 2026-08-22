from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import re

from tools.rules_library.baseline import FormulaSpec, RuleExceptionSpec, SourceSpec
from tools.rules_library.coverage import coverage_record
from tools.rules_library.errors import BuildError
from tools.rules_library.formulas import formula_catalog_payload, formula_records
from tools.rules_library.models import DraftAsset, ExtractedSource
from tools.rules_library.text import lookup_key


BUILD_TOOL_VERSION = "rules-library-builder-v4"
NORMALIZER_VERSION = "semantic-markdown-v2"


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def write_json(path: Path, value: object) -> str:
    content = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        indent=2,
        sort_keys=True,
    ).encode("utf-8") + b"\n"
    path.write_bytes(content)
    return sha256_bytes(content)


def _reference_pattern(
    identities: list[tuple[DraftAsset, str]],
) -> tuple[re.Pattern[str] | None, dict[str, str]]:
    ignored_aliases = {
        "动作", "反应", "攻击", "伤害", "法术", "规则", "属性", "装备",
        "语言", "速度", "感官", "状态", "世界", "战斗", "移动", "目录",
        "前言", "简介",
    }
    target_sets: dict[str, set[str]] = {}
    display_aliases: dict[str, str] = {}
    for draft, asset_id in identities:
        for alias in draft.aliases:
            normalized = lookup_key(alias)
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
        if (normalized := lookup_key(match.group(0))) in targets
    }


def _asset_id(asset: DraftAsset, used_ids: set[str]) -> str:
    category_slug = asset.category.replace("_", "-")
    identity = "\0".join(
        (asset.source.source_id, asset.category, "/".join(asset.chapter_path))
    )
    suffix = sha256_bytes(identity.encode("utf-8"))[:12]
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
        "status", "rights_holder", "basis", "transformation_scope",
        "distribution_scope", "attribution", "evidence",
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


def _asset_records(
    staging: Path,
    extracted_sources: tuple[ExtractedSource, ...],
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[DraftAsset]]:
    drafts = [asset for source in extracted_sources for asset in source.assets]
    used_ids: set[str] = set()
    identities = [(draft, _asset_id(draft, used_ids)) for draft in drafts]
    by_source_order = {
        (draft.source.source_id, draft.order): asset_id
        for draft, asset_id in identities
    }
    if len(by_source_order) != len(identities):
        raise BuildError("duplicate_asset_order", "规则资产构建顺序不唯一。")
    alias_index: dict[str, list[str]] = {}
    for draft, asset_id in identities:
        for alias in draft.aliases:
            normalized = lookup_key(alias)
            if normalized:
                alias_index.setdefault(normalized, []).append(asset_id)
    automatic_pattern, automatic_targets = _reference_pattern(identities)
    index_items: list[dict[str, object]] = []
    coverage_items: list[dict[str, object]] = []
    for draft, asset_id in identities:
        cross_references: list[str] = []
        if draft.parent_order is not None:
            parent_id = by_source_order.get(
                (draft.source.source_id, draft.parent_order)
            )
            if parent_id is None or parent_id == asset_id:
                raise BuildError(
                    "broken_cross_reference",
                    "规则资产父级引用无法解析。",
                    draft.source.source_id,
                    draft.source.relative_path,
                )
            cross_references.append(parent_id)
        for reference in draft.explicit_references:
            matches = alias_index.get(lookup_key(reference), [])
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
        content_sha256 = sha256_bytes(body.encode("utf-8"))
        directory = "sections" if draft.category == "semantic_section" else "entities"
        relative_path = f"{directory}/{asset_id}.md"
        metadata: dict[str, object] = {
            "id": asset_id,
            "title": draft.title,
            "category": draft.category,
            "aliases": list(draft.aliases),
            "activation_condition": draft.activation_condition,
            "rule_status": draft.rule_status,
            "source": {
                "id": draft.source.source_id,
                "title": draft.source.title,
                "version": draft.source.version,
                "sha256": draft.source.sha256,
            },
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
        (staging / relative_path).write_bytes(markdown)
        index_items.append(
            {
                **metadata,
                "file_sha256": sha256_bytes(markdown),
                "path": relative_path,
            }
        )
        coverage_items.append(coverage_record(draft.source, draft, asset_id))
    return index_items, coverage_items, drafts


def _add_backlinks(index_items: list[dict[str, object]]) -> None:
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


def _source_record(extracted: ExtractedSource) -> dict[str, object]:
    raw_visual_pages = extracted.source.options.get("visual_only_pages", [])
    if not isinstance(raw_visual_pages, list) or not all(
        type(page) is int and 1 <= page <= extracted.page_count
        for page in raw_visual_pages
    ):
        raise BuildError("invalid_baseline", "规则基线清单无效。")
    expected_visual_pages = set(raw_visual_pages)
    mapped_pages = {page for asset in extracted.assets for page in asset.pages}
    actual_visual_pages = set(range(1, extracted.page_count + 1)) - mapped_pages
    if actual_visual_pages != expected_visual_pages:
        raise BuildError(
            "unmapped_source_page",
            "固定来源存在未声明的空白规则页或视觉页声明已失效。",
            extracted.source.source_id,
            extracted.source.relative_path,
        )
    return {
        "id": extracted.source.source_id,
        "title": extracted.source.title,
        "version": extracted.source.version,
        "sha256": extracted.source.sha256,
        "format": extracted.source.source_format,
        "page_count": extracted.page_count,
        "outline_count": extracted.outline_count,
        "total_text_characters": extracted.total_text_characters,
        "structure_counts": dict(sorted(extracted.structure_counts.items())),
        "parser_versions": dict(sorted(extracted.parser_versions.items())),
        "page_coverage": [
            {
                "pdf_page": page,
                "label": extracted.page_labels[page - 1],
                "status": "visual_only" if page in actual_visual_pages else "generated",
            }
            for page in range(1, extracted.page_count + 1)
        ],
        "rights": _rights(extracted.source),
    }


def _resolve_rule(
    alias: str,
    index_items: list[dict[str, object]],
    *,
    error_code: str,
    error_message: str,
) -> dict[str, object]:
    normalized_alias = lookup_key(alias)
    matches: list[dict[str, object]] = []
    for item in index_items:
        aliases = item.get("aliases")
        if not isinstance(aliases, list):
            raise AssertionError("规则索引缺少已验证别名。")
        if any(
            isinstance(candidate, str) and lookup_key(candidate) == normalized_alias
            for candidate in aliases
        ):
            matches.append(item)
    if len(matches) != 1:
        raise BuildError(
            error_code,
            f"{error_message}别名：{alias}；匹配数：{len(matches)}。",
        )
    return matches[0]


def _rule_exception_records(
    specs: tuple[RuleExceptionSpec, ...],
    index_items: list[dict[str, object]],
    drafts: list[DraftAsset],
) -> list[dict[str, object]]:
    if len(index_items) != len(drafts):
        raise AssertionError("规则索引与提取草稿数量不一致。")
    body_by_id = {
        str(item["id"]): "\n\n".join(draft.body_parts).strip()
        for item, draft in zip(index_items, drafts, strict=True)
    }
    records: list[dict[str, object]] = []
    seen_pairs: set[tuple[str, str]] = set()
    for spec in specs:
        if spec.review_status != "verified":
            raise BuildError(
                "unreviewed_rule_exception",
                "规则例外声明尚未完成复核。",
            )
        specific = _resolve_rule(
            spec.specific_rule_alias,
            index_items,
            error_code="unresolved_rule_exception",
            error_message="规则例外声明无法唯一定位规则条目。",
        )
        general = _resolve_rule(
            spec.general_rule_alias,
            index_items,
            error_code="unresolved_rule_exception",
            error_message="规则例外声明无法唯一定位规则条目。",
        )
        specific_id = str(specific["id"])
        general_id = str(general["id"])
        pair = (specific_id, general_id)
        references = specific.get("cross_references")
        if (
            specific_id == general_id
            or specific.get("category") == "semantic_section"
            or specific.get("extraction_status") != "verified"
            or general.get("extraction_status") != "verified"
            or general.get("rule_status") != "default"
            or not isinstance(references, list)
            or not all(isinstance(reference, str) for reference in references)
        ):
            raise BuildError("invalid_rule_exception", "规则例外声明无效。")
        if general_id not in references:
            raise BuildError(
                "broken_rule_exception_reference",
                "具体实体没有引用规则例外声明中的一般规则。",
            )
        conflict_values = (
            spec.scope,
            spec.general_value,
            spec.specific_value,
            spec.general_evidence,
            spec.specific_evidence,
            spec.review_evidence,
        )
        if (
            pair in seen_pairs
            or any(not value.strip() for value in conflict_values)
            or spec.general_value == spec.specific_value
            or spec.general_value not in spec.general_evidence
            or spec.specific_value not in spec.specific_evidence
            or spec.general_evidence not in body_by_id[general_id]
            or spec.specific_evidence not in body_by_id[specific_id]
        ):
            raise BuildError(
                "unverified_rule_exception",
                "规则例外声明无法由两侧规则正文验证。",
            )
        seen_pairs.add(pair)
        records.append(
            {
                "id": spec.exception_id,
                "specific_rule_id": specific_id,
                "general_rule_id": general_id,
                "scope": spec.scope,
                "general_value": spec.general_value,
                "specific_value": spec.specific_value,
                "general_evidence": spec.general_evidence,
                "specific_evidence": spec.specific_evidence,
                "review_status": spec.review_status,
                "review_evidence": spec.review_evidence,
            }
        )
    records.sort(key=lambda record: str(record["id"]))
    return records


def assemble_library(
    staging: Path,
    extracted_sources: tuple[ExtractedSource, ...],
    rule_exceptions: tuple[RuleExceptionSpec, ...],
    formula_catalog_version: str,
    formulas: tuple[FormulaSpec, ...],
) -> dict[str, object]:
    (staging / "sections").mkdir()
    (staging / "entities").mkdir()
    index_items, coverage_items, drafts = _asset_records(staging, extracted_sources)
    _add_backlinks(index_items)
    exception_items = _rule_exception_records(rule_exceptions, index_items, drafts)
    formula_items = formula_records(formulas, index_items, drafts)
    index_items.sort(key=lambda item: str(item["id"]))
    coverage_items.sort(key=lambda item: str(item["asset_id"]))
    if len(index_items) != len(coverage_items):
        raise BuildError("coverage_mapping_missing", "规则资产缺少完整叶级覆盖映射。")
    source_items = [_source_record(extracted) for extracted in extracted_sources]
    index_hash = write_json(
        staging / "index.json",
        {"format": "dnd-rules-index-v1", "items": index_items},
    )
    coverage_hash = write_json(
        staging / "coverage.json",
        {"format": "dnd-rules-leaf-coverage-v1", "items": coverage_items},
    )
    sources_hash = write_json(
        staging / "sources.json",
        {"format": "dnd-rules-sources-v1", "items": source_items},
    )
    blocked_hash = write_json(
        staging / "blocked.json",
        {"format": "dnd-rules-blocked-v1", "items": []},
    )
    exceptions_hash = write_json(
        staging / "exceptions.json",
        {"format": "dnd-rules-exceptions-v1", "items": exception_items},
    )
    formulas_hash = write_json(
        staging / "formulas.json",
        formula_catalog_payload(formula_catalog_version, formula_items),
    )
    public_ready = all(
        isinstance(item["rights"], dict)
        and item["rights"].get("status") == "authorized"
        for item in source_items
    )
    parser_versions: dict[str, str] = {}
    for extracted in extracted_sources:
        for parser, version in extracted.parser_versions.items():
            previous = parser_versions.setdefault(parser, version)
            if previous != version:
                raise BuildError("parser_version_mismatch", "规则来源使用了不同解析器版本。")
    identity = {
        "build_tool_version": BUILD_TOOL_VERSION,
        "normalizer_version": NORMALIZER_VERSION,
        "parser_versions": dict(sorted(parser_versions.items())),
        "sources_sha256": sources_hash,
        "index_sha256": index_hash,
        "coverage_sha256": coverage_hash,
        "blocked_sha256": blocked_hash,
        "exceptions_sha256": exceptions_hash,
        "formulas_sha256": formulas_hash,
        "asset_count": len(index_items),
        "category_counts": dict(
            sorted(Counter(draft.category for draft in drafts).items())
        ),
        "distribution": {
            "content_quality": "passed",
            "local_preview": "available",
            "public_release": "available" if public_ready else "blocked",
        },
    }
    return {
        "identity": identity,
        "asset_count": len(index_items),
        "library_sha256": sha256_bytes(canonical_json(identity)),
    }
