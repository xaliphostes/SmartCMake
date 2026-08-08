"""How comments reach (or stay out of) the generated CMake."""

import unittest

from support import ScmakeError, compile_body, compile_source

class TestBlockComments(unittest.TestCase):
    def test_a_block_comment_spans_lines(self):
        self.assertEqual(
            compile_body('/* one\n   two */\nexecutable a { sources: ["a.cpp"] }'),
            "# one\n# two\nadd_executable(a a.cpp)")

    def test_a_doc_block_drops_its_delimiter_lines(self):
        out = compile_body('/**\n * Doc.\n * More.\n */\n'
                           'executable a { sources: ["a.cpp"] }')
        self.assertEqual(out, "# Doc.\n# More.\nadd_executable(a a.cpp)")

    def test_leading_asterisks_are_stripped(self):
        self.assertEqual(
            compile_body('/** One line. */\nexecutable a { sources: ["a.cpp"] }'),
            "# One line.\nadd_executable(a a.cpp)")

    def test_interior_blank_lines_are_kept(self):
        # Only the edges are trimmed; a blank line inside is a paragraph break.
        out = compile_source('/**\n * One.\n *\n * Two.\n */\nproject P { }', "t.scmake")
        self.assertIn("# One.\n#\n# Two.", out)

    def test_a_comment_before_code_on_the_same_line_stays_with_it(self):
        out = compile_body('executable a { sources: ["a.cpp"] }\n'
                           '/* about b */ executable b { sources: ["b.cpp"] }')
        self.assertEqual(out, "add_executable(a a.cpp)\n"
                              "# about b\nadd_executable(b b.cpp)")

    def test_an_empty_block_comment_emits_nothing(self):
        self.assertEqual(compile_body('/**/\nexecutable a { sources: ["a.cpp"] }'),
                         "add_executable(a a.cpp)")

    def test_an_unterminated_block_comment_is_an_error(self):
        with self.assertRaises(ScmakeError):
            compile_source("/* never closed\nproject P { }", "t.scmake")

if __name__ == "__main__":
    unittest.main()
