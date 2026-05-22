import typer
from pathlib import Path
from core.parser import analyze_source_code
from agents.orchestrator import process_codebase
from dotenv import load_dotenv

# Load environment variables (.env) for the API key
load_dotenv()

app = typer.Typer(help="Multi-Agent AST Pattern Analyzer & Auto-Refactorer")

@app.command()
def scan(file_path: Path = typer.Argument(..., help="Path to the Python file to scan")):
    """Scans a Python file for architectural anti-patterns without modifying it."""
    if not file_path.exists() or not file_path.is_file():
        typer.secho(f"Error: File '{file_path}' does not exist.", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    
    source_code = file_path.read_text(encoding="utf-8")
    smells = analyze_source_code(source_code, file_path.name)
    
    if not smells:
        typer.secho("✅ No code smells detected. Code is clean!", fg=typer.colors.GREEN)
        return

    typer.secho(f"⚠️ Found {len(smells)} code smell(s):", fg=typer.colors.YELLOW)
    for i, smell in enumerate(smells, 1):
        typer.echo(f"  {i}. {smell.target_name} (Line {smell.line_number}): {smell.issue_type}")

@app.command()
def fix(
    file_path: Path = typer.Argument(..., help="Path to the Python file to fix"),
    report: bool = typer.Option(False, "--report", help="Generate a Markdown report of the changes"),
    apply: bool = typer.Option(False, "--apply", help="Overwrite the original file with the validated refactors")
):
    """Autonomously refactors code smells and validates with generated tests."""
    if not file_path.exists() or not file_path.is_file():
        typer.secho(f"Error: File '{file_path}' does not exist.", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    
    source_code = file_path.read_text(encoding="utf-8")
    typer.secho(f"🚀 Starting multi-agent refactoring on {file_path.name}...\n", fg=typer.colors.CYAN)
    
    results = process_codebase(source_code, file_path.name)
    
    if results and report:
        report_path = file_path.with_name(f"{file_path.stem}_refactor_report.md")
        generate_markdown_report(results, report_path)
        typer.secho(f"\n📄 Markdown report generated and saved to: {report_path}", fg=typer.colors.GREEN)

    if apply and results:
        new_source = source_code
        changes_applied = 0
        for res in results:
            if res.get("validated", False):
                smell = res["smell"]
                refactor = res["refactor"]
                if smell.raw_code in new_source:
                    new_source = new_source.replace(smell.raw_code, refactor.refactored_code)
                    changes_applied += 1
        
        if changes_applied > 0:
            file_path.write_text(new_source, encoding="utf-8")
            typer.secho(f"\n✅ Successfully applied {changes_applied} validated fix(es) directly to {file_path.name}!", fg=typer.colors.GREEN)

def generate_markdown_report(results: list, output_path: Path):
    """Generates a comprehensive Markdown report of the AI's actions."""
    lines = [f"# Refactoring Report\n"]
    for res in results:
        smell, refactor, test, validated = res["smell"], res["refactor"], res["test"], res.get("validated", False)
        status = "✅ VALIDATED" if validated else "❌ FAILED TESTS"
        
        lines.extend([
            f"## Target: `{smell.target_name}` ({status})",
            f"**Issue Detected:** {smell.issue_type}\n\n### Explanation\n{refactor.explanation}\n",
            f"### Original Code\n```python\n{smell.raw_code}\n```\n",
            f"### Refactored Code\n```python\n{refactor.refactored_code}\n```\n",
            f"### Generated Test\n```python\n{test.pytest_code}\n```\n---\n"
        ])
    output_path.write_text("\n".join(lines), encoding="utf-8")

if __name__ == "__main__":
    app()