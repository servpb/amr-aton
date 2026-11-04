import json
import wave
import numpy as np
import pytest
from src.audio.local_diagnostic import LocalAudioDiagnostic

def test_recording_disabled_until_explicit_start():
    d=LocalAudioDiagnostic()
    d.push(np.ones(160,dtype=np.int16),np.zeros(160,dtype=np.int16),np.zeros(160,dtype=np.int16))
    assert d._samples==0
    assert not d.ready

def test_three_tracks_are_preserved_and_capture_is_bounded(tmp_path):
    clock=[100.0]
    d=LocalAudioDiagnostic(clock=lambda:clock[0])
    d.start(1)
    a=np.full(20000,1,dtype=np.int16);b=a*2;c=a*3
    d.push(a,b,c)
    assert d.ready
    d.push(a,b,c)
    assert d._samples==16000
    path=d.save(tmp_path)
    with wave.open(str(path),'rb') as wav:
        assert wav.getnchannels()==3
        assert wav.getnframes()==16000
        samples=np.frombuffer(wav.readframes(16000),dtype='<i2').reshape(-1,3)
    assert np.all(samples[:,0]==1)
    assert np.all(samples[:,1]==2)
    assert np.all(samples[:,2]==3)
    assert json.loads(path.with_suffix('.json').read_text())['local_only']
    assert not d.ready

def test_wall_clock_deadline_finishes_when_no_audio_arrives():
    clock=[10.0]
    d=LocalAudioDiagnostic(clock=lambda:clock[0]);d.start(30)
    clock[0]=41
    assert d.ready

def test_refuses_overlapping_recording():
    d=LocalAudioDiagnostic();d.start(1)
    with pytest.raises(RuntimeError):d.start(1)

@pytest.mark.parametrize('seconds',[0,31,300])
def test_duration_cannot_exceed_user_authorization(seconds):
    with pytest.raises(ValueError):LocalAudioDiagnostic().start(seconds)
