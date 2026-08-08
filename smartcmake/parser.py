"""Kept so that `from smartcmake.parser import parse` stays the public entry
point. The grammar itself lives in the `parsing` package, split by concern.
"""

from __future__ import annotations

from .parsing import TARGET_KEYWORDS, Parser, parse

__all__ = ["parse", "Parser", "TARGET_KEYWORDS"]
