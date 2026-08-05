"""Run with:  python3 -m unittest discover -s tests"""

import shutil
import sys
import tempfile
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


class TestFunctions(unittest.TestCase):
    def test_function_wraps_its_body(self):
        out = compile_source('function f(a) { raw "body()" }', "t.scmake")
        self.assertIn("function(f a)\n    body()\nendfunction()", out)

    def test_parameters_are_bound_in_the_body(self):
        out = compile_source(
            'function addLib(name) { library(name)(SHARED) { sources: [ARGN] } }',
            "t.scmake")
        self.assertIn("add_library(${name} SHARED ${ARGN})", out)

    def test_declared_functions_become_callable(self):
        out = compile_source('function f(a) { raw "x()" }\nf("one", "two")', "t.scmake")
        self.assertIn("f(one two)", out)

    def test_unknown_calls_are_still_rejected(self):
        with self.assertRaises(ScmakeError):
            compile_source('notDeclared("x")', "t.scmake")

    def test_redefining_a_function_is_an_error(self):
        with self.assertRaises(ScmakeError):
            compile_source('function f(a) { raw "x()" }\nfunction f(b) { raw "y()" }',
                           "t.scmake")


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


class TestInstall(unittest.TestCase):
    def test_targets_with_an_artifact_destination(self):
        self.assertEqual(
            compile_body('install { targets: [app]\nruntime: "bin" }'),
            "install(TARGETS app RUNTIME DESTINATION bin)")

    def test_inside_a_target_it_defaults_to_that_target(self):
        out = compile_body('executable app { sources: ["m.cpp"]\n'
                           'install { runtime: "bin" } }')
        self.assertIn("install(TARGETS app RUNTIME DESTINATION bin)", out)

    def test_directory_form(self):
        self.assertEqual(
            compile_body('install { directory: "include/"\ndestination: "include" }'),
            "install(DIRECTORY include/ DESTINATION include)")

    def test_arguments_follow_cmake_order_not_source_order(self):
        # destination is written first but must come out after EXPORT.
        self.assertEqual(
            compile_body('install { destination: "lib"\nexport: "Ts"\n'
                         'targets: [core] }'),
            "install(TARGETS core EXPORT Ts DESTINATION lib)")

    def test_export_alone_is_the_kind(self):
        self.assertEqual(
            compile_body('install { export: "Ts"\ndestination: "lib/cmake"\n'
                         'namespace: "T::" }'),
            "install(EXPORT Ts DESTINATION lib/cmake NAMESPACE T::)")

    def test_flags_render_as_bare_words(self):
        self.assertEqual(
            compile_body('install { files: ["a.txt"]\ndestination: "share"\n'
                         'optional: true }'),
            "install(FILES a.txt DESTINATION share OPTIONAL)")

    def test_unknown_settings_are_rejected(self):
        with self.assertRaises(ScmakeError):
            compile_body('install { targets: [app]\ndestinaton: "bin" }')

    def test_a_subject_is_required_outside_a_target(self):
        with self.assertRaises(ScmakeError):
            compile_body('install { destination: "bin" }')


class TestFunctionGuards(unittest.TestCase):
    def test_shadowing_a_builtin_statement_is_rejected(self):
        with self.assertRaises(ScmakeError) as cm:
            compile_source('function enableTesting() { raw "x()" }', "t.scmake")
        self.assertIn("shadows a built-in", str(cm.exception))

    def test_enable_testing_inside_a_function_is_rejected(self):
        # CMake accepts it and then silently emits no CTestTestfile.cmake.
        with self.assertRaises(ScmakeError) as cm:
            compile_source('function setup() { enableTesting() }', "t.scmake")
        self.assertIn("directory scope", str(cm.exception))

    def test_it_is_found_through_nested_blocks(self):
        with self.assertRaises(ScmakeError):
            compile_source('function setup() { when (cmake.FOO) { enableTesting() } }',
                           "t.scmake")


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
