from __future__ import annotations

from pathlib import Path
from typing import Any
import unittest

from tools.rules_library.baseline import SourceSpec, load_baseline
from tools.rules_library.pdf_extractor import _detected_markers
from tools.rules_library.pdf_layout import LayoutLine, extract_page_lines


class _FakeTable:
    bbox = (50.0, 100.0, 290.0, 180.0)

    def extract(self) -> list[list[str]]:
        return [["护甲", "护甲等级", "力量"], ["兽皮甲", "14 (最大 2)", "-"]]


class _FakePage:
    width = 600.0
    height = 800.0
    rects = [
        {
            "x0": 310.0,
            "x1": 550.0,
            "top": 100.0,
            "bottom": 180.0,
            "width": 240.0,
            "height": 80.0,
            "fill": True,
            "non_stroking_color": (0.8, 0.8, 0.8),
        }
    ]

    def dedupe_chars(self, **_options: object) -> _FakePage:
        return self

    def extract_words(self, **_options: object) -> list[dict[str, object]]:
        return [
            _word("自有规则", 55, 50, 12, "Fixture-Bold"),
            _word("护甲表", 60, 76, 9.5, "Fixture-Bold"),
            _word("护甲", 60, 110, 8, "Fixture-Regular"),
            _word("护甲等级", 130, 110, 8, "Fixture-Regular"),
            _word("力量", 220, 110, 8, "Fixture-Regular"),
            _word("兽皮甲", 60, 140, 8, "Fixture-Regular"),
            _word("14", 130, 140, 8, "Fixture-Regular"),
            _word("(最大", 160, 140, 8, "Fixture-Regular"),
            _word("2)", 195, 140, 8, "Fixture-Regular"),
            _word("-", 220, 140, 8, "Fixture-Regular"),
            _word("普通正文", 55, 240, 9, "Fixture-Regular"),
            _word("侧栏标题", 320, 110, 9, "Fixture-Bold"),
            _word("仅在启用时适用。", 320, 140, 8, "Fixture-Regular"),
            _word("1. 脚注保留例外。", 55, 735, 6, "Fixture-Regular"),
        ]

    def find_tables(self) -> list[Any]:
        return [_FakeTable()]


class _BoxTable:
    def __init__(self, bbox: tuple[float, float, float, float]) -> None:
        self.bbox = bbox


class _SplitTablePage(_FakePage):
    rects: list[dict[str, object]] = [
        {
            "x0": 50.0,
            "x1": 290.0,
            "top": 45.0,
            "bottom": 230.0,
            "width": 240.0,
            "height": 185.0,
            "fill": True,
        }
    ]

    def extract_words(self, **_options: object) -> list[dict[str, object]]:
        return [
            _word("变体说明", 60, 52, 8, "Fixture-Bold"),
            _word("表格适用时保留侧栏。", 60, 64, 8, "Fixture-Regular"),
            _word("d100", 60, 80, 8, "Fixture-Bold"),
            _word("效应", 130, 80, 8, "Fixture-Bold"),
            _word("01", 60, 105, 8, "Fixture-Regular"),
            _word("第一段规则", 130, 105, 8, "Fixture-Regular"),
            _word("同一单元格续行", 130, 140, 8, "Fixture-Regular"),
            _word("31~40", 60, 175, 8, "Fixture-Regular"),
            _word("第二段规则", 130, 175, 8, "Fixture-Regular"),
            _word("尾行继续", 130, 210, 8, "Fixture-Regular"),
        ]

    def find_tables(self) -> list[Any]:
        return [
            _BoxTable((50, 100, 290, 120)),
            _BoxTable((50, 170, 290, 190)),
        ]


class _UnrenderableTablePage(_FakePage):
    rects: list[dict[str, object]] = []

    def extract_words(self, **_options: object) -> list[dict[str, object]]:
        return [_word("只有一格", 60, 110, 8, "Fixture-Regular")]

    def find_tables(self) -> list[Any]:
        return [_BoxTable((50, 100, 290, 130))]


