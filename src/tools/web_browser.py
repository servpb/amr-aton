"""Web browser automation and search tools for Aton using Playwright and native fallbacks."""

import logging
import urllib.parse
import webbrowser
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Try importing Playwright for deep automated browser control
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None  # type: ignore
    logger.info("Playwright not installed. Web tools will use default system browser.")


def normalize_url(url: str) -> str:
    """Ensure URL has a valid scheme."""
    cleaned = url.strip()
    if not cleaned.startswith(("http://", "https://")):
        return f"https://{cleaned}"
    return cleaned


def open_webpage(url: str, visible: bool = True) -> Dict[str, Any]:
    """Open a webpage in the browser.

    Args:
        url: The web address to navigate to.
        visible: Whether to open in a visible window.

    Returns:
        Dict containing execution status and user message.
    """
    target_url = normalize_url(url)
    logger.info(f"Navigating to webpage: {target_url}...")

    # 1. Try Playwright if available and headless/advanced control requested
    if sync_playwright is not None:
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=not visible)
                page = browser.new_page()
                page.goto(target_url, timeout=10000)
                title = page.title()
                if not visible:
                    # Headless extraction
                    content_preview = page.inner_text("body")[:300]
                    browser.close()
                    return {
                        "status": "success",
                        "message": f"Página '{title}' lida com sucesso: {content_preview}...",
                        "title": title,
                        "url": target_url,
                    }
                # Keep browser open for user by letting system launch or keeping process
                browser.close()
        except Exception as exc:
            logger.debug(f"Playwright navigation notice: {exc}. Falling back to default browser.")

    # 2. Native fallback: open in default Windows browser (Chrome, Edge, etc.)
    try:
        webbrowser.open(target_url)
        return {
            "status": "success",
            "message": f"Abrindo a página '{target_url}' no seu navegador, senhor.",
            "url": target_url,
        }
    except Exception as exc:
        logger.error(f"Failed to open webpage '{target_url}': {exc}")
        return {
            "status": "error",
            "message": f"Não foi possível abrir a página '{target_url}': {exc}",
        }


def web_search(query: str) -> Dict[str, Any]:
    """Perform a web search on Google.

    Args:
        query: Search term or question.

    Returns:
        Dict containing execution status and response message.
    """
    cleaned_query = query.strip()
    if not cleaned_query:
        return {"status": "error", "message": "Nenhum termo de pesquisa fornecido."}

    logger.info(f"Performing web search for: '{cleaned_query}'...")
    encoded_query = urllib.parse.quote_plus(cleaned_query)
    search_url = f"https://www.google.com/search?q={encoded_query}"

    try:
        webbrowser.open(search_url)
        return {
            "status": "success",
            "message": f"Pesquisando sobre '{cleaned_query}' no Google, senhor.",
            "query": cleaned_query,
            "url": search_url,
        }
    except Exception as exc:
        logger.error(f"Error performing web search for '{cleaned_query}': {exc}")
        return {
            "status": "error",
            "message": f"Erro ao realizar pesquisa na web: {exc}",
        }


def search_youtube(query: str) -> Dict[str, Any]:
    """Search for videos, music, or topics on YouTube.

    Args:
        query: Music, video, or channel to search.

    Returns:
        Dict containing execution status and response message.
    """
    cleaned_query = query.strip()
    if not cleaned_query:
        return {"status": "error", "message": "Nenhum termo de pesquisa para o YouTube fornecido."}

    logger.info(f"Searching YouTube for: '{cleaned_query}'...")
    encoded_query = urllib.parse.quote_plus(cleaned_query)
    yt_url = f"https://www.youtube.com/results?search_query={encoded_query}"

    try:
        webbrowser.open(yt_url)
        return {
            "status": "success",
            "message": f"Pesquisando '{cleaned_query}' no YouTube, senhor.",
            "query": cleaned_query,
            "url": yt_url,
        }
    except Exception as exc:
        logger.error(f"Error searching YouTube for '{cleaned_query}': {exc}")
        return {
            "status": "error",
            "message": f"Erro ao buscar no YouTube: {exc}",
        }


def dispatch_web_tool(tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
    """Route web tool calls to appropriate functions."""
    if tool_name == "web_search":
        q = tool_args.get("query", "")
        return web_search(query=q)
    elif tool_name == "search_youtube":
        q = tool_args.get("query", "")
        return search_youtube(query=q)
    elif tool_name == "open_webpage":
        u = tool_args.get("url", "")
        return open_webpage(url=u)
    else:
        return {
            "status": "error",
            "message": f"Ferramenta web desconhecida '{tool_name}'.",
        }


# Gemini Live Function Declarations for Web Automation
WEB_BROWSER_FUNCTION_DECLARATIONS = [
    {
        "name": "web_search",
        "description": "Pesquisa um termo, assunto, dúvida ou notícia na internet através do Google.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {
                    "type": "STRING",
                    "description": "Termo de busca ou pergunta a ser pesquisada na web (ex: 'previsão do tempo São Paulo', 'notícias tecnologia hoje').",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_youtube",
        "description": "Pesquisa e abre vídeos, músicas, canais ou playlists no YouTube.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {
                    "type": "STRING",
                    "description": "Nome da música, artista, vídeo ou tema para pesquisar no YouTube (ex: 'lo-fi hip hop', 'tutorial python', 'queen bohemian rhapsody').",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "open_webpage",
        "description": "Abre um site, portal ou endereço da web específico pelo link/URL no navegador.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "url": {
                    "type": "STRING",
                    "description": "Endereço ou domínio do site a ser acessado (ex: 'github.com', 'wikipedia.org', 'g1.globo.com').",
                },
            },
            "required": ["url"],
        },
    },
]
