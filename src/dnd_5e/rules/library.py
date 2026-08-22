from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any

from dnd_5e.errors import FacadeError


_MANIFEST_IDENTITY_KEYS = (
    "build_tool_version",
    "normalizer_version",
    "sources_sha256",
    "index_sha256",
    "coverage_sha256",
    "blocked_sha256",
    "asset_count",
    "category_counts",
    "distribution",
)
_INDEX_ITEM_KEYS = {
    "id",
    "title",
    "category",
    "aliases",
    "activation_condition",
    "rule_status",
    "source",
    "chapter_path",
    "pages",
    "cross_references",
    "referenced_by",
    "extraction_status",
    "content_sha256",
    "file_sha256",
    "path",
}


def _invalid_library() -> FacadeError:
    return FacadeError(
        "invalid_rules_library",
        "规则章节库缺失、损坏或内容哈希不一致。",
    )


def _load_json_object(content: bytes) -> dict[str, Any]:
    try:
        loaded: object = json.loads(content.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise _invalid_library() from error
    if not isinstance(loaded, dict):
        raise _invalid_library()
    return loaded


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _normalized_lookup(value: str) -> str:
    return re.sub(r"[\W_]+", "", value, flags=re.UNICODE).casefold()


def default_library_root() -> Path:
    return Path(__file__).resolve().parents[1] / "rule_assets"


def installed_library_identity() -> dict[str, str]:
    library_root = default_library_root()
    if not library_root.exists():
        empty_library: dict[str, list[object]] = {
            "semantic_sections": [],
            "entities": [],
        }
        return {
            "version": "bootstrap-empty-v1",
            "sha256": _sha256(_canonical_json(empty_library)),
        }
    library = RulesLibrary(library_root)
    return {"version": library.version, "sha256": library.sha256}


class RulesLibrary:
    def __init__(self, root: Path | None = None) -> None:
        requested_root = root or default_library_root()
        try:
            resolved_root = requested_root.resolve(strict=True)
        except OSError as error:
            raise _invalid_library() from error
        if requested_root.is_symlink() or not resolved_root.is_dir():
            raise _invalid_library()
        self._root = resolved_root
        try:
            manifest_content = (resolved_root / "library.json").read_bytes()
            index_content = (resolved_root / "index.json").read_bytes()
        except OSError as error:
            raise _invalid_library() from error
        manifest = _load_json_object(manifest_content)
        index = _load_json_object(index_content)
        self._validate_manifest(manifest, index_content)
        self._items = self._validate_index(index, manifest)
        self._version = str(manifest["library_version"])
        self._sha256 = str(manifest["library_sha256"])

    @staticmethod
    def _validate_manifest(manifest: dict[str, Any], index_content: bytes) -> None:
        if (
            manifest.get("format") != "dnd-rules-library-v1"
            or not isinstance(manifest.get("library_version"), str)
            or not isinstance(manifest.get("library_sha256"), str)
            or not all(key in manifest for key in _MANIFEST_IDENTITY_KEYS)
            or manifest.get("index_sha256") != _sha256(index_content)
        ):
            raise _invalid_library()
        identity = {key: manifest[key] for key in _MANIFEST_IDENTITY_KEYS}
        if _sha256(_canonical_json(identity)) != manifest["library_sha256"]:
            raise _invalid_library()

    def _validate_index(
        self,
        index: dict[str, Any],
        manifest: dict[str, Any],
    ) -> tuple[dict[str, object], ...]:
        raw_items = index.get("items")
        if index.get("format") != "dnd-rules-index-v1" or not isinstance(
            raw_items, list
        ):
            raise _invalid_library()
        items: list[dict[str, object]] = []
        seen_ids: set[str] = set()
        for raw_item in raw_items:
            if not isinstance(raw_item, dict) or not _INDEX_ITEM_KEYS.issubset(raw_item):
                raise _invalid_library()
            asset_id = raw_item.get("id")
            aliases = raw_item.get("aliases")
            chapter_path = raw_item.get("chapter_path")
            relative_path = raw_item.get("path")
            if (
                not isinstance(asset_id, str)
                or not asset_id
                or asset_id in seen_ids
                or not isinstance(aliases, list)
                or not all(isinstance(alias, str) and alias for alias in aliases)
                or not isinstance(chapter_path, list)
                or not all(
                    isinstance(chapter, str) and chapter for chapter in chapter_path
                )
                or not isinstance(relative_path, str)
            ):
                raise _invalid_library()
            pure_path = PurePosixPath(relative_path)
            if pure_path.is_absolute() or ".." in pure_path.parts:
                raise _invalid_library()
            resolved_asset = (self._root / pure_path).resolve(strict=False)
            if not resolved_asset.is_relative_to(self._root):
                raise _invalid_library()
            seen_ids.add(asset_id)
            items.append(dict(raw_item))
        if len(items) != manifest.get("asset_count"):
            raise _invalid_library()
        return tuple(items)

    @property
    def version(self) -> str:
        return self._version

    @property
    def sha256(self) -> str:
        return self._sha256

    def _load_asset(self, item: dict[str, object]) -> dict[str, object]:
        relative_path = item["path"]
        expected_hash = item["file_sha256"]
        if not isinstance(relative_path, str) or not isinstance(expected_hash, str):
            raise _invalid_library()
        asset_path = self._root / PurePosixPath(relative_path)
        try:
            if asset_path.is_symlink() or not asset_path.is_file():
                raise _invalid_library()
            content = asset_path.read_bytes()
        except OSError as error:
            raise _invalid_library() from error
        if _sha256(content) != expected_hash:
            raise _invalid_library()
        try:
            markdown = content.decode("utf-8")
        except UnicodeError as error:
            raise _invalid_library() from error
        result = {
            key: value
            for key, value in item.items()
            if key not in {"path", "file_sha256"}
        }
        result["conclusion_markdown"] = markdown
        return result

    def query(
        self,
        *,
        kind: str,
        value: str,
        limit: int = 20,
    ) -> list[dict[str, object]]:
        normalized_value = _normalized_lookup(value)
        matches: list[dict[str, object]] = []
        if kind == "id":
            matches = [item for item in self._items if item["id"] == value]
        elif kind == "alias":
            for item in self._items:
                aliases = item["aliases"]
                if not isinstance(aliases, list):
                    raise _invalid_library()
                if any(
                    isinstance(alias, str)
                    and _normalized_lookup(alias) == normalized_value
                    for alias in aliases
                ):
                    matches.append(item)
        elif kind == "topic":
            for item in self._items:
                title = item["title"]
                aliases = item["aliases"]
                chapter_path = item["chapter_path"]
                if (
                    not isinstance(title, str)
                    or not isinstance(aliases, list)
                    or not isinstance(chapter_path, list)
                ):
                    raise _invalid_library()
                searchable_values = [title, *aliases, *chapter_path]
                if any(
                    isinstance(candidate, str)
                    and normalized_value in _normalized_lookup(candidate)
                    for candidate in searchable_values
                ):
                    matches.append(item)
        else:
            raise AssertionError(f"未知查询类型：{kind}")
        matches.sort(key=lambda item: str(item["id"]))
        selected = matches[:limit]
        if not selected:
            raise FacadeError("rule_not_found", "规则章节库中没有匹配项。")
        return [self._load_asset(item) for item in selected]
