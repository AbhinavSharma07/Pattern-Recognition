# Project Details: Multi-Agent AST Pattern Analyzer & Auto-Refactorer

## 1. Project Overview

**Objective:** Develop an autonomous, end-to-end Python code analysis and refactoring tool. The system will statically analyze codebases to detect architectural anti-patterns using Abstract Syntax Trees (AST). Upon detection, a multi-agent LLM system will autonomously refactor the code, write unit tests to verify the refactor, and safely execute the tests in a sandboxed environment before accepting the changes.

**Key Features:**
-   **Automated Code Smell Detection:** Identify common anti-patterns in Python code using AST analysis.
-   **LLM-Powered Refactoring:** Utilize large language models to generate improved, refactored code.
-   **Automated Test Generation:** LLMs will create `pytest` compatible unit tests for the refactored code.
-   **Sandboxed Validation:** Execute generated tests in an isolated environment to ensure correctness and prevent regressions.
-   **Feedback Loop:** If tests fail, the system will attempt to iterate on the refactoring.
-   **CLI Interface:** A user-friendly command-line tool to initiate scans and manage refactoring.
-   **Reporting:** Generate clear reports on detected smells, proposed refactors, and validation results.

## 2. System Architecture

The system is designed with a modular architecture, divided into three primary pipelines:

1.  **Static Analysis Engine:**
    -   **Purpose:** Parses raw Python files into Abstract Syntax Trees (ASTs).
    -   **Functionality:** Identifies predefined "code smells" (e.g., excessive function arguments, deep nesting, bare `except` clauses).
    -   **Output:** Extracts the problematic code context into structured `CodeSmell` data objects.

2.  **Agent Orchestration Layer:**
    -   **Purpose:** Manages the interaction and workflow between various AI agents.
    -   **Framework:** Utilizes LangChain (or LangGraph for more complex, cyclic agent workflows).
    -   **Agents:**
        -   **Refactor Agent:** Takes a `CodeSmell` object and generates a `RefactorProposal` (refactored code, explanation, new imports) using an LLM with structured outputs.
        -   **Test Agent:** Takes the `RefactorProposal` and generates a `TestCaseProposal` (pytest code) using an LLM with structured outputs.
        -   **Reviewer Agent (Future):** An optional agent to review refactors or test cases before execution.

3.  **Sandbox Validation Engine:**
    -   **Purpose:** Safely executes the refactored code and its generated tests.
    -   **Mechanism:** Dynamically writes the refactored code and tests to an isolated environment (initially a temporary directory, later potentially a Docker container).
    -   **Validation:** Runs `pytest` against the generated files and captures the results.
    -   **Feedback:** Provides test results back to the Agent Orchestration Layer to inform further refactoring attempts if tests fail.

## 3. Technology Stack & Dependencies

### Programming Language
-   **Python 3.10+**: The primary language for the entire project.

### Core Application & LLM Framework
-   **`langchain`**: For building and orchestrating the agentic workflows, managing LLM interactions, and creating chains.
-   **`pydantic`**: Essential for data validation and defining structured outputs for the LLMs, ensuring agents return data in a predictable format.

### LLM Provider Integrations
-   **`langchain-openai`**: Specific package for interacting with OpenAI models (e.g., GPT-4, GPT-3.5-turbo) as our primary LLM backend.
-   **`python-dotenv`**: To securely load API keys and other environment variables from a `.env` file, keeping sensitive information out of the codebase.

### Static Analysis
-   **Built-in Python `ast` module**: For parsing Python source code into Abstract Syntax Trees, enabling structural analysis.

### Command-Line Interface (CLI)
-   **`typer`**: For creating a user-friendly and robust command-line interface, allowing easy interaction with the tool (e.g., `refactor scan ./my_project --auto-fix`).

### Sandbox & Testing
-   **`pytest`**: The testing framework we will use to validate the refactored code. The Test Agent will generate `pytest` compatible tests.
-   **`docker` (Python SDK)**: For a more secure and isolated sandbox environment in later phases. This allows running generated code in containers, preventing unintended side effects on the host system.

### Development & Utility
-   **`black`**: Code formatter for consistent code style.
-   **`flake8`**: Linter for identifying stylistic and programmatic errors.
-   **`mypy`**: Static type checker for ensuring type correctness.

## 4. Proposed Directory Structure

