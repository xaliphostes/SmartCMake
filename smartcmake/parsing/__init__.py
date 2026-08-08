"""Recursive-descent parser: tokens -> AST.

The grammar is split by concern — `cursor` navigates the token stream and
decides which statement a comment belongs to, `expressions` and `statements`
hold the two halves of the grammar, `declarations` the statements that
introduce a name, and `includes` the one production that reads a file. They are
mixins on the single `Parser` below, so a production can call any other without
threading state around.
"""

from __future__ import annotations

from pathlib import Path

from ..lexer import Comment, Token, tokenize
from .cursor import Cursor
from .declarations import TARGET_KEYWORDS, DeclarationParser
from .expressions import ExpressionParser
from .includes import IncludeParser
from .statements import StatementParser

__all__ = ["parse", "Parser", "TARGET_KEYWORDS"]


class Parser(Cursor, ExpressionParser, DeclarationParser, StatementParser,
             IncludeParser):
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


def parse(src: str, filename: str = "<scmake>", base_dir: Path | None = None,
          stack: tuple[Path, ...] = ()) -> list:
    toks, comments = tokenize(src, filename)
    return Parser(toks, comments, filename, base_dir, stack).parse_program()
