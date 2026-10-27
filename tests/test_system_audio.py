"""Tests for Windows System Audio and Media Controls (Phase 6)."""

from unittest.mock import MagicMock, patch
import pytest
from src.tools.system_audio import (
    SYSTEM_AUDIO_FUNCTION_DECLARATIONS,
    control_system_media,
    dispatch_audio_control_tool,
    set_system_volume,
)
from src.tools import ALL_ATON_TOOLS, dispatch_tool


def test_control_system_media_valid_actions():
    """Verify universal media control handles play_pause, next, prev, stop."""
    with patch("src.tools.system_audio._send_media_key") as mock_key:
        res_play = control_system_media("play_pause")
        assert res_play["status"] == "success"
        assert "Reprodução alternada" in res_play["message"]
        assert mock_key.call_count == 1

        res_next = control_system_media("next")
        assert res_next["status"] == "success"
        assert "próxima faixa" in res_next["message"].lower()

        res_prev = control_system_media("previous")
        assert res_prev["status"] == "success"
        assert "faixa anterior" in res_prev["message"].lower()

        res_stop = control_system_media("stop")
        assert res_stop["status"] == "success"
        assert "interrompida" in res_stop["message"].lower()


def test_control_system_media_invalid_action():
    """Verify invalid action returns an error."""
    res = control_system_media("invalid_action_xyz")
    assert res["status"] == "error"
    assert "inválida" in res["message"]


def test_set_system_volume_read_and_mock():
    """Verify setting system volume and mute with pycaw AudioUtilities."""
    mock_speakers = MagicMock()
    mock_speakers.volume_percent = 45.0
    mock_speakers.EndpointVolume.GetMute.return_value = 0

    with patch("pycaw.pycaw.AudioUtilities.GetSpeakers", return_value=mock_speakers):
        # Set level
        res = set_system_volume(level=60)
        assert res["status"] == "success"
        assert mock_speakers.volume_percent == 60.0
        assert "60%" in res["message"]

        # Set mute
        res_mute = set_system_volume(mute=True)
        assert res_mute["status"] == "success"
        mock_speakers.EndpointVolume.SetMute.assert_called_with(1, None)
        assert "mudo" in res_mute["message"]


def test_dispatch_audio_control_tool():
    """Verify audio control tool dispatcher."""
    with patch("src.tools.system_audio._send_media_key"):
        res = dispatch_audio_control_tool("control_system_media", {"action": "play_pause"})
        assert res["status"] == "success"

        # Unknown tool
        err_res = dispatch_audio_control_tool("unknown_audio_tool", {})
        assert err_res["status"] == "error"


def test_unified_dispatch_audio_tools():
    """Verify dispatch_tool routes audio tools correctly."""
    with patch("src.tools.system_audio._send_media_key"):
        res = dispatch_tool("control_system_media", {"action": "next"})
        assert res["status"] == "success"


def test_audio_tools_in_all_aton_tools():
    """Verify set_system_volume and control_system_media are in ALL_ATON_TOOLS."""
    names = [t["name"] for t in ALL_ATON_TOOLS]
    assert "set_system_volume" in names
    assert "control_system_media" in names
    assert len(ALL_ATON_TOOLS) == 31
