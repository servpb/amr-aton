"""Unit tests for Windows application management tool (Phase 1)."""

from unittest.mock import MagicMock, patch
import pytest

from src.tools.windows_apps import (
    WINDOWS_APP_FUNCTION_DECLARATIONS,
    close_application,
    dispatch_tool,
    list_running_applications,
    open_application,
    resolve_app_target,
)
from src.core.task_context import TaskContextManager


def test_resolve_app_target():
    """Verify friendly name resolution to target executables or URLs."""
    assert resolve_app_target("bloco de notas") == "notepad"
    assert resolve_app_target("notepad") == "notepad"
    assert resolve_app_target("chrome") == "chrome"
    assert resolve_app_target("msedge") == "msedge"
    assert resolve_app_target("edge") == "msedge"
    assert resolve_app_target("google.com") == "https://google.com"
    assert resolve_app_target("https://youtube.com") == "https://youtube.com"
    assert resolve_app_target("www.github.com") == "https://www.github.com"
    assert resolve_app_target("custom_program") == "custom_program"


def test_function_declarations_schema():
    """Verify tool declarations conform to Gemini Live schema expectations."""
    assert len(WINDOWS_APP_FUNCTION_DECLARATIONS) == 3
    names = [t["name"] for t in WINDOWS_APP_FUNCTION_DECLARATIONS]
    assert "open_application" in names
    assert "close_application" in names
    assert "list_running_applications" in names

    for decl in WINDOWS_APP_FUNCTION_DECLARATIONS:
        assert "name" in decl
        assert "description" in decl
        assert "parameters" in decl
        assert decl["parameters"]["type"] == "OBJECT"


@patch("subprocess.Popen")
def test_open_application_subprocess(mock_popen):
    """Verify open_application launches binary via subprocess."""
    result = open_application("bloco de notas")
    assert result["status"] == "success"
    assert "aberto com sucesso" in result["message"]
    mock_popen.assert_called_once()


@patch("os.startfile")
def test_open_application_url(mock_startfile):
    """Verify open_application opens URLs via os.startfile."""
    result = open_application("https://google.com")
    assert result["status"] == "success"
    assert "aberto com sucesso" in result["message"]
    mock_startfile.assert_called_once_with("https://google.com")


@patch("src.tools.windows_apps.list_visible_windows_with_process")
@patch("ctypes.windll.user32")
def test_close_application_success(mock_user32, mock_list_win):
    """Verify close_application identifies window and sends WM_CLOSE."""
    mock_list_win.return_value = [
        {"hwnd": 12345, "title": "Sem título - Bloco de Notas", "pid": 5678, "process_name": "notepad.exe"}
    ]
    mock_user32.IsWindow.return_value = False  # Window closed after WM_CLOSE
    result = close_application("notepad")
    assert result["status"] == "success"
    assert "fechada com sucesso" in result["message"]
    mock_user32.PostMessageW.assert_called_once_with(12345, 0x0010, 0, 0)


@patch("src.tools.windows_apps.list_visible_windows_with_process", return_value=[])
@patch("psutil.process_iter", return_value=[])
def test_close_application_not_running(mock_psutil, mock_list_win):
    """Verify close_application handles non-running processes gracefully."""
    result = close_application("inexistent_app_xyz")
    assert result["status"] == "error"
    assert "não parece estar em execução" in result["message"]


@patch("subprocess.run")
def test_list_running_applications(mock_run):
    """Verify list_running_applications parses tasklist output."""
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout='"chrome.exe","1234","Console","1","50,000 K"\n"notepad.exe","5678","Console","1","10,000 K"\n',
    )
    result = list_running_applications()
    assert result["status"] == "success"
    assert "Google Chrome" in result["apps"]
    assert "Bloco de Notas" in result["apps"]


def test_dispatch_tool_routing():
    """Verify dispatch_tool routes tool names to respective functions with parameters."""
    with patch("src.tools.windows_apps.open_application") as mock_open:
        mock_open.return_value = {"status": "success"}
        res = dispatch_tool("open_application", {"app_name": "calc"})
        assert res["status"] == "success"
        mock_open.assert_called_once_with(app_name="calc", args=None)

    with patch("src.tools.windows_apps.close_application") as mock_close:
        mock_close.return_value = {"status": "success"}
        res = dispatch_tool("close_application", {"app_name": "calc", "force": True})
        assert res["status"] == "success"
        mock_close.assert_called_once_with(app_name="calc", force=True)

    with patch("src.tools.windows_apps.list_running_applications") as mock_list:
        mock_list.return_value = {"status": "success"}
        res = dispatch_tool("list_running_applications", {})
        assert res["status"] == "success"
        mock_list.assert_called_once()

    res_unknown = dispatch_tool("unknown_tool", {})
    assert res_unknown["status"] == "error"


