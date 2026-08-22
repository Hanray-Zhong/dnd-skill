from __future__ import annotations

from dataclasses import dataclass, field

from tools.rules_library.baseline import SourceSpec


@dataclass
class DraftAsset:
    source: SourceSpec
    title: str
    category: str
    aliases: tuple[str, ...]
    chapter_path: tuple[str, ...]
    rule_status: str
    activation_condition: str
    explicit_references: tuple[str, ...]
    order: int
    pages: list[int] = field(default_factory=list)
    page_labels: list[str] = field(default_factory=list)
    body_parts: list[str] = field(default_factory=list)
    extraction_status: str = "verified"

    def append_body(self, body: str, page: int, page_label: str) -> None:
        self.body_parts.append(body)
        if page not in self.pages:
            self.pages.append(page)
            self.page_labels.append(page_label)


@dataclass(frozen=True)
class ExtractedSource:
    source: SourceSpec
    assets: tuple[DraftAsset, ...]
    page_count: int
    outline_count: int
    total_text_characters: int
    page_labels: tuple[str, ...]
