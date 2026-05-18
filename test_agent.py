from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from core.schemas import RefactorProposal, TestCaseProposal

def get_test_agent():
    """
    Configures and returns the LangChain test generation agent.
    """
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.1)
    
    structured_llm = llm.with_structured_output(TestCaseProposal)

    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an expert Python QA engineer. Given a refactored Python function, write a robust pytest function to test it. Consider edge cases, valid inputs, and potential errors. Return the pytest code strictly according to the requested schema. Ensure the code is ready to execute."),
        ("user", "Target Function: {original_function_name}\n\nRefactored Code:\n{refactored_code}\n\nExplanation of changes: {explanation}")
    ])

    return prompt | structured_llm

def run_test_agent(proposal: RefactorProposal) -> TestCaseProposal:
    """
    Executes the test generation agent on a given RefactorProposal.
    """
    agent = get_test_agent()
    
    # We pass the refactored proposal into the prompt to generate corresponding tests
    response = agent.invoke(proposal.model_dump())
    return response