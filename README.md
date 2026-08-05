# SmartCMake

<center>
    <img src="media/logo2.png" alt="drawing" width="200"/><br>
</center>

A small TypeScript-flavoured language that compiles to `CMakeLists.txt`.

You write `build.scmake`, run `scmake`, and get a plain `CMakeLists.txt` that any CMake ≥ 3.20 can consume. Nothing at build time depends on SmartCMake — the relationship is exactly TypeScript → JavaScript: you keep the readable source, you ship the generated artifact, and consumers never need the compiler.

```
build.scmake  ──scmake──▶  CMakeLists.txt  ──cmake──▶  build system
```

## Why

CMake's language has no data structures and no loops worth using, so build files grow by copy-paste. For example, Rosetta's test suite is 197 lines of CMake describing 18 targets that differ only by name:

```cmake
add_executable(matrix matrix.cpp)
target_include_directories(matrix PRIVATE ${CMAKE_SOURCE_DIR}/../include)
target_compile_options(matrix PRIVATE -fannotation-attributes)
target_link_libraries(matrix PRIVATE GTest::gtest_main)
gtest_discover_tests(matrix)
# ... ×17 more
```

The same thing in SmartCMake:

```ts
for (suite of SUITES) {
    executable(suite.name) {
        sources: [`${suite.name}.cpp`]
        include: [INCLUDE]
        compileOptions: ["-fannotation-attributes"]
        link: [GTest.gtest_main]
        discoverTests()
    }
}
```

The full translation is in `examples/rosetta-tests scmake`; it regenerates rosetta's `tests/CMakeLists.txt` command-for-command (verified: 109 commands either side, configures and builds with the real toolchain).

## Install

Pure Python 3.10+, no dependencies.

```sh
pip install -e .        # provides the `scmake` command
```

Or run it straight from the checkout without installing:

```sh
python3 -m smartcmake build.scmake
```

## Usage

```sh
scmake build.scmake                  # writes CMakeLists.txt beside the source
scmake build.scmake -o out/CMake.txt # explicit destination
scmake build.scmake -o -             # print to stdout
scmake build.scmake --check          # exit 1 if CMakeLists.txt is stale (for CI)
```

Errors carry a source location:

```
build.scmake:14:0: error: unknown setting 'cxxx'
```

## The one idea to hold on to

Two kinds of logic look similar and mean different things:

| | runs | ends up in the output |
|---|---|---|
| `const`, `for`, `if` | **when you run `scmake`** | no — they expand away |
| `set`, `when`, `function` | when CMake configures | yes — real `set()` / `if()` / `function()` |

So `if` picks a branch now, at compile time, and only the winner is written out. `when` writes a literal `if()/else()/endif()` block that CMake decides later. Use `if` for "which targets exist"; use `when` for "what the user's machine looks like".

## Language reference

### Project

```ts
project MyApp {              // or: project "my-app" { ... }
    cmakeMinimum: "3.20"     // hoisted to the top of the file automatically
    version: "1.4.0"
    languages: [CXX, C]      // defaults to [CXX]
    ...
}
```

### Settings

Scalar settings become CMake variables; `true`/`false` become `ON`/`OFF`.

| setting | emits |
|---|---|
| `cxx: 23` / `c: 17` | `set(CMAKE_CXX_STANDARD 23)` |
| `standardRequired: true` | `set(CMAKE_CXX_STANDARD_REQUIRED ON)` |
| `extensions: false` | `set(CMAKE_CXX_EXTENSIONS OFF)` |
| `scanForModules: false` | `set(CMAKE_CXX_SCAN_FOR_MODULES OFF)` |
| `buildType: "Release"` | `set(CMAKE_BUILD_TYPE Release)` |
| `positionIndependent: true` | `set(CMAKE_POSITION_INDEPENDENT_CODE ON)` |
| `exportCompileCommands: true` | `set(CMAKE_EXPORT_COMPILE_COMMANDS ON)` |
| `cxxCompiler:` / `cCompiler:` | `set(CMAKE_CXX_COMPILER ...)` |
| `prefixPath:` | `set(CMAKE_PREFIX_PATH ...)` |
| `runtimeOutputDir:` / `libraryOutputDir:` / `archiveOutputDir:` | the matching `CMAKE_*_OUTPUT_DIRECTORY` |

List settings become directory-scope commands:

| setting | emits |
|---|---|
| `compileOptions: [...]` | `add_compile_options(...)` |
| `linkOptions: [...]` | `add_link_options(...)` |
| `defines: [...]` | `add_compile_definitions(...)` |
| `includeDirs: [...]` | `include_directories(...)` |
| `linkDirs: [...]` | `link_directories(...)` |

### Targets

