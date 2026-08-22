from __future__ import annotations

from pathlib import Path
import re

from tools.rules_library.baseline import SourceSpec
from tools.rules_library.errors import BuildError
from tools.rules_library.models import DraftAsset, ExtractedSource
from tools.rules_library.pdf_fonts import recover_cid_maps
from tools.rules_library.pdf_layout import (
    LayoutLine,
    Marker,
    extract_layout,
    extract_outline,
    load_dependencies,
    lookup_key,
    outline_markers,
)


def _option_number(options: dict[str, object], key: str, default: float) -> float:
    value = options.get(key, default)
    return float(value) if isinstance(value, (int, float)) else default


def _is_heading(line: LayoutLine, options: dict[str, object]) -> bool:
    minimum_size = _option_number(options, "minimum_heading_size", 9.5)
    left_margin = _option_number(options, "left_margin", 55)
    right_margin = _option_number(options, "right_margin", 309)
    margin_tolerance = _option_number(options, "margin_tolerance", 12)
    bold = any(
        "bold" in font.casefold() or "simhei" in font.casefold()
        for font in line.fonts
    )
    near_margin = min(
        abs(line.x0 - left_margin),
        abs(line.x0 - right_margin),
    ) <= margin_tolerance
    return line.size >= minimum_size and bold and near_margin


def _heading_level(size: float) -> int:
    if size >= 17:
        return 1
    if size >= 13:
        return 2
    if size >= 11.5:
        return 3
    return 4


def _detected_markers(lines: list[LayoutLine], source: SourceSpec) -> list[Marker]:
    detected: list[Marker] = []
    previous_line: LayoutLine | None = None
    for line in lines:
        if not _is_heading(line, source.options):
            previous_line = line
            continue
        if (
            detected
            and previous_line is not None
            and detected[-1].line_index == previous_line.index
            and previous_line.page == line.page
            and previous_line.column == line.column
            and line.top - previous_line.top <= 18
            and re.fullmatch(r"[\x00-\x7f\s\W]+", line.text) is not None
        ):
            detected[-1].title = f"{detected[-1].title} {line.text}"
            previous_line = line
            continue
        detected.append(
            Marker(
                line_index=line.index,
                title=line.text,
                level=_heading_level(line.size),
                chapter_path=(line.text,),
                origin="detected",
            )
        )
        previous_line = line
    return detected


def _merge_markers(outline: list[Marker], detected: list[Marker]) -> list[Marker]:
    merged = list(outline)
    for candidate in detected:
        duplicate = next(
            (
                marker
                for marker in merged
                if marker.line_index == candidate.line_index
                and (
                    lookup_key(marker.title) in lookup_key(candidate.title)
                    or lookup_key(candidate.title) in lookup_key(marker.title)
                )
            ),
            None,
        )
        if duplicate is not None:
            duplicate.origin = "outline+detected"
            if len(candidate.title) < len(duplicate.title) * 2:
                duplicate.title = candidate.title
            continue
        preceding = [marker for marker in outline if marker.line_index <= candidate.line_index]
        if preceding:
            context = max(preceding, key=lambda marker: marker.line_index)
            prefix_length = min(len(context.chapter_path), max(candidate.level - 1, 0))
            candidate.chapter_path = (*context.chapter_path[:prefix_length], candidate.title)
        merged.append(candidate)
    merged.sort(
        key=lambda marker: (
            marker.line_index,
            marker.level,
            marker.outline_order if marker.outline_order is not None else 10**9,
            marker.title,
        )
    )
    unique: list[Marker] = []
    seen: set[tuple[int, str, tuple[str, ...]]] = set()
    for marker in merged:
        identity = (marker.line_index, lookup_key(marker.title), marker.chapter_path)
        if identity not in seen:
            seen.add(identity)
            unique.append(marker)
    return unique


def _entity_category(
    source: SourceSpec,
    marker: Marker,
    line: LayoutLine,
    context: str,
) -> str:
    raw_regions = source.options.get("entity_regions", [])
    if not isinstance(raw_regions, list):
        return "semantic_section"
    for region in raw_regions:
        if not isinstance(region, dict):
            continue
        pages = region.get("pages")
        category = region.get("category")
        detector = region.get("detector")
        if (
            not isinstance(pages, list)
            or len(pages) != 2
            or not all(type(value) is int for value in pages)
            or not isinstance(category, str)
            or not pages[0] <= line.page <= pages[1]
        ):
            continue
        matched = False
        if detector == "spell_fields":
            matched = sum(
                label in context
                for label in ("施法时间", "施法距离", "法术成分", "持续时间")
            ) >= 3
        elif detector == "outline":
            expected_level = region.get("outline_level")
            matched = "outline" in marker.origin and (
                expected_level is None or marker.level == expected_level
            )
        elif detector == "stat_block":
            matched = "AC" in context and "HP" in context and 13 <= line.size <= 15.5
        elif detector == "margin_heading":
            minimum = float(region.get("minimum_size", 9.5))
            maximum = float(region.get("maximum_size", 10.1))
            matched = "detected" in marker.origin and minimum <= line.size <= maximum
        elif detector == "all_headings":
            matched = "detected" in marker.origin
        if matched:
            return category
    return "semantic_section"


