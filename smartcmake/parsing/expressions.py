"""The expression grammar, lowest precedence first.

`parse_paren_args` lives here rather than with the statements: an argument list
is a list of expressions, and every caller of it wants that reading.
"""

from __future__ import annotations

from .. import nodes as N
from ..lexer import Token, tokenize


class ExpressionParser:
    """Mixed into Parser; relies on the Cursor helpers."""

    def parse_expr(self):
        return self.parse_or()

    def _binary(self, sub, ops):
        left = sub()
        while self.peek().kind == "PUNCT" and self.peek().value in ops:
            op = self.advance().value
            left = N.Binary(op, left, sub(), left.line)
        return left

    def parse_or(self):
        return self._binary(self.parse_and, ("||",))

    def parse_and(self):
        return self._binary(self.parse_equality, ("&&",))

    def parse_equality(self):
        return self._binary(self.parse_additive, ("==", "!=", "<", ">", "<=", ">="))

    def parse_additive(self):
        return self._binary(self.parse_unary, ("+",))

    def parse_unary(self):
        if self.at("PUNCT", "!"):
            tok = self.advance()
            return N.Unary("!", self.parse_unary(), tok.line)
        return self.parse_postfix()

    def parse_postfix(self):
        expr = self.parse_primary()
        while self.at("PUNCT", "."):
            self.advance()
            name = self.expect("IDENT").value
            expr = N.Member(expr, name, expr.line)
        return expr

    def parse_primary(self):
        tok = self.peek()

        if tok.kind == "STRING":
            self.advance()
            return N.Str(tok.value, tok.line)
        if tok.kind == "NUMBER":
            self.advance()
            return N.Num(tok.value, tok.line)
        if tok.kind == "TEMPLATE":
            self.advance()
            return N.Template(self._parse_template_parts(tok), tok.line)

        if tok.kind == "IDENT":
            self.advance()
            if tok.value in ("true", "false"):
                return N.Bool(tok.value == "true", tok.line)
            if self.at("PUNCT", "("):
                return N.CallExpr(tok.value, self.parse_paren_args(), tok.line)
            return N.Ident(tok.value, tok.line)

        if self.at("PUNCT", "["):
            self.advance()
            items = []
            while not self.at("PUNCT", "]"):
                items.append(self.parse_expr())
                if not self.accept("PUNCT", ","):
                    break
            self.expect("PUNCT", "]")
            return N.ListLit(items, tok.line)

        if self.at("PUNCT", "{"):
            self.advance()
            entries = []
            while not self.at("PUNCT", "}"):
                if self.at("STRING"):
                    key = self.advance().value
                else:
                    key = self.expect("IDENT").value
                self.expect("PUNCT", ":")
                entries.append((key, self.parse_expr()))
                if not self.accept("PUNCT", ","):
                    break
            self.expect("PUNCT", "}")
            return N.ObjectLit(entries, tok.line)

        if self.at("PUNCT", "("):
            self.advance()
            inner = self.parse_expr()
            self.expect("PUNCT", ")")
            return inner

        raise self.error(f"expected an expression, got {tok.value!r}")

    def parse_paren_args(self) -> list:
        self.expect("PUNCT", "(")
        args = []
        while not self.at("PUNCT", ")"):
            args.append(self.parse_expr())
            if not self.accept("PUNCT", ","):
                break
        self.expect("PUNCT", ")")
        return args

    def _parse_template_parts(self, tok: Token) -> list:
        # The lexer keeps a `${...}` body as raw source; re-parsing it here is
        # what keeps nesting rules trivial.
        from . import Parser  # deferred: Parser is assembled from this mixin

        parts = []
        for part in tok.value:
            if part[0] == "lit":
                parts.append(("lit", part[1]))
                continue
            _, src, line = part
            sub_toks, _ = tokenize(src, self.filename)
            sub = Parser(sub_toks, [], self.filename)
            for t in sub_toks:
                t.line = line
            parts.append(("expr", sub.parse_expr()))
        return parts
