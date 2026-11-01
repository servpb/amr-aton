"""Unit tests for programmatic destination guard, ambiguity protection, volume rules, and resume flow."""

from unittest.mock import MagicMock, patch
import pytest

from src.core.destination_guard import evaluate_destination_guard, resolve_clarified_destination
from src.core.target_context import get_target_context
from src.tools import dispatch_tool


@pytest.fixture(autouse=True)
def clean_context():
    """Ensure target context is clean before and after each test."""
    ctx = get_target_context()
    ctx.clear()
    yield
    ctx.clear()


def test_ambiguous_youtube_blocked_without_physical_effect():
    """Verify 'Abra o YouTube' without destination or active context is blocked without executing."""
    ctx = get_target_context()
    assert ctx.get_active_target() is None

    # Even if Gemini calls launch_fire_tv_app or open_application, guard blocks
    with patch("src.tools.fire_tv._run") as mock_adb, patch("subprocess.Popen") as mock_popen:
        res = dispatch_tool("launch_fire_tv_app", {"app_name": "youtube"})
        assert res["status"] == "needs_clarification"
        assert res["destination_needed"] is True
        assert "computador ou no Fire Stick" in res["message"]

        # Verify NO physical action occurred
        mock_adb.assert_not_called()
        mock_popen.assert_not_called()

        # Verify pending action was saved
        pending = ctx.get_pending_action()
        assert pending is not None
        assert pending["action_type"] == "open_app"
        assert pending["params"]["app_name"] == "youtube"


def test_resume_after_clarification_fire_tv():
    """Verify answering 'No Fire Stick' resumes and executes original app launch on Fire TV."""
    ctx = get_target_context()
    # Trigger ambiguous block
    dispatch_tool("open_application", {"app_name": "youtube"})
    assert ctx.get_pending_action() is not None

    with patch("src.tools.fire_tv.launch_fire_tv_app", return_value={"status": "success", "confirmed": True, "message": "YouTube aberto no Fire Stick"}) as mock_launch:
        res = dispatch_tool("resolve_destination", {"destination": "fire_tv"})
        assert res["status"] == "success"
        mock_launch.assert_called_once_with("youtube")

        # Context is now active for fire_tv and pending is cleared
        assert ctx.get_active_target() == "fire_tv"
        assert ctx.get_pending_action() is None


def test_resume_after_clarification_pc():
    """Verify answering 'No computador' resumes and executes on PC."""
    ctx = get_target_context()
    # Trigger ambiguous block
    dispatch_tool("launch_fire_tv_app", {"app_name": "youtube"})
    assert ctx.get_pending_action() is not None

    with patch("src.tools.web_browser.search_youtube", return_value={"status": "success", "message": "YouTube aberto no PC"}) as mock_yt:
        res = dispatch_tool("resolve_destination", {"destination": "pc"})
        assert res["status"] == "success"
        mock_yt.assert_called_once()

        assert ctx.get_active_target() == "pc"
        assert ctx.get_pending_action() is None


def test_unequivocal_command_chrome_never_blocked():
    """Verify unequivocal PC command (e.g. Chrome) executes immediately without asking."""
    ctx = get_target_context()
    with patch("src.tools.windows_apps.open_application", return_value={"status": "success", "message": "Chrome aberto"}) as mock_open:
        res = dispatch_tool("open_application", {"app_name": "chrome"})
        assert res["status"] == "success"
        mock_open.assert_called_once()
        assert ctx.get_active_target() == "pc"


def test_unequivocal_command_downloader_never_blocked():
    """Verify unequivocal Fire TV command (e.g. Downloader) executes immediately on Fire Stick."""
    ctx = get_target_context()
    with patch("src.tools.fire_tv.launch_fire_tv_app", return_value={"status": "success", "confirmed": True, "message": "Downloader aberto"}) as mock_launch:
        res = dispatch_tool("launch_fire_tv_app", {"app_name": "downloader"})
        assert res["status"] == "success"
        mock_launch.assert_called_once_with("downloader")
        assert ctx.get_active_target() == "fire_tv"


