"""AST -> CMakeLists.txt.

Evaluation and emission happen in a single pass. `const`, `for` and `if` are
transpile-time constructs and disappear from the output; `set`, `when` and the
target/settings vocabulary become CMake commands.
"""

from __future__ import annotations

import difflib
from typing import Any

from . import nodes as N
from .errors import ScmakeError

WRAP_AT = 88

# Settings that map straight onto a CMake variable.
SIMPLE_VARS = {
    "cxx": "CMAKE_CXX_STANDARD",
    "c": "CMAKE_C_STANDARD",
    "standardRequired": "CMAKE_CXX_STANDARD_REQUIRED",
    "extensions": "CMAKE_CXX_EXTENSIONS",
    "scanForModules": "CMAKE_CXX_SCAN_FOR_MODULES",
    "buildType": "CMAKE_BUILD_TYPE",
    "positionIndependent": "CMAKE_POSITION_INDEPENDENT_CODE",
    "exportCompileCommands": "CMAKE_EXPORT_COMPILE_COMMANDS",
    "cxxCompiler": "CMAKE_CXX_COMPILER",
    "cCompiler": "CMAKE_C_COMPILER",
    "prefixPath": "CMAKE_PREFIX_PATH",
    "runtimeOutputDir": "CMAKE_RUNTIME_OUTPUT_DIRECTORY",
    "libraryOutputDir": "CMAKE_LIBRARY_OUTPUT_DIRECTORY",
    "archiveOutputDir": "CMAKE_ARCHIVE_OUTPUT_DIRECTORY",
}

# Directory-scope settings that take a list.
DIRECTORY_LISTS = {
    "compileOptions": "add_compile_options",
    "linkOptions": "add_link_options",
    "defines": "add_compile_definitions",
    "includeDirs": "include_directories",
    "linkDirs": "link_directories",
}

# Target-scope settings; all take an optional visibility qualifier.
TARGET_LISTS = {
    "include": "target_include_directories",
    "link": "target_link_libraries",
    "compileOptions": "target_compile_options",
    "linkOptions": "target_link_options",
    "defines": "target_compile_definitions",
    "features": "target_compile_features",
}

VISIBILITIES = ("PRIVATE", "PUBLIC", "INTERFACE")

# install { ... }. What is being installed comes first in CMake's grammar, so
# these three tables are emitted in order and never in the order they were
# written; `export` is a kind on its own but a modifier next to `targets`.
INSTALL_KINDS = (
    ("targets", "TARGETS"),
    ("files", "FILES"),
    ("programs", "PROGRAMS"),
    ("directory", "DIRECTORY"),
    ("export", "EXPORT"),
)

# Per-artifact destinations, emitted as `<WORD> DESTINATION <dir>`.
INSTALL_ARTIFACTS = (
    ("runtime", "RUNTIME"),
    ("library", "LIBRARY"),
    ("archive", "ARCHIVE"),
    ("bundle", "BUNDLE"),
    ("framework", "FRAMEWORK"),
    ("includes", "INCLUDES"),
)

INSTALL_WORDS = (
    ("destination", "DESTINATION"),
    ("namespace", "NAMESPACE"),
    ("file", "FILE"),
    ("rename", "RENAME"),
    ("component", "COMPONENT"),
    ("configurations", "CONFIGURATIONS"),
    ("permissions", "PERMISSIONS"),
    ("pattern", "PATTERN"),
)

INSTALL_FLAGS = (("optional", "OPTIONAL"), ("excludeFromAll", "EXCLUDE_FROM_ALL"))

INSTALL_KEYS = {k for k, _ in (*INSTALL_KINDS, *INSTALL_ARTIFACTS,
                               *INSTALL_WORDS, *INSTALL_FLAGS)}

DIRECTORY_CALLS = {
    "enableTesting": ("enable_testing", 0),
    "subdirectory": ("add_subdirectory", 1),
    "include": ("include", 1),
}

