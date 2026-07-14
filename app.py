import difflib
import json
import os
from pathlib import Path

import gradio as gr

try:
    import spaces
except ImportError:
    spaces = None

from core.parser import load_config
from core.severity import get_severity
from agents.orchestrator import process_codebase
from agents.main import build_combined_markdown_report, build_execution_trace, build_metrics_table, status_label
from dotenv import load_dotenv

load_dotenv()

REPORT_PATH = Path("refactor_report.md")


def _running_on_hf_space() -> bool:
    """True on a public HF Space (SPACE_ID set) -- disables Docker sandbox and shared config writes."""
    return bool(os.environ.get("SPACE_ID"))


if spaces is not None:
    @spaces.GPU
    def _zerogpu_startup_check():
        """Never called -- exists only because ZeroGPU refuses to start a Space with no @spaces.GPU function."""
        return None


def _render_result(res: dict) -> str:
    smells, refactor, test = res["smells"], res["refactor"], res["test"]
    original_source = res.get("source_code", "")
    status = status_label(res)

    issues_list = "\n".join(
        f"- **{s.issue_type}** [{get_severity(s.issue_type)}] in `{s.target_name}` (line {s.line_number})\n"
        f"  - {s.reason}"
        for s in smells
    )

    diff = difflib.unified_diff(
        original_source.splitlines(keepends=True),
        refactor.refactored_code.splitlines(keepends=True),
        fromfile='original', tofile='refactored',
    )

    return "\n".join([
        f"### Unified Refactor — {len(smells)} issue(s) addressed",
        f"**Validation Status:** {status}\n",
        f"**Agent Execution**\n```\n{build_execution_trace(res)}\n```\n",
        f"**Issues Addressed:**\n{issues_list}\n",
        f"**AST Metrics**\n{build_metrics_table(res)}\n",
        f"**AI Explanation:** {refactor.explanation}\n",
        "**Code Diff**",
        f"```diff\n{''.join(diff)}\n```",
        "**Generated Pytest Validation**",
        f"```python\n{test.pytest_code}\n```",
        "---",
    ])


def run_analysis(code_input: str, uploaded_files, use_docker: bool, config_text: str, request: gr.Request = None):
    """
    Runs the multi-agent pipeline over the pasted snippet and/or uploaded files.
    Returns (status_markdown, report_file_path_or_None).
    """
    try:
        config = json.loads(config_text)
    except json.JSONDecodeError as e:
        return f"⚠️ **Invalid configuration JSON, not run:** {e}", None

    files_to_process = []
    if code_input and code_input.strip():
        files_to_process.append(("pasted_code.py", code_input))
    for file_path in uploaded_files or []:
        path = Path(file_path)
        files_to_process.append((path.name, path.read_text(encoding="utf-8")))

    if not files_to_process:
        return "⚠️ Please paste some code or upload at least one `.py` file.", None

    # No Docker daemon inside a Space container.
    if _running_on_hf_space():
        use_docker = False

    # Scope the cache per browser session so results aren't shared across visitors.
    cache_namespace = request.session_hash if request is not None else None

    results_by_file = {
        file_name: process_codebase(source, file_name, use_docker, config, cache_namespace=cache_namespace)
        for file_name, source in files_to_process
    }

    total_smells = sum(len(r["smells"]) for results in results_by_file.values() for r in results)
    if total_smells == 0:
        return "✅ No structural code smells detected across all file(s). Your code is clean!", None

    lines = [f"### 🔍 Found and processed {total_smells} code smell(s) across {len(files_to_process)} file(s)\n"]
    for file_name, results in results_by_file.items():
        if not results:
            continue
        lines.append(f"## 📄 `{file_name}`\n")
        lines.extend(_render_result(res) for res in results)

    non_empty_results = {name: results for name, results in results_by_file.items() if results}
    REPORT_PATH.write_text(build_combined_markdown_report(non_empty_results), encoding="utf-8")

    return "\n".join(lines), str(REPORT_PATH)


def save_config(config_text: str):
    try:
        json.loads(config_text)  # validate only; parsed value isn't needed further here
    except json.JSONDecodeError as e:
        return f"⚠️ Invalid JSON, not saved: {e}"

    if _running_on_hf_space():
        # config.json is shared filesystem state on a Space -- writing it would leak to every visitor.
        return "ℹ️ Changes apply to your session's analysis runs. Saving to disk is disabled on this public demo."

    config = json.loads(config_text)
    Path("config.json").write_text(json.dumps(config, indent=4), encoding="utf-8")
    return "✅ Configuration saved!"


with gr.Blocks(title="AST Refactor Bot") as demo:
    gr.Markdown("# 🤖 Multi-Agent AST Auto-Refactorer")
    gr.Markdown(
        "Paste a Python snippet below, or upload one or more `.py` files, "
        "to have the AI agents analyze, refactor, and validate them."
    )

    with gr.Row():
        with gr.Column(scale=1):
            gr.Markdown("### ⚙️ Configuration")
            use_docker = gr.Checkbox(
                label="Use Docker Sandbox",
                value=False,
                info="Requires Docker to be available in this environment.",
                visible=not _running_on_hf_space(),
            )
            with gr.Accordion("Edit Configuration JSON", open=False):
                config_box = gr.Code(
                    value=json.dumps(load_config("config.json"), indent=4),
                    language="json",
                    label="Configuration (JSON)",
                )
                save_btn = gr.Button("Save Config to File")
                save_status = gr.Markdown()

        with gr.Column(scale=2):
            code_input = gr.Code(value="", label="Paste Python Code Here", language="python", lines=12)
            uploaded_files = gr.File(
                label="Or upload one or more .py files",
                file_count="multiple",
                file_types=[".py"],
            )
            analyze_btn = gr.Button("🚀 Analyze & Refactor", variant="primary")

    output_md = gr.Markdown()
    report_file = gr.File(label="📄 Download Markdown Report")

    save_btn.click(fn=save_config, inputs=[config_box], outputs=[save_status])
    analyze_btn.click(
        fn=run_analysis,
        inputs=[code_input, uploaded_files, use_docker, config_box],
        outputs=[output_md, report_file],
    )

if __name__ == "__main__":
    demo.launch()
