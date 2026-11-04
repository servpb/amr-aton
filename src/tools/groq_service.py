"""Groq LPU Tool and Service for fast inference and command processing."""
from typing import Any, Dict, List, Optional
from src.integrations.groq_client import (
    DEFAULT_GROQ_MODEL,
    FAST_GROQ_MODEL,
    SUPPORTED_GROQ_MODELS,
    get_groq_client,
)


def query_groq_llm(
    prompt: str,
    system_prompt: str = "",
    model: str = "",
) -> Dict[str, Any]:
    """Execute ultra-fast text reasoning or answer generation using Groq LPU inference.

    Args:
        prompt: The user prompt or instruction.
        system_prompt: Optional system instructions or persona.
        model: Model name ('openai/gpt-oss-20b' ou 'openai/gpt-oss-120b').

    Returns:
        Dict with status, content, model, elapsed_ms and tokens usage.
    """
    client = get_groq_client()
    if not client.enabled:
        return {
            "status": "error",
            "message": "A API Groq não está habilitada ou a chave GROQ_API_KEY não foi configurada no .env.",
        }

    messages: List[Dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    else:
        messages.append({
            "role": "system",
            "content": (
                "Você é o Aton, um assistente pessoal inteligente de alta performance. "
                "Responda sempre em português do Brasil de forma clara, prestativa e concisa."
            ),
        })
    messages.append({"role": "user", "content": prompt})

    res = client.chat(messages, model=model if model else None)
    if res.get("status") == "success":
        return {
            "status": "success",
            "content": res.get("content", ""),
            "model": res.get("model", ""),
            "elapsed_ms": res.get("elapsed_ms", 0),
            "usage": res.get("usage", {}),
        }
    return {
        "status": "error",
        "message": res.get("error", "Erro desconhecido ao consultar a API Groq."),
        "code": res.get("code"),
    }


def check_groq_connection() -> Dict[str, Any]:
    """Check if Groq API is configured, healthy and responsive."""
    client = get_groq_client()
    if not client.enabled:
        return {
            "status": "unconfigured",
            "message": "Chave GROQ_API_KEY não configurada no .env ou cliente desativado.",
        }

    res = client.chat(
        [
            {"role": "system", "content": "Responda apenas com a palavra OK."},
            {"role": "user", "content": "ping"},
        ],
        model=FAST_GROQ_MODEL,
        max_tokens=10,
    )

    if res.get("status") == "success":
        return {
            "status": "connected",
            "message": f"Conexão com Groq API ativa e operacional ({res.get('elapsed_ms')}ms).",
            "model": res.get("model"),
            "elapsed_ms": res.get("elapsed_ms"),
            "default_model": client.default_model,
            "supported_models": SUPPORTED_GROQ_MODELS,
        }
    return {
        "status": "failed",
        "message": f"Falha ao conectar com Groq API: {res.get('error')}",
        "code": res.get("code"),
    }


GROQ_FUNCTION_DECLARATIONS = [
    {
        "name": "query_groq_llm",
        "description": "Executa uma consulta de inteligência artificial ou raciocínio ultra-rápido utilizando os modelos LPU da Groq (openai/gpt-oss-20b, openai/gpt-oss-120b ou qwen/qwen3.8-27b). Use quando o usuário pedir para consultar a Groq, perguntar para a Groq, processar pela Groq ou solicitar resposta via Groq (ou grok, groc, grog).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "prompt": {
                    "type": "STRING",
                    "description": "A pergunta, texto para resumo, análise ou instrução a ser processada.",
                },
                "system_prompt": {
                    "type": "STRING",
                    "description": "Instruções de sistema opcionais para guiar o tom ou formato da resposta.",
                },
                "model": {
                    "type": "STRING",
                    "description": f"Modelo a ser usado. Padrão: '{DEFAULT_GROQ_MODEL}'. Opção rápida: '{FAST_GROQ_MODEL}'.",
                },
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "check_groq_connection",
        "description": "Verifica a integridade, status e latência da conexão com a API Groq LPU. Use SEMPRE que o usuário pedir para verificar, testar, checar ou medir a conexão com a Groq (ou variações fonéticas faladas como Grok, Groc, Grog).",
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        },
    },
]


def dispatch_groq_tool(tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
    """Dispatch Groq tools."""
    if tool_name == "query_groq_llm":
        return query_groq_llm(
            prompt=tool_args.get("prompt", ""),
            system_prompt=tool_args.get("system_prompt", ""),
            model=tool_args.get("model", ""),
        )
    elif tool_name == "check_groq_connection":
        return check_groq_connection()
    return {"status": "unknown_tool", "tool_name": tool_name}
