from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import uuid

from dnd_5e import __version__
from dnd_5e.catalog import skill_suite_sha256
from dnd_5e.errors import FacadeError
from dnd_5e.state_store import (
    CampaignSummary,
    STATE_APPLICATION_ID,
    STATE_SCHEMA_OBJECTS,
    STATE_SCHEMA_STATEMENTS,
    STATE_SCHEMA_VERSION,
    initialize_state_store,
    read_state_store,
)


WORKSPACE_DIRECTORIES = (
    "inputs",
    "inputs/modules",
    "inputs/characters",
    "inputs/attachments",
    "state",
    "state/snapshots",
    "views",
    "views/shared",
    "views/players",
    "views/dm",
    "archives",
    ".runtime",
)
_MANIFEST_KEYS = {
    "campaign_id",
    "compatibility",
    "created_at",
    "extensions",
    "format",
    "format_version",
    "storage",
}
_REQUIRED_PERSISTENT_DIRECTORIES = (
    "inputs",
    "inputs/modules",
    "inputs/characters",
    "inputs/attachments",
    "state",
    "state/snapshots",
    "archives",
    ".runtime",
)
_PROJECTION_DIRECTORIES = ("views", "views/shared", "views/players", "views/dm")


def _sha256(value: object) -> str:
    canonical_value = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical_value).hexdigest()


def _compatibility_manifest() -> dict[str, dict[str, str]]:
    return {
        "skill_suite": {
            "version": __version__,
            "sha256": skill_suite_sha256(),
        },
        "rules_library": {
            "version": "bootstrap-empty-v1",
            "sha256": _sha256({"semantic_sections": [], "entities": []}),
        },
        "formula_catalog": {
            "version": "bootstrap-empty-v1",
            "sha256": _sha256({"formulas": [], "tables": []}),
        },
        "state_schema": {
            "version": STATE_SCHEMA_VERSION,
            "sha256": _sha256(
                {
                    "application_id": STATE_APPLICATION_ID,
                    "objects": sorted(STATE_SCHEMA_OBJECTS),
                    "statements": STATE_SCHEMA_STATEMENTS,
                }
            ),
        },
        "map_schema": {
            "version": "bootstrap-empty-v1",
            "sha256": _sha256({"map_schemas": []}),
        },
    }


