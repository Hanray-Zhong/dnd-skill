from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SKILL_IDS = [
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
]

_CONFIGURE_FAULT_SCRIPT = """
import json
import os
from pathlib import Path
import sqlite3
import sys

from dnd_5e.errors import FacadeError
from dnd_5e.workspace import configure_campaign_difficulty


def interrupt_transaction(point: str) -> None:
    if point != sys.argv[2]:
        return
    if sys.argv[3] == "crash":
        os._exit(86)
    if sys.argv[3] == "write_error":
        raise sqlite3.OperationalError("受控写入失败")
    raise AssertionError(f"未知故障模式：{sys.argv[3]}")


try:
    configure_campaign_difficulty(
        Path(sys.argv[1]),
        expected_revision=1,
        idempotency_key=sys.argv[4],
        difficulty="challenging",
        failure_injector=interrupt_transaction,
    )
except FacadeError as error:
    print(
        json.dumps(
            {"code": error.code, "message": error.message},
            ensure_ascii=False,
            sort_keys=True,
        ),
        file=sys.stderr,
    )
    raise SystemExit(2)
"""


def _facade_environment() -> dict[str, str]:
    environment = os.environ.copy()
    source_path = str(REPOSITORY_ROOT / "src")
    existing_python_path = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        f"{source_path}{os.pathsep}{existing_python_path}"
        if existing_python_path
        else source_path
    )
    return environment


def run_facade(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "dnd_5e", *arguments],
        cwd=REPOSITORY_ROOT,
        env=_facade_environment(),
        capture_output=True,
        text=True,
        check=False,
    )


def run_configure_fault(
    workspace: Path,
    *,
    failure_point: str,
    failure_mode: str,
    idempotency_key: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-c",
            _CONFIGURE_FAULT_SCRIPT,
            str(workspace),
            failure_point,
            failure_mode,
            idempotency_key,
        ],
        cwd=REPOSITORY_ROOT,
        env=_facade_environment(),
        capture_output=True,
        text=True,
        check=False,
    )
