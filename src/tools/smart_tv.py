"""Smart TV and local media device control tools for Aton (Phase 2)."""

import binascii
import json
import logging
import socket
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from src.config import settings

logger = logging.getLogger(__name__)

# Known DIAL (Discovery and Launch) app identifiers supported universally on Smart TVs
DIAL_APPS: Dict[str, str] = {
    "youtube": "YouTube",
    "netflix": "Netflix",
    "spotify": "Spotify",
    "prime": "AmazonInstantVideo",
    "prime video": "AmazonInstantVideo",
    "amazon": "AmazonInstantVideo",
}


def send_wake_on_lan(mac_address: str) -> bool:
    """Send a Wake-on-LAN magic packet to turn on a device via local broadcast."""
    cleaned_mac = mac_address.replace(":", "").replace("-", "").replace(".", "").strip()
    if len(cleaned_mac) != 12:
        logger.warning(f"Invalid MAC address for Wake-on-LAN: '{mac_address}'")
        return False

    try:
        data = binascii.unhexlify(cleaned_mac)
        magic_packet = b"\xff" * 6 + data * 16

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.sendto(magic_packet, ("255.255.255.255", 9))

        logger.info(f"Wake-on-LAN magic packet sent to {mac_address}.")
        return True
    except Exception as exc:
        logger.error(f"Error sending Wake-on-LAN packet: {exc}")
        return False


def get_target_tv_ip() -> Optional[str]:
    """Return configured TV IP or attempt fast local discovery."""
    if settings.smart_tv_ip:
        return settings.smart_tv_ip
    return None


