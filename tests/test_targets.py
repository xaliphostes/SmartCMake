"""Targets: declaration, handles, and settings applied to them."""

import unittest

from support import ErrorCase, ScmakeError, compile_body, compile_source

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


class TestTargetHandles(unittest.TestCase):
    DECL = 'const app = executable("app") {\n sources: ["main.cpp"]\n}\n'

    def test_a_target_bound_to_a_const_is_still_declared(self):
        self.assertEqual(compile_body(self.DECL), "add_executable(app main.cpp)")

    def test_a_method_emits_the_standalone_command(self):
        self.assertEqual(compile_body(self.DECL + "app.link(fmt)"),
                         "add_executable(app main.cpp)\n"
                         "target_link_libraries(app PRIVATE fmt)")

    def test_a_leading_visibility_is_taken_as_the_qualifier(self):
        self.assertIn("target_include_directories(app PUBLIC inc)",
                      compile_body(self.DECL + "app.include(PUBLIC, \"inc\")"))

    def test_list_valued_arguments_are_flattened(self):
        self.assertIn("target_compile_options(app PRIVATE -Wall -Wextra)",
                      compile_body('const FLAGS = ["-Wall", "-Wextra"]\n'
                                   + self.DECL + "app.compileOptions(FLAGS)"))

    def test_sources_after_the_fact_become_target_sources(self):
        # It cannot fold into add_executable — that line is already written.
        self.assertIn("target_sources(app PRIVATE extra.cpp)",
                      compile_body(self.DECL + 'app.sources("extra.cpp")'))

    def test_properties_and_alias(self):
        out = compile_body(self.DECL + 'app.properties({ OUTPUT_NAME: "demo" })\n'
                           'app.alias("D::app")')
        self.assertIn("set_target_properties(app PROPERTIES OUTPUT_NAME demo)", out)
        self.assertIn("add_executable(D::app ALIAS app)", out)

    def test_discover_tests_still_pulls_in_the_gtest_preamble(self):
        out = compile_source("project P {\n" + self.DECL + "app.discoverTests()\n}")
        self.assertIn("gtest_discover_tests(app)", out)
        self.assertIn("enable_testing()", out)
        # The preamble has to land above the declaration, not below it.
        self.assertLess(out.index("include(GoogleTest)"), out.index("add_executable("))

    def test_a_handle_renders_as_its_name_wherever_a_name_is_expected(self):
        out = compile_body('const core = library("core") { sources: ["c.cpp"] }\n'
                           + self.DECL + "app.link(core)\n"
                           "install { targets: [core, app] destination: \"bin\" }")
        self.assertIn("target_link_libraries(app PRIVATE core)", out)
        self.assertIn("install(TARGETS core app DESTINATION bin)", out)

    def test_the_declaration_keeps_its_comment_block(self):
        out = compile_body("// The front end.\n" + self.DECL)
        self.assertEqual(out, "# The front end.\nadd_executable(app main.cpp)")

    def test_a_handle_declared_in_a_loop_is_scoped_to_the_iteration(self):
        out = compile_body('for (n of ["a", "b"]) {\n'
                           '  const t = executable(n) { sources: [`${n}.cpp`] }\n'
                           "  t.link(GTest.gtest_main)\n}")
        self.assertEqual(out.count("target_link_libraries("), 2)
        self.assertIn("target_link_libraries(b PRIVATE GTest::gtest_main)", out)

    def test_a_reopened_block_takes_the_whole_target_vocabulary(self):
        out = compile_body(self.DECL + 'app {\n defines(PUBLIC): ["F=1"]\n'
                           ' install { runtime: "bin" }\n}')
        self.assertIn("target_compile_definitions(app PUBLIC F=1)", out)
        self.assertIn("install(TARGETS app RUNTIME DESTINATION bin)", out)

    def test_sources_in_a_reopened_block_also_become_target_sources(self):
        self.assertIn("target_sources(app PRIVATE extra.cpp)",
                      compile_body(self.DECL + 'app { sources: ["extra.cpp"] }'))

    def test_an_interface_target_still_defaults_to_interface_visibility(self):
        self.assertIn("target_include_directories(h INTERFACE inc)",
                      compile_body('const h = interface("h") { }\nh.include("inc")'))


class TestTargetHandleErrors(ErrorCase):
    def test_using_a_target_before_it_is_declared(self):
        # CMake's own rule for target_*(); here it is caught at transpile time.
        self.expect_error('app.link(fmt)\nconst app = executable("app") '
                          '{ sources: ["m.cpp"] }',
                          "unknown target 'app'")

    def test_applying_a_method_to_something_that_is_not_a_target(self):
        self.expect_error('const X = "s"\nX.link(fmt)', "'X' is not a target")

    def test_an_unknown_method(self):
        self.expect_error('const a = executable("a") { sources: ["m.cpp"] }\n'
                          "a.lnk(fmt)", "a target has no lnk()")

    def test_a_field_typo_is_not_read_as_a_namespaced_target(self):
        self.expect_error('const a = executable("a") { sources: ["m.cpp"] }\n'
                          "message(a.lnk)", "a target has no field 'lnk'")

    def test_a_bare_name_in_a_const_must_be_parenthesised(self):
        self.expect_error('const a = executable a { sources: ["m.cpp"] }',
                          "give the name in parentheses")

    def test_doc_cannot_be_set_after_the_declaration(self):
        self.expect_error('const a = executable("a") { sources: ["m.cpp"] }\n'
                          'a { doc: "x" }', "doc: belongs where the target is declared")

    def test_a_method_needs_at_least_one_value(self):
        self.expect_error('const a = executable("a") { sources: ["m.cpp"] }\n'
                          "a.link()", "link(...) needs at least one value")

if __name__ == "__main__":
    unittest.main()
