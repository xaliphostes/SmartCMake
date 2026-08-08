"""Read-only queries over the AST, used before or instead of walking it."""

from __future__ import annotations

from . import nodes as N


def find_call(body: list, name: str):
    """Depth-first search for a call to `name`, through every nested body."""
    for st in body:
        if isinstance(st, N.Call) and st.name == name:
            return st
        for attr in ("body", "then", "orelse"):
            nested = getattr(st, attr, None)
            if isinstance(nested, list):
                found = find_call(nested, name)
                if found is not None:
                    return found
    return None


def find_setting(body: list, name: str):
    for st in body:
        if isinstance(st, N.Setting) and st.name == name and not st.args:
            return st.value
    return None
