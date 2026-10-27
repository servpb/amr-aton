"""Tests for Desktop Typing, Document and Keyboard Automation (Phase 7)."""

import os
from unittest.mock import MagicMock, patch
import pyperclip
import pytest

# Initialize pyperclip lazy loader so that mock patching targets the real clipboard function
try:
    pyperclip.paste()
except Exception:
    pass

from src.tools.desktop_automation import (
    DESKTOP_AUTOMATION_FUNCTION_DECLARATIONS,
    create_and_open_document,
    dispatch_desktop_automation_tool,
    focus_application_window,
    send_keyboard_shortcut,
    type_text_in_active_window,
)
from src.tools import ALL_ATON_TOOLS, dispatch_tool


def test_type_text_in_active_window_clipboard():
    """Verify typing text using clipboard paste (Ctrl+V)."""
    with patch("src.tools.desktop_automation.pyautogui.hotkey") as mock_hotkey, patch("src.tools.desktop_automation.pyperclip.copy") as mock_copy:
        res = type_text_in_active_window("Olá, este é um teste com acentuação e maçã.")
        assert res["status"] == "success"
        assert "Texto inserido" in res["message"]
        mock_copy.assert_called()
        mock_hotkey.assert_called_with("ctrl", "v")


def test_type_text_with_enter():
    """Verify typing with press_enter sends Enter key."""
    with patch("src.tools.desktop_automation.pyautogui.hotkey"), patch("src.tools.desktop_automation.pyautogui.press") as mock_press, patch("src.tools.desktop_automation.pyperclip.copy"):
        res = type_text_in_active_window("Texto com enter", press_enter=True)
        assert res["status"] == "success"
        mock_press.assert_called_with("enter")


def test_type_text_empty():
    """Verify empty text returns error."""
    res = type_text_in_active_window("")
    assert res["status"] == "error"


def test_create_and_open_document_txt(tmp_path):
    """Verify creating a .txt document."""
    with patch("os.startfile") as mock_open:
        res = create_and_open_document(
            file_name="teste_nota",
            content="Conteúdo da nota de teste",
            file_type="txt",
            directory=str(tmp_path),
        )
        assert res["status"] == "success"
        assert os.path.exists(res["file_path"])
        with open(res["file_path"], "r", encoding="utf-8") as f:
            assert f.read() == "Conteúdo da nota de teste"
        mock_open.assert_called_once_with(res["file_path"])


def test_create_and_open_document_docx(tmp_path):
    """Verify creating a real Word .docx document."""
    with patch("os.startfile"):
        res = create_and_open_document(
            file_name="teste_word",
            content="Título do Documento\nPrimeiro parágrafo.\nSegundo parágrafo.",
            file_type="docx",
            directory=str(tmp_path),
        )
        assert res["status"] == "success"
        assert os.path.exists(res["file_path"])
        assert res["file_path"].endswith(".docx")
        assert os.path.getsize(res["file_path"]) > 1000


def test_create_and_open_document_xlsx(tmp_path):
    """Verify creating a real Excel .xlsx spreadsheet."""
    with patch("os.startfile"):
        content = "Produto; Quantidade; Preco\nNotebook; 2; 4500.00\nMouse; 5; 80.00"
        res = create_and_open_document(
            file_name="teste_planilha",
            content=content,
            file_type="xlsx",
            directory=str(tmp_path),
        )
        assert res["status"] == "success"
        assert os.path.exists(res["file_path"])
        assert res["file_path"].endswith(".xlsx")
        assert os.path.getsize(res["file_path"]) > 1000


def test_send_keyboard_shortcut():
    """Verify executing shortcut combinations."""
    with patch("src.tools.desktop_automation.pyautogui.hotkey") as mock_hotkey:
        res = send_keyboard_shortcut("ctrl+s")
        assert res["status"] == "success"
        assert "ctrl+s" in res["message"]
        mock_hotkey.assert_called_with("ctrl", "s")

    with patch("src.tools.desktop_automation.pyautogui.press") as mock_press:
        res = send_keyboard_shortcut("enter")
        assert res["status"] == "success"
        mock_press.assert_called_with("enter")


def test_focus_application_window():
    """Verify focus application window logic."""
    with patch("src.tools.desktop_automation.gw.getAllWindows", return_value=[]), patch("src.tools.windows_apps.open_application") as mock_open_app:
        mock_open_app.return_value = {"status": "success", "message": "Abrindo notepad"}
        res = focus_application_window("notepad")
        assert res["status"] == "success"


def test_dispatch_desktop_automation_tool():
    """Verify tool dispatcher for desktop automation tools."""
    with patch("src.tools.desktop_automation.pyautogui.hotkey"), patch("src.tools.desktop_automation.pyperclip.copy"):
        res = dispatch_desktop_automation_tool("type_text_in_active_window", {"text": "Teste"})
        assert res["status"] == "success"

        # Unknown tool
        err = dispatch_desktop_automation_tool("unknown_desktop_tool", {})
        assert err["status"] == "error"


def test_unified_dispatcher_desktop_tools(tmp_path):
    """Verify dispatch_tool routes desktop tools properly."""
    with patch("os.startfile"):
        res = dispatch_tool(
            "create_and_open_document",
            {"file_name": "teste_unificado", "content": "Dados", "file_type": "txt", "directory": str(tmp_path)},
        )
        assert res["status"] == "success"


def test_all_aton_tools_count_with_desktop():
    """Verify that ALL_ATON_TOOLS contains at least 35 active tools."""
    assert len(ALL_ATON_TOOLS) >= 35
    names = [t["name"] for t in ALL_ATON_TOOLS]
    assert "type_text_in_active_window" in names
    assert "create_and_open_document" in names
    assert "send_keyboard_shortcut" in names
    assert "focus_application_window" in names
