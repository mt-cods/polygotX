
import unittest

from polyglot import (
    parse_file,
    build_ast,
    analyze_data_flow,
)


class TestPhase3(unittest.TestCase):

    def make_program(self, source):
        blocks = parse_file(source)
        return build_ast(blocks, "test.poly")

    def test_valid_python_to_javascript_flow(self):
        source = """[python]
export("total", 100)
[/python]
[javascript]
console.log(shared.total);
[/javascript]"""

        report = analyze_data_flow(
            self.make_program(source)
        )

        self.assertEqual(report.issues, [])
        self.assertEqual(len(report.dependencies), 1)
        self.assertEqual(
            report.dependencies[0]["variable"], "total"
        )
        self.assertEqual(
            report.dependencies[0]["from_block"], 1
        )
        self.assertEqual(
            report.dependencies[0]["to_block"], 2
        )

    def test_missing_shared_variable(self):
        source = """[javascript]
console.log(shared.salary);
[/javascript]"""

        report = analyze_data_flow(
            self.make_program(source)
        )

        self.assertEqual(len(report.issues), 1)
        self.assertEqual(
            report.issues[0].variable, "salary"
        )

    def test_multiple_definitions(self):
        source = """[python]
export("total", 100)
[/python]
[python]
export("total", 200)
[/python]"""

        report = analyze_data_flow(
            self.make_program(source)
        )

        self.assertEqual(
            len(report.definitions["total"]), 2
        )

    def test_javascript_can_export_shared_value(self):
        source = """[javascript]
shared.result = 42;
[/javascript]
[python]
print(shared["result"])
[/python]"""

        report = analyze_data_flow(
            self.make_program(source)
        )

        self.assertEqual(report.issues, [])
        self.assertEqual(len(report.dependencies), 1)

    def test_python_shared_dictionary_read(self):
        source = """[python]
export("total", 100)
[/python]
[python]
print(shared["total"])
[/python]"""

        report = analyze_data_flow(
            self.make_program(source)
        )

        self.assertEqual(report.issues, [])
        self.assertEqual(len(report.dependencies), 1)


if __name__ == "__main__":
    unittest.main()
