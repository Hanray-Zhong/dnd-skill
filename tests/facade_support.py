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


def run_facade(*arguments: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    source_path = str(REPOSITORY_ROOT / "src")
    existing_python_path = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        f"{source_path}{os.pathsep}{existing_python_path}"
        if existing_python_path
        else source_path
    )
    return subprocess.run(
        [sys.executable, "-m", "dnd_5e", *arguments],
        cwd=REPOSITORY_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
