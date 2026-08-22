from __future__ import annotations

from dataclasses import dataclass
import importlib
from pathlib import Path
import re
from typing import Any

from tools.rules_library.baseline import SourceSpec
from tools.rules_library.errors import BuildError
from tools.rules_library.pdf_fonts import replace_cid_placeholders
from tools.rules_library.pdf_structure import extract_semantic_blocks
from tools.rules_library.text import lookup_key, normalized_text


@dataclass(frozen=True)
class LayoutLine:
    index: int
    page: int
    page_label: str
    column: int
    top: float
    x0: float
    size: float
    fonts: tuple[str, ...]
    text: str
    block_kind: str
    rendered_text: str
    structure_group: str | None
    is_colored: bool


@dataclass(frozen=True)
class OutlineEntry:
    title: str
    level: int
    page: int
    top: float | None
    left: float | None
    chapter_path: tuple[str, ...]
    order: int


@dataclass
class Marker:
    line_index: int
    title: str
    level: int
    chapter_path: tuple[str, ...]
    origin: str
    outline_order: int | None = None
    heading_end_index: int | None = None


def _color_is_visible(color: object) -> bool:
    if isinstance(color, (int, float)):
        return abs(float(color)) > 0.01
    if isinstance(color, (tuple, list)):
        return any(
            isinstance(component, (int, float)) and abs(float(component)) > 0.01
            for component in color
        )
    return False


def _adjustment_mapping(source: SourceSpec, key: str) -> dict[str, float]:
    raw_mapping = source.options.get(key, {})
    if not isinstance(raw_mapping, dict) or not all(
        isinstance(font, str)
        and font
        and isinstance(adjustment, (int, float))
        and abs(float(adjustment)) <= 100
        for font, adjustment in raw_mapping.items()
    ):
        raise BuildError("invalid_baseline", "规则基线清单无效。")
    return {
        str(font).casefold(): float(adjustment)
        for font, adjustment in raw_mapping.items()
    }


def _coordinate_groups(
    words: list[dict[str, Any]],
    midpoint: float,
) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for word in sorted(
        words,
        key=lambda item: (
            0 if float(item["x0"]) < midpoint else 1,
            float(item["top"]),
            float(item["x0"]),
        ),
    ):
        column = 0 if float(word["x0"]) < midpoint else 1
        group = next(
            (
                candidate
                for candidate in reversed(groups[-10:])
                if candidate["column"] == column
                and abs(float(candidate["top"]) - float(word["top"])) <= 2.8
            ),
            None,
        )
        if group is None:
            group = {
                "column": column,
                "top": float(word["top"]),
                "x0": float(word["x0"]),
                "words": [],
            }
            groups.append(group)
        group["x0"] = min(float(group["x0"]), float(word["x0"]))
        group["words"].append(word)
    return groups


def load_dependencies(source: SourceSpec) -> tuple[Any, Any]:
    try:
        return importlib.import_module("pdfplumber"), importlib.import_module("pypdf")
    except ModuleNotFoundError as error:
        raise BuildError(
            "missing_build_dependency",
            "PDF 构建需要 rules-build 可选依赖。",
            source.source_id,
            source.relative_path,
        ) from error


