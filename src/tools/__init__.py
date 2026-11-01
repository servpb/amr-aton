"""Tools module: Windows automation, Playwright, local hardware controls, GPS navigation, Workspace, Memory, System Controls, Desktop Typing, and Second Brain."""

from typing import Any, Dict
from src.core.memory import (
    MEMORY_FUNCTION_DECLARATIONS,
    dispatch_memory_tool,
    forget_memory,
    get_daily_briefing,
    recall_memory,
    remember_fact,
)
from src.tools.desktop_automation import (
    DESKTOP_AUTOMATION_FUNCTION_DECLARATIONS,
    create_and_open_document,
    dispatch_desktop_automation_tool,
    focus_application_window,
    send_keyboard_shortcut,
    type_text_in_active_window,
)
from src.tools.gmail import (
    GMAIL_FUNCTION_DECLARATIONS,
    authenticate_gmail,
    check_gmail_connection,
    dispatch_gmail_tool,
    get_email_content,
    list_unread_emails,
    remove_gmail_account,
)
from src.tools.google_calendar import (
    GOOGLE_CALENDAR_FUNCTION_DECLARATIONS,
    create_calendar_event,
    dispatch_calendar_tool,
    get_calendar_events,
)
from src.tools.google_maps import (
    GOOGLE_MAPS_FUNCTION_DECLARATIONS,
    dispatch_maps_tool,
    estimate_traffic_route,
    find_places_nearby,
    navigate_to,
)
from src.tools.google_tasks import (
    GOOGLE_TASKS_FUNCTION_DECLARATIONS,
    complete_task,
    create_task,
    dispatch_tasks_tool,
    list_tasks,
)
from src.tools.network_tools import (
    NETWORK_TOOLS_DEFINITIONS,
    get_network_info,
    list_network_devices,
    revoke_network_device,
    scan_network_devices,
)
from src.tools.phone_finder import (
    PHONE_FINDER_FUNCTION_DECLARATIONS,
    dispatch_phone_tool,
    trigger_phone_alarm,
)
from src.tools.screen_perception import (
    SCREEN_PERCEPTION_FUNCTION_DECLARATIONS,
    descrever_tela,
    dispatch_screen_perception_tool,
    ler_conteudo_tela,
    localizar_e_clicar_elemento,
    preencher_campo_na_tela,
    rolar_tela,
)
from src.tools.second_brain_tools import (
    SECOND_BRAIN_FUNCTION_DECLARATIONS,
    atualizar_memoria_cerebro,
    buscar_memoria,
    consultar_autoconhecimento,
    criar_cliente_cerebro,
    criar_tarefa_cerebro,
    dispatch_second_brain_tool,
    esquecer_memoria_cerebro,
    perguntar_ao_cerebro,
    resumo_geral_cerebro,
    salvar_memoria,
)
from src.tools.smart_lights import (
    SMART_LIGHTS_FUNCTION_DECLARATIONS,
    control_lights,
    control_smart_plug,
    dispatch_lights_tool,
)
from src.tools.smart_tv import (
    SMART_TV_FUNCTION_DECLARATIONS,
    control_tv_media,
    control_tv_power,
    control_tv_volume,
    dispatch_tv_tool,
    get_tv_status,
    launch_tv_app,
)
from src.tools.system_audio import (
    SYSTEM_AUDIO_FUNCTION_DECLARATIONS,
    control_system_media,
    dispatch_audio_control_tool,
    set_system_volume,
)
from src.tools.system_telemetry import (
    SYSTEM_TELEMETRY_FUNCTION_DECLARATIONS,
    dispatch_telemetry_tool,
    get_system_telemetry,
)
from src.tools.web_browser import (
    WEB_BROWSER_FUNCTION_DECLARATIONS,
    dispatch_web_tool,
    open_webpage,
    play_pc_youtube,
    search_youtube,
    web_search,
)
from src.tools.windows_apps import (
    WINDOWS_APP_FUNCTION_DECLARATIONS,
    close_application,
    dispatch_tool as dispatch_windows_tool,
    list_running_applications,
    open_application,
)
from src.tools.youtube import (
    YOUTUBE_FUNCTION_DECLARATIONS,
    authenticate_youtube,
    check_youtube_connection,
    delete_youtube_video,
    dispatch_youtube_tool,
    get_youtube_channel_stats,
    get_youtube_video_details,
    list_youtube_channels,
    list_youtube_comments,
    list_youtube_videos,
    remove_youtube_account,
    reply_to_youtube_comment,
    update_youtube_video_metadata,
    upload_youtube_video,
)