```ts
executable app { sources: ["main.cpp"] }
library core(SHARED) { sources: ["a.cpp"] }   // STATIC when omitted
interface headers { include: ["include"] }    // header-only
executable(name) { ... }                      // computed name
```

Inside a target body:

| setting | emits |
|---|---|
| `sources: [...]` | folded into `add_executable` / `add_library` |
| `include(VIS): [...]` | `target_include_directories` |
| `link(VIS): [...]` | `target_link_libraries` |
| `compileOptions(VIS): [...]` | `target_compile_options` |
| `linkOptions(VIS): [...]` | `target_link_options` |
| `defines(VIS): [...]` | `target_compile_definitions` |
| `features(VIS): [...]` | `target_compile_features` |
| `properties: { KEY: value }` | `set_target_properties` |
| `doc: "text"` | a `#` comment above the target |
| `discoverTests()` | `gtest_discover_tests(<target>)` |
| `alias("Ns::name")` | `add_library(Ns::name ALIAS <target>)` |

`VIS` is `PRIVATE` (the default), `PUBLIC`, or `INTERFACE`; an `interface` target defaults to `INTERFACE`.

### Dependencies

```ts
fetch googletest {
    git: "https://github.com/google/googletest.git"
    tag: "v1.15.2"
    options: { INSTALL_GTEST: false }   // forced cache entries, set before use
}
```

emits `include(FetchContent)` once, then `FetchContent_Declare` / `FetchContent_MakeAvailable`. `url`, `hash` and `dir` are accepted too.

Using `discoverTests()` anywhere makes SmartCMake insert `enable_testing()` and `include(GoogleTest)` above the first target, unless you wrote them yourself.

### Variables and references

```ts
const INCLUDE = `${cmake.SOURCE_DIR}/../include`   // transpile-time, vanishes
set ROOT = "/opt/sdk" cache(PATH, "SDK location")  // a real CMake cache entry
```

| you write | you get |
|---|---|
| `cmake.SOURCE_DIR` | `${CMAKE_SOURCE_DIR}` (a `CMAKE_` prefix is added if missing) |
| `env.HOME` | `$ENV{HOME}` |
| `vars.ROOT` | `${ROOT}` |
| `GTest.gtest_main` | `GTest::gtest_main` |

Strings are `"..."` or `'...'`; backticks give multi-line text and
`${...}` interpolation, as in TypeScript.

### Control flow

```ts
const SUITES = [
    { name: "matrix", extra: [Eigen.Eigen] },
    { name: "moc" },
]

for (suite of SUITES) {
    executable(suite.name) {
        sources: [`${suite.name}.cpp`]
        link: [GTest.gtest_main] + get(suite, "extra", [])
    }
}

if (SUITES.length > 0) { enableTesting() }      // decided now

when (!cmake.CXX_COMPILER) {                    // decided by CMake
    cCompiler: `${vars.ROOT}/bin/clang`
    cxxCompiler: `${vars.ROOT}/bin/clang++`
}
```

`when` conditions translate rather than evaluate: `!` → `NOT`, `&&` → `AND`, `||` → `OR`, `==` on strings → `STREQUAL` (on numbers → `EQUAL`), and `defined(x)`, `exists(p)`, `target(t)`, `command(c)` → `DEFINED`, `EXISTS`, `TARGET`, `COMMAND`. String literals in conditions are always quoted, so a value that happens to match a variable name is not silently re-read as one.

Built-in transpile-time functions: `upper`, `lower`, `join`, `replace`, `len`, `get`. Lists and strings concatenate with `+`; `.length` works on lists.

### Installing

```ts
install {
    targets: [core, app]
    export: "ToolkitTargets"
    runtime: "bin"
    archive: "lib"
    includes: "include"
}

install { directory: "include/" destination: "include" }
install { export: "ToolkitTargets" destination: "lib/cmake/toolkit" namespace: "T::" }
```

Inside a target block the subject is implied, which is usually what you want:

```ts
executable app {
    sources: ["main.cpp"]
    install { runtime: "bin" }        // install(TARGETS app RUNTIME DESTINATION bin)
}
```

Exactly one of `targets`, `files`, `programs`, `directory` or `export` says what is being installed — except that alongside `targets`, `export` names the export set rather than being the subject. The rest are modifiers:

| setting | emits |
|---|---|
| `runtime:` / `library:` / `archive:` / `bundle:` / `framework:` / `includes:` | `RUNTIME DESTINATION ...` and friends |
| `destination:` | `DESTINATION` |
| `namespace:` / `file:` / `rename:` / `component:` | `NAMESPACE` / `FILE` / `RENAME` / `COMPONENT` |
| `configurations:` / `permissions:` / `pattern:` | the matching keyword |
| `optional: true` / `excludeFromAll: true` | `OPTIONAL` / `EXCLUDE_FROM_ALL` |

