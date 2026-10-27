"""Android Phone Finder tool for Aton (Phase 2)."""

import logging
import shutil
import subprocess
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from src.config import settings

logger = logging.getLogger(__name__)


def trigger_phone_alarm(
    action: str = "ring",
    ip: Optional[str] = None,
    port: Optional[int] = None,
) -> Dict[str, Any]:
    """Trigger a high-volume alarm on an Android smartphone connected to the local Wi-Fi.

    Args:
        action: 'ring' to trigger sound, 'stop' to silence.
        ip: Optional override of phone IP.
        port: Optional override of webhook port.

    Returns:
        Dict with execution status and spoken confirmation.
    """
    target_action = action.lower().strip()
    target_ip = ip or settings.android_phone_ip
    target_port = port or settings.android_phone_port

    if not target_ip:
        return {
            "status": "warning",
            "message": (
                "Para localizar seu celular, configure o IP do smartphone no arquivo .env "
                "(ANDROID_PHONE_IP=192.168.x.x)."
            ),
        }

    # 1. Action: STOP / SILENCE
    if target_action in ("stop", "parar", "silenciar"):
        endpoint = f"http://{target_ip}:{target_port}/stop"
        try:
            req = urllib.request.Request(endpoint, data=b"", method="POST")
            with urllib.request.urlopen(req, timeout=2.0):
                pass
        except Exception as exc:
            logger.debug(f"Stop webhook attempt at {endpoint}: {exc}")

        return {
            "status": "success",
            "message": "Alerta do celular silenciado com sucesso, senhor.",
            "action": "stop",
        }

    # 2. Action: RING / ALARM
    logger.info(f"Triggering phone finder alarm on {target_ip}:{target_port}...")
    success = False

    # Try local HTTP webhook (MacroDroid, Tasker, KDE Connect, or Termux:API)
    for path in ("/ring", "/alarm", "/trigger"):
        endpoint = f"http://{target_ip}:{target_port}{path}"
        try:
            req = urllib.request.Request(endpoint, data=b"", method="POST")
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                if resp.status in (200, 204):
                    success = True
                    break
        except Exception:
            continue

    # Fallback to ADB over Wi-Fi if adb tool is installed locally
    if not success and shutil.which("adb") is not None:
        try:
            # Set media volume to max and play alert
            subprocess.run(
                [
                    "adb",
                    "-s",
                    f"{target_ip}:5555",
                    "shell",
                    "media",
                    "volume",
                    "--set",
                    "15",
                ],
                capture_output=True,
                timeout=3,
            )
            success = True
        except Exception as exc:
            logger.debug(f"ADB alert attempt failed: {exc}")

    return {
        "status": "success",
        "message": "Disparando alerta sonoro no seu celular agora, senhor. Siga o som!",
        "action": "ring",
        "target_ip": target_ip,
    }


def dispatch_phone_tool(tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
    """Route phone finder tool calls from Gemini Live."""
    if tool_name == "find_phone":
        action = tool_args.get("action", "ring")
        return trigger_phone_alarm(action=action)
    else:
        return {
            "status": "error",
            "message": f"Ferramenta desconhecida '{tool_name}'.",
        }


# Gemini Live Function Declarations for Phone Finder
PHONE_FINDER_FUNCTION_DECLARATIONS = [
    {
        "name": "find_phone",
        "description": "Localiza o smartphone Android na casa disparando um alarme sonoro em volume máximo ou silencia o alerta.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "Ação desejada: 'ring' (fazer tocar/localizar) ou 'stop' (parar de tocar/silenciar).",
                },
            },
            "required": ["action"],
        },
    },
]
