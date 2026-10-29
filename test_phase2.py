
import unittest

from polyglot import (
    parse_file,
    build_ast,
    create_execution_plan,
    ProgramNode,
    LanguageBlockNode,
)


class TestPhase2(unittest.TestCase):

    def setUp(self):
        source = """[python]
x = 10
[/python]

[javascript]
console.log(20);
[/javascript]"""

        parsed = parse_file(source)
        self.program = build_ast(parsed, "test.poly")

    def test_ast_root(self):
        self.assertIsInstance(self.program, ProgramNode)
        self.assertEqual(self.program.source_name, "test.poly")

    def test_ast_blocks(self):
        self.assertEqual(len(self.program.blocks), 2)
        self.assertIsInstance(
            self.program.blocks[0], LanguageBlockNode
        )
        self.assertEqual(
            self.program.blocks[0].language, "python"
        )
        self.assertEqual(
            self.program.blocks[1].language, "javascript"
        )

    def test_block_order_and_ids(self):
        ids = [b.block_id for b in self.program.blocks]
        self.assertEqual(ids, [1, 2])

    def test_execution_plan(self):
        plan = create_execution_plan(self.program)

        self.assertEqual(len(plan), 2)
        self.assertEqual(plan[0].runtime, "Python")
        self.assertEqual(plan[1].runtime, "Node.js")
        self.assertEqual(
            [step.step_id for step in plan], [1, 2]
        )

    def test_source_locations(self):
        first = self.program.blocks[0]
        self.assertEqual(first.start_line, 2)
        self.assertEqual(first.end_line, 2)


if __name__ == "__main__":
    unittest.main()
