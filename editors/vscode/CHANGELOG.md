# Changelog

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
