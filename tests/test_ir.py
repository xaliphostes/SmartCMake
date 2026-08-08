"""The analyzer's output, asserted as structure rather than as text.

These are the tests that should not move when the renderer's formatting does:
they say which commands a program means and in what order, not how the lines
come out. Everything about spelling — wrapping, indentation, blank lines — is
`test_settings.TestFormatting`'s business.
"""

import unittest

from support import analyze_source, command_names, commands, ir


class TestCommandList(unittest.TestCase):
    def test_a_target_becomes_one_add_executable_with_its_sources_folded_in(self):
        self.assertIn(
            ("add_executable", ["app", "a.cpp", "b.cpp"]),
            commands(analyze_source(
                'executable app { sources: ["a.cpp", "b.cpp"] }')))

    def test_a_setting_becomes_a_separate_command(self):
        got = commands(analyze_source(
            'executable app { sources: ["m.cpp"] link(PUBLIC): [fmt] }'))
        self.assertIn(("target_link_libraries", ["app", "PUBLIC", "fmt"]), got)

    def test_transpile_time_statements_produce_no_commands(self):
        # Only the project() line the wrapper adds; nothing from the four
        # statements below it.
        self.assertEqual(
            command_names(analyze_source(
                'const A = 1\nrecord R { a: string }\n'
                'if (A == 2) { message("no") }\nfor (x of []) { message("no") }')),
            ["project"])

    def test_an_empty_list_setting_produces_no_command_at_all(self):
        # Not an argument-less target_link_libraries — the node is never made.
        got = command_names(analyze_source(
            'const app = executable("app") { sources: ["m.cpp"] }\n'
            "const NONE = []\napp.link(NONE)"))
        self.assertEqual(got, ["project", "add_executable"])


class TestBlocks(unittest.TestCase):
    def test_a_when_is_one_block_not_three_commands(self):
        node = next(n for n in analyze_source('when (defined(X)) { message("a") }')
                    if isinstance(n, ir.Block))
        self.assertEqual(node.open, "if(DEFINED X)")
        self.assertEqual(node.close, "endif()")
        self.assertEqual(command_names(node.body), ["message"])

    def test_no_else_arm_is_none_and_an_empty_one_is_a_list(self):
        # The renderer writes `else()` for [] and nothing for None, so the two
        # cases have to stay distinguishable in the IR.
        plain = next(n for n in analyze_source('when (defined(X)) { message("a") }')
                     if isinstance(n, ir.Block))
        self.assertIsNone(plain.orelse)

        empty = next(n for n in analyze_source(
            'when (defined(X)) { message("a") } else { const UNUSED = 1 }')
            if isinstance(n, ir.Block))
        self.assertEqual(empty.orelse, [])

    def test_a_function_is_a_block_whose_body_holds_its_commands(self):
        node = next(n for n in analyze_source('function f(a) { message("x") }')
                    if isinstance(n, ir.Block))
        self.assertEqual(node.open, "function(f a)")
        self.assertEqual(node.close, "endfunction()")
        self.assertEqual(command_names(node.body), ["message"])


class TestAutoIncludePlacement(unittest.TestCase):
    """The gtest preamble goes above the first target declared at directory
    scope, however that target came to be declared."""

    # The whole sequence, not just "preamble before target": a slot that is
    # merely stale still puts the preamble first, so relative order alone
    # passes even when the preamble lands above the file header.
    EXPECTED = ["project", "enable_testing", "include", "add_executable",
                "gtest_discover_tests"]

    def test_above_a_plain_target(self):
        self.assertEqual(
            command_names(analyze_source(
                'executable t { sources: ["m.cpp"] discoverTests() }')),
            self.EXPECTED)

    def test_above_a_target_bound_to_a_const(self):
        # The declaration is one level down, inside a ConstDecl.
        self.assertEqual(
            command_names(analyze_source(
                'const t = executable("t") { sources: ["m.cpp"] }\n'
                "t.discoverTests()")),
            self.EXPECTED)

    def test_above_a_target_declared_inside_a_loop(self):
        self.assertEqual(
            command_names(analyze_source(
                'for (n of ["a"]) {\n'
                '  const t = executable(n) { sources: ["m.cpp"] }\n'
                "  t.discoverTests()\n}")),
            self.EXPECTED)

    def test_it_stays_above_the_targets_comment_block(self):
        nodes = analyze_source('// about the target\n'
                               'executable t { sources: ["m.cpp"] discoverTests() }')
        preamble = next(i for i, n in enumerate(nodes)
                        if isinstance(n, ir.Command) and n.name == "enable_testing")
        comment = next(i for i, n in enumerate(nodes)
                       if isinstance(n, ir.Comment) and "about the target" in n.lines)
        self.assertLess(preamble, comment)

    def test_when_every_target_is_nested_it_falls_back_to_the_project_line(self):
        # A target inside a `when` is not at directory scope, so nothing claims
        # the slot and the preamble goes straight after project().
        self.assertEqual(
            command_names(analyze_source(
                'when (defined(X)) {\n'
                '  executable t { sources: ["m.cpp"] discoverTests() }\n}'),
                nested=False),
            ["project", "enable_testing", "include"])


class TestRenderer(unittest.TestCase):
    def test_every_node_type_renders(self):
        from smartcmake.render import render
        out = render([ir.Comment(["c", ""]), ir.Blank(), ir.Raw(["verbatim"]),
                      ir.Command("cmd", ["a"]),
                      ir.Block("if(X)", [ir.Command("inner")], "endif()", [])])
        self.assertEqual(out, "# c\n#\n\nverbatim\ncmd(a)\nif(X)\n"
                              "    inner()\nelse()\nendif()\n")

    def test_an_unknown_node_is_an_error_rather_than_silently_dropped(self):
        from smartcmake.render import render
        with self.assertRaises(TypeError):
            render([object()])


if __name__ == "__main__":
    unittest.main()