```
ast_agent_refactorer/
├── core/
│   ├── __init__.py
│   ├── parser.py          # AST NodeVisitor implementation for code smell detection
│   ├── schemas.py         # Pydantic models (CodeSmell, RefactorProposal, etc.)
│   └── sandbox.py         # Secure code execution and pytest runner
├── agents/
│   ├── __init__.py
│   ├── orchestrator.py    # Manages the agent workflow (LangGraph/LangChain)
│   ├── refactor_agent.py  # LLM prompts and chains for code rewriting
│   └── test_agent.py      # LLM prompts and chains for pytest generation
├── cli/
│   ├── __init__.py
│   └── main.py            # Command Line Interface entry point
├── tests/
│   ├── test_parser.py     # Unit tests for the AST parser
│   ├── test_agents.py     # Unit tests for agent interactions
│   └── test_sandbox.py    # Unit tests for the sandbox execution
├── .env                   # Environment variables (e.g., API keys)
├── pyproject.toml         # Project configuration (e.g., for Black, Flake8)
├── requirements.txt       # Python package dependencies (minimal list)
├── PROJECT_DETAILS.md     # This document
└── README.md              # High-level project description and usage
```

## 5. Development Roadmap (Phased Approach)

### Phase 1: Foundation & Static Analysis (Estimated: 3 Days)
-   **Goal:** Establish project structure and a robust AST-based code smell detection.
-   **Tasks:**
    -   Set up the repository structure and initial virtual environment.
    -   Implement `core/schemas.py` with `CodeSmell`, `RefactorProposal`, `TestCaseProposal` Pydantic models.
    -   Implement `core/parser.py` with `AntiPatternVisitor` to detect 3-5 distinct anti-patterns (e.g., excessive arguments, deep nesting, bare `except`).
    -   Create basic unit tests for `parser.py` in `tests/test_parser.py`.
-   **Milestone:** A CLI command (using a placeholder `cli/main.py`) that can scan a given Python file and print structured JSON of all detected `CodeSmell` objects.

### Phase 2: Agent Orchestration (Estimated: 4 Days)
-   **Goal:** Integrate LLMs to perform refactoring and test generation.
-   **Tasks:**
    -   Configure LLM provider integration (OpenAI API) and `python-dotenv` for API key management.
    -   Develop `agents/refactor_agent.py`: Create LangChain prompts and chains that take a `CodeSmell` and output a `RefactorProposal` (enforcing Pydantic schema).
    -   Develop `agents/test_agent.py`: Create LangChain prompts and chains that take a `RefactorProposal` (specifically the `refactored_code`) and output a `TestCaseProposal`.
    -   Implement `agents/orchestrator.py` to sequence these agents.
-   **Milestone:** The system can take a problematic code snippet, generate a refactored version, and generate corresponding pytest code, without actual execution.

### Phase 3: Sandbox Validation & Feedback Loop (Estimated: 4 Days)
-   **Goal:** Safely execute generated code and tests, and enable iterative improvements.
-   **Tasks:**
    -   Implement `core/sandbox.py`: Functions to create isolated temporary directories, write refactored code and tests, and execute `pytest` via `subprocess`.
    -   Capture `pytest` output (stdout, stderr, exit code).
    -   Integrate the sandbox into the `orchestrator.py` workflow.
    -   Implement the **Feedback Loop**: If `pytest` fails, feed the error trace and original `CodeSmell` back to the Refactor Agent for a retry (with a defined maximum retry limit).
-   **Milestone:** Autonomous, validated code modification where the system can attempt refactors, run tests, and retry if tests fail.

### Phase 4: CLI Polish & Reporting (Estimated: 3 Days)
-   **Goal:** Create a user-friendly CLI and comprehensive reporting.
-   **Tasks:**
    -   Finalize `cli/main.py` using `typer` to provide commands like `ast-refactor scan <path>` and `ast-refactor fix <path>`.
    -   Implement robust error handling and logging throughout the application.
    -   Develop a reporting module to generate a summary of changes, diffs, and test results (e.g., in Markdown or HTML format).
    -   Add configuration options (e.g., LLM model choice, max retries, anti-pattern thresholds).
-   **Milestone:** A fully functional command-line tool that can scan, auto-fix with validation, and report on changes.

## 6. Future Considerations (V2 & Beyond)
-   **Advanced AST Modification:** Explore using `libcst` or similar libraries for more robust AST manipulation, allowing for precise in-place refactoring without relying solely on string replacement.
-   **Enhanced Security Sandboxing:** Fully integrate the `docker` Python SDK to run code execution in isolated containers, providing stronger security guarantees.
-   **Custom Anti-Pattern Rules:** Allow users to define their own anti-pattern detection rules.
-   **Multi-File Refactoring:** Extend agents to understand and refactor code across multiple interdependent files.
-   **Integration with CI/CD:** Develop hooks for integration into existing CI/CD pipelines.
-   **Different LLM Backends:** Support for other LLM providers (e.g., Google Gemini, Anthropic Claude) or local LLMs (e.g., via Ollama).
-   **UI/Dashboard:** A web-based interface for visualizing code smells, refactoring proposals, and progress.

---
