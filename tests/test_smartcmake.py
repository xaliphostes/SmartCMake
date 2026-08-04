"""Run with:  python3 -m unittest discover -s tests"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from smartcmake import ScmakeError, compile_source  # noqa: E402


def compile_body(body: str) -> str:
    """Compile a project body and return the CMake below the project() line."""
    out = compile_source("project P {\n" + body + "\n}\n", "t.scmake")
    lines = out.splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith("project(")) + 1
    return "\n".join(l for l in lines[start:] if l).strip()


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


class TestTargets(unittest.TestCase):
    def test_executable_with_default_private_visibility(self):
        self.assertEqual(
            compile_body('executable app {\n sources: ["a.cpp"]\n link: [fmt] }'),
            "add_executable(app a.cpp)\ntarget_link_libraries(app PRIVATE fmt)")

    def test_explicit_visibility_qualifier(self):
        self.assertEqual(
            compile_body('executable app { sources: ["a.cpp"]\n'
                         ' include(PUBLIC): ["inc"] }'),
            "add_executable(app a.cpp)\n"
            "target_include_directories(app PUBLIC inc)")

    def test_bad_visibility_is_rejected(self):
        with self.assertRaises(ScmakeError):
            compile_body('executable app { sources: ["a.cpp"]\n link(SECRET): [x] }')

    def test_library_kind_and_default(self):
        self.assertIn("add_library(core STATIC a.cpp)",
                      compile_body('library core { sources: ["a.cpp"] }'))
        self.assertIn("add_library(core SHARED a.cpp)",
                      compile_body('library core(SHARED) { sources: ["a.cpp"] }'))

    def test_interface_library_defaults_to_interface_visibility(self):
        self.assertEqual(
            compile_body('interface hdr { include: ["inc"] }'),
            "add_library(hdr INTERFACE)\n"
            "target_include_directories(hdr INTERFACE inc)")

    def test_target_without_sources_is_an_error(self):
        with self.assertRaises(ScmakeError):
            compile_body("executable app { link: [fmt] }")

    def test_namespaced_target_reference(self):
        self.assertIn("target_link_libraries(app PRIVATE GTest::gtest_main)",
                      compile_body('executable app { sources: ["a.cpp"]\n'
                                   ' link: [GTest.gtest_main] }'))


class TestTranspileTimeConstructs(unittest.TestCase):
    def test_for_of_expands_at_compile_time(self):
        out = compile_body('const T = ["a", "b"]\n'
                           'for (t of T) { executable(t) { sources: [`${t}.cpp`] } }')
        self.assertEqual(out, "add_executable(a a.cpp)\nadd_executable(b b.cpp)")

    def test_if_picks_one_arm_and_leaves_no_trace(self):
        out = compile_body('const DEBUG = true\n'
                           'if (DEBUG) { defines: ["DBG"] } else { defines: ["NDEBUG"] }')
        self.assertEqual(out, "add_compile_definitions(DBG)")

    def test_const_never_reaches_the_output(self):
        self.assertEqual(compile_body('const X = "hello"'), "")

    def test_object_fields_and_get_default(self):
        out = compile_body('const S = [{ name: "a", extra: [fmt] }, { name: "b" }]\n'
                           'for (s of S) { executable(s.name) {\n'
                           '  sources: [`${s.name}.cpp`]\n'
                           '  link: [base] + get(s, "extra", [])\n} }')
        self.assertIn("target_link_libraries(a PRIVATE base fmt)", out)
        self.assertIn("target_link_libraries(b PRIVATE base)", out)

    def test_string_helpers(self):
        self.assertIn("add_compile_definitions(NAME=APP)",
                      compile_body('defines: [`NAME=${upper("app")}`]'))


class TestConfigureTimeConstructs(unittest.TestCase):
    def test_when_becomes_a_real_if_block(self):
        self.assertEqual(
            compile_body('when (!cmake.CXX_COMPILER) { cxxCompiler: "clang++" }'),
            "if(NOT CMAKE_CXX_COMPILER)\n"
            '    set(CMAKE_CXX_COMPILER clang++)\n'
            "endif()")

    def test_when_else_and_defined(self):
        out = compile_body('when (defined(vars.FOO) && cmake.BUILD_TYPE == "Debug") '
                           '{ defines: ["A"] } else { defines: ["B"] }')
        self.assertIn('if(DEFINED FOO AND CMAKE_BUILD_TYPE STREQUAL "Debug")', out)
        self.assertIn("else()", out)
        self.assertIn("endif()", out)

    def test_variable_and_env_references(self):
        out = compile_body('set ROOT = `${env.HOME}/sdk`\n'
                           'includeDirs: [`${vars.ROOT}/include`]')
        self.assertIn("set(ROOT $ENV{HOME}/sdk)", out)
        self.assertIn("include_directories(${ROOT}/include)", out)

    def test_cache_variable(self):
        self.assertIn('set(ROOT /opt CACHE PATH "where")',
                      compile_body('set ROOT = "/opt" cache(PATH, "where")'))


class TestFetchAndTesting(unittest.TestCase):
    def test_fetch_emits_declare_and_make_available_once(self):
        out = compile_body('fetch json { git: "https://x/json.git"\n tag: "v3" }\n'
                           'fetch gt { git: "https://x/gt.git"\n tag: "v1" }')
        self.assertEqual(out.count("include(FetchContent)"), 1)
        self.assertIn("GIT_REPOSITORY https://x/json.git", out)
        self.assertIn("FetchContent_MakeAvailable(json)", out)

    def test_fetch_options_become_forced_cache_entries(self):
        out = compile_body('fetch gt { git: "https://x/gt.git"\n'
                           ' options: { INSTALL_GTEST: false } }')
        self.assertIn('set(INSTALL_GTEST OFF CACHE BOOL "" FORCE)', out)

    def test_discover_tests_pulls_in_googletest_support(self):
        out = compile_body('executable t { sources: ["t.cpp"]\n discoverTests() }')
        self.assertIn("enable_testing()", out)
        self.assertIn("include(GoogleTest)", out)
        self.assertIn("gtest_discover_tests(t)", out)
        self.assertLess(out.index("include(GoogleTest)"), out.index("add_executable"))

    def test_explicit_enable_testing_is_not_duplicated(self):
        out = compile_body('enableTesting()\n'
                           'executable t { sources: ["t.cpp"]\n discoverTests() }')
        self.assertEqual(out.count("enable_testing()"), 1)


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


class TestExample(unittest.TestCase):
    def test_rosetta_example_compiles(self):
        path = Path(__file__).resolve().parents[1] / "examples" / "rosetta-tests.scmake"
        out = compile_source(path.read_text(), str(path))
        self.assertEqual(out.count("add_executable("), 18)
        self.assertEqual(out.count("gtest_discover_tests("), 17)
        self.assertIn("target_link_libraries(\n    inheritance\n    PRIVATE\n"
                      "    GTest::gtest_main\n    nlohmann_json::nlohmann_json\n)", out)


if __name__ == "__main__":
    unittest.main()
