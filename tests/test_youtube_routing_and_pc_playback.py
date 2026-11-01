"""Unit tests for YouTube Playback Routing, PC Direct Playback, and Task Context Integrity.

Scenarios verified:
1. Context PC + explicit Fire Stick request.
2. Context Fire Stick + explicit PC request.
3. Request without destination and without context (clarification needed).
4. Playback maintaining PC context.
5. Search without automatic playback.
6. Ordinal choice resuming correct task and tool.
7. Autoplay blocked without false confirmation.
8. Failure after send without automatic retry.
"""

from unittest.mock import MagicMock, patch
import pytest

from src.core.destination_guard import evaluate_destination_guard, resolve_clarified_destination
from src.core.target_context import get_target_context
from src.core.task_context import TaskContextManager, get_task_context
from src.tools import dispatch_tool
from src.tools.task_tools import selecionar_opcao_pendente
from src.tools.web_browser import play_pc_youtube


@pytest.fixture(autouse=True)
def clean_context():
    """Ensure clean target and task contexts before each test."""
    target_ctx = get_target_context()
    target_ctx.clear()
    task_ctx = get_task_context()
    task_ctx._active_task = None
    task_ctx._pending_action = None
    task_ctx._pending_clarification = None
    task_ctx._pending_candidates = None
    yield
    target_ctx.clear()
    task_ctx._active_task = None
    task_ctx._pending_action = None
    task_ctx._pending_clarification = None
    task_ctx._pending_candidates = None


def test_1_context_pc_with_explicit_fire_tv():
    """Scenario 1: Context is PC, but user explicitly requests Fire Stick.
    Fire Stick request must override prior PC context.
    """
    ctx = get_target_context()
    ctx.set_target("pc")
    assert ctx.get_active_target() == "pc"

    with patch("src.tools.fire_tv.play_fire_tv_youtube", return_value={"status": "success", "confirmed": True, "message": "Tocando no Fire Stick"}) as mock_ftv, \
         patch("src.tools.web_browser.play_pc_youtube") as mock_pc:
        
        # User says explicitly 'no Fire Stick'
        res = dispatch_tool("play_fire_tv_youtube", {"query": "Roberto Carlos", "destination": "fire_tv"})
        assert res["status"] == "success"
        mock_ftv.assert_called_once()
        mock_pc.assert_not_called()
        assert ctx.get_active_target() == "fire_tv"


def test_2_context_fire_tv_with_explicit_pc():
    """Scenario 2: Context is Fire Stick, but user explicitly requests PC.
    PC request must override prior Fire TV context and launch play_pc_youtube.
    """
    ctx = get_target_context()
    ctx.set_target("fire_tv")
    assert ctx.get_active_target() == "fire_tv"

    with patch("src.tools.web_browser.play_pc_youtube", return_value={"status": "success", "execution_state": "concluida", "message": "Tocando no PC"}) as mock_pc, \
         patch("src.tools.fire_tv.play_fire_tv_youtube") as mock_ftv:
        
        # Explicit PC destination
        res = dispatch_tool("play_fire_tv_youtube", {"query": "Roberto Carlos", "destination": "pc"})
        assert res["status"] == "success"
        mock_pc.assert_called_once_with(query="Roberto Carlos", video_id=None)
        mock_ftv.assert_not_called()
        assert ctx.get_active_target() == "pc"


def test_3_request_without_destination_and_without_context():
    """Scenario 3: User requests playback without destination and with no active context.
    Must block with needs_clarification and produce zero physical effect.
    """
    ctx = get_target_context()
    assert ctx.get_active_target() is None

    with patch("src.tools.fire_tv.play_fire_tv_youtube") as mock_ftv, \
         patch("src.tools.web_browser.play_pc_youtube") as mock_pc:
        
        res = dispatch_tool("play_music", {"query": "Roberto Carlos"})
        assert res["status"] == "needs_clarification"
        assert res["destination_needed"] is True
        assert "computador ou no Fire Stick" in res["message"]

        mock_ftv.assert_not_called()
        mock_pc.assert_not_called()

        pending = ctx.get_pending_action()
        assert pending is not None
        assert pending["action_type"] == "play_music"
        assert pending["params"]["query"] == "Roberto Carlos"


