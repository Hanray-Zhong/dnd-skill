from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any

from tools.rules_library.errors import BuildError


_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class SourceSpec:
    source_id: str
    title: str
    version: str
    relative_path: str
    sha256: str
    source_format: str
    options: dict[str, object]


@dataclass(frozen=True)
class Baseline:
    library_version: str
    sources: tuple[SourceSpec, ...]


@dataclass(frozen=True)
class ValidatedSource:
    spec: SourceSpec
    path: Path


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        loaded: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise BuildError("invalid_baseline", "规则基线清单无效。") from error
    if not isinstance(loaded, dict):
        raise BuildError("invalid_baseline", "规则基线清单无效。")
    return loaded


def _required_string(mapping: dict[str, Any], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise BuildError("invalid_baseline", "规则基线清单无效。")
    return value


def load_baseline(path: Path) -> Baseline:
    loaded = _load_json_object(path)
    raw_sources = loaded.get("sources")
    if (
        loaded.get("format") != "dnd-rules-baseline-v1"
        or not isinstance(raw_sources, list)
        or not raw_sources
    ):
        raise BuildError("invalid_baseline", "规则基线清单无效。")

    sources: list[SourceSpec] = []
    source_ids: set[str] = set()
    for raw_source in raw_sources:
        if not isinstance(raw_source, dict):
            raise BuildError("invalid_baseline", "规则基线清单无效。")
        source_id = _required_string(raw_source, "id")
        relative_path = _required_string(raw_source, "path")
        source_hash = _required_string(raw_source, "sha256")
        pure_path = PurePosixPath(relative_path)
        if (
            source_id in source_ids
            or pure_path.is_absolute()
            or ".." in pure_path.parts
            or not _SHA256_PATTERN.fullmatch(source_hash)
        ):
            raise BuildError("invalid_baseline", "规则基线清单无效。")
        source_ids.add(source_id)
        known_keys = {"id", "title", "version", "path", "sha256", "format"}
        sources.append(
            SourceSpec(
                source_id=source_id,
                title=_required_string(raw_source, "title"),
                version=_required_string(raw_source, "version"),
                relative_path=relative_path,
                sha256=source_hash,
                source_format=_required_string(raw_source, "format"),
                options={
                    key: value
                    for key, value in raw_source.items()
                    if key not in known_keys
                },
            )
        )
    return Baseline(
        library_version=_required_string(loaded, "library_version"),
        sources=tuple(sources),
    )


def _file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as source_file:
        for chunk in iter(lambda: source_file.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def validate_sources(
    baseline: Baseline,
    reference_root: Path,
) -> tuple[ValidatedSource, ...]:
    try:
        resolved_root = reference_root.resolve(strict=True)
    except OSError as error:
        raise BuildError("reference_root_unavailable", "开发参考资料根目录不可用。") from error
    if not resolved_root.is_dir():
        raise BuildError("reference_root_unavailable", "开发参考资料根目录不可用。")

    validated: list[ValidatedSource] = []
    for spec in baseline.sources:
        requested_path = reference_root / PurePosixPath(spec.relative_path)
        try:
            resolved_path = requested_path.resolve(strict=True)
        except OSError as error:
            raise BuildError(
                "source_missing",
                "固定来源文件缺失。",
                spec.source_id,
                spec.relative_path,
            ) from error
        if (
            requested_path.is_symlink()
            or not resolved_path.is_relative_to(resolved_root)
            or not resolved_path.is_file()
        ):
            raise BuildError(
                "unsafe_source_path",
                "固定来源路径越出开发参考资料边界。",
                spec.source_id,
                spec.relative_path,
            )
        actual_hash = _file_sha256(resolved_path)
        if actual_hash != spec.sha256:
            raise BuildError(
                "source_hash_mismatch",
                "固定来源的 SHA-256 不匹配。",
                spec.source_id,
                spec.relative_path,
            )
        validated.append(ValidatedSource(spec=spec, path=resolved_path))
    return tuple(validated)
