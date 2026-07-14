import ast
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
    """
    Replaces a target function's body with AI-refactored code while preserving
    formatting elsewhere in the file. Only matches smells whose target IS the
    containing function (e.g. Too Many Arguments, Excessive Nesting Depth) --
    it can't target a sub-expression inside a function (a call, an except
    clause, a comprehension), since those smells' target_name isn't a function
    name; those are left for the caller's string-replace fallback.
    """
    def __init__(self, target_name: str, new_code: str):
        self.target_name = target_name
        self.applied = False
        try:
            # A refactor commonly introduces a helper function alongside the
            # fix, i.e. more than one top-level statement -- parse_module (not
            # parse_statement, which only accepts exactly one statement) so
            # multi-statement replacements don't fail to parse here.
            self.replacement_statements = list(cst.parse_module(new_code).body)
        except Exception as e:
            logging.warning(f"Failed to parse refactored code with libcst: {e}. Will use fallback.", exc_info=True)
            self.replacement_statements = None

    def leave_FunctionDef(self, original_node, updated_node):
        if (
            not self.applied
            and self.replacement_statements
            and original_node.name.value == self.target_name
        ):
            self.applied = True
            if len(self.replacement_statements) == 1:
                return self.replacement_statements[0]
            return cst.FlattenSentinel(self.replacement_statements)
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
            new_source, changes_applied = apply_validated_fixes(source_code, results)

            if changes_applied > 0:
                file_path.write_text(new_source, encoding="utf-8")
                typer.secho(f"✅ Successfully applied {changes_applied} validated fix(es) directly to {file_path.name}!", fg=typer.colors.GREEN)
            elif any(res.get("validated", False) for res in results):
                typer.secho(
                    "⚠️ Validated fixes were found, but none could be safely applied "
                    "(see warnings above -- they likely overlap with each other).",
                    fg=typer.colors.YELLOW,
                )

def apply_validated_fixes(source_code: str, results: list) -> tuple:
    """
    Applies every validated fix in `results` to `source_code`, one at a time.

    Two validated fixes can overlap (e.g. a whole-function rewrite for
    "Excessive Nesting Depth" and a fix for one call inside that same
    function) -- applying both via naive string-replacement can silently
    produce syntactically invalid Python. To guard against that, each
    candidate result is verified with ast.parse before being kept; a fix that
    would break the file is skipped (and logged) rather than written.

    Returns (new_source, count_of_fixes_actually_applied).
    """
    new_source = source_code
    changes_applied = 0
    new_imports = set()

    for res in results:
        if not res.get("validated", False):
            continue

        smell = res["smell"]
        refactor = res["refactor"]
        candidate_source = None

        if HAS_LIBCST:
            try:
                module = cst.parse_module(new_source)
                transformer = RefactorTransformer(smell.target_name, refactor.refactored_code)
                modified_module = module.visit(transformer)
                if not module.deep_equals(modified_module):
                    candidate_source = modified_module.code
            except Exception as e:
                logging.warning(f"LibCST transformation failed for {smell.target_name}: {e}", exc_info=True)

        # Fallback: either libcst isn't available, the target isn't a function
        # (e.g. a call/except/comprehension smell -- RefactorTransformer can only
        # match function-level targets), or the libcst parse/transform failed.
        if candidate_source is None and smell.raw_code in new_source:
            candidate_source = new_source.replace(smell.raw_code, refactor.refactored_code)

        if candidate_source is None:
            continue

        try:
            ast.parse(candidate_source)
        except SyntaxError as e:
            logging.warning(
                f"Skipping fix for '{smell.target_name}': applying it would leave the file with "
                f"invalid Python ({e}). It likely overlaps with another already-applied fix."
            )
            continue

        new_source = candidate_source
        changes_applied += 1
        for imp in refactor.required_imports:
            if imp not in new_source:
                new_imports.add(imp)

    if new_imports:
        new_source = "\n".join(sorted(new_imports)) + "\n\n" + new_source

    return new_source, changes_applied

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
    """Renders a single smell/refactor/test result as a Markdown section."""
    smell, refactor, test = res["smell"], res["refactor"], res["test"]
    status = status_label(res)

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