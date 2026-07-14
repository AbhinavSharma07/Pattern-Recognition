# Multi-Agent AST Pattern Analyzer & Auto-Refactorer 
  
An autonomous, end-to-end Python code analysis and refactoring tool that uses Abstract Syntax Trees (AST) and a multi-agent LLM system to detect, refactor, and validate code improvements.

---

## Key Features

-   **🤖 Automated Code Smell Detection:** Identifies common anti-patterns in Python code (e.g., deep nesting, excessive arguments) using static AST analysis.
-   **🧠 LLM-Powered Refactoring:** Utilizes large language models to generate improved, more efficient code based on detected smells.
-   **🧪 Automated Test Generation:** An AI agent creates `pytest` compatible unit tests to verify the correctness of the refactored code.
-   **🛡️ Sandboxed Validation:** Executes generated tests in an isolated environment to ensure the refactored code is safe and correct before applying changes.
-   **🔄 Feedback Loop:** If validation fails, the system can automatically attempt to re-refactor the code based on the test errors.
-   **⌨️ CLI Interface:** A user-friendly command-line tool to initiate scans and manage the refactoring process.

## Technology Stack

-   **Language:** Python 3.10+
-   **Static Analysis:** Built-in `ast` module
-   **Agent Framework:** LangChain / LangGraph
-   **LLM Integration:** Groq
-   **Data Validation:** Pydantic
-   **CLI Framework:** Typer
-   **Testing:** `pytest`

## Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-username/your-repository-name.git
    cd your-repository-name
    ```

2.  **Create and activate a virtual environment:**
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # On Windows, use: .venv\Scripts\activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Set up environment variables:**
    Create a `.env` file in the root directory and add an API key for whichever
    LLM backend you want to use. The default (`config.json`'s `llm_backend`) is
    **Groq**, since it's free and confirmed to reliably complete the full
    refactor → test → review → sandbox pipeline:
    ```
    GROQ_API_KEY="your-groq-api-key-here"
    ```

    Alternative backends are also supported — set `llm_backend.provider` in
    `config.json` to switch, and provide the matching key:
    ```
    OPENAI_API_KEY="your-openai-api-key-here"      # provider: "openai"
    OLLAMA_API_KEY="your-ollama-cloud-key-here"     # provider: "ollama" (omit for a local Ollama server)
    ```

## Basic Usage

To scan a Python file or directory for code smells:
```bash
python -m agents.main scan path/to/your/code
```

To automatically attempt to fix detected smells (add `--apply` to write the
validated refactors back to disk, `--report` for a Markdown summary, and
`--docker` to run the sandbox tests inside a container):
```bash
python -m agents.main fix path/to/your/code --apply --report
```

Alternatively, install the project (`pip install -e .`) to get an `ast-refactor`
command on your PATH:
```bash
ast-refactor scan path/to/your/code
ast-refactor fix path/to/your/code --apply
```

To launch the Gradio UI:
```bash
python app.py
```

## Example

Save this as `example.py` — it's deliberately packed with several anti-patterns at once:

```python
import os

def process_user_data(a, b, c, d, e, f, g):
    if a > 0:
        for i in range(b):
            while c < 10:
                if d == 5:
                    print(e, f, g)
                    c += 1

    try:
        os.system("echo risky")
    except Exception as e:
        print(f"Error: {e}")

    valid_data = [x for x in range(100) if x % 2 == 0 if x % 3 == 0 if x % 5 == 0]
    return valid_data
```

Running `ast-refactor scan example.py` reports every smell in it:

```
⚠️ Found 5 code smell(s) in example.py:
  1. process_user_data (Line 3): Too Many Arguments
  2. process_user_data (Line 3): Excessive Nesting Depth
  3. os.system (Line 12): Discouraged 'os.system' call
  4. except Exception block (Line 13): Generic Exception
  5. list comprehension (Line 16): Complex List Comprehension
```

Running `ast-refactor fix example.py --apply --report` sends all five smells
through the full agent pipeline as **one unified refactor** (refactor → generate
tests → review → sandbox-validate) that addresses every issue in the file at
once, rather than one independent refactor per smell -- if that refactor's
tests pass, the whole file is updated in place and a Markdown report is
written explaining every issue that was fixed.

## Running the Tests

```bash
pip install -r requirements.txt
pytest -v
```
