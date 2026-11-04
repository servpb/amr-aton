"""Voice failure modes tested without a microphone, network or Vosk model."""
import json
import time
from types import SimpleNamespace
from unittest.mock import Mock, AsyncMock
import numpy as np
import pytest
from src.audio.recorder import AudioRecorder
from src.audio.wake_word import WakeWordDetector
from src.core.voice_health import readiness, session_expired

def test_callback_queue_is_bounded_and_keeps_recent_audio():
    rec = AudioRecorder()
    for i in range(100):
        rec._audio_callback(np.full((1280,1), i, dtype=np.int16),1280,None,None)
    assert rec._queue.qsize() == 25
    assert rec.received_chunks == 100
    assert rec.dropped_chunks == 75
    first = rec.read_chunk(timeout=0)
    assert np.frombuffer(first,dtype=np.int16)[0] == 75

def test_old_audio_is_discarded_not_delivered_late():
    rec = AudioRecorder()
    rec._queue.put((time.monotonic()-90,b'old'))
    rec._queue.put((time.monotonic(),b'current'))
    assert rec.read_chunk(.01) == b'current'
    assert rec.dropped_chunks == 1
    assert rec.last_chunk_age_ms < 500

def test_open_stream_without_callbacks_is_not_healthy():
    rec = AudioRecorder()
    rec._is_recording = True
    rec._stream = SimpleNamespace(active=True)
    assert not rec.is_healthy()
    rec._audio_callback(np.zeros((1280,1),dtype=np.int16),1280,None,None)
    assert rec.is_healthy()

@pytest.mark.parametrize('field,value,state', [
    ('microphone_healthy',False,'mic_error'),
    ('detector_ready',False,'init_error'),
    ('warmup_complete',False,'local_listening'),
    ('warmup_error','failed','init_error'),
    ('muted',True,'muted'),
])
def test_readiness_never_hides_failure(field,value,state):
    params=dict(muted=False,microphone_healthy=True,detector_ready=True,warmup_complete=True,warmup_error=None)
    params[field]=value
    assert readiness(**params)[0] == state

def test_noise_cannot_extend_absolute_session_limit():
    assert not session_expired(100,219,120)
    assert session_expired(100,220,120)
    assert session_expired(100,900,120)
    assert not session_expired(0,900,120)

@pytest.mark.parametrize('text,final,expected', [
    ('a tão',False,False),('a tão',True,True),
    ('olá tão',False,False),('olá tão',True,True),
    ('eaton',False,False),('eaton',True,True),
    ('atom',False,False),('tom',False,False),
    ('não chame aton',True,False),('a empresa eaton',True,False),
    ('aton',False,True),('oi aton',False,True),('aton por favor',True,True),
])
def test_acoustic_variants_are_final_only(monkeypatch,text,final,expected):
    monkeypatch.setattr(WakeWordDetector,'_initialize_model',lambda self: None)
    detector=WakeWordDetector(cooldown_seconds=0)
    detector._vosk_rec=SimpleNamespace(
        AcceptWaveform=lambda data: final,
        Result=lambda: json.dumps({'text':text}),
        PartialResult=lambda: json.dumps({'partial':text}),Reset=lambda:None)
    assert detector.process_pcm_chunk(bytes(2560)) is expected
    assert detector.processed_chunks == 1

def test_transcripts_not_logged_by_default(monkeypatch,caplog):
    from src.audio import wake_word
    monkeypatch.setattr(wake_word.settings,'wake_diagnostics',False)
    monkeypatch.setattr(WakeWordDetector,'_initialize_model',lambda self: None)
    detector=WakeWordDetector(cooldown_seconds=0)
    detector._vosk_rec=SimpleNamespace(AcceptWaveform=lambda data:True,
        Result=lambda:json.dumps({'text':'private conversation text'}))
    with caplog.at_level('INFO'):
        detector.process_pcm_chunk(bytes(2560))
    assert 'private conversation text' not in caplog.text

@pytest.mark.asyncio
async def test_connect_timeout_returns_to_sleep(monkeypatch):
    import asyncio
    from src.core import assistant as module
    a=module.AMRAssistant.__new__(module.AMRAssistant)
    a.state=module.AssistantState.SLEEPING
    a._is_warmup_complete=True
    async def hang():
        await asyncio.sleep(5)
    a._live_client=SimpleNamespace(connect=hang)
    a.tray=Mock()
    a.player=Mock()
    a._go_to_sleep=AsyncMock()
    monkeypatch.setattr(module.settings,'voice_connect_timeout_seconds',0.02)
    await asyncio.wait_for(a._wake_up(),timeout=1)
    a._go_to_sleep.assert_awaited_once()

@pytest.mark.asyncio
async def test_active_conversation_cannot_open_duplicate_session():
    from src.core.assistant import AMRAssistant,AssistantState
    a=AMRAssistant.__new__(AMRAssistant)
    a.state=AssistantState.CONVERSING
    a._is_warmup_complete=True
    a._live_client=SimpleNamespace(connect=AsyncMock())
    await a._wake_up()
    a._live_client.connect.assert_not_called()


@pytest.mark.asyncio
async def test_diagnostic_test_respects_mute_without_enabling_microphone():
    from src.core.assistant import AMRAssistant
    a=AMRAssistant.__new__(AMRAssistant)
    a._is_muted=True
    a._voice_test_requested=True
    a.tray=Mock()
    a.recorder=Mock()
    a.wake_detector=Mock()
    await a._begin_voice_test()
    a.wake_detector.start_diagnostics.assert_not_called()
    a.recorder.flush.assert_not_called()
    assert not a._voice_test_requested


