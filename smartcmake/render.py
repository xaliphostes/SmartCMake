"""IR -> CMakeLists.txt text.

Pure formatting: line wrapping, indentation, comment markers, blank-line
normalisation. It knows nothing about scmake's vocabulary, so a change to what
a construct *means* never reaches this file.
"""

from __future__ import annotations

from . import ir

WRAP_AT = 88


def render(nodes: list) -> str:
    """Render a command list into the final file text."""
    return _normalize(render_lines(nodes))


def render_lines(nodes: list) -> list[str]:
    out: list[str] = []
    for node in nodes:
        if isinstance(node, ir.Blank):
            out.append("")
        elif isinstance(node, ir.Comment):
            out.extend(f"# {line}" if line else "#" for line in node.lines)
        elif isinstance(node, ir.Raw):
            out.extend(node.lines)
        elif isinstance(node, ir.Command):
            out.extend(render_command(node.name, node.args, node.force_wrap))
        elif isinstance(node, ir.Block):
            out.append(node.open)
            out.extend(indent(render_lines(node.body)))
            if node.orelse is not None:
                out.append("else()")
                out.extend(indent(render_lines(node.orelse)))
            out.append(node.close)
        else:  # pragma: no cover - every node type is handled above
            raise TypeError(f"cannot render {type(node).__name__}")
    return out


def render_command(name: str, args: list, force_wrap: bool = False) -> list[str]:
    """Render one CMake command, wrapping when it gets long. A list argument is
    a group (`GIT_TAG v1.2.3`) that must never be split across lines."""
    units = [" ".join(str(x) for x in a) if isinstance(a, (list, tuple)) else str(a)
             for a in args]
    one_line = f"{name}({' '.join(units)})"
    if not force_wrap and (len(one_line) <= WRAP_AT or len(units) <= 1):
        return [one_line]
    return [f"{name}(", *[f"    {u}" for u in units], ")"]


def wrap_comment(text: str, width: int = 76) -> list[str]:
    """Reflow a doc string: source line breaks and indentation are collapsed so
    a multi-line template literal comes out as a tidy comment block."""
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if len(candidate) > width and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def indent(lines: list[str]) -> list[str]:
    return [f"    {line}" if line else "" for line in lines]


def _normalize(lines: list[str]) -> str:
    out: list[str] = []
    for line in lines:
        if not line and (not out or not out[-1]):
            continue
        out.append(line.rstrip())
    while out and not out[-1]:
        out.pop()
    return "\n".join(out) + "\n"
