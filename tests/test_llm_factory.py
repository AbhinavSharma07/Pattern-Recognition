import pytest
from langchain_openai import ChatOpenAI

from agents import llm_factory


def test_groq_missing_api_key_raises(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        llm_factory.build_chat_llm({"llm_backend": {"provider": "groq", "model": "llama-3.3-70b-versatile"}})


def test_groq_builds_chat_openai_pointed_at_groq_endpoint(monkeypatch):
    monkeypatch.setenv("", "test-key")

    llm = llm_factory.build_chat_llm({"llm_backend": {"provider": "groq", "model": "llama-3.3-70b-versatile"}})

    assert isinstance(llm, ChatOpenAI)
    assert str(llm.openai_api_base) == llm_factory.GROQ_BASE_URL


def test_default_provider_is_openai(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    llm = llm_factory.build_chat_llm({})

    assert isinstance(llm, ChatOpenAI)
    assert llm.model_name == "gpt-4o-mini"


class _FakeLLM:
    """Captures the kwargs with_structured_output was called with."""
    def __init__(self):
        self.calls = []

    def with_structured_output(self, schema, **kwargs):
        self.calls.append((schema, kwargs))
        return "structured-llm"


def test_groq_structured_output_uses_function_calling(monkeypatch):
    fake_llm = _FakeLLM()
    monkeypatch.setattr(llm_factory, "build_chat_llm", lambda config: fake_llm)

    result = llm_factory.build_structured_llm({"llm_backend": {"provider": "groq"}}, dict)

    assert result == "structured-llm"
    assert fake_llm.calls == [(dict, {"method": "function_calling"})]


def test_openai_structured_output_uses_default_method(monkeypatch):
    fake_llm = _FakeLLM()
    monkeypatch.setattr(llm_factory, "build_chat_llm", lambda config: fake_llm)

    llm_factory.build_structured_llm({}, dict)

    assert fake_llm.calls == [(dict, {})]
