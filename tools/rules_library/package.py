from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import tempfile
import zipfile
from typing import Any

from dnd_5e import __version__
from dnd_5e.catalog import SKILL_IDS
from dnd_5e.rules import RulesLibrary
from tools.rules_library.errors import BuildError


_DISTRIBUTION_NAME = "dnd_5e_skill_suite"
_DIST_INFO = f"{_DISTRIBUTION_NAME}-{__version__}.dist-info"
_DATA_ROOT = f"{_DISTRIBUTION_NAME}-{__version__}.data/data"
_WHEEL_NAME = f"{_DISTRIBUTION_NAME}-{__version__}-py3-none-any.whl"


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_json(path: Path) -> dict[str, Any]:
    try:
        loaded: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise BuildError("invalid_rules_library", "规则章节库无法打包。") from error
    if not isinstance(loaded, dict):
        raise BuildError("invalid_rules_library", "规则章节库无法打包。")
    return loaded


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _validated_library_files(library_root: Path) -> tuple[dict[str, Any], dict[str, bytes]]:
    library = RulesLibrary(library_root)
    resolved_root = library_root.resolve(strict=True)
    manifest = _load_json(resolved_root / "library.json")
    index = _load_json(resolved_root / "index.json")
    distribution = manifest.get("distribution")
    if (
        not isinstance(distribution, dict)
        or distribution.get("content_quality") != "passed"
        or distribution.get("local_preview") != "available"
    ):
        raise BuildError("local_preview_blocked", "规则章节库尚不能生成本地预览包。")
    raw_items = index.get("items")
    if not isinstance(raw_items, list):
        raise BuildError("invalid_rules_library", "规则章节库无法打包。")

    library_contents: dict[str, bytes] = {}
    for path in sorted(item for item in resolved_root.rglob("*") if item.is_file()):
        if path.is_symlink():
            raise BuildError("invalid_rules_library", "规则章节库无法打包。")
        relative_path = path.relative_to(resolved_root).as_posix()
        library_contents[relative_path] = path.read_bytes()
    expected_paths = {
        "library.json",
        "index.json",
        "sources.json",
        "coverage.json",
        "blocked.json",
    }
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            raise BuildError("invalid_rules_library", "规则章节库无法打包。")
        asset_relative_path = raw_item.get("path")
        expected_hash = raw_item.get("file_sha256")
        if not isinstance(asset_relative_path, str) or not isinstance(
            expected_hash, str
        ):
            raise BuildError("invalid_rules_library", "规则章节库无法打包。")
        pure_path = PurePosixPath(asset_relative_path)
        if pure_path.is_absolute() or ".." in pure_path.parts:
            raise BuildError("invalid_rules_library", "规则章节库无法打包。")
        expected_paths.add(asset_relative_path)
        content = library_contents.get(asset_relative_path)
        if content is None or _sha256(content) != expected_hash:
            raise BuildError("invalid_rules_library", "规则章节库无法打包。")
    if set(library_contents) != expected_paths:
        raise BuildError("invalid_rules_library", "规则章节库包含未列入清单的文件。")
    for manifest_key, relative_path in (
        ("index_sha256", "index.json"),
        ("sources_sha256", "sources.json"),
        ("coverage_sha256", "coverage.json"),
        ("blocked_sha256", "blocked.json"),
    ):
        if manifest.get(manifest_key) != _sha256(library_contents[relative_path]):
            raise BuildError("invalid_rules_library", "规则章节库清单哈希不一致。")
    files = {
        f"dnd_5e/rule_assets/{relative_path}": content
        for relative_path, content in library_contents.items()
    }
    return manifest, files


def _runtime_files() -> dict[str, bytes]:
    repository_root = _repository_root()
    package_root = repository_root / "src" / "dnd_5e"
    files = {
        path.relative_to(package_root.parent).as_posix(): path.read_bytes()
        for path in sorted(package_root.rglob("*.py"))
        if path.is_file()
    }
    for skill_id in SKILL_IDS:
        manifest = repository_root / "skills" / skill_id / "SKILL.md"
        if not manifest.is_file():
            raise BuildError("package_source_missing", "本地预览包缺少 Skill manifest。")
        archive_path = (
            f"{_DATA_ROOT}/share/dnd-5e-skill-suite/skills/{skill_id}/SKILL.md"
        )
        manifest_content = manifest.read_bytes()
        files[archive_path] = manifest_content
        files[f"dnd_5e/skill_manifests/{skill_id}/SKILL.md"] = manifest_content
    return files


def _metadata_files() -> dict[str, bytes]:
    metadata = (
        "Metadata-Version: 2.4\n"
        "Name: dnd-5e-skill-suite\n"
        f"Version: {__version__}\n"
        "Summary: 本地优先的 D&D 5E 跑团 Skill Suite\n"
        "Requires-Python: >=3.11\n"
        "\n"
    ).encode("utf-8")
    wheel = (
        "Wheel-Version: 1.0\n"
        "Generator: dnd-rules-local-preview-v1\n"
        "Root-Is-Purelib: true\n"
        "Tag: py3-none-any\n"
        "\n"
    ).encode("utf-8")
    entry_points = (
        "[console_scripts]\n"
        "dnd-5e = dnd_5e.cli:main\n"
    ).encode("utf-8")
    return {
        f"{_DIST_INFO}/METADATA": metadata,
        f"{_DIST_INFO}/WHEEL": wheel,
        f"{_DIST_INFO}/entry_points.txt": entry_points,
    }


def _record_hash(content: bytes) -> str:
    digest = hashlib.sha256(content).digest()
    encoded = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return f"sha256={encoded}"


def _record(entries: dict[str, bytes]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    for path, content in sorted(entries.items()):
        writer.writerow((path, _record_hash(content), len(content)))
    writer.writerow((f"{_DIST_INFO}/RECORD", "", ""))
    return output.getvalue().encode("utf-8")


def _write_wheel(path: Path, entries: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, mode="w", compression=zipfile.ZIP_DEFLATED) as wheel:
        for archive_path, content in sorted(entries.items()):
            info = zipfile.ZipInfo(archive_path, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            wheel.writestr(info, content)


def build_preview_wheel(
    *,
    library_root: Path,
    output_directory: Path,
) -> dict[str, object]:
    manifest, entries = _validated_library_files(library_root)
    entries.update(_runtime_files())
    entries.update(_metadata_files())
    entries[f"{_DIST_INFO}/RECORD"] = _record(entries)
    output_directory.mkdir(parents=True, exist_ok=True)
    wheel_path = output_directory / _WHEEL_NAME
    if wheel_path.exists():
        raise BuildError("package_output_exists", "本地预览 wheel 已存在。")
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=output_directory,
            prefix=".preview-wheel-",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
        _write_wheel(temporary_path, entries)
        os.replace(temporary_path, wheel_path)
    except OSError as error:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise BuildError("package_write_failed", "本地预览 wheel 写入失败。") from error
    return {
        "ok": True,
        "wheel": wheel_path.name,
        "library_version": manifest["library_version"],
        "asset_count": manifest["asset_count"],
    }
