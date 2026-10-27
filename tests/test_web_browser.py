"""Unit tests for Web Browser automation and Search tool (Phase 1)."""

from unittest.mock import patch
import pytest

from src.tools import ALL_ATON_TOOLS, dispatch_tool
from src.tools.web_browser import (
    WEB_BROWSER_FUNCTION_DECLARATIONS,
    dispatch_web_tool,
    normalize_url,
    open_webpage,
    search_youtube,
    web_search,
)


def test_normalize_url():
    """Verify URL normalization prepends https scheme if missing."""
    assert normalize_url("google.com") == "https://google.com"
    assert normalize_url("wikipedia.org") == "https://wikipedia.org"
    assert normalize_url("http://example.com") == "http://example.com"
    assert normalize_url("https://github.com") == "https://github.com"


def test_web_browser_declarations_schema():
    """Verify web function declarations conform to expected schema."""
    assert len(WEB_BROWSER_FUNCTION_DECLARATIONS) == 3
    names = [t["name"] for t in WEB_BROWSER_FUNCTION_DECLARATIONS]
    assert "web_search" in names
    assert "search_youtube" in names
    assert "open_webpage" in names

    for decl in WEB_BROWSER_FUNCTION_DECLARATIONS:
        assert "name" in decl
        assert "description" in decl
        assert "parameters" in decl
        assert decl["parameters"]["type"] == "OBJECT"


@patch("webbrowser.open")
def test_web_search_success(mock_open):
    """Verify web_search constructs query URL and triggers browser."""
    result = web_search("noticias de tecnologia")
    assert result["status"] == "success"
    assert "Pesquisando" in result["message"]
    assert "noticias+de+tecnologia" in result["url"]
    mock_open.assert_called_once_with(result["url"])


def test_web_search_empty():
    """Verify web_search safely rejects empty query."""
    result = web_search("   ")
    assert result["status"] == "error"
    assert "Nenhum termo" in result["message"]


@patch("webbrowser.open")
def test_search_youtube_success(mock_open):
    """Verify search_youtube constructs query URL and triggers browser."""
    result = search_youtube("musica lofi")
    assert result["status"] == "success"
    assert "YouTube" in result["message"]
    assert "musica+lofi" in result["url"]
    mock_open.assert_called_once_with(result["url"])


def test_search_youtube_empty():
    """Verify search_youtube safely rejects empty query."""
    result = search_youtube("")
    assert result["status"] == "error"


@patch("webbrowser.open")
def test_open_webpage(mock_open):
    """Verify open_webpage opens normalized URL."""
    result = open_webpage("g1.globo.com")
    assert result["status"] == "success"
    assert "https://g1.globo.com" in result["url"]
    mock_open.assert_called_once_with("https://g1.globo.com")


def test_dispatch_web_tool():
    """Verify dispatch_web_tool routes calls properly."""
    with patch("src.tools.web_browser.web_search") as mock_ws:
        mock_ws.return_value = {"status": "success"}
        res = dispatch_web_tool("web_search", {"query": "teste"})
        assert res["status"] == "success"
        mock_ws.assert_called_once_with(query="teste")

    with patch("src.tools.web_browser.search_youtube") as mock_yt:
        mock_yt.return_value = {"status": "success"}
        res = dispatch_web_tool("search_youtube", {"query": "video"})
        assert res["status"] == "success"
        mock_yt.assert_called_once_with(query="video")

    with patch("src.tools.web_browser.open_webpage") as mock_ow:
        mock_ow.return_value = {"status": "success"}
        res = dispatch_web_tool("open_webpage", {"url": "site.com"})
        assert res["status"] == "success"
        mock_ow.assert_called_once_with(url="site.com")

    res_unknown = dispatch_web_tool("unknown_web_tool", {})
    assert res_unknown["status"] == "error"


def test_unified_dispatcher():
    """Verify unified dispatch_tool handles both Windows and Web tools."""
    with patch("src.tools.dispatch_windows_tool") as mock_win:
        mock_win.return_value = {"status": "success"}
        res = dispatch_tool("open_application", {"app_name": "calc"})
        assert res["status"] == "success"
        mock_win.assert_called_once()

    with patch("src.tools.dispatch_web_tool") as mock_web:
        mock_web.return_value = {"status": "success"}
        res = dispatch_tool("web_search", {"query": "brasil"})
        assert res["status"] == "success"
        mock_web.assert_called_once()

    res_unknown = dispatch_tool("completely_unknown", {})
    assert res_unknown["status"] == "error"


def test_all_aton_tools_count():
    """Verify combined tool list contains at least the core Windows and Web tools."""
    assert len(ALL_ATON_TOOLS) >= 6
    names = [t["name"] for t in ALL_ATON_TOOLS]
    assert "open_application" in names
    assert "close_application" in names
    assert "list_running_applications" in names
    assert "web_search" in names
    assert "search_youtube" in names
    assert "open_webpage" in names
