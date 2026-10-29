
import unittest

from polyglot import (
    parse_file,
    build_ast,
    lower_to_ir,
    IntermediateRepresentation,
)


class TestPhase6IR(unittest.TestCase):

    def make_program(self, source):
        blocks = parse_file(source)
        return build_ast(blocks, "test.poly")

    def test_ir_type(self):
        program = self.make_program(
            "[python]\n"
            "x = 10\n"
            "[/python]\n"
        )

        ir = lower_to_ir(program)

        self.assertIsInstance(
            ir, IntermediateRepresentation
        )

    def test_one_instruction_per_block(self):
        program = self.make_program(
            "[python]\n"
            "x = 10\n"
            "[/python]\n"
            "[javascript]\n"
            "console.log(20);\n"
            "[/javascript]\n"
        )

        ir = lower_to_ir(program)

        self.assertEqual(len(ir.instructions), 2)

    def test_instruction_order(self):
        program = self.make_program(
            "[python]\n"
            "x = 10\n"
            "[/python]\n"
            "[javascript]\n"
            "console.log(x);\n"
            "[/javascript]\n"
        )

        ir = lower_to_ir(program)

        self.assertEqual(
            [item.instruction_id for item in ir.instructions],
            [1, 2],
        )
        self.assertEqual(
            [item.language for item in ir.instructions],
            ["python", "javascript"],
        )

    def test_source_locations_are_preserved(self):
        program = self.make_program(
            "[python]\n"
            "x = 10\n"
            "[/python]\n"
        )

        ir = lower_to_ir(program)

        self.assertEqual(
            ir.instructions[0].source_line, 2
        )
        self.assertEqual(
            ir.instructions[0].operands["end_line"], 2
        )

    def test_empty_program(self):
        program = self.make_program("")
        ir = lower_to_ir(program)

        self.assertEqual(ir.instructions, [])


if __name__ == "__main__":
    unittest.main()
