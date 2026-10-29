
import unittest

from polyglot import parse_file, PolyglotSyntaxError


class TestPolyglotParser(unittest.TestCase):

    def test_valid_mixed_blocks(self):
        source = """[python]
x = 10
[/python]

[javascript]
console.log(20);
[/javascript]"""

        blocks = parse_file(source)

        self.assertEqual(len(blocks), 2)
        self.assertEqual(blocks[0]["language"], "python")
        self.assertEqual(blocks[1]["language"], "javascript")
        self.assertEqual(blocks[0]["code"], "x = 10")

    def test_missing_closing_tag(self):
        source = "[python]\nx = 10"

        with self.assertRaisesRegex(
            PolyglotSyntaxError, "Missing"
        ):
            parse_file(source)

    def test_mismatched_closing_tag(self):
        source = "[python]\nx = 10\n[/javascript]"

        with self.assertRaisesRegex(
            PolyglotSyntaxError, "Expected"
        ):
            parse_file(source)

    def test_nested_blocks(self):
        source = (
            "[python]\n"
            "x = 10\n"
            "[javascript]\n"
            "[/javascript]\n"
            "[/python]"
        )

        with self.assertRaisesRegex(
            PolyglotSyntaxError, "Nested"
        ):
            parse_file(source)

    def test_code_outside_block(self):
        source = "x = 10\n[python]\nprint(x)\n[/python]"

        with self.assertRaisesRegex(
            PolyglotSyntaxError, "outside"
        ):
            parse_file(source)


if __name__ == "__main__":
    unittest.main()
