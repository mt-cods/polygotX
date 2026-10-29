import json
import re
import subprocess
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import List
from dataclasses import dataclass
import re

MARKER = "__POLY_SHARED__"

PY_RUNNER = r'''
import json
import sys
import traceback

p = json.loads(sys.stdin.read())
shared = p["shared"]

def export(name, value):
    shared[name] = value

env = {
    "__builtins__": __builtins__,
    "shared": shared,
    "export": export,
}

# Import variables from previous blocks
env.update(shared)

source_code = "\n" * (p["line"] - 1) + p["code"]

try:
    exec(compile(source_code, p["filename"], "exec"), env)

    # Export variables defined in this Python block
    for name, value in env.items():
        if name.startswith("_") or name in ("shared", "export"):
            continue

        try:
            json.dumps(value)
            shared[name] = value
        except (TypeError, ValueError):
            pass

    print("__POLY_SHARED__" + json.dumps(shared))

except Exception:
    traceback.print_exc()
    sys.exit(1)
'''

JS_RUNNER = r'''
const fs = require("fs");
const p = JSON.parse(fs.readFileSync(0, "utf8"));
const shared = p.shared;

const sourceCode =
    "\n".repeat(p.line - 1) +
    p.code +
    "\n//# sourceURL=" + p.filename;

const blocked = new Set([
    "p", "fs", "shared", "sourceCode", "blocked", "scope"
]);

const scope = new Proxy(shared, {
    has(target, key) {
        if (typeof key !== "string") return false;
        if (blocked.has(key)) return false;
        if (key in globalThis) return false;
        return true;
    },

    get(target, key) {
        return target[key];
    },

    set(target, key, value) {
        target[key] = value;
        return true;
    }
});

try {
    with (scope) {
        eval(sourceCode);
    }

    console.log("__POLY_SHARED__" + JSON.stringify(shared));
} catch (e) {
    console.error(e.stack || e.message);
    process.exitCode = 1;
}
'''

import re


class PolyglotSyntaxError(Exception):
    """Error in the outer Polyglot source-file structure."""


class Lexer:
    """Converts source lines into Polyglot structural tokens."""

    MARKER_PATTERN = re.compile(
        r"^\s*\[(?P<closing>/)?"
        r"(?P<language>python|javascript)\]\s*$"
    )

    def __init__(self, source):
        self.source = source

    def tokenize(self):
        tokens = []

        for line_number, line in enumerate(
            self.source.splitlines(), start=1
        ):
            match = self.MARKER_PATTERN.fullmatch(line)

            if match:
                language = match.group("language")
                closing = match.group("closing")

                tokens.append({
                    "type": "END" if closing else "START",
                    "language": language,
                    "line": line_number,
                    "text": line,
                })
            else:
                tokens.append({
                    "type": "LINE",
                    "language": None,
                    "line": line_number,
                    "text": line,
                })

        return tokens


class Parser:
    """Validates tokens and builds a structured block list."""

    def __init__(self, tokens):
        self.tokens = tokens

    def parse(self):
        blocks = []
        current_language = None
        code_lines = []
        start_line = None

        for token in self.tokens:
            kind = token["type"]
            line_number = token["line"]
            text = token["text"]

            if kind == "START":
                if current_language is not None:
                    raise PolyglotSyntaxError(
                        f"Line {line_number}: Nested block "
                        f"inside [{current_language}]"
                    )

                current_language = token["language"]
                code_lines = []
                start_line = line_number + 1

            elif kind == "END":
                if current_language is None:
                    raise PolyglotSyntaxError(
                        f"Line {line_number}: Unexpected closing "
                        f"tag {text}"
                    )

                if token["language"] != current_language:
                    raise PolyglotSyntaxError(
                        f"Line {line_number}: Expected "
                        f"[/{current_language}], got {text}"
                    )

                blocks.append({
                    "language": current_language,
                    "code": "\n".join(code_lines),
                    "line": start_line,
                    "end_line": line_number - 1,
                })

                current_language = None
                code_lines = []
                start_line = None

            else:
                if current_language is None:
                    if text.strip():
                        raise PolyglotSyntaxError(
                            f"Line {line_number}: Code outside "
                            f"a language block"
                        )
                else:
                    code_lines.append(text)

        if current_language is not None:
            raise PolyglotSyntaxError(
                f"End of file: Missing "
                f"[/{current_language}] closing tag"
            )

        return blocks


