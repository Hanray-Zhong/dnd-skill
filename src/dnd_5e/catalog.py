from __future__ import annotations

import hashlib
from importlib import metadata
from pathlib import Path
import re


SKILL_IDS = (
    "dnd-5e",
    "dnd-5e-campaign-start",
    "dnd-5e-module-import",
    "dnd-5e-rules",
    "dnd-5e-character",
    "dnd-5e-session",
    "dnd-5e-combat",
    "dnd-5e-scene",
    "dnd-5e-campaign-state",
    "dnd-5e-world",
    "dnd-5e-adventure",
)
PLAYER_FACADE_ID = "dnd-5e"
_DISTRIBUTION_NAME = "dnd-5e-skill-suite"
_INSTALLED_SKILLS_PATH = ("share", _DISTRIBUTION_NAME, "skills")
_NAME_PATTERN = re.compile(r"^name:\s*([^\s]+)\s*$", re.MULTILINE)


class SkillCatalogError(RuntimeError):
    """Skill 目录与固定公开清单不一致。"""


def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _repository_manifest_paths() -> dict[str, Path] | None:
    skills_root = repository_root() / "skills"
    if not skills_root.is_dir():
        return None
    return {
        path.parent.name: path
        for path in skills_root.glob("*/SKILL.md")
        if path.is_file()
    }


def _installed_manifest_paths() -> dict[str, Path]:
    try:
        distribution = metadata.distribution(_DISTRIBUTION_NAME)
    except metadata.PackageNotFoundError as error:
        raise SkillCatalogError("找不到已安装的 Skill manifest") from error

    manifest_paths: dict[str, Path] = {}
    for entry in distribution.files or ():
        parts = entry.parts
        for skill_id in SKILL_IDS:
            suffix = (*_INSTALLED_SKILLS_PATH, skill_id, "SKILL.md")
            if len(parts) >= len(suffix) and parts[-len(suffix) :] == suffix:
                manifest_paths[skill_id] = Path(str(distribution.locate_file(entry)))
    if not manifest_paths:
        packaged_skills = Path(__file__).resolve().parent / "skill_manifests"
        manifest_paths = {
            path.parent.name: path
            for path in packaged_skills.glob("*/SKILL.md")
            if path.is_file()
        }
    return manifest_paths


def skill_manifest_paths() -> dict[str, Path]:
    return _repository_manifest_paths() or _installed_manifest_paths()


def _validated_manifest_paths() -> dict[str, Path]:
    manifest_paths = skill_manifest_paths()
    discovered_ids = set(manifest_paths)
    expected_ids = set(SKILL_IDS)
    if discovered_ids != expected_ids:
        missing = sorted(expected_ids - discovered_ids)
        unexpected = sorted(discovered_ids - expected_ids)
        raise SkillCatalogError(
            f"Skill 清单不一致：缺少 {missing or '无'}；多出 {unexpected or '无'}"
        )

    for skill_id in SKILL_IDS:
        manifest_path = manifest_paths[skill_id]
        manifest = manifest_path.read_text(encoding="utf-8")
        match = _NAME_PATTERN.search(manifest)
        if match is None or match.group(1) != skill_id:
            raise SkillCatalogError(f"{manifest_path} 的 name 与目录标识不一致")
    return manifest_paths


def skill_suite_sha256() -> str:
    manifest_paths = _validated_manifest_paths()
    hasher = hashlib.sha256()
    hasher.update(b"dnd-5e-skill-suite-content-v1\0")
    content_paths = [
        (f"skills/{skill_id}/SKILL.md", manifest_paths[skill_id])
        for skill_id in SKILL_IDS
    ]
    runtime_root = Path(__file__).resolve().parent
    content_paths.extend(
        (f"runtime/{path.name}", path) for path in sorted(runtime_root.glob("*.py"))
    )
    for relative_path, content_path in content_paths:
        content = content_path.read_bytes()
        hasher.update(relative_path.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(len(content).to_bytes(8, byteorder="big"))
        hasher.update(content)
    return hasher.hexdigest()


def public_skill_catalog() -> list[dict[str, object]]:
    _validated_manifest_paths()

    return [
        {"id": skill_id, "player_facade": skill_id == PLAYER_FACADE_ID}
        for skill_id in SKILL_IDS
    ]
