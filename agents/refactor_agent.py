from langchain_core.prompts import ChatPromptTemplate
from core.schemas import CodeSmell, RefactorProposal
from agents.llm_factory import build_structured_llm
from typing import Dict, Any

def get_refactor_agent(config: Dict[str, Any] = None):
    """
    Configures and returns the LangChain refactoring agent.
    """
    # Enforce the structured output using our Pydantic model
    structured_llm = build_structured_llm(config, RefactorProposal)

    # Create the prompt template instructing the LLM on how to behave
    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You are an elite Python software engineer. Your task is to analyze a structural "
            "anti-pattern (code smell) in Python code and provide a refactored version that fixes "
            "*only that issue* while strictly preserving the original behavior.\n\n"
            "Make the smallest change that actually fixes the issue:\n"
            "- Preserve program behavior exactly.\n"
            "- Only modify the code required to fix the detected issue -- do not also \"clean up\" "
            "unrelated code just because you noticed it.\n"
            "- Do not rename variables, functions, or classes unless the rename is itself required "
            "to fix the issue.\n"
            "- Do not reorder statements or declarations that aren't part of the fix.\n"
            "- Preserve existing comments and docstrings; only add new ones for parts you actually change.\n"
            "- Preserve formatting and structure outside the region you're fixing.\n"
            "- Prefer a targeted, minimal edit over a full rewrite of the function -- only rewrite "
            "the whole thing if the smell genuinely requires restructuring everything (e.g. deep nesting).\n\n"
            "Ensure the refactored code follows PEP 8 and is ready for production."
        )),
        ("user", "File: {file_name}\nTarget: {target_name}\nIssue: {issue_type}\n\nCode to refactor:\n{raw_code}\n\n{feedback_section}")
    ])

    # Chain the prompt and the structured LLM together
    return prompt | structured_llm

def run_refactor_agent(smell: CodeSmell, feedback: str = None, config: Dict[str, Any] = None) -> RefactorProposal:
    """
    Executes the refactoring agent on a given CodeSmell.
    If feedback from a failed test is provided, it attempts to fix the errors.
    """
    agent = get_refactor_agent(config)
    
    inputs = smell.model_dump()
    if feedback:
        inputs["feedback_section"] = f"PREVIOUS ATTEMPT FAILED WITH TESTS:\n{feedback}\nPlease fix the errors and provide an updated refactor."
    else:
        inputs["feedback_section"] = ""

    # We pass the properties of the CodeSmell object directly into the prompt variables
    response = agent.invoke(inputs)
    return response