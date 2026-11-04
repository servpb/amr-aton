import json
from types import SimpleNamespace
import pytest
from src.audio.wake_comparison import VoskWakeComparison, evaluate_candidate

def result(text, conf=.95, duration=.6):
    return {'text':text,'result':[{'word':w,'conf':conf,'start':i*.2,'end':i*.2+duration} for i,w in enumerate(text.split())]}

@pytest.mark.parametrize('text', ['pão','oi','dom','bom','[unk]','atom [unk]','a empresa eaton'])
def test_common_words_and_unknowns_are_not_candidates(text):
    assert not evaluate_candidate(result(text),{'atom','eaton'})[0]

@pytest.mark.parametrize('data', [result('atom',.5),result('atom',duration=.01),{'text':'atom'},result('atom',float('nan'))])
def test_candidate_needs_final_word_evidence(data):
    assert not evaluate_candidate(data,{'atom'})[0]

def test_exact_final_target_is_only_a_candidate():
    assert evaluate_candidate(result('oi atom'),{'oi atom'}) == (True,'candidate_only')

def test_missing_vocabulary_removed_and_unknown_path_kept():
    captured=[]
    rec=SimpleNamespace(SetWords=lambda x:None,Reset=lambda:None,
        AcceptWaveform=lambda data:True,Result=lambda:json.dumps(result('atom')))
    def factory(model,rate,grammar):
        captured.extend(json.loads(grammar))
        return rec
    model=SimpleNamespace(vosk_model_find_word=lambda word: 1 if word in {'atom','oi','pão'} else -1)
    comparison=VoskWakeComparison(model,factory,16000)
    assert '[unk]' in captured
    assert 'pão' in captured
    assert 'eaton' not in captured
    observation=comparison.process(bytes(2560))
    assert observation['candidate'] is True
    assert comparison.candidate_count == 1
    # It returns a diagnostic record, never a wake boolean or callback.
    assert isinstance(observation,dict)


@pytest.mark.parametrize('candidate,expected', [(True,True),(False,False)])
def test_experimental_activation_policy(monkeypatch,candidate,expected):
    from unittest.mock import Mock
    from src.audio.wake_word import WakeWordDetector
    monkeypatch.setattr(WakeWordDetector,'_initialize_model',lambda self:None)
    d=WakeWordDetector(cooldown_seconds=0)
    d._directed=SimpleNamespace(process=lambda *a,**kw:{'candidate':candidate,'reason':'candidate_only' if candidate else 'low_confidence'},reset=Mock())
    d._vosk_rec=Mock()
    assert d.process_pcm_chunk(bytes(2560)) is expected
    # Negative directed result must not be bypassed by generic recognition.
    d._vosk_rec.AcceptWaveform.assert_not_called()
    if candidate:
        assert d.last_decision=='accepted_directed_final'
        d._directed.reset.assert_called_once()


def test_directed_rearm_after_sleep_preserves_general_stop(monkeypatch):
    from unittest.mock import Mock
    from src.audio.wake_word import WakeWordDetector
    monkeypatch.setattr(WakeWordDetector,'_initialize_model',lambda self:None)
    d=WakeWordDetector(cooldown_seconds=0)
    d._directed=SimpleNamespace(process=lambda *a,**kw:{'candidate':True,'reason':'candidate_only'},reset=Mock())
    d._vosk_rec=SimpleNamespace(AcceptWaveform=lambda data:True,Result=lambda:json.dumps({'text':'pare'}),Reset=Mock())
    assert d.process_pcm_chunk(bytes(2560))
    assert d.detect_stop_command(bytes(2560))
    d.reset()
    assert d.process_pcm_chunk(bytes(2560))


def test_no_transcription_logging_outside_diagnostic_window(caplog):
    model=SimpleNamespace(vosk_model_find_word=lambda word:1)
    rec=SimpleNamespace(SetWords=lambda value:None,AcceptWaveform=lambda data:True,Result=lambda:json.dumps(result('atom')))
    c=VoskWakeComparison(model,lambda *a:rec,16000,shadow_only=False)
    with caplog.at_level('INFO'):
        assert c.process(bytes(2560),diagnostics=False)['candidate']
    assert "final='atom'" not in caplog.text
