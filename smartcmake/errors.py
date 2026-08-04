"""Diagnostics shared by every stage of the compiler."""

from __future__ import annotations


class ScmakeError(Exception):
    """A user-facing compile error carrying a source location."""

    def __init__(self, message: str, line: int = 0, col: int = 0,
                 filename: str = "<scmake>"):
        self.message = message
        self.line = line
        self.col = col
        self.filename = filename
        super().__init__(message)

    def __str__(self) -> str:
        where = self.filename
        if self.line:
            where = f"{where}:{self.line}:{self.col}"
        return f"{where}: error: {self.message}"