# Names emit_call resolves before user-defined functions. A function using one
# of these would never be reached, so defining it is an error rather than a
# silent shadow.
BUILTIN_STATEMENTS = {*DIRECTORY_CALLS, "findPackage", "message", "cmake",
                      "discoverTests", "alias", "install", "raw"}


# Field types a `record` can use, beyond the records already declared. `list`
# is `any[]`, which is what most build data wants: a list of names whose
# elements may be strings, targets or namespaced references alike.
PRIMITIVE_TYPES = ("string", "number", "bool", "target", "list", "any")

# Target settings reachable as `app.<name>(...)` on a handle. Everything here
# is a standalone CMake command, which is what lets it be written after the
# declaration rather than inside it.
HANDLE_METHODS = (*TARGET_LISTS, "sources", "properties", "discoverTests", "alias")


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


class RecordType:
    """A declared record. Defaults are evaluated once, here, so they see the
    scope the record was written in rather than wherever it is later used."""

    def __init__(self, name: str, fields: list):
        self.name = name
        self.fields = fields  # [(name, TypeRef, default_value, has_default)]

    @property
    def field_names(self) -> set:
        return {f[0] for f in self.fields}


class TargetCtx:
    def __init__(self, kind: str, name: str, qualifier: str | None,
                 declared: bool = False):
        self.kind = kind
        self.name = name
        self.qualifier = qualifier
        self.sources: list[str] = []
        self.doc: str = ""
        # True for a `app { ... }` block: add_executable/add_library is already
        # in the output, so nothing can be folded back into it.
        self.declared = declared


