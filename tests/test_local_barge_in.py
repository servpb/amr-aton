from src.audio.barge_in import LocalBargeInGate

def test_only_sustained_speech_during_playback_triggers():
    gate=LocalBargeInGate(warmup_seconds=0)
    assert not gate.update(playing=False,probability=1,rms=1000,now=0)
    for i in range(7):
        assert not gate.update(playing=True,probability=.9,rms=1000,now=i*.01)
    assert gate.update(playing=True,probability=.9,rms=1000,now=.07)
    assert not gate.update(playing=True,probability=.9,rms=1000,now=.08)

def test_noise_and_short_transients_do_not_trigger():
    gate=LocalBargeInGate(warmup_seconds=0)
    for i in range(100):
        assert not gate.update(playing=True,probability=.1,rms=2000,now=i*.01)
    for i in range(5):
        assert not gate.update(playing=True,probability=.9,rms=1000,now=2+i*.01)
    assert not gate.update(playing=True,probability=.1,rms=1000,now=2.1)
    for i in range(7):
        assert not gate.update(playing=True,probability=.9,rms=1000,now=3+i*.01)

def test_startup_guard_and_rearm_for_second_response():
    gate=LocalBargeInGate()
    for i in range(50):
        assert not gate.update(playing=True,probability=1,rms=1000,now=i*.01)
    for i in range(7):
        assert not gate.update(playing=True,probability=1,rms=1000,now=.5+i*.01)
    assert gate.update(playing=True,probability=1,rms=1000,now=.57)
    gate.update(playing=False,probability=0,rms=0,now=1)
    assert not gate.update(playing=True,probability=1,rms=1000,now=2)
    for i in range(7):
        assert not gate.update(playing=True,probability=1,rms=1000,now=2.5+i*.01)
    assert gate.update(playing=True,probability=1,rms=1000,now=2.57)

def test_silent_signal_is_not_speech_even_with_high_probability():
    gate=LocalBargeInGate(warmup_seconds=0)
    for i in range(50):
        assert not gate.update(playing=True,probability=1,rms=10,now=i*.01)
