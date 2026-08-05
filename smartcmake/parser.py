"""Recursive-descent parser: tokens -> AST."""

from __future__ import annotations

from pathlib import Path

from . import nodes as N
from .errors import ScmakeError
from .lexer import Comment, Token, tokenize

TARGET_KEYWORDS = ("executable", "library", "interface")


def parse(src: str, filename: str = "<scmake>", base_dir: Path | None = None,
          stack: tuple[Path, ...] = ()) -> list:
    toks, comments = tokenize(src, filename)
    return Parser(toks, comments, filename, base_dir, stack).parse_program()


class Parser:
    def __init__(self, toks: list[Token], comments: list[Comment], filename: str,
                 base_dir: Path | None = None, stack: tuple[Path, ...] = ()):
        self.toks = toks
        self.i = 0
        self.comments = comments
        self.ci = 0
        self.filename = filename
        # Where `#include "..."` resolves relative paths from, and the chain of
        # files currently being included, used to detect cycles.
        self.base_dir = base_dir if base_dir is not None else Path(filename).parent
        self.stack = stack

    # --- token helpers ----------------------------------------------------

    def peek(self, k: int = 0) -> Token:
        return self.toks[min(self.i + k, len(self.toks) - 1)]

    def advance(self) -> Token:
        tok = self.toks[self.i]
        if tok.kind != "EOF":
            self.i += 1
        return tok

    def at(self, kind: str, value=None) -> bool:
        tok = self.peek()
        return tok.kind == kind and (value is None or tok.value == value)

    def accept(self, kind: str, value=None):
        return self.advance() if self.at(kind, value) else None

    def expect(self, kind: str, value=None) -> Token:
        tok = self.accept(kind, value)
        if tok is None:
            got = self.peek()
            shown = "end of file" if got.kind == "EOF" else repr(got.value)
            raise ScmakeError(f"expected {value or kind.lower()}, got {shown}",
                              got.line, got.col, self.filename)
        return tok

    def error(self, msg: str, tok: Token | None = None) -> ScmakeError:
        tok = tok or self.peek()
        return ScmakeError(msg, tok.line, tok.col, self.filename)

    def take_comments(self, before_line: int) -> list[Comment]:
        out = []
        while self.ci < len(self.comments) and self.comments[self.ci].line < before_line:
            out.append(self.comments[self.ci])
            self.ci += 1
        return out

    def split_comments(self, items: list[Comment], stmt_line: int):
        """A comment block belongs to the statement below it only when it is
        directly above it; anything separated by a blank line stands alone."""
        if not items:
            return [], []
        groups: list[list[Comment]] = [[items[0]]]
        for c in items[1:]:
            if c.line == groups[-1][-1].line + 1:
                groups[-1].append(c)
            else:
                groups.append([c])
        attached: list[str] = []
        if groups[-1][-1].line == stmt_line - 1:
            attached = [c.text for c in groups.pop()]
        floating = [N.CommentBlock([c.text for c in g], line=g[0].line) for g in groups]
        return floating, attached

    # --- statements -------------------------------------------------------

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
        floating, comments = self.split_comments(self.take_comments(tok.line), tok.line)

        # `#include "path.scmake"` splices another file's statements in here.
        if tok.kind == "PUNCT" and tok.value == "#":
            return [*floating, *self.parse_include()]

        if tok.kind != "IDENT":
            raise self.error(f"expected a statement, got {tok.value!r}")

        kw = tok.value
        if kw == "function":
            st = self.parse_function()
        elif kw == "install" and self.peek(1).kind == "PUNCT" and self.peek(1).value == "{":
            self.advance()
            st = N.Install(self.parse_block())
        elif kw == "project":
            st = self.parse_project()
        elif kw == "const":
            st = self.parse_const()
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
        else:
            st = self.parse_setting_or_call()

        st.comments = comments
        st.line = tok.line
        return [*floating, st]

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
        self.expect("PUNCT", "=")
        return N.ConstDecl(name, self.parse_expr())

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
                raise self.error("cache(...) needs a type, e.g. cache(PATH, \"doc\")")
            node.cache_type = _static_word(args[0], self, "cache type")
            if len(args) > 1:
                node.cache_doc = _static_word(args[1], self, "cache doc")
            if len(args) > 2:
                node.force = True
        return node

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

    def parse_target(self):
        kind = self.advance().value
        if self.at("PUNCT", "("):
            self.advance()
            name = self.parse_expr()
            self.expect("PUNCT", ")")
        elif self.at("STRING") or self.at("TEMPLATE"):
            name = self.parse_expr()
        else:
            name = N.Str(self.expect("IDENT").value)

        qualifier = None
        if self.at("PUNCT", "("):
            args = self.parse_paren_args()
            if len(args) != 1:
                raise self.error("expected one library kind, e.g. library foo(STATIC)")
            qualifier = _static_word(args[0], self, "library kind")

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

    def parse_include(self) -> list:
        """`#include "cmake/utils.scmake"` — parse that file and return its
        statements, so they are spliced into the output at this point."""
        hash_tok = self.advance()
        word = self.expect("IDENT")
        if word.value != "include":
            raise self.error(f"unknown directive '#{word.value}'", word)
        if not self.at("STRING"):
            raise self.error('#include needs a quoted path, '
                             'e.g. #include "cmake/utils.scmake"')
        raw = self.advance().value

        target = Path(raw)
        if not target.is_absolute():
            target = self.base_dir / target
        try:
            resolved = target.resolve()
        except OSError:
            resolved = target

        if resolved in self.stack:
            chain = " -> ".join(p.name for p in (*self.stack, resolved))
            raise ScmakeError(f"#include cycle: {chain}",
                              hash_tok.line, hash_tok.col, self.filename)
        try:
            text = resolved.read_text()
        except OSError as exc:
            raise ScmakeError(f"cannot read #include {raw!r}: {exc.strerror}",
                              hash_tok.line, hash_tok.col, self.filename) from None

        return parse(text, str(resolved), resolved.parent, (*self.stack, resolved))

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

    def parse_paren_args(self) -> list:
        self.expect("PUNCT", "(")
        args = []
        while not self.at("PUNCT", ")"):
            args.append(self.parse_expr())
            if not self.accept("PUNCT", ","):
                break
        self.expect("PUNCT", ")")
        return args

    # --- expressions ------------------------------------------------------

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

    def _parse_template_parts(self, tok: Token) -> list:
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


def _static_word(node, parser: Parser, what: str) -> str:
    """Pull a bare word / string out of an already-parsed expression node."""
    if isinstance(node, N.Ident):
        return node.name
    if isinstance(node, (N.Str, N.Num)):
        return str(node.value)
    raise ScmakeError(f"{what} must be a plain word or string",
                      getattr(node, "line", 0), 0, parser.filename)
