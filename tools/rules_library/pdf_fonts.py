from __future__ import annotations

import hashlib
import importlib
import re
import struct
from typing import Any, Callable

from tools.rules_library.baseline import SourceSpec
from tools.rules_library.errors import BuildError


def _font_family(base_font: str) -> str:
    name = base_font.lstrip("/").split("+", 1)[-1]
    return re.sub(r"\d+$", "", name).casefold()


def _table_directory(font_data: bytes) -> dict[str, tuple[int, int]]:
    if len(font_data) < 12:
        return {}
    table_count = struct.unpack_from(">H", font_data, 4)[0]
    tables: dict[str, tuple[int, int]] = {}
    for index in range(table_count):
        record_offset = 12 + index * 16
        if record_offset + 16 > len(font_data):
            return {}
        tag, _checksum, offset, length = struct.unpack_from(
            ">4sIII", font_data, record_offset
        )
        tables[tag.decode("latin-1")] = (offset, length)
    return tables


def _glyph_fingerprints(font_data: bytes) -> dict[int, str]:
    tables = _table_directory(font_data)
    if not {"head", "loca", "glyf", "maxp"}.issubset(tables):
        return {}
    head_offset = tables["head"][0]
    loca_offset = tables["loca"][0]
    glyf_offset = tables["glyf"][0]
    maxp_offset = tables["maxp"][0]
    if head_offset + 52 > len(font_data) or maxp_offset + 6 > len(font_data):
        return {}
    location_format = struct.unpack_from(">h", font_data, head_offset + 50)[0]
    glyph_count = struct.unpack_from(">H", font_data, maxp_offset + 4)[0]
    locations: list[int] = []
    for glyph_id in range(glyph_count + 1):
        entry_offset = loca_offset + glyph_id * (2 if location_format == 0 else 4)
        if location_format == 0:
            if entry_offset + 2 > len(font_data):
                return {}
            location = struct.unpack_from(">H", font_data, entry_offset)[0] * 2
        else:
            if entry_offset + 4 > len(font_data):
                return {}
            location = struct.unpack_from(">I", font_data, entry_offset)[0]
        locations.append(location)
    fingerprints: dict[int, str] = {}
    for glyph_id in range(glyph_count):
        start = glyf_offset + locations[glyph_id]
        end = glyf_offset + locations[glyph_id + 1]
        if 0 <= start < end <= len(font_data):
            fingerprints[glyph_id] = hashlib.sha256(font_data[start:end]).hexdigest()
    return fingerprints


def _font_components(font: Any) -> tuple[dict[int, str], Callable[[int], int]]:
    descendants = font.get("/DescendantFonts")
    if not descendants:
        return {}, lambda cid: cid
    descendant = descendants[0].get_object()
    descriptor = descendant.get("/FontDescriptor")
    if descriptor is None:
        return {}, lambda cid: cid
    font_file = descriptor.get_object().get("/FontFile2")
    if font_file is None:
        return {}, lambda cid: cid
    font_data = font_file.get_object().get_data()
    fingerprints = _glyph_fingerprints(font_data)
    cid_to_gid = descendant.get("/CIDToGIDMap")
    if str(cid_to_gid) == "/Identity" or cid_to_gid is None:
        return fingerprints, lambda cid: cid
    mapping_data = cid_to_gid.get_object().get_data()

    def mapped_gid(cid: int) -> int:
        offset = cid * 2
        if offset + 2 > len(mapping_data):
            return 0
        return int(struct.unpack_from(">H", mapping_data, offset)[0])

    return fingerprints, mapped_gid


def _source_code(value: object) -> int | None:
    if not isinstance(value, str) or not value:
        return None
    if len(value) == 1:
        return ord(value)
    try:
        return int.from_bytes(value.encode("latin-1"), byteorder="big")
    except UnicodeEncodeError:
        return None


