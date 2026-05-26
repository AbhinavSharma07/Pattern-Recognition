from langchain_openai import ChatOpenAI
from langchain_community.chat_models import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from core.schemas import RefactorProposal, TestCaseProposal
from typing import Dict, Any

def get_test_agent(config: Dict[str, Any] = None):
    """
    Configures and returns the LangChain test generation agent.
    """
    config = config or {}
    llm_config = config.get("llm_backend", {"provider": "openai", "model": "gpt-4o-mini"})
    
    if llm_config.get("provider") == "ollama":
        llm = ChatOllama(model=llm_config.get("model", "llama3"), temperature=0.1)
    else:
        llm = ChatOpenAI(model=llm_config.get("model", "gpt-4o-mini"), temperature=0.1)
    
    structured_llm = llm.with_structured_output(TestCaseProposal)

    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an expert Python QA engineer. Given a refactored Python function, write a robust pytest function to test it. Consider edge cases, valid inputs, and potential errors. Return the pytest code strictly according to the requested schema. Ensure the code is ready to execute.\n\nIMPORTANT: Assume the refactored function is saved in a file named `target_module.py`. You MUST import the target function from it at the top of your test code (e.g., `from target_module import your_function`)."),
        ("user", "Target Function: {original_function_name}\n\nRefactored Code:\n{refactored_code}\n\nExplanation of changes: {explanation}")
    ])

    return prompt | structured_llm

def run_test_agent(proposal: RefactorProposal, config: Dict[str, Any] = None) -> TestCaseProposal:
    """
    Executes the test generation agent on a given RefactorProposal.
    """
    agent = get_test_agent(config)
    
    # We pass the refactored proposal into the prompt to generate corresponding tests
    response = agent.invoke(proposal.model_dump())
    return response