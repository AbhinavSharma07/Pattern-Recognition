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


def test_process_codebase_cache_isolated_by_namespace(tmp_path, monkeypatch):
    """Two different cache_namespaces (e.g. two different browser sessions on a
    shared public deployment) must never share cached results."""
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

    orchestrator.process_codebase(SOURCE_WITH_SMELL, "bad.py", config={}, cache_namespace="session-a")
    orchestrator.process_codebase(SOURCE_WITH_SMELL, "bad.py", config={}, cache_namespace="session-b")

    assert calls["n"] == 2  # each namespace re-invokes the agent; no cross-session cache hit


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
    # Reached the sandbox and the generated tests genuinely failed -- not an API/generation error.
    assert results[0]["stage"] == "sandbox"
    assert results[0]["error_kind"] is None


def test_process_codebase_survives_refactor_agent_exception(tmp_path, monkeypatch):
    """A model that never returns usable structured output (e.g. an Ollama model
    ignoring the JSON schema) must not crash the whole run -- it should be
    treated like any other retryable failure and reported, not raised."""
    monkeypatch.chdir(tmp_path)

    def always_raises(smell, feedback, config):
        raise ValueError("Invalid json output: not json at all")

    monkeypatch.setattr(orchestrator, "run_refactor_agent", always_raises)

    results = orchestrator.process_codebase(SOURCE_WITH_SMELL, "bad.py", config={})

    assert len(results) == 1
    assert results[0]["validated"] is False
    assert "Invalid json output" in results[0]["refactor"].explanation
    assert results[0]["test"].pytest_code  # placeholder test proposal, not None
    assert results[0]["stage"] == "refactor"
    assert results[0]["error_kind"] == "generation_error"


def test_process_codebase_classifies_rate_limit_as_api_error(tmp_path, monkeypatch):
    """A provider rate-limit/transport error must be distinguishable from the model
    just producing unusable output -- it never got a real chance to generate."""
    monkeypatch.chdir(tmp_path)

    def rate_limited(smell, feedback, config):
        raise RuntimeError("Error code: 429 - rate_limit_exceeded, please try again later")

    monkeypatch.setattr(orchestrator, "run_refactor_agent", rate_limited)

    results = orchestrator.process_codebase(SOURCE_WITH_SMELL, "bad.py", config={})

    assert results[0]["stage"] == "refactor"
    assert results[0]["error_kind"] == "api_error"


def test_process_codebase_reviewer_rejection_has_no_error_kind(tmp_path, monkeypatch):
    """A reviewer rejecting a proposal is a legitimate outcome, not a system error --
    it must not be misreported as an API/generation error."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(orchestrator, "run_refactor_agent", lambda smell, feedback, config: SAMPLE_REFACTOR)
    monkeypatch.setattr(orchestrator, "run_test_agent", lambda proposal, config: SAMPLE_TEST)
    monkeypatch.setattr(
        orchestrator, "run_reviewer_agent",
        lambda smell, refactor, test, config: ReviewDecision(approved=False, feedback="Not good enough."),
    )

    results = orchestrator.process_codebase(SOURCE_WITH_SMELL, "bad.py", config={})

    assert results[0]["validated"] is False
    assert results[0]["stage"] == "review"
    assert results[0]["error_kind"] is None


def test_classify_error_detects_api_signals():
    assert orchestrator._classify_error(RuntimeError("HTTP 429 Too Many Requests")) == "api_error"
    assert orchestrator._classify_error(RuntimeError("Rate limit exceeded")) == "api_error"
    assert orchestrator._classify_error(RuntimeError("Connection timeout")) == "api_error"
    assert orchestrator._classify_error(ValueError("Invalid json output: garbage")) == "generation_error"
