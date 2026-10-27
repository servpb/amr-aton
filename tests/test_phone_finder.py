"""Unit tests for Phone Finder tool (Phase 2)."""

from unittest.mock import MagicMock, patch
import pytest

from src.tools import ALL_ATON_TOOLS, dispatch_tool
from src.tools.phone_finder import (
    PHONE_FINDER_FUNCTION_DECLARATIONS,
    dispatch_phone_tool,
    trigger_phone_alarm,
)


def test_phone_finder_declarations_schema():
    """Verify phone finder declarations conform to schema."""
    assert len(PHONE_FINDER_FUNCTION_DECLARATIONS) == 1
    decl = PHONE_FINDER_FUNCTION_DECLARATIONS[0]
    assert decl["name"] == "find_phone"
    assert "description" in decl
    assert "parameters" in decl
    assert decl["parameters"]["type"] == "OBJECT"


def test_trigger_phone_alarm_unconfigured():
    """Verify informative warning when no phone IP is configured."""
    result = trigger_phone_alarm(action="ring", ip=None)
    assert result["status"] == "warning"
    assert "ANDROID_PHONE_IP" in result["message"]


@patch("urllib.request.urlopen")
def test_trigger_phone_alarm_ring_success(mock_urlopen):
    """Verify phone alarm trigger calls webhook."""
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_urlopen.return_value.__enter__.return_value = mock_resp

    result = trigger_phone_alarm(action="ring", ip="192.168.1.100", port=8080)
    assert result["status"] == "success"
    assert "alerta sonoro" in result["message"]
    assert result["action"] == "ring"


@patch("urllib.request.urlopen")
def test_trigger_phone_alarm_stop_success(mock_urlopen):
    """Verify phone alarm silence calls stop endpoint."""
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_urlopen.return_value.__enter__.return_value = mock_resp

    result = trigger_phone_alarm(action="stop", ip="192.168.1.100", port=8080)
    assert result["status"] == "success"
    assert "silenciado" in result["message"]
    assert result["action"] == "stop"


def test_dispatch_phone_tool():
    """Verify dispatch_phone_tool routes find_phone."""
    with patch("src.tools.phone_finder.trigger_phone_alarm") as mock_alarm:
        mock_alarm.return_value = {"status": "success"}
        res = dispatch_phone_tool("find_phone", {"action": "ring"})
        assert res["status"] == "success"
        mock_alarm.assert_called_once_with(action="ring")

    res_unknown = dispatch_phone_tool("unknown_tool", {})
    assert res_unknown["status"] == "error"


def test_unified_dispatcher_phone():
    """Verify unified dispatch_tool routes find_phone."""
    with patch("src.tools.dispatch_phone_tool") as mock_p:
        mock_p.return_value = {"status": "success"}
        res = dispatch_tool("find_phone", {"action": "ring"})
        assert res["status"] == "success"
        mock_p.assert_called_once()
