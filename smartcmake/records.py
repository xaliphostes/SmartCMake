"""`record` declarations and the type checking they enable.

Records are transpile-time only: nothing here produces IR. What they produce is
a checked value — an object literal comes back with its defaults filled in, so
a field with a default is always present afterwards and `get(x, "f", ...)` is
never needed to read one.
"""

from __future__ import annotations

import difflib
from typing import Any

from . import nodes as N
from .tables import PRIMITIVE_TYPES
from .values import TargetHandle


class RecordType:
    """A declared record. Defaults are evaluated once, at declaration, so they
    see the scope the record was written in rather than wherever it is used."""

    def __init__(self, name: str, fields: list):
        self.name = name
        self.fields = fields  # [(name, TypeRef, default_value, has_default)]

    @property
    def field_names(self) -> set:
        return {f[0] for f in self.fields}


class RecordsMixin:
    """Mixed into Analyzer; relies on its `records`, `eval` and `err`."""

    def declare_record(self, st: N.RecordDecl) -> None:
        if st.name in PRIMITIVE_TYPES:
            raise self.err(f"{st.name!r} is a built-in type", st)
        if st.name in self.records:
            raise self.err(f"record {st.name!r} is already defined", st)

        fields = []
        seen: set[str] = set()
        for f in st.fields:
            if f.name in seen:
                raise self.err(f"record {st.name!r} declares {f.name!r} twice", f)
            seen.add(f.name)
            # A record may refer to itself or to one declared earlier, but not
            # to one declared later — the same rule `function` already follows.
            self.check_type_exists(f.type_ref, f, allow=st.name)
            default = self.eval(f.default) if f.has_default else None
            if f.has_default:
                default = self.check_type(default, f.type_ref, f,
                                          f"{st.name}.{f.name} default")
            fields.append((f.name, f.type_ref, default, f.has_default))
        self.records[st.name] = RecordType(st.name, fields)

    def check_type_exists(self, ref: N.TypeRef, node, allow: str = "") -> None:
        if ref.name in PRIMITIVE_TYPES or ref.name in self.records or ref.name == allow:
            return
        known = [*PRIMITIVE_TYPES, *self.records]
        raise self.err(f"unknown type {ref.name!r}{suggest(ref.name, known)}", node)

    def check_type(self, value, ref: N.TypeRef, node, path: str):
        """Validate `value` against `ref`, returning it with record defaults
        filled in."""
        if ref.dims:
            if not isinstance(value, list):
                raise self.err(f"{path} should be {type_name(ref)}, "
                               f"got {value_kind(value)}", node)
            inner = N.TypeRef(ref.name, ref.dims - 1, ref.line)
            return [self.check_type(v, inner, node, f"{path}[{i}]")
                    for i, v in enumerate(value)]

        name = ref.name
        if name == "any":
            return value
        if name == "list":
            ok = isinstance(value, list)
        elif name == "string":
            ok = isinstance(value, str)
        elif name == "number":
            # bool is an int in Python; `true` is not a number here.
            ok = isinstance(value, (int, float)) and not isinstance(value, bool)
        elif name == "bool":
            ok = isinstance(value, bool)
        elif name == "target":
            ok = isinstance(value, TargetHandle)
        else:
            record = self.records.get(name)
            if record is None:
                self.check_type_exists(ref, node)  # raises if genuinely unknown
                raise self.err(f"{name} is still being declared here, so it "
                               "cannot be given a default of its own type", node)
            return self.check_record(value, record, node, path)

        if not ok:
            raise self.err(f"{path} should be {type_name(ref)}, "
                           f"got {value_kind(value)}", node)
        return value

    def check_record(self, value, record: RecordType, node, path: str) -> dict:
        if not isinstance(value, dict):
            raise self.err(f"{path} should be a {record.name} object, "
                           f"got {value_kind(value)}", node)
        known = record.field_names
        for key in value:
            if key not in known:
                raise self.err(
                    f"{record.name} has no field {key!r}; it has "
                    f"{', '.join(sorted(known))}{suggest(key, known)}", node)

        out: dict[str, Any] = {}
        for fname, type_ref, default, has_default in record.fields:
            if fname in value:
                out[fname] = self.check_type(value[fname], type_ref, node,
                                             f"{path}.{fname}")
            elif has_default:
                out[fname] = default
            else:
                raise self.err(f"{path} is missing {fname!r} "
                               f"({type_name(type_ref)}), which {record.name} "
                               "declares without a default", node)
        return out


def type_name(ref: N.TypeRef) -> str:
    return ref.name + "[]" * ref.dims


def value_kind(value: Any) -> str:
    """How a wrongly-typed value is described back to the author."""
    if isinstance(value, TargetHandle):
        return f"the target {value.name!r}"
    if isinstance(value, bool):
        return "true" if value else "false"  # as written in the source, not ON/OFF
    if isinstance(value, (int, float)):
        return f"the number {value}"
    if isinstance(value, str):
        return f"the string {value!r}"
    if isinstance(value, list):
        return "a list"
    if isinstance(value, dict):
        return "an object"
    return type(value).__name__


def suggest(name: str, known) -> str:
    """A typo is the whole reason records exist, so name the likely intent."""
    close = difflib.get_close_matches(name, sorted(known), n=1, cutoff=0.7)
    return f" — did you mean {close[0]!r}?" if close else ""
