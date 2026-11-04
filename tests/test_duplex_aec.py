"""AEC pilot protocol tests without opening real devices or saving audio."""
import time
from types import SimpleNamespace
import numpy as np
import pytest
from src.audio.duplex_aec import DuplexAecEngine,AecRecorder,AecPlayer

class Processor:
    def __init__(self): self.calls=[]
    def process(self,near,far):
        self.calls.append((near.copy(),far.copy()))
        return near.copy()

def frame(engine,value=.1):
    out=np.zeros((160,1),dtype=np.float32)
    engine._callback(np.full((160,1),value,dtype=np.float32),out,160,None,None)
    return out

def test_reference_is_exact_rendered_frame_and_capture_is_aggregated():
    processor=Processor()
    engine=DuplexAecEngine(processor=processor)
    rec=AecRecorder(engine)
    rec._is_recording=True
    engine.enqueue(np.full(160,.25,dtype=np.float32))
    output=frame(engine)
    assert np.all(output==.25)
    assert np.array_equal(processor.calls[0][1],(output[:,0]*32767).astype(np.int16))
    assert rec.read_chunk(0) is None
    for _ in range(7):frame(engine)
    pcm=rec.read_chunk(0)
    assert len(pcm)==2560
    assert rec.received_chunks==1
    assert engine.frames_processed==8

def test_stop_clears_long_output_without_waiting_for_playback():
    engine=DuplexAecEngine(processor=Processor())
    player=AecPlayer(engine)
    player.play_sound(np.full(24000*30,.1,dtype=np.float32))
    assert player.is_playing
    player.stop()
    assert not player.is_playing
    assert not np.any(frame(engine))

def test_stop_allows_future_greeting_without_replaying_old_sound():
    engine=DuplexAecEngine(processor=Processor())
    engine.enqueue(np.full(1000,.9,dtype=np.float32))
    engine.clear_output()
    engine.enqueue(np.full(80,.2,dtype=np.float32))
    out=frame(engine)
    assert np.all(out[:80,0]==.2)
    assert not np.any(out[80:])

def test_processing_failure_does_not_pass_raw_microphone_to_recognizer():
    class Broken:
        def process(self,*args):raise RuntimeError('failed')
    engine=DuplexAecEngine(processor=Broken())
    rec=AecRecorder(engine);rec._is_recording=True
    engine.enqueue(np.ones(160,dtype=np.float32))
    assert not np.any(frame(engine))
    assert engine.error=='RuntimeError'
    assert rec.read_chunk(0) is None
    assert not rec.is_healthy()

def test_render_fifo_preserves_sample_order_across_boundaries():
    engine=DuplexAecEngine(processor=Processor())
    engine.enqueue(np.arange(90,dtype=np.float32))
    engine.enqueue(np.arange(90,240,dtype=np.float32))
    assert np.array_equal(engine._render(160),np.arange(160,dtype=np.float32))
    tail=engine._render(160)
    assert np.array_equal(tail[:80],np.arange(160,240,dtype=np.float32))
    assert not np.any(tail[80:])

def test_queue_limit_prevents_unbounded_output():
    engine=DuplexAecEngine(processor=Processor())
    with pytest.raises(RuntimeError):engine.enqueue(np.zeros(16000*121,dtype=np.float32))

def test_real_webrtc_processor_handles_aligned_silence():
    library=pytest.importorskip('pywebrtc_audio')
    processor=library.AudioProcessor(sample_rate=16000,echo_cancellation=True,noise_suppression=True,auto_gain_control=False)
    engine=DuplexAecEngine(processor=processor)
    for _ in range(20):
        frame(engine,value=0)
    assert engine.error is None
    assert engine.frames_processed==20
    assert engine.clean_rms==0