def _aliases(title: str) -> tuple[str, ...]:
    aliases = [title]
    english_start = re.search(r"[A-Za-z]", title)
    if english_start is not None:
        chinese = title[: english_start.start()].strip(" ：:，,、")
        english = title[english_start.start() :].strip()
        english = re.split(r"\s+(?:[0-9０-９]+\s*[环级换]|戏法)\b", english)[0]
        if chinese:
            aliases.append(chinese)
        if english:
            aliases.append(english)
    return tuple(dict.fromkeys(alias for alias in aliases if alias))


def _rule_status(title: str) -> tuple[str, str]:
    if any(
        keyword in title.casefold()
        for keyword in ("变体", "可选", "variant", "optional")
    ):
        return "optional", "仅在战役明确启用该可选规则时适用。"
    return "default", "三宝书规则基线适用且没有更具体规则覆盖。"


def _render_body(lines: list[LayoutLine]) -> str:
    rendered: list[str] = []
    previous_page: int | None = None
    for line in lines:
        if previous_page is not None and line.page != previous_page:
            rendered.append("")
        rendered.append(f"{line.text}  ")
        previous_page = line.page
    return "\n".join(rendered).strip()


def extract_pdf(path: Path, source: SourceSpec) -> ExtractedSource:
    pdfplumber, pypdf = load_dependencies(source)
    try:
        reader = pypdf.PdfReader(path)
        labels = [str(label) for label in reader.page_labels]
    except Exception as error:
        raise BuildError(
            "unreadable_pdf",
            "固定来源 PDF 无法读取。",
            source.source_id,
            source.relative_path,
        ) from error
    if len(labels) != len(reader.pages):
        labels = [str(number) for number in range(1, len(reader.pages) + 1)]
    outline = extract_outline(reader, source)
    try:
        cid_maps = recover_cid_maps(reader, source)
        lines, heights = extract_layout(pdfplumber, path, labels, cid_maps)
    except BuildError:
        raise
    except Exception as error:
        raise BuildError(
            "pdf_extraction_failed",
            "固定来源 PDF 的排版文本提取失败。",
            source.source_id,
            source.relative_path,
        ) from error
    if not lines:
        raise BuildError(
            "pdf_extraction_failed",
            "固定来源 PDF 没有可提取文本。",
            source.source_id,
            source.relative_path,
        )
    outline_marker_items = outline_markers(outline, lines, heights)
    markers = _merge_markers(outline_marker_items, _detected_markers(lines, source))
    if not markers or markers[0].line_index > 0:
        markers.insert(
            0,
            Marker(
                line_index=0,
                title=source.title,
                level=0,
                chapter_path=(source.title,),
                origin="generated-root",
            ),
        )

    assets: list[DraftAsset] = []
    for position, marker in enumerate(markers):
        line = lines[marker.line_index]
        next_index = (
            markers[position + 1].line_index if position + 1 < len(markers) else len(lines)
        )
        body_lines = lines[marker.line_index + 1 : next_index]
        context = " ".join(
            candidate.text
            for candidate in lines[marker.line_index + 1 : marker.line_index + 15]
        )
        category = _entity_category(source, marker, line, context)
        status, activation = _rule_status(marker.title)
        body = _render_body(body_lines)
        extraction_status = "verified"
        if not body:
            body = "本目录项在固定来源中作为层级索引，正文由相邻下级语义单元承载。"
            extraction_status = "index_only"
        asset = DraftAsset(
            source=source,
            title=marker.title,
            category=category,
            aliases=_aliases(marker.title),
            chapter_path=marker.chapter_path,
            rule_status=status,
            activation_condition=activation,
            explicit_references=(),
            order=len(assets),
            extraction_status=extraction_status,
        )
        asset.append_body(body, line.page, line.page_label)
        for body_line in body_lines:
            if body_line.page not in asset.pages:
                asset.pages.append(body_line.page)
                asset.page_labels.append(body_line.page_label)
        assets.append(asset)
    return ExtractedSource(
        source=source,
        assets=tuple(assets),
        page_count=len(reader.pages),
        outline_count=len(outline),
        total_text_characters=sum(len(line.text) for line in lines),
        page_labels=tuple(labels),
    )
