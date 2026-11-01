"""Unit tests for Fire TV YouTube search, music playback, and destination disambiguation."""

from unittest.mock import MagicMock, patch
import pytest

from src.core.target_context import get_target_context
from src.tools import dispatch_tool
from src.tools.fire_tv import (
    get_fire_tv_youtube_playback_state,
    play_fire_tv_youtube,
    search_fire_tv_youtube,
)
from src.tools.youtube_search import lookup_youtube_videos


@pytest.fixture(autouse=True)
def clean_context():
    """Ensure context is clean before and after tests."""
    ctx = get_target_context()
    ctx.clear()
    yield
    ctx.clear()


def test_search_fire_tv_youtube_success_and_step_differentiation():
    """Verify search intent is sent to YouTube app without starting playback."""
    with patch("src.tools.fire_tv._execute", return_value={"status": "success", "output": ""}) as mock_exec, \
         patch("src.tools.fire_tv._get_foreground_package", return_value="com.amazon.firetv.youtube"):
        res = search_fire_tv_youtube("Roberto Carlos")
        assert res["status"] == "success"
        assert res["step"] == "search_opened_in_app"
        assert res["confirmed"] is True
        assert "Roberto Carlos" in res["message"]

        # Verify command sent matches search intent and does NOT start playback
        mock_exec.assert_called_once()
        cmd = mock_exec.call_args[0][0]
        assert "am" in cmd and "start" in cmd
        assert any("results?search_query=Roberto%20Carlos" in arg or "results?search_query=Roberto+Carlos" in arg for arg in cmd)
        assert "com.amazon.firetv.youtube" in cmd


def test_search_fire_tv_youtube_unconfirmed_focus():
    """Verify return state when search intent is delivered but foreground focus check times out."""
    with patch("src.tools.fire_tv._execute", return_value={"status": "success", "output": ""}), \
         patch("src.tools.fire_tv._get_foreground_package", return_value="com.amazon.tv.launcher"):
        res = search_fire_tv_youtube("Receitas de bolo")
        assert res["status"] == "success"
        assert res["step"] == "search_sent"
        assert res["confirmed"] is False


def test_search_fire_tv_youtube_rejects_empty():
    """Verify empty query is rejected safely."""
    res = search_fire_tv_youtube("   ")
    assert res["status"] == "error"
    assert "Nenhum termo" in res["message"]


def test_play_fire_tv_youtube_playback_confirmed():
    """Verify specific song lookup and playback confirmation via media session."""
    mock_candidates = [
        {
            "id": "bsN1_oRPLns",
            "title": "Roberto Carlos - Como é Grande o Meu Amor por Você",
            "channel": "Roberto Carlos",
        }
    ]
    with patch("src.tools.youtube_search.lookup_youtube_videos", return_value=mock_candidates), \
         patch("src.tools.fire_tv._execute", return_value={"status": "success", "output": ""}) as mock_exec, \
         patch("src.tools.fire_tv.get_fire_tv_youtube_playback_state", return_value={"is_playing": True, "title": "Roberto Carlos"}):
        res = play_fire_tv_youtube("Como é Grande o Meu Amor por Você, do Roberto Carlos")
        assert res["status"] == "success"
        assert res["step"] == "playback_confirmed"
        assert res["confirmed"] is True
        assert res["video_id"] == "bsN1_oRPLns"
        assert "Reprodução confirmada" in res["message"]

        # Ensure correct watch URL was invoked
        mock_exec.assert_called_once()
        cmd = mock_exec.call_args[0][0]
        assert any("watch?v=bsN1_oRPLns" in arg for arg in cmd)


def test_play_fire_tv_youtube_video_selected_and_opened():
    """Verify return step when video is opened but media session playback is not yet active."""
    mock_candidates = [
        {"id": "1w7OgIMMRc4", "title": "Música Teste", "channel": "Artista"}
    ]
    with patch("src.tools.youtube_search.lookup_youtube_videos", return_value=mock_candidates), \
         patch("src.tools.fire_tv._execute", return_value={"status": "success", "output": ""}), \
         patch("src.tools.fire_tv.get_fire_tv_youtube_playback_state", return_value={"is_playing": False}):
        res = play_fire_tv_youtube("Música Teste")
        assert res["status"] == "success"
        assert res["step"] == "video_selected_and_opened"
        assert res["confirmed"] is False
        assert "escolhido e aberto" in res["message"]


