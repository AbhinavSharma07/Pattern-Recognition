import json
import hashlib
from pathlib import Path
from typing import List, Dict, Any
from core.parser import analyze_source_code, load_config
from core.sandbox import execute_tests

from agents.refactor_agent import run_refactor_agent
from agents.test_agent import run_test_agent
from agents.reviewer_agent import run_reviewer_agent

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

    """
    Orchestrates the full flow: Parse -> Detect -> Refactor -> Test Generation
    """
    print(f"[*] Analyzing {file_name} for code smells...")
    smells = analyze_source_code(source_code, file_name, config)
    
    if not smells:
        print("[+] No code smells detected. Code is clean!")
        return []

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
        
        MAX_RETRIES = 2
        success = False
        feedback = None
        
        for attempt in range(MAX_RETRIES + 1):
            if attempt > 0:
                print(f"\n[*] Retry {attempt}/{MAX_RETRIES} based on test feedback...")

            # Step 1: Refactor the bad code
            print("[*] Refactor Agent is rewriting the code...")
            refactor_proposal = run_refactor_agent(smell, feedback, config)
            print(f"[+] Refactoring complete. Explanation: {refactor_proposal.explanation}")
            
            # Step 2: Generate Pytest unit tests for the rewritten code
            print("[*] Test Agent is generating unit tests for the new code...")
            test_proposal = run_test_agent(refactor_proposal, config)
            
            # Step 2.5: Reviewer Agent checks the work
            print("[*] Reviewer Agent is verifying the code and tests...")
            review = run_reviewer_agent(smell, refactor_proposal, test_proposal, config)
            if not review.approved:
                print(f"[-] Reviewer REJECTED: {review.feedback}. Retrying...")
                feedback = f"REVIEWER FEEDBACK: {review.feedback}"
                continue
            print(f"[+] Reviewer APPROVED: {review.feedback}")

            # Step 3: Sandbox Validation
            print(f"[*] Running tests in isolated sandbox (Docker: {use_docker})...")
            sandbox_result = execute_tests(refactor_proposal.refactored_code, test_proposal.pytest_code, use_docker)
            
            if sandbox_result["success"]:
                print("[+] Tests PASSED! Refactoring validated.\n")
                success = True
                break
            else:
                print(f"[-] Tests FAILED. Extracting feedback for retry...")
                feedback = sandbox_result["output"]

        if not success:
            print("[!] Maximum retries reached. Refactoring could not be validated.\n")
        
        # Store the complete pipeline result
        result_data = {
            "smell": smell,
            "refactor": refactor_proposal,
            "test": test_proposal,
            "validated": success
        }
        results.append(result_data)
        
        # If successful, save the validated result to the cache
        if success:
            set_to_cache(cache_key, result_data)
        
    print("[*] All detected smells have been processed by the multi-agent system.")
    return results