def parse_file(source):
    lexer = Lexer(source)
    tokens = lexer.tokenize()

    parser = Parser(tokens)
    return parser.parse()


# ---------- PHASE 2: AST + EXECUTION PLAN ----------

@dataclass
class LanguageBlockNode:
    """AST node representing one language block."""

    block_id: int
    language: str
    code: str
    start_line: int
    end_line: int


@dataclass
class ProgramNode:
    """Root node representing the entire Polyglot program."""

    source_name: str
    blocks: List[LanguageBlockNode]


@dataclass
class ExecutionStep:
    """One step in the generated execution plan."""

    step_id: int
    block_id: int
    language: str
    runtime: str
    start_line: int
    end_line: int


def build_ast(parsed_blocks, source_name):
    """Convert parser output into structured AST nodes."""

    ast_blocks = []

    for index, block in enumerate(parsed_blocks, start=1):
        node = LanguageBlockNode(
            block_id=index,
            language=block["language"],
            code=block["code"],
            start_line=block["line"],
            end_line=block["end_line"],
        )
        ast_blocks.append(node)

    return ProgramNode(
        source_name=source_name,
        blocks=ast_blocks,
    )


def create_execution_plan(program):
    """Determine which runtime executes each block."""

    plan = []

    for index, block in enumerate(program.blocks, start=1):
        if block.language == "python":
            runtime = "Python"
        elif block.language == "javascript":
            runtime = "Node.js"
        else:
            raise ValueError(
                f"Unsupported language: {block.language}"
            )

        plan.append(
            ExecutionStep(
                step_id=index,
                block_id=block.block_id,
                language=block.language,
                runtime=runtime,
                start_line=block.start_line,
                end_line=block.end_line,
            )
        )

    return plan


# ---------- PHASE 3: DATA-FLOW ANALYSIS ----------

@dataclass
class DataFlowIssue:
    severity: str
    message: str
    block_id: int
    line: int
    variable: str


@dataclass
class DataFlowReport:
    definitions: dict
    dependencies: list
    issues: list



# def analyze_data_flow(program):
#     import ast
#     import re

#     definitions = {}
#     dependencies = []
#     issues = []
#     available = {}

#     def get_line(block, code, position):
#         return block.start_line + code[:position].count("\n")

#     def record_write(block, name, line):
#         definitions.setdefault(name, []).append({
#             "block_id": block.block_id,
#             "language": block.language,
#             "line": line,
#         })

#         available[name] = {
#             "block_id": block.block_id,
#             "language": block.language,
#             "line": line,
#         }

#     def record_read(block, name, line):
#         if name not in available:
#             issues.append(DataFlowIssue(
#                 severity="ERROR",
#                 message=(
#                     f"Shared variable '{name}' has no "
#                     "preceding definition."
#                 ),
#                 block_id=block.block_id,
#                 line=line,
#                 variable=name,
#             ))
#         else:
#             producer = available[name]
#             dependencies.append({
#                 "variable": name,
#                 "from_block": producer["block_id"],
#                 "to_block": block.block_id,
#                 "line": line,
#             })

#     for block in program.blocks:
#         code = block.code
#         lang = block.language

#         # Events are processed in source order.
#         events = []

#         if lang == "python":
#             # Parse Python syntax to find export() calls and
#             # shared reads. This is more reliable than regex alone.
#             try:
#                 tree = ast.parse(code)
#             except SyntaxError:
#                 # Leave syntax-error reporting to the runtime.
#                 continue

#             class PythonVisitor(ast.NodeVisitor):
#                 def visit_Call(self, node):
#                     # export("name", value)
#                     if (
#                         isinstance(node.func, ast.Name)
#                         and node.func.id == "export"
#                         and len(node.args) >= 2
#                         and isinstance(node.args[0], ast.Constant)
#                         and isinstance(node.args[0].value, str)
#                     ):
#                         name = node.args[0].value
#                         position = (
#                             node.lineno,
#                             node.col_offset,
#                             "write",
#                             name,
#                         )
#                         events.append(position)

