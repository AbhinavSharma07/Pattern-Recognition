from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from core.schemas import CodeSmell, RefactorProposal, TestCaseProposal
from agents.llm_factory import build_structured_llm
from typing import Dict, Any, List

class ReviewDecision(BaseModel):
    approved: bool = Field(description="True if the refactor and tests are solid and safe to run. False otherwise.")
    feedback: str = Field(description="If approved=False, provide detailed feedback on what needs to be fixed. If True, write a short approval note.")

def get_reviewer_agent(config: Dict[str, Any] = None):
    """Configures the Reviewer Agent to act as a gatekeeper."""
    structured_llm = build_structured_llm(config, ReviewDecision)

    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a Senior Principal Python Engineer acting as a code reviewer. Your job is to review an AI-generated unified refactor of a whole file (addressing one or more listed issues at once) and its accompanying Pytest unit tests.\n\nReject the proposal (approved=False) if:\n1. The refactored code changes the original logic or introduces bugs.\n2. The refactor doesn't actually address all of the listed issues.\n3. The refactor makes unrelated changes beyond what the listed issues require.\n4. The test code is missing imports, contains syntax errors, or does not properly test the changed code.\n5. The AI hallucinated variables or external dependencies.\n\nProvide clear feedback if rejecting. If it looks perfect, approve it (approved=True)."),
        ("user", "Issues this refactor is meant to address:\n{issues_summary}\n\nOriginal File:\n{original_source}\n\nRefactored File Proposal:\n{refactored_code}\n\nPytest Code Proposal:\n{pytest_code}")
    ])

    return prompt | structured_llm

def _format_issues_summary(smells: List[CodeSmell]) -> str:
    return "\n".join(f"{i}. [{smell.issue_type}] in `{smell.target_name}`" for i, smell in enumerate(smells, 1))

def run_reviewer_agent(
    source_code: str,
    smells: List[CodeSmell],
    refactor: RefactorProposal,
    test: TestCaseProposal,
    config: Dict[str, Any] = None,
) -> ReviewDecision:
    """
    Executes the Reviewer Agent to evaluate a whole-file refactor (addressing
    every smell in `smells`) and its test proposal before sandboxing.
    """
    agent = get_reviewer_agent(config)
    inputs = {
        "issues_summary": _format_issues_summary(smells),
        "original_source": source_code,
        "refactored_code": refactor.refactored_code,
        "pytest_code": test.pytest_code,
    }
    return agent.invoke(inputs)
