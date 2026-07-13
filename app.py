import streamlit as st
import json
from core.parser import load_config
from agents.orchestrator import process_codebase
from dotenv import load_dotenv

# Load environment variables (.env) for the API key
load_dotenv()

st.set_page_config(page_title="AST Refactor Bot", page_icon="🤖", layout="wide")

st.title("🤖 Multi-Agent AST Auto-Refactorer")
st.markdown("Paste your Python code below or upload a file to have the AI agents analyze, refactor, and validate it.")

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

code_input = st.text_area("Paste Python Code Here:", height=300)
uploaded_file = st.file_uploader("Or Upload a .py file", type=["py"])

if uploaded_file:
    code_input = uploaded_file.getvalue().decode("utf-8")
    st.text_area("Uploaded Code:", value=code_input, height=300, disabled=True)

if st.button("🚀 Analyze & Refactor", type="primary"):
    if not code_input.strip():
        st.warning("Please provide some code to analyze.")
    else:
        with st.spinner("Agents are scanning and processing the codebase..."):
            # Run the multi-agent pipeline
            results = process_codebase(code_input, "streamlit_input.py", use_docker, st.session_state.config)

            if not results:
                st.success("✅ No structural code smells detected. Your code is clean!")
            else:
                st.success(f"🔍 Successfully processed {len(results)} code smell(s)!")
                
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