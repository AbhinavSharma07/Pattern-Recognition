# Project Details: Multi-Agent AST Pattern Analyzer & Auto-Refactorer

## 0. Status: Feature-complete (v1)

All four roadmap phases below are implemented, dependency-installable
(`requirements.txt` / `pyproject.toml`), and covered by an automated test
suite (`tests/`, run in CI via `.github/workflows/ci.yml`). The `scan`
command, the sandbox, and the Gradio UI have been exercised directly
(not just read) to confirm they run without crashing. The one thing that
has **not** been exercised end-to-end is the `fix` command against a real
LLM — that requires a live `OPENAI_API_KEY` and real API spend, and was
instead verified by mocking the LLM calls in `tests/test_agents.py` and
`tests/test_orchestrator.py` to confirm the LangChain/LangGraph wiring
(prompt variables, structured-output schemas, retry/cache logic) is correct.

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

## 4. Actual Directory Structure

`core` and `agents` are namespace packages (no `__init__.py` needed on
Python 3.10+). There is no separate `cli/` package — the Typer CLI lives in
`agents/main.py` alongside the agent code it calls.

```
Pattern-Recognition/
├── core/
│   ├── parser.py          # AntiPatternVisitor: AST-based code smell detection
│   ├── schemas.py         # Pydantic models (CodeSmell, RefactorProposal, TestCaseProposal)
│   └── sandbox.py         # Isolated pytest execution (subprocess, optional Docker)
├── agents/
│   ├── orchestrator.py    # LangGraph workflow: refactor -> test -> review -> sandbox,
│   │                      # with retry-on-failure and validated-result caching
│   ├── refactor_agent.py  # LLM chain: CodeSmell -> RefactorProposal
│   ├── test_agent.py      # LLM chain: RefactorProposal -> TestCaseProposal
│   ├── reviewer_agent.py  # LLM gatekeeper: approves/rejects a refactor+test pair pre-sandbox
│   └── main.py            # Typer CLI entry point (`scan`, `fix --apply --report --docker`)
├── tests/
│   ├── test_parser.py       # Built-in + custom-rule smell detection
│   ├── test_sandbox.py      # Real pytest execution in a temp dir (pass/fail/syntax-error cases)
│   ├── test_agents.py       # Prompt-wiring checks with the LLM mocked out
│   └── test_orchestrator.py # Full LangGraph flow with the LLM mocked out (incl. caching, retries)
├── app.py                 # Gradio UI (deployable as a Hugging Face Space)
├── .github/workflows/ci.yml  # Installs requirements.txt and runs pytest on push/PR
├── .env                   # Environment variables (e.g., API keys) — gitignored, not committed
├── config.json             # Default anti-pattern rule configuration
├── pyproject.toml          # Project metadata, dependencies, [project.scripts], tool config
├── requirements.txt         # Pinned dependency list for `pip install -r`
├── PROJECT_DETAILS.md       # This document
└── README.md                # High-level project description and usage
```

## 5. Development Roadmap (Phased Approach)

### Phase 1: Foundation & Static Analysis — ✅ Complete
-   **Goal:** Establish project structure and a robust AST-based code smell detection.
-   Delivered: `core/schemas.py` (`CodeSmell`, `RefactorProposal`, `TestCaseProposal`); `core/parser.py`'s
    `AntiPatternVisitor` detects long functions, too-many-arguments, bare/generic `except`, excessive
    nesting depth, complex list comprehensions, and user-defined custom rules (`Call`/`Import`/`Decorator`
    matchers from `config.json`); `tests/test_parser.py` covers all of the above.
-   **Milestone met via:** `agents/main.py scan <path>` (not the originally-planned `cli/main.py` — the CLI
    ended up living alongside the agents it calls).

### Phase 2: Agent Orchestration — ✅ Complete
-   **Goal:** Integrate LLMs to perform refactoring and test generation.
-   Delivered: `agents/refactor_agent.py` and `agents/test_agent.py` as planned, plus an unplanned addition —
    `agents/reviewer_agent.py`, an LLM gatekeeper that approves/rejects a refactor+test pair before it ever
    reaches the sandbox. `agents/orchestrator.py` sequences all of it as a LangGraph `StateGraph`.
    Both OpenAI and (optional) Ollama backends are supported via `config.json`'s `llm_backend`.
-   **Verification:** `tests/test_agents.py` and `tests/test_orchestrator.py` exercise the real LangChain
    prompt templates and LangGraph control flow with the LLM call itself mocked out.

### Phase 3: Sandbox Validation & Feedback Loop — ✅ Complete
-   **Goal:** Safely execute generated code and tests, and enable iterative improvements.
-   Delivered: `core/sandbox.py` runs generated code + pytest in a temp dir via `subprocess` (with a hard
    timeout), or optionally inside a `python:3.10-slim` Docker container via the `docker` SDK. The
    orchestrator's `retries_left` loop feeds sandbox/reviewer failures back to the Refactor Agent.
-   **Verification:** `tests/test_sandbox.py` runs real pytest subprocesses (pass, fail, and syntax-error
    cases); `tests/test_orchestrator.py::test_process_codebase_retries_then_gives_up` exercises the retry path.

### Phase 4: CLI Polish & Reporting — ✅ Complete
-   **Goal:** Create a user-friendly CLI and comprehensive reporting.
-   Delivered: `agents/main.py` (`scan`, `fix --apply --report --docker --config`), Markdown diff reports via
    `difflib`, `libcst`-based in-place refactor application (falls back to string replacement if libcst fails
    to parse), and a `pyproject.toml` `[project.scripts]` entry (`ast-refactor`) for installed use.

## 6. Already Delivered Beyond the Original Roadmap
These were listed as "V2 & Beyond" ideas but are implemented in v1:
-   **Advanced AST Modification** — `agents/main.py`'s `RefactorTransformer` uses `libcst` for in-place
    refactor application.
-   **Enhanced Security Sandboxing** — `core/sandbox.py` already supports a Docker-isolated sandbox
    (`--docker` CLI flag / "Use Docker Sandbox" in the UI).
-   **UI/Dashboard** — `app.py` is a working Gradio UI (paste/upload code, edit config, view results), deployable directly as a Hugging Face Space.
-   **Basic CI** — `.github/workflows/ci.yml` runs the test suite on every push/PR (though it doesn't yet
    run the tool's own `scan`/`fix` against itself — see below).

## 7. Genuinely Open (V2 & Beyond)
-   **Custom Anti-Pattern Rules:** `config.json` already supports user-defined `Call`/`Import`/`Decorator`
    rules; adding entirely new rule *categories* (beyond those three) still requires editing `core/parser.py`.
-   **Multi-File Refactoring:** Agents still operate on one smell/file at a time; no cross-file awareness.
-   **Deeper CI/CD Integration:** Running the refactor bot itself (not just its test suite) as a PR check.
-   **Additional LLM Backends:** Google Gemini / Anthropic Claude are not wired up (OpenAI + Ollama only).
-   **Live end-to-end verification:** The `fix` command has never been run against a real LLM in this
    project's history — only with the LLM mocked. Recommended before relying on it in production.

---
