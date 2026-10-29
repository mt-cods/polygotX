
import unittest

from polyglot import (
    SymbolTable,
    build_ast,
    analyze_data_flow,
    build_symbol_table,
    find_duplicate_definitions,
)


class TestPhase5SymbolTable(unittest.TestCase):

    def make_program(self, source):
        from polyglot import parse_file
        blocks = parse_file(source)
        return build_ast(blocks, "test.poly")

    def test_define_and_lookup(self):
        table = SymbolTable()
        table.define("total", 1, "python", 2)

        symbol = table.lookup("total")

        self.assertIsNotNone(symbol)
        self.assertEqual(symbol.latest_definition.block_id, 1)

    def test_missing_symbol(self):
        table = SymbolTable()
        self.assertIsNone(table.lookup("missing"))
        self.assertFalse(table.contains("missing"))

    def test_duplicate_definition_warning(self):
        source = (
            '[python]\n'
            'export("score", 70)\n'
            '[/python]\n'
            '[javascript]\n'
            'shared.score = 95;\n'
            '[/javascript]\n'
        )

        program = self.make_program(source)
        report = analyze_data_flow(program)
        table = build_symbol_table(program, report)
        warnings = find_duplicate_definitions(table)

        self.assertEqual(len(warnings), 1)
        self.assertIn("score", warnings[0])

    def test_single_definition_has_no_warning(self):
        source = (
            '[python]\n'
            'export("total", 100)\n'
            '[/python]\n'
        )

        program = self.make_program(source)
        report = analyze_data_flow(program)
        table = build_symbol_table(program, report)

        self.assertEqual(find_duplicate_definitions(table), [])

    def test_multiple_definitions_are_preserved(self):
        table = SymbolTable()
        table.define("value", 1, "python", 2)
        table.define("value", 2, "javascript", 5)

        symbol = table.lookup("value")

        self.assertEqual(len(symbol.definitions), 2)
        self.assertEqual(
            symbol.latest_definition.language, "javascript"
        )


if __name__ == "__main__":
    unittest.main()
