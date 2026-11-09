"""The rest of the statement vocabulary: project, set, install, fetch,
function, directory-scope settings and bare calls.

Everything here turns one statement into one or more IR commands. The tables
that say *which* command live in `tables`; this file is the shape of the
arguments and the rules about them.
"""

from __future__ import annotations

from typing import Any

from . import ir
from . import nodes as N
from .astutil import find_call
from .tables import (BUILTIN_STATEMENTS, DIRECTORY_CALLS, DIRECTORY_LISTS,
                     FETCH_KEYS, INSTALL_ARTIFACTS, INSTALL_FLAGS, INSTALL_KEYS,
                     INSTALL_KINDS, INSTALL_WORDS, SIMPLE_VARS)
from .values import cm_list, cm_quote, cm_value, truthy

PROJECT_HEADER_KEYS = {"cmakeMinimum", "version", "languages", "description"}


class CommandsMixin:
    """Mixed into Analyzer; relies on its state, `eval`, `err` and
    `emit_statement`."""

    def emit_project(self, st: N.Project, out: list) -> None:
        header: dict[str, Any] = {}
        rest = []
        for sub in st.body:
            if (isinstance(sub, N.Setting) and sub.name in PROJECT_HEADER_KEYS
                    and not sub.args):
                header[sub.name] = self.eval(sub.value)
            else:
                rest.append(sub)

        if "cmakeMinimum" in header and not self.minimum_emitted:
            out.append(minimum_command(header["cmakeMinimum"]))
            out.append(ir.Blank())

        args: list = [st.name]
        if "version" in header:
            args += ["VERSION", cm_value(header["version"])]
        if "description" in header:
            args += ["DESCRIPTION", cm_value(header["description"])]
        langs = header.get("languages", ["CXX"])
        if not isinstance(langs, list):
            langs = [langs]
        args += ["LANGUAGES", *[str(x) for x in langs]]
        out.append(ir.Command("project", args))
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
        out.append(ir.Command("set", args))

    def emit_install(self, st: N.Install, out: list, ctx) -> None:
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
        if "fileSets" in opts and key != "targets":
            raise self.err("fileSets only applies to install { targets: ... }", st)
        for name, keyword in INSTALL_ARTIFACTS:
            if name == "includes":
                # FILE_SET <name> belongs with the artifact kinds, before INCLUDES
                for file_set in cm_list(opts.get("fileSets", [])):
                    args.append(["FILE_SET", file_set])
            if name in opts:
                args.append([keyword, "DESTINATION", cm_value(opts[name])])
        for name, keyword in INSTALL_WORDS:
            if name in opts:
                args.append([keyword, *cm_list(opts[name])])
        for name, keyword in INSTALL_FLAGS:
            if truthy(opts.get(name, False)):
                args.append([keyword])

        out.append(ir.Command("install", args))

    def emit_function(self, st: N.Function, out: list) -> None:
        if st.name in BUILTIN_STATEMENTS:
            raise self.err(f"function {st.name!r} shadows a built-in statement, "
                           "so calls to it would emit the built-in instead", st)
        if st.name in self.functions:
            raise self.err(f"function {st.name!r} is already defined", st)
        # CMake only honours enable_testing() at directory scope: inside a
        # function it is accepted and then quietly produces no CTestTestfile,
        # so the whole suite disappears without an error anywhere.
        buried = find_call(st.body, "enableTesting")
        if buried is not None:
            raise self.err("enableTesting() does not work inside a function — CMake "
                           "honours it at directory scope only; call it there instead",
                           buried)
        # Registered before the body is walked so a function can recurse.
        self.functions.add(st.name)

        body: list = []
        self.push()
        # Parameters and CMake's implicit argument variables are bound to their
        # own expansions, so the body says `target_name`, not `vars.target_name`.
        for name in (*st.params, "ARGC", "ARGN", "ARGV"):
            self.define(name, "${" + name + "}")
        for sub in st.body:
            self.emit_statement(sub, body, None)
        self.pop()
        while body and isinstance(body[0], ir.Blank):
            body.pop(0)  # targets space themselves; not wanted after function(

        if not st.comments:
            # emit_statement already spaced the block when it had comments.
            out.append(ir.Blank())
        out.append(ir.Block(f"function({' '.join([st.name, *st.params])})",
                            body, "endfunction()"))
        out.append(ir.Blank())

    def emit_fetch(self, st: N.Fetch, out: list) -> None:
        opts: dict[str, Any] = {}
        for sub in st.body:
            if not isinstance(sub, N.Setting) or sub.args:
                raise self.err("a fetch block only accepts `key: value` settings", sub)
            opts[sub.name] = self.eval(sub.value)

        if not self.fetch_included:
            out.append(ir.Command("include", ["FetchContent"]))
            self.fetch_included = True

        args: list = [st.name]
        for key, cmake_key in FETCH_KEYS:
            if key in opts:
                args.append([cmake_key, cm_value(opts[key])])
        out.append(ir.Command("FetchContent_Declare", args, force_wrap=True))

        for key, value in opts.get("options", {}).items():
            kind = "BOOL" if isinstance(value, bool) else "STRING"
            out.append(ir.Command(
                "set", [key, cm_value(value), ["CACHE", kind, '""', "FORCE"]]))

        out.append(ir.Command("FetchContent_MakeAvailable", [st.name]))

    # --- settings and calls ------------------------------------------------

    def emit_setting(self, st: N.Setting, out: list, ctx) -> None:
        value = self.eval(st.value)

        if ctx is not None:
            self.emit_target_setting(st, value, out, ctx)
            return

        if st.args:
            raise self.err(f"{st.name!r} takes no qualifier at this scope", st)

        if st.name in SIMPLE_VARS:
            out.append(ir.Command("set", [SIMPLE_VARS[st.name], cm_value(value)]))
            return
        if st.name in DIRECTORY_LISTS:
            values = cm_list(value)
            if values:
                out.append(ir.Command(DIRECTORY_LISTS[st.name], values))
            return
        raise self.err(f"unknown setting {st.name!r}", st)

    def spread_args(self, nodes: list) -> list[str]:
        """Arguments of a raw CMake command: a list contributes one argument per
        element, as `cmake("target_sources", t, PRIVATE, FILES)` callers mean,
        rather than one `a;b;c` string."""
        args: list[str] = []
        for node in nodes:
            value = self.eval(node)
            args.extend(cm_list(value) if isinstance(value, list) else [cm_value(value)])
        return args

    def emit_call(self, st: N.Call, out: list, ctx) -> None:
        args = [cm_value(self.eval(a)) for a in st.args]

        if ctx is not None and st.name == "discoverTests":
            self.needs_gtest = True
            out.append(ir.Command("gtest_discover_tests", [ctx.name, *args]))
            return
        if ctx is not None and st.name == "alias":
            if len(args) != 1:
                raise self.err("alias(...) takes one name", st)
            cmd = "add_executable" if ctx.kind == "executable" else "add_library"
            out.append(ir.Command(cmd, [args[0], "ALIAS", ctx.name]))
            return

        if st.name in DIRECTORY_CALLS:
            cmake_name, arity = DIRECTORY_CALLS[st.name]
            if arity == 0 and args:
                raise self.err(f"{st.name}() takes no arguments", st)
            if st.name == "enableTesting":
                self.has_enable_testing = True
            if st.name == "include" and args and args[0] == "GoogleTest":
                self.has_gtest_include = True
            out.append(ir.Command(cmake_name, args))
            return

        if st.name == "findPackage":
            out.append(ir.Command("find_package", self.spread_args(st.args)))
            return
        if st.name == "message":
            text = [cm_quote(self.eval(a)) for a in st.args]
            out.append(ir.Command("message", ["STATUS", *text]))
            return
        if st.name == "cmake":
            spread = self.spread_args(st.args)
            out.append(ir.Command(spread[0].strip('"'), spread[1:]))
            return
        if st.name in self.functions:
            out.append(ir.Command(st.name, args))
            return

        raise self.err(f"unknown command {st.name}()", st)


def minimum_command(version) -> ir.Command:
    """A single group, so the version can never be wrapped away from VERSION."""
    return ir.Command("cmake_minimum_required", [["VERSION", version]])
