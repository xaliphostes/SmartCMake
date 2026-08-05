"""Tokenizer for .scmake sources.

Produces a flat token stream plus a separate list of comments; comments are
kept out of the stream so the parser stays simple, and are re-attached to the
statement that follows them so the emitter can carry them into the CMake output.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .errors import ScmakeError

PUNCT2 = ("==", "!=", "&&", "||", ">=", "<=")
PUNCT1 = "{}()[]:,.=!<>+#"

ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "0": "\0"}


@dataclass
class Token:
    kind: str  # IDENT | NUMBER | STRING | TEMPLATE | PUNCT | EOF
    value: Any
    line: int
    col: int

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"{self.kind}({self.value!r})@{self.line}:{self.col}"


@dataclass
class Comment:
    text: str
    line: int


def tokenize(src: str, filename: str = "<scmake>") -> tuple[list[Token], list[Comment]]:
    toks: list[Token] = []
    comments: list[Comment] = []
    i, line, col = 0, 1, 1
    n = len(src)

    def err(msg: str) -> ScmakeError:
        return ScmakeError(msg, line, col, filename)

    while i < n:
        c = src[i]

        if c == "\n":
            i += 1
            line += 1
            col = 1
            continue
        if c in " \t\r":
            i += 1
            col += 1
            continue

        # comments -------------------------------------------------------
        if src.startswith("//", i):
            j = src.find("\n", i)
            j = n if j < 0 else j
            comments.append(Comment(src[i + 2:j].strip(), line))
            col += j - i
            i = j
            continue
        if src.startswith("/*", i):
            j = src.find("*/", i + 2)
            if j < 0:
                raise err("unterminated block comment")
            block = src[i + 2:j]
            for offset, part in enumerate(block.splitlines() or [""]):
                comments.append(Comment(part.strip().lstrip("*").strip(),
                                        line + offset))
            line += block.count("\n")
            i = j + 2
            col = 1
            continue

        start_line, start_col = line, col

        # template string -------------------------------------------------
        if c == "`":
            parts, i, line = _lex_template(src, i, line, filename)
            toks.append(Token("TEMPLATE", parts, start_line, start_col))
            col = 1
            continue

        # plain string ----------------------------------------------------
        if c in "\"'":
            start_i = i
            value, i = _lex_string(src, i, line, col, filename)
            toks.append(Token("STRING", value, start_line, start_col))
            col += i - start_i
            continue

        # number ----------------------------------------------------------
        if c.isdigit():
            j = i
            while j < n and (src[j].isdigit() or src[j] == "."):
                j += 1
            text = src[i:j]
            value: Any = float(text) if "." in text else int(text)
            toks.append(Token("NUMBER", value, start_line, start_col))
            col += j - i
            i = j
            continue

        # identifier ------------------------------------------------------
        if c.isalpha() or c == "_":
            j = i
            while j < n and (src[j].isalnum() or src[j] in "_"):
                j += 1
            toks.append(Token("IDENT", src[i:j], start_line, start_col))
            col += j - i
            i = j
            continue

        # punctuation -----------------------------------------------------
        two = src[i:i + 2]
        if two in PUNCT2:
            toks.append(Token("PUNCT", two, start_line, start_col))
            i += 2
            col += 2
            continue
        if c in PUNCT1:
            toks.append(Token("PUNCT", c, start_line, start_col))
            i += 1
            col += 1
            continue

        raise err(f"unexpected character {c!r}")

    toks.append(Token("EOF", None, line, col))
    return toks, comments


def _lex_string(src: str, i: int, line: int, col: int, filename: str) -> tuple[str, int]:
    quote = src[i]
    i += 1
    buf: list[str] = []
    while True:
        if i >= len(src) or src[i] == "\n":
            raise ScmakeError("unterminated string", line, col, filename)
        c = src[i]
        if c == "\\":
            nxt = src[i + 1]
            buf.append(ESCAPES.get(nxt, nxt))
            i += 2
            continue
        if c == quote:
            return "".join(buf), i + 1
        buf.append(c)
        i += 1


def _lex_template(src: str, i: int, line: int,
                  filename: str) -> tuple[list[tuple], int, int]:
    """Lex `text ${expr} text`. Expression bodies are kept as raw source and
    re-parsed by the parser, which keeps nesting rules trivial."""
    start_line = line
    i += 1  # opening backtick
    parts: list[tuple] = []
    buf: list[str] = []
    n = len(src)

    while True:
        if i >= n:
            raise ScmakeError("unterminated template string", start_line, 1, filename)
        c = src[i]
        if c == "`":
            i += 1
            break
        if c == "\\":
            nxt = src[i + 1]
            buf.append(ESCAPES.get(nxt, nxt))
            i += 2
            continue
        if c == "$" and i + 1 < n and src[i + 1] == "{":
            if buf:
                parts.append(("lit", "".join(buf)))
                buf = []
            depth = 1
            i += 2
            expr_start, expr_line = i, line
            while i < n:
                ch = src[i]
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        break
                elif ch == "\n":
                    line += 1
                i += 1
            if i >= n:
                raise ScmakeError("unterminated ${...} in template string",
                                  expr_line, 1, filename)
            parts.append(("expr", src[expr_start:i], expr_line))
            i += 1  # closing brace
            continue
        if c == "\n":
            line += 1
        buf.append(c)
        i += 1

    if buf:
        parts.append(("lit", "".join(buf)))
    return parts, i, line
