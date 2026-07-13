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


def build_chat_llm(config: Dict[str, Any] = None):
    """
    Builds the chat LLM configured under config['llm_backend'].

    provider="openai" -> ChatOpenAI (requires OPENAI_API_KEY).
    provider="ollama"  -> ChatOllama, talking to a local server by default
                          (http://localhost:11434, no auth), or to Ollama's
                          hosted cloud API (https://ollama.com) if an
                          OLLAMA_API_KEY environment variable is set.
    """
    config = config or {}
    llm_config = config.get("llm_backend", {"provider": "openai", "model": "gpt-4o-mini"})

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
