import os
from typing import Any, Dict

from langchain_openai import ChatOpenAI

try:
    from langchain_ollama import ChatOllama
except ImportError:
    try:
        from langchain_community.chat_models import ChatOllama
    except ImportError:
        ChatOllama = None

OLLAMA_CLOUD_BASE_URL = "https://ollama.com"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"


def build_chat_llm(config: Dict[str, Any] = None):
    """
    Builds the chat LLM configured under config['llm_backend'].

    provider="openai" -> ChatOpenAI (requires OPENAI_API_KEY).
    provider="ollama"  -> ChatOllama, talking to a local server by default
                          (http://localhost:11434, no auth), or to Ollama's
                          hosted cloud API (https://ollama.com) if an
                          OLLAMA_API_KEY environment variable is set.
    provider="groq"    -> ChatOpenAI pointed at Groq's OpenAI-compatible
                          endpoint (requires GROQ_API_KEY). Groq designed
                          their API to be a drop-in OpenAI-client target,
                          so no dedicated client library is needed. Default
                          model is "openai/gpt-oss-120b": confirmed live to
                          complete refactor -> test -> review -> sandbox
                          successfully, unlike llama-3.3-70b-versatile
                          (rejects strict json_schema outright) and
                          gpt-oss-20b (unreliable tool-calling specifically
                          for the test-generation step).
    """
    config = config or {}
    llm_config = config.get("llm_backend", {"provider": "openai", "model": "gpt-4o-mini"})

    if llm_config.get("provider") == "groq":
        groq_api_key = os.getenv("GROQ_API_KEY")
        if not groq_api_key:
            raise RuntimeError("Groq support requires a GROQ_API_KEY environment variable.")

        return ChatOpenAI(
            model=llm_config.get("model", "openai/gpt-oss-120b"),
            temperature=0.1,
            api_key=groq_api_key,
            base_url=llm_config.get("base_url", GROQ_BASE_URL),
        )

    if llm_config.get("provider") == "ollama":
        if ChatOllama is None:
            raise RuntimeError(
                "Ollama support requires the 'langchain-ollama' package. Install it with: pip install langchain-ollama"
            )

        ollama_api_key = os.getenv("OLLAMA_API_KEY")
        base_url = llm_config.get("base_url")
        client_kwargs = {}

        if ollama_api_key:
            # Route to Ollama's hosted cloud API unless a different base_url was
            # explicitly configured (e.g. a self-hosted cloud-compatible server).
            base_url = base_url or OLLAMA_CLOUD_BASE_URL
            client_kwargs["headers"] = {"Authorization": f"Bearer {ollama_api_key}"}

        return ChatOllama(
            model=llm_config.get("model", "llama3"),
            temperature=0.1,
            base_url=base_url,
            client_kwargs=client_kwargs,
        )

    return ChatOpenAI(model=llm_config.get("model", "gpt-4o-mini"), temperature=0.1)


def build_structured_llm(config: Dict[str, Any], schema):
    """
    Builds the configured chat LLM and applies structured-output enforcement,
    picking whichever request method is most reliable for the provider.

    Groq's strict json_schema mode has been observed (live) to reject outputs
    containing a multi-line string field (e.g. generated pytest code) with a
    'json_validate_failed' error even though the same schema works fine for
    simpler fields; function-calling handles multi-line string arguments more
    robustly there, so it's used instead for provider="groq".
    """
    config = config or {}
    llm_config = config.get("llm_backend", {"provider": "openai", "model": "gpt-4o-mini"})
    llm = build_chat_llm(config)

    if llm_config.get("provider") == "groq":
        return llm.with_structured_output(schema, method="function_calling")
    return llm.with_structured_output(schema)
