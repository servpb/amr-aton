"""Unit tests for Smart TV and Media Device Control (Phase 2)."""

from unittest.mock import MagicMock, patch
import pytest

from src.tools import ALL_ATON_TOOLS, dispatch_tool
from src.tools.smart_tv import (
    SMART_TV_FUNCTION_DECLARATIONS,
    control_tv_media,
    control_tv_power,
    control_tv_volume,
    dispatch_tv_tool,
    get_tv_status,
    launch_tv_app,
    send_wake_on_lan,
)


def test_smart_tv_declarations_schema():
    """Verify Smart TV function declarations conform to expected schema."""
    assert len(SMART_TV_FUNCTION_DECLARATIONS) == 5
    names = [t["name"] for t in SMART_TV_FUNCTION_DECLARATIONS]
    assert "control_tv_volume" in names
    assert "control_tv_media" in names
    assert "control_tv_power" in names
    assert "launch_tv_app" in names
    assert "get_tv_status" in names

    for decl in SMART_TV_FUNCTION_DECLARATIONS:
        assert "name" in decl
        assert "description" in decl
        assert "parameters" in decl
        assert decl["parameters"]["type"] == "OBJECT"


@patch("socket.socket")
def test_send_wake_on_lan_valid_mac(mock_socket_class):
    """Verify Wake-on-LAN constructs packet and transmits via broadcast."""
    mock_socket = MagicMock()
    mock_socket_class.return_value.__enter__.return_value = mock_socket

    success = send_wake_on_lan("AA:BB:CC:DD:EE:FF")
    assert success is True
    mock_socket.sendto.assert_called_once()
    packet, target = mock_socket.sendto.call_args[0]
    assert len(packet) == 102
    assert packet.startswith(b"\xff" * 6)
    assert target == ("255.255.255.255", 9)


def test_send_wake_on_lan_invalid_mac():
    """Verify Wake-on-LAN safely rejects malformed MAC address."""
    success = send_wake_on_lan("invalid-mac")
    assert success is False


@patch("src.tools.smart_tv.send_wake_on_lan")
def test_control_tv_power_on_with_mac(mock_wol):
    """Verify turning TV on triggers Wake-on-LAN."""
    mock_wol.return_value = True
    result = control_tv_power(action="on", mac_address="AA:BB:CC:DD:EE:FF")
    assert result["status"] == "success"
    assert "inicialização" in result["message"]
    mock_wol.assert_called_once_with("AA:BB:CC:DD:EE:FF")


def test_control_tv_power_on_without_mac():
    """Verify turning TV on without MAC gives informative instruction."""
    result = control_tv_power(action="on", mac_address=None, ip=None)
    assert result["status"] == "warning"
    assert "SMART_TV_MAC" in result["message"]


def test_control_tv_power_off_with_ip():
    """Verify turning TV off with IP address confirms command."""
    result = control_tv_power(action="off", ip="192.168.1.50")
    assert result["status"] == "success"
    assert "desligar" in result["message"]


def test_control_tv_volume_actions():
    """Verify volume mute, up, down, and set actions."""
    res_mute = control_tv_volume(action="mute", ip="192.168.1.50")
    assert res_mute["status"] == "success"
    assert "mudo" in res_mute["message"]

    res_unmute = control_tv_volume(action="unmute", ip="192.168.1.50")
    assert res_unmute["status"] == "success"
    assert "restaurado" in res_unmute["message"]

    res_up = control_tv_volume(action="up", ip="192.168.1.50")
    assert res_up["status"] == "success"
    assert "aumentado" in res_up["message"]

    res_set = control_tv_volume(action="set", level=25, ip="192.168.1.50")
    assert res_set["status"] == "success"
    assert "25%" in res_set["message"]


def test_control_tv_volume_unconfigured():
    """Verify volume command without IP returns warning."""
    result = control_tv_volume(action="up", ip=None)
    assert result["status"] == "warning"
    assert "SMART_TV_IP" in result["message"]


def test_control_tv_media_actions():
    """Verify media play and pause actions."""
    res_pause = control_tv_media(action="pause", ip="192.168.1.50")
    assert res_pause["status"] == "success"
    assert "pausada" in res_pause["message"]

    res_play = control_tv_media(action="play", ip="192.168.1.50")
    assert res_play["status"] == "success"
    assert "retomada" in res_play["message"]


@patch("urllib.request.urlopen")
def test_launch_tv_app(mock_urlopen):
    """Verify launching TV app via DIAL HTTP POST."""
    mock_resp = MagicMock()
    mock_resp.status = 201
    mock_urlopen.return_value.__enter__.return_value = mock_resp

    result = launch_tv_app(app_name="YouTube", ip="192.168.1.50")
    assert result["status"] == "success"
    assert "YouTube" in result["message"]


@patch("src.tools.smart_tv.is_port_open")
def test_get_tv_status_online(mock_port):
    """Verify get_tv_status reports online when TV ports respond."""
    mock_port.return_value = True
    result = get_tv_status(ip="192.168.1.50")
    assert result["status"] == "online"
    assert "online" in result["message"]


@patch("src.tools.smart_tv.is_port_open")
def test_get_tv_status_offline(mock_port):
    """Verify get_tv_status reports offline when ports do not respond."""
    mock_port.return_value = False
    result = get_tv_status(ip="192.168.1.50")
    assert result["status"] == "offline"


def test_dispatch_tv_tool():
    """Verify dispatch_tv_tool correctly routes tool calls."""
    with patch("src.tools.smart_tv.control_tv_volume") as mock_vol:
        mock_vol.return_value = {"status": "success"}
        res = dispatch_tv_tool("control_tv_volume", {"action": "mute"})
        assert res["status"] == "success"
        mock_vol.assert_called_once_with(action="mute", level=None)

    with patch("src.tools.smart_tv.control_tv_media") as mock_med:
        mock_med.return_value = {"status": "success"}
        res = dispatch_tv_tool("control_tv_media", {"action": "play"})
        assert res["status"] == "success"
        mock_med.assert_called_once_with(action="play")

    res_unknown = dispatch_tv_tool("unknown_tv_tool", {})
    assert res_unknown["status"] == "error"


def test_unified_dispatcher_with_tv():
    """Verify unified dispatcher routes TV tools properly."""
    with patch("src.tools.dispatch_tv_tool") as mock_tv:
        mock_tv.return_value = {"status": "success"}
        res = dispatch_tool("control_tv_volume", {"action": "up"})
        assert res["status"] == "success"
        mock_tv.assert_called_once()


def test_all_aton_tools_combined():
    """Verify ALL_ATON_TOOLS combines at least 11 tools."""
    assert len(ALL_ATON_TOOLS) >= 11
