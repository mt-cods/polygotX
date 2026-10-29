
import contextlib
import io
import streamlit as st

from polyglot import (
    parse_file,
    build_ast,
    create_execution_plan,
    analyze_data_flow,
    display_data_flow_report,
    build_symbol_table,
    find_duplicate_definitions,
    lower_to_ir,
    execute_ir,
)

st.set_page_config(
    page_title="PolyglotX Compiler Studio",
    page_icon="🔀",
    layout="wide",
)

st.title(" PolyglotX Compiler Studio")
st.caption(
    "A multi-language compiler prototype for Python and JavaScript"
)

DEFAULT_SOURCE = '''[python]
marks = [80, 90, 85]
average = sum(marks) / len(marks)
export("average", average)
print("Average:", average)
[/python]

[javascript]
const avg = shared.average;
const grade = avg >= 85 ? "A" : "B";
console.log("Grade:", grade);
[/javascript]
'''

if "poly_source" not in st.session_state:
    st.session_state.poly_source = DEFAULT_SOURCE

source = st.text_area(
    "Polyglot source (.poly)",
    key="poly_source",
    height=300,
)

analyze_button = st.button(
    "Analyze and Compile",
    type="primary",
)

if analyze_button:
    try:
        # Stage 1: Parse source
        parsed_blocks = parse_file(source)

        # Stage 2: Construct AST and execution plan
        program = build_ast(parsed_blocks, "editor.poly")
        plan = create_execution_plan(program)

        # Stage 3: Static data-flow analysis
        report = analyze_data_flow(program)

        # Stage 4: Symbol table
        symbol_table = build_symbol_table(program, report)
        warnings = find_duplicate_definitions(symbol_table)

        # Stage 5: Intermediate representation
        ir = lower_to_ir(program)

        tab_ast, tab_ir, tab_flow, tab_output = st.tabs(
            ["AST / Plan", "Intermediate Representation",
             "Data Flow", "Execution Output"]
        )

        with tab_ast:
            st.subheader("Abstract Syntax Tree")
            st.json({
                "source": program.source_name,
                "blocks": [
                    {
                        "block_id": block.block_id,
                        "language": block.language,
                        "start_line": block.start_line,
                        "end_line": block.end_line,
                        "code": block.code,
                    }
                    for block in program.blocks
                ],
            })

            st.subheader("Execution Plan")
            st.dataframe([
                {
                    "Step": step.step_id,
                    "Block": step.block_id,
                    "Language": step.language,
                    "Runtime": step.runtime,
                    "Start line": step.start_line,
                    "End line": step.end_line,
                }
                for step in plan
            ], use_container_width=True)

        with tab_ir:
            st.subheader("Intermediate Representation")
            st.dataframe([
                {
                    "Instruction": item.instruction_id,
                    "Opcode": item.opcode,
                    "Block": item.block_id,
                    "Language": item.language,
                    "Source line": item.source_line,
                    "Runtime": item.operands.get("runtime"),
                }
                for item in ir.instructions
            ], use_container_width=True)

        with tab_flow:
            st.subheader("Data-Flow Analysis")

            if report.issues:
                for issue in report.issues:
                    st.error(
                        f"{issue.message} "
                        f"Block {issue.block_id}, line {issue.line}"
                    )
            else:
                st.success("No missing shared variables detected.")

            st.subheader("Shared Symbols")
            st.json(report.definitions)

            st.subheader("Dependencies")
            if report.dependencies:
                st.dataframe(
                    report.dependencies,
                    use_container_width=True,
                )
            else:
                st.info("No shared-variable dependencies found.")

            if warnings:
                st.subheader("Semantic Warnings")
                for warning in warnings:
                    st.warning(warning)

        with tab_output:
            st.subheader("Program Execution")

            if report.issues:
                st.error(
                    "Execution cancelled because static analysis "
                    "reported errors."
                )
            else:
                output_buffer = io.StringIO()

                with contextlib.redirect_stdout(output_buffer):
                    execute_ir(ir)

                st.code(
                    output_buffer.getvalue() or "(No output)",
                    language="text",
                )

    except Exception as error:
        st.error(f"Compiler error: {error}")
