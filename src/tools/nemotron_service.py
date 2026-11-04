"""Nemotron & OpenRouter Service for Deep Planning and Complex Task Reasoning."""
from typing import Any, Dict, List, Optional
from src.integrations.openrouter_client import (
    DEFAULT_NEMOTRON_MODEL,
    SUPPORTED_FREE_MODELS,
    get_openrouter_client,
)


def planejar_tarefa_complexa(
    objetivo: str,
    restricoes: str = "",
    contexto: str = "",
    model: str = "",
) -> Dict[str, Any]:
    """Execute deep task planning and decomposition using NVIDIA Nemotron.

    Args:
        objetivo: The main challenge or objective to be planned.
        restricoes: Specific constraints, limitations or requirements.
        contexto: Additional context or background info.
        model: Optional model name (defaults to 'nvidia/llama-3.1-nemotron-70b-instruct:free').

    Returns:
        Dict with status, plano (structured plan text), model, elapsed_ms, and token usage.
    """
    client = get_openrouter_client()
    if not client.enabled:
        return {
            "status": "error",
            "message": "O módulo Nemotron não está habilitado ou nenhuma chave NVIDIA_API_KEY / OPENROUTER_API_KEY foi configurada no .env.",
        }

    res = client.plan_task(
        objective=objetivo,
        constraints=restricoes,
        context=contexto,
        model=model if model else None,
    )

    if res.get("status") == "success":
        return {
            "status": "success",
            "plano": res.get("content", ""),
            "model": res.get("model", ""),
            "elapsed_ms": res.get("elapsed_ms", 0),
            "usage": res.get("usage", {}),
        }
    return {
        "status": "error",
        "message": res.get("error", "Erro ao executar planejamento com a Nemotron."),
        "code": res.get("code"),
    }


def consultar_nemotron(
    prompt: str,
    system_prompt: str = "",
    model: str = "",
) -> Dict[str, Any]:
    """Execute a general reasoning or analysis query using NVIDIA Nemotron."""
    client = get_openrouter_client()
    if not client.enabled:
        return {
            "status": "error",
            "message": "Chave OPENROUTER_API_KEY não configurada no .env.",
        }

    messages: List[Dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    else:
        messages.append({
            "role": "system",
            "content": (
                "Você é o modelo NVIDIA Nemotron integrado ao assistente Aton. "
                "Responda em português do Brasil com precisão lógica, clareza e profundidade analítica."
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
        "message": res.get("error", "Erro ao consultar Nemotron."),
        "code": res.get("code"),
    }


def check_nemotron_connection() -> Dict[str, Any]:
    """Check if NVIDIA NIM / OpenRouter Nemotron endpoint is reachable and responsive."""
    client = get_openrouter_client()
    if not client.enabled:
        return {
            "status": "unconfigured",
            "message": "Nenhuma chave NVIDIA_API_KEY ou OPENROUTER_API_KEY configurada no .env ou cliente desativado.",
        }

    res = client.chat(
        [
            {"role": "system", "content": "Responda apenas com a palavra OK."},
            {"role": "user", "content": "ping"},
        ],
        model=client.default_model,
        max_tokens=10,
    )

    provider_label = "NVIDIA NIM Oficial (build.nvidia.com)" if client.provider == "nvidia_nim" else "OpenRouter"
    if res.get("status") == "success":
        return {
            "status": "connected",
            "message": f"Conexão com {provider_label} e NVIDIA Nemotron ativa ({res.get('elapsed_ms')}ms).",
            "provider": client.provider,
            "model": res.get("model"),
            "elapsed_ms": res.get("elapsed_ms"),
            "default_model": client.default_model,
            "supported_models": SUPPORTED_FREE_MODELS,
        }
    return {
        "status": "failed",
        "message": f"Falha ao conectar com Nemotron via {provider_label}: {res.get('error')}",
        "code": res.get("code"),
    }


NEMOTRON_FUNCTION_DECLARATIONS = [
    {
        "name": "planejar_tarefa_complexa",
        "description": "Decompõe e planeja tarefas complexas, projetos desafiadores ou automações usando o modelo NVIDIA Nemotron 70B. Use quando o usuário pedir para planejar, estruturar, decompor etapas ou desenhar um plano de ação detalhado.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "objetivo": {
                    "type": "STRING",
                    "description": "O objetivo, desafio ou meta principal que precisa de planejamento.",
                },
                "restricoes": {
                    "type": "STRING",
                    "description": "Restrições de tempo, recursos, ferramentas ou regras a serem respeitadas.",
                },
                "contexto": {
                    "type": "STRING",
                    "description": "Informações de contexto adicionais sobre o ambiente ou situação.",
                },
            },
            "required": ["objetivo"],
        },
    },
    {
        "name": "consultar_nemotron",
        "description": "Executa uma consulta de raciocínio lógico avançado ou análise profunda utilizando o modelo NVIDIA Nemotron 70B.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "prompt": {
                    "type": "STRING",
                    "description": "A pergunta, problema analítico ou desafio de lógica a ser analisado.",
                },
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "check_nemotron_connection",
        "description": "Verifica a integridade, disponibilidade e latência da conexão com o modelo NVIDIA Nemotron via OpenRouter. Use quando o usuário pedir para verificar, testar ou checar a conexão com a Nemotron ou OpenRouter.",
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        },
    },
]


def dispatch_nemotron_tool(tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
    """Dispatch Nemotron tools."""
    if tool_name == "planejar_tarefa_complexa":
        return planejar_tarefa_complexa(
            objetivo=tool_args.get("objetivo", ""),
            restricoes=tool_args.get("restricoes", ""),
            contexto=tool_args.get("contexto", ""),
            model=tool_args.get("model", ""),
        )
    elif tool_name == "consultar_nemotron":
        return consultar_nemotron(
            prompt=tool_args.get("prompt", ""),
            system_prompt=tool_args.get("system_prompt", ""),
            model=tool_args.get("model", ""),
        )
    elif tool_name == "check_nemotron_connection":
        return check_nemotron_connection()
    return {"status": "unknown_tool", "tool_name": tool_name}

