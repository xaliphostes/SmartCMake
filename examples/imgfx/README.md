# imgfx — a data-driven example

A small greyscale image tool: a core library, three filters each built into its
own static library, and a GoogleTest suite for the filters that have one. Every
filter is one row of a table in `build.scmake`, and the tool that links them is
a value the loop can reach.

Like `toolkit/`, this one really builds, so the generated CMake can be checked
against a real toolchain.

```sh
scmake build.scmake                 # writes CMakeLists.txt (gitignored)
cmake -S . -B build
cmake --build build
ctest --test-dir build              # 4 tests
./build/imgfx invert < data/gradient.pgm
```

`cmake -S . -B build -DIMGFX_BUILD_TESTS=OFF` skips the GoogleTest fetch, so
the library, filters and tool build with no network access.

The `threshold` filter's cutoff comes from the table, not from the `.cpp`:

```sh
./build/imgfx threshold < data/gradient.pgm | head -1
# 0 0 0 255 255 255 255 255      cutoff 96, from defines: ["IMGFX_THRESHOLD=96"]
# 0 0 0 0 255 255 255 255        what the .cpp's own fallback of 128 would give
```

## What it shows

- **`#include`, both of the things it can carry.** `cmake/filter.scmake`
  declares the `Filter` record and the shared `WARNINGS` list and emits no CMake
  at all — what the splice provides is the *definitions*, which stay visible
  after the splice point. `cmake/googletest.scmake` is the other kind: it is
  spliced inside the `when (vars.IMGFX_BUILD_TESTS)` block and its commands land
  right there, inside the generated `if()/endif()`. Paths resolve relative to
  the file doing the including.
- **Targets as values** — `const tool = executable("imgfx") { ... }` is declared
  *before* the filters, so the loop can call `tool.link(lib)` on each filter as
  it goes. Without handles the tool would have to be declared last and given a
  list of names that nothing checks. A handle cannot exist before its `add_*`
  line has been written, which is the order CMake needs anyway.
- **`record`** — `Filter` gives the table a shape. `defines` and `options`
  default to `[]`, so most rows leave them out and `f.defines` still reads back
  without `get(f, "defines", [])`. A misspelled key is an error at the table,
  with a line number, instead of a target that configures cleanly and fails to
  link.
- **Empty lists emit nothing** — `lib.defines(f.defines)` is written once for
  every filter but only `threshold` produces a
  `target_compile_definitions(...)`. That is what makes a defaulted field
  usable without guarding each use.
- **Transpile-time vs configure-time, nested** — `if (f.test)` is decided when
  you run `scmake`, and the arm that loses is never written out at all;
  `threshold` simply has no test target in the generated file. The `when`
  inside it becomes a real `if(IMGFX_BUILD_TESTS)` that CMake evaluates.
- **PUBLIC include propagation** — only `imgfx_core` names `include/`.
  Everything else picks it up by linking core, so the path appears once.

## Comments, and where they end up

Two rules shape where the comments in this example are written, both worth
knowing before the generated CMake surprises you:

- **A comment inside a multi-line expression attaches to the next statement.**
  So the notes about individual filters sit *above* `const FILTERS`, not between
  its rows — a note written between two rows would surface above the first
  command the loop emits, which belongs to a different filter. This is the
  limitation described at the end of the Comments section in the top-level
  README.
- **A comment block reaches the output unless the statement below it emits
  nothing.** `cmake/filter.scmake` has no blank line between its header and
  `const WARNINGS`, so the header belongs to that `const`, which produces no
  CMake and takes the comment with it. A blank line there would make it a
  free-standing block, and free-standing blocks *are* emitted — which is why
  `cmake/googletest.scmake`, whose comment cannot be dropped either way, keeps
  its header down to what a CMake reader wants to know.

## Compared with `toolkit/`

`toolkit/` factors the same kind of repetition into `function` + `#include`.
Both are the right tool in different places:

|                            | `toolkit/`                      | `imgfx/`                       |
| -------------------------- | ------------------------------- | ------------------------------ |
| repetition lives in        | a CMake `function()`            | a `for` over a table           |
| runs                       | when CMake configures           | when you run `scmake`          |
| callable from hand-written CMake | yes — it is a real function | no — it expands away           |
| per-target settings        | passed as arguments, unchecked  | record fields, checked         |

A function body cannot see scmake's data — inside it, a parameter is the string
`${name}` and nothing more, which is why `toolkit`'s table is a bare list of
names. Use a function when hand-written CMake has to call it, or when the body
must run at configure time. Use a record and a loop when the table carries
per-target settings.
