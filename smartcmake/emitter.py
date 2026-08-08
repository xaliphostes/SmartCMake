"""AST -> CMakeLists.txt, in two steps.

    AST --analyzer--> IR (a command list) --render--> text

The analyzer decides what commands the program means; the renderer decides how
they are spelled. This module is only the seam between them, kept so that
`from smartcmake import emit` stays the public entry point.
"""

from __future__ import annotations

from .analyzer import Analyzer, analyze
from .render import render

__all__ = ["emit", "analyze", "render", "Analyzer"]


def emit(program: list, filename: str = "build.scmake") -> str:
    return render(analyze(program, filename))