class _HeaderBoundaryPage(_FakePage):
    rects: list[dict[str, object]] = []

    def extract_words(self, **_options: object) -> list[dict[str, object]]:
        return [
            _word("10", 60, 72, 8, "Fixture-Regular"),
            _word("60", 150, 72, 8, "Fixture-Regular"),
            _word("色彩", 60, 86, 8, "Fixture-Bold"),
            _word("伤害抗性", 150, 86, 8, "Fixture-Bold"),
            _word("黑、红铜", 60, 110, 8, "Fixture-Regular"),
            _word("强酸", 150, 110, 8, "Fixture-Regular"),
        ]

    def find_tables(self) -> list[Any]:
        return [_BoxTable((50, 100, 290, 130))]


class _OffsetFontPage(_FakePage):
    rects: list[dict[str, object]] = []

    def extract_words(self, **_options: object) -> list[dict[str, object]]:
        return [
            _word("半龙获得", 60, 100, 8, "Fixture-Regular"),
            _word("10", 130, 120, 8, "Fixture-Number"),
            _word("尺盲视与", 150, 100, 8, "Fixture-Regular"),
            _word("60", 220, 120, 8, "Fixture-Number"),
            _word("尺黑暗视觉。", 240, 100, 8, "Fixture-Regular"),
        ]

    def find_tables(self) -> list[Any]:
        return []


class _OffsetFontSidebarPage(_OffsetFontPage):
    rects: list[dict[str, object]] = [
        {
            "x0": 50.0,
            "x1": 264.99,
            "top": 80.0,
            "bottom": 135.0,
            "width": 214.99,
            "height": 55.0,
            "fill": True,
        }
    ]

    def extract_words(self, **options: object) -> list[dict[str, object]]:
        return [
            *super().extract_words(**options),
            _word("1", 560, 760, 8, "Fixture-Number"),
        ]


class _DrowOffsetFontPage(_OffsetFontPage):
    def extract_words(self, **_options: object) -> list[dict[str, object]]:
        return [
            _word("在阳光下暴露超过", 60, 100, 8.4, "Fixture-Regular"),
            _word("1", 150, 118.12, 8.4, "ERSTMY+Cambria4"),
            _word("小时后将永久消失。", 160, 100, 8.4, "Fixture-Regular"),
        ]


def _word(
    text: str,
    x0: float,
    top: float,
    size: float,
    font: str,
) -> dict[str, Any]:
    return {
        "text": text,
        "x0": x0,
        "x1": x0 + 50,
        "top": top,
        "bottom": top + size,
        "size": size,
        "fontname": font,
    }


