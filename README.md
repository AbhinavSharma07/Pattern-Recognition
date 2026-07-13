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

## Running the Tests

```bash
pip install -r requirements.txt
pytest -v
```