# Combined declarations for Gemini Live API (68 tools active)
from src.core.destination_guard import evaluate_destination_guard, resolve_clarified_destination
from src.core.target_context import get_target_context
from src.tools.fire_tv import FIRE_TV_FUNCTION_DECLARATIONS, dispatch_fire_tv_tool

RESOLVE_DESTINATION_DECLARATION = [
    {
        "name": "resolve_destination",
        "description": "Resolve o destino de um pedido pendente quando o usuário esclarece onde executar ('No Fire Stick' ou 'No computador'). Retoma e executa automaticamente o pedido pendente.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "destination": {
                    "type": "STRING",
                    "enum": ["fire_tv", "pc", "tv"],
                    "description": "O destino escolhido pelo usuário ('fire_tv' para Fire Stick, 'pc' para computador, 'tv' para televisão).",
                }
            },
            "required": ["destination"],
        },
    }
]


from src.tools.module_tools import (
    MODULE_TOOLS_DECLARATIONS,
    detalhar_modulo,
    dispatch_module_tool,
    listar_modulos,
    listar_recursos_pendentes,
)
from src.tools.task_tools import (
    TASK_TOOLS_DECLARATIONS,
    cancelar_tarefa_atual,
    consultar_status_tarefa,
    dispatch_task_tool,
    selecionar_opcao_pendente,
)

ALL_ATON_TOOLS = (
    RESOLVE_DESTINATION_DECLARATION +
    FIRE_TV_FUNCTION_DECLARATIONS +
    WINDOWS_APP_FUNCTION_DECLARATIONS
    + WEB_BROWSER_FUNCTION_DECLARATIONS
    + SMART_TV_FUNCTION_DECLARATIONS
    + PHONE_FINDER_FUNCTION_DECLARATIONS
    + SMART_LIGHTS_FUNCTION_DECLARATIONS
    + GOOGLE_MAPS_FUNCTION_DECLARATIONS
    + GOOGLE_CALENDAR_FUNCTION_DECLARATIONS
    + GMAIL_FUNCTION_DECLARATIONS
    + GOOGLE_TASKS_FUNCTION_DECLARATIONS
    + MEMORY_FUNCTION_DECLARATIONS
    + SYSTEM_TELEMETRY_FUNCTION_DECLARATIONS
    + SYSTEM_AUDIO_FUNCTION_DECLARATIONS
    + DESKTOP_AUTOMATION_FUNCTION_DECLARATIONS
    + SECOND_BRAIN_FUNCTION_DECLARATIONS
    + SCREEN_PERCEPTION_FUNCTION_DECLARATIONS
    + NETWORK_TOOLS_DEFINITIONS
    + YOUTUBE_FUNCTION_DECLARATIONS
    + MODULE_TOOLS_DECLARATIONS
    + TASK_TOOLS_DECLARATIONS
)


