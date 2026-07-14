import logging
import sys
import typer
import difflib
from pathlib import Path
from typing import Dict, List
from core.parser import analyze_source_code, load_config
from agents.orchestrator import process_codebase
from dotenv import load_dotenv

# Windows consoles often default to a legacy codepage (e.g. cp1252) that can't
# encode the emoji used in this CLI's output, crashing with UnicodeEncodeError.
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Load environment variables (.env) for the API key
load_dotenv()

app = typer.Typer(help="Multi-Agent AST Pattern Analyzer & Auto-Refactorer")

def _get_python_files(path: Path) -> List[Path]:
    """Gathers all Python files from a path, excluding common virtual environments and hidden directories."""
    if path.is_file():
        return [path]
    
    typer.echo(f"Searching for Python files in {path}...")
    return [
        p for p in path.rglob("*.py")
        if not any(part.startswith('.') or part in ('venv', '.venv', '__pycache__') for part in p.parts)
    ]


@app.command()
def scan(
    path: Path = typer.Argument(..., help="Path to the Python file or directory to scan"),
    config: Path = typer.Option("config.json", "--config", "-c", help="Path to a custom JSON configuration file")
):
    """Scans Python file(s) for architectural anti-patterns without modifying them."""
    if not path.exists():
        typer.secho(f"Error: Path '{path}' does not exist.", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    
    custom_config = load_config(str(config))
    files_to_scan = _get_python_files(path)
    total_smells = 0

    for file_path in files_to_scan:
        source_code = file_path.read_text(encoding="utf-8")
        smells = analyze_source_code(source_code, str(file_path), custom_config)
        
        if smells:
            total_smells += len(smells)
            typer.secho(f"\n⚠️ Found {len(smells)} code smell(s) in {file_path}:", fg=typer.colors.YELLOW)
            for i, smell in enumerate(smells, 1):
                typer.echo(f"  {i}. {smell.target_name} (Line {smell.line_number}): {smell.issue_type}")

    if total_smells == 0:
        typer.secho("✅ No code smells detected. Code is clean!", fg=typer.colors.GREEN)

@app.command()
def fix(
    path: Path = typer.Argument(..., help="Path to the Python file or directory to fix"),
    report: bool = typer.Option(False, "--report", help="Generate a Markdown report of the changes"),
    apply: bool = typer.Option(False, "--apply", help="Overwrite the original file with the validated refactors"),
    docker: bool = typer.Option(False, "--docker", help="Run validation tests securely inside a Docker container"),
    config: Path = typer.Option("config.json", "--config", "-c", help="Path to a custom JSON configuration file")
):
    """Autonomously refactors code smells in file(s) and validates with generated tests."""
    if not path.exists():
        typer.secho(f"Error: Path '{path}' does not exist.", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    
    custom_config = load_config(str(config))
    files_to_fix = _get_python_files(path)
    
    for file_path in files_to_fix:
        source_code = file_path.read_text(encoding="utf-8")
        typer.secho(f"\n🚀 Starting multi-agent refactoring on {file_path}...\n", fg=typer.colors.CYAN)
        
        results = process_codebase(source_code, file_path.name, use_docker=docker, config=custom_config)
        
        if results and report:
            report_path = file_path.with_name(f"{file_path.stem}_refactor_report.md")
            generate_markdown_report(results, report_path)
            typer.secho(f"\n📄 Markdown report generated and saved to: {report_path}", fg=typer.colors.GREEN)

        if apply and results:
            new_source, changes_applied = apply_validated_fixes(source_code, results)

            if changes_applied > 0:
                file_path.write_text(new_source, encoding="utf-8")
                typer.secho(f"✅ Successfully applied the validated unified refactor to {file_path.name}!", fg=typer.colors.GREEN)
            else:
                typer.secho(
                    f"⚠️ No validated refactor to apply for {file_path.name} (see the status above).",
                    fg=typer.colors.YELLOW,
                )

def apply_validated_fixes(source_code: str, results: list) -> tuple:
    """
    Applies the validated result (if any) to source_code.

    Each file now gets exactly one unified refactor addressing every smell
    detected in it at once, so "applying" a validated result is just using
    its refactored_code as the new whole-file content directly -- there's no
    more per-smell patching, and therefore no more risk of two separate
    fixes overlapping and corrupting the file (a real bug the old per-smell
    approach had).

    `results` is expected to have zero or one entries (process_codebase
    returns one consolidated result per file); only the first validated one
    is used, since there is only ever one.

    Returns (new_source, count_of_fixes_actually_applied) -- count is 0 or 1,
    kept as a count rather than a bool for backward-compatible call sites.
    """
    for res in results:
        if res.get("validated", False):
            return res["refactor"].refactored_code, 1
    return source_code, 0

_STAGE_LABELS = {
    "refactor": "Refactor Generation",
    "test_generation": "Test Generation",
    "review": "Code Review",
    "sandbox": "Sandbox Validation",
}


def status_label(res: dict) -> str:
    """
    Renders a precise status for a single result, distinguishing:
    - VALIDATED: sandbox tests actually ran and passed.
    - VALIDATION FAILED: sandbox tests actually ran and failed.
    - REJECTED BY REVIEWER: the reviewer declined it; never reached the sandbox.
    - API ERROR during <stage>: a provider/transport error (rate limit, timeout,
      connection error, ...) -- the model/pipeline never got a real chance.
    - <STAGE> FAILED: the model produced unusable output at that stage (e.g. bad
      structured output) -- distinct from an API error, and distinct from a test
      that actually ran and failed.
    """
    if res.get("validated", False):
        return "✅ VALIDATED (sandbox tests passed)"

    stage = res.get("stage")
    error_kind = res.get("error_kind")

    if stage == "sandbox":
        return "❌ VALIDATION FAILED (generated tests ran and failed)"
    if stage == "review" and error_kind is None:
        return "⚠️ REJECTED BY REVIEWER (never reached sandbox validation)"
    if error_kind == "api_error":
        return f"🔌 API ERROR during {_STAGE_LABELS.get(stage, 'processing')} (validation skipped)"
    if stage in _STAGE_LABELS:
        return f"⚠️ {_STAGE_LABELS[stage].upper()} FAILED (validation skipped)"
    return "❌ VALIDATION SKIPPED (pipeline did not complete)"


def _render_result_section(res: dict) -> str:
    """Renders a file-level unified-refactor result (addressing every smell
    found in that file at once) as a Markdown section."""
    smells, refactor, test = res["smells"], res["refactor"], res["test"]
    original_source = res.get("source_code", "")
    status = status_label(res)

    issues_list = "\n".join(
        f"- **{s.issue_type}** in `{s.target_name}` (line {s.line_number})" for s in smells
    )

    diff = difflib.unified_diff(
        original_source.splitlines(keepends=True),
        refactor.refactored_code.splitlines(keepends=True),
        fromfile='original', tofile='refactored',
    )

    return "\n".join([
        f"## Unified Refactor ({status})",
        f"**Issues Addressed ({len(smells)}):**\n{issues_list}\n",
        f"### Explanation\n{refactor.explanation}\n",
        f"### Code Diff\n```diff\n{''.join(diff)}\n```\n",
        f"### Generated Test\n```python\n{test.pytest_code}\n```\n---\n",
    ])


def build_markdown_report(results: list) -> str:
    """Builds a Markdown report string for a single file's worth of results."""
    lines = ["# Refactoring Report\n"]
    lines.extend(_render_result_section(res) for res in results)
    return "\n".join(lines)


def build_combined_markdown_report(results_by_file: Dict[str, list]) -> str:
    """Builds one combined Markdown report covering multiple files' results (used by the Gradio UI)."""
    lines = ["# Refactoring Report\n"]
    for file_name, results in results_by_file.items():
        lines.append(f"# File: `{file_name}`\n")
        lines.extend(_render_result_section(res) for res in results)
    return "\n".join(lines)


def generate_markdown_report(results: list, output_path: Path):
    """Generates a comprehensive Markdown report of the AI's actions and writes it to disk."""
    output_path.write_text(build_markdown_report(results), encoding="utf-8")

if __name__ == "__main__":
    app()