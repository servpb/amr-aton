"""Groq LPU text connector with ultra-low latency inference and pilot compatibility."""
import json
import socket
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
import time
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "openai/gpt-oss-20b"

# Official supported Groq models for the account
DEFAULT_GROQ_MODEL = "openai/gpt-oss-20b"
FAST_GROQ_MODEL = "openai/gpt-oss-20b"
REASONING_GROQ_MODEL = "openai/gpt-oss-120b"
MULTILINGUAL_GROQ_MODEL = "qwen/qwen3.8-27b"
SUPPORTED_GROQ_MODELS = [
    "openai/gpt-oss-20b",
    "openai/gpt-oss-120b",
    "qwen/qwen3.8-27b",
    "whisper-large-v3",
    "whisper-large-v3-turbo",
]

CASES = {
    "open_browser": "Exemplo ficticio: abra o Chrome.",
    "volume": "Exemplo ficticio: ajuste o volume para 30 por cento.",
    "ambiguous": "Exemplo ficticio: abra aquele programa.",
}
EXPECTED = {
    "open_browser": {"action": "open_application", "application": "chrome"},
    "volume": {"action": "set_volume", "level": 30},
    "ambiguous": {"action": "clarify"},
}
INSTRUCTION = (
    "Classifique o exemplo ficticio. Nao execute nada. Responda apenas JSON: "
    '{"action":"open_application","application":"chrome"} ou '
    '{"action":"set_volume","level":30} ou {"action":"clarify"}. '
    "Se o pedido for ambiguo use clarify."
)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _post(key: str, payload: dict, timeout: float):
    request = Request(
        ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AtonAssistant/1.0",
        },
    )
    with build_opener(NoRedirect()).open(request, timeout=timeout) as response:
        raw = response.read(262145)
    if len(raw) > 262144:
        raise ValueError("oversized_response")
    return json.loads(raw.decode("utf-8"))


