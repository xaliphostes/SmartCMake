"""Statements that introduce a name: project, const, record, set, target,
fetch and function.

They are grouped because they share a shape — a keyword, a name, then a body —
and because the name is what later statements refer to.
"""

from __future__ import annotations

from .. import nodes as N
from ..errors import ScmakeError

TARGET_KEYWORDS = ("executable", "library", "interface")


class DeclarationParser:
    """Mixed into Parser; relies on the Cursor and expression helpers."""

    def parse_project(self):
        self.advance()
        if self.at("STRING"):
            name = self.advance().value
        else:
            name = self.expect("IDENT").value
        return N.Project(name, self.parse_block())

    def parse_const(self):
        self.advance()
        name = self.expect("IDENT").value
        type_ref = self.parse_type() if self.accept("PUNCT", ":") else None
        self.expect("PUNCT", "=")
        # `const app = executable("app") { ... }` declares the target here and
        # binds a handle to it, so later statements can name it.
        if self.at("IDENT") and self.peek().value in TARGET_KEYWORDS:
            return N.ConstDecl(name, self.parse_target(expression=True), type_ref)
        return N.ConstDecl(name, self.parse_expr(), type_ref)

    def parse_record(self):
        self.advance()
        name = self.expect("IDENT").value
        self.expect("PUNCT", "{")
        fields = []
        while True:
            # A record produces no CMake, so comments inside it document the
            # .scmake only. Dropping them here stops them drifting onto the
            # next statement, which is where take_comments would leave them.
            self.take_comments(self.peek().line)
            if self.at("PUNCT", "}"):
                break
            if self.at("EOF"):
                raise self.error("unterminated record, expected '}'")
            tok = self.expect("IDENT")
            self.expect("PUNCT", ":")
            type_ref = self.parse_type()
            default, has_default = None, False
            if self.accept("PUNCT", "="):
                default, has_default = self.parse_expr(), True
            self.accept("PUNCT", ",")
            fields.append(N.FieldDecl(tok.value, type_ref, default, has_default,
                                      tok.line))
        self.expect("PUNCT", "}")
        return N.RecordDecl(name, fields)

    def parse_type(self):
        tok = self.expect("IDENT")
        dims = 0
        while self.at("PUNCT", "["):
            self.advance()
            self.expect("PUNCT", "]")
            dims += 1
        return N.TypeRef(tok.value, dims, tok.line)

    def parse_set(self):
        self.advance()
        name = self.expect("IDENT").value
        self.expect("PUNCT", "=")
        value = self.parse_expr()
        node = N.SetVar(name, value)
        if self.at("IDENT", "cache"):
            self.advance()
            args = self.parse_paren_args()
            if not args:
                raise self.error('cache(...) needs a type, e.g. cache(PATH, "doc")')
            node.cache_type = static_word(args[0], self, "cache type")
            if len(args) > 1:
                node.cache_doc = static_word(args[1], self, "cache doc")
            if len(args) > 2:
                node.force = True
        return node

    def parse_target(self, expression: bool = False):
        kind = self.advance().value
        if self.at("PUNCT", "("):
            self.advance()
            name = self.parse_expr()
            self.expect("PUNCT", ")")
        elif self.at("STRING") or self.at("TEMPLATE"):
            name = self.parse_expr()
        elif expression:
            # `const app = executable app { ... }` names the target twice and
            # reads as if `app` were being referenced rather than declared.
            raise self.error(f'give the name in parentheses here, e.g. '
                             f'{kind}("name") {{ ... }}')
        else:
            name = N.Str(self.expect("IDENT").value)

        qualifier = None
        if self.at("PUNCT", "("):
            args = self.parse_paren_args()
            if len(args) != 1:
                raise self.error("expected one library kind, e.g. library foo(STATIC)")
            qualifier = static_word(args[0], self, "library kind")

        return N.Target(kind, name, qualifier, self.parse_block())

    def parse_fetch(self):
        self.advance()
        name = self.expect("IDENT").value
        return N.Fetch(name, self.parse_block())

    def parse_function(self):
        self.advance()
        name = self.expect("IDENT").value
        params: list[str] = []
        self.expect("PUNCT", "(")
        while not self.at("PUNCT", ")"):
            params.append(self.expect("IDENT").value)
            if not self.accept("PUNCT", ","):
                break
        self.expect("PUNCT", ")")
        return N.Function(name, params, self.parse_block())


def static_word(node, parser, what: str) -> str:
    """Pull a bare word / string out of an already-parsed expression node."""
    if isinstance(node, N.Ident):
        return node.name
    if isinstance(node, (N.Str, N.Num)):
        return str(node.value)
    raise ScmakeError(f"{what} must be a plain word or string",
                      getattr(node, "line", 0), 0, parser.filename)
