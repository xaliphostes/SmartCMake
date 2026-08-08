"""The intermediate representation: what the analyzer produces and the
renderer consumes.

It is a *command list*, not a mirror of the AST. The output of this language is
a flat sequence of CMake commands with shallow nesting for `if()` and
`function()`, and the IR is shaped like the output rather than the input — a
node type per language construct would be pure cost.

Nothing here knows how a command is spelled; that is `render`. Nothing here
knows what a command means; that is the analyzer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Command:
    """One CMake command. `args` holds already-stringified arguments; a list
    element is a group (`GIT_TAG v1.2.3`) that must never be split across
    lines when the command is wrapped."""
    name: str
    args: list = field(default_factory=list)
    force_wrap: bool = False


@dataclass
class Comment:
    """Lines to render as `#` comments. An empty line becomes a bare `#`."""
    lines: list


@dataclass
class Blank:
    """One blank line. Runs of these are collapsed when rendering, so callers
    can ask for separation without tracking what came before."""


@dataclass
class Raw:
    """Lines emitted verbatim — the `raw` escape hatch."""
    lines: list


@dataclass
class Block:
    """A construct with an opening line, an indented body and a closing line:
    `if()/endif()` and `function()/endfunction()`.

    `orelse` is None when there is no else arm, and a list (possibly empty)
    when there is one — an `else()` that a branch left empty still has to be
    written, so emptiness and absence are different things here.
    """
    open: str
    body: list
    close: str
    orelse: Optional[list] = None


Node = Any  # Command | Comment | Blank | Raw | Block
