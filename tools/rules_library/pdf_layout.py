from __future__ import annotations

from dataclasses import dataclass
import importlib
from pathlib import Path
import re
from typing import Any

from tools.rules_library.baseline import SourceSpec
from tools.rules_library.errors import BuildError
from tools.rules_library.pdf_fonts import replace_cid_placeholders


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


def normalized_text(text: str) -> str:
    normalized = " ".join(text.replace("\u00a0", " ").split())
    normalized = re.sub(
        r"(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])",
        "",
        normalized,
    )
    normalized = re.sub(r"\s+([，。；：、？！）》】])", r"\1", normalized)
    normalized = re.sub(r"([（《【])\s+", r"\1", normalized)
    return normalized.strip()


def lookup_key(text: str) -> str:
    return re.sub(r"[\W_]+", "", text, flags=re.UNICODE).casefold()


def extract_page_lines(
    page: Any,
    *,
    page_number: int,
    page_label: str,
    first_index: int,
    cid_maps: dict[str, dict[int, str]],
) -> list[LayoutLine]:
    deduplicated = page.dedupe_chars(
        tolerance=1,
        extra_attrs=("fontname", "size"),
    )
    words: list[dict[str, Any]] = deduplicated.extract_words(
        extra_attrs=["size", "fontname"],
        use_text_flow=False,
        keep_blank_chars=False,
    )
    midpoint = float(page.width) / 2
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

    lines: list[LayoutLine] = []
    for group in sorted(groups, key=lambda item: (item["column"], item["top"])):
        grouped_words = sorted(group["words"], key=lambda item: float(item["x0"]))
        decoded_words = [
            replace_cid_placeholders(
                str(word["text"]),
                str(word["fontname"]),
                cid_maps,
            )
            for word in grouped_words
        ]
        text = normalized_text(" ".join(decoded_words))
        if not text:
            continue
        if float(group["top"]) > float(page.height) - 45 and (
            lookup_key(text) == lookup_key(page_label)
            or re.fullmatch(r"\d+", text) is not None
        ):
            continue
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
            )
        )
    return lines


def extract_layout(
    pdfplumber: Any,
    path: Path,
    labels: list[str],
    cid_maps: dict[str, dict[int, str]],
) -> tuple[list[LayoutLine], list[float]]:
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
