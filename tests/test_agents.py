"""
Agent tests replace the LLM (ChatOpenAI/ChatOllama) with a fake Runnable so the
LangChain prompt-wiring (correct input keys, structured-output schema) is
exercised without needing network access or an OPENAI_API_KEY.
"""
from langchain_core.runnables import RunnableLambda
from core.schemas import CodeSmell, RefactorProposal, TestCaseProposal
from agents import refactor_agent, test_agent, reviewer_agent
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
    monkeypatch.setattr(refactor_agent, "ChatOpenAI", FakeChatModel)

    result = refactor_agent.run_refactor_agent(SAMPLE_SMELL, config={})

    assert result == SAMPLE_REFACTOR


def test_run_refactor_agent_with_feedback(monkeypatch):
    FakeChatModel.RESPONSES = {RefactorProposal: SAMPLE_REFACTOR}
    monkeypatch.setattr(refactor_agent, "ChatOpenAI", FakeChatModel)

    result = refactor_agent.run_refactor_agent(
        SAMPLE_SMELL, feedback="tests failed: AssertionError", config={}
    )

    assert result == SAMPLE_REFACTOR


def test_run_test_agent(monkeypatch):
    FakeChatModel.RESPONSES = {TestCaseProposal: SAMPLE_TEST}
    monkeypatch.setattr(test_agent, "ChatOpenAI", FakeChatModel)

    result = test_agent.run_test_agent(SAMPLE_REFACTOR, config={})

    assert result == SAMPLE_TEST


def test_run_reviewer_agent(monkeypatch):
    decision = ReviewDecision(approved=True, feedback="Looks good.")
    FakeChatModel.RESPONSES = {ReviewDecision: decision}
    monkeypatch.setattr(reviewer_agent, "ChatOpenAI", FakeChatModel)

    result = reviewer_agent.run_reviewer_agent(SAMPLE_SMELL, SAMPLE_REFACTOR, SAMPLE_TEST, config={})

    assert result == decision
