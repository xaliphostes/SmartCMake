"""SmartCMake — a TypeScript-flavoured language that compiles to CMakeLists.txt."""

from .emitter import emit
from .errors import ScmakeError
from .parser import parse

__version__ = "0.1.0"


def compile_source(src: str, filename: str = "<scmake>") -> str:
    """Compile .scmake source text into CMakeLists.txt text."""
    return emit(parse(src, filename), filename)


__all__ = ["compile_source", "parse", "emit", "ScmakeError", "__version__"]
