"""Web browser automation and search tools for Aton using Playwright and native fallbacks."""

import logging
import re
import time
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


def play_pc_youtube(
    query: Optional[str] = None,
    video_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Search and launch playback of a video or song directly on PC browser without degrading to search.

    Differentiates playing vs searching. Reuses lookup_youtube_videos.
    Handles generic requests (e.g. 'uma música de Roberto Carlos') by presenting real candidate options.
    Awaits player state verification without falsely confirming autoplay.
    """
    from src.core.task_context import get_task_context
    from src.tools.youtube_search import lookup_youtube_videos

    task_mgr = get_task_context()
    task_id, action_id = task_mgr.record_action_planned("play_pc_youtube", {"query": query, "video_id": video_id})

    if not task_mgr.is_action_allowed(task_id):
        return {
            "status": "cancelled",
            "task_id": task_id,
            "action_id": action_id,
            "execution_state": "cancelada",
            "target": "pc",
            "transport_state": "not_sent",
            "action_sent": False,
            "verification_state": "unverified",
            "message": "Reprodução no computador cancelada antes do envio, senhor.",
        }

    vid = (video_id or "").strip()
    q = (query or "").strip()

    if not vid and not q:
        return {
            "status": "needs_clarification",
            "message": "Por favor, informe o título da música ou vídeo que o senhor deseja tocar no computador.",
        }

    target_vid = vid
    target_title = q

    if not target_vid:
        generic_match = re.search(
            r"^(?:uma\s+m[uú]sica|m[uú]sica|algo|alguma\s+coisa|faixa|som)\s+(?:do|da|de|pelo|pela)\s+(.+)$",
            q,
            re.IGNORECASE,
        )
        artist_name = generic_match.group(1).strip() if generic_match else None

        candidates = lookup_youtube_videos(q, max_results=3)
        if not candidates:
            task_mgr.record_transport_result(task_id, action_id, "not_sent")
            task_mgr.record_verification_result(task_id, action_id, "failed")
            return {
                "status": "error",
                "task_id": task_id,
                "action_id": action_id,
                "execution_state": "falhou",
                "target": "pc",
                "transport_state": "not_sent",
                "action_sent": False,
                "verification_state": "failed",
                "message": f"Nenhum vídeo encontrado para '{q}' no YouTube, senhor.",
            }

        is_just_artist = bool(artist_name)
        if not is_just_artist:
            for c in candidates:
                if q.lower() == c.get("channel", "").lower():
                    is_just_artist = True
                    break

        # If generic artist request with multiple options, present candidates
        if is_just_artist and len(candidates) > 1:
            cand_titles = [f"'{c['title']}'" for c in candidates[:2]]
            task_mgr.set_pending_candidates(candidates, context_hint="youtube_music_pc")
            active_task = task_mgr.get_active_task()
            return {
                "status": "needs_clarification",
                "step": "multiple_candidates",
                "task_id": active_task.task_id if active_task else task_id,
                "execution_state": "aguardando_esclarecimento",
                "target": "pc",
                "query": q,
                "candidates": [c["title"] for c in candidates],
                "message": f"Encontrei opções no computador como {', ou '.join(cand_titles)}. Qual música o senhor prefere ouvir, ou posso colocar a primeira?",
            }

        target_vid = candidates[0]["id"]
        target_title = candidates[0]["title"]

    watch_url = f"https://www.youtube.com/watch?v={target_vid}"
    logger.info(f"Opening YouTube playback on PC: {watch_url} ({target_title})...")

    try:
        webbrowser.open(watch_url)
        task_mgr.record_transport_result(task_id, action_id, "sent_confirmed")
    except Exception as exc:
        logger.error(f"Error launching browser for '{watch_url}': {exc}")
        task_mgr.record_transport_result(task_id, action_id, "sent_uncertain")
        task_mgr.record_verification_result(task_id, action_id, "failed")
        return {
            "status": "error",
            "task_id": task_id,
            "action_id": action_id,
            "execution_state": "falhou",
            "target": "pc",
            "transport_state": "sent_uncertain",
            "action_sent": False,
            "verification_state": "failed",
            "message": f"Erro ao abrir vídeo no computador: {exc}",
        }

    # Bounded verification of player state without falsely confirming autoplay
    time.sleep(1.0)
    audio_confirmed = False
    try:
        from pycaw.pycaw import AudioUtilities, IAudioMeterInformation
        sessions = AudioUtilities.GetAllSessions()
        for s in sessions:
            if s.Process and s.Process.name().lower() in ("msedge.exe", "chrome.exe", "firefox.exe", "brave.exe"):
                try:
                    meter = s._ctl.QueryInterface(IAudioMeterInformation)
                    if meter and meter.GetPeakValue() > 0.001:
                        audio_confirmed = True
                        break
                except Exception:
                    pass
    except Exception as e:
        logger.debug(f"Audio meter verification skipped/failed: {e}")

    if audio_confirmed:
        task_mgr.record_verification_result(
            task_id,
            action_id,
            "confirmed",
            evidence={"type": "audio_meter", "video_id": target_vid, "title": target_title},
        )
        return {
            "status": "success",
            "task_id": task_id,
            "action_id": action_id,
            "execution_state": "concluida",
            "target": "pc",
            "transport_state": "sent_confirmed",
            "action_sent": True,
            "verification_state": "confirmed",
            "video_id": target_vid,
            "title": target_title,
            "url": watch_url,
            "message": f"Reproduzindo '{target_title}' no computador, senhor.",
        }
    else:
        # Autoplay might be blocked or unverified: Report honestly as inconclusive
        task_mgr.record_verification_result(
            task_id,
            action_id,
            "inconclusive",
            evidence={"type": "url_opened_unverified_audio", "video_id": target_vid, "title": target_title},
        )
        return {
            "status": "success",
            "task_id": task_id,
            "action_id": action_id,
            "execution_state": "inconclusiva",
            "target": "pc",
            "transport_state": "sent_confirmed",
            "action_sent": True,
            "verification_state": "inconclusive",
            "video_id": target_vid,
            "title": target_title,
            "url": watch_url,
            "message": f"Abri o vídeo '{target_title}', mas não consegui confirmar a reprodução automática. Pode ser necessário clicar para reproduzir.",
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
    elif tool_name == "play_pc_youtube":
        q = tool_args.get("query")
        v = tool_args.get("video_id")
        return play_pc_youtube(query=q, video_id=v)
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
        "name": "play_pc_youtube",
        "description": "Reproduz um vídeo, música ou clipe específico no YouTube do computador. Busca a melhor correspondência e abre diretamente a página de reprodução.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {
                    "type": "STRING",
                    "description": "Nome da música ou artista para tocar no computador (ex: 'Como É Grande o Meu Amor por Você Roberto Carlos').",
                },
                "video_id": {
                    "type": "STRING",
                    "description": "ID do vídeo do YouTube se já conhecido.",
                },
            },
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
