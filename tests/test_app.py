import json

from core.schemas import CodeSmell, RefactorProposal, TestCaseProposal
import app

SOURCE_WITH_SMELL = "def f(a, b, c, d, e, f):\n    pass\n"

SAMPLE_RESULT = {
    "smells": [],
    "refactor": RefactorProposal(
        original_function_name="f", explanation="Bundled args.", refactored_code="def f(*args):\n    pass\n"
    ),
    "test": TestCaseProposal(target_function_name="f", pytest_code="def test_f():\n    pass\n"),
    "validated": True,
    "source_code": SOURCE_WITH_SMELL,
    "config": {},
}


def _make_smell(target_name="f", issue_type="Too Many Arguments"):
    return CodeSmell(file_name="pasted_code.py", target_name=target_name, line_number=1, issue_type=issue_type, raw_code=SOURCE_WITH_SMELL)


def test_render_result_includes_final_code_when_validated():
    rendered = app._render_result(SAMPLE_RESULT)

    assert "Final Refactored Code" in rendered
    assert "def f(*args):\n    pass" in rendered


def test_render_result_labels_code_as_unvalidated_when_not_validated():
    result = dict(SAMPLE_RESULT, validated=False)
    rendered = app._render_result(result)

    assert "Proposed Refactored Code" in rendered
    assert "unvalidated" in rendered.lower()


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
    result = dict(SAMPLE_RESULT, smells=[_make_smell()])
    monkeypatch.setattr(app, "process_codebase", lambda *a, **k: [result])
    monkeypatch.chdir(tmp_path)

    message, report_path = app.run_analysis(SOURCE_WITH_SMELL, [], False, "{}")

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


def test_save_config_on_hf_space_does_not_write_shared_file(tmp_path, monkeypatch):
    """Saving to the shared config.json on a public Space would leak to every visitor."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SPACE_ID", "someuser/somespace")

    status = app.save_config('{"max_arguments": 3}')

    assert "session" in status.lower()
    assert not (tmp_path / "config.json").exists()


def test_run_analysis_forces_docker_off_on_hf_space(monkeypatch):
    """No Docker daemon exists inside a Space container, regardless of the flag."""
    monkeypatch.setenv("SPACE_ID", "someuser/somespace")
    captured = {}

    def fake_process_codebase(source, file_name, use_docker, config, cache_namespace=None):
        captured["use_docker"] = use_docker
        return []

    monkeypatch.setattr(app, "process_codebase", fake_process_codebase)

    app.run_analysis("def add(a, b):\n    return a + b\n", [], True, "{}")

    assert captured["use_docker"] is False


def test_run_analysis_syntax_error_skips_pipeline_entirely(monkeypatch, tmp_path):
    """A syntax error must short-circuit before AST analysis or any AI agent runs,
    and must never be misreported as 'no smells found'."""
    monkeypatch.chdir(tmp_path)
    called = {"n": 0}

    def fake_process_codebase(*a, **k):
        called["n"] += 1
        return []

    monkeypatch.setattr(app, "process_codebase", fake_process_codebase)

    message, report = app.run_analysis("def f(:\n    pass\n", [], False, "{}")

    assert called["n"] == 0  # the multi-agent pipeline was never invoked
    assert "syntax" in message.lower()
    assert "failed" in message.lower()
    assert "no structural code smells" not in message.lower()


def test_run_analysis_scopes_cache_to_session(monkeypatch):
    """One visitor's cached result must never be served to a different visitor."""
    captured = {}

    def fake_process_codebase(source, file_name, use_docker, config, cache_namespace=None):
        captured["cache_namespace"] = cache_namespace
        return []

    monkeypatch.setattr(app, "process_codebase", fake_process_codebase)

    class FakeRequest:
        session_hash = "abc123"

    app.run_analysis("def add(a, b):\n    return a + b\n", [], False, "{}", request=FakeRequest())

    assert captured["cache_namespace"] == "abc123"