def test_play_fire_tv_youtube_generic_request_asks_clarification():
    """Verify 'Toque uma música do Roberto Carlos' without specific title asks for clarification."""
    mock_candidates = [
        {"id": "vid1", "title": "Como é Grande o Meu Amor por Você", "channel": "Roberto Carlos"},
        {"id": "vid2", "title": "Detalhes", "channel": "Roberto Carlos"},
        {"id": "vid3", "title": "Emoções", "channel": "Roberto Carlos"},
    ]
    with patch("src.tools.youtube_search.lookup_youtube_videos", return_value=mock_candidates):
        res = play_fire_tv_youtube("uma música do Roberto Carlos")
        assert res["status"] == "needs_clarification"
        assert res["step"] == "multiple_candidates"
        assert len(res["candidates"]) == 3
        assert "Qual música o senhor prefere tocar" in res["message"]


def test_playback_state_parser():
    """Verify parsing of dumpsys media_session output for YouTube."""
    fake_dumpsys = """
    Sessions Stack - have 4 sessions:
      starboard_media com.amazon.firetv.youtube/starboard_media (userId=0)
        package=com.amazon.firetv.youtube
        state=PlaybackState {state=3, position=1460, buffered position=0, speed=1.0, updated=36411351}
        metadata:size=4, description=Roberto Carlos - Como é Grande o Meu Amor por Você, Roberto Carlos, null
    """
    with patch("src.tools.fire_tv._execute", return_value={"status": "success", "output": fake_dumpsys}):
        state = get_fire_tv_youtube_playback_state()
        assert state["is_playing"] is True
        assert state["is_paused"] is False
        assert state["state_code"] == 3
        assert "Roberto Carlos" in state["title"]


def test_destination_guard_blocks_ambiguous_youtube_search():
    """Verify 'Pesquise Roberto Carlos no YouTube' without destination is blocked and asks PC or Fire Stick."""
    ctx = get_target_context()
    assert ctx.get_active_target() is None

    res = dispatch_tool("search_fire_tv_youtube", {"query": "Roberto Carlos"})
    assert res["status"] == "needs_clarification"
    assert res["destination_needed"] is True
    assert "computador ou no Fire Stick" in res["message"]

    # Resume on Fire TV
    with patch("src.tools.fire_tv.search_fire_tv_youtube", return_value={"status": "success", "step": "search_opened_in_app", "confirmed": True, "message": "OK"}) as mock_search:
        res_resume = dispatch_tool("resolve_destination", {"destination": "fire_tv"})
        assert res_resume["status"] == "success"
        mock_search.assert_called_once_with("Roberto Carlos")
        assert ctx.get_active_target() == "fire_tv"


def test_destination_guard_blocks_ambiguous_play_music():
    """Verify 'Toque Como é Grande o Meu Amor por Você' without destination asks PC or Fire Stick."""
    ctx = get_target_context()
    assert ctx.get_active_target() is None

    res = dispatch_tool("play_fire_tv_youtube", {"query": "Como é Grande o Meu Amor por Você"})
    assert res["status"] == "needs_clarification"
    assert res["destination_needed"] is True

    # Resume on PC (Phase 16.1: routes to play_pc_youtube preserving playback intention)
    with patch("src.tools.web_browser.play_pc_youtube", return_value={"status": "success", "message": "Tocando no PC"}) as mock_play:
        res_resume = dispatch_tool("resolve_destination", {"destination": "pc"})
        assert res_resume["status"] == "success"
        mock_play.assert_called_once_with(query="Como é Grande o Meu Amor por Você", video_id=None)
        assert ctx.get_active_target() == "pc"


def test_explicit_destination_fire_tv_search_passes_immediately():
    """Verify explicit destination 'no Fire Stick' executes immediately without asking."""
    ctx = get_target_context()
    with patch("src.tools.fire_tv.search_fire_tv_youtube", return_value={"status": "success", "step": "search_opened_in_app", "confirmed": True, "message": "Busca aberta"}) as mock_search:
        res = dispatch_tool("search_fire_tv_youtube", {"query": "Roberto Carlos", "destination": "fire_tv"})
        assert res["status"] == "success"
        mock_search.assert_called_once()
        assert ctx.get_active_target() == "fire_tv"

