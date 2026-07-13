import json

from core.schemas import RefactorProposal, TestCaseProposal
import app

SAMPLE_RESULT = {
    "smell": None,
    "refactor": RefactorProposal(
        original_function_name="f", explanation="Bundled args.", refactored_code="def f(*args):\n    pass\n"
    ),
    "test": TestCaseProposal(target_function_name="f", pytest_code="def test_f():\n    pass\n"),
    "validated": True,
}


def _make_smell(target_name="f", issue_type="Too Many Arguments"):
    from core.schemas import CodeSmell
    return CodeSmell(file_name="pasted_code.py", target_name=target_name, line_number=1, issue_type=issue_type, raw_code="def f(a, b, c, d, e, f):\n    pass\n")


def test_run_analysis_no_input_returns_warning():
    message, report = app.run_analysis("", [], False, "{}")
    assert "paste some code" in message.lower()
    assert report is None


def test_run_analysis_invalid_config_json():
    message, report = app.run_analysis("def f(): pass", [], False, "{not valid json")
    assert "invalid configuration json" in message.lower()
    assert report is None


def test_run_analysis_clean_code_reports_no_smells(monkeypatch):
    monkeypatch.setattr(app, "process_codebase", lambda *a, **k: [])

    message, report = app.run_analysis("def add(a, b):\n    return a + b\n", [], False, "{}")

    assert "no structural code smells" in message.lower()
    assert report is None


def test_run_analysis_with_smell_generates_report(monkeypatch, tmp_path):
    result = dict(SAMPLE_RESULT, smell=_make_smell())
    monkeypatch.setattr(app, "process_codebase", lambda *a, **k: [result])
    monkeypatch.chdir(tmp_path)

    message, report_path = app.run_analysis("def f(a, b, c, d, e, f):\n    pass\n", [], False, "{}")

    assert "found and processed 1 code smell" in message.lower()
    assert "pasted_code.py" in message
    assert report_path is not None
    assert (tmp_path / "refactor_report.md").exists()


def test_save_config_writes_valid_json(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    status = app.save_config('{"max_arguments": 3}')

    assert "saved" in status.lower()
    assert json.loads((tmp_path / "config.json").read_text()) == {"max_arguments": 3}


def test_save_config_rejects_invalid_json(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    status = app.save_config("{not valid")

    assert "invalid json" in status.lower()
    assert not (tmp_path / "config.json").exists()
