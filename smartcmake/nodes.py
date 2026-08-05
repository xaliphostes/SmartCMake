"""AST node definitions.

Statements carry `comments` (the comment lines directly above them in the
source) and `line`, so diagnostics and the emitted CMake can both point back
at the original .scmake.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

# --- statements ------------------------------------------------------------


@dataclass
class Project:
    name: str
    body: list
    comments: list = field(default_factory=list)
    line: int = 0


@dataclass
class ConstDecl:
    """Transpile-time binding. Never appears in the CMake output."""
    name: str
    value: Any
    comments: list = field(default_factory=list)
    line: int = 0


@dataclass
class SetVar:
    """A real CMake variable: `set VAR = value [cache(TYPE, "doc")]`."""
    name: str
    value: Any
    cache_type: Optional[str] = None
    cache_doc: str = ""
    force: bool = False
    comments: list = field(default_factory=list)
    line: int = 0


@dataclass
class ForOf:
    var: str
    iterable: Any
    body: list
    comments: list = field(default_factory=list)
    line: int = 0


@dataclass
class If:
    """Transpile-time branch: evaluated now, only one arm reaches the output."""
    cond: Any
    then: list
    orelse: list = field(default_factory=list)
    comments: list = field(default_factory=list)
    line: int = 0


@dataclass
class When:
    """Configure-time branch: becomes a literal if()/else()/endif() block."""
    cond: Any
    then: list
    orelse: list = field(default_factory=list)
    comments: list = field(default_factory=list)
    line: int = 0


@dataclass
class Target:
    kind: str  # executable | library | interface
    name: Any  # expression
    qualifier: Optional[str] = None  # STATIC | SHARED | MODULE ...
    body: list = field(default_factory=list)
    comments: list = field(default_factory=list)
    line: int = 0


@dataclass
class Fetch:
    name: str
    body: list
    comments: list = field(default_factory=list)
    line: int = 0


@dataclass
class Install:
    """`install { targets: [...] runtime: "bin" }` -> one install() command."""
    body: list
    comments: list = field(default_factory=list)
    line: int = 0


@dataclass
class Function:
    """A CMake function(). Parameters are bound in the body, so `target_name`
    reads as `${target_name}` without going through `vars.`."""
    name: str
    params: list
    body: list
    comments: list = field(default_factory=list)
    line: int = 0


@dataclass
class CommentBlock:
    """A free-standing comment (one not sitting directly above a statement)."""
    lines: list
    comments: list = field(default_factory=list)
    line: int = 0


@dataclass
class Raw:
    """Escape hatch: emit the value verbatim."""
    value: Any
    comments: list = field(default_factory=list)
    line: int = 0


@dataclass
class Setting:
    """`name: value` or `name(ARGS): value`."""
    name: str
    args: list
    value: Any
    comments: list = field(default_factory=list)
    line: int = 0


@dataclass
class Call:
    name: str
    args: list
    comments: list = field(default_factory=list)
    line: int = 0


# --- expressions -----------------------------------------------------------


@dataclass
class Str:
    value: str
    line: int = 0


@dataclass
class Num:
    value: Any
    line: int = 0


@dataclass
class Bool:
    value: bool
    line: int = 0


@dataclass
class Ident:
    name: str
    line: int = 0


@dataclass
class Member:
    obj: Any
    name: str
    line: int = 0


@dataclass
class ListLit:
    items: list
    line: int = 0


@dataclass
class ObjectLit:
    entries: list  # [(key, value_node)]
    line: int = 0


@dataclass
class Template:
    parts: list  # [("lit", str) | ("expr", node)]
    line: int = 0


@dataclass
class Unary:
    op: str
    operand: Any
    line: int = 0


@dataclass
class Binary:
    op: str
    left: Any
    right: Any
    line: int = 0


@dataclass
class CallExpr:
    name: str
    args: list
    line: int = 0
