"""Tests for agents.main.status_label, the shared status-rendering logic used by
both the CLI Markdown report and the Gradio UI."""
from agents.main import status_label


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
