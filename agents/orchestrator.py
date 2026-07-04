import json
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from langgraph.graph import StateGraph, END

from core.parser import analyze_source_code
from core.sandbox import execute_tests
from core.schemas import CodeSmell, RefactorProposal, TestCaseProposal
from agents.refactor_agent import run_refactor_agent
from agents.test_agent import run_test_agent
from agents.reviewer_agent import run_reviewer_agent

# --- 1. Define the State for our Graph ---
class AgentGraphState(BaseModel):
    """Represents the state of our multi-agent workflow."""
    smell: CodeSmell
    refactor_proposal: Optional[RefactorProposal] = None
    test_proposal: Optional[TestCaseProposal] = None
    feedback: Optional[str] = None
    retries_left: int = 2
    use_docker: bool = False
    config: Dict[str, Any]
    
    # The final validated result
    final_result: Optional[Dict] = None

# --- 2. Define the Nodes (Agent Functions) ---
def refactor_code_node(state: AgentGraphState) -> AgentGraphState:
    """Node that runs the refactoring agent."""
    print("[*] Refactor Agent is rewriting the code...")
    proposal = run_refactor_agent(state.smell, state.feedback, state.config)
    print(f"[+] Refactoring complete. Explanation: {proposal.explanation}")
    state.refactor_proposal = proposal
    return state

def generate_tests_node(state: AgentGraphState) -> AgentGraphState:
    """Node that runs the test generation agent."""
    print("[*] Test Agent is generating unit tests...")
    proposal = run_test_agent(state.refactor_proposal, state.config)
    state.test_proposal = proposal
    return state

def review_proposal_node(state: AgentGraphState) -> AgentGraphState:
    """Node that runs the reviewer agent."""
    print("[*] Reviewer Agent is verifying the code and tests...")
    review = run_reviewer_agent(state.smell, state.refactor_proposal, state.test_proposal, state.config)
    if not review.approved:
        print(f"[-] Reviewer REJECTED: {review.feedback}. Retrying...")
        state.feedback = f"REVIEWER FEEDBACK: {review.feedback}"
        state.retries_left -= 1
    else:
        print(f"[+] Reviewer APPROVED: {review.feedback}")
        state.feedback = None # Clear feedback on approval
    return state

def sandbox_validation_node(state: AgentGraphState) -> AgentGraphState:
    """Node that runs the sandbox validation."""
    print(f"[*] Running tests in isolated sandbox (Docker: {state.use_docker})...")
    result = execute_tests(state.refactor_proposal.refactored_code, state.test_proposal.pytest_code, state.use_docker)
    
    if result["success"]:
        print("[+] Tests PASSED! Refactoring validated.\n")
        state.final_result = {"smell": state.smell, "refactor": state.refactor_proposal, "test": state.test_proposal, "validated": True}
    else:
        print(f"[-] Tests FAILED. Extracting feedback for retry...")
        state.feedback = result["output"]
        state.retries_left -= 1
        state.final_result = {"smell": state.smell, "refactor": state.refactor_proposal, "test": state.test_proposal, "validated": False}
    return state


def process_codebase(source_code: str, file_name: str = "temp.py", use_docker: bool = False, config: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    """
    Orchestrates the full flow: Parse -> Detect -> Refactor -> Test Generation
    """
    
    # --- Caching Setup ---
    CACHE_DIR = Path(".agent_cache")
    CACHE_DIR.mkdir(exist_ok=True)

    def get_cache_key(smell):
        return hashlib.sha256(smell.raw_code.encode()).hexdigest()

    def get_from_cache(key):
        cache_file = CACHE_DIR / f"{key}.json"
        if cache_file.exists():
            return json.loads(cache_file.read_text())
        return None

    def set_to_cache(key, data):
        (CACHE_DIR / f"{key}.json").write_text(json.dumps(data, indent=2))

    print(f"[*] Analyzing {file_name} for code smells...")
    smells = analyze_source_code(source_code, file_name, config)
    
    if not smells:
        print("[+] No code smells detected. Code is clean!")
        return []

    # --- 3. Build the LangGraph ---
    workflow = StateGraph(AgentGraphState)
    workflow.add_node("refactor", refactor_code_node)
    workflow.add_node("generate_tests", generate_tests_node)
    workflow.add_node("review", review_proposal_node)
    workflow.add_node("sandbox", sandbox_validation_node)

    # --- 4. Define the Edges (Control Flow) ---
    workflow.set_entry_point("refactor")
    workflow.add_edge("refactor", "generate_tests")
    workflow.add_edge("generate_tests", "review")

    def should_continue(state: AgentGraphState) -> str:
        if state.retries_left <= 0:
            print("[!] Maximum retries reached. Refactoring could not be validated.\n")
            return "end"
        if state.feedback: # If there's feedback from reviewer or sandbox
            return "refactor" # Go back to the start
        return "sandbox" # Proceed to validation

    workflow.add_conditional_edges(
        "review",
        should_continue,
        {"sandbox": "sandbox", "refactor": "refactor", "end": END}
    )
    workflow.add_conditional_edges(
        "sandbox",
        lambda s: "end" if s.final_result and s.final_result["validated"] else ("refactor" if s.retries_left > 0 else "end"),
        {"refactor": "refactor", "end": END}
    )

    app = workflow.compile()
    # --- End of Graph Definition ---

    print(f"[!] Found {len(smells)} code smell(s). Starting AI agents...\n")
    
    results = []
    for i, smell in enumerate(smells, 1):
        print(f"--- Processing Smell {i}/{len(smells)}: {smell.issue_type} in `{smell.target_name}` ---")
        
        cache_key = get_cache_key(smell)
        cached_result = get_from_cache(cache_key)
        
        if cached_result:
            print("[*] Found validated result in cache. Skipping agent calls.")
            results.append(cached_result)
            continue

        # Invoke the graph for the current smell
        initial_state = AgentGraphState(smell=smell, use_docker=use_docker, config=config)
        final_state = app.invoke(initial_state)
        result_data = final_state.get("final_result")
        if not result_data: # Handle cases where max retries are hit
            result_data = {"smell": smell, "refactor": final_state.get('refactor_proposal'), "test": final_state.get('test_proposal'), "validated": False}
        results.append(result_data) 
        
        # If successful, save the validated result to the cache
        if result_data and result_data["validated"]:
            set_to_cache(cache_key, result_data)
        
    print("[*] All detected smells have been processed by the multi-agent system.")
    return results