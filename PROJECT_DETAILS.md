# Project Details: Multi-Agent AST Pattern Analyzer & Auto-Refactorer

## 0. Status: Feature-complete (v1), deployed

All four roadmap phases below are implemented, dependency-installable
(`requirements.txt` / `pyproject.toml`), and covered by an automated test
suite (`tests/`, run in CI via `.github/workflows/ci.yml`). The `scan`
command, the sandbox, and the Gradio UI have been exercised directly
(not just read) to confirm they run without crashing. The `fix` command
**has** since been exercised end-to-end against a real LLM (Groq, via
`agents/llm_factory.py`) in addition to the mocked-LLM coverage in
`tests/test_agents.py` and `tests/test_orchestrator.py`. The app is also
deployed as a public Hugging Face Space (Gradio SDK, ZeroGPU-compatible
startup check in `app.py`).

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
    -   **Functionality:** Identifies predefined "code smells" (e.g., excessive function arguments, deep
        nesting, bare `except` clauses, a heuristic "potential infinite loop" check). Each smell carries a
        deterministic, AST-derived `reason` string and is classified into a severity (`core/severity.py`:
        Critical/High/Medium/Low) used to sort the smells list most-severe-first before refactoring.
    -   **Output:** Extracts the problematic code context into structured `CodeSmell` data objects.
    -   **Metrics:** `core/metrics.py` independently computes deterministic AST metrics (cyclomatic
        complexity, max nesting depth, function/argument counts, LOC, etc.) for a before/after comparison
        table in every report — not tied to smell detection, just a structural snapshot of the file.