def test_explicit_destination_precedence_and_switching():
    """Verify explicit destination takes precedence over active session context."""
    ctx = get_target_context()
    ctx.set_target("fire_tv")
    assert ctx.get_active_target() == "fire_tv"

    # User says "abra o youtube no computador"
    with patch("src.tools.web_browser.search_youtube", return_value={"status": "success", "message": "YouTube aberto no PC"}) as mock_yt:
        res = dispatch_tool("search_youtube", {"destination": "pc"})
        assert res["status"] == "success"
        mock_yt.assert_called_once()
        # Context switched to PC
        assert ctx.get_active_target() == "pc"

    # Subsequent pause uses PC context
    with patch("src.tools.system_audio.control_system_media", return_value={"status": "success", "message": "Mídia pausada no PC"}) as mock_media:
        res = dispatch_tool("control_system_media", {"action": "pause"})
        assert res["status"] == "success"
        mock_media.assert_called_once_with(action="pause")


def test_context_cleared_on_sleep():
    """Verify context and pending action are completely purged when assistant goes to sleep."""
    ctx = get_target_context()
    ctx.set_target("fire_tv")
    ctx.set_pending_action("media", {"action": "pause"})

    # Simulate sleep cleanup
    ctx.clear()
    assert ctx.get_active_target() is None
    assert ctx.get_pending_action() is None

    # After wake, 'pause' is blocked again
    res = dispatch_tool("control_fire_tv", {"action": "pause"})
    assert res["status"] == "needs_clarification"
    assert res["destination_needed"] is True


def test_volume_rules_computer_controls_windows():
    """Verify volume with destination PC controls Windows audio."""
    ctx = get_target_context()
    with patch("src.tools.system_audio.set_system_volume", return_value={"status": "success", "volume": 60, "message": "Volume ajustado"}) as mock_vol:
        res = dispatch_tool("set_system_volume", {"level": 60, "destination": "pc"})
        assert res["status"] == "success"
        mock_vol.assert_called_once_with(level=60, mute=None)
        assert ctx.get_active_target() == "pc"


def test_volume_rules_tv_reports_unavailable_never_touches_pc():
    """Verify TV volume request informs unavailable and NEVER replaces with PC action."""
    with patch("src.tools.system_audio.set_system_volume") as mock_pc_vol:
        res = dispatch_tool("control_tv_volume", {"action": "up"})
        assert res["status"] == "unavailable"
        assert "não está disponível nesta versão" in res["message"]
        assert "Fire Stick não gerencia o volume" in res["message"]

        # Ensure Windows volume was NOT touched!
        mock_pc_vol.assert_not_called()

        # Also via set_system_volume with destination="tv"
        res2 = dispatch_tool("set_system_volume", {"level": 80, "destination": "tv"})
        assert res2["status"] == "unavailable"
        mock_pc_vol.assert_not_called()


def test_volume_ambiguous_blocks_and_asks():
    """Verify 'Aumente o volume' without destination and without context asks for clarification."""
    ctx = get_target_context()
    assert ctx.get_active_target() is None

    with patch("src.tools.system_audio.set_system_volume") as mock_pc_vol:
        res = dispatch_tool("set_system_volume", {"level": 70})
        assert res["status"] == "needs_clarification"
        assert res["destination_needed"] is True
        assert "computador ou da TV" in res["message"]
        mock_pc_vol.assert_not_called()

        pending = ctx.get_pending_action()
        assert pending is not None
        assert pending["action_type"] == "volume"


def test_tv_power_reports_unavailable_never_touches_pc():
    """Verify TV power command informs unavailable and never executes PC power action."""
    res = dispatch_tool("control_tv_power", {"action": "off"})
    assert res["status"] == "unavailable"
    assert "ligar/desligar a televisão ainda não está disponível" in res["message"]
