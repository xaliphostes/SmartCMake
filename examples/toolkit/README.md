# toolkit — a multi-file example

A small but complete project: a static library, two command-line tools, and a
GoogleTest suite per module. Unlike the other two examples this one really
builds, so the generated CMake can be checked against a real toolchain.

```sh
scmake build.scmake                 # writes CMakeLists.txt (gitignored)
cmake -S . -B build
cmake --build build
ctest --test-dir build              # 6 tests
./build/meshinfo data/tetra.obj
```

`cmake -S . -B build -DTOOLKIT_BUILD_TESTS=OFF` skips the GoogleTest fetch, so
the library and tools build with no network access.

## What it shows

- **`#include`** — `build.scmake` splices in `cmake/helpers.scmake` and
  `cmake/googletest.scmake`. Paths resolve relative to the including file.
- **`function`** — `add_test_suite` and `add_tool` are real CMake functions, so
  the per-target repetition lives in one place. Parameters are bound in the
  body: `name` is `${name}`, `ARGN` is the caller's trailing arguments.
- **`install`** — as a block, including the implied-subject form inside a
  target (`install { runtime: "bin" }`).
- **Transpile-time vs configure-time** — the `for` over `SUITES` expands away
  before CMake ever runs, while the `when` around it becomes a real `if()`
  that CMake evaluates against the `TOOLKIT_BUILD_TESTS` cache entry.

## Two traps this example is shaped around

Both are CMake behaviours that fail *silently*, so `scmake` rejects them:

- **`enableTesting()` must be at directory scope.** Called inside a function,
  CMake accepts it and then emits no `CTestTestfile.cmake` at all — every test
  disappears with no error anywhere. `build.scmake` calls it directly; only the
  fetch and `include("GoogleTest")` live in `use_googletest()`.
- **A function may not be named after a built-in statement.** Naming it
  `enableTesting` would mean calls reach the built-in instead, so the function
  body would never run.