class PdfStructureExtractionTests(unittest.TestCase):
    def test_real_pdf_adapter_preserves_table_sidebar_and_footnote_semantics(
        self,
    ) -> None:
        lines = extract_page_lines(
            _FakePage(),
            page_number=1,
            page_label="1",
            first_index=0,
            cid_maps={},
        )
        by_kind = {
            kind: [line.rendered_text for line in lines if line.block_kind == kind]
            for kind in {line.block_kind for line in lines}
        }

        self.assertIn("| 护甲 | 护甲等级 | 力量 |", by_kind["table"][0])
        self.assertIn("| 兽皮甲 | 14 (最大 2) | - |", by_kind["table"][0])
        self.assertIn("**护甲表**", by_kind["table"][0])
        self.assertEqual(
            ["> 侧栏标题", "> 仅在启用时适用。"],
            by_kind["sidebar"],
        )
        self.assertEqual(
            ["[^pdf-p1-n1]: 1. 脚注保留例外。"],
            by_kind["footnote"],
        )
        self.assertIn("普通正文", by_kind["paragraph"])

    def test_split_table_zones_keep_continuation_rows_in_one_table(self) -> None:
        lines = extract_page_lines(
            _SplitTablePage(),
            page_number=1,
            page_label="1",
            first_index=0,
            cid_maps={},
        )
        tables = [line.rendered_text for line in lines if line.block_kind == "table"]

        self.assertEqual(1, len(tables))
        self.assertIn("|  | 同一单元格续行 |", tables[0])
        self.assertIn("| 31~40 | 第二段规则 |", tables[0])
        self.assertIn("|  | 尾行继续 |", tables[0])
        self.assertEqual(1, tables[0].count("| --- | --- |"))
        self.assertEqual(
            ["> 变体说明", "> 表格适用时保留侧栏。"],
            [line.rendered_text for line in lines if line.block_kind == "sidebar"],
        )

    def test_detected_but_unrenderable_table_fails_instead_of_downgrading(self) -> None:
        with self.assertRaisesRegex(ValueError, "表格"):
            extract_page_lines(
                _UnrenderableTablePage(),
                page_number=1,
                page_label="1",
                first_index=0,
                cid_maps={},
            )

    def test_table_top_extension_keeps_preceding_numbers_out_of_header(self) -> None:
        lines = extract_page_lines(
            _HeaderBoundaryPage(),
            page_number=1,
            page_label="1",
            first_index=0,
            cid_maps={},
        )
        table = next(line.rendered_text for line in lines if line.block_kind == "table")

        self.assertIn("| 色彩 | 伤害抗性 |", table)
        self.assertIn("| 黑、红铜 | 强酸 |", table)
        self.assertNotIn("| 10 | 60 |", table)
        self.assertIn(
            "10 60",
            [line.rendered_text for line in lines if line.block_kind == "paragraph"],
        )

    def test_fixed_font_top_adjustment_restores_visual_reading_line(self) -> None:
        lines = extract_page_lines(
            _OffsetFontPage(),
            page_number=1,
            page_label="1",
            first_index=0,
            cid_maps={},
            font_top_adjustments={"fixture-number": -20},
        )

        self.assertIn(
            "半龙获得 10 尺盲视与 60 尺黑暗视觉。",
            [line.rendered_text for line in lines],
        )

    def test_adjusted_words_keep_sidebar_membership_and_footer_is_removed(self) -> None:
        lines = extract_page_lines(
            _OffsetFontSidebarPage(),
            page_number=1,
            page_label="1",
            first_index=0,
            cid_maps={},
            font_top_adjustments={"fixture-number": -20},
        )

        self.assertEqual(
            ["> 半龙获得 10 尺盲视与 60 尺黑暗视觉。"],
            [line.rendered_text for line in lines],
        )

    def test_mm_baseline_restores_drow_numeric_font_to_visual_line(self) -> None:
        baseline = load_baseline(
            Path(__file__).parents[1]
            / "tools"
            / "rules_library"
            / "core-cn-baseline.json"
        )
        mm_source = next(
            source for source in baseline.sources if source.source_id == "mm-cn-1.3.2"
        )
        raw_adjustments = mm_source.options["font_top_adjustments"]
        if not isinstance(raw_adjustments, dict):
            self.fail("MM 规则基线缺少字体纵向偏移映射")
        adjustments = {
            str(font).casefold(): float(offset)
            for font, offset in raw_adjustments.items()
        }

        lines = extract_page_lines(
            _DrowOffsetFontPage(),
            page_number=1,
            page_label="1",
            first_index=0,
            cid_maps={},
            font_top_adjustments=adjustments,
        )

        self.assertIn(
            "在阳光下暴露超过 1 小时后将永久消失。",
            [line.rendered_text for line in lines],
        )

    def test_multiline_sidebar_heading_forms_one_complete_monster_marker(self) -> None:
        source = SourceSpec(
            source_id="mm",
            title="自有怪物资料",
            version="1",
            relative_path="fixture.pdf",
            sha256="0" * 64,
            source_format="pdf",
            options={
                "left_margin": 55,
                "right_margin": 309,
                "margin_tolerance": 12,
                "minimum_heading_size": 9.5,
            },
        )
        lines = [
            _layout_line(0, 100, "兽人 · 格乌什之眼 Orc Eye of", 14, True),
            _layout_line(1, 123, "Gruumsh", 14, True),
            _layout_line(2, 150, "AC：16", 8, False),
        ]

        markers = _detected_markers(lines, source)

        self.assertEqual(1, len(markers))
        self.assertEqual("兽人 · 格乌什之眼 Orc Eye of Gruumsh", markers[0].title)
        self.assertEqual(
            ("兽人 · 格乌什之眼 Orc Eye of Gruumsh",),
            markers[0].chapter_path,
        )


def _layout_line(
    index: int,
    top: float,
    text: str,
    size: float,
    bold: bool,
) -> LayoutLine:
    return LayoutLine(
        index=index,
        page=1,
        page_label="1",
        column=0,
        top=top,
        x0=55,
        size=size,
        fonts=("Fixture-Bold" if bold else "Fixture-Regular",),
        text=text,
        block_kind="sidebar",
        rendered_text=f"> {text}",
        structure_group="p1-sidebar-1",
        is_colored=bold,
    )


if __name__ == "__main__":
    unittest.main()
