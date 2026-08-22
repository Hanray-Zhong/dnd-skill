from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any, cast

from dnd_5e.errors import FacadeError


_MANIFEST_IDENTITY_KEYS = (
    "build_tool_version",
    "normalizer_version",
    "parser_versions",
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
_AUTHORITATIVE_RULE_STATUSES = {"default", "conditional", "optional"}
_KNOWN_EXTRACTION_STATUSES = {"verified", "index_only"}
_METADATA_HASHES = {
    "index_sha256": "index.json",
    "sources_sha256": "sources.json",
    "coverage_sha256": "coverage.json",
    "blocked_sha256": "blocked.json",
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
            contents = {
                filename: (resolved_root / filename).read_bytes()
                for filename in ("index.json", "sources.json", "coverage.json", "blocked.json")
            }
            manifest_content = (resolved_root / "library.json").read_bytes()
        except OSError as error:
            raise _invalid_library() from error
        manifest = _load_json_object(manifest_content)
        index = _load_json_object(contents["index.json"])
        sources = _load_json_object(contents["sources.json"])
        coverage = _load_json_object(contents["coverage.json"])
        blocked = _load_json_object(contents["blocked.json"])
        self._validate_manifest(manifest, contents)
        self._validate_supporting_manifests(sources, coverage, blocked)
        self._items = self._validate_index(index, manifest)
        self._validate_coverage(coverage, self._items)
        self._version = str(manifest["library_version"])
        self._sha256 = str(manifest["library_sha256"])

    @staticmethod
    def _validate_manifest(
        manifest: dict[str, Any],
        contents: dict[str, bytes],
    ) -> None:
        distribution = manifest.get("distribution")
        parser_versions = manifest.get("parser_versions")
        if (
            manifest.get("format") != "dnd-rules-library-v1"
            or not isinstance(manifest.get("library_version"), str)
            or not isinstance(manifest.get("library_sha256"), str)
            or not all(key in manifest for key in _MANIFEST_IDENTITY_KEYS)
            or not isinstance(distribution, dict)
            or distribution.get("content_quality") != "passed"
            or distribution.get("local_preview") != "available"
            or not isinstance(parser_versions, dict)
            or not parser_versions
            or not all(
                isinstance(name, str)
                and name
                and isinstance(version, str)
                and version
                for name, version in parser_versions.items()
            )
            or any(
                manifest.get(hash_key) != _sha256(contents[filename])
                for hash_key, filename in _METADATA_HASHES.items()
            )
        ):
            raise _invalid_library()
        identity = {key: manifest[key] for key in _MANIFEST_IDENTITY_KEYS}
        if _sha256(_canonical_json(identity)) != manifest["library_sha256"]:
            raise _invalid_library()

    @staticmethod
    def _validate_supporting_manifests(
        sources: dict[str, Any],
        coverage: dict[str, Any],
        blocked: dict[str, Any],
    ) -> None:
        if (
            sources.get("format") != "dnd-rules-sources-v1"
            or not isinstance(sources.get("items"), list)
            or coverage.get("format") != "dnd-rules-leaf-coverage-v1"
            or not isinstance(coverage.get("items"), list)
            or blocked.get("format") != "dnd-rules-blocked-v1"
            or blocked.get("items") != []
        ):
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
            cross_references = raw_item.get("cross_references")
            referenced_by = raw_item.get("referenced_by")
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
                or raw_item.get("rule_status") not in _AUTHORITATIVE_RULE_STATUSES
                or raw_item.get("extraction_status") not in _KNOWN_EXTRACTION_STATUSES
                or not isinstance(cross_references, list)
                or not all(isinstance(reference, str) for reference in cross_references)
                or not isinstance(referenced_by, list)
                or not all(isinstance(reference, str) for reference in referenced_by)
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
        by_id = {str(item["id"]): item for item in items}
        for asset_id, item in by_id.items():
            references = cast(list[str], item["cross_references"])
            backlinks = cast(list[str], item["referenced_by"])
            if any(
                reference not in by_id
                or asset_id
                not in cast(list[str], by_id[reference]["referenced_by"])
                for reference in references
            ) or any(
                backlink not in by_id
                or asset_id
                not in cast(list[str], by_id[backlink]["cross_references"])
                for backlink in backlinks
            ):
                raise _invalid_library()
        category_counts = dict(
            sorted(Counter(str(item["category"]) for item in items).items())
        )
        if category_counts != manifest.get("category_counts"):
            raise _invalid_library()
        return tuple(items)

    @staticmethod
    def _validate_coverage(
        coverage: dict[str, Any],
        items: tuple[dict[str, object], ...],
    ) -> None:
        raw_records = coverage.get("items")
        if not isinstance(raw_records, list):
            raise _invalid_library()
        asset_ids = {str(item["id"]) for item in items}
        covered: set[str] = set()
        for record in raw_records:
            if not isinstance(record, dict):
                raise _invalid_library()
            asset_id = record.get("asset_id")
            if (
                not isinstance(asset_id, str)
                or asset_id in covered
                or record.get("validation_status") != "已验证"
            ):
                raise _invalid_library()
            covered.add(asset_id)
        if covered != asset_ids:
            raise _invalid_library()

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
        authoritative_items = [
            item for item in self._items if item["extraction_status"] == "verified"
        ]
        if kind == "id":
            matches = [item for item in authoritative_items if item["id"] == value]
        elif kind == "alias":
            for item in authoritative_items:
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
            for item in authoritative_items:
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
