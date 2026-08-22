from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest
import uuid

from tests.facade_support import run_facade


class Dnd5eFacadeTests(unittest.TestCase):
    def test_create_initializes_an_empty_campaign_workspace(self) -> None:
        initial_config = {
            "advancement": "xp",
            "difficulty": "standard",
            "roll_policy": "players",
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "campaign"

            result = run_facade(
                "create",
                str(workspace),
                "--initial-config",
                json.dumps(initial_config),
            )
            payload = json.loads(result.stdout) if result.stdout else None
            entries = sorted(
                f"{path.relative_to(workspace)}{'/' if path.is_dir() else ''}"
                for path in workspace.rglob("*")
            ) if workspace.exists() else []
            campaign_id_is_uuid = False
            if isinstance(payload, dict) and isinstance(payload.get("campaign_id"), str):
                campaign_id_is_uuid = str(uuid.UUID(payload["campaign_id"])) == payload["campaign_id"]

            self.assertEqual(
                {
                    "returncode": 0,
                    "ok": True,
                    "operation": "create",
                    "revision": 1,
                    "campaign_status": "awaiting_session_zero",
                    "continuation": {
                        "allowed": True,
                        "next_step": "session_zero",
                        "ready_to_play": False,
                    },
                    "initial_config": initial_config,
                    "workspace": str(workspace.resolve()),
                    "campaign_id_is_uuid": True,
                    "entries": [
                        ".runtime/",
                        "archives/",
                        "campaign.json",
                        "inputs/",
                        "inputs/attachments/",
                        "inputs/characters/",
                        "inputs/modules/",
                        "state/",
                        "state/campaign.sqlite3",
                        "state/snapshots/",
                        "views/",
                        "views/dm/",
                        "views/players/",
                        "views/shared/",
                    ],
                },
                {
                    "returncode": result.returncode,
                    "ok": payload.get("ok") if isinstance(payload, dict) else None,
                    "operation": payload.get("operation") if isinstance(payload, dict) else None,
                    "revision": payload.get("revision") if isinstance(payload, dict) else None,
                    "campaign_status": (
                        payload.get("campaign_status")
                        if isinstance(payload, dict)
                        else None
                    ),
                    "continuation": (
                        payload.get("continuation")
                        if isinstance(payload, dict)
                        else None
                    ),
                    "initial_config": (
                        payload.get("initial_config")
                        if isinstance(payload, dict)
                        else None
                    ),
                    "workspace": payload.get("workspace") if isinstance(payload, dict) else None,
                    "campaign_id_is_uuid": campaign_id_is_uuid,
                    "entries": entries,
                },
                msg=result.stderr,
            )

    def test_open_restores_the_same_empty_campaign(self) -> None:
        initial_config = {
            "advancement": "milestone",
            "difficulty": "challenging",
            "roll_policy": "players",
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "campaign"
            create_result = run_facade(
                "create",
                str(workspace),
                "--initial-config",
                json.dumps(initial_config),
            )
            created = json.loads(create_result.stdout)
            manifest_before = (workspace / "campaign.json").read_bytes()
            database_before = (workspace / "state" / "campaign.sqlite3").read_bytes()

            open_result = run_facade("open", str(workspace))
            opened = json.loads(open_result.stdout) if open_result.stdout else None

            self.assertEqual(
                {
                    "create_returncode": 0,
                    "open_returncode": 0,
                    "same_campaign_id": True,
                    "same_revision": True,
                    "same_initial_config": True,
                    "operation": "open",
                    "campaign_status": "awaiting_session_zero",
                    "continuation": {
                        "allowed": True,
                        "next_step": "session_zero",
                        "ready_to_play": False,
                    },
                    "workspace": str(workspace.resolve()),
                    "manifest_unchanged": True,
                    "database_unchanged": True,
                },
                {
                    "create_returncode": create_result.returncode,
                    "open_returncode": open_result.returncode,
                    "same_campaign_id": (
                        isinstance(opened, dict)
                        and created["campaign_id"] == opened.get("campaign_id")
                    ),
                    "same_revision": (
                        isinstance(opened, dict)
                        and created["revision"] == opened.get("revision")
                    ),
                    "same_initial_config": (
                        isinstance(opened, dict)
                        and created["initial_config"] == opened.get("initial_config")
                    ),
                    "operation": opened.get("operation") if isinstance(opened, dict) else None,
                    "campaign_status": (
                        opened.get("campaign_status")
                        if isinstance(opened, dict)
                        else None
                    ),
                    "continuation": (
                        opened.get("continuation")
                        if isinstance(opened, dict)
                        else None
                    ),
                    "workspace": opened.get("workspace") if isinstance(opened, dict) else None,
                    "manifest_unchanged": (
                        manifest_before == (workspace / "campaign.json").read_bytes()
                    ),
                    "database_unchanged": (
                        database_before
                        == (workspace / "state" / "campaign.sqlite3").read_bytes()
                    ),
                },
                msg=open_result.stderr,
            )

    def test_create_accepts_an_existing_empty_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "selected-empty-directory"
            workspace.mkdir()

            result = run_facade("create", str(workspace))
            payload = json.loads(result.stdout) if result.stdout else None

            self.assertEqual(
                {
                    "returncode": 0,
                    "ok": True,
                    "revision": 1,
                    "campaign_status": "awaiting_session_zero",
                    "ready_to_play": False,
                    "manifest_exists": True,
                },
                {
                    "returncode": result.returncode,
                    "ok": payload.get("ok") if isinstance(payload, dict) else None,
                    "revision": payload.get("revision") if isinstance(payload, dict) else None,
                    "campaign_status": (
                        payload.get("campaign_status")
                        if isinstance(payload, dict)
                        else None
                    ),
                    "ready_to_play": (
                        payload.get("continuation", {}).get("ready_to_play")
                        if isinstance(payload, dict)
                        and isinstance(payload.get("continuation"), dict)
                        else None
                    ),
                    "manifest_exists": (workspace / "campaign.json").is_file(),
                },
                msg=result.stderr,
            )

    def test_create_rejects_a_nonempty_directory_without_modifying_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "existing-content"
            workspace.mkdir()
            marker = workspace / "keep-me.txt"
            marker.write_text("用户原有内容\n", encoding="utf-8")

            result = run_facade("create", str(workspace))
            error_payload = json.loads(result.stderr) if result.stderr else None

            self.assertEqual(
                {
                    "returncode": 2,
                    "error": {
                        "ok": False,
                        "error": {
                            "code": "workspace_not_empty",
                            "message": "战役创建只接受新建或完全空目录。",
                        },
                    },
                    "stdout": "",
                    "marker": "用户原有内容\n",
                    "entries": ["keep-me.txt"],
                    "has_traceback": False,
                },
                {
                    "returncode": result.returncode,
                    "error": error_payload,
                    "stdout": result.stdout,
                    "marker": marker.read_text(encoding="utf-8"),
                    "entries": sorted(path.name for path in workspace.iterdir()),
                    "has_traceback": "Traceback" in result.stderr,
                },
            )

    def test_create_rejects_a_symlink_workspace_without_following_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_root = Path(temporary_directory)
            real_directory = temporary_root / "real-empty-directory"
            real_directory.mkdir()
            workspace_link = temporary_root / "campaign-link"
            workspace_link.symlink_to(real_directory, target_is_directory=True)

            result = run_facade("create", str(workspace_link))
            error_payload = json.loads(result.stderr) if result.stderr else None

            self.assertEqual(
                {
                    "returncode": 2,
                    "error": {
                        "ok": False,
                        "error": {
                            "code": "unsafe_workspace",
                            "message": "战役工作区路径不安全。",
                        },
                    },
                    "stdout": "",
                    "link_preserved": True,
                    "target_entries": [],
                    "has_traceback": False,
                },
                {
                    "returncode": result.returncode,
                    "error": error_payload,
                    "stdout": result.stdout,
                    "link_preserved": workspace_link.is_symlink(),
                    "target_entries": sorted(path.name for path in real_directory.iterdir()),
                    "has_traceback": "Traceback" in result.stderr,
                },
            )

    def test_create_rejects_the_filesystem_root_as_unsafe(self) -> None:
        filesystem_root = Path(tempfile.gettempdir()).resolve().anchor

        result = run_facade("create", filesystem_root)
        error_payload = json.loads(result.stderr) if result.stderr else None

        self.assertEqual(
            {
                "returncode": 2,
                "error": {
                    "ok": False,
                    "error": {
                        "code": "unsafe_workspace",
                        "message": "战役工作区路径不安全。",
                    },
                },
                "stdout": "",
                "has_traceback": False,
            },
            {
                "returncode": result.returncode,
                "error": error_payload,
                "stdout": result.stdout,
                "has_traceback": "Traceback" in result.stderr,
            },
        )

    def test_create_cleans_up_after_initialization_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "read-only-empty-directory"
            workspace.mkdir(mode=0o500)
            try:
                result = run_facade("create", str(workspace))
            finally:
                workspace.chmod(0o700)
            error_payload = json.loads(result.stderr) if result.stderr else None

            self.assertEqual(
                {
                    "returncode": 2,
                    "error": {
                        "ok": False,
                        "error": {
                            "code": "initialization_failed",
                            "message": "战役初始化失败，未留下有效战役。",
                        },
                    },
                    "stdout": "",
                    "workspace_preserved": True,
                    "entries": [],
                    "manifest_exists": False,
                    "has_traceback": False,
                },
                {
                    "returncode": result.returncode,
                    "error": error_payload,
                    "stdout": result.stdout,
                    "workspace_preserved": workspace.is_dir(),
                    "entries": sorted(path.name for path in workspace.iterdir()),
                    "manifest_exists": (workspace / "campaign.json").exists(),
                    "has_traceback": "Traceback" in result.stderr,
                },
            )

    def test_open_rebuilds_missing_empty_projection_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "campaign"
            create_result = run_facade("create", str(workspace))
            self.assertEqual(0, create_result.returncode, msg=create_result.stderr)
            manifest_before = (workspace / "campaign.json").read_bytes()
            database_before = (workspace / "state" / "campaign.sqlite3").read_bytes()
            shutil.rmtree(workspace / "views")

            result = run_facade("open", str(workspace))
            payload = json.loads(result.stdout) if result.stdout else None

            self.assertEqual(
                {
                    "returncode": 0,
                    "ok": True,
                    "operation": "open",
                    "projection_directories": ["dm", "players", "shared"],
                    "manifest_unchanged": True,
                    "database_unchanged": True,
                },
                {
                    "returncode": result.returncode,
                    "ok": payload.get("ok") if isinstance(payload, dict) else None,
                    "operation": payload.get("operation") if isinstance(payload, dict) else None,
                    "projection_directories": sorted(
                        path.name for path in (workspace / "views").iterdir()
                    ) if (workspace / "views").is_dir() else [],
                    "manifest_unchanged": (
                        manifest_before == (workspace / "campaign.json").read_bytes()
                    ),
                    "database_unchanged": (
                        database_before
                        == (workspace / "state" / "campaign.sqlite3").read_bytes()
                    ),
                },
                msg=result.stderr,
            )


if __name__ == "__main__":
    unittest.main()
