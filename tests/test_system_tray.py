"""Tests for System Tray Integration (Phase 6)."""

from unittest.mock import MagicMock, patch
from PIL import Image
import pytest
from src.integrations.system_tray import AtonSystemTray, generate_tray_icon


def test_generate_tray_icon_states():
    """Verify tray icon generator produces valid RGBA images for all states."""
    for state in ("sleeping", "listening", "speaking", "muted"):
        img = generate_tray_icon(state=state, size=64)
        assert isinstance(img, Image.Image)
        assert img.size == (64, 64)
        assert img.mode == "RGBA"


def test_system_tray_initialization_and_menu():
    """Verify tray manager initializes with expected properties and menu."""
    mute_cb = MagicMock()
    briefing_cb = MagicMock()
    exit_cb = MagicMock()

    tray = AtonSystemTray(
        hud_url="http://localhost:8443",
        on_toggle_mute=mute_cb,
        on_request_briefing=briefing_cb,
        on_exit=exit_cb,
    )

    assert tray.is_muted is False
    assert "Em espera" in tray.status_text

    menu = tray._build_menu()
    assert menu is not None

    # Test toggle mute handler
    tray._handle_toggle_mute(None, None)
    assert tray.is_muted is True
    mute_cb.assert_called_once_with(True)

    # Test briefing handler
    tray._handle_briefing(None, None)
    briefing_cb.assert_called_once()

    # Test open HUD handler with patched webbrowser
    with patch("webbrowser.open") as mock_browser:
        tray._handle_open_hud(None, None)
        mock_browser.assert_called_once_with("http://localhost:8443")

    # Test exit handler
    tray._handle_exit(None, None)
    exit_cb.assert_called_once()


def test_system_tray_update_state():
    """Verify state updates change status_text and icon."""
    tray = AtonSystemTray()
    tray.update_state(state="listening", status_text="Ouvindo...")
    assert tray._state == "listening"
    assert tray.status_text == "Ouvindo..."


def test_system_tray_lifecycle_mocked():
    """Verify start and stop create and terminate the icon safely."""
    import threading
    stop_event = threading.Event()

    with patch("pystray.Icon") as mock_icon_cls:
        mock_instance = MagicMock()
        mock_instance.run.side_effect = lambda: stop_event.wait(timeout=2.0)
        mock_instance.stop.side_effect = lambda: stop_event.set()
        mock_icon_cls.return_value = mock_instance

        tray = AtonSystemTray()
        tray.start()
        assert tray._is_running is True

        tray.stop()
        assert tray._is_running is False
        mock_instance.stop.assert_called_once()
