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
"""

if __name__ == "__main__":
    if not os.getenv("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY is not set. Please create a .env file and add your key.")
    else:
        print("Starting end-to-end Phase 2 test...\n")
        # This will trigger the parser, the refactor LLM, and the testing LLM
        results = process_codebase(SAMPLE_BAD_CODE, "bad_code.py")
        
        for res in results:
            print("\n" + "="*60)
            print(f"TARGET FUNCTION: {res['smell'].target_name}")
            print("="*60)
            print("\n[REFACTORED CODE PROPOSAL]")
            print(res['refactor'].refactored_code)
            print("\n[GENERATED PYTEST PROPOSAL]")
            print(res['test'].pytest_code)
            print("="*60 + "\n")