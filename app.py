import streamlit as st
import json
from core.parser import load_config
from agents.orchestrator import process_codebase
from agents.main import build_combined_markdown_report
from dotenv import load_dotenv

# Load environment variables (.env) for the API key
load_dotenv()

st.set_page_config(page_title="AST Refactor Bot", page_icon="🤖", layout="wide")

st.title("🤖 Multi-Agent AST Auto-Refactorer")
st.markdown(
    "Paste a Python snippet below, or upload one or more `.py` files (multi-select), "
    "to have the AI agents analyze, refactor, and validate them."
)

# Sidebar settings
st.sidebar.header("⚙️ Configuration")

# Load config into session state if not already there
if 'config' not in st.session_state:
    st.session_state.config = load_config("config.json")

use_docker = st.sidebar.checkbox("Use Docker Sandbox", value=st.session_state.config.get("use_docker", False), help="Requires Docker Desktop to be running.")

# Interactive JSON editor for the config (Streamlit has no built-in JSON editor
# widget, so we edit the raw text and validate/parse it on save).
with st.sidebar.expander("Edit Configuration JSON", expanded=False):
    config_text = st.text_area(
        "Configuration (JSON)",
        value=json.dumps(st.session_state.config, indent=4),
        height=300,
    )
    if st.button("Save Config to File"):
        try:
            st.session_state.config = json.loads(config_text)
            with open("config.json", "w", encoding="utf-8") as f:
                json.dump(st.session_state.config, f, indent=4)
            st.success("Configuration saved!")
        except json.JSONDecodeError as e:
            st.error(f"Invalid JSON, not saved: {e}")

code_input = st.text_area("Paste Python Code Here:", height=250)
uploaded_files = st.file_uploader(
    "Or upload one or more .py files",
    type=["py"],
    accept_multiple_files=True,
    help="Select multiple files at once from your OS file picker to process a whole batch in one run.",
)

if st.button("🚀 Analyze & Refactor", type="primary"):
    files_to_process = []
    if code_input.strip():
        files_to_process.append(("pasted_code.py", code_input))
    for uploaded_file in uploaded_files:
        files_to_process.append((uploaded_file.name, uploaded_file.getvalue().decode("utf-8")))

    if not files_to_process:
        st.warning("Please paste some code or upload at least one .py file.")
    else:
        results_by_file = {}
        with st.spinner(f"Agents are scanning and processing {len(files_to_process)} file(s)..."):
            for file_name, source in files_to_process:
                results_by_file[file_name] = process_codebase(
                    source, file_name, use_docker, st.session_state.config
                )

        total_smells = sum(len(r) for r in results_by_file.values())

        if total_smells == 0:
            st.success("✅ No structural code smells detected across all file(s). Your code is clean!")
        else:
            st.success(f"🔍 Found and processed {total_smells} code smell(s) across {len(files_to_process)} file(s)!")

            report_md = build_combined_markdown_report(
                {name: results for name, results in results_by_file.items() if results}
            )
            st.download_button(
                "📄 Download Markdown Report",
                data=report_md,
                file_name="refactor_report.md",
                mime="text/markdown",
            )

            for file_name, results in results_by_file.items():
                if not results:
                    continue

                st.markdown(f"### 📄 `{file_name}`")
                for i, res in enumerate(results, 1):
                    smell = res["smell"]
                    refactor = res["refactor"]
                    test = res["test"]
                    validated = res.get("validated", False)

                    with st.expander(f"Issue {i}: {smell.issue_type} in `{smell.target_name}`", expanded=True):
                        if validated:
                            st.success("Validation Status: ✅ PASSED SANDBOX TESTS (Safe to apply)")
                        else:
                            st.error("Validation Status: ❌ FAILED SANDBOX TESTS (Refactor introduced errors)")

                        col1, col2 = st.columns(2)

                        with col1:
                            st.subheader("Original Code")
                            st.code(smell.raw_code, language="python")
                            st.markdown(f"**AI Explanation:** {refactor.explanation}")

                        with col2:
                            st.subheader("Refactored Code")
                            st.code(refactor.refactored_code, language="python")

                        st.subheader("Generated Pytest Validations")
                        st.code(test.pytest_code, language="python")