#                     # shared["name"]
#                     # shared.get("name")
#                     if (
#                         isinstance(node.func, ast.Attribute)
#                         and isinstance(node.func.value, ast.Name)
#                         and node.func.value.id == "shared"
#                         and node.func.attr == "get"
#                         and node.args
#                         and isinstance(node.args[0], ast.Constant)
#                         and isinstance(node.args[0].value, str)
#                     ):
#                         events.append((
#                             node.lineno,
#                             node.col_offset,
#                             "read",
#                             node.args[0].value,
#                         ))

#                     self.generic_visit(node)

#                 def visit_Subscript(self, node):
#                     if (
#                         isinstance(node.value, ast.Name)
#                         and node.value.id == "shared"
#                         and isinstance(node.slice, ast.Constant)
#                         and isinstance(node.slice.value, str)
#                     ):
#                         # shared["name"] = value is a write.
#                         if isinstance(node.ctx, ast.Store):
#                             events.append((
#                                 node.lineno,
#                                 node.col_offset,
#                                 "write",
#                                 node.slice.value,
#                             ))
#                         else:
#                             events.append((
#                                 node.lineno,
#                                 node.col_offset,
#                                 "read",
#                                 node.slice.value,
#                             ))

#                     self.generic_visit(node)

#             PythonVisitor().visit(tree)

#         elif lang == "javascript":
#             # Lightweight JavaScript scanner. This recognizes
#             # dot notation and quoted bracket notation.
#             pattern = re.compile(
#                 r"""(?<![\w$])shared\s*"""
#                 r"""(?:\.\s*([A-Za-z_$][\w$]*)"""
#                 r"""|\[\s*["']([^"']+)["']\s*\])"""
#                 r"""\s*(?:(=(?!=|>)|\+\+|--))?"""
#             )

#             for match in pattern.finditer(code):
#                 name = match.group(1) or match.group(2)
#                 operator = match.group(3)
#                 line = get_line(block, code, match.start())

#                 if operator in ("=", "++", "--"):
#                     events.append((
#                         line,
#                         match.start(),
#                         "write",
#                         name,
#                     ))

#                     # Increment/decrement also reads the old value.
#                     if operator in ("++", "--"):
#                         events.append((
#                             line,
#                             match.start(),
#                             "read",
#                             name,
#                         ))
#                 else:
#                     events.append((
#                         line,
#                         match.start(),
#                         "read",
#                         name,
#                     ))

#         # Sort by source location. For assignment, process the
#         # write before later reads in the same statement.
#         events.sort(key=lambda event: (event[0], event[1]))

#         for line, position, kind, name in events:
#             if kind == "read":
#                 record_read(block, name, line)
#             else:
#                 record_write(block, name, line)

#     return DataFlowReport(
#         definitions=definitions,
#         dependencies=dependencies,
#         issues=issues,
#     )


