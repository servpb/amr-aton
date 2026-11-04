"""Nemotron connector supporting both Direct NVIDIA NIM API and OpenRouter."""
import json
import logging
import socket
import time
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

logger = logging.getLogger(__name__)

NVIDIA_NIM_ENDPOINT = "https://integrate.api.nvidia.com/v1/chat/completions"
OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"

DEFAULT_NEMOTRON_MODEL_OPENROUTER = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"
DEFAULT_NEMOTRON_MODEL_NVIDIA = "nvidia/llama-3.1-nemotron-70b-instruct"

# Official available Nemotron free models on OpenRouter
REASONING_NEMOTRON_MODEL = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"
LIGHTNING_NEMOTRON_MODEL = "nvidia/nemotron-3.5-lightning:free"
ULTRA_NEMOTRON_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"

# Compatibility constant for previous references
DEFAULT_NEMOTRON_MODEL = DEFAULT_NEMOTRON_MODEL_OPENROUTER

SUPPORTED_FREE_MODELS = [
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
    "nvidia/nemotron-3.5-lightning:free",
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "google/gemma-4-31b-it:free",
    "nvidia/llama-3.1-nemotron-70b-instruct",
]


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _post_api(endpoint: str, key: str, payload: dict, timeout: float) -> dict:
    """Internal HTTP POST using standard library to NVIDIA NIM or OpenRouter."""
    headers = {
        "Authorization": "Bearer " + key,
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/aton-assistant",
        "X-Title": "Aton Personal Assistant",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AtonAssistant/1.0",
    }
    request = Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers=headers,
    )
    with build_opener(NoRedirect()).open(request, timeout=timeout) as response:
        raw = response.read(262145)
    if len(raw) > 262144:
        raise ValueError("oversized_response")
    return json.loads(raw.decode("utf-8"))


# Backward-compatible wrapper for tests monkeypatching _post_openrouter
def _post_openrouter(key: str, payload: dict, timeout: float) -> dict:
    return _post_api(OPENROUTER_ENDPOINT, key, payload, timeout)