def extract_page_lines(
    page: Any,
    *,
    page_number: int,
    page_label: str,
    first_index: int,
    cid_maps: dict[str, dict[int, str]],
    font_top_adjustments: dict[str, float] | None = None,
) -> list[LayoutLine]:
    deduplicated = page.dedupe_chars(
        tolerance=1,
        extra_attrs=("fontname", "size", "non_stroking_color"),
    )
    raw_words: list[dict[str, Any]] = deduplicated.extract_words(
        extra_attrs=["size", "fontname", "non_stroking_color"],
        use_text_flow=False,
        keep_blank_chars=False,
    )
    words = [dict(word) for word in raw_words]
    adjustments = font_top_adjustments or {}
    for word in words:
        word["_source_top"] = float(word["top"])
        font_name = str(word["fontname"])
        adjustment = adjustments.get(
            font_name.casefold(),
            0.0,
        )
        word["top"] = float(word["top"]) + adjustment
        word["bottom"] = float(word["bottom"]) + adjustment
        word["text"] = replace_cid_placeholders(
            str(word["text"]),
            str(word["fontname"]),
            cid_maps,
        )
    midpoint = float(page.width) / 2
    detected_structures = extract_semantic_blocks(page, words)
    semantic_blocks = detected_structures.blocks
    assigned = {word_id for block in semantic_blocks for word_id in block.word_ids}
    semantic_lines = [
        LayoutLine(
            index=0,
            page=page_number,
            page_label=page_label,
            column=(
                2
                if block.width >= float(page.width) * 0.7
                else 0
                if block.x0 < midpoint
                else 1
            ),
            top=block.top,
            x0=block.x0,
            size=block.size,
            fonts=block.fonts,
            text=block.text,
            block_kind=block.block_kind,
            rendered_text=block.rendered_text,
            structure_group=f"p{page_number}-{block.block_kind}-{index + 1}",
            is_colored=block.is_colored,
        )
        for index, block in enumerate(semantic_blocks)
    ]
    words = [word for word in words if id(word) not in assigned]
    groups = _coordinate_groups(words, midpoint)

    lines: list[LayoutLine] = []
    for group in sorted(groups, key=lambda item: (item["column"], item["top"])):
        grouped_words = sorted(group["words"], key=lambda item: float(item["x0"]))
        text = normalized_text(" ".join(str(word["text"]) for word in grouped_words))
        if not text:
            continue
        source_top = min(
            float(word.get("_source_top", word["top"]))
            for word in grouped_words
        )
        is_page_label = lookup_key(text) == lookup_key(page_label)
        if (
            is_page_label and source_top > float(page.height) - 75
        ) or (
            re.fullmatch(r"\d+", text) is not None
            and source_top > float(page.height) - 45
        ):
            continue
        sidebar_groups = {
            detected_structures.sidebar_groups[id(word)]
            for word in grouped_words
            if id(word) in detected_structures.sidebar_groups
        }
        is_sidebar = len(sidebar_groups) == 1 and all(
            id(word) in detected_structures.sidebar_groups for word in grouped_words
        )
        is_footnote = (
            not is_sidebar
            and
            float(group["top"]) >= float(page.height) * 0.72
            and max(float(word["size"]) for word in grouped_words) <= 7
            and re.match(r"^(?:\*|†|‡|\d{1,2}[.、)])\s*", text) is not None
        )
        block_kind = (
            "sidebar" if is_sidebar else "footnote" if is_footnote else "paragraph"
        )
        rendered_text = (
            f"> {text}"
            if is_sidebar
            else
            f"[^pdf-p{page_number}-n{1 + sum(line.block_kind == 'footnote' for line in lines)}]: {text}"
            if is_footnote
            else text
        )
        lines.append(
            LayoutLine(
                index=first_index + len(lines),
                page=page_number,
                page_label=page_label,
                column=int(group["column"]),
                top=float(group["top"]),
                x0=float(group["x0"]),
                size=max(float(word["size"]) for word in grouped_words),
                fonts=tuple(
                    sorted({str(word["fontname"]) for word in grouped_words})
                ),
                text=text,
                block_kind=block_kind,
                rendered_text=rendered_text,
                structure_group=(
                    f"p{page_number}-{next(iter(sidebar_groups))}"
                    if is_sidebar
                    else f"p{page_number}-footnote-{len(lines) + 1}"
                    if is_footnote
                    else None
                ),
                is_colored=any(
                    _color_is_visible(word.get("non_stroking_color"))
                    for word in grouped_words
                ),
            )
        )
    lines.extend(semantic_lines)
    lines.sort(key=lambda line: (line.column, line.top, line.x0, line.block_kind))
    return [
        LayoutLine(
            index=first_index + index,
            page=line.page,
            page_label=line.page_label,
            column=line.column,
            top=line.top,
            x0=line.x0,
            size=line.size,
            fonts=line.fonts,
            text=line.text,
            block_kind=line.block_kind,
            rendered_text=line.rendered_text,
            structure_group=line.structure_group,
            is_colored=line.is_colored,
        )
        for index, line in enumerate(lines)
    ]


