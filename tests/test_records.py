"""`record` declarations and the checking they enable."""

import unittest

from support import ErrorCase, compile_body

class TestRecords(unittest.TestCase):
    SUITE = ('record Suite {\n name: string\n extra: list = []\n'
             ' parallel: bool = true\n}\n')

    def test_a_record_declaration_emits_nothing(self):
        self.assertEqual(compile_body(self.SUITE), "")

    def test_defaults_are_filled_in_so_get_is_not_needed(self):
        out = compile_body(self.SUITE + 'const S: Suite[] = [{ name: "a" }]\n'
                           "for (s of S) {\n"
                           ' executable(s.name) { sources: ["m.cpp"] link: s.extra }\n}')
        self.assertEqual(out, "add_executable(a m.cpp)")

    def test_a_supplied_field_wins_over_the_default(self):
        out = compile_body(self.SUITE +
                           'const S: Suite[] = [{ name: "a", extra: [fmt] }]\n'
                           "for (s of S) {\n"
                           ' executable(s.name) { sources: ["m.cpp"] link: s.extra }\n}')
        self.assertIn("target_link_libraries(a PRIVATE fmt)", out)

    def test_a_bare_type_annotation_checks_a_single_value(self):
        self.assertEqual(compile_body('const N: number = 3\ncxx: N'),
                         "set(CMAKE_CXX_STANDARD 3)")

    def test_every_primitive_type(self):
        out = compile_body(
            'const c = library("c") { sources: ["c.cpp"] }\n'
            "record R { s: string  n: number  b: bool  l: list  a: any\n"
            "          t: target  tags: string[] }\n"
            'const S: R[] = [{ s: "x", n: 1, b: true, l: [1], a: 3, t: c,\n'
            '                  tags: ["p", "q"] }]\n'
            "for (r of S) {\n"
            ' executable(r.s) { sources: ["m.cpp"] link: [r.t] defines: r.tags }\n}')
        self.assertIn("target_link_libraries(x PRIVATE c)", out)
        self.assertIn("target_compile_definitions(x PRIVATE p q)", out)

    def test_records_nest(self):
        out = compile_body('record Dep { lib: string }\nrecord R { d: Dep }\n'
                           'const S: R[] = [{ d: { lib: "fmt" } }]\n'
                           "for (r of S) {\n"
                           ' executable("a") { sources: ["m.cpp"] link: [r.d.lib] }\n}')
        self.assertIn("target_link_libraries(a PRIVATE fmt)", out)

    def test_an_empty_list_value_emits_no_command(self):
        # A field defaulting to [] is routine, and a bare
        # target_link_libraries(a PRIVATE) would be pure noise.
        out = compile_body('const a = executable("a") { sources: ["m.cpp"] }\n'
                           "const NONE = []\na.link(NONE)")
        self.assertEqual(out, "add_executable(a m.cpp)")

    def test_comments_inside_a_record_do_not_drift_onto_the_next_statement(self):
        out = compile_body("record R {\n // the binary's name\n name: string\n}\n"
                           'executable app { sources: ["m.cpp"] }')
        self.assertEqual(out, "add_executable(app m.cpp)")


class TestRecordErrors(ErrorCase):
    def test_an_unknown_field_is_rejected_and_a_near_miss_suggested(self):
        self.expect_error('record Suite { name: string  extra: list = [] }\n'
                          'const S: Suite[] = [{ name: "a", extrs: [] }]',
                          "Suite has no field 'extrs'; it has extra, name "
                          "— did you mean 'extra'?")

    def test_a_field_with_no_default_is_required(self):
        self.expect_error("record Suite { name: string }\n"
                          "const S: Suite[] = [{ }]",
                          "S[0] is missing 'name' (string)")

    def test_a_wrongly_typed_field_names_its_path(self):
        self.expect_error("record Suite { name: string }\n"
                          "const S: Suite[] = [{ name: 3 }]",
                          "S[0].name should be string, got the number 3")

    def test_true_is_not_a_number(self):
        self.expect_error("record R { n: number }\nconst S: R[] = [{ n: true }]",
                          "S[0].n should be number, got true")

    def test_a_scalar_where_a_list_was_annotated(self):
        self.expect_error('record Suite { name: string }\n'
                          'const S: Suite[] = { name: "a" }',
                          "S should be Suite[], got an object")

    def test_an_unknown_type_is_caught_even_when_nothing_is_checked(self):
        self.expect_error("const S: Suit[] = []", "unknown type 'Suit'")

    def test_a_misspelled_primitive_is_suggested(self):
        self.expect_error("record R { a: Strng }",
                          "unknown type 'Strng' — did you mean 'string'?")

    def test_a_duplicate_record_is_rejected(self):
        self.expect_error("record R { a: string }\nrecord R { b: string }",
                          "record 'R' is already defined")

    def test_a_duplicate_field_is_rejected(self):
        self.expect_error("record R { a: string  a: number }",
                          "record 'R' declares 'a' twice")

    def test_a_record_cannot_shadow_a_primitive_type(self):
        self.expect_error("record string { a: string }", "'string' is a built-in type")

    def test_a_default_is_checked_against_its_own_field_type(self):
        self.expect_error("record R { a: string = 3 }",
                          "R.a default should be string, got the number 3")

    def test_a_target_declaration_cannot_be_annotated(self):
        self.expect_error('const a: string = executable("a") { sources: ["m.cpp"] }',
                          "a target declaration cannot be annotated")

if __name__ == "__main__":
    unittest.main()