def _created_at() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _write_manifest_last(workspace: Path, manifest: dict[str, object]) -> None:
    temporary_directory = workspace / ".runtime"
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=temporary_directory,
        prefix="campaign-",
        suffix=".json.tmp",
        delete=False,
    ) as temporary_file:
        temporary_path = Path(temporary_file.name)
        json.dump(
            manifest,
            temporary_file,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        temporary_file.write("\n")
        temporary_file.flush()
        os.fsync(temporary_file.fileno())
    manifest_path = workspace / "campaign.json"
    try:
        os.link(temporary_path, manifest_path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise
    try:
        temporary_path.unlink()
    except OSError:
        pass
    try:
        directory_descriptor = os.open(workspace, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(directory_descriptor)
    except OSError:
        pass
    finally:
        os.close(directory_descriptor)


def _clean_created_workspace(
    workspace: Path,
    created_directories: list[Path],
    *,
    database_created: bool,
    root_created: bool,
) -> None:
    if database_created:
        for relative_file in (
            "state/campaign.sqlite3",
            "state/campaign.sqlite3-journal",
            "state/campaign.sqlite3-shm",
            "state/campaign.sqlite3-wal",
        ):
            path = workspace / relative_file
            try:
                if path.is_file() and not path.is_symlink():
                    path.unlink()
            except OSError:
                pass
    for directory in reversed(created_directories):
        try:
            directory.rmdir()
        except OSError:
            pass
    if root_created:
        try:
            workspace.rmdir()
        except OSError:
            pass


def _invalid_manifest() -> FacadeError:
    return FacadeError(
        "invalid_manifest",
        "根清单无效或包含越界路径。",
    )


def _invalid_state_store() -> FacadeError:
    return FacadeError(
        "invalid_state_store",
        "战役状态库缺失、损坏或与根清单不一致。",
    )


def _incompatible_campaign() -> FacadeError:
    return FacadeError(
        "incompatible_campaign",
        "战役兼容组合不受当前版本支持，必须先执行显式迁移。",
    )


def _valid_campaign_id(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return str(uuid.UUID(value)) == value
    except ValueError:
        return False


def _valid_created_at(value: object) -> bool:
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    canonical = (
        parsed.astimezone(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )
    return value == canonical


def _load_manifest(workspace: Path) -> tuple[dict[str, object], Path]:
    manifest_path = workspace / "campaign.json"
    try:
        if manifest_path.is_symlink() or not manifest_path.is_file():
            raise _invalid_manifest()
        loaded: object = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FacadeError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise _invalid_manifest() from error

    if not isinstance(loaded, dict) or set(loaded) != _MANIFEST_KEYS:
        raise _invalid_manifest()
    manifest: dict[str, object] = loaded
    storage = manifest.get("storage")
    if (
        manifest.get("format") != "dnd-5e-campaign"
        or type(manifest.get("format_version")) is not int
        or manifest.get("format_version") != 1
        or not _valid_campaign_id(manifest.get("campaign_id"))
        or not _valid_created_at(manifest.get("created_at"))
        or not isinstance(manifest.get("compatibility"), dict)
        or not isinstance(manifest.get("extensions"), dict)
        or not isinstance(storage, dict)
        or set(storage) != {"engine", "path"}
        or storage.get("engine") != "sqlite3"
        or storage.get("path") != "state/campaign.sqlite3"
    ):
        raise _invalid_manifest()
    if manifest.get("compatibility") != _compatibility_manifest():
        raise _incompatible_campaign()

    state_directory = workspace / "state"
    database_path = state_directory / "campaign.sqlite3"
    try:
        resolved_database = database_path.resolve(strict=True)
    except OSError as error:
        raise _invalid_manifest() from error
    if (
        state_directory.is_symlink()
        or database_path.is_symlink()
        or not database_path.is_file()
        or not resolved_database.is_relative_to(workspace)
    ):
        raise _invalid_manifest()
    return manifest, resolved_database


def _validate_persistent_directories(workspace: Path) -> None:
    for relative_directory in _REQUIRED_PERSISTENT_DIRECTORIES:
        directory = workspace / relative_directory
        if directory.is_symlink() or not directory.is_dir():
            raise _invalid_manifest()


def _rebuild_projection_directories(workspace: Path) -> None:
    for relative_directory in _PROJECTION_DIRECTORIES:
        directory = workspace / relative_directory
        if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
            raise _invalid_manifest()
        try:
            directory.mkdir(mode=0o700, exist_ok=True)
        except OSError as error:
            raise FacadeError(
                "projection_rebuild_failed",
                "工作区投影目录无法重建。",
            ) from error


def create_campaign(
    workspace: Path,
    initial_config: dict[str, object],
) -> CampaignSummary:
    requested_workspace = workspace.expanduser()
    try:
        candidate_workspace = requested_workspace.resolve(strict=False)
        filesystem_root = Path(candidate_workspace.anchor).resolve(strict=True)
        user_home = Path.home().resolve(strict=True)
    except OSError as error:
        raise FacadeError("unsafe_workspace", "战役工作区路径不安全。") from error
    if (
        requested_workspace.is_symlink()
        or candidate_workspace == filesystem_root
        or candidate_workspace == user_home
    ):
        raise FacadeError("unsafe_workspace", "战役工作区路径不安全。")
    workspace_exists = requested_workspace.exists()
    if workspace_exists:
        if not requested_workspace.is_dir():
            raise FacadeError("unsafe_workspace", "战役工作区路径不安全。")
        if next(requested_workspace.iterdir(), None) is not None:
            raise FacadeError(
                "workspace_not_empty",
                "战役创建只接受新建或完全空目录。",
            )
        resolved_workspace = requested_workspace.resolve(strict=True)
    else:
        resolved_workspace = requested_workspace.resolve(strict=False)

    root_created = False
    database_created = False
    created_directories: list[Path] = []
    try:
        if not workspace_exists:
            resolved_workspace.mkdir(mode=0o700)
            root_created = True
        for relative_directory in WORKSPACE_DIRECTORIES:
            directory = resolved_workspace / relative_directory
            directory.mkdir(mode=0o700)
            created_directories.append(directory)

        campaign_id = str(uuid.uuid4())
        event_id = str(uuid.uuid4())
        created_at = _created_at()
        database_path = resolved_workspace / "state" / "campaign.sqlite3"
        database_descriptor = os.open(
            database_path,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600,
        )
        database_created = True
        os.close(database_descriptor)
        summary = initialize_state_store(
            database_path,
            campaign_id=campaign_id,
            event_id=event_id,
            created_at=created_at,
            initial_config=initial_config,
        )
        manifest: dict[str, object] = {
            "format": "dnd-5e-campaign",
            "format_version": 1,
            "campaign_id": campaign_id,
            "created_at": created_at,
            "storage": {
                "engine": "sqlite3",
                "path": "state/campaign.sqlite3",
            },
            "compatibility": _compatibility_manifest(),
            "extensions": {},
        }
        _write_manifest_last(resolved_workspace, manifest)
        return summary
    except (OSError, sqlite3.Error, TypeError, ValueError) as error:
        _clean_created_workspace(
            resolved_workspace,
            created_directories,
            database_created=database_created,
            root_created=root_created,
        )
        raise FacadeError(
            "initialization_failed",
            "战役初始化失败，未留下有效战役。",
        ) from error


def open_campaign(workspace: Path) -> CampaignSummary:
    requested_workspace = workspace.expanduser()
    if requested_workspace.is_symlink():
        raise FacadeError("unsafe_workspace", "战役工作区路径不安全。")
    try:
        resolved_workspace = requested_workspace.resolve(strict=True)
    except OSError as error:
        raise _invalid_manifest() from error
    if not resolved_workspace.is_dir():
        raise _invalid_manifest()
    manifest, database_path = _load_manifest(resolved_workspace)
    _validate_persistent_directories(resolved_workspace)
    try:
        summary = read_state_store(database_path)
    except (OSError, sqlite3.Error, TypeError, ValueError) as error:
        raise _invalid_state_store() from error
    if (
        summary.campaign_id != manifest.get("campaign_id")
        or summary.created_at != manifest.get("created_at")
    ):
        raise _invalid_state_store()
    _rebuild_projection_directories(resolved_workspace)
    return summary