def recover_cid_maps(reader: Any, source: SourceSpec) -> dict[str, dict[int, str]]:
    try:
        cmap_module = importlib.import_module("pypdf._cmap")
        parse_to_unicode = cmap_module._parse_to_unicode
    except (ModuleNotFoundError, AttributeError) as error:
        raise BuildError(
            "missing_build_dependency",
            "PDF 字形恢复需要兼容的 pypdf 构建依赖。",
            source.source_id,
            source.relative_path,
        ) from error

    fonts: dict[tuple[str, int], Any] = {}
    for page in reader.pages:
        resources = page.get("/Resources", {})
        for reference in resources.get("/Font", {}).values():
            font = reference.get_object()
            base_font = str(font.get("/BaseFont", ""))
            reference_id = int(getattr(reference, "idnum", id(reference)))
            fonts[(base_font, reference_id)] = font

    font_components: dict[tuple[str, int], tuple[dict[int, str], Callable[[int], int]]] = {}
    known_by_family: dict[str, dict[str, set[str]]] = {}
    missing: list[tuple[str, tuple[str, int], Any]] = []
    for identity, font in fonts.items():
        base_font = identity[0]
        components = _font_components(font)
        font_components[identity] = components
        if "/ToUnicode" not in font:
            missing.append((base_font, identity, font))
            continue
        mapping, _entries = parse_to_unicode(font)
        fingerprints, cid_to_gid = components
        family_map = known_by_family.setdefault(_font_family(base_font), {})
        for raw_code, unicode_text in mapping.items():
            source_code = _source_code(raw_code)
            if (
                source_code is None
                or not isinstance(unicode_text, str)
                or len(unicode_text) != 1
            ):
                continue
            fingerprint = fingerprints.get(cid_to_gid(source_code))
            if fingerprint is not None:
                family_map.setdefault(fingerprint, set()).add(unicode_text)

    recovered: dict[str, dict[int, str]] = {}
    for base_font, identity, _font in missing:
        fingerprints, cid_to_gid = font_components[identity]
        family_map = known_by_family.get(_font_family(base_font), {})
        cid_mapping: dict[int, str] = {}
        for cid in range(65536):
            glyph_id = cid_to_gid(cid)
            if glyph_id == 0 and cid > 255:
                break
            fingerprint = fingerprints.get(glyph_id)
            candidates = family_map.get(fingerprint, set()) if fingerprint else set()
            if len(candidates) == 1:
                cid_mapping[cid] = next(iter(candidates))
        if cid_mapping:
            recovered[base_font.lstrip("/")] = cid_mapping
    raw_overrides = source.options.get("cid_overrides", {})
    if not isinstance(raw_overrides, dict):
        raise BuildError("invalid_baseline", "规则基线清单无效。")
    for font_name, raw_mapping in raw_overrides.items():
        if not isinstance(font_name, str) or not isinstance(raw_mapping, dict):
            raise BuildError("invalid_baseline", "规则基线清单无效。")
        target = recovered.setdefault(font_name, {})
        for raw_cid, character in raw_mapping.items():
            if (
                not isinstance(raw_cid, str)
                or not raw_cid.isdecimal()
                or not isinstance(character, str)
                or len(character) != 1
            ):
                raise BuildError("invalid_baseline", "规则基线清单无效。")
            cid = int(raw_cid)
            if cid in target and target[cid] != character:
                raise BuildError(
                    "conflicting_glyph_mapping",
                    "PDF 字形轮廓映射与复核映射冲突。",
                    source.source_id,
                    source.relative_path,
                )
            target[cid] = character
    return recovered


def replace_cid_placeholders(
    text: str,
    font_name: str,
    cid_maps: dict[str, dict[int, str]],
) -> str:
    mapping = cid_maps.get(font_name)
    if mapping is None or "(cid:" not in text:
        return text

    def replacement(match: re.Match[str]) -> str:
        cid = int(match.group(1))
        return mapping.get(cid, match.group(0))

    return re.sub(r"\(cid:(\d+)\)", replacement, text)
