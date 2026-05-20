from typing import List, Dict, Any
from core.parser import analyze_source_code

from agents.refactor_agent import run_refactor_agent
from agents.test_agent import run_test_agent

def process_codebase(source_code: str, file_name: str = "temp.py") -> List[Dict[str, Any]]:
    """
    Orchestrates the full flow: Parse -> Detect -> Refactor -> Test Generation
    """
    print(f"[*] Analyzing {file_name} for code smells...")
    smells = analyze_source_code(source_code, file_name)
    
    if not smells:
        print("[+] No code smells detected. Code is clean!")
        return []

    print(f"[!] Found {len(smells)} code smell(s). Starting AI agents...\n")
    
    results = []
    for i, smell in enumerate(smells, 1):
        print(f"--- Processing Smell {i}/{len(smells)}: {smell.issue_type} in `{smell.target_name}` ---")
        
        # Step 1: Refactor the bad code
        print("[*] Refactor Agent is rewriting the code...")
        refactor_proposal = run_refactor_agent(smell)
        print(f"[+] Refactoring complete. Explanation: {refactor_proposal.explanation}")
        
        # Step 2: Generate Pytest unit tests for the rewritten code
        print("[*] Test Agent is generating unit tests for the new code...")
        test_proposal = run_test_agent(refactor_proposal)
        print("[+] Test generation complete.\n")
        
        # Store the complete pipeline result
        results.append({
            "smell": smell,
            "refactor": refactor_proposal,
            "test": test_proposal
        })
        
    print("[*] All detected smells have been processed by the multi-agent system.")
    return results