def dispatch_tool(tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
    """Unified dispatcher for all Aton local, web, Smart TV, phone, IoT, GPS, Workspace, Memory, System, Desktop, Second Brain, and Network tools."""
    if tool_name == "resolve_destination":
        return resolve_clarified_destination(tool_args.get("destination", ""))

    # Evaluate destination guard and ambiguity boundaries before physical execution
    decision, payload = evaluate_destination_guard(tool_name, tool_args)
    if decision in ("BLOCKED", "UNAVAILABLE"):
        return payload
    if decision == "EXECUTE" and payload:
        tool_name = payload.get("tool_name", tool_name)
        tool_args = payload.get("args", tool_args)

    if tool_name in {item["name"] for item in FIRE_TV_FUNCTION_DECLARATIONS}:
        return dispatch_fire_tv_tool(tool_name, tool_args)
    # Check Windows app tools
    if tool_name in ("open_application", "close_application", "list_running_applications"):
        res = dispatch_windows_tool(tool_name, tool_args)
        if isinstance(res, dict) and res.get("status") == "success":
            get_target_context().set_target("pc")
        return res
    # Check Web browser tools
    elif tool_name in ("web_search", "search_youtube", "open_webpage", "play_pc_youtube"):
        res = dispatch_web_tool(tool_name, tool_args)
        if isinstance(res, dict) and res.get("status") in ("success", "inconclusive"):
            get_target_context().set_target("pc")
        return res
    # Check Smart TV tools
    elif tool_name in (
        "control_tv_volume",
        "control_tv_media",
        "control_tv_power",
        "launch_tv_app",
        "get_tv_status",
    ):
        res = dispatch_tv_tool(tool_name, tool_args)
        if isinstance(res, dict) and res.get("status") == "success":
            get_target_context().set_target("smart_tv")
        return res
    # Check Phone Finder tools
    elif tool_name in ("find_phone",):
        return dispatch_phone_tool(tool_name, tool_args)
    # Check Smart Lights & Plugs tools
    elif tool_name in ("control_lights", "control_smart_plug"):
        return dispatch_lights_tool(tool_name, tool_args)
    # Check Google Maps tools
    elif tool_name in ("navigate_to", "find_places_nearby", "estimate_traffic_route"):
        return dispatch_maps_tool(tool_name, tool_args)
    # Check Google Calendar tools
    elif tool_name in ("get_calendar_events", "create_calendar_event"):
        return dispatch_calendar_tool(tool_name, tool_args)
    # Check Gmail tools
    elif tool_name in (
        "list_unread_emails",
        "get_email_content",
        "authenticate_gmail",
        "check_gmail_connection",
        "remove_gmail_account",
    ):
        return dispatch_gmail_tool(tool_name, tool_args)
    # Check Google Tasks tools
    elif tool_name in ("list_tasks", "create_task", "complete_task"):
        return dispatch_tasks_tool(tool_name, tool_args)
    # Check Semantic Memory & Briefing tools
    elif tool_name in ("remember_fact", "recall_memory", "forget_memory", "get_daily_briefing"):
        return dispatch_memory_tool(tool_name, tool_args)
    # Check System Telemetry tools
    elif tool_name in ("get_system_telemetry",):
        return dispatch_telemetry_tool(tool_name, tool_args)
    # Check System Audio & Media tools
    elif tool_name in ("set_system_volume", "control_system_media"):
        res = dispatch_audio_control_tool(tool_name, tool_args)
        if isinstance(res, dict) and res.get("status") == "success":
            get_target_context().set_target("pc")
        return res
    # Check Desktop Typing & Office Automation tools
    elif tool_name in (
        "type_text_in_active_window",
        "create_and_open_document",
        "send_keyboard_shortcut",
        "focus_application_window",
    ):
        res = dispatch_desktop_automation_tool(tool_name, tool_args)
        if isinstance(res, dict) and res.get("status") == "success":
            get_target_context().set_target("pc")
        return res
    # Check Second Brain tools
    elif tool_name in (
        "salvar_memoria",
        "buscar_memoria",
        "perguntar_ao_cerebro",
        "criar_cliente_cerebro",
        "criar_tarefa_cerebro",
        "resumo_geral_cerebro",
        "esquecer_memoria_cerebro",
        "atualizar_memoria_cerebro",
        "consultar_autoconhecimento",
    ):
        return dispatch_second_brain_tool(tool_name, tool_args)
    # Check Screen Perception & UI Interaction tools
    elif tool_name in (
        "descrever_tela",
        "ler_conteudo_tela",
        "localizar_e_clicar_elemento",
        "preencher_campo_na_tela",
        "rolar_tela",
    ):
        return dispatch_screen_perception_tool(tool_name, tool_args)
    # Check Network Discovery & Authorized Devices tools
    elif tool_name == "get_network_info":
        return get_network_info()
    elif tool_name == "list_network_devices":
        return list_network_devices()
    elif tool_name == "revoke_network_device":
        return revoke_network_device(tool_args.get("device_identifier", ""))
    elif tool_name == "scan_network_devices":
        return scan_network_devices(tool_args.get("subnet_range"))
    # Check Task Status, Choice Selection & Cancellation tools
    elif tool_name in ("consultar_status_tarefa", "selecionar_opcao_pendente", "cancelar_tarefa_atual"):
        return dispatch_task_tool(tool_name, tool_args)
    # Check Module Explanation & Introspection tools
    elif tool_name in ("listar_modulos", "detalhar_modulo", "listar_recursos_pendentes"):
        return dispatch_module_tool(tool_name, tool_args)
    # Check YouTube Multi-Account & Multi-Channel tools
    elif tool_name in (
        "list_youtube_channels",
        "get_youtube_channel_stats",
        "list_youtube_videos",
        "get_youtube_video_details",
        "list_youtube_comments",
        "reply_to_youtube_comment",
        "update_youtube_video_metadata",
        "upload_youtube_video",
        "delete_youtube_video",
        "authenticate_youtube",
        "check_youtube_connection",
        "remove_youtube_account",
    ):
        return dispatch_youtube_tool(tool_name, tool_args)
    else:
        return {
            "status": "error",
            "message": f"Ferramenta desconhecida '{tool_name}'.",
        }


__all__ = [
    "ALL_ATON_TOOLS",
    "MODULE_TOOLS_DECLARATIONS",
    "TASK_TOOLS_DECLARATIONS",
    "consultar_status_tarefa",
    "selecionar_opcao_pendente",
    "cancelar_tarefa_atual",
    "dispatch_task_tool",
    "detalhar_modulo",
    "dispatch_module_tool",
    "listar_modulos",
    "listar_recursos_pendentes",
    "DESKTOP_AUTOMATION_FUNCTION_DECLARATIONS",
    "GMAIL_FUNCTION_DECLARATIONS",
    "GOOGLE_CALENDAR_FUNCTION_DECLARATIONS",
    "GOOGLE_MAPS_FUNCTION_DECLARATIONS",
    "GOOGLE_TASKS_FUNCTION_DECLARATIONS",
    "MEMORY_FUNCTION_DECLARATIONS",
    "PHONE_FINDER_FUNCTION_DECLARATIONS",
    "SCREEN_PERCEPTION_FUNCTION_DECLARATIONS",
    "SECOND_BRAIN_FUNCTION_DECLARATIONS",
    "SMART_LIGHTS_FUNCTION_DECLARATIONS",
    "SMART_TV_FUNCTION_DECLARATIONS",
    "SYSTEM_AUDIO_FUNCTION_DECLARATIONS",
    "SYSTEM_TELEMETRY_FUNCTION_DECLARATIONS",
    "WEB_BROWSER_FUNCTION_DECLARATIONS",
    "WINDOWS_APP_FUNCTION_DECLARATIONS",
    "YOUTUBE_FUNCTION_DECLARATIONS",
    "authenticate_gmail",
    "authenticate_youtube",
    "buscar_memoria",
    "check_gmail_connection",
    "check_youtube_connection",
    "close_application",
    "complete_task",
    "control_lights",
    "control_smart_plug",
    "control_system_media",
    "control_tv_media",
    "control_tv_power",
    "control_tv_volume",
    "create_and_open_document",
    "create_calendar_event",
    "create_cliente_cerebro",
    "create_task",
    "criar_cliente_cerebro",
    "criar_tarefa_cerebro",
    "delete_youtube_video",
    "dispatch_audio_control_tool",
    "dispatch_calendar_tool",
    "dispatch_desktop_automation_tool",
    "dispatch_gmail_tool",
    "dispatch_lights_tool",
    "dispatch_maps_tool",
    "dispatch_memory_tool",
    "dispatch_phone_tool",
    "dispatch_second_brain_tool",
    "dispatch_tasks_tool",
    "dispatch_telemetry_tool",
    "dispatch_tool",
    "dispatch_tv_tool",
    "dispatch_web_tool",
    "dispatch_windows_tool",
    "dispatch_youtube_tool",
    "estimate_traffic_route",
    "find_places_nearby",
    "focus_application_window",
    "forget_memory",
    "get_calendar_events",
    "get_daily_briefing",
    "get_email_content",
    "get_system_telemetry",
    "get_tv_status",
    "get_youtube_channel_stats",
    "get_youtube_video_details",
    "launch_tv_app",
    "list_running_applications",
    "list_tasks",
    "list_unread_emails",
    "list_youtube_channels",
    "list_youtube_comments",
    "list_youtube_videos",
    "navigate_to",
    "open_application",
    "open_webpage",
    "perguntar_ao_cerebro",
    "play_pc_youtube",
    "recall_memory",
    "remember_fact",
    "remove_gmail_account",
    "remove_youtube_account",
    "reply_to_youtube_comment",
    "resumo_geral_cerebro",
    "salvar_memoria",
    "search_youtube",
    "send_keyboard_shortcut",
    "set_system_volume",
    "trigger_phone_alarm",
    "type_text_in_active_window",
    "update_youtube_video_metadata",
    "upload_youtube_video",
    "web_search",
]
