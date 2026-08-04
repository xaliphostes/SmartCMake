"""Command line driver: scmake build.scmake [-o CMakeLists.txt]"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, compile_source
from .errors import ScmakeError


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="scmake",
        description="Compile a .scmake source file into CMakeLists.txt")
    ap.add_argument("source", type=Path, help="the .scmake file to compile")
    ap.add_argument("-o", "--output", type=Path,
                    help="output path ('-' for stdout); "
                         "defaults to CMakeLists.txt beside the source")
    ap.add_argument("--check", action="store_true",
                    help="do not write; exit 1 if the output is out of date")
    ap.add_argument("--version", action="version", version=f"smartcmake {__version__}")
    args = ap.parse_args(argv)

    try:
        text = args.source.read_text()
    except OSError as exc:
        print(f"scmake: cannot read {args.source}: {exc.strerror}", file=sys.stderr)
        return 2

    try:
        cmake = compile_source(text, str(args.source))
    except ScmakeError as exc:
        print(exc, file=sys.stderr)
        return 1

    if args.output and str(args.output) == "-":
        sys.stdout.write(cmake)
        return 0

    target = args.output or args.source.parent / "CMakeLists.txt"

    if args.check:
        current = target.read_text() if target.exists() else None
        if current == cmake:
            return 0
        print(f"scmake: {target} is out of date with {args.source}", file=sys.stderr)
        return 1

    target.write_text(cmake)
    print(f"scmake: wrote {target}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