def test_4_playback_maintaining_pc_context():
    """Scenario 4: User requests playback when PC context is active.
    Must dispatch to play_pc_youtube (never search_youtube) and maintain PC context.
    """
    ctx = get_target_context()
    ctx.set_target("pc")

    with patch("src.tools.web_browser.play_pc_youtube", return_value={"status": "success", "execution_state": "concluida", "message": "Tocando no PC"}) as mock_pc, \
         patch("src.tools.web_browser.search_youtube") as mock_search:
        
        res = dispatch_tool("play_music", {"query": "Evidências"})
        assert res["status"] == "success"
        mock_pc.assert_called_once_with(query="Evidências", video_id=None)
        mock_search.assert_not_called()
        assert ctx.get_active_target() == "pc"


def test_5_search_without_automatic_playback():
    """Scenario 5: User explicitly asks to search ('pesquisar').
    Must open search results (search_youtube), never initiate direct playback.
    """
    ctx = get_target_context()
    ctx.set_target("pc")

    with patch("src.tools.web_browser.search_youtube", return_value={"status": "success", "message": "Pesquisando no YouTube"}) as mock_search, \
         patch("src.tools.web_browser.play_pc_youtube") as mock_play:
        
        res = dispatch_tool("search_youtube", {"query": "Roberto Carlos"})
        assert res["status"] == "success"
        mock_search.assert_called_once_with(query="Roberto Carlos")
        mock_play.assert_not_called()


def test_6_ordinal_choice_resumes_correct_task_and_tool():
    """Scenario 6: Generic request produces candidates; user chooses 'a segunda'.
    Candidate resolution must resume the correct task and call play_pc_youtube.
    """
    task_mgr = get_task_context()
    target_ctx = get_target_context()
    target_ctx.set_target("pc")

    task = task_mgr.start_task("tocar_musica", target="pc", parameters={"query": "Roberto Carlos"})
    candidates = [
        {"id": "vid_1", "title": "Roberto Carlos - Como é Grande o Meu Amor Por Você"},
        {"id": "vid_2", "title": "Roberto Carlos - Detalhes"},
        {"id": "vid_3", "title": "Roberto Carlos - Emoções"},
    ]
    task_mgr.set_pending_candidates(candidates, context_hint="youtube_music_pc")

    with patch("src.tools.web_browser.play_pc_youtube", return_value={"status": "success", "title": "Roberto Carlos - Detalhes"}) as mock_play_pc, \
         patch("src.tools.web_browser.search_youtube") as mock_search:
        
        res = selecionar_opcao_pendente(escolha="a segunda")
        assert res["status"] == "success"
        mock_play_pc.assert_called_once_with(video_id="vid_2", query="Roberto Carlos - Detalhes")
        mock_search.assert_not_called()


def test_7_autoplay_blocked_without_false_confirmation():
    """Scenario 7: Browser opens watch?v=ID but autoplay is blocked (no audio output).
    Must report verification_state='inconclusive' and inform honestly without false confirmation.
    """
    with patch("src.tools.youtube_search.lookup_youtube_videos", return_value=[{"id": "test_id", "title": "Video Teste"}]), \
         patch("webbrowser.open", return_value=True), \
         patch("time.sleep"), \
         patch("pycaw.pycaw.AudioUtilities.GetAllSessions", return_value=[]):
        
        res = play_pc_youtube(video_id="test_id", query="Video Teste")
        assert res["status"] == "success"
        assert res["verification_state"] == "inconclusive"
        assert res["execution_state"] == "inconclusiva"
        assert "não consegui confirmar a reprodução" in res["message"]
        assert "watch?v=test_id" in res["url"]


def test_8_failure_after_send_without_automatic_retry():
    """Scenario 8: Action sent with uncertain transport state must not be duplicated.
    Task context records action_sent and verification inconclusive without auto duplicate.
    """
    task_mgr = get_task_context()
    task = task_mgr.start_task("tocar_musica", target="pc", parameters={"query": "Roberto Carlos"})
    task_id, action_id = task_mgr.record_action_planned("play_url", {"video_id": "vid_123"})
    task_mgr.record_transport_result(task_id, action_id, "sent_uncertain")

    active_task = task_mgr.get_active_task()
    assert active_task is not None
    assert active_task.transport_state == "sent_uncertain"

    # Verification records inconclusive
    task_mgr.record_verification_result(task_id, action_id, "inconclusive", evidence={"reason": "no_ack"})
    task_after = task_mgr.get_active_task()
    assert task_after.verification_state == "inconclusive"
