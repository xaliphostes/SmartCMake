"""Directory-scope settings, and how a command is spelled."""

import unittest

from support import ScmakeError, compile_body, compile_source

class TestSettings(unittest.TestCase):
    def test_scalar_settings_map_to_cmake_variables(self):
        self.assertEqual(compile_body("cxx: 23\nstandardRequired: true"),
                         "set(CMAKE_CXX_STANDARD 23)\n"
                         "set(CMAKE_CXX_STANDARD_REQUIRED ON)")

    def test_booleans_become_on_off(self):
        self.assertEqual(compile_body("extensions: false"),
                         "set(CMAKE_CXX_EXTENSIONS OFF)")

    def test_list_settings_become_directory_commands(self):
        self.assertEqual(compile_body('compileOptions: ["-Wall", "-Wextra"]'),
                         "add_compile_options(-Wall -Wextra)")

    def test_header_settings_shape_the_project_call(self):
        out = compile_source('project P { cmakeMinimum: "3.20"\n'
                             'version: "1.2"\nlanguages: [CXX, C] }')
        self.assertIn("cmake_minimum_required(VERSION 3.20)", out)
        self.assertIn('project(P VERSION 1.2 LANGUAGES CXX C)', out)

    def test_minimum_is_hoisted_above_earlier_statements(self):
        out = compile_source('set FOO = "1"\nproject P { cmakeMinimum: "3.20" }')
        lines = [l for l in out.splitlines() if l and not l.startswith("#")]
        self.assertEqual(lines[0], "cmake_minimum_required(VERSION 3.20)")

    def test_unknown_setting_is_an_error_with_a_location(self):
        with self.assertRaises(ScmakeError) as cm:
            compile_source("project P {\n\n  nonsense: 1\n}")
        self.assertIn("unknown setting 'nonsense'", str(cm.exception))
        self.assertIn("t.scmake:3", str(cm.exception).replace("<scmake>", "t.scmake"))


class TestFormatting(unittest.TestCase):
    def test_arguments_with_spaces_are_quoted(self):
        self.assertIn('set(CMAKE_BUILD_TYPE "Rel With Deb")',
                      compile_body('buildType: "Rel With Deb"'))

    def test_long_commands_wrap_one_argument_per_line(self):
        out = compile_body('compileOptions: ["-Wall", "-Wextra", "-Wpedantic", '
                           '"-Wshadow", "-Wconversion", "-Wsign-conversion", '
                           '"-Wold-style-cast", "-Wnon-virtual-dtor"]')
        self.assertTrue(out.startswith("add_compile_options(\n    -Wall"))
        self.assertTrue(out.endswith(")"))

    def test_comments_above_a_statement_are_carried_over(self):
        out = compile_body('// keep me\ncxx: 20')
        self.assertEqual(out, "# keep me\nset(CMAKE_CXX_STANDARD 20)")

    def test_block_comments_keep_line_numbers_straight(self):
        # A /* */ comment must not shift the line count of what follows.
        with self.assertRaises(ScmakeError) as cm:
            compile_source("project P {\n/* one */\n/* two\n   three */\n bogus: 1\n}")
        self.assertIn(":5:", str(cm.exception))

    def test_block_comment_is_carried_over(self):
        self.assertEqual(compile_body("/* keep me */\ncxx: 20"),
                         "# keep me\nset(CMAKE_CXX_STANDARD 20)")

    def test_raw_passes_cmake_through_untouched(self):
        self.assertIn("foo_bar(BAZ)", compile_body('raw "foo_bar(BAZ)"'))

if __name__ == "__main__":
    unittest.main()
