from langchain_core.prompts import ChatPromptTemplate
from core.schemas import CodeSmell, RefactorProposal
from agents.llm_factory import build_structured_llm
from typing import Dict, Any, List

def get_refactor_agent(config: Dict[str, Any] = None):
    """
    Configures and returns the LangChain refactoring agent.
    """
    # Enforce the structured output using our Pydantic model
    structured_llm = build_structured_llm(config, RefactorProposal)

    # Create the prompt template instructing the LLM on how to behave
    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You are an elite Python software engineer. You will be given an entire Python file "
            "and a list of every structural anti-pattern (code smell) detected in it. Produce ONE "
            "unified refactored version of the WHOLE file that fixes every listed issue at once, "
            "while strictly preserving the original behavior. Do not refactor anything not related "
            "to the listed issues.\n\n"
            "Make the smallest changes that actually fix the listed issues:\n"
            "- Preserve program behavior exactly.\n"
            "- Only modify the code required to fix the listed issues -- do not also \"clean up\" "
            "unrelated code just because you noticed it.\n"
            "- Do not rename variables, functions, or classes unless the rename is itself required "
            "to fix an issue.\n"
            "- Do not reorder statements or declarations that aren't part of a fix.\n"
            "- Preserve existing comments and docstrings; only add new ones for parts you actually change.\n"
            "- Preserve formatting and structure outside the regions you're fixing.\n"
            "- Prefer targeted, minimal edits over full rewrites -- only rewrite a whole function if "
            "the smell genuinely requires restructuring it (e.g. deep nesting).\n\n"
            "Return the complete file content in refactored_code (not just the changed snippets). "
            "Ensure the refactored code follows PEP 8 and is ready for production."
        )),
        ("user", (
            "File: {file_name}\n\n"
            "Issues detected in this file:\n{issues_summary}\n\n"
            "Full file to refactor:\n{source_code}\n\n"
            "{feedback_section}"
        ))
    ])

    # Chain the prompt and the structured LLM together
    return prompt | structured_llm

def _format_issues_summary(smells: List[CodeSmell]) -> str:
    return "\n".join(
        f"{i}. [{smell.issue_type}] in `{smell.target_name}` (line {smell.line_number}):\n"
        f"```python\n{smell.raw_code}\n```"
        for i, smell in enumerate(smells, 1)
    )

def run_refactor_agent(
    file_name: str,
    source_code: str,
    smells: List[CodeSmell],
    feedback: str = None,
    config: Dict[str, Any] = None,
) -> RefactorProposal:
    """
    Executes the refactoring agent on a whole file, addressing every detected
    smell in one unified refactor. If feedback from a failed test/review is
    provided, it attempts to fix the errors in the next attempt.
    """
    agent = get_refactor_agent(config)

    inputs = {
        "file_name": file_name,
        "source_code": source_code,
        "issues_summary": _format_issues_summary(smells),
    }
    if feedback:
        inputs["feedback_section"] = f"PREVIOUS ATTEMPT FAILED WITH TESTS:\n{feedback}\nPlease fix the errors and provide an updated refactor."
    else:
        inputs["feedback_section"] = ""

    response = agent.invoke(inputs)
    return response
