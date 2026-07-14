import os
from agents.orchestrator import process_codebase
from dotenv import load_dotenv

# Load environment variables (specifically OPENAI_API_KEY from your .env file)
load_dotenv()

SAMPLE_BAD_CODE = """
def process_user_data(a, b, c, d, e, f, g):
    if a > 0:
        for i in range(b):
            while c < 10:
                if d == 5:
                    print(e, f, g)
                    c += 1

    # Anti-Pattern: Generic Exception
    try:
        print("Doing something risky")
    except Exception as e:
        print(f"Error: {e}")
        
    # Anti-Pattern: Complex List Comprehension
    valid_data = [x for x in range(100) if x % 2 == 0 if x % 3 == 0 if x % 5 == 0]
"""

if __name__ == "__main__":
    if not any(os.getenv(key) for key in ("GROQ_API_KEY", "OPENAI_API_KEY", "OLLAMA_API_KEY")):
        print("ERROR: No LLM API key is set. Please create a .env file and add one (see README.md).")
    else:
        print("Starting end-to-end demo...\n")
        # This will trigger the parser and the full unified refactor -> test -> review -> sandbox pipeline
        results = process_codebase(SAMPLE_BAD_CODE, "bad_code.py")

        for res in results:
            print("\n" + "="*60)
            issues = ", ".join(f"{s.issue_type} in {s.target_name}" for s in res["smells"])
            print(f"ISSUES ADDRESSED: {issues}")
            print("="*60)
            print("\n[UNIFIED REFACTOR PROPOSAL]")
            print(res['refactor'].refactored_code)
            print("\n[GENERATED PYTEST PROPOSAL]")
            print(res['test'].pytest_code)
            print("="*60 + "\n")