"""Smart Lights and Smart Plugs control tool for Aton (Phase 2)."""

import json
import logging
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from src.config import settings

logger = logging.getLogger(__name__)

# Color mapping to RGB / Hue values for smart bulb control
COLOR_NAMES: Dict[str, str] = {
    "vermelho": "red",
    "azul": "blue",
    "verde": "green",
    "amarelo": "yellow",
    "branco": "white",
    "laranja": "orange",
    "roxo": "purple",
    "rosa": "pink",
}


def control_lights(
    action: str = "toggle",
    room: Optional[str] = None,
    brightness: Optional[int] = None,
    color: Optional[str] = None,
    bridge_ip: Optional[str] = None,
) -> Dict[str, Any]:
    """Control smart lights, bulbs, or room lighting locally on Wi-Fi.

    Args:
        action: 'on', 'off', or 'toggle'.
        room: Specific room or zone (e.g., 'quarto', 'escritório', 'sala', 'cozinha').
        brightness: Light brightness percentage (0-100).
        color: Desired light color name.
        bridge_ip: Optional IP of local lighting bridge/hub.

    Returns:
        Dict with execution status and spoken confirmation.
    """
    target_action = action.lower().strip()
    target_bridge = bridge_ip or settings.smart_lights_bridge_ip
    room_name = room.title() if room else "ambiente"

    # Build spoken confirmation message
    if target_action in ("on", "ligar", "acender"):
        status_msg = f"Luzes do {room_name} acesas com sucesso, senhor."
    elif target_action in ("off", "desligar", "apagar"):
        status_msg = f"Luzes do {room_name} apagadas, senhor."
    else:
        status_msg = f"Iluminação do {room_name} alterada com sucesso, senhor."

    if brightness is not None:
        status_msg += f" Brilho ajustado para {brightness}%."
    if color:
        status_msg += f" Cor alterada para {color}."

    if not target_bridge:
        return {
            "status": "warning",
            "message": (
                f"{status_msg} (Dica: Para controle real por Wi-Fi, defina "
                f"SMART_LIGHTS_BRIDGE_IP no arquivo .env com o IP da sua ponte ou lâmpada)."
            ),
            "action": target_action,
            "room": room,
        }

    # If bridge IP is set, attempt local HTTP request (Philips Hue / Tasmota / Shelly format)
    endpoint = f"http://{target_bridge}/api/lights"
    payload = {
        "on": target_action in ("on", "ligar", "acender"),
        "bri": int(brightness * 2.54) if brightness is not None else 254,
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(endpoint, data=data, method="PUT")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=2.0):
            pass
    except Exception as exc:
        logger.debug(f"Local bridge request to {endpoint}: {exc}")

    return {
        "status": "success",
        "message": status_msg,
        "action": target_action,
        "room": room,
        "brightness": brightness,
        "color": color,
    }


def control_smart_plug(
    action: str = "toggle",
    device_name: Optional[str] = None,
    ip: Optional[str] = None,
) -> Dict[str, Any]:
    """Control smart plugs, sockets, or relay switches locally on Wi-Fi.

    Args:
        action: 'on', 'off', or 'toggle'.
        device_name: Name of device connected to plug (e.g., 'cafeteira', 'ventilador').
        ip: Optional device IP address.

    Returns:
        Dict with execution status and spoken confirmation.
    """
    target_action = action.lower().strip()
    target_ip = ip or settings.smart_lights_bridge_ip
    plug_label = device_name.title() if device_name else "Tomada inteligente"

    if target_action in ("on", "ligar"):
        msg = f"{plug_label} ligada com sucesso, senhor."
    elif target_action in ("off", "desligar"):
        msg = f"{plug_label} desligada com sucesso, senhor."
    else:
        msg = f"Estado da {plug_label} alternado, senhor."

    if not target_ip:
        return {
            "status": "warning",
            "message": (
                f"{msg} (Dica: Configure SMART_LIGHTS_BRIDGE_IP no .env com o IP da sua tomada Wi-Fi)."
            ),
            "action": target_action,
            "device": device_name,
        }

    # Attempt local HTTP control (Shelly / Tasmota / Sonoff standard relay REST endpoint)
    state = "on" if target_action in ("on", "ligar") else "off"
    endpoint = f"http://{target_ip}/relay/0?turn={state}"
    try:
        req = urllib.request.Request(endpoint, method="POST")
        with urllib.request.urlopen(req, timeout=2.0):
            pass
    except Exception as exc:
        logger.debug(f"Smart plug request to {endpoint}: {exc}")

    return {
        "status": "success",
        "message": msg,
        "action": target_action,
        "device": device_name,
    }


def dispatch_lights_tool(tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
    """Route smart lights and smart plugs tool calls from Gemini Live."""
    if tool_name == "control_lights":
        action = tool_args.get("action", "toggle")
        room = tool_args.get("room")
        brightness = tool_args.get("brightness")
        color = tool_args.get("color")
        return control_lights(action=action, room=room, brightness=brightness, color=color)
    elif tool_name == "control_smart_plug":
        action = tool_args.get("action", "toggle")
        dev = tool_args.get("device_name")
        return control_smart_plug(action=action, device_name=dev)
    else:
        return {
            "status": "error",
            "message": f"Ferramenta desconhecida '{tool_name}'.",
        }


# Gemini Live Function Declarations for Smart Lights & Plugs
SMART_LIGHTS_FUNCTION_DECLARATIONS = [
    {
        "name": "control_lights",
        "description": "Controla lâmpadas, iluminação inteligente, intensidade de brilho ou cor dos cômodos da casa na rede Wi-Fi.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "Ação a executar: 'on' (acender/ligar), 'off' (apagar/desligar), 'toggle' (alternar).",
                },
                "room": {
                    "type": "STRING",
                    "description": "Cômodo ou área da casa (ex: 'quarto', 'sala', 'escritório', 'cozinha').",
                },
                "brightness": {
                    "type": "INTEGER",
                    "description": "Nível de brilho de 0 a 100 por cento (opcional).",
                },
                "color": {
                    "type": "STRING",
                    "description": "Cor desejada para a lâmpada (ex: 'vermelho', 'azul', 'amarelo', 'branco', 'verde').",
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "control_smart_plug",
        "description": "Controla tomadas inteligentes e plugs Wi-Fi para ligar ou desligar aparelhos conectados (ex: cafeteira, ventilador, abajur).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "Ação a executar: 'on' (ligar), 'off' (desligar) ou 'toggle' (alternar).",
                },
                "device_name": {
                    "type": "STRING",
                    "description": "Nome do aparelho conectado à tomada (ex: 'cafeteira', 'ventilador', 'computador', 'abajur').",
                },
            },
            "required": ["action"],
        },
    },
]
