"""
Exercises the LangGraph wiring in agents/orchestrator.py end-to-end (parse ->
refactor -> test -> review -> sandbox) with the LLM-calling functions replaced
by fakes, so it doesn't need network access or an OPENAI_API_KEY.
"""
from core.schemas import RefactorProposal, TestCaseProposal
from agents.reviewer_agent import ReviewDecision
from agents import orchestrator

SOURCE_WITH_SMELL = "def f(a, b, c, d, e, f):\n    pass\n"
CLEAN_SOURCE = "def add(a, b):\n    return a + b\n"

SAMPLE_REFACTOR = RefactorProposal(
    original_function_name="f",
    explanation="Reduced argument count.",
    refactored_code="def f(*args):\n    pass\n",
)
SAMPLE_TEST = TestCaseProposal(target_function_name="f", pytest_code="def test_f():\n    pass\n")


def test_process_codebase_no_smells_returns_empty(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert orchestrator.process_codebase(CLEAN_SOURCE, "clean.py", config={}) == []


def test_process_codebase_happy_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(orchestrator, "run_refactor_agent", lambda smell, feedback, config: SAMPLE_REFACTOR)
    monkeypatch.setattr(orchestrator, "run_test_agent", lambda proposal, config: SAMPLE_TEST)
    monkeypatch.setattr(
        orchestrator, "run_reviewer_agent",
        lambda smell, refactor, test, config: ReviewDecision(approved=True, feedback="Looks good."),
    )
    monkeypatch.setattr(
        orchestrator, "execute_tests",
        lambda refactored_code, test_code, use_docker=False: {"success": True, "output": "1 passed"},
    )

    results = orchestrator.process_codebase(SOURCE_WITH_SMELL, "bad.py", config={})

    assert len(results) == 1
    assert results[0]["validated"] is True
    assert results[0]["refactor"] == SAMPLE_REFACTOR
    assert results[0]["test"] == SAMPLE_TEST


def test_process_codebase_caches_validated_result(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    calls = {"n": 0}

    def fake_refactor(smell, feedback, config):
        calls["n"] += 1
        return SAMPLE_REFACTOR

    monkeypatch.setattr(orchestrator, "run_refactor_agent", fake_refactor)
    monkeypatch.setattr(orchestrator, "run_test_agent", lambda proposal, config: SAMPLE_TEST)
    monkeypatch.setattr(
        orchestrator, "run_reviewer_agent",
        lambda smell, refactor, test, config: ReviewDecision(approved=True, feedback="Looks good."),
    )
    monkeypatch.setattr(
        orchestrator, "execute_tests",
        lambda refactored_code, test_code, use_docker=False: {"success": True, "output": "1 passed"},
    )

    first = orchestrator.process_codebase(SOURCE_WITH_SMELL, "bad.py", config={})
    second = orchestrator.process_codebase(SOURCE_WITH_SMELL, "bad.py", config={})

    assert calls["n"] == 1  # second run should be served from cache, not re-invoke the agent
    assert first[0]["refactor"] == second[0]["refactor"] == SAMPLE_REFACTOR


def test_process_codebase_retries_then_gives_up(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(orchestrator, "run_refactor_agent", lambda smell, feedback, config: SAMPLE_REFACTOR)
    monkeypatch.setattr(orchestrator, "run_test_agent", lambda proposal, config: SAMPLE_TEST)
    monkeypatch.setattr(
        orchestrator, "run_reviewer_agent",
        lambda smell, refactor, test, config: ReviewDecision(approved=True, feedback="Looks good."),
    )
    monkeypatch.setattr(
        orchestrator, "execute_tests",
        lambda refactored_code, test_code, use_docker=False: {"success": False, "output": "AssertionError"},
    )

    results = orchestrator.process_codebase(SOURCE_WITH_SMELL, "bad.py", config={})

    assert len(results) == 1
    assert results[0]["validated"] is False