def analyze_data_flow(program):
    import ast
    import re
    import builtins

    definitions = {}
    dependencies = []
    issues = []
    available = {}

    # Names that are language-provided, not shared variables.
    python_builtins = set(dir(builtins))

    js_globals = {
        "console", "Math", "JSON", "Array", "Object",
        "String", "Number", "Boolean", "Date", "Promise",
        "Map", "Set", "RegExp", "Error", "undefined",
        "NaN", "Infinity", "parseInt", "parseFloat",
        "isNaN", "require", "process"
    }

    def record_write(block, name, line):
        if not name or name.startswith("_"):
            return

        item = {
            "block_id": block.block_id,
            "language": block.language,
            "line": line,
        }

        definitions.setdefault(name, []).append(item)
        available[name] = item

    def record_read(block, name, line):
        if not name or name.startswith("_"):
            return

        if name not in available:
            issues.append(DataFlowIssue(
                severity="ERROR",
                message=(
                    f"Variable '{name}' is read before "
                    "a preceding shared definition."
                ),
                block_id=block.block_id,
                line=line,
                variable=name,
            ))
        else:
            producer = available[name]

            dependencies.append({
                "variable": name,
                "from_block": producer["block_id"],
                "to_block": block.block_id,
                "line": line,
            })

    for block in program.blocks:
        code = block.code
        lang = block.language

        # --------------------------------------------------
        # PYTHON ANALYSIS
        # --------------------------------------------------
        if lang == "python":
            try:
                tree = ast.parse(code)
            except SyntaxError:
                # Runtime will report the syntax error.
                continue

            class PythonVisitor(ast.NodeVisitor):
                def line(self, node):
                    return block.start_line + node.lineno - 1

                def visit_Name(self, node):
                    # Reads are ordinary variable references.
                    if isinstance(node.ctx, ast.Load):
                        if node.id not in python_builtins:
                            record_read(
                                block, node.id, self.line(node)
                            )

                def write_target(self, target):
                    # Handle x = ..., a, b = ..., etc.
                    if isinstance(target, ast.Name):
                        record_write(
                            block, target.id, self.line(target)
                        )

                    elif isinstance(target, (ast.Tuple, ast.List)):
                        for element in target.elts:
                            self.write_target(element)

                    elif isinstance(target, ast.Starred):
                        self.write_target(target.value)

                    elif isinstance(target, ast.Subscript):
                        self.visit(target)

                def visit_Assign(self, node):
                    # Read RHS first, then define LHS variables.
                    self.visit(node.value)

                    for target in node.targets:
                        self.write_target(target)

                def visit_AnnAssign(self, node):
                    if node.value is not None:
                        self.visit(node.value)

                    self.write_target(node.target)

                def visit_AugAssign(self, node):
                    # x += 1 reads x before updating it.
                    if isinstance(node.target, ast.Name):
                        record_read(
                            block,
                            node.target.id,
                            self.line(node),
                        )
                        self.visit(node.value)
                        record_write(
                            block,
                            node.target.id,
                            self.line(node),
                        )
                    else:
                        self.generic_visit(node)

                def visit_NamedExpr(self, node):
                    self.visit(node.value)
                    self.write_target(node.target)

                def visit_FunctionDef(self, node):
                    # Function names can be shared, but function
                    # locals are not shared variables.
                    record_write(
                        block, node.name, self.line(node)
                    )
                    # Do not analyze the function body as if it
                    # executes immediately.

                def visit_AsyncFunctionDef(self, node):
                    record_write(
                        block, node.name, self.line(node)
                    )

                def visit_ClassDef(self, node):
                    record_write(
                        block, node.name, self.line(node)
                    )
                    # Class-body analysis needs separate scope rules.

                def visit_Import(self, node):
                    for alias in node.names:
                        name = alias.asname or alias.name.split(".")[0]
                        record_write(
                            block, name, self.line(node)
                        )

                def visit_ImportFrom(self, node):
                    for alias in node.names:
                        if alias.name != "*":
                            name = alias.asname or alias.name
                            record_write(
                                block, name, self.line(node)
                            )

                def visit_Call(self, node):
                    # export("name", value)
                    if (
                        isinstance(node.func, ast.Name)
                        and node.func.id == "export"
                        and len(node.args) >= 2
                        and isinstance(node.args[0], ast.Constant)
                        and isinstance(node.args[0].value, str)
                    ):
                        record_write(
                            block,
                            node.args[0].value,
                            self.line(node),
                        )

                    # shared.get("name")
                    if (
                        isinstance(node.func, ast.Attribute)
                        and isinstance(node.func.value, ast.Name)
                        and node.func.value.id == "shared"
                        and node.func.attr == "get"
                        and node.args
                        and isinstance(node.args[0], ast.Constant)
                        and isinstance(node.args[0].value, str)
                    ):
                        record_read(
                            block,
                            node.args[0].value,
                            self.line(node),
                        )

                    self.generic_visit(node)

                def visit_Subscript(self, node):
                    if (
                        isinstance(node.value, ast.Name)
                        and node.value.id == "shared"
                        and isinstance(node.slice, ast.Constant)
                        and isinstance(node.slice.value, str)
                    ):
                        name = node.slice.value

                        if isinstance(node.ctx, ast.Store):
                            record_write(
                                block, name, self.line(node)
                            )
                        elif isinstance(node.ctx, ast.Load):
                            record_read(
                                block, name, self.line(node)
                            )

                        # Avoid recording shared as an ordinary
                        # variable reference.
                        if not isinstance(node.ctx, ast.Store):
                            self.visit(node.slice)
                        return

                    self.generic_visit(node)

            PythonVisitor().visit(tree)

        # --------------------------------------------------
        # JAVASCRIPT ANALYSIS
        # --------------------------------------------------
        elif lang == "javascript":
            # This lightweight scanner supports simple identifier
            # assignments and references. It is not a full JS parser.

            # Mask comments and quoted strings to avoid interpreting
            # identifiers inside them as variable references.
            masked = list(code)
            pattern = re.compile(
                r"""//[^\n]*|/\*[\s\S]*?\*/|"""
                r"""'(?:\\.|[^'\\])*'|"""
                r'''"(?:\\.|[^"\\])*"|'''
                r"""`(?:\\.|[^`\\])*`"""
            )

            for match in pattern.finditer(code):
                for i in range(match.start(), match.end()):
                    if masked[i] != "\n":
                        masked[i] = " "

            clean = "".join(masked)

            # Names declared with let/const/var are block-local
            # in this interpreter's separate JS eval blocks.
            local_names = set(
                re.findall(
                    r"\b(?:let|const|var)\s+"
                    r"([A-Za-z_$][\w$]*)",
                    clean,
                )
            )

            # Skip declarations themselves; they are not shared
            # across separately evaluated JS blocks.
            tokens = list(re.finditer(
                r"[A-Za-z_$][\w$]*|"
                r"\+\+|--|"
                r"\+=|-=|\*=|/=|"
                r"=(?!=|>)",
                clean,
            ))

            # Determine simple assignment targets.
            writes = {}

            for i, token in enumerate(tokens):
                name = token.group()

                if not re.fullmatch(r"[A-Za-z_$][\w$]*", name):
                    continue

                next_token = tokens[i + 1] if i + 1 < len(tokens) else None

                if next_token and next_token.group() in {
                    "=", "+=", "-=", "*=", "/=", "++", "--"
                }:
                    # Ignore declared local variables.
                    if name not in local_names:
                        writes.setdefault(token.start(), []).append(
                            (name, token.start())
                        )

            for token in tokens:
                name = token.group()

                if not re.fullmatch(r"[A-Za-z_$][\w$]*", name):
                    continue

                position = token.start()
                line = block.start_line + code[:position].count("\n")

                # Ignore language globals and declared locals.
                if name in js_globals or name in local_names:
                    continue

                # Ignore property names, e.g. console.log.
                before = clean[:position].rstrip()
                if before.endswith("."):
                    continue

                # Ignore declaration keywords.
                if name in {
                    "let", "const", "var", "function", "return",
                    "if", "else", "for", "while", "true", "false",
                    "null", "new", "throw", "try", "catch",
                    "typeof", "instanceof", "await", "async"
                }:
                    continue

                # Ignore the identifier in a simple assignment
                # target; process its write at the operator.
                following = clean[token.end():].lstrip()
                is_target = bool(re.match(
                    r"(?:\+=|-=|\*=|/=|=(?!=|>)|\+\+|--)",
                    following,
                ))

                if is_target:
                    continue

                # A normal identifier occurrence is a read.
                record_read(block, name, line)

            # Process writes after reads have been scanned.
            # This is a simplified approximation for basic code.
            for position, entries in writes.items():
                line = block.start_line + code[:position].count("\n")
                for name, _ in entries:
                    record_write(block, name, line)

    return DataFlowReport(
        definitions=definitions,
        dependencies=dependencies,
        issues=issues,
    )


