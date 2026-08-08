"""Statement dispatch, and the statements that are not declarations.

`parse_statement` is where the language's ambiguities are resolved, and the
order of its branches is load-bearing: a keyword sitting before `:` is a
setting key, and the two trailing shapes (`app.link(...)`, `app { ... }`) are
only reached once every keyword has had its turn.
"""

from __future__ import annotations

from .. import nodes as N
from .declarations import TARGET_KEYWORDS


class StatementParser:
    """Mixed into Parser; relies on the Cursor, expression and declaration
    helpers."""

    def parse_program(self) -> list:
        body = []
        while not self.at("EOF"):
            body.extend(self.parse_statement())
        body.extend(self.take_trailing_comments())
        return body

    def parse_block(self) -> list:
        self.expect("PUNCT", "{")
        body = []
        while not self.at("PUNCT", "}"):
            if self.at("EOF"):
                raise self.error("unterminated block, expected '}'")
            body.extend(self.parse_statement())
        self.expect("PUNCT", "}")
        return body

    def take_trailing_comments(self) -> list:
        floating, _ = self.split_comments(self.take_comments(1 << 30), -1)
        return floating

    def parse_statement(self) -> list:
        tok = self.peek()
        floating, comments = self.split_comments(self.take_comments(tok.line),
                                                 tok.line)

        # `#include "path.scmake"` splices another file's statements in here.
        if tok.kind == "PUNCT" and tok.value == "#":
            return [*floating, *self.parse_include()]

        if tok.kind != "IDENT":
            raise self.error(f"expected a statement, got {tok.value!r}")

        kw = tok.value
        # `library: "lib"` inside an install block is a setting, not a target
        # declaration. A keyword sitting right before ':' is always a key.
        if self.next_is(":"):
            st = self.parse_setting_or_call()
        elif kw == "function":
            st = self.parse_function()
        elif kw == "install" and self.next_is("{"):
            self.advance()
            st = N.Install(self.parse_block())
        elif kw == "project":
            st = self.parse_project()
        elif kw == "const":
            st = self.parse_const()
        # Guarded the way `install {` is, so a user function named `record`
        # stays callable as `record(...)`.
        elif kw == "record" and self.peek(1).kind == "IDENT":
            st = self.parse_record()
        elif kw == "set":
            st = self.parse_set()
        elif kw == "for":
            st = self.parse_for()
        elif kw in ("if", "when"):
            st = self.parse_branch(kw)
        elif kw in TARGET_KEYWORDS:
            st = self.parse_target()
        elif kw == "fetch":
            st = self.parse_fetch()
        elif kw == "raw":
            self.advance()
            st = N.Raw(self.parse_expr())
        # Both of these shapes are reached only after every keyword above has
        # had its turn, so `install { ... }` and friends are already claimed.
        elif self.next_is("."):
            st = self.parse_method_call()
        elif self.next_is("{"):
            st = self.parse_reopen()
        else:
            st = self.parse_setting_or_call()

        st.comments = comments
        st.line = tok.line
        return [*floating, st]

    def parse_for(self):
        self.advance()
        self.expect("PUNCT", "(")
        var = self.expect("IDENT").value
        self.expect("IDENT", "of")
        iterable = self.parse_expr()
        self.expect("PUNCT", ")")
        return N.ForOf(var, iterable, self.parse_block())

    def parse_branch(self, kw: str):
        self.advance()
        self.expect("PUNCT", "(")
        cond = self.parse_expr()
        self.expect("PUNCT", ")")
        then = self.parse_block()
        orelse = []
        if self.at("IDENT", "else"):
            self.advance()
            if self.at("IDENT", kw) or self.at("IDENT", "if"):
                orelse = self.parse_statement()
            else:
                orelse = self.parse_block()
        cls = N.If if kw == "if" else N.When
        return cls(cond, then, orelse)

    def parse_method_call(self):
        """`app.link(core)`, and `app.debug.link(...)` if a handle ever sits
        behind a field. The tail has to be a call: a bare `app.link` would read
        as an expression thrown away."""
        obj = self.parse_primary()
        while self.at("PUNCT", "."):
            self.advance()
            tok = self.expect("IDENT")
            if self.at("PUNCT", "("):
                return N.MethodCall(obj, tok.value, self.parse_paren_args())
            if self.at("PUNCT", "{"):
                # `app.install { ... }` — a block, not a call. Reopening the
                # target is how a block-shaped setting is applied to it.
                name = obj.name if isinstance(obj, N.Ident) else "<target>"
                raise self.error(f"{tok.value} takes a block, so it goes inside "
                                 f"a target block: {name} {{ {tok.value} {{ ... }} }}")
            obj = N.Member(obj, tok.value, obj.line)
        raise self.error("a statement starting with a name must end in a call, "
                         "e.g. app.link(core)")

    def parse_reopen(self):
        tok = self.expect("IDENT")
        return N.Reopen(N.Ident(tok.value, tok.line), self.parse_block())

    def parse_setting_or_call(self):
        tok = self.expect("IDENT")
        args = self.parse_paren_args() if self.at("PUNCT", "(") else None
        if self.accept("PUNCT", ":"):
            value = self.parse_expr()
            self.accept("PUNCT", ",")
            return N.Setting(tok.value, args or [], value)
        if args is None:
            raise self.error(f"expected ':' or '(' after {tok.value!r}", tok)
        return N.Call(tok.value, args)
