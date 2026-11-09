"""Expression evaluation, and the one place expressions are *not* evaluated.

`eval` reduces an expression to a transpile-time value. `condition` does the
opposite: it translates an expression into CMake `if()` syntax and leaves the
deciding to CMake. That pair is the language's central distinction, so the two
live next to each other.
"""

from __future__ import annotations

from typing import Any

from . import nodes as N
from .values import TargetHandle, cm_quote, cm_value, stringify, truthy


class ExpressionsMixin:
    """Mixed into Analyzer; relies on its `lookup` and `err`."""

    def eval(self, node) -> Any:
        if isinstance(node, N.Str):
            return node.value
        if isinstance(node, (N.Num, N.Bool)):
            return node.value
        if isinstance(node, N.ListLit):
            out = []
            for item in node.items:
                value = self.eval(item)
                out.extend(value if isinstance(value, list) else [value])
            return out
        if isinstance(node, N.ObjectLit):
            return {key: self.eval(val) for key, val in node.entries}
        if isinstance(node, N.Template):
            parts = []
            for kind, part in node.parts:
                parts.append(part if kind == "lit" else stringify(self.eval(part)))
            return "".join(parts)
        if isinstance(node, N.Ident):
            value, found = self.lookup(node.name)
            # An unbound identifier is a bare CMake word: PRIVATE, STATIC, CXX...
            return value if found else node.name
        if isinstance(node, N.Member):
            return self.eval_member(node)
        if isinstance(node, N.Unary):
            return not truthy(self.eval(node.operand))
        if isinstance(node, N.Binary):
            return self.eval_binary(node)
        if isinstance(node, N.CallExpr):
            return self.eval_call(node)
        raise self.err(f"cannot evaluate {type(node).__name__}", node)

    def eval_member(self, node: N.Member) -> Any:
        if isinstance(node.obj, N.Ident):
            base = node.obj.name
            bound, found = self.lookup(base)
            if not found:
                if base == "cmake":
                    name = node.name
                    if not name.startswith("CMAKE_"):
                        name = "CMAKE_" + name
                    return "${" + name + "}"
                if base == "env":
                    return "$ENV{" + node.name + "}"
                if base == "vars":
                    return "${" + node.name + "}"
                # Otherwise a namespaced CMake target: GTest.gtest_main
                return f"{base}::{node.name}"
            obj = bound
        else:
            obj = self.eval(node.obj)

        if isinstance(obj, TargetHandle):
            # Without this a typo would fall through to the namespaced-target
            # guess below and quietly produce `app::lnk`.
            if node.name not in ("name", "kind"):
                raise self.err(
                    f"a target has no field {node.name!r}; settings are applied "
                    f"by calling them, e.g. {obj.name}.link(core)", node)
            return getattr(obj, node.name)

        if isinstance(obj, dict):
            if node.name not in obj:
                raise self.err(f"no field {node.name!r} on that value", node)
            return obj[node.name]
        if isinstance(obj, list) and node.name == "length":
            return len(obj)
        return f"{stringify(obj)}::{node.name}"

    def eval_binary(self, node: N.Binary) -> Any:
        if node.op == "&&":
            left = self.eval(node.left)
            return self.eval(node.right) if truthy(left) else left
        if node.op == "||":
            left = self.eval(node.left)
            return left if truthy(left) else self.eval(node.right)

        left, right = self.eval(node.left), self.eval(node.right)
        if node.op == "+":
            if isinstance(left, list) or isinstance(right, list):
                as_list = lambda v: v if isinstance(v, list) else [v]
                return as_list(left) + as_list(right)
            if isinstance(left, str) or isinstance(right, str):
                return stringify(left) + stringify(right)
            return left + right
        ops = {
            "==": lambda a, b: a == b,
            "!=": lambda a, b: a != b,
            "<": lambda a, b: a < b,
            ">": lambda a, b: a > b,
            "<=": lambda a, b: a <= b,
            ">=": lambda a, b: a >= b,
        }
        return ops[node.op](left, right)

    def eval_call(self, node: N.CallExpr) -> Any:
        args = [self.eval(a) for a in node.args]
        name = node.name
        if name == "upper":
            return stringify(args[0]).upper()
        if name == "lower":
            return stringify(args[0]).lower()
        if name == "join":
            sep = stringify(args[1]) if len(args) > 1 else " "
            return sep.join(stringify(x) for x in args[0])
        if name == "replace":
            return stringify(args[0]).replace(stringify(args[1]), stringify(args[2]))
        if name == "var":
            # vars.X with a computed name: var(`cgogn_${c}_FOUND`) -> ${cgogn_core_FOUND}
            if len(args) != 1:
                raise self.err("var(name) takes one argument", node)
            return "${" + stringify(args[0]) + "}"
        if name in ("prefix", "suffix"):
            # prefix(["a", "b"], "src/") -> ["src/a", "src/b"]; a string works too
            if len(args) != 2:
                raise self.err(f"{name}(list, text) takes two arguments", node)
            text = stringify(args[1])
            items = args[0] if isinstance(args[0], list) else [args[0]]
            result = [text + stringify(x) if name == "prefix" else stringify(x) + text
                      for x in items]
            return result if isinstance(args[0], list) else result[0]
        if name == "len":
            return len(args[0])
        if name == "get":
            default = args[2] if len(args) > 2 else ""
            return args[0].get(stringify(args[1]), default)
        raise self.err(f"unknown function {name}()", node)

    # --- configure-time conditions -----------------------------------------

    def condition(self, node) -> str:
        """Render an expression as CMake if() syntax rather than evaluating it."""
        if isinstance(node, N.Unary):
            return f"NOT {self.condition(node.operand)}"
        if isinstance(node, N.Binary):
            if node.op in ("&&", "||"):
                joiner = "AND" if node.op == "&&" else "OR"
                return (f"{self.condition(node.left)} {joiner} "
                        f"{self.condition(node.right)}")
            left, right = node.left, node.right
            numeric = isinstance(right, N.Num) or isinstance(left, N.Num)
            table = {"==": "EQUAL" if numeric else "STREQUAL",
                     "!=": "EQUAL" if numeric else "STREQUAL",
                     "<": "LESS", ">": "GREATER",
                     "<=": "LESS_EQUAL", ">=": "GREATER_EQUAL"}
            expr = f"{self.condition(left)} {table[node.op]} {self.condition(right)}"
            return f"NOT ({expr})" if node.op == "!=" else expr
        if isinstance(node, N.CallExpr):
            unary = {"defined": "DEFINED", "exists": "EXISTS",
                     "target": "TARGET", "command": "COMMAND"}
            if node.name in unary and len(node.args) == 1:
                return f"{unary[node.name]} {self.condition(node.args[0])}"
            if node.name == "var" and len(node.args) == 1:
                # like vars.X: a variable is named bare in a condition
                return stringify(self.eval(node.args[0]))
            raise self.err(f"{node.name}() is not valid in a when(...) condition",
                           node)
        if isinstance(node, N.Member):
            # In a CMake condition a variable is named bare, not dereferenced.
            rendered = stringify(self.eval(node))
            if rendered.startswith("${") and rendered.endswith("}"):
                return rendered[2:-1]
            return rendered
        if isinstance(node, N.Ident):
            value, found = self.lookup(node.name)
            return cm_quote(value) if found else node.name
        if isinstance(node, (N.Str, N.Template)):
            # Always quoted: an unquoted word in if() is re-read as a variable
            # name if one by that name happens to be defined.
            return cm_quote(self.eval(node))
        return cm_value(self.eval(node))