class OpenRouterClient:
    """Client for NVIDIA Nemotron supporting both direct NVIDIA NIM and OpenRouter endpoints."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        default_model: Optional[str] = None,
        timeout: float = 25.0,
        enabled: bool = True,
        strict_free_tier: bool = True,
        provider: Optional[str] = None,
    ):
        try:
            from src.config import settings
            configured_openrouter_key = settings.openrouter_api_key
            configured_nvidia_key = settings.nvidia_api_key
            configured_model = settings.openrouter_model
            configured_timeout = settings.openrouter_timeout_seconds
            configured_enabled = settings.openrouter_enabled or settings.nvidia_enabled
        except Exception:
            configured_openrouter_key = ""
            configured_nvidia_key = ""
            configured_model = DEFAULT_NEMOTRON_MODEL_OPENROUTER
            configured_timeout = 25.0
            configured_enabled = True

        # Determine key and provider (priority: explicit arg -> OpenRouter -> NVIDIA NIM)
        if api_key is not None:
            self._key = api_key.strip()
        elif configured_openrouter_key:
            self._key = configured_openrouter_key.strip()
        elif configured_nvidia_key:
            self._key = configured_nvidia_key.strip()
        else:
            self._key = ""

        self._explicit_provider = provider
        self._custom_model = default_model
        self.timeout = min(60.0, max(1.0, float(timeout or configured_timeout)))
        self.enabled = bool(enabled and configured_enabled and self._key)
        self.strict_free_tier = strict_free_tier
        self._cooldown_until = 0.0

    @property
    def provider(self) -> str:
        if self._explicit_provider:
            return self._explicit_provider
        if self._key.startswith("nvapi-"):
            return "nvidia_nim"
        return "openrouter"

    @property
    def endpoint(self) -> str:
        if self.provider == "nvidia_nim":
            return NVIDIA_NIM_ENDPOINT
        return OPENROUTER_ENDPOINT

    @property
    def default_model(self) -> str:
        if self._custom_model:
            return self._custom_model
        if self.provider == "nvidia_nim":
            return DEFAULT_NEMOTRON_MODEL_NVIDIA
        return DEFAULT_NEMOTRON_MODEL_OPENROUTER

    def chat(
        self,
        messages: List[Dict[str, str]],
        *,
        model: Optional[str] = None,
        temperature: float = 0.6,
        max_tokens: int = 2048,
        json_mode: bool = False,
    ) -> Dict[str, Any]:
        """Send chat completion request to NVIDIA NIM or OpenRouter."""
        if not self.enabled:
            return {
                "status": "disabled",
                "error": f"{self.provider} client is disabled or missing API key.",
            }
        if time.monotonic() < self._cooldown_until:
            remaining = round(self._cooldown_until - time.monotonic(), 1)
            return {
                "status": "cooldown",
                "error": f"Client in rate-limit cooldown. Retry in {remaining}s.",
            }

        selected_model = model or self.default_model

        # Guard: Ensure model is free if OpenRouter and strict free tier is enforced
        if self.provider == "openrouter" and self.strict_free_tier and not selected_model.endswith(":free"):
            return {
                "status": "policy_blocked",
                "error": f"Model '{selected_model}' rejected: only free models with ':free' suffix allowed on OpenRouter.",
            }

        payload: Dict[str, Any] = {
            "model": selected_model,
            "messages": messages,
            "temperature": max(0.0, min(2.0, temperature)),
            "max_tokens": max(1, min(8192, max_tokens)),
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        started = time.monotonic()
        try:
            if self.provider == "openrouter":
                data = _post_openrouter(self._key, payload, self.timeout)
            else:
                data = _post_api(self.endpoint, self._key, payload, self.timeout)

            elapsed_ms = round((time.monotonic() - started) * 1000)
            choice = data.get("choices", [{}])[0]
            message = choice.get("message", {})
            content = message.get("content") or message.get("reasoning") or ""
            usage = data.get("usage", {})
            return {
                "status": "success",
                "content": content,
                "model": data.get("model", selected_model),
                "provider": self.provider,
                "finish_reason": choice.get("finish_reason", "stop"),
                "elapsed_ms": elapsed_ms,
                "usage": {
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0),
                },
            }
        except HTTPError as exc:
            err_body = ""
            try:
                err_body = exc.read().decode("utf-8")
            except Exception:
                pass

            if exc.code == 429:
                delay = 60
                header = exc.headers.get("Retry-After", "") if exc.headers else ""
                try:
                    delay = max(60, int(header))
                except (ValueError, TypeError):
                    pass
                self._cooldown_until = time.monotonic() + delay
                return {
                    "status": "rate_limited",
                    "retry_after_seconds": delay,
                    "error": f"{self.provider} rate limit reached.",
                }

            if exc.code == 404 and "Not found for account" in err_body:
                # Check if fallback to OpenRouter is possible
                from src.config import settings
                if self.provider == "nvidia_nim" and settings.openrouter_api_key:
                    logger.warning("NVIDIA NIM endpoint não provisionado na conta. Comutando automaticamente para OpenRouter...")
                    fallback_client = OpenRouterClient(api_key=settings.openrouter_api_key, provider="openrouter")
                    return fallback_client.chat(messages, model=DEFAULT_NEMOTRON_MODEL_OPENROUTER, temperature=temperature, max_tokens=max_tokens, json_mode=json_mode)

                return {
                    "status": "account_not_provisioned",
                    "code": 404,
                    "error": (
                        "A conta NVIDIA ainda não teve o acesso de inferência em nuvem liberado no build.nvidia.com. "
                        "Para liberar: acesse https://build.nvidia.com/nvidia/llama-3_1-nemotron-70b-instruct, "
                        "confirme o e-mail de ativação da NVIDIA e teste o modelo uma vez no playground da página. "
                        "Alternativa imediata: adicione OPENROUTER_API_KEY no .env para usar a Nemotron sem esperar."
                    ),
                }

            auth_err = exc.code in (401, 403)
            return {
                "status": "authentication_failed" if auth_err else "provider_error",
                "code": exc.code,
                "error": (
                    f"Authentication failed (invalid {self.provider} API key)"
                    if auth_err
                    else f"{self.provider} HTTP error {exc.code}"
                ),
            }
        except (TimeoutError, socket.timeout):
            return {"status": "timeout", "error": "Request timed out."}
        except URLError:
            return {"status": "network_error", "error": "Network unreachable or DNS error."}
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    def plan_task(
        self,
        objective: str,
        *,
        constraints: str = "",
        context: str = "",
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Perform deep task planning and decomposition using NVIDIA Nemotron."""
        system_prompt = (
            "Você é o módulo de Planejamento Avançado do assistente Aton, movido pelo modelo NVIDIA Nemotron.\n"
            "Seu papel é analisar objetivos complexos e produzir um plano de ação estruturado, rigoroso e viável.\n"
            "Diretrizes:\n"
            "1. Responda em Português do Brasil com tom analítico e executivo.\n"
            "2. Estruture sua resposta nas seguintes seções claras:\n"
            "   - Objetivo Central\n"
            "   - Pré-requisitos e Dependências\n"
            "   - Plano Passo a Passo (Etapas ordenadas com critérios de conclusão)\n"
            "   - Riscos Identificados e Planos de Mitigação\n"
            "   - Critério de Pronto (Definição de Sucesso)\n"
            "3. Seja pragmático, objetivo e não inclua dados sensíveis ou especulações."
        )

        user_content = f"Objetivo: {objective}\n"
        if constraints:
            user_content += f"Restrições/Limitações: {constraints}\n"
        if context:
            user_content += f"Contexto Adicional: {context}\n"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]
        return self.chat(messages, model=model, temperature=0.5, max_tokens=2500)

    def ask(
        self,
        prompt: str,
        *,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
    ) -> str:
        """Simple helper to ask Nemotron a question."""
        messages: List[Dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        res = self.chat(messages, model=model)
        if res.get("status") == "success":
            return res.get("content", "")
        raise RuntimeError(f"{self.provider} error: {res.get('error', res.get('status'))}")


# NemotronClient alias
NemotronClient = OpenRouterClient

_openrouter_client_instance: Optional[OpenRouterClient] = None


def get_openrouter_client() -> OpenRouterClient:
    """Return a shared singleton instance of OpenRouterClient."""
    global _openrouter_client_instance
    if _openrouter_client_instance is None:
        _openrouter_client_instance = OpenRouterClient()
    return _openrouter_client_instance


def get_nemotron_client() -> OpenRouterClient:
    """Alias for get_openrouter_client."""
    return get_openrouter_client()
