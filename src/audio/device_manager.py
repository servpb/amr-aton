"""Audio device discovery and management for Windows."""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    import sounddevice as sd
except ImportError:
    sd = None  # type: ignore
    logger.warning("sounddevice is not installed. Audio features will run in mock/fallback mode.")


def list_audio_devices() -> List[Dict[str, Any]]:
    """List all available audio input and output devices.

    Returns:
        List of dictionaries containing device index, name, and channel capabilities.
    """
    if sd is None:
        logger.warning("Cannot list audio devices: sounddevice is not available.")
        return []

    devices = []
    try:
        all_devices = sd.query_devices()
        for idx, dev in enumerate(all_devices):
            devices.append({
                "index": idx,
                "name": dev.get("name", "Unknown"),
                "max_input_channels": dev.get("max_input_channels", 0),
                "max_output_channels": dev.get("max_output_channels", 0),
                "default_samplerate": dev.get("default_samplerate", 44100),
            })
    except Exception as exc:
        logger.error(f"Error querying audio devices: {exc}")
    return devices


def get_default_input_device() -> Optional[Dict[str, Any]]:
    """Get the system's default audio input device (microphone)."""
    if sd is None:
        return None
    try:
        dev_info = sd.query_devices(kind="input")
        return dict(dev_info) if dev_info else None
    except Exception as exc:
        logger.warning(f"Could not determine default input device: {exc}")
        return None


def get_default_output_device() -> Optional[Dict[str, Any]]:
    """Get the system's default audio output device (speakers/headphones)."""
    if sd is None:
        return None
    try:
        dev_info = sd.query_devices(kind="output")
        return dict(dev_info) if dev_info else None
    except Exception as exc:
        logger.warning(f"Could not determine default output device: {exc}")
        return None
