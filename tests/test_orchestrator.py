"""Exercises the LangGraph wiring in agents/orchestrator.py end-to-end with LLM calls faked out."""
from core.schemas import RefactorProposal, TestCaseProposal
from agents.reviewer_agent import ReviewDecision
from agents import orchestrator

SOURCE_WITH_SMELL = "def f(a, b, c, d, e, f):\n    pass\n"
CLEAN_SOURCE = "def add(a, b):\n    return a + b\n"

# Two independent smells in one file, to confirm they're bundled into ONE
# unified refactor rather than two separate ones.
MULTI_SMELL_SOURCE = (
    "def f(a, b, c, d, e, f):\n"
    "    try:\n"
    "        pass\n"
    "    except:\n"
    "        pass\n"
)

SAMPLE_REFACTOR = RefactorProposal(
    original_function_name="f",
    explanation="Reduced argument count and fixed the bare except.",
    refactored_code="def f(*args):\n    try:\n        pass\n    except Exception:\n        pass\n",
)
SAMPLE_TEST = TestCaseProposal(target_function_name="f", pytest_code="def test_f():\n    pass\n")


def _refactor_stub(file_name, source_code, smells, feedback, config):
    return SAMPLE_REFACTOR


def _reviewer_approve_stub(source_code, smells, refactor, test, config):
    return ReviewDecision(approved=True, feedback="Looks good.")


