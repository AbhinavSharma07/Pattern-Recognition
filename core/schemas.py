from pydantic import BaseModel, Field
from typing import List

class CodeSmell(BaseModel):
    """Represents a structural anti-pattern found in the source code."""
    file_name: str = Field(description="The name of the file where the smell was found.")
    target_name: str = Field(description="The name of the function or class containing the smell.")
    line_number: int = Field(description="The starting line number of the code block.")
    issue_type: str = Field(description="A description of the identified anti-pattern.")
    raw_code: str = Field(description="The raw string representation of the problematic code block.")
    reason: str = Field(
        default="",
        description="Deterministic, AST-derived explanation of why this was flagged (e.g. actual count vs configured threshold).",
    )

class RefactorProposal(BaseModel):
    """The structured response expected from the LLM Refactoring Agent."""
    original_function_name: str = Field(description="The name of the function being refactored.")
    explanation: str = Field(description="Brief explanation of why the original code was problematic and how it was fixed.")
    refactored_code: str = Field(description="The complete, fully refactored Python code block.")
    required_imports: List[str] = Field(
        default_factory=list,
        description="Any new imports required by the refactored code."
    )

class TestCaseProposal(BaseModel):
    """The structured response expected from the LLM Testing Agent."""
    target_function_name: str = Field(description="The name of the function being tested.")
    pytest_code: str = Field(description="A complete pytest function to validate the refactored code.")