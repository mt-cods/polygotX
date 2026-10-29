
import unittest
import subprocess
import sys
from pathlib import Path


class TestPhase4Diagnostics(unittest.TestCase):

    def run_program(self, source):
        test_file = Path("phase4_temp.poly")
        test_file.write_text(source, encoding="utf-8")

        try:
            return subprocess.run(
                [sys.executable, "polyglot.py", str(test_file)],
                capture_output=True,
                text=True,
                timeout=10
            )
        finally:
            test_file.unlink(missing_ok=True)

    def test_python_runtime_error(self):
        result = self.run_program(
            "[python]\n"
            "x = 1\n"
            "y = 1 / 0\n"
            "[/python]\n"
        )

        self.assertIn("RUNTIME ERROR", result.stdout)
        self.assertIn("ZeroDivisionError", result.stdout + result.stderr)

    def test_javascript_runtime_error(self):
        result = self.run_program(
            "[javascript]\n"
            "throw new Error('test failure');\n"
            "[/javascript]\n"
        )

        self.assertIn("RUNTIME ERROR", result.stdout)
        self.assertIn("test failure", result.stdout + result.stderr)

    def test_missing_closing_tag(self):
        result = self.run_program(
            "[python]\n"
            "print('hello')\n"
        )

        self.assertIn("Missing [/python]", result.stdout)

    def test_successful_program(self):
        result = self.run_program(
            "[python]\n"
            "export('answer', 42)\n"
            "[/python]\n"
            "[javascript]\n"
            "console.log(shared.answer);\n"
            "[/javascript]\n"
        )

        self.assertIn("42", result.stdout)
        self.assertNotIn("RUNTIME ERROR", result.stdout)


if __name__ == "__main__":
    unittest.main()
