from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tools.rules_library.table_entities import repair_table_cells
from tools.rules_library.text import normalized_text


_Bbox = tuple[float, float, float, float]


@dataclass(frozen=True)
class SemanticBlock:
    word_ids: frozenset[int]
    top: float
    x0: float
    width: float
    size: float
    fonts: tuple[str, ...]
    text: str
    block_kind: str
    rendered_text: str
    is_colored: bool


@dataclass(frozen=True)
class DetectedStructures:
    blocks: tuple[SemanticBlock, ...]
    sidebar_groups: dict[int, str]


def _bbox(raw: object) -> _Bbox | None:
    if not isinstance(raw, (tuple, list)) or len(raw) != 4:
        return None
    if not all(isinstance(value, (int, float)) for value in raw):
        return None
    x0, top, x1, bottom = (float(value) for value in raw)
    return (x0, top, x1, bottom) if x0 < x1 and top < bottom else None


def _inside(
    word: dict[str, Any],
    bbox: _Bbox,
    *,
    tolerance: float = 0.0,
) -> bool:
    center_x = (float(word["x0"]) + float(word["x1"])) / 2
    center_y = (float(word["top"]) + float(word["bottom"])) / 2
    return (
        bbox[0] - tolerance <= center_x <= bbox[2] + tolerance
        and bbox[1] - tolerance <= center_y <= bbox[3] + tolerance
    )


