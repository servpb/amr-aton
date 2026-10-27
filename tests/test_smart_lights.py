"""Unit tests for Smart Lights and Smart Plugs control tool (Phase 2)."""

from unittest.mock import MagicMock, patch
import pytest

from src.tools import ALL_ATON_TOOLS, dispatch_tool
from src.tools.smart_lights import (
    SMART_LIGHTS_FUNCTION_DECLARATIONS,
    control_lights,
    control_smart_plug,
    dispatch_lights_tool,
)


def test_smart_lights_declarations_schema():
    """Verify smart lights function declarations schema."""
    assert len(SMART_LIGHTS_FUNCTION_DECLARATIONS) == 2
    names = [t["name"] for t in SMART_LIGHTS_FUNCTION_DECLARATIONS]
    assert "control_lights" in names
    assert "control_smart_plug" in names

    for decl in SMART_LIGHTS_FUNCTION_DECLARATIONS:
        assert "name" in decl
        assert "description" in decl
        assert "parameters" in decl
        assert decl["parameters"]["type"] == "OBJECT"


def test_control_lights_messages():
    """Verify light on, off, brightness, and color confirmation messages."""
    res_on = control_lights(action="on", room="quarto")
    assert "Luzes do Quarto acesas" in res_on["message"]

    res_off = control_lights(action="off", room="sala")
    assert "Luzes do Sala apagadas" in res_off["message"]

    res_params = control_lights(
        action="on",
        room="escritório",
        brightness=75,
        color="azul",
    )
    assert "75%" in res_params["message"]
    assert "azul" in res_params["message"]


@patch("urllib.request.urlopen")
def test_control_lights_with_bridge(mock_urlopen):
    """Verify control_lights sends HTTP PUT when bridge is configured."""
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_urlopen.return_value.__enter__.return_value = mock_resp

    result = control_lights(action="on", bridge_ip="192.168.1.80")
    assert result["status"] == "success"
    mock_urlopen.assert_called_once()


def test_control_smart_plug_messages():
    """Verify smart plug on and off confirmation messages."""
    res_on = control_smart_plug(action="on", device_name="cafeteira")
    assert "Cafeteira ligada" in res_on["message"]

    res_off = control_smart_plug(action="off", device_name="ventilador")
    assert "Ventilador desligada" in res_off["message"]


@patch("urllib.request.urlopen")
def test_control_smart_plug_with_ip(mock_urlopen):
    """Verify smart plug sends HTTP POST when device IP is provided."""
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_urlopen.return_value.__enter__.return_value = mock_resp

    result = control_smart_plug(action="on", device_name="abajur", ip="192.168.1.85")
    assert result["status"] == "success"
    mock_urlopen.assert_called_once()


def test_dispatch_lights_tool():
    """Verify dispatch_lights_tool routes calls properly."""
    with patch("src.tools.smart_lights.control_lights") as mock_l:
        mock_l.return_value = {"status": "success"}
        res = dispatch_lights_tool(
            "control_lights",
            {"action": "on", "room": "sala", "brightness": 50},
        )
        assert res["status"] == "success"
        mock_l.assert_called_once_with(action="on", room="sala", brightness=50, color=None)

    with patch("src.tools.smart_lights.control_smart_plug") as mock_p:
        mock_p.return_value = {"status": "success"}
        res = dispatch_lights_tool(
            "control_smart_plug",
            {"action": "off", "device_name": "cafeteira"},
        )
        assert res["status"] == "success"
        mock_p.assert_called_once_with(action="off", device_name="cafeteira")

    res_unknown = dispatch_lights_tool("unknown_lights_tool", {})
    assert res_unknown["status"] == "error"


def test_unified_dispatcher_lights_and_plug():
    """Verify unified dispatcher routes light and plug tools."""
    with patch("src.tools.dispatch_lights_tool") as mock_dl:
        mock_dl.return_value = {"status": "success"}
        res1 = dispatch_tool("control_lights", {"action": "on"})
        assert res1["status"] == "success"

        res2 = dispatch_tool("control_smart_plug", {"action": "off"})
        assert res2["status"] == "success"
        assert mock_dl.call_count == 2


def test_total_all_aton_tools_count():
    """Verify complete tools list contains at least 14 active tools."""
    assert len(ALL_ATON_TOOLS) >= 14
