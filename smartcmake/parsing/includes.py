"""`#include "cmake/utils.scmake"` — the only place the parser touches the
filesystem.

It is a splice, not an import-once: the included file's statements are parsed
and returned in place, exactly as C's `#include` behaves. Cycles are reported
rather than followed.
"""

from __future__ import annotations

from pathlib import Path

from ..errors import ScmakeError


class IncludeParser:
    """Mixed into Parser; relies on its `base_dir`, `stack` and `filename`."""

    def parse_include(self) -> list:
        from . import parse  # deferred: parse() builds the Parser this mixes into

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
