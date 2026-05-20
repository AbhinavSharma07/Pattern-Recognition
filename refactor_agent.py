from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from core.schemas import CodeSmell, RefactorProposal

def get_refactor_agent():
    """
    Configures and returns the LangChain refactoring agent.
    """
    # Initialize the LLM. 
    # gpt-4o-mini is cost-effective and excellent at structured outputs.
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.1)
    
    # Enforce the structured output using our Pydantic model
    structured_llm = llm.with_structured_output(RefactorProposal)

    # Create the prompt template instructing the LLM on how to behave
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an elite Python software engineer. Your task is to analyze structural anti-patterns (code smells) in Python code and provide a refactored version that fixes the issue while strictly maintaining the original functionality. Ensure the refactored code is clean, follows PEP 8, and is ready for production."),
        ("user", "File: {file_name}\nTarget: {target_name}\nIssue: {issue_type}\n\nCode to refactor:\n{raw_code}\n\n{feedback_section}")
    ])

    # Chain the prompt and the structured LLM together
    return prompt | structured_llm

def run_refactor_agent(smell: CodeSmell, feedback: str = None) -> RefactorProposal:
    """
    Executes the refactoring agent on a given CodeSmell.
    If feedback from a failed test is provided, it attempts to fix the errors.
    """
    agent = get_refactor_agent()
    
    inputs = smell.model_dump()
    if feedback:
        inputs["feedback_section"] = f"PREVIOUS ATTEMPT FAILED WITH TESTS:\n{feedback}\nPlease fix the errors and provide an updated refactor."
    else:
        inputs["feedback_section"] = ""

    # We pass the properties of the CodeSmell object directly into the prompt variables
    response = agent.invoke(inputs)
    return response