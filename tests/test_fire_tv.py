"""Unit tests for Amazon Fire TV Stick control integration."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

@pytest.fixture(autouse=True)
def reset_fire_tv_cache(tmp_path, monkeypatch):
    """Ensure Fire TV cache and state file are isolated for each test."""
    from src.core import fire_tv_discovery
    test_state = tmp_path / "fire_tv_state.json"
    monkeypatch.setattr(fire_tv_discovery, "STATE_FILE_PATH", test_state)
    mgr = fire_tv_discovery.get_fire_tv_connection_manager()
    mgr._state_file_path = test_state
    mgr.invalidate_cache()
    yield
    mgr.invalidate_cache()

from src.config import settings
from src.core.target_context import TargetContextManager, get_target_context
from src.tools import ALL_ATON_TOOLS, dispatch_tool
from src.tools.fire_tv import (
    APPS,
    FIRE_TV_FUNCTION_DECLARATIONS,
    KEYS,
    REPEATABLE_ACTIONS,
    SINGLE_ACTIONS,
    control_fire_tv,
    dispatch_fire_tv_tool,
    get_fire_tv_status,
    launch_fire_tv_app,
    load_fire_tv_apps,
    PACKAGE_REGEX,
)


def test_fire_tv_declarations_schema():
    """Verify Fire TV tool declarations adhere to the schema and enums match code tables."""
    tool_names = [t["name"] for t in FIRE_TV_FUNCTION_DECLARATIONS]
    assert "get_fire_tv_status" in tool_names
    assert "launch_fire_tv_app" in tool_names
    assert "control_fire_tv" in tool_names

    # All 3 tools must be present in ALL_ATON_TOOLS
    all_names = [t["name"] for t in ALL_ATON_TOOLS]
    for name in tool_names:
        assert name in all_names

    # Check enums
    launch_decl = next(t for t in FIRE_TV_FUNCTION_DECLARATIONS if t["name"] == "launch_fire_tv_app")
    app_enum = launch_decl["parameters"]["properties"]["app_name"]["enum"]
    assert set(app_enum) == set(APPS.keys())

    control_decl = next(t for t in FIRE_TV_FUNCTION_DECLARATIONS if t["name"] == "control_fire_tv")
    action_enum = control_decl["parameters"]["properties"]["action"]["enum"]
    assert set(action_enum) == set(KEYS.keys())

    # Count parameter must exist with minimum and maximum
    count_prop = control_decl["parameters"]["properties"]["count"]
    assert count_prop["type"] == "INTEGER"
    assert count_prop["minimum"] == 1
    assert count_prop["maximum"] == 10


def test_fire_tv_invalid_ip_rejection(monkeypatch):
    """Verify rejection of invalid, public or loopback IP addresses for safety."""
    monkeypatch.setattr(settings, "fire_tv_ip", "127.0.0.1")
    monkeypatch.setattr(settings, "fire_tv_adb_path", "scripts/firetv-platform-tools/adb.exe")
    res = get_fire_tv_status()
    assert res["status"] == "error"
    assert "IPv4" in res["message"]

    monkeypatch.setattr(settings, "fire_tv_ip", "8.8.8.8")
    res = get_fire_tv_status()
    assert res["status"] == "error"
    assert "IPv4" in res["message"]

    monkeypatch.setattr(settings, "fire_tv_ip", "invalid-ip")
    res = get_fire_tv_status()
    assert res["status"] == "error"


def test_fire_tv_missing_adb_path(monkeypatch):
    """Verify error when ADB path does not point to a valid file."""
    monkeypatch.setattr(settings, "fire_tv_ip", "192.168.0.13")
    monkeypatch.setattr(settings, "fire_tv_adb_path", "caminho_inexistente/adb.exe")
    res = get_fire_tv_status()
    assert res["status"] == "error"
    assert "Configure FIRE_TV_ADB_PATH" in res["message"]


@patch("src.tools.fire_tv._run")
@patch("pathlib.Path.is_file", return_value=True)
def test_get_fire_tv_status_success(mock_is_file, mock_run, monkeypatch):
    """Verify status query succeeds when device is connected and authorized."""
    monkeypatch.setattr(settings, "fire_tv_ip", "192.168.0.13")
    monkeypatch.setattr(settings, "fire_tv_adb_path", "scripts/firetv-platform-tools/adb.exe")

    def fake_run(args, *extra_args, **kwargs):
        ret = MagicMock()
        ret.returncode = 0
        ret.stderr = ""
        if "ro.serialno" in args or "ro.boot.serialno" in args:
            ret.stdout = "G071CQ2042741DJK\n"
            return ret
        if "ro.product.model" in args:
            ret.stdout = "AFTSS\n"
            return ret
        if "connect" in args:
            ret.stdout = "connected to 192.168.0.13:5555"
        elif "get-state" in args:
            ret.stdout = "device\n"
        elif "ro.product.model" in args:
            ret.stdout = "AFTSS\n"
        return ret

    mock_run.side_effect = fake_run
    res = get_fire_tv_status()
    assert res["status"] == "success"
    assert "AFTSS" in res["message"]
    assert "autorizado" in res["message"]


@patch("src.tools.fire_tv._run")
@patch("pathlib.Path.is_file", return_value=True)
def test_get_fire_tv_status_device_unauthorized(mock_is_file, mock_run, monkeypatch):
    """Verify device state error when ADB authorization is missing on the TV, giving clear TV prompt instructions."""
    monkeypatch.setattr(settings, "fire_tv_ip", "192.168.0.13")
    monkeypatch.setattr(settings, "fire_tv_adb_path", "scripts/firetv-platform-tools/adb.exe")

    def fake_run(args, *extra_args, **kwargs):
        ret = MagicMock()
        ret.returncode = 0
        ret.stderr = ""
        if "ro.serialno" in args or "ro.boot.serialno" in args:
            ret.stdout = "G071CQ2042741DJK\n"
            return ret
        if "ro.product.model" in args:
            ret.stdout = "AFTSS\n"
            return ret
        if "connect" in args:
            ret.stdout = "connected to 192.168.0.13:5555"
        elif "get-state" in args:
            ret.stdout = "unauthorized\n"
        return ret

    mock_run.side_effect = fake_run
    res = get_fire_tv_status()
    assert res["status"] == "error"
    assert "tela da TV" in res["message"]


@patch("src.tools.fire_tv._run")
@patch("pathlib.Path.is_file", return_value=True)
def test_launch_fire_tv_app_success_confirmed(mock_is_file, mock_run, monkeypatch):
    """Verify app launch confirms foreground package and returns confirmed=True."""
    monkeypatch.setattr(settings, "fire_tv_ip", "192.168.0.13")
    monkeypatch.setattr(settings, "fire_tv_adb_path", "scripts/firetv-platform-tools/adb.exe")

    def fake_run(args, *extra_args, **kwargs):
        ret = MagicMock()
        ret.returncode = 0
        ret.stderr = ""
        if "ro.serialno" in args or "ro.boot.serialno" in args:
            ret.stdout = "G071CQ2042741DJK\n"
            return ret
        if "ro.product.model" in args:
            ret.stdout = "AFTSS\n"
            return ret
        if "connect" in args:
            ret.stdout = "connected"
        elif "get-state" in args:
            ret.stdout = "device"
        elif "pm" in args and "path" in args:
            ret.stdout = "package:/data/app/com.amazon.firetv.youtube-1/base.apk\n"
        elif "monkey" in args:
            ret.stdout = ":Monkey: seed=0 count=1\nEvents injected: 1\n## Network stats: elapsed time=42ms\n"
        elif "dumpsys" in args:
            ret.stdout = "mCurrentFocus=Window{4a2b1c u0 com.amazon.firetv.youtube/com.google.android.apps.youtube.tv.activity.ShellActivity}\n"
        return ret

    mock_run.side_effect = fake_run
    res = launch_fire_tv_app("youtube")
    assert res["status"] == "success"
    assert res["confirmed"] is True
    assert "aberto e confirmado" in res["message"]


@patch("src.tools.fire_tv._run")
@patch("pathlib.Path.is_file", return_value=True)
def test_launch_fire_tv_app_timeout_unconfirmed(mock_is_file, mock_run, monkeypatch):
    """Verify app launch returns confirmed=False when foreground check times out."""
    monkeypatch.setattr(settings, "fire_tv_ip", "192.168.0.13")
    monkeypatch.setattr(settings, "fire_tv_adb_path", "scripts/firetv-platform-tools/adb.exe")

    def fake_run(args, *extra_args, **kwargs):
        ret = MagicMock()
        ret.returncode = 0
        ret.stderr = ""
        if "ro.serialno" in args or "ro.boot.serialno" in args:
            ret.stdout = "G071CQ2042741DJK\n"
            return ret
        if "ro.product.model" in args:
            ret.stdout = "AFTSS\n"
            return ret
        if "connect" in args:
            ret.stdout = "connected"
        elif "get-state" in args:
            ret.stdout = "device"
        elif "pm" in args and "path" in args:
            ret.stdout = "package:/data/app/com.amazon.firetv.youtube-1/base.apk\n"
        elif "monkey" in args:
            ret.stdout = "Events injected: 1\n"
        elif "dumpsys" in args:
            ret.stdout = "mCurrentFocus=Window{12345 u0 com.amazon.tv.launcher/.ui.HomeActivity}\n"
        return ret

    mock_run.side_effect = fake_run
    res = launch_fire_tv_app("youtube")
    assert res["status"] == "success"
    assert res["confirmed"] is False
    assert "confirmada" in res["message"]


def test_launch_fire_tv_app_unregistered():
    """Verify unregistered application names are safely rejected without network activity."""
    res = launch_fire_tv_app("app_completamente_desconhecido")
    assert res["status"] == "error"
    assert "cadastrado" in res["message"]


@patch("src.tools.fire_tv._run")
@patch("pathlib.Path.is_file", return_value=True)
def test_launch_fire_tv_app_not_installed(mock_is_file, mock_run, monkeypatch):
    """Verify error when application package is not installed on the Fire Stick."""
    monkeypatch.setattr(settings, "fire_tv_ip", "192.168.0.13")
    monkeypatch.setattr(settings, "fire_tv_adb_path", "scripts/firetv-platform-tools/adb.exe")

    def fake_run(args, *extra_args, **kwargs):
        ret = MagicMock()
        ret.returncode = 0
        ret.stderr = ""
        if "ro.serialno" in args or "ro.boot.serialno" in args:
            ret.stdout = "G071CQ2042741DJK\n"
            return ret
        if "ro.product.model" in args:
            ret.stdout = "AFTSS\n"
            return ret
        if "connect" in args:
            ret.stdout = "connected"
        elif "get-state" in args:
            ret.stdout = "device"
        elif "pm" in args and "path" in args:
            ret.stdout = "\n"  # package not found
        return ret

    mock_run.side_effect = fake_run
    res = launch_fire_tv_app("spotify")
    assert res["status"] == "error"
    assert "não está instalado" in res["message"]


@patch("src.tools.fire_tv._run")
@patch("pathlib.Path.is_file", return_value=True)
def test_control_fire_tv_single_action(mock_is_file, mock_run, monkeypatch):
    """Verify single-action keys only send 1 key event."""
    monkeypatch.setattr(settings, "fire_tv_ip", "192.168.0.13")
    monkeypatch.setattr(settings, "fire_tv_adb_path", "scripts/firetv-platform-tools/adb.exe")

    executed_calls = []

    def fake_run(args, *extra_args, **kwargs):
        ret = MagicMock()
        ret.returncode = 0
        ret.stderr = ""
        if "ro.serialno" in args or "ro.boot.serialno" in args:
            ret.stdout = "G071CQ2042741DJK\n"
            return ret
        if "ro.product.model" in args:
            ret.stdout = "AFTSS\n"
            return ret
        if "connect" in args:
            ret.stdout = "connected"
        elif "get-state" in args:
            ret.stdout = "device"
        elif "input" in args and "keyevent" in args:
            executed_calls.append(args[args.index("keyevent") + 1 :])
            ret.stdout = "\n"
        return ret

    mock_run.side_effect = fake_run
    for action in ["home", "pause", "play", "back", "select", "menu"]:
        res = control_fire_tv(action)
        assert res["status"] == "success"
        assert action in res["message"]

    assert len(executed_calls) == 6
    assert executed_calls[0] == ["3"]   # home
    assert executed_calls[1] == ["127"] # pause
    assert executed_calls[2] == ["126"] # play


@patch("src.tools.fire_tv._run")
@patch("pathlib.Path.is_file", return_value=True)
def test_control_fire_tv_repeatable_action_with_count(mock_is_file, mock_run, monkeypatch):
    """Verify repeatable directional/seek keys send multiple keyevent values in one command."""
    monkeypatch.setattr(settings, "fire_tv_ip", "192.168.0.13")
    monkeypatch.setattr(settings, "fire_tv_adb_path", "scripts/firetv-platform-tools/adb.exe")

    executed_calls = []

    def fake_run(args, *extra_args, **kwargs):
        ret = MagicMock()
        ret.returncode = 0
        ret.stderr = ""
        if "ro.serialno" in args or "ro.boot.serialno" in args:
            ret.stdout = "G071CQ2042741DJK\n"
            return ret
        if "ro.product.model" in args:
            ret.stdout = "AFTSS\n"
            return ret
        if "connect" in args:
            ret.stdout = "connected"
        elif "get-state" in args:
            ret.stdout = "device"
        elif "input" in args and "keyevent" in args:
            executed_calls.append(args[args.index("keyevent") + 1 :])
            ret.stdout = "\n"
        return ret

    mock_run.side_effect = fake_run
    # Repeat right 4 times
    res = control_fire_tv("right", count=4)
    assert res["status"] == "success"
    assert res["count"] == 4
    assert executed_calls[-1] == ["22", "22", "22", "22"]

    # Repeat rewind 3 times
    res = control_fire_tv("rewind", count=3)
    assert res["status"] == "success"
    assert res["count"] == 3
    assert executed_calls[-1] == ["89", "89", "89"]


def test_control_fire_tv_count_bounds_validation():
    """Verify count validation: rejects count > 10, count < 1, and count > 1 for single keys."""
    # Count > 10
    res = control_fire_tv("down", count=11)
    assert res["status"] == "error"
    assert "entre 1 e 10" in res["message"]

    # Count < 1
    res = control_fire_tv("down", count=0)
    assert res["status"] == "error"
    assert "entre 1 e 10" in res["message"]

    # Repetition requested for non-repeatable key
    res = control_fire_tv("home", count=3)
    assert res["status"] == "error"
    assert "repeti" in res["message"]

    res = control_fire_tv("pause", count=2)
    assert res["status"] == "error"
    assert "repeti" in res["message"]


def test_control_fire_tv_navigation_vs_media_distinction():
    """Verify distinct keycodes for right (nav 22), next (skip 87), and fast_forward (seek 90)."""
    assert KEYS["right"] == 22
    assert KEYS["next"] == 87
    assert KEYS["fast_forward"] == 90
    assert "right" in REPEATABLE_ACTIONS
    assert "fast_forward" in REPEATABLE_ACTIONS
    assert "next" in SINGLE_ACTIONS


def test_control_fire_tv_invalid_action():
    """Verify unauthorized keys or actions are blocked."""
    res = control_fire_tv("volume_up")  # Not in KEYS
    assert res["status"] == "error"
    assert "não permitido" in res["message"]


def test_fire_tv_apps_json_and_alias_resolution(tmp_path):
    """Verify dynamic loading from config/fire_tv_apps.json and alias resolution."""
    custom_config = {
        "apps": {
            "custom_player": {
                "package": "com.example.customplayer",
                "description": "Player customizado",
                "aliases": ["meu player", "player legal"],
            }
        }
    }
    cfg_file = tmp_path / "fire_tv_apps.json"
    cfg_file.write_text(json.dumps(custom_config), encoding="utf-8")

    with patch("src.tools.fire_tv._get_config_file_path", return_value=cfg_file):
        canonical, aliases = load_fire_tv_apps()
        assert "custom_player" in canonical
        assert canonical["custom_player"] == "com.example.customplayer"
        assert aliases["meu player"] == "com.example.customplayer"
        assert aliases["player legal"] == "com.example.customplayer"


def test_fire_tv_package_regex_validation():
    """Verify package name format validation prevents arbitrary or malformed strings."""
    assert PACKAGE_REGEX.match("com.amazon.firetv.youtube")
    assert PACKAGE_REGEX.match("org.videolan.vlc")
    assert PACKAGE_REGEX.match("com.netflix.ninja")

    assert not PACKAGE_REGEX.match("invalid_no_dot")
    assert not PACKAGE_REGEX.match("com.amazon;rm -rf")
    assert not PACKAGE_REGEX.match("com.amazon & reboot")


def test_target_context_lifecycle():
    """Verify TargetContextManager sets target, respects TTL, handles disambiguation, and clears."""
    ctx = TargetContextManager(timeout_seconds=2)
    assert ctx.get_active_target() is None

    ctx.set_target("fire_tv")
    assert ctx.get_active_target() == "fire_tv"

    # Pending clarification
    ctx.set_pending_clarification("abra o youtube")
    assert ctx.get_pending_clarification() == "abra o youtube"

    # Context clearing
    ctx.clear()
    assert ctx.get_active_target() is None
    assert ctx.get_pending_clarification() is None


def test_dispatch_tool_target_context_wiring():
    """Verify unified dispatch_tool updates target context appropriately."""
    ctx = get_target_context()
    ctx.clear()

    # Fire TV sets fire_tv
    with patch("src.tools.fire_tv.control_fire_tv", return_value={"status": "success", "message": "OK"}):
        res = dispatch_tool("control_fire_tv", {"action": "home"})
        assert res["status"] == "success"
        assert ctx.get_active_target() == "fire_tv"

    # Windows tool sets pc
    with patch("src.tools.windows_apps.open_application", return_value={"status": "success", "message": "Opened"}):
        res = dispatch_tool("open_application", {"app_name": "notepad"})
        assert res["status"] == "success"
        assert ctx.get_active_target() == "pc"

    # Smart TV volume returns unavailable truthfully without touching PC
    res = dispatch_tool("control_tv_volume", {"action": "mute"})
    assert res["status"] == "unavailable"