2.  **Agent Orchestration Layer:**
    -   **Purpose:** Manages the interaction and workflow between various AI agents.
    -   **Framework:** Utilizes LangGraph (`agents/orchestrator.py`'s `StateGraph`) for the cyclic
        refactor/retry workflow.
    -   **Agents:**
        -   **Refactor Agent:** Takes all `CodeSmell`s detected in a file (severity-sorted) and generates a
            single `RefactorProposal` (refactored code, explanation, new imports) addressing every issue in
            that file at once ("unified refactoring" — see section 6), using an LLM with structured outputs.
        -   **Test Agent:** Takes the `RefactorProposal` and generates a `TestCaseProposal` (pytest code) using an LLM with structured outputs.
        -   **Reviewer Agent:** An LLM gatekeeper that approves/rejects a refactor+test pair before it ever reaches the sandbox.
    -   **LLM Backends:** `agents/llm_factory.py` builds the chat model per `config.json`'s `llm_backend`
        (OpenAI, Ollama, or Groq — Groq needs `method="function_calling"` for structured output since its
        strict `json_schema` mode rejects some models).

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
-   **`langchain-openai`**: Interacts with OpenAI models, and also with Groq's OpenAI-compatible endpoint
    (`agents/llm_factory.py` points the same client at Groq's base URL when configured).
-   **`langchain-ollama`**: Optional local/self-hosted backend.
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
│   ├── parser.py          # AntiPatternVisitor: AST-based code smell detection (incl. reason text,
│   │                      # infinite-loop heuristic); delegates nesting-depth math to metrics.py
│   ├── metrics.py         # Deterministic AST metrics (complexity, nesting depth, LOC, etc.) for reports
│   ├── severity.py        # Issue-type -> severity (Critical/High/Medium/Low) lookup + sort key
│   ├── schemas.py         # Pydantic models (CodeSmell, RefactorProposal, TestCaseProposal)
│   └── sandbox.py         # Isolated pytest execution (subprocess, optional Docker)
├── agents/
│   ├── orchestrator.py    # LangGraph workflow: refactor -> test -> review -> sandbox,
│   │                      # with retry-on-failure, severity-sorted smells, and validated-result caching
│   ├── llm_factory.py     # Builds the chat model per config.json's llm_backend (OpenAI/Ollama/Groq)
│   ├── refactor_agent.py  # LLM chain: CodeSmell(s) -> RefactorProposal
│   ├── test_agent.py      # LLM chain: RefactorProposal -> TestCaseProposal
│   ├── reviewer_agent.py  # LLM gatekeeper: approves/rejects a refactor+test pair pre-sandbox
│   └── main.py            # Typer CLI entry point (`scan`, `fix --apply --report --docker`) +
│                           # shared report rendering (execution trace, metrics table, status label)
├── tests/
│   ├── test_parser.py       # Built-in + custom-rule smell detection, reason text, infinite-loop heuristic
│   ├── test_metrics.py      # core/metrics.py AST metrics
│   ├── test_severity.py     # core/severity.py lookup + sort order
│   ├── test_sandbox.py      # Real pytest execution in a temp dir (pass/fail/syntax-error cases)
│   ├── test_agents.py       # Prompt-wiring checks with the LLM mocked out
│   ├── test_llm_factory.py  # Per-provider chat model construction (OpenAI/Ollama/Groq)
│   ├── test_orchestrator.py # Full LangGraph flow with the LLM mocked out (incl. caching, retries, severity sort)
│   ├── test_reporting.py    # Shared report-rendering helpers (status_label, execution trace, metrics table)
│   ├── test_apply.py        # apply_validated_fixes: whole-file write of the validated unified refactor
│   └── test_app.py          # Gradio app.py: run_analysis/save_config, HF-Space gating, session cache scoping
├── app.py                 # Gradio UI (deployed as a Hugging Face Space; ZeroGPU startup no-op)
├── .github/workflows/ci.yml  # Installs requirements.txt and runs pytest on push/PR
├── .env                   # Environment variables (e.g., API keys) — gitignored, not committed
├── config.json             # Default anti-pattern rule configuration + llm_backend selection
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
    `difflib`, whole-file refactor application (`--apply` writes the validated unified refactor directly --
    see the "Unified Refactoring" note below), and a `pyproject.toml` `[project.scripts]` entry
    (`ast-refactor`) for installed use.

## 6. Already Delivered Beyond the Original Roadmap
These were listed as "V2 & Beyond" ideas but are implemented in v1:
-   **Unified Per-File Refactoring** — each file gets exactly one consolidated refactor addressing every
    smell detected in it, rather than one independent refactor per smell. This eliminates the overlapping-edit
    conflicts the original per-smell design was prone to (and the libcst-based `RefactorTransformer` that used
    to paper over them was removed as a result -- `--apply` is now a direct whole-file write of the validated
    refactor).
-   **Enhanced Security Sandboxing** — `core/sandbox.py` already supports a Docker-isolated sandbox
    (`--docker` CLI flag / "Use Docker Sandbox" in the UI; forced off automatically on Hugging Face Spaces,
    which have no Docker daemon).
-   **UI/Dashboard** — `app.py` is a working Gradio UI (paste/upload code, edit config, view results),
    deployed as a public Hugging Face Space. Per-visitor state (config edits, cached results) is scoped to
    the Gradio session hash so one visitor's data is never served to another.
-   **Basic CI** — `.github/workflows/ci.yml` runs the test suite on every push/PR (though it doesn't yet
    run the tool's own `scan`/`fix` against itself — see below).
-   **Additional LLM Backend (Groq)** — `agents/llm_factory.py` supports Groq (OpenAI-compatible endpoint)
    as a free-tier alternative to OpenAI, in addition to Ollama.
-   **Severity Levels, Reasons & AST Metrics** — every `CodeSmell` now carries a deterministic `reason`
    string (`core/parser.py`) and a severity classification (`core/severity.py`) used to sort the smells
    list most-severe-first before refactoring. Every report includes a before/after AST metrics table
    (`core/metrics.py`) and a step-by-step agent execution trace (`agents/main.py:build_execution_trace`).
-   **Potential-Infinite-Loop Heuristic** — `core/parser.py`'s `visit_While` flags `while` loops whose
    condition variable is never unconditionally updated in the loop body. This is a best-effort heuristic,
    not a soundness guarantee (loop termination is undecidable in general per Rice's theorem), and is always
    reported as "Potential", never asserted as fact.

## 7. Genuinely Open (V2 & Beyond)
-   **Custom Anti-Pattern Rules:** `config.json` already supports user-defined `Call`/`Import`/`Decorator`
    rules; adding entirely new rule *categories* (beyond those three) still requires editing `core/parser.py`.
-   **Multi-File Refactoring:** Agents still operate on one file at a time (unified across smells within
    that file); no cross-file awareness.
-   **Deeper CI/CD Integration:** Running the refactor bot itself (not just its test suite) as a PR check.
-   **Additional LLM Backends:** Google Gemini / Anthropic Claude are not wired up (OpenAI, Ollama, and Groq
    only).

---
