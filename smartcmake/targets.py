"""Targets: declaring them, binding them to a value, and applying settings.

The three ways to set something on a target all land here — inside the
declaration block, on a handle (`app.link(core)`), and in a reopened block
(`app { link: [core] }`). Only the first can fold into `add_executable` /
`add_library`; the other two are written after it and must be commands of their
own.
"""

from __future__ import annotations

from . import ir
from . import nodes as N
from .render import wrap_comment
from .tables import FILE_SET_KEYS, HANDLE_METHODS, TARGET_LISTS, VISIBILITIES
from .values import TargetHandle, cm_list, cm_value, flatten, stringify


class TargetCtx:
    """The target a body is being read for."""

    def __init__(self, kind: str, name: str, qualifier: str | None,
                 declared: bool = False):
        self.kind = kind
        self.name = name
        self.qualifier = qualifier
        self.sources: list[str] = []
        self.has_file_set = False
        self.doc: str = ""
        # True for an `app { ... }` block: add_executable/add_library is already
        # in the output, so nothing can be folded back into it.
        self.declared = declared


class TargetsMixin:
    """Mixed into Analyzer; relies on its scopes, `eval`, `err` and
    `emit_statement`."""

    def emit_target(self, st: N.Target, out: list) -> TargetHandle:
        # The first target written at directory scope is where the gtest
        # preamble goes. Claimed here, by the code that actually declares a
        # target, so any future way of reaching this point is covered too.
        if out is self.nodes and self.first_target_slot is None:
            self.first_target_slot = self.statement_slot

        name = str(self.eval(st.name))
        ctx = TargetCtx(st.kind, name, st.qualifier)
        handle = TargetHandle(st.kind, name, st.qualifier)

        body: list = []
        self.push()
        self.define("self", handle)
        for sub in st.body:
            self.emit_statement(sub, body, ctx)
        self.pop()

        if st.kind == "executable":
            command, args = "add_executable", [name, *ctx.sources]
        elif st.kind == "interface":
            command, args = "add_library", [name, "INTERFACE", *ctx.sources]
        elif st.qualifier == "DEFAULT":
            # No kind at all: CMake's own default, STATIC unless BUILD_SHARED_LIBS.
            command, args = "add_library", [name, *ctx.sources]
        else:
            command, args = "add_library", [name, st.qualifier or "STATIC",
                                            *ctx.sources]

        # Sources may still arrive after the declaration (a handle's
        # `sources(...)`, a `fileSet`, a reopened block), which is ordinary
        # CMake, so the check waits for the end of the file.
        if not ctx.sources and not ctx.has_file_set and st.kind != "interface":
            self.sourceless.setdefault(name, st)

        if not st.comments:
            # emit_statement already spaced the block when it had comments.
            out.append(ir.Blank())
        if ctx.doc:
            out.append(ir.Comment(wrap_comment(ctx.doc)))
        out.append(ir.Command(command, args))
        out.extend(body)
        return handle

    # --- targets as values -------------------------------------------------

    def handle_of(self, node, what: str) -> TargetHandle:
        if isinstance(node, N.Ident):
            value, found = self.lookup(node.name)
            # An unbound name would otherwise fall back to a bare CMake word and
            # be reported as "not a target", which hides the real problem: it is
            # not declared yet. CMake needs the declaration first too.
            if not found:
                raise self.err(
                    f"unknown target {node.name!r} — declare it before use, "
                    f'e.g. `const {node.name} = executable("{node.name}") '
                    "{ ... }`", node)
        else:
            value = self.eval(node)
        if isinstance(value, TargetHandle):
            return value
        named = repr(node.name) if isinstance(node, N.Ident) else "that value"
        raise self.err(f"{named} is not a target, so {what} does not apply "
                       "to it", node)

    def emit_method_call(self, st: N.MethodCall, out: list) -> None:
        handle = self.handle_of(st.obj, f"{st.name}(...)")
        args = [self.eval(a) for a in st.args]

        # `sources` is the odd one out only in which command it becomes: the
        # declaration is already written, so it cannot fold into add_executable
        # / add_library the way a `sources:` inside the block does.
        command = TARGET_LISTS.get(
            st.name, "target_sources" if st.name == "sources" else None)
        if command is not None:
            vis, rest = self.method_visibility(args, handle)
            if not rest:
                raise self.err(f"{st.name}(...) needs at least one value", st)
            values = cm_list(flatten(rest))
            # Written but empty — `t.link(suite.extra)` where `extra` defaulted
            # to []. That is ordinary data-driven code, not a mistake, and a
            # bare target_link_libraries(t PRIVATE) is only noise.
            if values:
                out.append(ir.Command(command, [handle.name, vis, *values]))
                if st.name == "sources":
                    self.sourceless.pop(handle.name, None)
            return

        if st.name == "fileSet":
            vis, rest = self.method_visibility(args, handle)
            if len(rest) != 1 or not isinstance(rest[0], dict):
                raise self.err("fileSet(...) takes an optional visibility and one "
                               "{ files: [...] } object", st)
            command = self.file_set_command(handle.name, vis, rest[0], st)
            if command is not None:
                out.append(command)
                self.sourceless.pop(handle.name, None)
            return

        if st.name == "properties":
            if len(args) != 1 or not isinstance(args[0], dict):
                raise self.err("properties(...) takes one { key: value } object", st)
            out.append(ir.Command("set_target_properties",
                                  _properties_args(handle.name, args[0])))
            return

        if st.name == "discoverTests":
            self.needs_gtest = True
            out.append(ir.Command("gtest_discover_tests",
                                  [handle.name, *cm_list(flatten(args))]))
            return

        if st.name == "alias":
            if len(args) != 1:
                raise self.err("alias(...) takes one name", st)
            out.append(ir.Command(_alias_command(handle.kind),
                                  [cm_value(args[0]), "ALIAS", handle.name]))
            return

        raise self.err(f"a target has no {st.name}(); available: "
                       f"{', '.join(sorted(HANDLE_METHODS))}", st)

    def method_visibility(self, args: list, handle: TargetHandle) -> tuple[str, list]:
        """`app.link(PUBLIC, core)`. PUBLIC/PRIVATE/INTERFACE are reserved in
        CMake and cannot name a target, so a leading one is never ambiguous."""
        default = "INTERFACE" if handle.kind == "interface" else "PRIVATE"
        if args and isinstance(args[0], str) and args[0] in VISIBILITIES:
            return args[0], args[1:]
        return default, args

    def emit_reopen(self, st: N.Reopen, out: list) -> None:
        """`app { link: [core] }` — the whole target vocabulary, applied to a
        target declared earlier."""
        handle = self.handle_of(st.obj, "a target block")
        ctx = TargetCtx(handle.kind, handle.name, handle.qualifier, declared=True)
        self.push()
        self.define("self", handle)
        for sub in st.body:
            self.emit_statement(sub, out, ctx)
        self.pop()

    # --- settings inside a target body -------------------------------------

    def emit_target_setting(self, st: N.Setting, value, out: list,
                            ctx: TargetCtx) -> None:
        if st.name == "sources":
            if ctx.declared:
                files = cm_list(value)
                if files:
                    out.append(ir.Command(
                        "target_sources",
                        [ctx.name, self.visibility(st, ctx), *files]))
                    self.sourceless.pop(ctx.name, None)
                return
            ctx.sources.extend(cm_list(value))
            return

        if st.name == "fileSet":
            if not isinstance(value, dict):
                raise self.err("fileSet expects { files: [...], baseDirs: [...], "
                               "name: ..., type: ... }", st)
            command = self.file_set_command(ctx.name, self.visibility(st, ctx),
                                            value, st)
            if command is not None:
                out.append(command)
                ctx.has_file_set = True
                self.sourceless.pop(ctx.name, None)
            return

        if st.name == "doc":
            if ctx.declared:
                raise self.err("doc: belongs where the target is declared — it "
                               "becomes the comment above add_executable / "
                               "add_library, which is already written", st)
            # A data-driven comment: emitted above the target declaration, so
            # a generated target can still explain itself.
            ctx.doc = stringify(value)
            return

        if st.name == "properties":
            if not isinstance(value, dict):
                raise self.err("properties expects { key: value, ... }", st)
            out.append(ir.Command("set_target_properties",
                                  _properties_args(ctx.name, value)))
            return

        if st.name in TARGET_LISTS:
            values = cm_list(value)
            # An empty list is a no-op, not a bare `target_link_libraries(t
            # PRIVATE)`; record fields that default to [] make this routine.
            if values:
                out.append(ir.Command(
                    TARGET_LISTS[st.name],
                    [ctx.name, self.visibility(st, ctx), *values]))
            return

        raise self.err(f"unknown target setting {st.name!r}", st)

    def file_set_command(self, target: str, vis: str, spec: dict, st):
        """`target_sources(<t> <VIS> FILE_SET <name> [TYPE <type>] [BASE_DIRS
        ...] FILES ...)`. `name` defaults to HEADERS; TYPE is only written when
        it differs from the name, since HEADERS and CXX_MODULES name their own
        type."""
        unknown = set(spec) - set(FILE_SET_KEYS)
        if unknown:
            raise self.err(f"unknown fileSet key(s) {', '.join(sorted(unknown))}; "
                           f"expected {', '.join(FILE_SET_KEYS)}", st)
        files = cm_list(spec.get("files", []))
        if not files:
            return None  # an empty set, e.g. a record field defaulting to []
        name = stringify(spec.get("name", "HEADERS"))
        args: list = [target, vis, ["FILE_SET", cm_value(name)]]
        set_type = stringify(spec.get("type", ""))
        if set_type and set_type != name:
            args.append(["TYPE", cm_value(set_type)])
        if name not in ("HEADERS", "CXX_MODULES") and not set_type:
            raise self.err(f"file set {name!r} needs a type: HEADERS or CXX_MODULES", st)
        base_dirs = cm_list(spec.get("baseDirs", []))
        if base_dirs:
            args.append(["BASE_DIRS", *base_dirs])
        args += ["FILES", *files]
        return ir.Command("target_sources", args)

    def visibility(self, st: N.Setting, ctx: TargetCtx) -> str:
        if not st.args:
            return "INTERFACE" if ctx.kind == "interface" else "PRIVATE"
        vis = str(self.eval(st.args[0]))
        if vis not in VISIBILITIES:
            raise self.err(f"visibility must be one of {', '.join(VISIBILITIES)}", st)
        return vis


def _properties_args(target: str, mapping: dict) -> list:
    args = [target, "PROPERTIES"]
    for key, val in mapping.items():
        args += [key, cm_value(val)]
    return args


def _alias_command(kind: str) -> str:
    return "add_executable" if kind == "executable" else "add_library"