def validate_proposal(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    action = value.get("action")
    if action == "clarify":
        return set(value) == {"action"}
    if action == "open_application":
        return set(value) == {"action", "application"} and value["application"] == "chrome"
    if action == "set_volume":
        return (
            set(value) == {"action", "level"}
            and type(value["level"]) is int
            and 0 <= value["level"] <= 100
        )
    return False


class GroqPilotClient:
    """Only fixed synthetic cases can leave this boundary for the pilot."""

    def __init__(self, api_key: str, *, enabled: bool = False, free_plan_verified: bool = False, timeout: float = 12):
        self._key = api_key
        self.enabled = enabled
        self.free_plan_verified = free_plan_verified
        self.timeout = min(20, max(1, timeout))
        self._next_request = 0.0

    def run_case(self, case_id: str) -> Dict[str, Any]:
        if not self.enabled:
            return {"status": "disabled"}
        if not self.free_plan_verified:
            return {"status": "free_plan_not_verified"}
        if not self._key:
            return {"status": "missing_key"}
        if case_id not in CASES:
            return {"status": "unknown_synthetic_case"}
        if time.monotonic() < self._next_request:
            return {"status": "cooldown"}
        from src.core.router import DataClass, FreeEndpoint, ModelRouter, RouteRequest, TaskKind

        decision = ModelRouter(enabled=True, endpoints=(FreeEndpoint("groq", MODEL, True),)).route(
            RouteRequest(TaskKind.COMMAND, DataClass.SYNTHETIC)
        )
        if not decision.allowed:
            return {"status": "policy_blocked"}
        self._next_request = time.monotonic() + 3
        payload = {
            "model": decision.model,
            "max_completion_tokens": 512,
            "messages": [
                {"role": "system", "content": INSTRUCTION},
                {"role": "user", "content": CASES[case_id]},
            ],
        }
        started = time.monotonic()
        try:
            data = _post(self._key, payload, self.timeout)
            choice = data["choices"][0]
            if choice.get("finish_reason") != "stop":
                return {"status": "incomplete_response"}
            message = choice["message"]
            if message.get("tool_calls"):
                return {"status": "unexpected_tool_call"}
            proposal = json.loads(message["content"])
            if not validate_proposal(proposal):
                return {"status": "invalid_proposal"}
            return {
                "status": "ok",
                "proposal": proposal,
                "matches_expected": proposal == EXPECTED[case_id],
                "elapsed_ms": round((time.monotonic() - started) * 1000),
            }
        except HTTPError as exc:
            if exc.code == 429:
                delay = 60
                header = exc.headers.get("Retry-After", "") if exc.headers else ""
                try:
                    delay = max(60, int(header))
                except ValueError:
                    try:
                        date = parsedate_to_datetime(header)
                        delay = max(60, int((date - datetime.now(timezone.utc)).total_seconds()) + 1)
                    except (ValueError, TypeError, OverflowError):
                        pass
                self._next_request = time.monotonic() + delay
                return {"status": "rate_limited", "retry_after_seconds": delay}
            return {"status": "authentication_failed" if exc.code in (401, 403) else "provider_error"}
        except (TimeoutError, socket.timeout):
            return {"status": "timeout"}
        except URLError:
            return {"status": "network_error"}
        except (ValueError, KeyError, IndexError, TypeError):
            return {"status": "invalid_response"}


class GroqClient:
    """Production-grade client for Groq Chat Completions API with ultra-low latency LPU inference."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        default_model: str = DEFAULT_GROQ_MODEL,
        timeout: float = 15.0,
        enabled: bool = True,
    ):
        try:
            from src.config import settings
            configured_key = settings.groq_api_key
            configured_model = settings.groq_model
            configured_timeout = settings.groq_timeout_seconds
            configured_enabled = settings.groq_enabled
        except Exception:
            configured_key = ""
            configured_model = DEFAULT_GROQ_MODEL
            configured_timeout = 15.0
            configured_enabled = True

        if api_key is not None:
            self._key = api_key.strip()
        else:
            self._key = (configured_key or "").strip()
        self.default_model = default_model or configured_model or DEFAULT_GROQ_MODEL
        self.timeout = min(60.0, max(1.0, float(timeout or configured_timeout)))
        self.enabled = bool(enabled and configured_enabled and self._key)
        self._cooldown_until = 0.0

    def chat(
        self,
        messages: List[Dict[str, str]],
        *,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        json_mode: bool = False,
    ) -> Dict[str, Any]:
        """Send a chat completion request to Groq API."""
        if not self.enabled:
            return {"status": "disabled", "error": "Groq client is disabled or missing API key."}
        if time.monotonic() < self._cooldown_until:
            remaining = round(self._cooldown_until - time.monotonic(), 1)
            return {"status": "cooldown", "error": f"Client in rate-limit cooldown. Retry in {remaining}s."}

        selected_model = model or self.default_model
        payload: Dict[str, Any] = {
            "model": selected_model,
            "messages": messages,
            "temperature": max(0.0, min(2.0, temperature)),
            "max_completion_tokens": max(1, min(8192, max_tokens)),
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        started = time.monotonic()
        try:
            data = _post(self._key, payload, self.timeout)
            elapsed_ms = round((time.monotonic() - started) * 1000)
            choice = data.get("choices", [{}])[0]
            content = choice.get("message", {}).get("content", "")
            usage = data.get("usage", {})
            return {
                "status": "success",
                "content": content,
                "model": data.get("model", selected_model),
                "finish_reason": choice.get("finish_reason", "stop"),
                "elapsed_ms": elapsed_ms,
                "usage": {
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0),
                },
            }
        except HTTPError as exc:
            if exc.code == 429:
                delay = 60
                header = exc.headers.get("Retry-After", "") if exc.headers else ""
                try:
                    delay = max(60, int(header))
                except (ValueError, TypeError):
                    pass
                self._cooldown_until = time.monotonic() + delay
                return {"status": "rate_limited", "retry_after_seconds": delay, "error": "Groq rate limit reached."}
            auth_err = exc.code in (401, 403)
            return {
                "status": "authentication_failed" if auth_err else "provider_error",
                "code": exc.code,
                "error": "Authentication failed (invalid Groq API key)" if auth_err else f"Groq HTTP error {exc.code}",
            }
        except (TimeoutError, socket.timeout):
            return {"status": "timeout", "error": "Request timed out."}
        except URLError:
            return {"status": "network_error", "error": "Network unreachable or DNS error."}
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    def ask(self, prompt: str, *, system_prompt: Optional[str] = None, model: Optional[str] = None) -> str:
        """Simple helper to ask Groq a question and get text back."""
        messages: List[Dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        res = self.chat(messages, model=model)
        if res.get("status") == "success":
            return res.get("content", "")
        raise RuntimeError(f"Groq error: {res.get('error', res.get('status'))}")


_groq_client_instance: Optional[GroqClient] = None


def get_groq_client() -> GroqClient:
    """Return a shared singleton instance of GroqClient."""
    global _groq_client_instance
    if _groq_client_instance is None:
        _groq_client_instance = GroqClient()
    return _groq_client_instance
