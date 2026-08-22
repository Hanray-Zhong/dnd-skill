from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from tools.rules_library.baseline import SourceSpec
from tools.rules_library.errors import BuildError
from tools.rules_library.models import DraftAsset, ExtractedSource


_CATEGORY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
_RULE_STATUSES = {"default", "conditional", "optional", "review"}


def _invalid_fixture(source: SourceSpec) -> BuildError:
    return BuildError(
        "invalid_extraction_fixture",
        "合成规则提取夹具无效。",
        source.source_id,
        source.relative_path,
    )


def _string_list(value: object, source: SourceSpec) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item for item in value
    ):
        raise _invalid_fixture(source)
    return tuple(dict.fromkeys(value))


def _render_table(block: dict[str, Any], source: SourceSpec) -> str:
    headers = _string_list(block.get("headers"), source)
    rows = block.get("rows")
    if not isinstance(rows, list) or not rows:
        raise _invalid_fixture(source)
    rendered_rows: list[str] = []
    for row in rows:
        values = _string_list(row, source)
        if len(values) != len(headers):
            raise _invalid_fixture(source)
        rendered_rows.append("| " + " | ".join(values) + " |")
    return "\n".join(
        [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join("---" for _ in headers) + " |",
            *rendered_rows,
        ]
    )


def _render_content_block(block: dict[str, Any], source: SourceSpec) -> str:
    kind = block.get("kind")
    if kind == "paragraph":
        text = block.get("text")
        if isinstance(text, str) and text:
            return text
    elif kind == "table":
        return _render_table(block, source)
    elif kind == "sidebar":
        title = block.get("title")
        text = block.get("text")
        if isinstance(title, str) and title and isinstance(text, str) and text:
            return f"> **{title}**\n>\n> {text}"
    elif kind == "footnote":
        label = block.get("label")
        text = block.get("text")
        if isinstance(label, str) and label and isinstance(text, str) and text:
            return f"[^{label}]: {text}"
    raise _invalid_fixture(source)


def _load_fixture(path: Path, source: SourceSpec) -> dict[str, Any]:
    try:
        loaded: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise _invalid_fixture(source) from error
    if not isinstance(loaded, dict):
        raise _invalid_fixture(source)
    return loaded


def extract_fixture(path: Path, source: SourceSpec) -> ExtractedSource:
    loaded = _load_fixture(path, source)
    pages = loaded.get("pages")
    if (
        loaded.get("format") != "dnd-rules-extraction-fixture-v1"
        or not isinstance(pages, list)
        or not pages
    ):
        raise _invalid_fixture(source)

    assets: list[DraftAsset] = []
    current: DraftAsset | None = None
    chapter_stack: list[str] = []
    page_labels: list[str] = []
    total_text_characters = 0
    expected_page = 1

    for raw_page in pages:
        if not isinstance(raw_page, dict):
            raise _invalid_fixture(source)
        page_number = raw_page.get("number")
        page_label = raw_page.get("label")
        blocks = raw_page.get("blocks")
        if (
            type(page_number) is not int
            or page_number != expected_page
            or not isinstance(page_label, str)
            or not page_label
            or not isinstance(blocks, list)
        ):
            raise _invalid_fixture(source)
        expected_page += 1
        page_labels.append(page_label)

        for raw_block in blocks:
            if not isinstance(raw_block, dict):
                raise _invalid_fixture(source)
            if raw_block.get("kind") == "heading":
                level = raw_block.get("level")
                title = raw_block.get("title")
                category = raw_block.get("category", "semantic_section")
                if (
                    type(level) is not int
                    or not 1 <= level <= 6
                    or not isinstance(title, str)
                    or not title
                    or not isinstance(category, str)
                    or not _CATEGORY_PATTERN.fullmatch(category)
                ):
                    raise _invalid_fixture(source)
                rule_status = raw_block.get("rule_status", "default")
                if rule_status not in _RULE_STATUSES:
                    raise _invalid_fixture(source)
                aliases = raw_block.get("aliases", [])
                references = raw_block.get("references", [])
                parsed_aliases = _string_list(aliases, source)
                parsed_references = _string_list(references, source)
                chapter_stack = chapter_stack[: level - 1]
                chapter_stack.append(title)
                current = DraftAsset(
                    source=source,
                    title=title,
                    category=category,
                    aliases=tuple(dict.fromkeys((title, *parsed_aliases))),
                    chapter_path=tuple(chapter_stack),
                    rule_status=str(rule_status),
                    activation_condition=str(
                        raw_block.get(
                            "activation_condition",
                            "三宝书规则基线适用且没有更具体规则覆盖。",
                        )
                    ),
                    explicit_references=parsed_references,
                    order=len(assets),
                )
                current.pages.append(page_number)
                current.page_labels.append(page_label)
                assets.append(current)
                continue

            if current is None:
                raise _invalid_fixture(source)
            rendered = _render_content_block(raw_block, source)
            current.append_body(rendered, page_number, page_label)
            total_text_characters += len(rendered)

    if not assets or any(not asset.body_parts for asset in assets):
        raise _invalid_fixture(source)
    return ExtractedSource(
        source=source,
        assets=tuple(assets),
        page_count=len(pages),
        outline_count=0,
        total_text_characters=total_text_characters,
        page_labels=tuple(page_labels),
    )
