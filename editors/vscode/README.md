# SmartCMake for Visual Studio Code

Syntax highlighting and editing support for [SmartCMake](../../README.md)
`.scmake` sources.

## What you get

- **Highlighting** that follows the actual grammar, not a keyword-soup
  approximation. In particular the two kinds of logic are visually distinct:
  `const` / `for` / `if` (transpile-time, they vanish) read as declarations and
  control flow, while `set` / `when` (which become real `set()` / `if()`) get
  their own scopes.
- **Settings vs. free-form keys.** Known settings (`sources`, `link`,
  `compileOptions`, `cmakeMinimum`, `git`, `tag`, …) are scoped as
  `support.type.property-name`; other `key:` pairs — object literals, the
  `properties: { … }` block, `fetch` `options:` — are `variable.other.property`,
  so a typo'd setting name looks different from a correct one.
- **Visibility qualifiers.** `link(PUBLIC):`, `include(PRIVATE):`,
  `features(INTERFACE):` highlight the qualifier separately.
- **Template literals.** `` `${cmake.SOURCE_DIR}/../include` `` highlights the
  `${…}` body as an expression, with `cmake.` / `env.` / `vars.` marked as the
  builtin namespaces they are, and `GTest.gtest_main`-style references shown as
  namespace + member.
- **Comments** — `//` and `/* */` — plus bracket matching, auto-closing pairs
  (including backticks), indentation rules, and comment toggling.
- **Records and type annotations.** A `record Name { ... }` body is its own
  block, so `string` / `number` / `bool` / `target` / `list` / `any` are scoped
  as types only where a type can appear — a `buildType: Release` elsewhere is
  untouched. The annotation in `const ROWS: Suite[] = [...]` is highlighted the
  same way, and an object-literal default (`d: Dep = { lib: "x" }`) does not
  end the record block.
- **Target handles.** In `app.link(core)` the method is scoped as
  `support.function.method`, distinct from the `GTest.gtest_main` namespace
  form that shares its shape.
- **Snippets** for `project`, `executable`, `library`, `interface`, `fetch`,
  `when`, `if`, `for`, `const`, `set`, `setcache`, `discoverTests`,
  `findPackage`, `raw`, `cmake`, plus `record`, `consttyped`, `exehandle`,
  `libhandle` and `reopen`.

This is highlighting only — there is no language server, so no diagnostics or
completion. `scmake build.scmake` remains the thing that tells you whether the
file is valid.

## Install

### From the checkout (development)

Symlink the extension into your VS Code extensions directory and restart:

```sh
ln -s "$PWD/editors/vscode" ~/.vscode/extensions/smartcmake-0.2.0
```

For VS Code Insiders use `~/.vscode-insiders/extensions/` instead. Open any
`.scmake` file; the language indicator in the status bar should read
"SmartCMake".

### As a `.vsix`

```sh
npm install -g @vscode/vsce
cd editors/vscode
vsce package
code --install-extension smartcmake-0.2.0.vsix
```

## Layout

```
package.json                     contribution points (language, grammar, snippets)
language-configuration.json      comments, brackets, auto-closing, indentation
syntaxes/scmake.tmLanguage.json  the TextMate grammar (scopeName: source.scmake)
snippets/scmake.json             snippets
```

## Working on the grammar

To see the scope under the cursor, run **Developer: Inspect Editor Tokens and
Scopes** from the command palette. Changes to the grammar or the language
configuration are picked up with **Developer: Reload Window**.

The grammar was checked against `examples/hello.scmake`,
`examples/rosetta-tests.scmake` and `examples/imgfx/` (every token receives a
scope) and against a fixture covering the rest of the vocabulary in the top-level README: `cache(...)`,
`raw`, `findPackage`, `alias`, `properties`, the `defined`/`exists`/`target`/
`command` predicates, the `upper`/`lower`/`join`/`replace`/`len`/`get` builtins,
`else` / `else if`, single-quoted and multi-line template strings, and block
comments.

Every `match` / `begin` / `end` in the grammar compiles, every `captures` index
is within its pattern's group count, and every `#name` reference resolves to a
repository entry — worth re-checking after an edit, since a dangling reference
fails silently at runtime.
