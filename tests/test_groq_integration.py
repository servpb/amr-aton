"""Comprehensive test suite for Groq API integration and tools."""
import json
import pytest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

from src.integrations.groq_client import (
    DEFAULT_GROQ_MODEL,
    FAST_GROQ_MODEL,
    GroqClient,
    get_groq_client,
)
from src.tools.groq_service import (
    GROQ_FUNCTION_DECLARATIONS,
    check_groq_connection,
    dispatch_groq_tool,
    query_groq_llm,
)
from src.tools import ALL_ATON_TOOLS, dispatch_tool


def test_groq_client_init_disabled_without_key():
    client = GroqClient(api_key="", enabled=True)
    assert client.enabled is False
    res = client.chat([{"role": "user", "content": "olá"}])
    assert res["status"] == "disabled"


def test_groq_client_chat_success(monkeypatch):
    def fake_post(key, payload, timeout):
        assert key == "gsk_test123"
        assert payload["model"] == DEFAULT_GROQ_MODEL
        assert payload["messages"][0]["content"] == "teste"
        return {
            "model": DEFAULT_GROQ_MODEL,
            "choices": [{"message": {"content": "Olá do Groq!"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 4, "total_tokens": 9},
        }

    monkeypatch.setattr("src.integrations.groq_client._post", fake_post)
    client = GroqClient(api_key="gsk_test123", enabled=True)
    res = client.chat([{"role": "user", "content": "teste"}])

    assert res["status"] == "success"
    assert res["content"] == "Olá do Groq!"
    assert res["model"] == DEFAULT_GROQ_MODEL
    assert res["usage"]["total_tokens"] == 9
    assert "elapsed_ms" in res


def test_groq_client_ask_helper(monkeypatch):
    def fake_post(key, payload, timeout):
        return {
            "model": FAST_GROQ_MODEL,
            "choices": [{"message": {"content": "Resposta rápida"}, "finish_reason": "stop"}],
            "usage": {},
        }

    monkeypatch.setattr("src.integrations.groq_client._post", fake_post)
    client = GroqClient(api_key="gsk_test123", enabled=True)
    answer = client.ask("Pergunta", system_prompt="Instrução", model=FAST_GROQ_MODEL)
    assert answer == "Resposta rápida"


def test_groq_client_rate_limit_429(monkeypatch):
    def fake_post(key, payload, timeout):
        raise HTTPError("url", 429, "Too Many Requests", {"Retry-After": "45"}, None)

    monkeypatch.setattr("src.integrations.groq_client._post", fake_post)
    client = GroqClient(api_key="gsk_test123", enabled=True)
    res = client.chat([{"role": "user", "content": "teste"}])

    assert res["status"] == "rate_limited"
    assert res["retry_after_seconds"] == 60  # mínimo 60s
    assert "rate limit" in res["error"].lower()

    # Próxima chamada imediata deve entrar em cooldown
    res_cooldown = client.chat([{"role": "user", "content": "teste 2"}])
    assert res_cooldown["status"] == "cooldown"


def test_groq_client_auth_failed_401(monkeypatch):
    def fake_post(key, payload, timeout):
        raise HTTPError("url", 401, "Unauthorized", {}, None)

    monkeypatch.setattr("src.integrations.groq_client._post", fake_post)
    client = GroqClient(api_key="gsk_invalid", enabled=True)
    res = client.chat([{"role": "user", "content": "teste"}])

    assert res["status"] == "authentication_failed"
    assert res["code"] == 401


def test_groq_client_network_timeout(monkeypatch):
    def fake_post(key, payload, timeout):
        raise TimeoutError("Socket timeout")

    monkeypatch.setattr("src.integrations.groq_client._post", fake_post)
    client = GroqClient(api_key="gsk_test123", enabled=True)
    res = client.chat([{"role": "user", "content": "teste"}])

    assert res["status"] == "timeout"


def test_query_groq_llm_tool(monkeypatch):
    def fake_post(key, payload, timeout):
        return {
            "model": "llama-3.3-70b-versatile",
            "choices": [{"message": {"content": "Resultado do processamento"}, "finish_reason": "stop"}],
            "usage": {"total_tokens": 15},
        }

    monkeypatch.setattr("src.integrations.groq_client._post", fake_post)
    client = get_groq_client()
    client._key = "gsk_test"
    client.enabled = True

    res = query_groq_llm(prompt="Resuma este texto")
    assert res["status"] == "success"
    assert res["content"] == "Resultado do processamento"


def test_check_groq_connection_tool(monkeypatch):
    def fake_post(key, payload, timeout):
        return {
            "model": FAST_GROQ_MODEL,
            "choices": [{"message": {"content": "OK"}, "finish_reason": "stop"}],
            "usage": {},
        }

    monkeypatch.setattr("src.integrations.groq_client._post", fake_post)
    client = get_groq_client()
    client._key = "gsk_test"
    client.enabled = True

    res = check_groq_connection()
    assert res["status"] == "connected"
    assert "ativa e operacional" in res["message"]


def test_dispatch_groq_tool():
    res = dispatch_groq_tool("unknown_tool", {})
    assert res["status"] == "unknown_tool"


def test_all_aton_tools_includes_groq():
    tool_names = [t["name"] for t in ALL_ATON_TOOLS]
    assert "query_groq_llm" in tool_names
    assert "check_groq_connection" in tool_names


def test_unified_dispatch_tool_groq(monkeypatch):
    def fake_post(key, payload, timeout):
        return {
            "model": FAST_GROQ_MODEL,
            "choices": [{"message": {"content": "OK"}, "finish_reason": "stop"}],
            "usage": {},
        }

    monkeypatch.setattr("src.integrations.groq_client._post", fake_post)
    client = get_groq_client()
    client._key = "gsk_test"
    client.enabled = True

    res = dispatch_tool("check_groq_connection", {})
    assert res["status"] == "connected"

