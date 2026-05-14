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
-   **Agent Framework:** LangChain
-   **LLM Integration:** `langchain-openai`
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
    Create a `.env` file in the root directory and add your OpenAI API key:
    ```
    OPENAI_API_KEY="your-api-key-here"
    ```

## Basic Usage

To scan a Python file or directory for code smells:
```bash
python -m cli.main scan path/to/your/code
```

To automatically attempt to fix detected smells:
```bash
python -m cli.main fix path/to/your/code
```
