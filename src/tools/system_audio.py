"""System Audio and Media Control Tool for Aton.

Provides Windows master volume adjustments, muting/unmuting, and
universal multimedia playback controls (play/pause, next, prev, stop).
"""

import ctypes
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Windows Virtual-Key Codes for Multimedia
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_STOP = 0xB2
VK_MEDIA_PLAY_PAUSE = 0xB3
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002


def _send_media_key(vk_code: int) -> None:
    """Send a virtual keyboard multimedia event in Windows."""
    user32 = ctypes.windll.user32
    user32.keybd_event(vk_code, 0, KEYEVENTF_EXTENDEDKEY, 0)
    user32.keybd_event(vk_code, 0, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0)


def set_system_volume(
    level: Optional[int] = None,
    mute: Optional[bool] = None,
) -> Dict[str, Any]:
    """Adjust the Windows master volume level and/or toggle mute.

    Args:
        level: Integer target volume percentage from 0 to 100.
        mute: Boolean to mute (True) or unmute (False).

    Returns:
        Dict with status, message in Portuguese, and audio status details.
    """
    try:
        from pycaw.pycaw import AudioUtilities

        speakers = AudioUtilities.GetSpeakers()
        if not speakers:
            return {
                "status": "error",
                "message": "Nenhum dispositivo de alto-falante padrão foi encontrado no Windows.",
            }

        # Apply mute if specified
        if mute is not None:
            mute_int = 1 if mute else 0
            speakers.EndpointVolume.SetMute(mute_int, None)
            logger.info(f"System master mute set to: {mute}")

        # Apply volume level if specified
        if level is not None:
            clamped_level = max(0, min(100, int(level)))
            speakers.volume_percent = float(clamped_level)
            logger.info(f"System master volume set to: {clamped_level}%")

        # Read back current state
        curr_vol = round(speakers.volume_percent)
        is_muted = bool(speakers.EndpointVolume.GetMute())

        if mute is True:
            msg = f"O som do computador foi colocado no mudo (volume estava em {curr_vol}%)."
        elif mute is False and level is None:
            msg = f"O som do computador foi desmutado (volume atual em {curr_vol}%)."
        elif level is not None:
            mute_status_str = " (em mudo)" if is_muted else ""
            msg = f"Volume mestre do Windows ajustado para {curr_vol}%{mute_status_str}."
        else:
            msg = f"Volume atual do computador está em {curr_vol}%{' (mudo)' if is_muted else ''}."

        return {
            "status": "success",
            "message": msg,
            "volume_percent": curr_vol,
            "is_muted": is_muted,
        }

    except Exception as e:
        logger.error(f"Error setting system volume: {e}", exc_info=True)
        return {
            "status": "error",
            "message": f"Falha ao ajustar o volume do Windows: {str(e)}",
        }


def control_system_media(action: str) -> Dict[str, Any]:
    """Control universal multimedia playback on Windows (Spotify, YouTube, Media Player).

    Args:
        action: Multimedia action ('play_pause', 'next', 'previous', 'stop').

    Returns:
        Dict with status and conversational message in Portuguese.
    """
    normalized_action = (action or "").lower().strip()

    action_map = {
        "play_pause": (VK_MEDIA_PLAY_PAUSE, "Reprodução alternada (Play/Pause)"),
        "play": (VK_MEDIA_PLAY_PAUSE, "Reprodução acionada (Play)"),
        "pause": (VK_MEDIA_PLAY_PAUSE, "Mídia pausada"),
        "next": (VK_MEDIA_NEXT_TRACK, "Avançado para a próxima faixa"),
        "next_track": (VK_MEDIA_NEXT_TRACK, "Avançado para a próxima faixa"),
        "prev": (VK_MEDIA_PREV_TRACK, "Retornado para a faixa anterior"),
        "previous": (VK_MEDIA_PREV_TRACK, "Retornado para a faixa anterior"),
        "previous_track": (VK_MEDIA_PREV_TRACK, "Retornado para a faixa anterior"),
        "stop": (VK_MEDIA_STOP, "Reprodução de mídia interrompida"),
    }

    if normalized_action not in action_map:
        return {
            "status": "error",
            "message": f"Ação multimídia inválida '{action}'. Escolha entre: 'play_pause', 'next', 'previous' ou 'stop'.",
        }

    vk_code, desc = action_map[normalized_action]

    try:
        _send_media_key(vk_code)
        logger.info(f"Simulated Windows media key: {normalized_action} (VK: 0x{vk_code:X})")
        return {
            "status": "success",
            "message": f"Com certeza, senhor. {desc}.",
            "action": normalized_action,
        }
    except Exception as e:
        logger.error(f"Error triggering media key: {e}", exc_info=True)
        return {
            "status": "error",
            "message": f"Não foi possível controlar a mídia do Windows: {str(e)}",
        }


# Declarations for Gemini Live API
SYSTEM_AUDIO_FUNCTION_DECLARATIONS = [
    {
        "name": "set_system_volume",
        "description": "Ajusta o volume de som mestre do computador Windows (0 a 100%) ou coloca/remove o som do modo mudo.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "level": {
                    "type": "INTEGER",
                    "description": "Nível de volume desejado de 0 a 100.",
                },
                "mute": {
                    "type": "BOOLEAN",
                    "description": "Defina como True para mutar ou False para desmutar.",
                },
            },
        },
    },
    {
        "name": "control_system_media",
        "description": "Controla a reprodução multimídia no Windows (Play/Pause, avançar música, voltar música ou parar), compatível com Spotify, reprodutores e navegadores.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "Ação a ser executada: 'play_pause' (pausar ou despausar), 'next' (próxima faixa), 'previous' (faixa anterior) ou 'stop' (parar).",
                }
            },
            "required": ["action"],
        },
    },
]


def dispatch_audio_control_tool(tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
    """Dispatch system audio control tool calls."""
    if tool_name == "set_system_volume":
        level = tool_args.get("level")
        mute = tool_args.get("mute")
        return set_system_volume(level=level, mute=mute)
    elif tool_name == "control_system_media":
        action = tool_args.get("action", "play_pause")
        return control_system_media(action=action)
    return {
        "status": "error",
        "message": f"Ferramenta de áudio do sistema desconhecida '{tool_name}'.",
    }
