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

# Failure-stage taxonomy for reporting: which stage the pipeline was in when it gave
# up, distinct from the boolean "validated" (which only means "sandbox tests passed").
# error_kind distinguishes a genuine API/transport problem from the model just
# producing bad output, so a rate-limit error isn't misreported as "tests failed"
# when no test ever ran.
STAGE_REFACTOR = "refactor"
STAGE_TEST_GENERATION = "test_generation"
STAGE_REVIEW = "review"
STAGE_SANDBOX = "sandbox"

ERROR_KIND_API = "api_error"
ERROR_KIND_GENERATION = "generation_error"

_API_ERROR_SIGNALS = (
    "rate limit", "rate_limit", "429", "quota", "insufficient_quota",
    "timeout", "connection", "503", "502", "500", "unavailable",
)


def _classify_error(e: Exception) -> str:
    """Best-effort classification of an agent-call exception, so the report can
    say "API error" (transient/provider-side) rather than implying the model's
    output itself was the problem."""
    text = str(e).lower()
    if any(signal in text for signal in _API_ERROR_SIGNALS):
        return ERROR_KIND_API
    return ERROR_KIND_GENERATION


# --- 1. Define the State for our Graph ---
class AgentGraphState(BaseModel):
    """
    Represents the state of our multi-agent workflow for a single file.

    One unified refactor is produced per file, addressing every smell detected
    in it at once -- not one independent refactor per smell. This avoids the
    overlapping-edit conflicts that arise when several isolated per-smell
    refactors touch the same region of a file, and gives a single, coherent,
    reviewable diff per file instead of a pile of small ones.
    """
    file_name: str
    source_code: str
    smells: List[CodeSmell]
    refactor_proposal: Optional[RefactorProposal] = None
    test_proposal: Optional[TestCaseProposal] = None
    feedback: Optional[str] = None
    stage: Optional[str] = None       # last stage attempted: refactor/test_generation/review/sandbox
    error_kind: Optional[str] = None  # api_error/generation_error, or None if no system error occurred
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
    """Node that runs the refactoring agent over the whole file and all its smells."""
    print(f"[*] Refactor Agent is rewriting {state.file_name} to address {len(state.smells)} smell(s)...")
    state.stage = STAGE_REFACTOR
    try:
        proposal = run_refactor_agent(state.file_name, state.source_code, state.smells, state.feedback, state.config)
    except Exception as e:
        print(f"[-] Refactor Agent failed: {e}")
        state.refactor_proposal = None
        state.feedback = f"REFACTOR AGENT ERROR: {e}"
        state.error_kind = _classify_error(e)
        state.retries_left -= 1
        return state
    print(f"[+] Refactoring complete. Explanation: {proposal.explanation}")
    state.refactor_proposal = proposal
    state.feedback = None
    state.error_kind = None
    return state

def generate_tests_node(state: AgentGraphState) -> AgentGraphState:
    """Node that runs the test generation agent."""
    if state.refactor_proposal is None:
        return state  # A previous step already failed; nothing to generate tests for.
    print("[*] Test Agent is generating unit tests...")
    state.stage = STAGE_TEST_GENERATION
    try:
        proposal = run_test_agent(state.refactor_proposal, state.config)
    except Exception as e:
        print(f"[-] Test Agent failed: {e}")
        state.test_proposal = None
        state.feedback = f"TEST AGENT ERROR: {e}"
        state.error_kind = _classify_error(e)
        state.retries_left -= 1
        return state
    state.test_proposal = proposal
    state.error_kind = None
    return state

def review_proposal_node(state: AgentGraphState) -> AgentGraphState:
    """Node that runs the reviewer agent."""
    if state.refactor_proposal is None or state.test_proposal is None:
        return state  # A previous step already failed; nothing to review.
    print("[*] Reviewer Agent is verifying the code and tests...")
    state.stage = STAGE_REVIEW
    try:
        review = run_reviewer_agent(state.source_code, state.smells, state.refactor_proposal, state.test_proposal, state.config)
    except Exception as e:
        print(f"[-] Reviewer Agent failed: {e}")
        state.feedback = f"REVIEWER AGENT ERROR: {e}"
        state.error_kind = _classify_error(e)
        state.retries_left -= 1
        return state
    if not review.approved:
        print(f"[-] Reviewer REJECTED: {review.feedback}. Retrying...")
        state.feedback = f"REVIEWER FEEDBACK: {review.feedback}"
        state.error_kind = None  # a legitimate rejection, not a system/API error
        state.retries_left -= 1
    else:
        print(f"[+] Reviewer APPROVED: {review.feedback}")
        state.feedback = None # Clear feedback on approval
        state.error_kind = None
    return state

