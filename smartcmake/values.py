"""The value model, and how a value becomes a CMake argument.

Transpile-time values are ordinary Python ones — str, int, float, bool, list,
dict — plus `TargetHandle`. The `cm_*` helpers are the boundary: everything
past them is CMake argument text.
"""

from __future__ import annotations

from typing import Any


class TargetHandle:
    """A declared target, as a value: `const app = executable("app") { ... }`.

    It renders as the target's name, so a handle drops straight into anywhere a
    name was already accepted — `link: [core]`, `install { targets: [...] }`,
    `${app}`. Because a handle only exists once its declaration has been
    emitted, referring to one before it is declared is impossible, which is
    also CMake's rule for target_*() commands.
    """

    def __init__(self, kind: str, name: str, qualifier: str | None = None):
        self.kind = kind
        self.name = name
        self.qualifier = qualifier

    def __str__(self) -> str:
        return self.name


def truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.upper() not in ("", "OFF", "FALSE", "NO", "0")
    return bool(value)


def stringify(value: Any) -> str:
    if isinstance(value, bool):
        return "ON" if value else "OFF"
    if isinstance(value, list):
        return ";".join(stringify(v) for v in value)
    return str(value)


def cm_quote(value: Any) -> str:
    """Render one CMake argument, always quoted."""
    text = stringify(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


def cm_value(value: Any) -> str:
    """Render one CMake argument, quoting only when it would otherwise split."""
    text = stringify(value)
    if text == "" or any(ch in text for ch in ' \t"()#;'):
        return cm_quote(value)
    return text


def cm_list(value: Any) -> list[str]:
    items = value if isinstance(value, list) else [value]
    return [cm_value(v) for v in items]


def flatten(values: list) -> list:
    """`app.link(GTest.gtest_main, EXTRA)` where EXTRA is itself a list."""
    out: list = []
    for value in values:
        out.extend(value if isinstance(value, list) else [value])
    return out
