"""Token-stream navigation, and the rule that decides which statement a
comment belongs to.

Comments are lexed into a separate list rather than the token stream, so
re-attaching them is a concern of its own: it is decided by line number, not by
position in the stream.
"""

from __future__ import annotations

from .. import nodes as N
from ..errors import ScmakeError
from ..lexer import Comment, Token


class Cursor:
    """Mixed into Parser; relies on its `toks`, `comments`, `i`, `ci` and
    `filename`."""

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

    def next_is(self, value: str) -> bool:
        """Whether the token after the current one is this punctuation."""
        nxt = self.peek(1)
        return nxt.kind == "PUNCT" and nxt.value == value

    # --- comment attachment -----------------------------------------------

    def take_comments(self, before_line: int) -> list[Comment]:
        # `<=` rather than `<` so that `/* note */ executable app { ... }` is
        # claimed by the statement it sits on. Without it the comment outlives
        # this statement and lands on the *next* one, which reads as a bug
        # specific to block comments — `//` cannot precede code on a line.
        out = []
        while (self.ci < len(self.comments)
               and self.comments[self.ci].line <= before_line):
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
            attached = _trim_blank_edges([c.text for c in groups.pop()])
        floating = []
        for g in groups:
            text = _trim_blank_edges([c.text for c in g])
            if text:  # a block that was nothing but its own delimiters
                floating.append(N.CommentBlock(text, line=g[0].line))
        return floating, attached


def _trim_blank_edges(lines: list[str]) -> list[str]:
    """Drop empty lines at the top and bottom of a comment block. `/** ... */`
    and `/*\\n ... \\n*/` contribute nothing on the delimiter lines themselves,
    which would otherwise surface as bare `#` lines wrapping the text. Interior
    blanks are kept — those are deliberate paragraph breaks.

    The blank lines still have to reach here rather than be dropped in the
    lexer: attachment to the statement below is decided by line number, and a
    `*/` sitting directly above the statement is what makes the block attach.
    """
    start, end = 0, len(lines)
    while start < end and not lines[start]:
        start += 1
    while end > start and not lines[end - 1]:
        end -= 1
    return lines[start:end]
