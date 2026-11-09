"""File sets, plain libraries, late sources, prefix/suffix, and list spreading."""

import unittest

from support import ScmakeError, compile_body


class TestPlainLibrary(unittest.TestCase):
    def test_default_kind_writes_no_kind(self):
        # CMake's own default: STATIC unless BUILD_SHARED_LIBS is ON
        self.assertEqual(compile_body('library core(DEFAULT) { sources: ["a.cpp"] }'),
                         "add_library(core a.cpp)")

    def test_omitted_kind_is_still_static(self):
        self.assertEqual(compile_body('library core { sources: ["a.cpp"] }'),
                         "add_library(core STATIC a.cpp)")


class TestLateSources(unittest.TestCase):
    def test_sources_may_arrive_through_a_handle(self):
        out = compile_body('const core = library("core")(DEFAULT) {}\n'
                           'core.sources(["a.cpp"])')
        self.assertIn("add_library(core)", out)
        self.assertIn("target_sources(core PRIVATE a.cpp)", out)

    def test_sources_may_arrive_in_a_reopened_block(self):
        out = compile_body('const core = library("core") {}\ncore { sources: ["a.cpp"] }')
        self.assertIn("target_sources(core PRIVATE a.cpp)", out)

    def test_a_target_that_never_gets_sources_is_still_an_error(self):
        with self.assertRaises(ScmakeError) as cm:
            compile_body('const core = library("core") {}')
        self.assertIn("has no sources", str(cm.exception))


class TestFileSets(unittest.TestCase):
    def test_headers_file_set_in_a_block(self):
        out = compile_body('library core(DEFAULT) {\n'
                           '  fileSet(PUBLIC): { baseDirs: ["include"], files: ["include/a.h"] }\n'
                           '  sources: ["a.cpp"]\n}')
        self.assertIn("target_sources(core PUBLIC FILE_SET HEADERS BASE_DIRS include FILES "
                      "include/a.h)", out)

    def test_a_file_set_alone_is_enough_for_a_library(self):
        out = compile_body('library core(DEFAULT) { fileSet(PUBLIC): { files: ["a.h"] } }')
        self.assertIn("add_library(core)", out)

    def test_handle_method_with_visibility(self):
        out = compile_body('const core = library("core") { sources: ["a.cpp"] }\n'
                           'core.fileSet(PUBLIC, { files: ["a.h", "b.h"] })')
        self.assertIn("target_sources(core PUBLIC FILE_SET HEADERS FILES a.h b.h)", out)

    def test_named_set_needs_a_type_and_writes_it(self):
        out = compile_body('library core { sources: ["a.cpp"]\n'
                           '  fileSet(PUBLIC): { name: "api", type: "HEADERS", files: ["a.h"] } }')
        self.assertIn("FILE_SET api TYPE HEADERS FILES a.h", out)
        with self.assertRaises(ScmakeError):
            compile_body('library core { sources: ["a.cpp"]\n'
                         '  fileSet: { name: "api", files: ["a.h"] } }')

    def test_unknown_key_is_an_error(self):
        with self.assertRaises(ScmakeError) as cm:
            compile_body('library core { sources: ["a.cpp"]\n  fileSet: { file: ["a.h"] } }')
        self.assertIn("unknown fileSet key", str(cm.exception))

    def test_empty_file_set_emits_nothing(self):
        out = compile_body('library core { sources: ["a.cpp"]\n  fileSet: { files: [] } }')
        self.assertNotIn("FILE_SET", out)

    def test_long_file_sets_wrap_one_file_per_line(self):
        files = ", ".join(f'"include/sift/Header{i}.h"' for i in range(6))
        out = compile_body(f'library core {{ sources: ["a.cpp"]\n'
                           f'  fileSet(PUBLIC): {{ baseDirs: ["include"], files: [{files}] }} }}')
        self.assertIn("    FILES\n    include/sift/Header0.h\n", out)


class TestInstallFileSets(unittest.TestCase):
    def test_file_set_comes_before_includes(self):
        self.assertEqual(
            compile_body('install { targets: [core]\nexport: "T"\narchive: "lib"\n'
                         'includes: "include"\nfileSets: ["HEADERS"] }'),
            "install(\n"
            "    TARGETS core\n"
            "    EXPORT T\n"
            "    ARCHIVE DESTINATION lib\n"
            "    FILE_SET HEADERS\n"
            "    INCLUDES DESTINATION include\n"
            ")")

    def test_only_with_targets(self):
        with self.assertRaises(ScmakeError):
            compile_body('install { files: ["a"]\ndestination: "x"\nfileSets: ["HEADERS"] }')


class TestPrefixSuffix(unittest.TestCase):
    def test_on_a_list(self):
        out = compile_body('const U = ["a", "b"]\n'
                           'library core { sources: suffix(prefix(U, "src/"), ".cpp") }')
        self.assertEqual(out, "add_library(core STATIC src/a.cpp src/b.cpp)")

    def test_on_a_string(self):
        self.assertEqual(compile_body('message(prefix("x", "a/"))'), 'message(STATUS "a/x")')


class TestSpreading(unittest.TestCase):
    def test_cmake_spreads_lists(self):
        self.assertEqual(compile_body('const L = ["a.h", "b.h"]\ncmake("foo", X, L)'),
                         "foo(X a.h b.h)")

    def test_find_package_spreads_lists(self):
        self.assertEqual(
            compile_body('const C = ["core", "geometry"]\n'
                         'findPackage(cgogn, REQUIRED, COMPONENTS, C)'),
            "find_package(cgogn REQUIRED COMPONENTS core geometry)")



class TestComputedVariables(unittest.TestCase):
    def test_var_is_a_reference_in_a_value(self):
        self.assertEqual(compile_body('const c = "core"\nset X = var(`lib_${c}`)'),
                         "set(X ${lib_core})")

    def test_var_is_bare_in_a_condition(self):
        out = compile_body('const c = "core"\n'
                           'when (var(`cgogn_${c}_FOUND`) && !defined(var(`X_${c}`))) {\n'
                           '  message("ok")\n}')
        self.assertIn("if(cgogn_core_FOUND AND NOT DEFINED X_core)", out)


if __name__ == "__main__":
    unittest.main()