def _group_words(words: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    rows: list[list[dict[str, Any]]] = []
    for word in sorted(words, key=lambda item: (float(item["top"]), float(item["x0"]))):
        row = next(
            (
                candidate
                for candidate in reversed(rows[-5:])
                if abs(float(candidate[0]["top"]) - float(word["top"])) <= 2.8
            ),
            None,
        )
        if row is None:
            row = []
            rows.append(row)
        row.append(word)
    return [sorted(row, key=lambda item: float(item["x0"])) for row in rows]


def _split_cells(row: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    cells: list[list[dict[str, Any]]] = []
    for word in row:
        if not cells or float(word["x0"]) - float(cells[-1][-1]["x1"]) > 6:
            cells.append([])
        cells[-1].append(word)
    return cells


def _text(words: list[dict[str, Any]]) -> str:
    return normalized_text(" ".join(str(word["text"]) for word in words))


def _has_color(word: dict[str, Any]) -> bool:
    color = word.get("non_stroking_color", 0)
    if isinstance(color, (int, float)):
        return abs(float(color)) > 0.01
    if isinstance(color, (tuple, list)):
        return any(
            isinstance(component, (int, float)) and abs(float(component)) > 0.01
            for component in color
        )
    return False


def _gap_contains_heading(
    upper: _Bbox,
    lower: _Bbox,
    words: list[dict[str, Any]],
) -> bool:
    for word in words:
        center_x = (float(word["x0"]) + float(word["x1"])) / 2
        center_y = (float(word["top"]) + float(word["bottom"])) / 2
        font = str(word["fontname"]).casefold()
        if (
            upper[3] < center_y < lower[1]
            and min(upper[0], lower[0]) <= center_x <= max(upper[2], lower[2])
            and float(word["size"]) >= 9.2
            and ("bold" in font or "simhei" in font)
        ):
            return True
    return False


def _should_merge_zones(
    first: _Bbox,
    second: _Bbox,
    words: list[dict[str, Any]],
) -> bool:
    horizontal_overlap = max(
        0.0,
        min(first[2], second[2]) - max(first[0], second[0]),
    )
    vertical_overlap = max(
        0.0,
        min(first[3], second[3]) - max(first[1], second[1]),
    )
    minimum_width = min(first[2] - first[0], second[2] - second[0])
    minimum_height = min(first[3] - first[1], second[3] - second[1])
    vertical_gap = max(first[1] - second[3], second[1] - first[3], 0.0)
    horizontal_gap = max(first[0] - second[2], second[0] - first[2], 0.0)
    if (
        horizontal_overlap >= minimum_width * 0.75
        and vertical_gap <= 60
    ):
        upper, lower = (first, second) if first[1] <= second[1] else (second, first)
        return not _gap_contains_heading(upper, lower, words)
    return vertical_overlap >= minimum_height * 0.75 and horizontal_gap <= 24


def _union(first: _Bbox, second: _Bbox) -> _Bbox:
    return (
        min(first[0], second[0]),
        min(first[1], second[1]),
        max(first[2], second[2]),
        max(first[3], second[3]),
    )


def _extend_table_bottom(
    zone: _Bbox,
    words: list[dict[str, Any]],
    page_height: float,
) -> float:
    current_bottom = min(page_height, zone[3] + 12)
    candidates = [
        word
        for word in words
        if zone[0]
        <= (float(word["x0"]) + float(word["x1"])) / 2
        <= zone[2]
        and (float(word["top"]) + float(word["bottom"])) / 2 > current_bottom
    ]
    for row in _group_words(candidates):
        row_top = min(float(word["top"]) for word in row)
        row_bottom = max(float(word["bottom"]) for word in row)
        bold_heading = any(
            float(word["size"]) >= 9.2
            and (
                "bold" in str(word["fontname"]).casefold()
                or "simhei" in str(word["fontname"]).casefold()
            )
            for word in row
        )
        continuation_indent = min(float(word["x0"]) for word in row) - zone[0]
        if (
            row_top - current_bottom > 24
            or bold_heading
            or continuation_indent < 20
        ):
            break
        current_bottom = row_bottom
    return min(page_height, current_bottom)


def _extend_table_top(zone: _Bbox, words: list[dict[str, Any]]) -> float:
    default_top = max(0.0, zone[1] - 18)
    candidates = [
        word
        for word in words
        if zone[0]
        <= (float(word["x0"]) + float(word["x1"])) / 2
        <= zone[2]
        and zone[1] - 36
        <= (float(word["top"]) + float(word["bottom"])) / 2
        < default_top
    ]
    title_rows = [
        row
        for row in _group_words(candidates)
        if row
        and max(float(word["size"]) for word in row) >= 9
        and all(
            "bold" in str(word["fontname"]).casefold()
            or "simhei" in str(word["fontname"]).casefold()
            for word in row
        )
    ]
    if not title_rows:
        return default_top
    return min(float(word["top"]) for row in title_rows for word in row)


def _table_zones(page: Any, words: list[dict[str, Any]]) -> list[_Bbox]:
    try:
        raw_boxes = [
            parsed
            for table in page.find_tables()
            if (parsed := _bbox(getattr(table, "bbox", None))) is not None
            and parsed[2] - parsed[0] >= 60
        ]
    except Exception as error:
        raise ValueError("PDF 表格边界无法可靠识别") from error
    zones = sorted(raw_boxes, key=lambda item: (item[1], item[0]))
    changed = True
    while changed:
        changed = False
        for first_index, first in enumerate(zones):
            matched_index = next(
                (
                    second_index
                    for second_index in range(first_index + 1, len(zones))
                    if _should_merge_zones(first, zones[second_index], words)
                ),
                None,
            )
            if matched_index is None:
                continue
            zones[first_index] = _union(first, zones.pop(matched_index))
            changed = True
            break
    return [
        (
            zone[0],
            _extend_table_top(zone, words),
            zone[2],
            _extend_table_bottom(zone, words, float(page.height)),
        )
        for zone in zones
    ]


def _render_table(words: list[dict[str, Any]]) -> tuple[str, str] | None:
    rows = _group_words(words)
    if len(rows) < 2:
        return None
    split_rows = [_split_cells(row) for row in rows]
    column_count = max((len(cells) for cells in split_rows), default=0)
    if column_count < 2:
        return None
    header_index = next(
        index for index, cells in enumerate(split_rows) if len(cells) == column_count
    )
    header_cells = split_rows[header_index]
    starts = [float(cell[0]["x0"]) for cell in header_cells]
    boundaries = [
        (float(header_cells[index][-1]["x1"]) + starts[index + 1]) / 2
        for index in range(len(starts) - 1)
    ]

    def values(row: list[dict[str, Any]]) -> list[str]:
        assigned: list[list[dict[str, Any]]] = [[] for _ in starts]
        for word in row:
            column = sum(float(word["x0"]) >= boundary for boundary in boundaries)
            assigned[column].append(word)
        return [_text(cell).replace("|", "\\|") for cell in assigned]

    header = values(rows[header_index])
    data = [
        repair_table_cells(header, values(row), title_column=0)
        for row in rows[header_index + 1 :]
    ]
    if not any(any(cell for cell in row) for row in data):
        return None
    title = " ".join(_text(row) for row in rows[:header_index]).strip()
    rendered_rows = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
        *("| " + " | ".join(row) + " |" for row in data),
    ]
    rendered = "\n".join(rendered_rows)
    if title:
        rendered = f"**{title}**\n\n{rendered}"
    return _text(words), rendered


def _is_bordered_callout(words: list[dict[str, Any]]) -> bool:
    rows = _group_words(words)
    return len(rows) >= 2 and all(len(_split_cells(row)) == 1 for row in rows)


def _sidebar_zones(page: Any) -> list[_Bbox]:
    zones: list[_Bbox] = []
    for raw_rect in getattr(page, "rects", []):
        if not isinstance(raw_rect, dict) or not raw_rect.get("fill"):
            continue
        bbox = _bbox(
            (
                raw_rect.get("x0"),
                raw_rect.get("top"),
                raw_rect.get("x1"),
                raw_rect.get("bottom"),
            )
        )
        if bbox is None:
            continue
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
        if width < float(page.width) * 0.28 or height < 45:
            continue
        zones.append(bbox)
    return zones


def _block(
    words: list[dict[str, Any]],
    bbox: _Bbox,
    kind: str,
    rendered: str,
    *,
    plain_text: str | None = None,
) -> SemanticBlock:
    return SemanticBlock(
        word_ids=frozenset(id(word) for word in words),
        top=bbox[1],
        x0=bbox[0],
        width=bbox[2] - bbox[0],
        size=max(float(word["size"]) for word in words),
        fonts=tuple(sorted({str(word["fontname"]) for word in words})),
        text=plain_text if plain_text is not None else _text(words),
        block_kind=kind,
        rendered_text=rendered,
        is_colored=any(_has_color(word) for word in words),
    )


def extract_semantic_blocks(
    page: Any,
    words: list[dict[str, Any]],
) -> DetectedStructures:
    table_zones = _table_zones(page, words)
    blocks: list[SemanticBlock] = []
    assigned: set[int] = set()
    sidebar_groups: dict[int, str] = {}
    sidebar_number = 0
    for bbox in table_zones:
        selected = [word for word in words if _inside(word, bbox)]
        rendered = _render_table(selected)
        if rendered is None:
            if _is_bordered_callout(selected):
                sidebar_number += 1
                for word in selected:
                    sidebar_groups[id(word)] = f"bordered-sidebar-{sidebar_number}"
                continue
            raise ValueError(
                "PDF 表格内容无法可靠恢复："
                f"page={getattr(page, 'page_number', '?')}, bbox={bbox}"
            )
        plain_text, rendered_text = rendered
        block = _block(
            selected,
            bbox,
            "table",
            rendered_text,
            plain_text=plain_text,
        )
        assigned.update(block.word_ids)
        blocks.append(block)
    for bbox in _sidebar_zones(page):
        selected = [
            word
            for word in words
            if id(word) not in assigned
            and id(word) not in sidebar_groups
            and _inside(word, bbox, tolerance=0.5)
        ]
        if len(selected) < 2:
            continue
        sidebar_number += 1
        for word in selected:
            sidebar_groups[id(word)] = f"sidebar-{sidebar_number}"
    return DetectedStructures(
        blocks=tuple(blocks),
        sidebar_groups=sidebar_groups,
    )
