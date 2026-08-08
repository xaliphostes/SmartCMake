"""The examples in examples/ still compile as documented."""

from pathlib import Path
import unittest

from support import compile_source

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
