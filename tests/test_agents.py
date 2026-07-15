"""
Agent tests replace the LLM (ChatOpenAI/ChatOllama) with a fake Runnable so the
LangChain prompt-wiring (correct input keys, structured-output schema) is
exercised without needing network access or an OPENAI_API_KEY.
"""
import pytest
from langchain_core.runnables import RunnableLambda
from core.schemas import CodeSmell, RefactorProposal, TestCaseProposal
from agents import refactor_agent, test_agent, reviewer_agent, llm_factory
from agents.reviewer_agent import ReviewDecision


class FakeChatModel:
    RESPONSES = {}

    def __init__(self, *args, **kwargs):
        pass

    def with_structured_output(self, schema):
        return RunnableLambda(lambda _: FakeChatModel.RESPONSES[schema])


SAMPLE_SMELL = CodeSmell(
    file_name="sample.py",
    target_name="do_thing",
    line_number=1,
    issue_type="Too Many Arguments",
    raw_code="def do_thing(a, b, c, d, e, f):\n    pass\n",
)

SAMPLE_REFACTOR = RefactorProposal(
    original_function_name="do_thing",
    explanation="Bundled arguments into a single config object.",
    refactored_code="def do_thing(config):\n    pass\n",
    required_imports=[],
)

SAMPLE_TEST = TestCaseProposal(
    target_function_name="do_thing",
    pytest_code="def test_do_thing():\n    assert do_thing({}) is None\n",
)


def test_run_refactor_agent(monkeypatch):
    FakeChatModel.RESPONSES = {RefactorProposal: SAMPLE_REFACTOR}
    monkeypatch.setattr(llm_factory, "ChatOpenAI", FakeChatModel)

    result = refactor_agent.run_refactor_agent("sample.py", SAMPLE_SMELL.raw_code, [SAMPLE_SMELL], config={})

    assert result == SAMPLE_REFACTOR


def test_run_refactor_agent_with_multiple_smells(monkeypatch):
    """A file with several smells is bundled into one refactor call, not one per smell."""
    FakeChatModel.RESPONSES = {RefactorProposal: SAMPLE_REFACTOR}
    monkeypatch.setattr(llm_factory, "ChatOpenAI", FakeChatModel)

    other_smell = CodeSmell(
        file_name="sample.py", target_name="except block", line_number=5,
        issue_type="Bare Except", raw_code="except:\n    pass\n",
    )

    result = refactor_agent.run_refactor_agent(
        "sample.py", SAMPLE_SMELL.raw_code, [SAMPLE_SMELL, other_smell], config={}
    )

    assert result == SAMPLE_REFACTOR


def test_run_refactor_agent_with_feedback(monkeypatch):
    FakeChatModel.RESPONSES = {RefactorProposal: SAMPLE_REFACTOR}
    monkeypatch.setattr(llm_factory, "ChatOpenAI", FakeChatModel)

    result = refactor_agent.run_refactor_agent(
        "sample.py", SAMPLE_SMELL.raw_code, [SAMPLE_SMELL],
        feedback="tests failed: AssertionError", config={},
    )

    assert result == SAMPLE_REFACTOR


# --- Salvage of a Groq 'tool_use_failed' response (see refactor_agent.py) ---

class _ToolUseFailedError(Exception):
    """Mirrors the real shape of openai.APIStatusError: a `.body` attribute holding
    the parsed JSON error, not just a stringified message."""
    def __init__(self, body):
        super().__init__(f"Error code: 400 - {body}")
        self.body = body


def test_salvage_extracts_code_from_python_fence():
    body = {"error": {"code": "tool_use_failed", "failed_generation": "```python\ndef f():\n    pass\n```"}}
    proposal = refactor_agent._salvage_refactor_from_tool_failure(_ToolUseFailedError(body), "sample.py")

    assert proposal is not None
    assert proposal.refactored_code == "def f():\n    pass"


def test_salvage_falls_back_to_raw_text_without_fence():
    body = {"error": {"code": "tool_use_failed", "failed_generation": "def f():\n    pass"}}
    proposal = refactor_agent._salvage_refactor_from_tool_failure(_ToolUseFailedError(body), "sample.py")

    assert proposal is not None
    assert "def f()" in proposal.refactored_code


def test_salvage_returns_none_for_unrelated_error():
    assert refactor_agent._salvage_refactor_from_tool_failure(RuntimeError("boom"), "sample.py") is None


def test_salvage_returns_none_for_different_error_code():
    body = {"error": {"code": "rate_limit_exceeded", "message": "slow down"}}
    assert refactor_agent._salvage_refactor_from_tool_failure(_ToolUseFailedError(body), "sample.py") is None


def test_salvage_returns_none_when_failed_generation_missing():
    body = {"error": {"code": "tool_use_failed"}}
    assert refactor_agent._salvage_refactor_from_tool_failure(_ToolUseFailedError(body), "sample.py") is None


def test_run_refactor_agent_recovers_from_tool_use_failed(monkeypatch):
    """The end-to-end call must return the salvaged refactor instead of raising,
    so the pipeline proceeds as if the LLM call had succeeded normally."""
    body = {
        "error": {
            "code": "tool_use_failed",
            "message": "Tool choice is required, but model did not call a tool",
            "failed_generation": "```python\ndef do_thing(config):\n    pass\n```",
        }
    }

    def _raise(_):
        raise _ToolUseFailedError(body)

    monkeypatch.setattr(llm_factory, "ChatOpenAI", FakeChatModel)
    monkeypatch.setattr(FakeChatModel, "with_structured_output", lambda self, schema: RunnableLambda(_raise))

    result = refactor_agent.run_refactor_agent("sample.py", SAMPLE_SMELL.raw_code, [SAMPLE_SMELL], config={})

    assert result.refactored_code == "def do_thing(config):\n    pass"
    assert "recovered" in result.explanation.lower()


def test_run_refactor_agent_reraises_when_not_salvageable(monkeypatch):
    def _raise(_):
        raise RuntimeError("some unrelated failure")

    monkeypatch.setattr(llm_factory, "ChatOpenAI", FakeChatModel)
    monkeypatch.setattr(FakeChatModel, "with_structured_output", lambda self, schema: RunnableLambda(_raise))

    with pytest.raises(RuntimeError, match="some unrelated failure"):
        refactor_agent.run_refactor_agent("sample.py", SAMPLE_SMELL.raw_code, [SAMPLE_SMELL], config={})


def test_run_test_agent(monkeypatch):
    FakeChatModel.RESPONSES = {TestCaseProposal: SAMPLE_TEST}
    monkeypatch.setattr(llm_factory, "ChatOpenAI", FakeChatModel)

    result = test_agent.run_test_agent(SAMPLE_REFACTOR, config={})

    assert result == SAMPLE_TEST


def test_run_reviewer_agent(monkeypatch):
    decision = ReviewDecision(approved=True, feedback="Looks good.")
    FakeChatModel.RESPONSES = {ReviewDecision: decision}
    monkeypatch.setattr(llm_factory, "ChatOpenAI", FakeChatModel)

    result = reviewer_agent.run_reviewer_agent(
        SAMPLE_SMELL.raw_code, [SAMPLE_SMELL], SAMPLE_REFACTOR, SAMPLE_TEST, config={}
    )

    assert result == decision
