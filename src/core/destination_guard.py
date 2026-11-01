"""Programmatic destination guard and clarification enforcement for AMR Assistant."""

import logging
import re
from typing import Any, Dict, Optional, Tuple

from src.core.target_context import get_target_context

logger = logging.getLogger(__name__)

AMBIGUOUS_APPS = {"youtube", "netflix", "spotify"}
PC_ONLY_APPS = {
    "chrome",
    "google chrome",
    "edge",
    "microsoft edge",
    "firefox",
    "brave",
    "notepad",
    "bloco de notas",
    "calc",
    "calculadora",
    "word",
    "excel",
    "powerpoint",
    "vscode",
    "code",
}
FIRE_TV_ONLY_APPS = {"downloader", "airscreen", "unitv", "ibo", "pluto", "pluto tv"}


def evaluate_destination_guard(
    tool_name: str,
    tool_args: Dict[str, Any],
) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Inspect and enforce destination boundaries before physical execution.

    Returns:
        Tuple of (decision, payload):
        - ("EXECUTE", {target_module, tool_name, resolved_args})
        - ("BLOCKED", {needs_clarification response dict})
        - ("UNAVAILABLE", {unavailable response dict})
    """
    ctx = get_target_context()
    raw_dest = tool_args.get("destination")
    explicit_dest: Optional[str] = None
    if raw_dest and str(raw_dest).strip().lower() not in ("none", "null", ""):
        norm = str(raw_dest).strip().lower()
        if norm in ("pc", "computador", "windows"):
            explicit_dest = "pc"
        elif norm in ("fire_tv", "firestick", "fire stick", "fire"):
            explicit_dest = "fire_tv"
        elif norm in ("tv", "smart_tv", "televisao", "televisão"):
            explicit_dest = "tv"

    query_text = str(tool_args.get("query") or tool_args.get("app_name") or "")
    if not explicit_dest and query_text:
        lower_q = query_text.lower()
        if re.search(r"\b(no\s+(computador|pc)|no\s+windows)\b", lower_q):
            explicit_dest = "pc"
            cleaned_q = re.sub(r"\s+no\s+(computador|pc|windows)\b", "", query_text, flags=re.IGNORECASE).strip()
            if "query" in tool_args:
                tool_args["query"] = cleaned_q
            elif "app_name" in tool_args:
                tool_args["app_name"] = cleaned_q
        elif re.search(r"\b(no\s+(fire\s*stick|firestick|firetv|fire\s*tv|fire))\b", lower_q):
            explicit_dest = "fire_tv"
            cleaned_q = re.sub(r"\s+no\s+(fire\s*stick|firestick|firetv|fire\s*tv|fire)\b", "", query_text, flags=re.IGNORECASE).strip()
            if "query" in tool_args:
                tool_args["query"] = cleaned_q
            elif "app_name" in tool_args:
                tool_args["app_name"] = cleaned_q
        elif re.search(r"\b(na\s+(tv|televis[aã]o|smart\s*tv))\b", lower_q):
            explicit_dest = "tv"
            cleaned_q = re.sub(r"\s+na\s+(tv|televis[aã]o|smart\s*tv)\b", "", query_text, flags=re.IGNORECASE).strip()
            if "query" in tool_args:
                tool_args["query"] = cleaned_q
            elif "app_name" in tool_args:
                tool_args["app_name"] = cleaned_q

    active_target = ctx.get_active_target()

    # 1. Smart TV Power: Never execute on PC, always report unavailable
    if tool_name == "control_tv_power":
        return "UNAVAILABLE", {
            "status": "unavailable",
            "message": "O controle de ligar/desligar a televisão ainda não está disponível nesta versão.",
        }

    # 2. Smart TV Volume or explicit TV volume request
    if tool_name == "control_tv_volume" or (tool_name == "set_system_volume" and explicit_dest == "tv"):
        return "UNAVAILABLE", {
            "status": "unavailable",
            "message": "O controle de volume da televisão ainda não está disponível nesta versão. O Fire Stick não gerencia o volume da TV por esta integração.",
        }

    # 3. Volume on PC or ambiguous volume
    if tool_name == "set_system_volume":
        if explicit_dest == "pc":
            ctx.set_target("pc")
            return "EXECUTE", {"target": "pc", "tool_name": tool_name, "args": tool_args}
        if active_target == "pc":
            return "EXECUTE", {"target": "pc", "tool_name": tool_name, "args": tool_args}
        if explicit_dest is None and active_target is None:
            # Ambiguous volume request: block without physical effect
            ctx.set_pending_action("volume", tool_args)
            return "BLOCKED", {
                "status": "needs_clarification",
                "destination_needed": True,
                "message": "Destino ambíguo. O senhor deseja alterar o volume do computador ou da TV? (Nota: o controle de volume da TV ainda não está disponível nesta versão).",
            }

    # 4. Media playback (pause, play, stop)
    if tool_name in ("control_system_media", "control_fire_tv", "control_tv_media"):
        action = tool_args.get("action", "pause")
        # Directional navigation or non-playback keys on Fire TV are not ambiguous
        if tool_name == "control_fire_tv" and action in (
            "up", "down", "left", "right", "home", "back", "select", "menu", "rewind", "fast_forward"
        ):
            ctx.set_target("fire_tv")
            return "EXECUTE", {"target": "fire_tv", "tool_name": "control_fire_tv", "args": tool_args}

        # For media playback actions (pause, play, stop, next, previous):
        if explicit_dest == "fire_tv":
            ctx.set_target("fire_tv")
            return "EXECUTE", {"target": "fire_tv", "tool_name": "control_fire_tv", "args": tool_args}
        if explicit_dest == "pc":
            ctx.set_target("pc")
            return "EXECUTE", {"target": "pc", "tool_name": "control_system_media", "args": tool_args}
        if explicit_dest == "tv":
            return "UNAVAILABLE", {
                "status": "unavailable",
                "message": "O controle de mídia direto da TV não está configurado nesta versão. Utilize o Fire Stick ou o computador.",
            }

        # No explicit destination: check session context
        if active_target == "fire_tv":
            return "EXECUTE", {"target": "fire_tv", "tool_name": "control_fire_tv", "args": tool_args}
        if active_target == "pc":
            return "EXECUTE", {"target": "pc", "tool_name": "control_system_media", "args": tool_args}

        # Neither explicit destination nor active context: BLOCK!
        ctx.set_pending_action("media", {"action": action})
        return "BLOCKED", {
            "status": "needs_clarification",
            "destination_needed": True,
            "message": "Destino ambíguo. O senhor não especificou se deseja controlar a reprodução no computador ou no Fire Stick. Pergunte verbalmente: 'No computador ou no Fire Stick?' e aguarde a resposta.",
        }

    # 5. YouTube Search and Playback
    if tool_name in ("search_fire_tv_youtube", "search_youtube"):
        query = str(tool_args.get("query", "")).strip()
        if explicit_dest == "fire_tv":
            ctx.set_target("fire_tv")
            return "EXECUTE", {"target": "fire_tv", "tool_name": "search_fire_tv_youtube", "args": {"query": query}}
        if explicit_dest == "pc":
            ctx.set_target("pc")
            return "EXECUTE", {"target": "pc", "tool_name": "search_youtube", "args": {"query": query}}
        if explicit_dest == "tv":
            ctx.set_target("fire_tv")
            return "EXECUTE", {"target": "fire_tv", "tool_name": "search_fire_tv_youtube", "args": {"query": query}}

        if active_target == "fire_tv":
            return "EXECUTE", {"target": "fire_tv", "tool_name": "search_fire_tv_youtube", "args": {"query": query}}
        if active_target == "pc":
            return "EXECUTE", {"target": "pc", "tool_name": "search_youtube", "args": {"query": query}}

        ctx.set_pending_action("youtube_search", {"query": query})
        return "BLOCKED", {
            "status": "needs_clarification",
            "destination_needed": True,
            "message": f"Destino ambíguo para a pesquisa '{query}'. O senhor deseja pesquisar no computador ou no Fire Stick? Pergunte: 'No computador ou no Fire Stick?' e aguarde a resposta.",
        }

    if tool_name in ("play_fire_tv_youtube", "play_pc_youtube", "play_music"):
        query = str(tool_args.get("query", "")).strip()
        video_id = tool_args.get("video_id")
        resolved_target = None

        if explicit_dest in ("fire_tv", "tv"):
            resolved_target = "fire_tv"
            ctx.set_target("fire_tv")
        elif explicit_dest == "pc":
            resolved_target = "pc"
            ctx.set_target("pc")
        elif active_target in ("fire_tv", "pc"):
            resolved_target = active_target
        else:
            ctx.set_pending_action("play_music", {"query": query, "video_id": video_id})
            return "BLOCKED", {
                "status": "needs_clarification",
                "destination_needed": True,
                "message": f"Destino ambíguo para tocar '{query}'. O senhor deseja tocar no computador ou no Fire Stick? Pergunte: 'No computador ou no Fire Stick?' e aguarde a resposta.",
            }

        if resolved_target == "fire_tv":
            args = {"query": query, "video_id": video_id, "destination": "fire_tv"}
            return "EXECUTE", {"target": "fire_tv", "tool_name": "play_fire_tv_youtube", "args": args}
        else:
            args = {"query": query, "video_id": video_id}
            return "EXECUTE", {"target": "pc", "tool_name": "play_pc_youtube", "args": args}

    # 6. App launching and search
    if tool_name in ("open_application", "search_youtube", "launch_fire_tv_app", "launch_tv_app"):
        app_name = str(tool_args.get("app_name", "")).strip().lower()
        if tool_name == "search_youtube":
            app_name = "youtube"

        # Check if app is unequivocally PC
        if app_name in PC_ONLY_APPS:
            ctx.set_target("pc")
            return "EXECUTE", {"target": "pc", "tool_name": "open_application", "args": tool_args}

        # Check if app is unequivocally Fire TV
        if app_name in FIRE_TV_ONLY_APPS:
            ctx.set_target("fire_tv")
            return "EXECUTE", {"target": "fire_tv", "tool_name": "launch_fire_tv_app", "args": tool_args}

        # For apps available on multiple platforms (YouTube, Netflix, Spotify):
        if explicit_dest == "fire_tv":
            ctx.set_target("fire_tv")
            return "EXECUTE", {"target": "fire_tv", "tool_name": "launch_fire_tv_app", "args": {"app_name": app_name}}
        if explicit_dest == "pc":
            ctx.set_target("pc")
            target_tool = "search_youtube" if app_name == "youtube" else "open_application"
            return "EXECUTE", {"target": "pc", "tool_name": target_tool, "args": {"app_name": app_name}}
        if explicit_dest == "tv":
            return "UNAVAILABLE", {
                "status": "unavailable",
                "message": f"Para abrir {app_name} na televisão, utilize o Fire Stick dizendo 'no Fire Stick'.",
            }

        # No explicit destination: check session context
        if active_target == "fire_tv":
            return "EXECUTE", {"target": "fire_tv", "tool_name": "launch_fire_tv_app", "args": {"app_name": app_name}}
        if active_target == "pc":
            target_tool = "search_youtube" if app_name == "youtube" else "open_application"
            return "EXECUTE", {"target": "pc", "tool_name": target_tool, "args": {"app_name": app_name}}

        # Neither explicit destination nor active context: BLOCK!
        ctx.set_pending_action("open_app", {"app_name": app_name})
        return "BLOCKED", {
            "status": "needs_clarification",
            "destination_needed": True,
            "message": f"Destino ambíguo para '{app_name}'. O senhor não especificou se deseja abrir no computador ou no Fire Stick. Pergunte verbalmente: 'No computador ou no Fire Stick?' e aguarde a resposta.",
        }

    # All other specialized tools (GPS, Gmail, Tasks, Memory, Network, Phone) are unambiguous
    return "EXECUTE", {"target": "passthrough", "tool_name": tool_name, "args": tool_args}


def resolve_clarified_destination(destination: str) -> Dict[str, Any]:
    """Resume and execute a previously blocked pending action once user clarifies destination."""
    from src.tools.fire_tv import control_fire_tv, launch_fire_tv_app
    from src.tools.system_audio import control_system_media, set_system_volume
    from src.tools.web_browser import search_youtube
    from src.tools.windows_apps import open_application

    ctx = get_target_context()
    norm_dest = destination.strip().lower()
    norm_dest = re.sub(r"^(no|na)\s+", "", norm_dest).strip()

    if norm_dest in ("fire_tv", "firestick", "fire stick", "fire"):
        target = "fire_tv"
    elif norm_dest in ("pc", "computador", "windows"):
        target = "pc"
    elif norm_dest in ("tv", "smart_tv", "televisao", "televisão"):
        target = "tv"
    else:
        return {
            "status": "error",
            "message": f"Destino '{destination}' não reconhecido. Responda 'No computador' ou 'No Fire Stick'.",
        }

    if target == "tv":
        pending = ctx.get_pending_action()
        ctx.clear_pending_action()
        if pending and pending.get("action_type") == "volume":
            return {
                "status": "unavailable",
                "message": "O controle de volume da televisão ainda não está disponível nesta versão. O Fire Stick não gerencia o volume da TV por esta integração.",
            }
        return {
            "status": "unavailable",
            "message": "As funções diretas da Smart TV ainda não estão disponíveis nesta versão. Utilize o Fire Stick ou o computador.",
        }

    # Set new active session target
    ctx.set_target(target)
    pending = ctx.get_pending_action()
    ctx.clear_pending_action()

    if not pending:
        label = "Fire Stick" if target == "fire_tv" else "computador"
        return {
            "status": "success",
            "message": f"Destino {label} ativado para os próximos comandos, senhor.",
        }

    action_type = pending.get("action_type")
    params = pending.get("params", {})

    if action_type == "open_app":
        app_name = params.get("app_name", "youtube")
        if target == "fire_tv":
            return launch_fire_tv_app(app_name)
        else:
            if app_name == "youtube":
                return search_youtube()
            return open_application(app_name)

    elif action_type == "media":
        action = params.get("action", "pause")
        if target == "fire_tv":
            return control_fire_tv(action)
        else:
            return control_system_media(action)

    elif action_type == "volume":
        if target == "pc":
            level = params.get("level")
            action = params.get("action", "up")
            if level is not None:
                return set_system_volume(level)
            return set_system_volume(50)  # Safe default if no level specified
        else:
            return {
                "status": "unavailable",
                "message": "O controle de volume da TV ainda não está disponível nesta versão.",
            }

    elif action_type == "youtube_search":
        from src.tools.fire_tv import search_fire_tv_youtube
        query = params.get("query", "")
        if target == "fire_tv":
            return search_fire_tv_youtube(query)
        else:
            return search_youtube(query)

    elif action_type == "play_music":
        from src.tools.fire_tv import play_fire_tv_youtube
        from src.tools.web_browser import play_pc_youtube
        query = params.get("query")
        video_id = params.get("video_id")
        if target == "fire_tv":
            return play_fire_tv_youtube(query=query, video_id=video_id)
        else:
            return play_pc_youtube(query=query, video_id=video_id)

    return {
        "status": "success",
        "message": f"Destino {'Fire Stick' if target == 'fire_tv' else 'computador'} ativado, senhor.",
    }

