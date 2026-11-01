"""Tool declarations and dispatchers for Aton's module explanation and capability introspection."""

import logging
from typing import Any, Dict, Optional

from src.core.module_registry import get_module_registry

logger = logging.getLogger(__name__)


def listar_modulos(area: Optional[str] = None) -> Dict[str, Any]:
    """Lista os módulos operacionais do Aton organizados por áreas com descrições curtas e resumo falado."""
    registry = get_module_registry()
    return registry.list_modules_overview(area_filter=area)


def detalhar_modulo(modulo: str) -> Dict[str, Any]:
    """Explica detalhadamente um módulo específico do Aton: objetivo, ferramentas, exemplos de comandos, limitações e status."""
    registry = get_module_registry()
    return registry.detail_module(query=modulo)


def listar_recursos_pendentes() -> Dict[str, Any]:
    """Lista quais módulos do Aton requerem configuração prévia ou autenticação para operar."""
    registry = get_module_registry()
    return registry.list_unconfigured_or_pending()


def dispatch_module_tool(tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
    """Dispatcher for module explanation and introspection tools."""
    if tool_name == "listar_modulos":
        return listar_modulos(area=tool_args.get("area"))
    elif tool_name == "detalhar_modulo":
        return detalhar_modulo(modulo=tool_args.get("modulo", ""))
    elif tool_name == "listar_recursos_pendentes":
        return listar_recursos_pendentes()
    return {
        "status": "error",
        "message": f"Ferramenta de autoconhecimento de módulos '{tool_name}' desconhecida.",
    }


MODULE_TOOLS_DECLARATIONS = [
    {
        "name": "listar_modulos",
        "description": "Lista os módulos e subsistemas funcionais do Aton por áreas (Sistema e Windows, Casa Inteligente, Google Workspace, Segundo Cérebro e Visão). Use quando o usuário perguntar 'quais módulos você tem?', 'o que você pode fazer?' ou pedir uma visão geral de suas capacidades.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "area": {
                    "type": "STRING",
                    "description": "Filtro opcional por área (ex: 'sistema_windows', 'casa_smart_tv', 'google_workspace', 'segundo_cerebro_ia', 'visao_interacao').",
                }
            },
        },
    },
    {
        "name": "detalhar_modulo",
        "description": "Explica detalhadamente o que faz um módulo específico do Aton, como usá-lo com exemplos de voz, suas limitações verificadas, status de configuração e ferramentas ativas. Use quando o usuário perguntar 'o que você faz no Fire Stick?', 'como uso o YouTube?', 'o que o módulo de tarefas faz?' ou pedir detalhes de um recurso específico.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "modulo": {
                    "type": "STRING",
                    "description": "Nome ou apelido do módulo a consultar (ex: 'fire_tv', 'fire stick', 'youtube', 'gmail', 'agenda', 'tarefas', 'maps', 'tela', 'visao', 'office', 'windows', 'volume', 'segundo_cerebro', 'luzes').",
                }
            },
            "required": ["modulo"],
        },
    },
    {
        "name": "listar_recursos_pendentes",
        "description": "Lista quais recursos ou módulos do Aton ainda necessitam de configuração de credenciais, chaves ou tokens para funcionarem plenamente. Use quando o usuário perguntar 'quais recursos precisam de configuração?' ou 'o que ainda falta configurar?'.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
]

