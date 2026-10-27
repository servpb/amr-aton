"""Tools module: Windows automation, Playwright, local hardware controls, GPS navigation, Workspace, Memory, and System Controls."""

from typing import Any, Dict
from src.core.memory import (
    MEMORY_FUNCTION_DECLARATIONS,
    dispatch_memory_tool,
    forget_memory,
    get_daily_briefing,
    recall_memory,
    remember_fact,
)
from src.tools.gmail import (
    GMAIL_FUNCTION_DECLARATIONS,
    dispatch_gmail_tool,
    get_email_content,
    list_unread_emails,
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
from src.tools.phone_finder import (
    PHONE_FINDER_FUNCTION_DECLARATIONS,
    dispatch_phone_tool,
    trigger_phone_alarm,
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

# Combined declarations for Gemini Live API (31 tools active)
ALL_ATON_TOOLS = (
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
)


def dispatch_tool(tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
    """Unified dispatcher for all Aton local, web, Smart TV, phone, IoT, GPS, Workspace, Memory, and System tools."""
    # Check Windows app tools
    if tool_name in ("open_application", "close_application", "list_running_applications"):
        return dispatch_windows_tool(tool_name, tool_args)
    # Check Web browser tools
    elif tool_name in ("web_search", "search_youtube", "open_webpage"):
        return dispatch_web_tool(tool_name, tool_args)
    # Check Smart TV tools
    elif tool_name in (
        "control_tv_volume",
        "control_tv_media",
        "control_tv_power",
        "launch_tv_app",
        "get_tv_status",
    ):
        return dispatch_tv_tool(tool_name, tool_args)
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
    elif tool_name in ("list_unread_emails", "get_email_content"):
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
        return dispatch_audio_control_tool(tool_name, tool_args)
    else:
        return {
            "status": "error",
            "message": f"Ferramenta desconhecida '{tool_name}'.",
        }


__all__ = [
    "ALL_ATON_TOOLS",
    "GMAIL_FUNCTION_DECLARATIONS",
    "GOOGLE_CALENDAR_FUNCTION_DECLARATIONS",
    "GOOGLE_MAPS_FUNCTION_DECLARATIONS",
    "GOOGLE_TASKS_FUNCTION_DECLARATIONS",
    "MEMORY_FUNCTION_DECLARATIONS",
    "PHONE_FINDER_FUNCTION_DECLARATIONS",
    "SMART_LIGHTS_FUNCTION_DECLARATIONS",
    "SMART_TV_FUNCTION_DECLARATIONS",
    "SYSTEM_AUDIO_FUNCTION_DECLARATIONS",
    "SYSTEM_TELEMETRY_FUNCTION_DECLARATIONS",
    "WEB_BROWSER_FUNCTION_DECLARATIONS",
    "WINDOWS_APP_FUNCTION_DECLARATIONS",
    "close_application",
    "complete_task",
    "control_lights",
    "control_smart_plug",
    "control_system_media",
    "control_tv_media",
    "control_tv_power",
    "control_tv_volume",
    "create_calendar_event",
    "create_task",
    "dispatch_audio_control_tool",
    "dispatch_calendar_tool",
    "dispatch_gmail_tool",
    "dispatch_lights_tool",
    "dispatch_maps_tool",
    "dispatch_memory_tool",
    "dispatch_phone_tool",
    "dispatch_tasks_tool",
    "dispatch_telemetry_tool",
    "dispatch_tool",
    "dispatch_tv_tool",
    "dispatch_web_tool",
    "dispatch_windows_tool",
    "estimate_traffic_route",
    "find_places_nearby",
    "forget_memory",
    "get_calendar_events",
    "get_daily_briefing",
    "get_email_content",
    "get_system_telemetry",
    "get_tv_status",
    "launch_tv_app",
    "list_running_applications",
    "list_tasks",
    "list_unread_emails",
    "navigate_to",
    "open_application",
    "open_webpage",
    "recall_memory",
    "remember_fact",
    "search_youtube",
    "set_system_volume",
    "trigger_phone_alarm",
    "web_search",
]
