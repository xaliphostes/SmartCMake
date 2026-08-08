# Changelog

## 0.2.0

- `record Name { ... }` declarations, highlighted as a block of their own so the
  field types (`string`, `number`, `bool`, `target`, `list`, `any`, and other
  records) are only special where a type is legal.
- Type annotations on `const`: `const ROWS: Suite[] = [...]`.
- Target handles: `app.link(core)` scopes the method as
  `support.function.method`, and `.length` / `.kind` as builtin properties.
  `.name` is left to the generic member rule — it is a builtin too, but far too
  common a record field to claim.
- A balanced `{ ... }` inside a record body (an object-literal default) no
  longer ends the block early.
- Snippets: `record`, `consttyped`, `exehandle`, `libhandle`, `reopen`.

## 0.1.0

Initial release.

- Syntax highlighting for `.scmake` (TextMate grammar, `source.scmake`).
- `/** ... */` scoped as `comment.block.documentation`, distinct from `/* ... */`.
- Language configuration: `//` and `/* */` comments, bracket matching and
  auto-closing for `{}`/`[]`/`()`/`"`/`'`/`` ` ``, indentation rules.
- `function` declarations, `install { ... }` blocks, and the `#include "..."`
  directive.
- Snippets for `project`, `executable`, `library`, `interface`, `function`,
  `#include`, `fetch`, `when`, `if`, `for`, `const`, `set`, `setcache`,
  `discoverTests`, `findPackage`, `raw` and `cmake`.
