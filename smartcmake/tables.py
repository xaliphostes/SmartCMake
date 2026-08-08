"""The vocabulary: which scmake setting becomes which CMake command.

Kept apart from the code that walks the AST, so adding a setting is a one-line
table edit rather than a search through the analyzer.
"""

from __future__ import annotations

# Settings that map straight onto a CMake variable.
SIMPLE_VARS = {
    "cxx": "CMAKE_CXX_STANDARD",
    "c": "CMAKE_C_STANDARD",
    "standardRequired": "CMAKE_CXX_STANDARD_REQUIRED",
    "extensions": "CMAKE_CXX_EXTENSIONS",
    "scanForModules": "CMAKE_CXX_SCAN_FOR_MODULES",
    "buildType": "CMAKE_BUILD_TYPE",
    "positionIndependent": "CMAKE_POSITION_INDEPENDENT_CODE",
    "exportCompileCommands": "CMAKE_EXPORT_COMPILE_COMMANDS",
    "cxxCompiler": "CMAKE_CXX_COMPILER",
    "cCompiler": "CMAKE_C_COMPILER",
    "prefixPath": "CMAKE_PREFIX_PATH",
    "runtimeOutputDir": "CMAKE_RUNTIME_OUTPUT_DIRECTORY",
    "libraryOutputDir": "CMAKE_LIBRARY_OUTPUT_DIRECTORY",
    "archiveOutputDir": "CMAKE_ARCHIVE_OUTPUT_DIRECTORY",
}

# Directory-scope settings that take a list.
DIRECTORY_LISTS = {
    "compileOptions": "add_compile_options",
    "linkOptions": "add_link_options",
    "defines": "add_compile_definitions",
    "includeDirs": "include_directories",
    "linkDirs": "link_directories",
}

# Target-scope settings; all take an optional visibility qualifier.
TARGET_LISTS = {
    "include": "target_include_directories",
    "link": "target_link_libraries",
    "compileOptions": "target_compile_options",
    "linkOptions": "target_link_options",
    "defines": "target_compile_definitions",
    "features": "target_compile_features",
}

VISIBILITIES = ("PRIVATE", "PUBLIC", "INTERFACE")

# install { ... }. What is being installed comes first in CMake's grammar, so
# these three tables are emitted in order and never in the order they were
# written; `export` is a kind on its own but a modifier next to `targets`.
INSTALL_KINDS = (
    ("targets", "TARGETS"),
    ("files", "FILES"),
    ("programs", "PROGRAMS"),
    ("directory", "DIRECTORY"),
    ("export", "EXPORT"),
)

# Per-artifact destinations, emitted as `<WORD> DESTINATION <dir>`.
INSTALL_ARTIFACTS = (
    ("runtime", "RUNTIME"),
    ("library", "LIBRARY"),
    ("archive", "ARCHIVE"),
    ("bundle", "BUNDLE"),
    ("framework", "FRAMEWORK"),
    ("includes", "INCLUDES"),
)

INSTALL_WORDS = (
    ("destination", "DESTINATION"),
    ("namespace", "NAMESPACE"),
    ("file", "FILE"),
    ("rename", "RENAME"),
    ("component", "COMPONENT"),
    ("configurations", "CONFIGURATIONS"),
    ("permissions", "PERMISSIONS"),
    ("pattern", "PATTERN"),
)

INSTALL_FLAGS = (("optional", "OPTIONAL"), ("excludeFromAll", "EXCLUDE_FROM_ALL"))

INSTALL_KEYS = {k for k, _ in (*INSTALL_KINDS, *INSTALL_ARTIFACTS,
                               *INSTALL_WORDS, *INSTALL_FLAGS)}

DIRECTORY_CALLS = {
    "enableTesting": ("enable_testing", 0),
    "subdirectory": ("add_subdirectory", 1),
    "include": ("include", 1),
}

# Names emit_call resolves before user-defined functions. A function using one
# of these would never be reached, so defining it is an error rather than a
# silent shadow.
BUILTIN_STATEMENTS = {*DIRECTORY_CALLS, "findPackage", "message", "cmake",
                      "discoverTests", "alias", "install", "raw"}

# Field types a `record` can use, beyond the records already declared. `list`
# is `any[]`, which is what most build data wants: a list of names whose
# elements may be strings, targets or namespaced references alike.
PRIMITIVE_TYPES = ("string", "number", "bool", "target", "list", "any")

# Target settings reachable as `app.<name>(...)` on a handle. Everything here
# is a standalone CMake command, which is what lets it be written after the
# declaration rather than inside it.
HANDLE_METHODS = (*TARGET_LISTS, "sources", "properties", "discoverTests", "alias")

# FetchContent_Declare argument order.
FETCH_KEYS = (("git", "GIT_REPOSITORY"), ("tag", "GIT_TAG"), ("url", "URL"),
              ("hash", "URL_HASH"), ("dir", "SOURCE_DIR"))