def extract_layout(
    pdfplumber: Any,
    path: Path,
    labels: list[str],
    cid_maps: dict[str, dict[int, str]],
    source: SourceSpec,
) -> tuple[list[LayoutLine], list[float]]:
    font_top_adjustments = _adjustment_mapping(source, "font_top_adjustments")
    lines: list[LayoutLine] = []
    page_heights: list[float] = []
    with pdfplumber.open(path) as document:
        for page_number, page in enumerate(document.pages, start=1):
            page_heights.append(float(page.height))
            page_label = labels[page_number - 1]
            page_lines = extract_page_lines(
                page,
                page_number=page_number,
                page_label=page_label,
                first_index=len(lines),
                cid_maps=cid_maps,
                font_top_adjustments=font_top_adjustments,
            )
            lines.extend(page_lines)
    return lines, page_heights


def extract_outline(reader: Any, source: SourceSpec) -> list[OutlineEntry]:
    entries: list[OutlineEntry] = []

    def walk(items: list[Any], level: int, ancestors: tuple[str, ...]) -> None:
        previous_title: str | None = None
        for item in items:
            if isinstance(item, list):
                child_ancestors = (
                    (*ancestors, previous_title) if previous_title is not None else ancestors
                )
                walk(item, level + 1, child_ancestors)
                continue
            title = normalized_text(str(getattr(item, "title", item)))
            try:
                page = int(reader.get_destination_page_number(item)) + 1
            except Exception as error:
                raise BuildError(
                    "unreadable_pdf_outline",
                    "固定来源的 PDF 书签无法定位。",
                    source.source_id,
                    source.relative_path,
                ) from error
            raw_top = getattr(item, "top", None)
            raw_left = getattr(item, "left", None)
            entries.append(
                OutlineEntry(
                    title=title,
                    level=level,
                    page=page,
                    top=float(raw_top) if raw_top is not None else None,
                    left=float(raw_left) if raw_left is not None else None,
                    chapter_path=(*ancestors, title),
                    order=len(entries),
                )
            )
            previous_title = title

    try:
        raw_outline = reader.outline
    except Exception as error:
        raise BuildError(
            "unreadable_pdf_outline",
            "固定来源的 PDF 书签无法读取。",
            source.source_id,
            source.relative_path,
        ) from error
    if not isinstance(raw_outline, list):
        raise BuildError(
            "unreadable_pdf_outline",
            "固定来源的 PDF 书签无法读取。",
            source.source_id,
            source.relative_path,
        )
    walk(raw_outline, 0, ())
    return entries


def outline_markers(
    entries: list[OutlineEntry],
    lines: list[LayoutLine],
    page_heights: list[float],
) -> list[Marker]:
    by_page: dict[int, list[LayoutLine]] = {}
    for line in lines:
        by_page.setdefault(line.page, []).append(line)
    consumed: set[tuple[int, str, int]] = set()
    markers: list[Marker] = []
    for entry in entries:
        page_lines = by_page.get(entry.page, [])
        if not page_lines:
            continue
        title_key = lookup_key(entry.title)
        textual_matches = [
            line
            for line in page_lines
            if lookup_key(line.text)
            and (
                lookup_key(line.text) in title_key
                or title_key in lookup_key(line.text)
            )
        ]
        target_top = (
            page_heights[entry.page - 1] - entry.top
            if entry.top is not None
            else None
        )
        target_column = (
            1
            if entry.left is not None and entry.left >= 297
            else 0
            if entry.left is not None
            else None
        )
        candidates = textual_matches or page_lines
        if target_column is not None:
            same_column = [line for line in candidates if line.column == target_column]
            candidates = same_column or candidates
        candidates = [
            line
            for line in candidates
            if (entry.page, title_key, line.index) not in consumed
        ] or candidates
        chosen = min(
            candidates,
            key=lambda line: (
                abs(line.top - target_top) if target_top is not None else line.index,
                line.index,
            ),
        )
        consumed.add((entry.page, title_key, chosen.index))
        markers.append(
            Marker(
                line_index=chosen.index,
                title=entry.title,
                level=entry.level,
                chapter_path=entry.chapter_path,
                origin="outline",
                outline_order=entry.order,
            )
        )
    return markers
