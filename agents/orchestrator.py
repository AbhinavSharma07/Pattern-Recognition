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
# Every node below catches Exception broadly and on purpose: an LLM call can fail
# in ways that have nothing to do with our code (a model that ignores the
# structured-output schema, a transient provider error, ...). Treating any such
# failure as retryable feedback keeps one bad LLM response from crashing the
# whole batch, instead of only doing so for the reviewer/sandbox-rejection path.
def refactor_code_node(state: AgentGraphState) -> AgentGraphState:
    """Node that runs the refactoring agent."""
    print("[*] Refactor Agent is rewriting the code...")
    try:
        proposal = run_refactor_agent(state.smell, state.feedback, state.config)
    except Exception as e:
        print(f"[-] Refactor Agent failed: {e}")
        state.refactor_proposal = None
        state.feedback = f"REFACTOR AGENT ERROR: {e}"
        state.retries_left -= 1
        return state
    print(f"[+] Refactoring complete. Explanation: {proposal.explanation}")
    state.refactor_proposal = proposal
    state.feedback = None
    return state

def generate_tests_node(state: AgentGraphState) -> AgentGraphState:
    """Node that runs the test generation agent."""
    if state.refactor_proposal is None:
        return state  # A previous step already failed; nothing to generate tests for.
    print("[*] Test Agent is generating unit tests...")
    try:
        proposal = run_test_agent(state.refactor_proposal, state.config)
    except Exception as e:
        print(f"[-] Test Agent failed: {e}")
        state.test_proposal = None
        state.feedback = f"TEST AGENT ERROR: {e}"
        state.retries_left -= 1
        return state
    state.test_proposal = proposal
    return state

def review_proposal_node(state: AgentGraphState) -> AgentGraphState:
    """Node that runs the reviewer agent."""
    if state.refactor_proposal is None or state.test_proposal is None:
        return state  # A previous step already failed; nothing to review.
    print("[*] Reviewer Agent is verifying the code and tests...")
    try:
        review = run_reviewer_agent(state.smell, state.refactor_proposal, state.test_proposal, state.config)
    except Exception as e:
        print(f"[-] Reviewer Agent failed: {e}")
        state.feedback = f"REVIEWER AGENT ERROR: {e}"
        state.retries_left -= 1
        return state
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
        return hashlib.sha256(f"{smell.issue_type}:{smell.raw_code}".encode()).hexdigest()

    def get_from_cache(key):
        cache_file = CACHE_DIR / f"{key}.json"
        if not cache_file.exists():
            return None
        data = json.loads(cache_file.read_text())
        return {
            "smell": CodeSmell(**data["smell"]),
            "refactor": RefactorProposal(**data["refactor"]),
            "test": TestCaseProposal(**data["test"]),
            "validated": data["validated"],
        }

    def set_to_cache(key, data):
        serializable = {
            "smell": data["smell"].model_dump(),
            "refactor": data["refactor"].model_dump(),
            "test": data["test"].model_dump(),
            "validated": data["validated"],
        }
        (CACHE_DIR / f"{key}.json").write_text(json.dumps(serializable, indent=2))

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
        if not result_data:
            # Max retries hit without ever reaching the sandbox (e.g. the LLM never
            # produced a usable proposal). Fall back to placeholder objects rather than
            # None, so report/UI/apply code downstream can keep assuming real objects.
            error_note = final_state.get("feedback") or "Agent pipeline failed for an unknown reason."
            refactor_proposal = final_state.get("refactor_proposal") or RefactorProposal(
                original_function_name=smell.target_name,
                explanation=f"Refactoring failed after exhausting retries. Last error: {error_note}",
                refactored_code=smell.raw_code,
            )
            test_proposal = final_state.get("test_proposal") or TestCaseProposal(
                target_function_name=smell.target_name,
                pytest_code="# No test could be generated: the agent pipeline failed before reaching this step.",
            )
            result_data = {"smell": smell, "refactor": refactor_proposal, "test": test_proposal, "validated": False}
        results.append(result_data)
        
        # If successful, save the validated result to the cache
        if result_data and result_data["validated"]:
            set_to_cache(cache_key, result_data)
        
    print("[*] All detected smells have been processed by the multi-agent system.")
    return results