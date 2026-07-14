import ast

from core.schemas import CodeSmell, RefactorProposal
from agents.main import apply_validated_fixes


def _result(source, refactored_code, validated=True):
    return {
        "smells": [CodeSmell(file_name="f.py", target_name="f", line_number=1, issue_type="x", raw_code=source)],
        "refactor": RefactorProposal(
            original_function_name="f.py",
            explanation="...",
            refactored_code=refactored_code,
        ),
        "test": None,
        "validated": validated,
    }


def test_applies_validated_unified_refactor():
    """Applying a validated refactor uses refactored_code as the new whole-file content."""
    source = "def f(a, b):\n    return a + b\n"
    refactored = "def f(*args):\n    return sum(args)\n"
    results = [_result(source, refactored)]

    new_source, count = apply_validated_fixes(source, results)

    assert count == 1
    assert new_source == refactored
    ast.parse(new_source)  # must be valid Python


def test_skips_unvalidated_fix():
    source = "def f(a, b):\n    return a + b\n"
    results = [_result(source, "def f(*args):\n    return sum(args)\n", validated=False)]

    new_source, count = apply_validated_fixes(source, results)

    assert count == 0
    assert new_source == source


def test_no_results_leaves_source_unchanged():
    source = "def f(a, b):\n    return a + b\n"

    new_source, count = apply_validated_fixes(source, [])

    assert count == 0
    assert new_source == source


def test_multi_statement_refactor_applies_cleanly():
    """Multiple top-level statements in the refactor are just part of the whole-file replacement."""
    source = "def f(a, b):\n    return a + b\n"
    refactored = (
        "def _helper(a, b):\n"
        "    return a + b\n\n\n"
        "def f(a, b):\n"
        "    return _helper(a, b)\n"
    )
    results = [_result(source, refactored)]

    new_source, count = apply_validated_fixes(source, results)

    assert count == 1
    assert new_source == refactored
    ast.parse(new_source)