from dataclasses import dataclass, field
from typing import Any


@dataclass
class IRInstruction:
    instruction_id: int
    opcode: str
    block_id: int
    language: str
    source_line: int
    operands: dict = field(default_factory=dict)


@dataclass
class IntermediateRepresentation:
    source_name: str
    instructions: list = field(default_factory=list)

    def display(self):
        print("\n========== INTERMEDIATE REPRESENTATION ==========")

        if not self.instructions:
            print("No instructions.")
            return

        for instruction in self.instructions:
            print(
                f"IR{instruction.instruction_id}: "
                f"{instruction.opcode} | "
                f"block={instruction.block_id} | "
                f"language={instruction.language} | "
                f"line={instruction.source_line}"
            )
            if instruction.operands:
                print(f"    operands={instruction.operands}")


def lower_to_ir(program):
    ir = IntermediateRepresentation(
        source_name=program.source_name
    )

    next_id = 1

    for block in program.blocks:
        ir.instructions.append(
            IRInstruction(
                instruction_id=next_id,
                opcode="EXEC_BLOCK",
                block_id=block.block_id,
                language=block.language,
                source_line=block.start_line,
                operands={
                    "code": block.code,
                    "end_line": block.end_line,
                    "runtime": (
                        "Python"
                        if block.language == "python"
                        else "Node.js"
                    ),
                },
            )
        )
        next_id += 1

    return ir


