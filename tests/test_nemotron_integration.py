"""Comprehensive tests for OpenRouter and NVIDIA Nemotron integration."""
import json
import pytest
from unittest.mock import MagicMock
from urllib.error import HTTPError, URLError

from src.integrations.openrouter_client import (
    DEFAULT_NEMOTRON_MODEL,
    OpenRouterClient,
    get_openrouter_client,
)
from src.tools.nemotron_service import (
    NEMOTRON_FUNCTION_DECLARATIONS,
    check_nemotron_connection,
    consultar_nemotron,
    dispatch_nemotron_tool,
    planejar_tarefa_complexa,
)
from src.tools import ALL_ATON_TOOLS, dispatch_tool


def test_openrouter_client_disabled_without_key():
    client = OpenRouterClient(api_key="", enabled=True)
    assert client.enabled is False
    res = client.chat([{"role": "user", "content": "olá"}])
    assert res["status"] == "disabled"


def test_openrouter_strict_free_tier_enforcement():
    client = OpenRouterClient(api_key="sk-or-test", enabled=True, strict_free_tier=True)
    res = client.chat([{"role": "user", "content": "olá"}], model="openai/gpt-4o")
    assert res["status"] == "policy_blocked"
    assert "only free models" in res["error"]


def test_nvidia_nim_direct_routing(monkeypatch):
    captured = {}

    def fake_post_api(endpoint, key, payload, timeout):
        captured["endpoint"] = endpoint
        captured["key"] = key
        captured["model"] = payload["model"]
        return {
            "model": "nvidia/llama-3.1-nemotron-70b-instruct",
            "choices": [{"message": {"content": "Resposta NIM H100"}, "finish_reason": "stop"}],
            "usage": {"total_tokens": 12},
        }

    monkeypatch.setattr("src.integrations.openrouter_client._post_api", fake_post_api)
    client = OpenRouterClient(api_key="nvapi-test12345", enabled=True)
    assert client.provider == "nvidia_nim"
    assert "nvidia.com" in client.endpoint

    res = client.chat([{"role": "user", "content": "teste nim"}])
    assert res["status"] == "success"
    assert res["provider"] == "nvidia_nim"
    assert "integrate.api.nvidia.com" in captured["endpoint"]
    assert captured["key"] == "nvapi-test12345"
    assert captured["model"] == "nvidia/llama-3.1-nemotron-70b-instruct"


