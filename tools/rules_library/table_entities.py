from __future__ import annotations

from dataclasses import dataclass
import re

from tools.rules_library.baseline import SourceSpec
from tools.rules_library.errors import BuildError
from tools.rules_library.models import DraftAsset
from tools.rules_library.text import lookup_key, normalized_text, title_aliases


_CATEGORY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
_SEPARATOR_PATTERN = re.compile(r"^:?-{3,}:?$")
_PRICE_HEADERS = {"价格", "工钱", "每日支出"}
_CURRENCY_PATTERN = re.compile(
    r"(?<![A-Za-z])(?:\d[\d,.]*|[×＊*])\s*(?:cp|sp|ep|gp|pp)\b",
    flags=re.IGNORECASE,
)
_PRICE_WEIGHT_SPILL_PATTERN = re.compile(
    r"^(?P<price>.*\b(?:cp|sp|ep|gp|pp))\s+"
    r"(?P<weight>(?:\d+(?:[./]\d+)?)|[¼½¾])$",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class TableEntitySpec:
    parent_key: str
    category: str
    title_column: int
    minimum_populated_cells: int


def _invalid_baseline(source: SourceSpec) -> BuildError:
    return BuildError(
        "invalid_baseline",
        "规则基线清单无效。",
        source.source_id,
        source.relative_path,
    )


def _specs(source: SourceSpec) -> tuple[TableEntitySpec, ...]:
    raw_specs = source.options.get("table_entities", [])
    if not isinstance(raw_specs, list):
        raise _invalid_baseline(source)
    specs: list[TableEntitySpec] = []
    for raw in raw_specs:
        if not isinstance(raw, dict):
            raise _invalid_baseline(source)
        parent_title = raw.get("parent_title")
        category = raw.get("category")
        title_column = raw.get("title_column", 0)
        minimum = raw.get("minimum_populated_cells", 2)
        if (
            not isinstance(parent_title, str)
            or not parent_title
            or not isinstance(category, str)
            or _CATEGORY_PATTERN.fullmatch(category) is None
            or type(title_column) is not int
            or title_column < 0
            or type(minimum) is not int
            or minimum < 2
        ):
            raise _invalid_baseline(source)
        specs.append(
            TableEntitySpec(
                parent_key=lookup_key(parent_title),
                category=category,
                title_column=title_column,
                minimum_populated_cells=minimum,
            )
        )
    if len({spec.parent_key for spec in specs}) != len(specs):
        raise _invalid_baseline(source)
    return tuple(specs)


def _split_row(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return []
    return [
        normalized_text(cell.replace("\\|", "|"))
        for cell in re.split(r"(?<!\\)\|", stripped[1:-1])
    ]


def _table(markdown: str) -> tuple[list[str], list[list[str]]] | None:
    table_lines = [line for line in markdown.splitlines() if line.strip().startswith("|")]
    if len(table_lines) < 3:
        return None
    headers = _split_row(table_lines[0])
    separator = _split_row(table_lines[1])
    if (
        not headers
        or len(separator) != len(headers)
        or not all(_SEPARATOR_PATTERN.fullmatch(cell) for cell in separator)
    ):
        return None
    rows: list[list[str]] = []
    for line in table_lines[2:]:
        cells = _split_row(line)
        if len(cells) != len(headers):
            continue
        if cells == headers:
            continue
        if all(_SEPARATOR_PATTERN.fullmatch(cell) for cell in cells):
            continue
        rows.append(cells)
    return headers, rows


def _merge_continuations(
    rows: list[list[str]],
    title_column: int,
) -> list[list[str]]:
    merged: list[list[str]] = []
    for row in rows:
        if title_column >= len(row) or row[title_column]:
            merged.append(list(row))
            continue
        if not merged:
            continue
        for index, cell in enumerate(row):
            if cell:
                merged[-1][index] = normalized_text(f"{merged[-1][index]} {cell}")
    return merged


def repair_table_cells(
    headers: list[str],
    row: list[str],
    title_column: int,
) -> list[str]:
    repaired = list(row)
    for index, header in enumerate(headers):
        if index == title_column or lookup_key(header) not in {
            lookup_key(candidate) for candidate in _PRICE_HEADERS
        }:
            continue
        match = _CURRENCY_PATTERN.search(repaired[index])
        if match is None:
            continue
        prefix = repaired[index][: match.start()].strip()
        if not prefix:
            continue
        repaired[title_column] = normalized_text(
            f"{repaired[title_column]} {prefix}"
        )
        repaired[index] = repaired[index][match.start() :].strip()
    price_index = next(
        (
            index
            for index, header in enumerate(headers)
            if lookup_key(header) in {lookup_key(candidate) for candidate in _PRICE_HEADERS}
        ),
        None,
    )
    weight_index = next(
        (
            index
            for index, header in enumerate(headers)
            if lookup_key(header) == lookup_key("重量")
        ),
        None,
    )
    if price_index is not None and weight_index is not None:
        spill = _PRICE_WEIGHT_SPILL_PATTERN.fullmatch(repaired[price_index])
        if spill is not None and repaired[weight_index].startswith("磅"):
            repaired[price_index] = spill.group("price")
            repaired[weight_index] = normalized_text(
                f"{spill.group('weight')} {repaired[weight_index]}"
            )
    return repaired


def _markdown_row(cells: list[str]) -> str:
    return "| " + " | ".join(cell.replace("|", "\\|") for cell in cells) + " |"


def table_row_entities(
    *,
    parent: DraftAsset,
    table_markdown: str,
    page: int,
    page_label: str,
    first_order: int,
) -> list[DraftAsset]:
    spec = next(
        (
            candidate
            for candidate in _specs(parent.source)
            if candidate.parent_key == lookup_key(parent.title)
        ),
        None,
    )
    if spec is None:
        return []
    parsed = _table(table_markdown)
    if parsed is None:
        raise BuildError(
            "unrecoverable_table_entity",
            "配置为独立规则对象的表格无法可靠解析。",
            parent.source.source_id,
            parent.source.relative_path,
        )
    headers, raw_rows = parsed
    if spec.title_column >= len(headers):
        raise _invalid_baseline(parent.source)
    entities: list[DraftAsset] = []
    for raw_row in _merge_continuations(raw_rows, spec.title_column):
        row = repair_table_cells(headers, raw_row, spec.title_column)
        title = row[spec.title_column]
        populated = [cell for cell in row if cell]
        if not title:
            continue
        if len(populated) < spec.minimum_populated_cells:
            continue
        body = "\n".join(
            (
                _markdown_row(headers),
                _markdown_row(["---" for _ in headers]),
                _markdown_row(row),
                "",
                f"完整规则上下文见“{parent.title}”。",
            )
        )
        entity = DraftAsset(
            source=parent.source,
            title=title,
            category=spec.category,
            aliases=title_aliases(title),
            chapter_path=(*parent.chapter_path, title),
            rule_status=parent.rule_status,
            activation_condition=parent.activation_condition,
            explicit_references=(),
            order=first_order + len(entities),
            parent_order=parent.order,
        )
        entity.append_body(body, page, page_label)
        entities.append(entity)
    return entities
