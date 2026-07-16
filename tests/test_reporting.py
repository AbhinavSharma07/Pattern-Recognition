"""Tests for agents.main's shared report-rendering logic, used by both the CLI and Gradio UI."""
from core.schemas import CodeSmell, RefactorProposal, TestCaseProposal, SyntaxIssue
from agents.main import (
    build_syntax_error_report,
    build_markdown_report,
    status_label,
    build_execution_trace,
    build_metrics_table,
)


def test_validated_result():
    assert "VALIDATED" in status_label({"validated": True})
    assert "PASSED" in status_label({"validated": True}).upper()


def test_sandbox_failure_says_tests_ran_and_failed():
    label = status_label({"validated": False, "stage": "sandbox", "error_kind": None})
    assert "VALIDATION FAILED" in label
    assert "ran and failed" in label


def test_reviewer_rejection_is_distinct_from_error():
    label = status_label({"validated": False, "stage": "review", "error_kind": None})
    assert "REJECTED BY REVIEWER" in label
    assert "ERROR" not in label


def test_api_error_during_refactor_is_distinct_from_generation_failure():
    label = status_label({"validated": False, "stage": "refactor", "error_kind": "api_error"})
    assert "API ERROR" in label
    assert "Refactor Generation" in label


def test_generation_error_does_not_say_api():
    label = status_label({"validated": False, "stage": "test_generation", "error_kind": "generation_error"})
    assert "FAILED" in label
    assert "Test Generation".upper() in label
    assert "API ERROR" not in label


def test_unknown_stage_falls_back_to_generic_skipped():
    label = status_label({"validated": False, "stage": None, "error_kind": None})
    assert "VALIDATION SKIPPED" in label


# --- build_execution_trace ---

def test_execution_trace_all_completed_when_validated():
    trace = build_execution_trace({"validated": True})
    assert "AST Analysis" in trace
    for stage_name in ("Refactor Agent", "Test Generator Agent", "Reviewer Agent", "Sandbox Validator"):
        assert f"✓ {stage_name}" in trace
    assert "✗" not in trace
    assert "Skipped" not in trace


def test_execution_trace_stops_at_refactor_failure():
    trace = build_execution_trace({"validated": False, "stage": "refactor", "error_kind": "api_error"})
    assert "✗ Refactor Agent" in trace
    # Everything after the failed stage must be explicitly marked Skipped, not
    # silently omitted or (worse) shown as if it ran.
    assert "— Test Generator Agent .......... Skipped" in trace
    assert "— Reviewer Agent .......... Skipped" in trace
    assert "— Sandbox Validator .......... Skipped" in trace


def test_execution_trace_shows_completed_stages_before_a_later_failure():
    trace = build_execution_trace({"validated": False, "stage": "sandbox", "error_kind": None})
    assert "✓ Refactor Agent .......... Completed" in trace
    assert "✓ Test Generator Agent .......... Completed" in trace
    assert "✓ Reviewer Agent .......... Completed" in trace
    assert "✗ Sandbox Validator" in trace


def test_execution_trace_review_rejection_vs_review_api_error():
    rejected = build_execution_trace({"validated": False, "stage": "review", "error_kind": None})
    assert "✗ Reviewer Agent .......... Rejected" in rejected

    api_error = build_execution_trace({"validated": False, "stage": "review", "error_kind": "api_error"})
    assert "✗ Reviewer Agent .......... Failed (API error)" in api_error


# --- build_metrics_table ---

SAMPLE_SMELL = CodeSmell(
    file_name="f.py", target_name="f", line_number=1,
    issue_type="Too Many Arguments", raw_code="def f(a, b, c, d, e, f):\n    pass\n",
)


def test_metrics_table_shows_before_only_when_not_validated():
    res = {
        "smells": [SAMPLE_SMELL],
        "source_code": SAMPLE_SMELL.raw_code,
        "refactor": RefactorProposal(original_function_name="f", explanation="x", refactored_code="def f(*a):\n    pass\n"),
        "validated": False,
        "config": {},
    }
    table = build_metrics_table(res)
    assert "refactor not validated" in table
    assert "Detected Smells" in table


def test_metrics_table_shows_real_before_after_when_validated():
    res = {
        "smells": [SAMPLE_SMELL],
        "source_code": SAMPLE_SMELL.raw_code,
        "refactor": RefactorProposal(
            original_function_name="f", explanation="x",
            refactored_code="def f(*args):\n    pass\n",
        ),
        "validated": True,
        "config": {},
    }
    table = build_metrics_table(res)
    assert "refactor not validated" not in table
    # Before: 6 args over the default threshold; after: *args collapses it to 0 named args.
    assert "| Max Arguments | 6 | 0 |" in table
    # The refactored code no longer has the smell, so Detected Smells should drop to 0.
    assert "| Detected Smells | 1 | 0 |" in table


def test_metrics_table_handles_unparseable_original_source():
    res = {"smells": [], "source_code": "def f(:\n", "refactor": None, "validated": False, "config": {}}
    table = build_metrics_table(res)
    assert "unavailable" in table.lower()


# --- Full refactored code section ---

def _make_result(validated: bool) -> dict:
    return {
        "smells": [SAMPLE_SMELL],
        "source_code": SAMPLE_SMELL.raw_code,
        "refactor": RefactorProposal(
            original_function_name="f", explanation="x", refactored_code="def f(*args):\n    pass\n",
        ),
        "test": TestCaseProposal(target_function_name="f", pytest_code="def test_f():\n    pass\n"),
        "validated": validated,
        "config": {},
    }


def test_report_includes_final_code_when_validated():
    report = build_markdown_report([_make_result(validated=True)])

    assert "Final Refactored Code" in report
    assert "def f(*args):\n    pass" in report


def test_report_labels_code_as_unvalidated_when_not_validated():
    report = build_markdown_report([_make_result(validated=False)])

    assert "Proposed Refactored Code" in report
    assert "unvalidated" in report.lower()
    assert "def f(*args):\n    pass" in report


# --- Validation caveat ---

def test_report_includes_validation_caveat_when_validated():
    report = build_markdown_report([_make_result(validated=True)])
    assert "Note on validation" in report


def test_report_omits_validation_caveat_when_not_validated():
    """No point caveating a claim ('VALIDATED') that isn't even being made."""
    report = build_markdown_report([_make_result(validated=False)])
    assert "Note on validation" not in report


# --- build_syntax_error_report ---

def test_syntax_error_report_includes_line_column_and_message():
    issue = SyntaxIssue(line_number=3, column_number=7, message="invalid syntax")
    report = build_syntax_error_report(issue)

    assert "Syntax Analysis" in report
    assert "Failed" in report
    assert "3" in report
    assert "7" in report
    assert "invalid syntax" in report
    assert "cannot continue" in report.lower()
