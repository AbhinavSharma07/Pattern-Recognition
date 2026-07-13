import logging
import sys
import typer
import difflib
from pathlib import Path
from typing import Dict, List
from core.parser import analyze_source_code, load_config
from agents.orchestrator import process_codebase
from dotenv import load_dotenv

try:
    import libcst as cst
    HAS_LIBCST = True
except ImportError:
    HAS_LIBCST = False

# Windows consoles often default to a legacy codepage (e.g. cp1252) that can't
# encode the emoji used in this CLI's output, crashing with UnicodeEncodeError.
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class RefactorTransformer(cst.CSTTransformer):
    """Safely replaces AST nodes with AI-refactored code while preserving formatting."""
    def __init__(self, target_name: str, new_code: str):
        self.target_name = target_name
        try:
            self.replacement_node = cst.parse_statement(new_code)
        except Exception as e:
            logging.warning(f"Failed to parse refactored code with libcst: {e}. Will use fallback.", exc_info=True)
            self.replacement_node = None

    def leave_FunctionDef(self, original_node, updated_node):
        if original_node.name.value == self.target_name and self.replacement_node:
            return self.replacement_node
        return updated_node

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
            new_source = source_code
            changes_applied = 0
            new_imports = set()

            for res in results:
                if res.get("validated", False):
                    smell = res["smell"]
                    refactor = res["refactor"]
                    
                    if HAS_LIBCST:
                        try:
                            module = cst.parse_module(new_source)
                            transformer = RefactorTransformer(smell.target_name, refactor.refactored_code)
                            modified_module = module.visit(transformer)
                            
                            if not module.deep_equals(modified_module):
                                new_source = modified_module.code
                                changes_applied += 1
                            elif smell.raw_code in new_source: # Fallback
                                new_source = new_source.replace(smell.raw_code, refactor.refactored_code)
                                changes_applied += 1
                        except Exception as e:
                            logging.warning(f"LibCST transformation failed for {smell.target_name}: {e}", exc_info=True)
                            pass # Let fallback catch it below
                    elif smell.raw_code in new_source:
                        new_source = new_source.replace(smell.raw_code, refactor.refactored_code)
                        changes_applied += 1
                        
                        for imp in refactor.required_imports:
                            if imp not in new_source:
                                new_imports.add(imp)
            
            if changes_applied > 0:
                if new_imports:
                    new_source = "\n".join(new_imports) + "\n\n" + new_source
                file_path.write_text(new_source, encoding="utf-8")
                typer.secho(f"✅ Successfully applied {changes_applied} validated fix(es) directly to {file_path.name}!", fg=typer.colors.GREEN)

def _render_result_section(res: dict) -> str:
    """Renders a single smell/refactor/test result as a Markdown section."""
    smell, refactor, test, validated = res["smell"], res["refactor"], res["test"], res.get("validated", False)
    status = "✅ VALIDATED" if validated else "❌ FAILED TESTS"

    diff = difflib.unified_diff(
        smell.raw_code.splitlines(keepends=True),
        refactor.refactored_code.splitlines(keepends=True),
        fromfile='original', tofile='refactored',
    )

    return "\n".join([
        f"## Target: `{smell.target_name}` ({status})",
        f"**Issue Detected:** {smell.issue_type}\n\n### Explanation\n{refactor.explanation}\n",
        f"### Code Diff\n```diff\n{''.join(diff)}\n```\n",
        f"### Generated Test\n```python\n{test.pytest_code}\n```\n---\n",
    ])


def build_markdown_report(results: list) -> str:
    """Builds a Markdown report string for a single file's worth of results."""
    lines = ["# Refactoring Report\n"]
    lines.extend(_render_result_section(res) for res in results)
    return "\n".join(lines)


def build_combined_markdown_report(results_by_file: Dict[str, list]) -> str:
    """Builds one combined Markdown report covering multiple files' results (used by the Streamlit UI)."""
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