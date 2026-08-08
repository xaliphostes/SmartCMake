"""`#include` — splicing another file's statements."""

import shutil
import tempfile
from pathlib import Path
import unittest

from support import ScmakeError, compile_source

class TestInclude(unittest.TestCase):
    def _tree(self, files: dict) -> Path:
        root = Path(tempfile.mkdtemp())
        for name, text in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        return root

    def test_include_splices_the_other_files_output(self):
        root = self._tree({
            "cmake/utils.scmake": 'function f(a) { raw "body()" }',
            "build.scmake": '#include "cmake/utils.scmake"\nf("x")\n',
        })
        out = compile_source((root / "build.scmake").read_text(),
                             str(root / "build.scmake"))
        self.assertIn("function(f a)", out)
        self.assertIn("f(x)", out)

    def test_paths_resolve_relative_to_the_including_file(self):
        root = self._tree({
            "a/b/leaf.scmake": 'raw "LEAF"',
            "a/mid.scmake": '#include "b/leaf.scmake"\nraw "MID"\n',
            "top.scmake": '#include "a/mid.scmake"\nraw "TOP"\n',
        })
        out = compile_source((root / "top.scmake").read_text(), str(root / "top.scmake"))
        self.assertEqual([l for l in out.splitlines() if l and not l.startswith("#")],
                         ["LEAF", "MID", "TOP"])

    def test_cycles_are_reported(self):
        root = self._tree({
            "one.scmake": '#include "two.scmake"',
            "two.scmake": '#include "one.scmake"',
        })
        with self.assertRaises(ScmakeError) as cm:
            compile_source((root / "one.scmake").read_text(), str(root / "one.scmake"))
        self.assertIn("cycle", str(cm.exception))

    def test_a_missing_include_is_reported(self):
        root = self._tree({"build.scmake": '#include "nope.scmake"'})
        with self.assertRaises(ScmakeError) as cm:
            compile_source((root / "build.scmake").read_text(),
                           str(root / "build.scmake"))
        self.assertIn("cannot read", str(cm.exception))

if __name__ == "__main__":
    unittest.main()
