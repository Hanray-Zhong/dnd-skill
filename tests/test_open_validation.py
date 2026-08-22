from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from tests.facade_support import run_facade


class OpenValidationFacadeTests(unittest.TestCase):
    def test_open_rejects_a_manifest_path_that_escapes_the_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_root = Path(temporary_directory)
            workspace = temporary_root / "campaign"
            create_result = run_facade("create", str(workspace))
            self.assertEqual(0, create_result.returncode, msg=create_result.stderr)
            database = workspace / "state" / "campaign.sqlite3"
            outside_database = temporary_root / "outside.sqlite3"
            outside_database.write_bytes(database.read_bytes())
            outside_before = outside_database.read_bytes()
            manifest_path = workspace / "campaign.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["storage"]["path"] = "../outside.sqlite3"
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False),
                encoding="utf-8",
            )

            result = run_facade("open", str(workspace))
            error_payload = json.loads(result.stderr) if result.stderr else None

            self.assertEqual(
                {
                    "returncode": 2,
                    "error": {
                        "ok": False,
                        "error": {
                            "code": "invalid_manifest",
                            "message": "根清单无效或包含越界路径。",
                        },
                    },
                    "stdout": "",
                    "outside_database_unchanged": True,
                    "has_traceback": False,
                },
                {
                    "returncode": result.returncode,
                    "error": error_payload,
                    "stdout": result.stdout,
                    "outside_database_unchanged": (
                        outside_before == outside_database.read_bytes()
                    ),
                    "has_traceback": "Traceback" in result.stderr,
                },
            )

    def test_open_rejects_a_corrupt_state_store_without_rewriting_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "campaign"
            create_result = run_facade("create", str(workspace))
            self.assertEqual(0, create_result.returncode, msg=create_result.stderr)
            database = workspace / "state" / "campaign.sqlite3"
            corrupt_content = b"not-a-sqlite-database\n"
            database.write_bytes(corrupt_content)

            result = run_facade("open", str(workspace))
            error_payload = json.loads(result.stderr) if result.stderr else None

            self.assertEqual(
                {
                    "returncode": 2,
                    "error": {
                        "ok": False,
                        "error": {
                            "code": "invalid_state_store",
                            "message": "战役状态库缺失、损坏或与根清单不一致。",
                        },
                    },
                    "stdout": "",
                    "database_unchanged": True,
                    "has_traceback": False,
                },
                {
                    "returncode": result.returncode,
                    "error": error_payload,
                    "stdout": result.stdout,
                    "database_unchanged": database.read_bytes() == corrupt_content,
                    "has_traceback": "Traceback" in result.stderr,
                },
            )

    def test_open_rejects_a_state_store_with_a_missing_schema_object(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "campaign"
            create_result = run_facade("create", str(workspace))
            self.assertEqual(0, create_result.returncode, msg=create_result.stderr)
            database = workspace / "state" / "campaign.sqlite3"
            with sqlite3.connect(database) as connection:
                connection.execute("DROP TABLE knowledge")
            database_before = database.read_bytes()

            result = run_facade("open", str(workspace))
            error_payload = json.loads(result.stderr) if result.stderr else None

            self.assertEqual(
                {
                    "returncode": 2,
                    "error": {
                        "ok": False,
                        "error": {
                            "code": "invalid_state_store",
                            "message": "战役状态库缺失、损坏或与根清单不一致。",
                        },
                    },
                    "stdout": "",
                    "database_unchanged": True,
                    "has_traceback": False,
                },
                {
                    "returncode": result.returncode,
                    "error": error_payload,
                    "stdout": result.stdout,
                    "database_unchanged": database_before == database.read_bytes(),
                    "has_traceback": "Traceback" in result.stderr,
                },
            )

    def test_open_rejects_wrong_schema_definitions_with_the_same_names(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "campaign"
            create_result = run_facade("create", str(workspace))
            self.assertEqual(0, create_result.returncode, msg=create_result.stderr)
            database = workspace / "state" / "campaign.sqlite3"
            with sqlite3.connect(database) as connection:
                connection.execute("DROP TABLE knowledge")
                connection.execute("CREATE TABLE knowledge (x INTEGER) STRICT")
                connection.execute("CREATE INDEX knowledge_by_fact ON knowledge(x)")
            database_before = database.read_bytes()

            result = run_facade("open", str(workspace))
            error_payload = json.loads(result.stderr) if result.stderr else None

            self.assertEqual(
                {
                    "returncode": 2,
                    "error": {
                        "ok": False,
                        "error": {
                            "code": "invalid_state_store",
                            "message": "战役状态库缺失、损坏或与根清单不一致。",
                        },
                    },
                    "stdout": "",
                    "database_unchanged": True,
                    "has_traceback": False,
                },
                {
                    "returncode": result.returncode,
                    "error": error_payload,
                    "stdout": result.stdout,
                    "database_unchanged": database_before == database.read_bytes(),
                    "has_traceback": "Traceback" in result.stderr,
                },
            )

    def test_open_rejects_an_unsupported_compatibility_combination(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "campaign"
            create_result = run_facade("create", str(workspace))
            self.assertEqual(0, create_result.returncode, msg=create_result.stderr)
            manifest_path = workspace / "campaign.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["compatibility"]["state_schema"]["version"] = "999"
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False),
                encoding="utf-8",
            )
            database_before = (workspace / "state" / "campaign.sqlite3").read_bytes()

            result = run_facade("open", str(workspace))
            error_payload = json.loads(result.stderr) if result.stderr else None

            self.assertEqual(
                {
                    "returncode": 2,
                    "error": {
                        "ok": False,
                        "error": {
                            "code": "incompatible_campaign",
                            "message": "战役兼容组合不受当前版本支持，必须先执行显式迁移。",
                        },
                    },
                    "stdout": "",
                    "database_unchanged": True,
                    "has_traceback": False,
                },
                {
                    "returncode": result.returncode,
                    "error": error_payload,
                    "stdout": result.stdout,
                    "database_unchanged": (
                        database_before
                        == (workspace / "state" / "campaign.sqlite3").read_bytes()
                    ),
                    "has_traceback": "Traceback" in result.stderr,
                },
            )


if __name__ == "__main__":
    unittest.main()