def execute_ir(ir, shared=None):
    if shared is None:
        shared = {}

    print("\n========== PROGRAM OUTPUT ==========")

    for instruction in ir.instructions:
        print(
            f"\n[IR{instruction.instruction_id}] "
            f"Executing {instruction.language}"
        )

        runtime_block = {
            "language": instruction.language,
            "code": instruction.operands["code"],
            "line": instruction.source_line,
            "filename": ir.source_name,
        }

        shared = run_block(runtime_block, shared)

    print("\nFinal shared data:", shared)
    return shared


def display_data_flow_report(report):
    """Display detected definitions and dependencies."""

    print("\n========== DATA-FLOW ANALYSIS ==========")

    print("\nExported/shared variables:")

    if not report.definitions:
        print("  No shared variable definitions found.")

    for name, locations in report.definitions.items():
        for item in locations:
            print(
                f"  {name}: Block #{item['block_id']} "
                f"({item['language']}), "
                f"line {item['line']}"
            )

    print("\nDependencies:")

    if not report.dependencies:
        print("  No cross-block dependencies found.")

    for dep in report.dependencies:
        print(
            f"  Block #{dep['to_block']} reads "
            f"'{dep['variable']}' from "
            f"Block #{dep['from_block']} "
            f"(line {dep['line']})"
        )

    print("\nDiagnostics:")

    if not report.issues:
        print("  No missing shared variables detected.")

    for issue in report.issues:
        print(
            f"  {issue.severity}: {issue.message} "
            f"Block #{issue.block_id}, "
            f"line {issue.line}"
        )


def display_ast(program):
    """Print a readable representation of the AST."""

    print("\n========== POLYGLOT AST ==========")
    print(f"Program: {program.source_name}")
    print(f"Total blocks: {len(program.blocks)}")

    for block in program.blocks:
        print(
            f"\n  LanguageBlockNode #{block.block_id}"
        )
        print(f"    Language: {block.language}")
        print(
            f"    Source lines: "
            f"{block.start_line}-{block.end_line}"
        )
        print(f"    Code:\n{block.code}")


def display_execution_plan(plan):
    """Show the execution plan before running code."""

    print("\n========== EXECUTION PLAN ==========")

    if not plan:
        print("No executable blocks found.")
        return

    for step in plan:
        print(
            f"Step {step.step_id}: "
            f"Block #{step.block_id} | "
            f"Language: {step.language} | "
            f"Runtime: {step.runtime} | "
            f"Lines: {step.start_line}-{step.end_line}"
        )


from dataclasses import dataclass, field


@dataclass
class SymbolDefinition:
    name: str
    block_id: int
    language: str
    line: int


@dataclass
class Symbol:
    name: str
    definitions: list = field(default_factory=list)

    @property
    def latest_definition(self):
        if not self.definitions:
            return None
        return self.definitions[-1]


@dataclass
class SymbolTable:
    symbols: dict = field(default_factory=dict)

    def define(self, name, block_id, language, line):
        symbol = self.symbols.setdefault(name, Symbol(name=name))

        previous = symbol.latest_definition

        definition = SymbolDefinition(
            name=name,
            block_id=block_id,
            language=language,
            line=line
        )

        symbol.definitions.append(definition)
        return previous

    def lookup(self, name):
        return self.symbols.get(name)

    def contains(self, name):
        return name in self.symbols

    def display(self):
        print("\n========== SYMBOL TABLE ==========")

        if not self.symbols:
            print("No shared symbols found.")
            return

        for name, symbol in self.symbols.items():
            print(f"\nSymbol: {name}")

            for index, definition in enumerate(
                symbol.definitions, start=1
            ):
                print(
                    f"  Definition {index}: "
                    f"Block #{definition.block_id} "
                    f"({definition.language}), "
                    f"line {definition.line}"
                )


def build_symbol_table(program, report):
    table = SymbolTable()

    # Definitions are stored by variable name in Phase 3.
    for name, locations in report.definitions.items():
        for item in locations:
            table.define(
                name=name,
                block_id=item["block_id"],
                language=item["language"],
                line=item["line"]
            )

    return table


