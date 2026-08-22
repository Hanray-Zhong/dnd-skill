from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from tools.rules_library.build import build_library
from tools.rules_library.errors import BuildError
from tools.rules_library.package import build_preview_wheel


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m tools.rules_library")
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="构建固定规则章节库")
    build.add_argument("--baseline", required=True, type=Path)
    build.add_argument("--reference-root", required=True, type=Path)
    build.add_argument("--output", required=True, type=Path)
    build.add_argument(
        "--publication",
        choices=("local-preview", "public"),
        default="local-preview",
    )
    preview = commands.add_parser("preview-wheel", help="生成自包含本地预览 wheel")
    preview.add_argument("--library", required=True, type=Path)
    preview.add_argument("--output-directory", required=True, type=Path)
    return parser


def main(arguments: list[str] | None = None) -> int:
    options = _parser().parse_args(arguments)
    try:
        if options.command == "build":
            result = build_library(
                baseline_path=options.baseline,
                reference_root=options.reference_root,
                output=options.output,
                publication=options.publication,
            )
        else:
            result = build_preview_wheel(
                library_root=options.library,
                output_directory=options.output_directory,
            )
    except BuildError as error:
        print(
            json.dumps(error.payload(), ensure_ascii=False, sort_keys=True),
            file=sys.stderr,
        )
        return 2
    print(json.dumps({"ok": True, **result}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
