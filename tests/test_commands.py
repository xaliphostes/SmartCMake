"""install, fetch and function — the rest of the vocabulary."""

import unittest

from support import ScmakeError, compile_body, compile_source

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

    def test_library_key_is_a_setting_not_a_target_declaration(self):
        # `library` also starts a target block, but in setting position
        # (right before ':') it is the LIBRARY destination.
        self.assertEqual(
            compile_body('install { targets: [core]\nlibrary: "lib"\n'
                         'archive: "lib"\nruntime: "bin" }'),
            "install(\n"
            "    TARGETS core\n"
            "    RUNTIME DESTINATION bin\n"
            "    LIBRARY DESTINATION lib\n"
            "    ARCHIVE DESTINATION lib\n"
            ")")

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

if __name__ == "__main__":
    unittest.main()