def find_duplicate_definitions(table):
    warnings = []

    for name, symbol in table.symbols.items():
        if len(symbol.definitions) > 1:
            for definition in symbol.definitions[1:]:
                warnings.append(
                    f"WARNING: Shared variable '{name}' is "
                    f"redefined in Block #{definition.block_id} "
                    f"({definition.language}), line {definition.line}."
                )

    return warnings


def run_block(block, shared):
    lang = block["language"]

    payload = {
        "code": block["code"],
        "shared": shared,
        "filename": block.get("filename", "program.poly"),
        "line": block["line"]
    }

    if lang == "python":
        command = [sys.executable, "-c", PY_RUNNER]
    elif lang == "javascript":
        command = ["node", "-e", JS_RUNNER]
    else:
        raise ValueError(f"Unsupported language: {lang}")

    try:
        result = subprocess.run(
            command,
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            timeout=5
        )
    except subprocess.TimeoutExpired:
        print(
            f"\nRUNTIME ERROR: {payload['filename']}, "
            f"block starting at line {block['line']}"
        )
        print(f"The {lang} block exceeded the 5-second timeout.")
        raise RuntimeError("Execution stopped: timeout")

    if result.returncode != 0:
        print(
            f"\nRUNTIME ERROR: {payload['filename']}, "
            f"{lang} block starting at line {block['line']}"
        )
        print(result.stderr.strip() or "The runtime exited with an error.")
        raise RuntimeError("Execution stopped due to a runtime error")

    lines = result.stdout.splitlines()

    marker_lines = [
        i for i, line in enumerate(lines)
        if line.startswith(MARKER)
    ]

    if not marker_lines:
        print(f"\nRUNTIME ERROR: {lang} did not return shared data.")
        raise RuntimeError("Runtime did not return shared data")

    marker_index = marker_lines[-1]

    try:
        shared = json.loads(
            lines[marker_index][len(MARKER):]
        )
    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"Invalid shared-data response from {lang}: {error}"
        ) from error

    for line in lines[:marker_index]:
        print(line)

    return shared

def main():
    if len(sys.argv) != 2:
        print("Usage: python polyglot.py demo.poly")
        return

    source_path = Path(sys.argv[1])
    source = source_path.read_text(encoding="utf-8")

    try:
        # Phase 1: Lex and parse the complete source file.
        parsed_blocks = parse_file(source)

        # Phase 2: Build AST and execution plan.
        program = build_ast(
            parsed_blocks,
            str(source_path),
        )

        plan = create_execution_plan(program)

        # Show compiler representations before execution.
        display_ast(program)
        display_execution_plan(plan)

        # Execute only after the entire plan is generated.
        shared = {}

        print("\n========== PROGRAM OUTPUT ==========")

        for step in plan:
            block = program.blocks[step.block_id - 1]

            print(
                f"\n[Step {step.step_id}] "
                f"Executing {step.language}"
            )

            runtime_block = {
                "language": block.language,
                "code": block.code,
                "line": block.start_line,
                "filename": program.source_name
            }

            shared = run_block(runtime_block, shared)

        print("\nFinal shared data:", shared)

        program = build_ast(
            parsed_blocks,
            str(source_path),
        )

        plan = create_execution_plan(program)
        report = analyze_data_flow(program)
        display_data_flow_report(report)

        # Stop before execution if data-flow errors exist.
        if report.issues:
            print("\nExecution cancelled due to data-flow errors.")
            return

        report = analyze_data_flow(program)
        display_data_flow_report(report)

        symbol_table = build_symbol_table(program, report)
        symbol_table.display()

        warnings = find_duplicate_definitions(symbol_table)

        if warnings:
            print("\n========== SEMANTIC WARNINGS ==========")
            for warning in warnings:
                print(warning)

        if report.issues:
            print("\nExecution cancelled due to data-flow errors.")
            return

        ir = lower_to_ir(program)

        display_ast(program)
        display_execution_plan(plan)
        ir.display()

        execute_ir(ir)
        
    except (
        PolyglotSyntaxError,
        ValueError,
        RuntimeError,
        subprocess.TimeoutExpired,
    ) as error:
        print("Polyglot error:", error)


if __name__ == "__main__":
    main()