def sandbox_validation_node(state: AgentGraphState) -> AgentGraphState:
    """Node that runs the sandbox validation."""
    print(f"[*] Running tests in isolated sandbox (Docker: {state.use_docker})...")
    state.stage = STAGE_SANDBOX
    result = execute_tests(state.refactor_proposal.refactored_code, state.test_proposal.pytest_code, state.use_docker)

    if result["success"]:
        print("[+] Tests PASSED! Refactoring validated.\n")
        state.final_result = {
            "smells": state.smells, "refactor": state.refactor_proposal, "test": state.test_proposal,
            "validated": True, "stage": STAGE_SANDBOX, "error_kind": None,
        }
    else:
        print(f"[-] Tests FAILED. Extracting feedback for retry...")
        state.feedback = result["output"]
        state.error_kind = None  # a genuine test failure -- tests did run
        state.retries_left -= 1
        state.final_result = {
            "smells": state.smells, "refactor": state.refactor_proposal, "test": state.test_proposal,
            "validated": False, "stage": STAGE_SANDBOX, "error_kind": None,
        }
    return state


def process_codebase(
    source_code: str,
    file_name: str = "temp.py",
    use_docker: bool = False,
    config: Dict[str, Any] = None,
    cache_namespace: str = None,
) -> List[Dict[str, Any]]:
    """
    Orchestrates the full flow: Parse -> Detect all smells -> one unified
    Refactor -> Test Generation -> Review -> Sandbox Validation, for the file
    as a whole.

    Returns a list with either zero entries (no smells found) or exactly one
    entry: the single consolidated result for this file, whose "smells" field
    lists every anti-pattern the refactor was meant to address. (Kept as a
    list, rather than returning the dict directly, so existing "for res in
    results" callers iterating over a file's results didn't need to change
    shape when this moved from one-result-per-smell to one-result-per-file.)

    cache_namespace scopes the result cache (e.g. to a browser session hash in
    a multi-tenant web UI) so one caller's cached results are never served to
    a different caller. Defaults to a shared namespace, matching the original
    single-user CLI behavior.
    """

    # --- Caching Setup ---
    CACHE_DIR = Path(".agent_cache") / (cache_namespace or "shared")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def get_cache_key(smells):
        # Keyed on the whole file's content plus which issues were found in it,
        # since the unified refactor addresses the file as a whole.
        fingerprint = source_code + "|" + "|".join(f"{s.issue_type}:{s.raw_code}" for s in smells)
        return hashlib.sha256(fingerprint.encode()).hexdigest()

    def get_from_cache(key):
        cache_file = CACHE_DIR / f"{key}.json"
        if not cache_file.exists():
            return None
        data = json.loads(cache_file.read_text())
        return {
            "smells": [CodeSmell(**s) for s in data["smells"]],
            "refactor": RefactorProposal(**data["refactor"]),
            "test": TestCaseProposal(**data["test"]),
            "validated": data["validated"],
            "stage": data.get("stage"),
            "error_kind": data.get("error_kind"),
            "source_code": data.get("source_code", ""),
        }

    def set_to_cache(key, data):
        serializable = {
            "smells": [s.model_dump() for s in data["smells"]],
            "refactor": data["refactor"].model_dump(),
            "test": data["test"].model_dump(),
            "validated": data["validated"],
            "stage": data.get("stage"),
            "error_kind": data.get("error_kind"),
            "source_code": data.get("source_code", ""),
        }
        (CACHE_DIR / f"{key}.json").write_text(json.dumps(serializable, indent=2))

    print(f"[*] Analyzing {file_name} for code smells...")
    smells = analyze_source_code(source_code, file_name, config)

    if not smells:
        print("[+] No code smells detected. Code is clean!")
        return []

    print(f"[!] Found {len(smells)} code smell(s) in {file_name}. Starting AI agents for one unified refactor...\n")

    cache_key = get_cache_key(smells)
    cached_result = get_from_cache(cache_key)
    if cached_result:
        print("[*] Found validated result in cache. Skipping agent calls.")
        return [cached_result]

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

    initial_state = AgentGraphState(
        file_name=file_name, source_code=source_code, smells=smells,
        use_docker=use_docker, config=config,
    )
    final_state = app.invoke(initial_state)
    result_data = final_state.get("final_result")
    if not result_data:
        # Max retries hit without ever reaching the sandbox (e.g. the LLM never
        # produced a usable proposal). Fall back to placeholder objects rather than
        # None, so report/UI/apply code downstream can keep assuming real objects.
        error_note = final_state.get("feedback") or "Agent pipeline failed for an unknown reason."
        refactor_proposal = final_state.get("refactor_proposal") or RefactorProposal(
            original_function_name=file_name,
            explanation=f"Refactoring failed after exhausting retries. Last error: {error_note}",
            refactored_code=source_code,
        )
        test_proposal = final_state.get("test_proposal") or TestCaseProposal(
            target_function_name=file_name,
            pytest_code="# No test could be generated: the agent pipeline failed before reaching this step.",
        )
        result_data = {
            "smells": smells, "refactor": refactor_proposal, "test": test_proposal, "validated": False,
            "stage": final_state.get("stage"), "error_kind": final_state.get("error_kind"),
        }

    result_data["source_code"] = source_code

    # If successful, save the validated result to the cache
    if result_data and result_data["validated"]:
        set_to_cache(cache_key, result_data)

    print("[*] File processed by the multi-agent system.")
    return [result_data]