def test_diagnostic_window_is_bounded(monkeypatch):
    from src.audio import wake_word
    monkeypatch.setattr(WakeWordDetector,'_initialize_model',lambda self:None)
    d=WakeWordDetector()
    monkeypatch.setattr(wake_word.time,'monotonic',lambda:100)
    d.start_diagnostics(1000)
    assert d._diagnostics_until == 160


@pytest.mark.parametrize('text,expected', [('pare',True),('parar',True),('não pare',False),('quando eu disse pare ele respondeu',False),('para',True)])
def test_stop_requires_explicit_short_command(monkeypatch,text,expected):
    monkeypatch.setattr(WakeWordDetector,'_initialize_model',lambda self:None)
    d=WakeWordDetector()
    d._stop_rec=SimpleNamespace(AcceptWaveform=lambda data:True,Result=lambda:json.dumps({'text':text}),Reset=Mock())
    assert d.detect_stop_command(bytes(2560)) is expected


def test_stop_recognizer_receives_silence_and_preserves_wake_state(monkeypatch):
    monkeypatch.setattr(WakeWordDetector,'_initialize_model',lambda self:None)
    d=WakeWordDetector()
    d._vosk_rec=Mock()
    stop=Mock()
    stop.AcceptWaveform.return_value=True
    stop.Result.return_value=json.dumps({'text':'pare'})
    d._stop_rec=stop
    assert d.detect_stop_command(bytes(2560))
    stop.AcceptWaveform.assert_called_once_with(bytes(2560))
    d._vosk_rec.AcceptWaveform.assert_not_called()


def test_partial_stop_never_ends_session_even_when_stable(monkeypatch):
    from src.audio import wake_word
    monkeypatch.setattr(WakeWordDetector,'_initialize_model',lambda self:None)
    clock=[100.0]
    monkeypatch.setattr(wake_word.time,'monotonic',lambda:clock[0])
    d=WakeWordDetector()
    d._stop_rec=SimpleNamespace(AcceptWaveform=lambda data:False,PartialResult=lambda:json.dumps({'partial':'pare'}),Reset=Mock())
    assert not d.detect_stop_command(bytes(2560))
    clock[0]+=.1
    d.reset(include_stop=False)
    assert not d.detect_stop_command(bytes(2560))
    clock[0]+=.2
    assert not d.detect_stop_command(bytes(2560))


@pytest.mark.asyncio
async def test_gemini_stop_tool_really_disconnects_and_returns_to_sleep(monkeypatch):
    from src.core import assistant as module
    a=module.AMRAssistant.__new__(module.AMRAssistant)
    a.state=module.AssistantState.CONVERSING
    a._receive_task=None
    a.player=Mock()
    a._live_client=SimpleNamespace(disconnect=AsyncMock())
    a.recorder=Mock()
    a.wake_detector=Mock()
    a.tray=Mock()
    a._is_muted=False
    a._is_warmup_complete=True
    scheduled=[]
    monkeypatch.setattr(module.asyncio,'create_task',lambda coro:scheduled.append(coro))
    a._handle_tool_call('id','stop_listening',{})
    assert len(scheduled)==1
    await scheduled[0]
    assert a.state==module.AssistantState.SLEEPING
    a.player.stop.assert_called_once()
    a._live_client.disconnect.assert_awaited_once()
    a.recorder.flush.assert_called_once()


def test_stop_tool_is_exposed_to_model_once():
    from src.tools import ALL_ATON_TOOLS
    assert sum(t['name']=='stop_listening' for t in ALL_ATON_TOOLS)==1


@pytest.mark.parametrize('text', ['encerre a conversa','encerrar a conversa','pare de falar'])
def test_local_stop_handles_explicit_end_conversation(monkeypatch,text):
    monkeypatch.setattr(WakeWordDetector,'_initialize_model',lambda self:None)
    d=WakeWordDetector()
    d._stop_rec=SimpleNamespace(AcceptWaveform=lambda data:True,Result=lambda:json.dumps({'text':text}),Reset=Mock())
    assert d.detect_stop_command(bytes(2560))


def test_constrained_stop_keeps_unknown_and_negative_alternatives():
    from src.audio.stop_commands import build_stop_recognizer
    grammar=[]
    rec=SimpleNamespace(SetWords=lambda flag:None)
    def factory(model,rate,phrases):
        grammar.extend(json.loads(phrases))
        return rec
    assert build_stop_recognizer(SimpleNamespace(vosk_model_find_word=lambda word:1),factory,16000) is rec
    assert '[unk]' in grammar
    assert 'não pare' in grammar
    assert 'encerre a conversa' in grammar


@pytest.mark.parametrize('text', ['não pare','ele disse pare','a palavra pare'])
def test_stop_does_not_trigger_on_negative_or_quoted_long_sentence(monkeypatch,text):
    monkeypatch.setattr(WakeWordDetector,'_initialize_model',lambda self:None)
    d=WakeWordDetector()
    d._stop_rec=SimpleNamespace(AcceptWaveform=lambda data:True,Result=lambda:json.dumps({'text':text}),Reset=Mock())
    assert not d.detect_stop_command(bytes(2560))
