"""Shared helpers for the test modules.

Not named `test_*`, so unittest discovery skips it. Importing it puts the
repository root on `sys.path`, which is what makes `import smartcmake` work
whether the suite is run with `python3 -m unittest discover -s tests` or by
running one module directly.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from smartcmake import ScmakeError, compile_source, parse  # noqa: E402
from smartcmake import ir  # noqa: E402
from smartcmake.analyzer import analyze  # noqa: E402

__all__ = ["ScmakeError", "compile_source", "compile_body", "ErrorCase",
           "ir", "analyze_source", "commands", "command_names"]


def analyze_source(body: str) -> list:
    """Analyze a project body and return the IR, without rendering it."""
    src = "project P {\n" + body + "\n}\n"
    return analyze(parse(src, "t.scmake"), "t.scmake")


def commands(nodes: list, nested: bool = True) -> list:
    """(name, args) for each command. `nested` descends into blocks."""
    out = []
    for node in nodes:
        if isinstance(node, ir.Command):
            out.append((node.name, node.args))
        elif isinstance(node, ir.Block) and nested:
            out.extend(commands(node.body))
            out.extend(commands(node.orelse or []))
    return out


def command_names(nodes: list, nested: bool = True) -> list:
    return [name for name, _ in commands(nodes, nested)]


def compile_body(body: str) -> str:
    """Compile a project body and return the CMake below the project() line."""
    out = compile_source("project P {\n" + body + "\n}\n", "t.scmake")
    lines = out.splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith("project(")) + 1
    return "\n".join(l for l in lines[start:] if l).strip()


class ErrorCase(unittest.TestCase):
    """For suites that assert on diagnostics rather than on output."""

    def expect_error(self, body: str, fragment: str):
        with self.assertRaises(ScmakeError) as cm:
            compile_source("project P {\n" + body + "\n}", "t.scmake")
        self.assertIn(fragment, str(cm.exception))
