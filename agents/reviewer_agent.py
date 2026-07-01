from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_community.chat_models import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from core.schemas import CodeSmell, RefactorProposal, TestCaseProposal
from typing import Dict, Any

class ReviewDecision(BaseModel):
    approved: bool = Field(description="True if the refactor and tests are solid and safe to run. False otherwise.")
    feedback: str = Field(description="If approved=False, provide detailed feedback on what needs to be fixed. If True, write a short approval note.")

def get_reviewer_agent(config: Dict[str, Any] = None):
    """Configures the Reviewer Agent to act as a gatekeeper."""
    config = config or {}
    llm_config = config.get("llm_backend", {"provider": "openai", "model": "gpt-4o-mini"})
    
    if llm_config.get("provider") == "ollama":
        llm = ChatOllama(model=llm_config.get("model", "llama3"), temperature=0.1)
    else:
        llm = ChatOpenAI(model=llm_config.get("model", "gpt-4o-mini"), temperature=0.1)
        
    structured_llm = llm.with_structured_output(ReviewDecision)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a Senior Principal Python Engineer acting as a code reviewer. Your job is to review AI-generated refactored code and its accompanying Pytest unit tests.\n\nReject the proposal (approved=False) if:\n1. The refactored code changes the original logic or introduces bugs.\n2. The test code is missing imports, contains syntax errors, or does not properly test the target function.\n3. The AI hallucinated variables or external dependencies.\n\nProvide clear feedback if rejecting. If it looks perfect, approve it (approved=True)."),
        ("user", "Original Issue: {issue_type}\n\nOriginal Code:\n{raw_code}\n\nRefactored Code Proposal:\n{refactored_code}\n\nPytest Code Proposal:\n{pytest_code}")
    ])
    
    return prompt | structured_llm

def run_reviewer_agent(smell: CodeSmell, refactor: RefactorProposal, test: TestCaseProposal, config: Dict[str, Any] = None) -> ReviewDecision:
    """
    Executes the Reviewer Agent to evaluate a refactor and test proposal before sandboxing.
    """
    agent = get_reviewer_agent(config)
    inputs = {
        "issue_type": smell.issue_type,
        "raw_code": smell.raw_code,
        "refactored_code": refactor.refactored_code,
        "pytest_code": test.pytest_code
    }
    return agent.invoke(inputs)