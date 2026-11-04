from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from src.core.assistant import AMRAssistant,AssistantState
from src.core.live_client import GeminiLiveClient
from src.config import settings

@pytest.mark.parametrize('enabled,frames,error,healthy,expected', [
    (False,300,None,True,False), (True,100,None,True,False),
    (True,300,'failed',True,False),(True,300,None,False,False),
    (True,300,None,True,True)])
def test_duplex_gate_needs_enabled_healthy_processing(monkeypatch,enabled,frames,error,healthy,expected):
    monkeypatch.setattr(settings,'audio_aec_enabled',enabled)
    a=AMRAssistant.__new__(AMRAssistant)
    a.recorder=SimpleNamespace(engine=SimpleNamespace(error=error,frames_processed=frames),is_healthy=lambda:healthy)
    assert a._aec_duplex_ready() is expected


def test_duplex_gate_rejects_legacy_recorder(monkeypatch):
    monkeypatch.setattr(settings,'audio_aec_enabled',True)
    a=AMRAssistant.__new__(AMRAssistant)
    a.recorder=SimpleNamespace()
    assert not a._aec_duplex_ready()


def test_interruption_clears_output_but_preserves_user_input():
    a=AMRAssistant.__new__(AMRAssistant)
    a.state=AssistantState.CONVERSING
    a.player=Mock();a.recorder=Mock();a.tray=Mock()
    a._was_playing=True
    a._on_voice_interrupted()
    a.player.stop.assert_called_once()
    a.recorder.flush.assert_not_called()
    assert a.state==AssistantState.CONVERSING  # New user request may continue; stop tool ends session.
    assert not a._was_playing


@pytest.mark.asyncio
async def test_server_interruption_drops_audio_on_same_event_and_calls_player_handler():
    callback=Mock()
    client=GeminiLiveClient(api_key='',on_interruption=callback)
    part=SimpleNamespace(inline_data=SimpleNamespace(data=b'old_audio'),text=None,function_call=None)
    interrupted=SimpleNamespace(server_content=SimpleNamespace(interrupted=True,model_turn=SimpleNamespace(parts=[part]),turn_complete=False),tool_call=None)
    fresh_part=SimpleNamespace(inline_data=SimpleNamespace(data=b'new_audio'),text=None,function_call=None)
    fresh=SimpleNamespace(server_content=SimpleNamespace(interrupted=False,model_turn=SimpleNamespace(parts=[fresh_part]),turn_complete=True),tool_call=None)
    async def receive():
        yield interrupted
        yield fresh
        client._is_connected=False
    client._session=SimpleNamespace(receive=receive)
    client._is_connected=True
    chunks=[chunk async for chunk in client.receive_stream()]
    assert chunks==[b'new_audio']
    callback.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize('enabled,expected_sends',[(True,1),(False,0)])
async def test_actual_audio_loop_streams_during_playback_only_with_aec(monkeypatch,enabled,expected_sends):
    import time
    from unittest.mock import AsyncMock
    from src.core import assistant as module
    from src.audio import duplex_aec
    rec=Mock()
    rec.engine=SimpleNamespace(error=None,frames_processed=300)
    rec.is_healthy.return_value=True
    rec.drain_available_chunks.side_effect=lambda chunk,**kwargs:chunk
    player=Mock()
    player.is_playing=True
    detector=Mock()
    detector.detect_stop_command.return_value=False
    monkeypatch.setattr(settings,'audio_aec_enabled',enabled)
    monkeypatch.setattr(settings,'gateway_enabled',False)
    monkeypatch.setattr(module,'AudioRecorder',lambda **kwargs:rec)
    monkeypatch.setattr(module,'AudioPlayer',lambda **kwargs:player)
    monkeypatch.setattr(module,'WakeWordDetector',lambda **kwargs:detector)
    monkeypatch.setattr(duplex_aec,'create_aec_pair',lambda *args:(rec,player))
    a=AMRAssistant()
    a.state=AssistantState.CONVERSING
    a._is_warmup_complete=True
    a._conversation_started_at=time.monotonic()
    a._last_voice_health_log=time.monotonic()
    a._was_playing=True
    a._start_background_warmup=Mock()
    a._run_reminders=AsyncMock()
    a.shutdown=AsyncMock()
    a._live_client=SimpleNamespace(is_connected=True,send_audio_chunk=AsyncMock())
    def one_chunk(timeout):
        a._running=False
        return bytes(2560)
    rec.read_chunk.side_effect=one_chunk
    await a.run()
    assert a._live_client.send_audio_chunk.await_count==expected_sends
    detector.detect_stop_command.assert_called_once()



def test_short_speech_vad_profile_is_explicit_only_in_aec(monkeypatch):
    from google.genai import types
    client=GeminiLiveClient(api_key='')
    monkeypatch.setattr(settings,'audio_aec_enabled',False)
    assert client._aec_realtime_config() is None
    monkeypatch.setattr(settings,'audio_aec_enabled',True)
    config=client._aec_realtime_config()
    assert config.activity_handling==types.ActivityHandling.START_OF_ACTIVITY_INTERRUPTS
    assert config.automatic_activity_detection.prefix_padding_ms==20
    assert config.automatic_activity_detection.silence_duration_ms==700


@pytest.mark.parametrize('server_open,should_suppress',[(True,True),(False,False)])
def test_local_pause_suppresses_only_the_still_generating_turn(server_open,should_suppress):
    a=AMRAssistant.__new__(AMRAssistant)
    a.state=AssistantState.CONVERSING
    a._live_client=SimpleNamespace(server_turn_open=server_open)
    a.player=Mock();a.recorder=Mock();a.tray=Mock()
    a._on_voice_interrupted(source='local_speech')
    assert a._suppress_interrupted_turn is should_suppress
    a.recorder.flush.assert_not_called()
    a._on_voice_turn_complete()
    assert not a._suppress_interrupted_turn


def test_server_interruption_releases_local_suppression_for_new_response():
    a=AMRAssistant.__new__(AMRAssistant)
    a.state=AssistantState.CONVERSING
    a._live_client=SimpleNamespace(server_turn_open=True)
    a.player=Mock();a.recorder=Mock();a.tray=Mock()
    a._on_voice_interrupted(source='local_speech')
    assert a._suppress_interrupted_turn
    a._on_voice_interrupted()
    assert not a._suppress_interrupted_turn