@patch("ctypes.windll.user32")
def test_close_application_active_window(mock_user32):
    """Verify close_application closes active window via WM_CLOSE when requested."""
    mock_user32.GetForegroundWindow.return_value = 12345
    mock_user32.GetWindowTextLengthW.return_value = 25
    mock_user32.IsWindow.return_value = False

    def mock_get_text(hwnd, buff, max_count):
        buff.value = "Janela de Teste"
        return 10
    mock_user32.GetWindowTextW.side_effect = mock_get_text

    result = close_application("janela_ativa")
    assert result["status"] == "success"
    assert "Janela 'Janela de Teste' fechada com sucesso" in result["message"]
    mock_user32.PostMessageW.assert_called_once_with(12345, 0x0010, 0, 0)


@patch("pyautogui.hotkey")
def test_close_application_tab(mock_hotkey):
    """Verify close_application closes active tab via Ctrl+W hotkey."""
    result = close_application("aba")
    assert result["status"] == "success"
    assert "Aba fechada com sucesso" in result["message"]
    mock_hotkey.assert_called_once_with("ctrl", "w")


@patch("src.tools.windows_apps.list_visible_windows_with_process")
@patch("ctypes.windll.user32")
def test_close_browser_identified_by_process_not_title(mock_user32, mock_list_win):
    """Verify window is identified by HWND associated process even if title lacks browser name."""
    mock_list_win.return_value = [
        {"hwnd": 8888, "title": "Roberto Carlos - YouTube — Personal", "pid": 2020, "process_name": "msedge.exe"}
    ]
    mock_user32.IsWindow.return_value = False

    result = close_application("edge")
    assert result["status"] == "success"
    assert "Roberto Carlos - YouTube" in result["message"]
    mock_user32.PostMessageW.assert_called_once_with(8888, 0x0010, 0, 0)


@patch("src.tools.windows_apps.list_visible_windows_with_process")
@patch("ctypes.windll.user32")
def test_close_browser_prioritizes_active_task_context(mock_user32, mock_list_win):
    """Verify 'feche o navegador' prioritizes window related to recent task context."""
    task_mgr = TaskContextManager()
    task = task_mgr.start_task(summary="Abrir YouTube", target="pc")
    task.references["app_name"] = "youtube.com"

    mock_list_win.return_value = [
        {"hwnd": 1111, "title": "Painel de Finanças - Google Chrome", "pid": 100, "process_name": "chrome.exe"},
        {"hwnd": 2222, "title": "YouTube - Microsoft Edge", "pid": 200, "process_name": "msedge.exe"},
    ]
    mock_user32.IsWindow.return_value = False

    with patch("src.tools.windows_apps.get_task_context", return_value=task_mgr):
        result = close_application("navegador")
        assert result["status"] == "success"
        assert "YouTube - Microsoft Edge" in result["message"]
        # Ensure only the YouTube Edge window was closed, not Chrome!
        mock_user32.PostMessageW.assert_called_once_with(2222, 0x0010, 0, 0)


@patch("src.tools.windows_apps.list_visible_windows_with_process")
def test_close_browser_ambiguous_candidates_asks_clarification(mock_list_win):
    """Verify 'feche o navegador' asks for clarification when multiple candidates exist without context."""
    task_mgr = TaskContextManager()
    # No active task context pointing to either
    mock_list_win.return_value = [
        {"hwnd": 1111, "title": "Painel de Vendas - Chrome", "pid": 100, "process_name": "chrome.exe"},
        {"hwnd": 2222, "title": "Notícias do Dia - Edge", "pid": 200, "process_name": "msedge.exe"},
    ]

    with patch("src.tools.windows_apps.get_task_context", return_value=task_mgr):
        result = close_application("navegador")
        assert result["status"] == "clarification_needed"
        assert "Encontrei mais de uma janela aberta" in result["message"]
        assert len(result["candidates"]) == 2


@patch("src.tools.windows_apps.list_visible_windows_with_process")
@patch("ctypes.windll.user32")
def test_close_window_pending_confirmation_no_auto_force(mock_user32, mock_list_win):
    """Verify window that does not close within timeout enters pending_confirmation without auto taskkill /F."""
    mock_list_win.return_value = [
        {"hwnd": 3333, "title": "Documento Não Salvo - Bloco de Notas", "pid": 500, "process_name": "notepad.exe"}
    ]
    # Window remains open after WM_CLOSE (e.g. unsaved changes dialog)
    mock_user32.IsWindow.return_value = True
    mock_user32.IsWindowVisible.return_value = True

    with patch("subprocess.run") as mock_run:
        result = close_application("notepad")
        assert result["status"] == "pending_confirmation"
        assert "alterações não salvas" in result["message"]
        # Must NOT have called taskkill /f automatically!
        mock_run.assert_not_called()


@patch("src.tools.windows_apps.list_visible_windows_with_process")
@patch("subprocess.run")
def test_close_application_explicit_force_termination(mock_run, mock_list_win):
    """Verify explicit force=True terminates process via taskkill /f /pid."""
    mock_list_win.return_value = [
        {"hwnd": 4444, "title": "App Travado", "pid": 777, "process_name": "badapp.exe"}
    ]
    mock_run.return_value = MagicMock(returncode=0)

    result = close_application("badapp", force=True)
    assert result["status"] == "success"
    assert "encerrado forçadamente" in result["message"]
    mock_run.assert_called_once()
    cmd = mock_run.call_args[0][0]
    assert "/f" in cmd
    assert "777" in cmd