class Emitter:
    def __init__(self, filename: str = "build.scmake"):
        self.filename = filename
        self.lines: list[str] = []
        self.scopes: list[dict[str, Any]] = [{}]
        self.fetch_included = False
        self.needs_gtest = False
        self.has_gtest_include = False
        self.has_enable_testing = False
        self.header_slot = 0
        self.first_target_slot: int | None = None
        self.minimum_emitted = False
        self.functions: set[str] = set()
        self.records: dict[str, RecordType] = {}

    # --- entry point ------------------------------------------------------

    def run(self, program: list) -> str:
        self.lines.append(f"# Generated by SmartCMake from {self.filename} — do not edit.")
        self.lines.append("")
        # cmake_minimum_required must be the first command in the file, whatever
        # order the source puts things in, so it is hoisted out of the project.
        for st in program:
            if isinstance(st, N.Project):
                minimum = _find_setting(st.body, "cmakeMinimum")
                if minimum is not None:
                    self.lines.append(
                        f"cmake_minimum_required(VERSION {self.eval(minimum)})")
                    self.minimum_emitted = True
                break
        self.header_slot = len(self.lines)
        for st in program:
            self.emit_statement(st, self.lines)
        self._insert_auto_includes()
        return _normalize(self.lines)

    def _insert_auto_includes(self) -> None:
        auto = []
        if self.needs_gtest:
            if not self.has_enable_testing:
                auto.append("enable_testing()")
            if not self.has_gtest_include:
                auto.append("include(GoogleTest)")
        if not auto:
            return
        slot = self.first_target_slot
        if slot is None:
            slot = self.header_slot
        self.lines[slot:slot] = ["", *auto]

    # --- scopes -----------------------------------------------------------

    def push(self) -> None:
        self.scopes.append({})

    def pop(self) -> None:
        self.scopes.pop()

    def define(self, name: str, value: Any) -> None:
        self.scopes[-1][name] = value

    def lookup(self, name: str):
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name], True
        return None, False

    def err(self, msg: str, node) -> ScmakeError:
        return ScmakeError(msg, getattr(node, "line", 0), 0, self.filename)

    # --- statement dispatch -----------------------------------------------

    def emit_statement(self, st, out: list, ctx: TargetCtx | None = None) -> None:
        # Anchor the auto-include slot above the first target's comment block,
        # not between the comment and the command it describes.
        if (_declares_target(st) and out is self.lines
                and self.first_target_slot is None):
            self.first_target_slot = len(out)

        if isinstance(st, N.CommentBlock):
            out.append("")
            out.extend(f"# {c}" if c else "#" for c in st.lines)
            out.append("")
            return

        mark = len(out)
        if st.comments:
            out.append("")
            out.extend(f"# {c}" if c else "#" for c in st.comments)
        after_comments = len(out)

        self.dispatch(st, out, ctx)

        # A comment on a transpile-time statement documents the .scmake, not the
        # CMake; if the statement emitted nothing, the comment goes with it.
        if st.comments and len(out) == after_comments:
            del out[mark:]

    def dispatch(self, st, out: list, ctx: TargetCtx | None) -> None:
        if isinstance(st, N.Project):
            self.emit_project(st, out)
        elif isinstance(st, N.ConstDecl):
            # A target on the right-hand side is declared here and bound as a
            # handle; every other value is an ordinary transpile-time binding.
            if isinstance(st.value, N.Target):
                if st.type_ref is not None:
                    raise self.err("a target declaration cannot be annotated — "
                                   "its type is the kind of target it declares", st)
                # The comment block sits on the const, but it documents the
                # target; hand it over so emit_target does not space it away.
                st.value.comments = st.comments
                self.define(st.name, self.emit_target(st.value, out))
            else:
                value = self.eval(st.value)
                if st.type_ref is not None:
                    # Up front: check_type only reaches the name through the
                    # elements, so `const X: Suit[] = []` would never resolve it.
                    self.check_type_exists(st.type_ref, st)
                    value = self.check_type(value, st.type_ref, st, st.name)
                self.define(st.name, value)
        elif isinstance(st, N.RecordDecl):
            self.declare_record(st)
        elif isinstance(st, N.SetVar):
            self.emit_set(st, out)
        elif isinstance(st, N.ForOf):
            self.emit_for(st, out, ctx)
        elif isinstance(st, N.If):
            self.emit_if(st, out, ctx)
        elif isinstance(st, N.When):
            self.emit_when(st, out, ctx)
        elif isinstance(st, N.Target):
            self.emit_target(st, out)
        elif isinstance(st, N.MethodCall):
            self.emit_method_call(st, out)
        elif isinstance(st, N.Reopen):
            self.emit_reopen(st, out)
        elif isinstance(st, N.Fetch):
            self.emit_fetch(st, out)
        elif isinstance(st, N.Function):
            self.emit_function(st, out)
        elif isinstance(st, N.Install):
            self.emit_install(st, out, ctx)
        elif isinstance(st, N.Raw):
            out.extend(str(self.eval(st.value)).splitlines() or [""])
        elif isinstance(st, N.Setting):
            self.emit_setting(st, out, ctx)
        elif isinstance(st, N.Call):
            self.emit_call(st, out, ctx)
        else:  # pragma: no cover - every node type is handled above
            raise self.err(f"unsupported statement {type(st).__name__}", st)

    # --- statements -------------------------------------------------------

    def emit_project(self, st: N.Project, out: list) -> None:
        header_keys = {"cmakeMinimum", "version", "languages", "description"}
        header: dict[str, Any] = {}
        rest = []
        for sub in st.body:
            if isinstance(sub, N.Setting) and sub.name in header_keys and not sub.args:
                header[sub.name] = self.eval(sub.value)
            else:
                rest.append(sub)

        if "cmakeMinimum" in header and not self.minimum_emitted:
            out.append(f"cmake_minimum_required(VERSION {header['cmakeMinimum']})")
            out.append("")

        args = [st.name]
        if "version" in header:
            args += ["VERSION", cm_value(header["version"])]
        if "description" in header:
            args += ["DESCRIPTION", cm_value(header["description"])]
        langs = header.get("languages", ["CXX"])
        if not isinstance(langs, list):
            langs = [langs]
        args += ["LANGUAGES", *[str(x) for x in langs]]
        out.extend(render_command("project", args))
        self.header_slot = len(out)

        self.push()
        for sub in rest:
            self.emit_statement(sub, out)
        self.pop()

    def emit_set(self, st: N.SetVar, out: list) -> None:
        args: list = [st.name, cm_value(self.eval(st.value))]
        if st.cache_type:
            cache = ["CACHE", st.cache_type, cm_quote(st.cache_doc)]
            if st.force:
                cache.append("FORCE")
            args.append(cache)
        out.extend(render_command("set", args))

    def emit_for(self, st: N.ForOf, out: list, ctx: TargetCtx | None) -> None:
        items = self.eval(st.iterable)
        if not isinstance(items, list):
            raise self.err("for (... of ...) needs a list", st)
        for item in items:
            self.push()
            self.define(st.var, item)
            for sub in st.body:
                self.emit_statement(sub, out, ctx)
            self.pop()

    def emit_if(self, st: N.If, out: list, ctx: TargetCtx | None) -> None:
        branch = st.then if truthy(self.eval(st.cond)) else st.orelse
        self.push()
        for sub in branch:
            self.emit_statement(sub, out, ctx)
        self.pop()

    def emit_when(self, st: N.When, out: list, ctx: TargetCtx | None) -> None:
        out.append(f"if({self.condition(st.cond)})")
        body: list[str] = []
        self.push()
        for sub in st.then:
            self.emit_statement(sub, body, ctx)
        self.pop()
        out.extend(indent(body))
        if st.orelse:
            out.append("else()")
            body = []
            self.push()
            for sub in st.orelse:
                self.emit_statement(sub, body, ctx)
            self.pop()
            out.extend(indent(body))
        out.append("endif()")

    def emit_install(self, st: N.Install, out: list, ctx: TargetCtx | None) -> None:
        opts: dict[str, Any] = {}
        for sub in st.body:
            if not isinstance(sub, N.Setting) or sub.args:
                raise self.err("install { ... } takes plain 'key: value' entries", st)
            if sub.name not in INSTALL_KEYS:
                raise self.err(f"unknown install setting {sub.name!r}", sub)
            if sub.name in opts:
                raise self.err(f"duplicate install setting {sub.name!r}", sub)
            opts[sub.name] = self.eval(sub.value)

        kinds = [k for k, _ in INSTALL_KINDS if k in opts]
        if "targets" in opts and "export" in kinds:
            kinds.remove("export")  # here EXPORT names the set, it is not the kind
        if len(kinds) > 1:
            raise self.err(f"install has more than one of {', '.join(kinds)}", st)

        if kinds:
            key = kinds[0]
            word = dict(INSTALL_KINDS)[key]
            values = opts[key] if isinstance(opts[key], list) else [opts[key]]
        elif ctx is not None:
            # Inside a target block the target itself is the obvious subject.
            key, word, values = "targets", "TARGETS", [ctx.name]
        else:
            names = ", ".join(k for k, _ in INSTALL_KINDS)
            raise self.err(f"install needs one of: {names}", st)

        args: list = [[word, *cm_list(values)]]
        if key == "targets" and "export" in opts:
            args.append(["EXPORT", cm_value(opts["export"])])
        for name, keyword in INSTALL_ARTIFACTS:
            if name in opts:
                args.append([keyword, "DESTINATION", cm_value(opts[name])])
        for name, keyword in INSTALL_WORDS:
            if name in opts:
                args.append([keyword, *cm_list(opts[name])])
        for name, keyword in INSTALL_FLAGS:
            if truthy(opts.get(name, False)):
                args.append([keyword])

        out.extend(render_command("install", args))

    def emit_function(self, st: N.Function, out: list) -> None:
        if st.name in BUILTIN_STATEMENTS:
            raise self.err(f"function {st.name!r} shadows a built-in statement, "
                           "so calls to it would emit the built-in instead", st)
        if st.name in self.functions:
            raise self.err(f"function {st.name!r} is already defined", st)
        # CMake only honours enable_testing() at directory scope: inside a
        # function it is accepted and then quietly produces no CTestTestfile,
        # so the whole suite disappears without an error anywhere.
        buried = _find_call(st.body, "enableTesting")
        if buried is not None:
            raise self.err("enableTesting() does not work inside a function — CMake "
                           "honours it at directory scope only; call it there instead",
                           buried)
        # Registered before the body is walked so a function can recurse.
        self.functions.add(st.name)

        body: list[str] = []
        self.push()
        # Parameters and CMake's implicit argument variables are bound to their
        # own expansions, so the body says `target_name`, not `vars.target_name`.
        for name in (*st.params, "ARGC", "ARGN", "ARGV"):
            self.define(name, "${" + name + "}")
        for sub in st.body:
            self.emit_statement(sub, body, None)
        self.pop()
        while body and not body[0]:
            body.pop(0)  # targets space themselves; not wanted after function(

        if not st.comments:
            # emit_statement already spaced the block when it had comments.
            out.append("")
        out.append(f"function({' '.join([st.name, *st.params])})")
        out.extend(indent(body))
        out.append("endfunction()")
        out.append("")

    def emit_target(self, st: N.Target, out: list) -> TargetHandle:
        name = str(self.eval(st.name))
        ctx = TargetCtx(st.kind, name, st.qualifier)
        handle = TargetHandle(st.kind, name, st.qualifier)

        body: list[str] = []
        self.push()
        self.define("self", handle)
        for sub in st.body:
            self.emit_statement(sub, body, ctx)
        self.pop()

        if st.kind == "executable":
            decl = ["add_executable", [name, *ctx.sources]]
        elif st.kind == "interface":
            decl = ["add_library", [name, "INTERFACE", *ctx.sources]]
        else:
            kind = st.qualifier or "STATIC"
            decl = ["add_library", [name, kind, *ctx.sources]]

        if not ctx.sources and st.kind != "interface":
            raise self.err(f"target {name!r} has no sources", st)

        if not st.comments:
            # emit_statement already spaced the block when it had comments.
            out.append("")
        if ctx.doc:
            out.extend(f"# {line}" for line in _wrap_comment(ctx.doc))
        out.extend(render_command(decl[0], decl[1]))
        out.extend(body)
        return handle

    # --- records -----------------------------------------------------------

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
        raise self.err(f"unknown type {ref.name!r}{_suggest(ref.name, known)}", node)

    def check_type(self, value, ref: N.TypeRef, node, path: str):
        """Validate `value` against `ref`. Records come back with their defaults
        filled in, so a field with a default is always present afterwards and
        `get(x, "field", ...)` is never needed to read one."""
        if ref.dims:
            if not isinstance(value, list):
                raise self.err(f"{path} should be {_type_name(ref)}, "
                               f"got {_value_kind(value)}", node)
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
            raise self.err(f"{path} should be {_type_name(ref)}, "
                           f"got {_value_kind(value)}", node)
        return value

    def check_record(self, value, record: RecordType, node, path: str) -> dict:
        if not isinstance(value, dict):
            raise self.err(f"{path} should be a {record.name} object, "
                           f"got {_value_kind(value)}", node)
        known = record.field_names
        for key in value:
            if key not in known:
                raise self.err(
                    f"{record.name} has no field {key!r}; it has "
                    f"{', '.join(sorted(known))}{_suggest(key, known)}", node)

        out: dict[str, Any] = {}
        for fname, type_ref, default, has_default in record.fields:
            if fname in value:
                out[fname] = self.check_type(value[fname], type_ref, node,
                                             f"{path}.{fname}")
            elif has_default:
                out[fname] = default
            else:
                raise self.err(f"{path} is missing {fname!r} "
                               f"({_type_name(type_ref)}), which {record.name} "
                               "declares without a default", node)
        return out

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
        command = TARGET_LISTS.get(st.name,
                                   "target_sources" if st.name == "sources" else None)
        if command is not None:
            vis, rest = self.method_visibility(args, handle)
            if not rest:
                raise self.err(f"{st.name}(...) needs at least one value", st)
            values = cm_list(_flatten(rest))
            # Written but empty — `t.link(suite.extra)` where `extra` defaulted
            # to []. That is ordinary data-driven code, not a mistake, and a
            # bare target_link_libraries(t PRIVATE) is only noise.
            if values:
                out.extend(render_command(command, [handle.name, vis, *values]))
            return

        if st.name == "properties":
            if len(args) != 1 or not isinstance(args[0], dict):
                raise self.err("properties(...) takes one { key: value } object", st)
            cmd: list = [handle.name, "PROPERTIES"]
            for key, val in args[0].items():
                cmd += [key, cm_value(val)]
            out.extend(render_command("set_target_properties", cmd))
            return

        if st.name == "discoverTests":
            self.needs_gtest = True
            out.extend(render_command("gtest_discover_tests",
                                      [handle.name, *cm_list(_flatten(args))]))
            return

        if st.name == "alias":
            if len(args) != 1:
                raise self.err("alias(...) takes one name", st)
            cmd_name = "add_executable" if handle.kind == "executable" else "add_library"
            out.extend(render_command(cmd_name,
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

    def emit_fetch(self, st: N.Fetch, out: list) -> None:
        opts: dict[str, Any] = {}
        for sub in st.body:
            if not isinstance(sub, N.Setting) or sub.args:
                raise self.err("a fetch block only accepts `key: value` settings", sub)
            opts[sub.name] = self.eval(sub.value)

        if not self.fetch_included:
            out.append("include(FetchContent)")
            self.fetch_included = True

        args: list = [st.name]
        mapping = [("git", "GIT_REPOSITORY"), ("tag", "GIT_TAG"),
                   ("url", "URL"), ("hash", "URL_HASH"), ("dir", "SOURCE_DIR")]
        for key, cmake_key in mapping:
            if key in opts:
                args.append([cmake_key, cm_value(opts[key])])
        out.extend(render_command("FetchContent_Declare", args, force_wrap=True))

        for key, value in opts.get("options", {}).items():
            kind = "BOOL" if isinstance(value, bool) else "STRING"
            out.extend(render_command(
                "set", [key, cm_value(value), ["CACHE", kind, '""', "FORCE"]]))

        out.append(f"FetchContent_MakeAvailable({st.name})")

    # --- settings and calls ------------------------------------------------

    def emit_setting(self, st: N.Setting, out: list, ctx: TargetCtx | None) -> None:
        value = self.eval(st.value)

        if ctx is not None:
            self.emit_target_setting(st, value, out, ctx)
            return

        if st.args:
            raise self.err(f"{st.name!r} takes no qualifier at this scope", st)

        if st.name in SIMPLE_VARS:
            out.extend(render_command("set", [SIMPLE_VARS[st.name], cm_value(value)]))
            return
        if st.name in DIRECTORY_LISTS:
            values = cm_list(value)
            if values:
                out.extend(render_command(DIRECTORY_LISTS[st.name], values))
            return
        raise self.err(f"unknown setting {st.name!r}", st)

    def emit_target_setting(self, st: N.Setting, value, out: list,
                            ctx: TargetCtx) -> None:
        if st.name == "sources":
            if ctx.declared:
                files = cm_list(value)
                if files:
                    out.extend(render_command(
                        "target_sources",
                        [ctx.name, self.visibility(st, ctx), *files]))
                return
            ctx.sources.extend(cm_list(value))
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
            args = [ctx.name, "PROPERTIES"]
            for key, val in value.items():
                args += [key, cm_value(val)]
            out.extend(render_command("set_target_properties", args))
            return

        if st.name in TARGET_LISTS:
            values = cm_list(value)
            # An empty list is a no-op, not a bare `target_link_libraries(t
            # PRIVATE)`; record fields that default to [] make this routine.
            if values:
                out.extend(render_command(TARGET_LISTS[st.name],
                                          [ctx.name, self.visibility(st, ctx),
                                           *values]))
            return

        raise self.err(f"unknown target setting {st.name!r}", st)

    def visibility(self, st: N.Setting, ctx: TargetCtx) -> str:
        if not st.args:
            return "INTERFACE" if ctx.kind == "interface" else "PRIVATE"
        vis = str(self.eval(st.args[0]))
        if vis not in VISIBILITIES:
            raise self.err(f"visibility must be one of {', '.join(VISIBILITIES)}", st)
        return vis

    def emit_call(self, st: N.Call, out: list, ctx: TargetCtx | None) -> None:
        args = [cm_value(self.eval(a)) for a in st.args]

        if ctx is not None and st.name == "discoverTests":
            self.needs_gtest = True
            out.extend(render_command("gtest_discover_tests", [ctx.name, *args]))
            return
        if ctx is not None and st.name == "alias":
            if len(args) != 1:
                raise self.err("alias(...) takes one name", st)
            cmd = "add_executable" if ctx.kind == "executable" else "add_library"
            out.extend(render_command(cmd, [args[0], "ALIAS", ctx.name]))
            return

        if st.name in DIRECTORY_CALLS:
            cmake_name, arity = DIRECTORY_CALLS[st.name]
            if arity == 0 and args:
                raise self.err(f"{st.name}() takes no arguments", st)
            if st.name == "enableTesting":
                self.has_enable_testing = True
            if st.name == "include" and args and args[0] == "GoogleTest":
                self.has_gtest_include = True
            out.extend(render_command(cmake_name, args))
            return

        if st.name == "findPackage":
            out.extend(render_command("find_package", args))
            return
        if st.name == "message":
            text = [cm_quote(self.eval(a)) for a in st.args]
            out.extend(render_command("message", ["STATUS", *text]))
            return
        if st.name == "cmake":
            out.extend(render_command(args[0].strip('"'), args[1:]))
            return
        if st.name in self.functions:
            out.extend(render_command(st.name, args))
            return

        raise self.err(f"unknown command {st.name}()", st)

    # --- expression evaluation ---------------------------------------------

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
                return f"{self.condition(node.left)} {joiner} {self.condition(node.right)}"
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
            raise self.err(f"{node.name}() is not valid in a when(...) condition", node)
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


# --- rendering helpers ------------------------------------------------------


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


def render_command(name: str, args: list, force_wrap: bool = False) -> list[str]:
    """Render one CMake command, wrapping when it gets long. A list argument is
    a group (`GIT_TAG v1.2.3`) that must never be split across lines."""
    units = [" ".join(str(x) for x in a) if isinstance(a, (list, tuple)) else str(a)
             for a in args]
    one_line = f"{name}({' '.join(units)})"
    if not force_wrap and (len(one_line) <= WRAP_AT or len(units) <= 1):
        return [one_line]
    return [f"{name}(", *[f"    {u}" for u in units], ")"]


def _type_name(ref: N.TypeRef) -> str:
    return ref.name + "[]" * ref.dims


def _value_kind(value: Any) -> str:
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


def _suggest(name: str, known) -> str:
    """A typo is the whole reason records exist, so name the likely intent."""
    close = difflib.get_close_matches(name, sorted(known), n=1, cutoff=0.7)
    return f" — did you mean {close[0]!r}?" if close else ""


def _flatten(values: list) -> list:
    """`app.link(GTest.gtest_main, EXTRA)` where EXTRA is itself a list."""
    out: list = []
    for value in values:
        out.extend(value if isinstance(value, list) else [value])
    return out


def _declares_target(st) -> bool:
    return isinstance(st, N.Target) or (isinstance(st, N.ConstDecl)
                                        and isinstance(st.value, N.Target))


def _find_call(body: list, name: str):
    """Depth-first search for a call to `name`, through every nested body."""
    for st in body:
        if isinstance(st, N.Call) and st.name == name:
            return st
        for attr in ("body", "then", "orelse"):
            nested = getattr(st, attr, None)
            if isinstance(nested, list):
                found = _find_call(nested, name)
                if found is not None:
                    return found
    return None


def _find_setting(body: list, name: str):
    for st in body:
        if isinstance(st, N.Setting) and st.name == name and not st.args:
            return st.value
    return None


def _wrap_comment(text: str, width: int = 76) -> list[str]:
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


def emit(program: list, filename: str = "build.scmake") -> str:
    return Emitter(filename).run(program)