def test_process_codebase_no_smells_returns_empty(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert orchestrator.process_codebase(CLEAN_SOURCE, "clean.py", config={}) == []


def test_process_codebase_happy_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(orchestrator, "run_refactor_agent", _refactor_stub)
    monkeypatch.setattr(orchestrator, "run_test_agent", lambda proposal, config: SAMPLE_TEST)
    monkeypatch.setattr(orchestrator, "run_reviewer_agent", _reviewer_approve_stub)
    monkeypatch.setattr(
        orchestrator, "execute_tests",
        lambda refactored_code, test_code, use_docker=False: {"success": True, "output": "1 passed"},
    )

    results = orchestrator.process_codebase(SOURCE_WITH_SMELL, "bad.py", config={})

    assert len(results) == 1
    assert results[0]["validated"] is True
    assert results[0]["refactor"] == SAMPLE_REFACTOR
    assert results[0]["test"] == SAMPLE_TEST
    assert len(results[0]["smells"]) == 1
    assert results[0]["source_code"] == SOURCE_WITH_SMELL
    assert results[0]["config"] == {}


def test_process_codebase_bundles_all_smells_into_one_refactor(tmp_path, monkeypatch):
    """Multiple smells in the same file must produce ONE unified refactor call."""
    monkeypatch.chdir(tmp_path)
    calls = []

    def counting_refactor(file_name, source_code, smells, feedback, config):
        calls.append(smells)
        return SAMPLE_REFACTOR

    monkeypatch.setattr(orchestrator, "run_refactor_agent", counting_refactor)
    monkeypatch.setattr(orchestrator, "run_test_agent", lambda proposal, config: SAMPLE_TEST)
    monkeypatch.setattr(orchestrator, "run_reviewer_agent", _reviewer_approve_stub)
    monkeypatch.setattr(
        orchestrator, "execute_tests",
        lambda refactored_code, test_code, use_docker=False: {"success": True, "output": "1 passed"},
    )

    results = orchestrator.process_codebase(MULTI_SMELL_SOURCE, "bad.py", config={})

    assert len(results) == 1  # one consolidated result for the whole file
    assert len(calls) == 1  # the refactor agent was invoked exactly once for this attempt
    assert len(calls[0]) == len(results[0]["smells"]) >= 2  # bundled, not split


def test_process_codebase_sorts_smells_by_severity(tmp_path, monkeypatch):
    """Bare Except (High) must be presented before Too Many Arguments (Medium)."""
    monkeypatch.chdir(tmp_path)
    captured = {}

    def capturing_refactor(file_name, source_code, smells, feedback, config):
        captured["order"] = [s.issue_type for s in smells]
        return SAMPLE_REFACTOR

    monkeypatch.setattr(orchestrator, "run_refactor_agent", capturing_refactor)
    monkeypatch.setattr(orchestrator, "run_test_agent", lambda proposal, config: SAMPLE_TEST)
    monkeypatch.setattr(orchestrator, "run_reviewer_agent", _reviewer_approve_stub)
    monkeypatch.setattr(
        orchestrator, "execute_tests",
        lambda refactored_code, test_code, use_docker=False: {"success": True, "output": "1 passed"},
    )

    orchestrator.process_codebase(MULTI_SMELL_SOURCE, "bad.py", config={})

    assert captured["order"].index("Bare Except") < captured["order"].index("Too Many Arguments")


def test_process_codebase_caches_validated_result(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    calls = {"n": 0}

    def fake_refactor(file_name, source_code, smells, feedback, config):
        calls["n"] += 1
        return SAMPLE_REFACTOR

    monkeypatch.setattr(orchestrator, "run_refactor_agent", fake_refactor)
    monkeypatch.setattr(orchestrator, "run_test_agent", lambda proposal, config: SAMPLE_TEST)
    monkeypatch.setattr(orchestrator, "run_reviewer_agent", _reviewer_approve_stub)
    monkeypatch.setattr(
        orchestrator, "execute_tests",
        lambda refactored_code, test_code, use_docker=False: {"success": True, "output": "1 passed"},
    )

    first = orchestrator.process_codebase(SOURCE_WITH_SMELL, "bad.py", config={})
    second = orchestrator.process_codebase(SOURCE_WITH_SMELL, "bad.py", config={})

    assert calls["n"] == 1  # second run should be served from cache, not re-invoke the agent
    assert first[0]["refactor"] == second[0]["refactor"] == SAMPLE_REFACTOR


def test_process_codebase_cache_isolated_by_namespace(tmp_path, monkeypatch):
    """Two different cache_namespaces must never share cached results."""
    monkeypatch.chdir(tmp_path)
    calls = {"n": 0}

    def fake_refactor(file_name, source_code, smells, feedback, config):
        calls["n"] += 1
        return SAMPLE_REFACTOR

    monkeypatch.setattr(orchestrator, "run_refactor_agent", fake_refactor)
    monkeypatch.setattr(orchestrator, "run_test_agent", lambda proposal, config: SAMPLE_TEST)
    monkeypatch.setattr(orchestrator, "run_reviewer_agent", _reviewer_approve_stub)
    monkeypatch.setattr(
        orchestrator, "execute_tests",
        lambda refactored_code, test_code, use_docker=False: {"success": True, "output": "1 passed"},
    )

    orchestrator.process_codebase(SOURCE_WITH_SMELL, "bad.py", config={}, cache_namespace="session-a")
    orchestrator.process_codebase(SOURCE_WITH_SMELL, "bad.py", config={}, cache_namespace="session-b")

    assert calls["n"] == 2  # each namespace re-invokes the agent; no cross-session cache hit


def test_process_codebase_retries_then_gives_up(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(orchestrator, "run_refactor_agent", _refactor_stub)
    monkeypatch.setattr(orchestrator, "run_test_agent", lambda proposal, config: SAMPLE_TEST)
    monkeypatch.setattr(orchestrator, "run_reviewer_agent", _reviewer_approve_stub)
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
    """A model that never returns usable structured output must not crash the run."""
    monkeypatch.chdir(tmp_path)

    def always_raises(file_name, source_code, smells, feedback, config):
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
    """A provider rate-limit/transport error must be distinguishable from a bad model output."""
    monkeypatch.chdir(tmp_path)

    def rate_limited(file_name, source_code, smells, feedback, config):
        raise RuntimeError("Error code: 429 - rate_limit_exceeded, please try again later")

    monkeypatch.setattr(orchestrator, "run_refactor_agent", rate_limited)

    results = orchestrator.process_codebase(SOURCE_WITH_SMELL, "bad.py", config={})

    assert results[0]["stage"] == "refactor"
    assert results[0]["error_kind"] == "api_error"


def test_process_codebase_reviewer_rejection_has_no_error_kind(tmp_path, monkeypatch):
    """A reviewer rejection must not be misreported as an API/generation error."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(orchestrator, "run_refactor_agent", _refactor_stub)
    monkeypatch.setattr(orchestrator, "run_test_agent", lambda proposal, config: SAMPLE_TEST)
    monkeypatch.setattr(
        orchestrator, "run_reviewer_agent",
        lambda source_code, smells, refactor, test, config: ReviewDecision(approved=False, feedback="Not good enough."),
    )

    results = orchestrator.process_codebase(SOURCE_WITH_SMELL, "bad.py", config={})

    assert results[0]["validated"] is False
    assert results[0]["stage"] == "review"
    assert results[0]["error_kind"] is None


def test_process_codebase_clears_stale_test_after_later_refactor_failure(tmp_path, monkeypatch):
    """A stale test_proposal from an earlier retry must not leak into a later refactor failure."""
    monkeypatch.chdir(tmp_path)
    calls = {"n": 0}

    def flaky_refactor(file_name, source_code, smells, feedback, config):
        calls["n"] += 1
        if calls["n"] == 1:
            return SAMPLE_REFACTOR
        raise RuntimeError("Error code: 429 rate_limit_exceeded")

    monkeypatch.setattr(orchestrator, "run_refactor_agent", flaky_refactor)
    monkeypatch.setattr(orchestrator, "run_test_agent", lambda proposal, config: SAMPLE_TEST)
    monkeypatch.setattr(
        orchestrator, "run_reviewer_agent",
        lambda source_code, smells, refactor, test, config: ReviewDecision(approved=False, feedback="Not good enough."),
    )

    results = orchestrator.process_codebase(SOURCE_WITH_SMELL, "bad.py", config={})

    assert len(results) == 1
    assert results[0]["validated"] is False
    assert results[0]["stage"] == "refactor"
    assert results[0]["error_kind"] == "api_error"
    assert results[0]["test"] != SAMPLE_TEST
    assert "No test could be generated" in results[0]["test"].pytest_code


def test_process_codebase_sanitizes_api_error_explanation(tmp_path, monkeypatch):
    """A raw provider exception (model names, org IDs, billing links, ...) must never
    reach the user-facing explanation -- only a generic, friendly message should."""
    monkeypatch.chdir(tmp_path)

    raw_error = (
        "Error code: 429 - {'error': {'message': 'Rate limit reached for model "
        "openai/gpt-oss-120b in organization org_01kxdna03pfh7vdg8tcbw4s53n "
        "service tier on_demand', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}"
    )

    def rate_limited(file_name, source_code, smells, feedback, config):
        raise RuntimeError(raw_error)

    monkeypatch.setattr(orchestrator, "run_refactor_agent", rate_limited)

    results = orchestrator.process_codebase(SOURCE_WITH_SMELL, "bad.py", config={})

    explanation = results[0]["refactor"].explanation
    assert results[0]["error_kind"] == "api_error"
    assert "org_01kxdna03pfh7vdg8tcbw4s53n" not in explanation
    assert "openai/gpt-oss-120b" not in explanation
    assert "429" not in explanation
    assert "try again later" in explanation.lower()


def test_classify_error_detects_api_signals():
    assert orchestrator._classify_error(RuntimeError("HTTP 429 Too Many Requests")) == "api_error"
    assert orchestrator._classify_error(RuntimeError("Rate limit exceeded")) == "api_error"
    assert orchestrator._classify_error(RuntimeError("Connection timeout")) == "api_error"
    assert orchestrator._classify_error(ValueError("Invalid json output: garbage")) == "generation_error"
