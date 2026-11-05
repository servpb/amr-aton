from types import SimpleNamespace
from unittest.mock import Mock, AsyncMock
import pytest
from src.core.assistant import AMRAssistant, AssistantState


def test_stop_preserves_live_and_capture():
    a=AMRAssistant.__new__(AMRAssistant)
    a.state=AssistantState.CONVERSING
    a.player=Mock(); a.recorder=Mock(); a.wake_detector=Mock(); a.tray=Mock()
    a._live_client=SimpleNamespace(server_turn_open=True,disconnect=Mock())
    a._stop_speaking()
    a.player.stop.assert_called_once()
    a.recorder.flush.assert_not_called()
    a._live_client.disconnect.assert_not_called()
    assert a.state==AssistantState.CONVERSING
    assert a._suppress_interrupted_turn


def test_continuous_default():
    from src.config import Settings
    assert Settings(_env_file=None).continuous_conversation_enabled is False


@pytest.mark.asyncio
async def test_stop_tool_returns_to_local_wake(monkeypatch):
    from src.core import assistant as module
    a=AMRAssistant.__new__(AMRAssistant)
    a._stop_speaking=Mock();a._go_to_sleep=AsyncMock()
    pending=[]
    monkeypatch.setattr(module.asyncio,'create_task',lambda coro:pending.append(coro))
    a._handle_tool_call('', 'stop_listening', {})
    a._stop_speaking.assert_not_called()
    for coro in pending: await coro
    a._go_to_sleep.assert_awaited_once()


def test_new_request_unblocks_response_after_stop():
    a=AMRAssistant.__new__(AMRAssistant)
    a.state=AssistantState.CONVERSING
    a._suppress_interrupted_turn=True
    a._on_new_user_turn()
    assert a._suppress_interrupted_turn is False


@pytest.mark.asyncio
async def test_client_releases_on_new_input_before_audio():
    from src.core.live_client import GeminiLiveClient
    resumed=Mock()
    c=GeminiLiveClient(api_key='',on_user_turn=resumed)
    part=SimpleNamespace(text=None,inline_data=SimpleNamespace(data=b'new'))
    async def receive():
        yield SimpleNamespace(server_content=SimpleNamespace(
            input_transcription=SimpleNamespace(text='Quanto e dois mais dois?'),
            interrupted=False,model_turn=SimpleNamespace(parts=[part]),turn_complete=False),tool_call=None)
        c._is_connected=False
    c._session=SimpleNamespace(receive=receive);c._is_connected=True
    chunks=[]
    async for chunk in c.receive_stream():
        resumed.assert_called_once()
        chunks.append(chunk)
    assert chunks==[b'new']
