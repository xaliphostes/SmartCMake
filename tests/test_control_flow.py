"""Transpile-time vs configure-time branching and loops."""

import unittest

from support import compile_body

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


class TestBranchOrdering(unittest.TestCase):
    """Both arms of a `when` are walked in source order. Walking has side
    effects the output depends on, so building the else arm first would move
    them into the wrong branch."""

    def test_fetch_content_include_lands_in_the_then_branch(self):
        out = compile_body('when (defined(X)) {\n'
                           '  fetch a { git: "https://e/a.git" }\n'
                           "} else {\n"
                           '  fetch b { git: "https://e/b.git" }\n'
                           "}")
        # include(FetchContent) is emitted once, by whichever fetch runs first.
        self.assertEqual(out.count("include(FetchContent)"), 1)
        self.assertLess(out.index("include(FetchContent)"),
                        out.index("FetchContent_Declare"))
        self.assertLess(out.index("include(FetchContent)"), out.index("else()"))

    def test_an_else_arm_that_emits_nothing_still_gets_its_else(self):
        out = compile_body('when (defined(X)) {\n  message("hi")\n'
                           "} else {\n  const UNUSED = 1\n}")
        self.assertIn("else()", out)

if __name__ == "__main__":
    unittest.main()