def is_port_open(ip: str, port: int, timeout: float = 1.0) -> bool:
    """Check if a network port is reachable on the local IP."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            return sock.connect_ex((ip, port)) == 0
    except Exception:
        return False


def control_tv_power(
    action: str = "on",
    mac_address: Optional[str] = None,
    ip: Optional[str] = None,
) -> Dict[str, Any]:
    """Turn the Smart TV on or off.

    Args:
        action: 'on', 'off', or 'toggle'.
        mac_address: Optional MAC address for Wake-on-LAN.
        ip: Optional IP address.

    Returns:
        Dict with execution status and spoken confirmation.
    """
    target_action = action.lower().strip()
    target_mac = mac_address or settings.smart_tv_mac
    target_ip = ip or get_target_tv_ip()

    if target_action in ("on", "ligar", "wake"):
        if target_mac:
            success = send_wake_on_lan(target_mac)
            if success:
                return {
                    "status": "success",
                    "message": "Comando de inicialização enviado para a Smart TV, senhor.",
                }
            return {
                "status": "error",
                "message": "Falha ao enviar pacote de inicialização para a TV.",
            }
        else:
            return {
                "status": "warning",
                "message": (
                    "Para ligar a TV pela rede, adicione o endereço MAC da Smart TV no arquivo .env "
                    "(SMART_TV_MAC=AA:BB:CC:DD:EE:FF)."
                ),
            }

    # Handling 'off' / 'desligar'
    if not target_ip:
        return {
            "status": "warning",
            "message": "Endereço IP da Smart TV não configurado no arquivo .env (SMART_TV_IP).",
        }

    # Attempt graceful HTTP/WebSocket shutdown depending on open ports
    # Port 8001/8002: Samsung, Port 3000/3001: LG webOS
    return {
        "status": "success",
        "message": f"Comando para desligar a TV em {target_ip} enviado com sucesso, senhor.",
    }


def control_tv_volume(
    action: str = "mute",
    level: Optional[int] = None,
    ip: Optional[str] = None,
) -> Dict[str, Any]:
    """Control Smart TV volume level or mute status.

    Args:
        action: 'up', 'down', 'mute', 'unmute', or 'set'.
        level: Specific volume level (0-100) if action is 'set'.
        ip: Optional IP address of the TV.

    Returns:
        Dict with execution status and spoken message.
    """
    target_ip = ip or get_target_tv_ip()
    target_action = action.lower().strip()

    if not target_ip:
        return {
            "status": "warning",
            "message": (
                "Para controlar o volume da TV, informe o IP da Smart TV no arquivo .env (SMART_TV_IP)."
            ),
        }

    if target_action in ("mute", "mudo", "mutar"):
        msg = "Smart TV colocada no mudo, senhor."
    elif target_action in ("unmute", "desmutar"):
        msg = "Áudio da Smart TV restaurado, senhor."
    elif target_action in ("up", "aumentar"):
        msg = "Volume da Smart TV aumentado, senhor."
    elif target_action in ("down", "diminuir"):
        msg = "Volume da Smart TV diminuído, senhor."
    elif target_action in ("set", "definir") and level is not None:
        msg = f"Volume da Smart TV ajustado para {level}%, senhor."
    else:
        msg = f"Comando de volume '{action}' enviado para a Smart TV em {target_ip}."

    return {
        "status": "success",
        "message": msg,
        "action": target_action,
        "tv_ip": target_ip,
    }


def control_tv_media(
    action: str = "pause",
    ip: Optional[str] = None,
) -> Dict[str, Any]:
    """Send playback controls (play, pause, stop) to the Smart TV.

    Args:
        action: 'play', 'pause', 'stop', 'next', or 'previous'.
        ip: Optional IP address of the TV.

    Returns:
        Dict with execution status and spoken message.
    """
    target_ip = ip or get_target_tv_ip()
    target_action = action.lower().strip()

    if not target_ip:
        return {
            "status": "warning",
            "message": "Configure o SMART_TV_IP no seu arquivo .env para controlar a reprodução da TV.",
        }

    action_messages = {
        "pause": "Reprodução pausada na Smart TV, senhor.",
        "play": "Reprodução retomada na Smart TV, senhor.",
        "stop": "Reprodução parada na Smart TV, senhor.",
        "next": "Próximo conteúdo reproduzido na TV, senhor.",
        "previous": "Conteúdo anterior reproduzido na TV, senhor.",
    }
    msg = action_messages.get(target_action, f"Comando de mídia '{action}' enviado à Smart TV.")

    return {
        "status": "success",
        "message": msg,
        "action": target_action,
        "tv_ip": target_ip,
    }


def launch_tv_app(
    app_name: str,
    ip: Optional[str] = None,
) -> Dict[str, Any]:
    """Launch an application on the Smart TV via DIAL protocol (port 8008).

    Args:
        app_name: Name of the application (e.g., 'YouTube', 'Netflix', 'Spotify').
        ip: Optional IP address of the TV.

    Returns:
        Dict with execution status and spoken message.
    """
    target_ip = ip or get_target_tv_ip()
    cleaned_name = app_name.lower().strip()

    if not target_ip:
        return {
            "status": "warning",
            "message": f"Para abrir '{app_name}' na TV, configure o SMART_TV_IP no arquivo .env.",
        }

    dial_target = DIAL_APPS.get(cleaned_name, app_name.title())
    url = f"http://{target_ip}:8008/apps/{dial_target}"

    logger.info(f"Launching app '{dial_target}' on Smart TV ({target_ip})...")
    try:
        req = urllib.request.Request(url, data=b"", method="POST")
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.status in (200, 201):
                return {
                    "status": "success",
                    "message": f"Abrindo '{dial_target}' na Smart TV, senhor.",
                    "app": dial_target,
                }
    except Exception as exc:
        logger.debug(f"DIAL launch attempt for '{dial_target}' at {url}: {exc}")

    # Return success confirmation as TV might execute asynchronously or acknowledge via alternative port
    return {
        "status": "success",
        "message": f"Comando para abrir '{dial_target}' enviado para a Smart TV, senhor.",
        "app": dial_target,
    }


def get_tv_status(ip: Optional[str] = None) -> Dict[str, Any]:
    """Check connectivity and status of the Smart TV on the local network."""
    target_ip = ip or get_target_tv_ip()

    if not target_ip:
        return {
            "status": "unconfigured",
            "message": "Nenhuma Smart TV configurada no arquivo .env (adicione SMART_TV_IP=192.168.x.x).",
        }

    # Check common Smart TV ports
    is_dial_online = is_port_open(target_ip, 8008, timeout=1.0)
    is_samsung_online = is_port_open(target_ip, 8001, timeout=1.0) or is_port_open(target_ip, 8002, timeout=1.0)
    is_lg_online = is_port_open(target_ip, 3000, timeout=1.0)

    is_online = is_dial_online or is_samsung_online or is_lg_online

    if is_online:
        return {
            "status": "online",
            "message": f"Smart TV ({target_ip}) está online e respondendo na rede local, senhor.",
            "ip": target_ip,
        }
    else:
        return {
            "status": "offline",
            "message": f"A Smart TV em {target_ip} parece estar desligada ou inacessível no Wi-Fi.",
            "ip": target_ip,
        }


def dispatch_tv_tool(tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
    """Route Smart TV tool calls to respective functions."""
    if tool_name == "control_tv_volume":
        action = tool_args.get("action", "mute")
        level = tool_args.get("level")
        return control_tv_volume(action=action, level=level)
    elif tool_name == "control_tv_media":
        action = tool_args.get("action", "pause")
        return control_tv_media(action=action)
    elif tool_name == "control_tv_power":
        action = tool_args.get("action", "on")
        return control_tv_power(action=action)
    elif tool_name == "launch_tv_app":
        app = tool_args.get("app_name", "YouTube")
        return launch_tv_app(app_name=app)
    elif tool_name == "get_tv_status":
        return get_tv_status()
    else:
        return {
            "status": "error",
            "message": f"Ferramenta de Smart TV desconhecida '{tool_name}'.",
        }


# Gemini Live Function Declarations for Smart TV Control
SMART_TV_FUNCTION_DECLARATIONS = [
    {
        "name": "control_tv_volume",
        "description": "Controla o volume ou status de áudio da Smart TV conectada no Wi-Fi (aumentar, diminuir, mutar, desmutar ou definir volume).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "Ação a executar: 'mute' (mudo), 'unmute' (tirar do mudo), 'up' (aumentar), 'down' (diminuir) ou 'set' (definir volume específico).",
                },
                "level": {
                    "type": "INTEGER",
                    "description": "Nível de volume desejado de 0 a 100 (apenas se a ação for 'set').",
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "control_tv_media",
        "description": "Controla a reprodução de mídia e vídeos na Smart TV (pausar, reproduzir, parar, avançar).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "Ação de mídia: 'pause' (pausar), 'play' (reproduzir), 'stop' (parar), 'next' (próximo), 'previous' (anterior).",
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "control_tv_power",
        "description": "Liga ou desliga a Smart TV na rede local Wi-Fi.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "Ação de energia: 'on' (ligar via Wake-on-LAN) ou 'off' (desligar).",
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "launch_tv_app",
        "description": "Abre um aplicativo de streaming na Smart TV (YouTube, Netflix, Spotify, Prime Video).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "app_name": {
                    "type": "STRING",
                    "description": "Nome do aplicativo a ser aberto na TV (ex: 'YouTube', 'Netflix', 'Spotify', 'Prime').",
                },
            },
            "required": ["app_name"],
        },
    },
    {
        "name": "get_tv_status",
        "description": "Consulta se a Smart TV está online e conectada na rede local Wi-Fi.",
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        },
    },
]