CMake's `install()` is order-sensitive, so the arguments come out in its order, not the order you wrote them. Anything not in the table above is a compile error; `raw` covers the rest.

### Functions

```ts
function add_genepi_library(target_name) {
    library(target_name)(SHARED) {
        sources: [ARGN, vars.CMAKE_JS_SRC]
        include(PUBLIC): [`${vars.PROJECT_SOURCE_DIR}/include`]
        properties: { PREFIX: "", SUFFIX: ".node" }
        link(PUBLIC): [genepi.genepi]
    }
}

add_genepi_library("mymod", "src.cpp")
```

emits a real `function()` / `endfunction()` pair, so the body runs when CMake configures — not when you run `scmake`. Inside it the parameters are bound to their own expansions, along with `ARGC`, `ARGN` and `ARGV`: writing `target_name` gives `${target_name}` without going through `vars.`. That is what lets the whole target vocabulary work inside a function body.

The name is emitted **verbatim**, so `function add_genepi_library(...)` is what CMake callers see. It is not camelCase-converted the way settings are, because the name is public API that hand-written CMake may call.

A function must be declared before it is called, which is also CMake's rule. Calling something undeclared is still an error rather than a guess; use `cmake("some_command", ...)` for commands defined outside SmartCMake.

Not covered yet: `PARENT_SCOPE` returns and `cmake_parse_arguments`. Both are reachable through `raw`.

### Multiple files

```ts
#include "cmake/utils.scmake"
```

splices that file's generated CMake in at this point, and its `const`s and functions stay visible afterwards. Paths are relative to the file doing the including, and cycles are reported rather than followed.

It is a splice, not an import-once: including the same file twice emits its commands twice, exactly as `#include` does in C. The `include("GNUInstallDirs")` *call* is unrelated — that one emits a CMake `include()` and does not read anything at compile time.

To ship a reusable module instead of inlining it, compile it on its own — a file with no `project` block is perfectly valid:

```sh
scmake cmake/utils.scmake -o cmake/utils.cmake
```

and have consumers `include("cmake/utils.cmake")` at CMake level.

### Other statements

```ts
enableTesting()
subdirectory("src")
include("GNUInstallDirs")
findPackage(Qt6, REQUIRED, COMPONENTS, Widgets)
message("configuring…")
cmake("some_command", ARG1, ARG2)   // any command not covered above
raw "set_directory_properties(PROPERTIES X 1)"
```

`cmake(...)` and `raw` are the escape hatches: anything CMake can do stays reachable without waiting for the language to grow a keyword for it.

### Comments

`//`, `/* ... */` and `/** ... */`, each of which may span as many lines as you
like:

```ts
/**
 * Everything downstream links against this.
 *
 * Second paragraph.
 */
library core(STATIC) { sources: ["a.cpp"] }
```

```cmake
# Everything downstream links against this.
#
# Second paragraph.
add_library(core STATIC a.cpp)
```

A leading `*` on a continuation line is stripped, and the `/**` and `*/` lines
contribute nothing, so a doc block does not come out wrapped in bare `#` lines.
Blank lines *inside* the block are kept — those are paragraph breaks.

A comment block directly above a statement is carried into the generated CMake
as `#` lines; one separated by a blank line stays where it is. A block comment
that precedes code on the same line — `/* note */ executable app { ... }` —
belongs to that statement. Comments on `const`/`for`/`if` are dropped, since
those statements produce no CMake. `doc:` covers the case where the comment
itself has to be generated.

One limitation: a comment *after* code on a line, or inside a multi-line
expression, is emitted near the following statement rather than the one it
trails, because a statement's extent is tracked by its first line only.

## Keeping the two files in sync

The generated header says `do not edit`, but nothing enforces it. In CI:

```sh
scmake build.scmake --check    # non-zero if CMakeLists.txt is out of date
```

## Status

Prototype (v0.1). It covers the vocabulary above and is exercised by 31 tests plus a real project; anything outside that vocabulary is a compile error, so you will not get silently wrong CMake — but you will meet the edges. `raw` and `cmake(...)` are there for those.

Not yet: `export()`, generator expressions as syntax, custom commands and targets, `find_package` component sugar, `macro()`, and `PARENT_SCOPE` /  `cmake_parse_arguments` inside `function`.

Editor support so far is syntax highlighting only — see `editors/vscode` (symlink it into `~/.vscode/extensions/` or `vsce package` it). There is no language server, so `scmake` is still what tells you the file is valid.

```sh
python3 -m unittest discover -s tests
```

## License

[MIT](./LICENSE)

## Author

[Xaliphostes](https://github.com/xaliphostes)
