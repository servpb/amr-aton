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


def test_resolve_app_target():
    """Verify friendly name resolution to target executables or URLs."""
    assert resolve_app_target("bloco de notas") == "notepad"
    assert resolve_app_target("notepad") == "notepad"
    assert resolve_app_target("chrome") == "chrome"
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


@patch("subprocess.run")
def test_close_application_success(mock_run):
    """Verify close_application issues taskkill command."""
    mock_run.return_value = MagicMock(returncode=0)
    result = close_application("notepad")
    assert result["status"] == "success"
    assert "encerrado com sucesso" in result["message"]
    mock_run.assert_called_once()


@patch("subprocess.run")
def test_close_application_not_running(mock_run):
    """Verify close_application handles non-running processes gracefully."""
    mock_run.return_value = MagicMock(returncode=128)
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
    """Verify dispatch_tool routes tool names to respective functions."""
    with patch("src.tools.windows_apps.open_application") as mock_open:
        mock_open.return_value = {"status": "success"}
        res = dispatch_tool("open_application", {"app_name": "calc"})
        assert res["status"] == "success"
        mock_open.assert_called_once_with(app_name="calc", args=None)

    with patch("src.tools.windows_apps.close_application") as mock_close:
        mock_close.return_value = {"status": "success"}
        res = dispatch_tool("close_application", {"app_name": "calc"})
        assert res["status"] == "success"
        mock_close.assert_called_once_with(app_name="calc")

    with patch("src.tools.windows_apps.list_running_applications") as mock_list:
        mock_list.return_value = {"status": "success"}
        res = dispatch_tool("list_running_applications", {})
        assert res["status"] == "success"
        mock_list.assert_called_once()

    res_unknown = dispatch_tool("unknown_tool", {})
    assert res_unknown["status"] == "error"


@patch("subprocess.run")
def test_close_application_with_force_fallback(mock_run):
    """Verify close_application retries with /F when graceful taskkill fails (e.g. Edge/Chrome)."""
    # First call fails with code 1 (requires /F), second call succeeds with code 0
    mock_run.side_effect = [
        MagicMock(returncode=1, stderr="ERROR: Process requires /F"),
        MagicMock(returncode=0, stdout="SUCCESS"),
    ]
    result = close_application("edge")
    assert result["status"] == "success"
    assert "encerrado com sucesso" in result["message"]
    assert mock_run.call_count == 2
    # Verify the second call contains /f
    second_call_args = mock_run.call_args_list[1][0][0]
    assert "/f" in second_call_args


def test_close_application_window_by_title():
    """Verify close_application closes a window matching title (e.g. YouTube)."""
    fake_win = MagicMock()
    fake_win.title = "YouTube - Microsoft Edge"

    with patch("pygetwindow.getAllWindows", return_value=[fake_win]):
        result = close_application("YouTube")
        assert result["status"] == "success"
        assert "YouTube - Microsoft Edge" in result["message"]
        fake_win.close.assert_called_once()


@patch("ctypes.windll.user32")
def test_close_application_active_window(mock_user32):
    """Verify close_application closes active window via WM_CLOSE when requested."""
    mock_user32.GetForegroundWindow.return_value = 12345
    mock_user32.GetWindowTextLengthW.return_value = 25
    
    # Mock GetWindowTextW to set buffer value
    def mock_get_text(hwnd, buff, max_count):
        buff.value = "Janela de Teste"
        return 10
    mock_user32.GetWindowTextW.side_effect = mock_get_text

    result = close_application("janela_ativa")
    assert result["status"] == "success"
    assert "Janela 'Janela de Teste' fechada com sucesso" in result["message"]
    mock_user32.PostMessageW.assert_called_once_with(12345, 0x0010, 0, 0)

