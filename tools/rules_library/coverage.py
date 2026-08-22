from __future__ import annotations

from tools.rules_library.baseline import SourceSpec
from tools.rules_library.errors import BuildError
from tools.rules_library.models import DraftAsset


def _configuration(source: SourceSpec, asset: DraftAsset) -> dict[str, object]:
    raw_coverage = source.options.get("coverage")
    if not isinstance(raw_coverage, dict):
        raise BuildError(
            "coverage_mapping_missing",
            "规则资产缺少完整叶级覆盖映射。",
            source.source_id,
            source.relative_path,
        )
    coverage = dict(raw_coverage)
    by_category = source.options.get("coverage_by_category", {})
    if not isinstance(by_category, dict):
        raise BuildError("invalid_baseline", "规则基线清单无效。")
    category_override = by_category.get(asset.category)
    if category_override is not None:
        if not isinstance(category_override, dict):
            raise BuildError("invalid_baseline", "规则基线清单无效。")
        coverage.update(category_override)
        return coverage

    routes = source.options.get("coverage_routes", [])
    if not isinstance(routes, list):
        raise BuildError("invalid_baseline", "规则基线清单无效。")
    first_page = asset.pages[0] if asset.pages else 0
    for route in routes:
        if not isinstance(route, dict):
            raise BuildError("invalid_baseline", "规则基线清单无效。")
        pages = route.get("pages")
        keywords = route.get("title_keywords")
        page_match = pages is None or (
            isinstance(pages, list)
            and len(pages) == 2
            and all(type(page) is int for page in pages)
            and pages[0] <= first_page <= pages[1]
        )
        keyword_match = keywords is None or (
            isinstance(keywords, list)
            and all(isinstance(keyword, str) for keyword in keywords)
            and any(keyword.casefold() in asset.title.casefold() for keyword in keywords)
        )
        if not page_match or not keyword_match:
            continue
        override = route.get("override")
        if not isinstance(override, dict):
            raise BuildError("invalid_baseline", "规则基线清单无效。")
        coverage.update(override)
        break
    return coverage


def coverage_record(
    source: SourceSpec,
    asset: DraftAsset,
    asset_id: str,
) -> dict[str, object]:
    coverage = _configuration(source, asset)
    required = {
        "matrix_id",
        "owner",
        "collaborators",
        "authoritative_state",
        "observable_result",
        "failure_path",
        "acceptance_scenario",
    }
    if not required.issubset(coverage):
        raise BuildError(
            "coverage_mapping_missing",
            "规则资产缺少完整叶级覆盖映射。",
            source.source_id,
            source.relative_path,
        )
    collaborators = coverage.get("collaborators")
    if not isinstance(collaborators, list) or not all(
        isinstance(item, str) and item for item in collaborators
    ):
        raise BuildError("invalid_baseline", "规则基线清单无效。")
    return {
        "asset_id": asset_id,
        "matrix_id": coverage["matrix_id"],
        "owner": coverage["owner"],
        "collaborators": collaborators,
        "authoritative_state": coverage["authoritative_state"],
        "observable_result": coverage["observable_result"],
        "failure_path": coverage["failure_path"],
        "acceptance_scenario": coverage["acceptance_scenario"],
        "activation_condition": asset.activation_condition,
        "rule_status": asset.rule_status,
        "validation_status": "已验证",
    }