def test_openrouter_chat_success(monkeypatch):
    def fake_post(key, payload, timeout):
        assert key == "sk-or-test"
        assert payload["model"] == DEFAULT_NEMOTRON_MODEL
        return {
            "model": DEFAULT_NEMOTRON_MODEL,
            "choices": [{"message": {"content": "Plano gerado com sucesso."}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 8, "total_tokens": 18},
        }

    monkeypatch.setattr("src.integrations.openrouter_client._post_openrouter", fake_post)
    client = OpenRouterClient(api_key="sk-or-test", enabled=True)
    res = client.chat([{"role": "user", "content": "teste"}])

    assert res["status"] == "success"
    assert res["content"] == "Plano gerado com sucesso."
    assert res["model"] == DEFAULT_NEMOTRON_MODEL
    assert res["usage"]["total_tokens"] == 18


def test_openrouter_plan_task_structure(monkeypatch):
    captured_payload = {}

    def fake_post(key, payload, timeout):
        nonlocal captured_payload
        captured_payload = payload
        return {
            "model": DEFAULT_NEMOTRON_MODEL,
            "choices": [{"message": {"content": "Etapa 1: Preparar ambiente."}, "finish_reason": "stop"}],
            "usage": {"total_tokens": 25},
        }

    monkeypatch.setattr("src.integrations.openrouter_client._post_openrouter", fake_post)
    client = OpenRouterClient(api_key="sk-or-test", enabled=True)
    res = client.plan_task(
        objective="Criar backup seguro",
        constraints="Sem softwares pagos",
        context="Windows 11",
    )

    assert res["status"] == "success"
    assert res["content"] == "Etapa 1: Preparar ambiente."
    # Check that system prompt and structured objective were passed
    messages = captured_payload.get("messages", [])
    assert len(messages) == 2
    assert "NVIDIA Nemotron" in messages[0]["content"]
    assert "Criar backup seguro" in messages[1]["content"]
    assert "Sem softwares pagos" in messages[1]["content"]


def test_openrouter_rate_limit_429(monkeypatch):
    def fake_post(key, payload, timeout):
        raise HTTPError("url", 429, "Too Many Requests", {"Retry-After": "30"}, None)

    monkeypatch.setattr("src.integrations.openrouter_client._post_openrouter", fake_post)
    client = OpenRouterClient(api_key="sk-or-test", enabled=True)
    res = client.chat([{"role": "user", "content": "teste"}])

    assert res["status"] == "rate_limited"
    assert res["retry_after_seconds"] == 60  # mínimo 60s
    assert "rate limit" in res["error"].lower()

    # Cooldown imediato
    res_cd = client.chat([{"role": "user", "content": "teste 2"}])
    assert res_cd["status"] == "cooldown"


def test_openrouter_auth_error_401(monkeypatch):
    def fake_post(key, payload, timeout):
        raise HTTPError("url", 401, "Unauthorized", {}, None)

    monkeypatch.setattr("src.integrations.openrouter_client._post_openrouter", fake_post)
    client = OpenRouterClient(api_key="sk-or-invalid", enabled=True)
    res = client.chat([{"role": "user", "content": "teste"}])

    assert res["status"] == "authentication_failed"
    assert res["code"] == 401


def test_planejar_tarefa_complexa_tool(monkeypatch):
    def fake_post(key, payload, timeout):
        return {
            "model": DEFAULT_NEMOTRON_MODEL,
            "choices": [{"message": {"content": "Plano detalhado em 4 fases."}, "finish_reason": "stop"}],
            "usage": {"total_tokens": 50},
        }

    monkeypatch.setattr("src.integrations.openrouter_client._post_openrouter", fake_post)
    client = get_openrouter_client()
    client._key = "sk-or-test"
    client.enabled = True

    res = planejar_tarefa_complexa(objetivo="Automatizar backup do sistema")
    assert res["status"] == "success"
    assert res["plano"] == "Plano detalhado em 4 fases."


def test_check_nemotron_connection_tool(monkeypatch):
    def fake_post(key, payload, timeout):
        return {
            "model": DEFAULT_NEMOTRON_MODEL,
            "choices": [{"message": {"content": "OK"}, "finish_reason": "stop"}],
            "usage": {},
        }

    monkeypatch.setattr("src.integrations.openrouter_client._post_openrouter", fake_post)
    client = get_openrouter_client()
    client._key = "sk-or-test"
    client.enabled = True

    res = check_nemotron_connection()
    assert res["status"] == "connected"
    assert "NVIDIA Nemotron ativa" in res["message"]


def test_dispatch_nemotron_tool():
    res = dispatch_nemotron_tool("unknown_tool", {})
    assert res["status"] == "unknown_tool"


def test_all_aton_tools_includes_nemotron():
    tool_names = [t["name"] for t in ALL_ATON_TOOLS]
    assert "planejar_tarefa_complexa" in tool_names
    assert "consultar_nemotron" in tool_names
    assert "check_nemotron_connection" in tool_names


def test_unified_dispatch_tool_nemotron(monkeypatch):
    def fake_post(key, payload, timeout):
        return {
            "model": DEFAULT_NEMOTRON_MODEL,
            "choices": [{"message": {"content": "OK"}, "finish_reason": "stop"}],
            "usage": {},
        }

    monkeypatch.setattr("src.integrations.openrouter_client._post_openrouter", fake_post)
    client = get_openrouter_client()
    client._key = "sk-or-test"
    client.enabled = True

    res = dispatch_tool("check_nemotron_connection", {})
    assert res["status"] == "connected"

