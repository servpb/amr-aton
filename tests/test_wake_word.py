"""Unit tests for Wake Word detection and Push-to-Talk."""

import time
import numpy as np
import pytest
from src.audio.push_to_talk import PushToTalk
from src.audio.wake_word import WakeWordDetector


def test_wake_word_detector_initialization():
    """Verify WakeWordDetector initializes with correct defaults."""
    detector = WakeWordDetector(wake_word="aton", threshold=0.6, cooldown_seconds=1.5)
    assert detector.wake_word == "aton"
    assert detector.threshold == 0.6
    assert detector.cooldown_seconds == 1.5


def test_wake_word_cooldown():
    """Verify that wake word enforces cooldown period between triggers."""
    detector = WakeWordDetector(wake_word="aton", cooldown_seconds=0.5)

    # First trigger should succeed
    assert detector.simulate_trigger() is True

    # Immediate next trigger should be blocked by cooldown
    # Empty or zero bytes during cooldown
    silence = np.zeros(1280, dtype=np.int16).tobytes()
    assert detector.process_pcm_chunk(silence) is False


def test_push_to_talk_callback():
    """Verify PushToTalk fires callback and toggles active state correctly."""
    callback_fired = []

    def on_activate():
        callback_fired.append(True)

    ptt = PushToTalk(hotkey="ctrl+space", on_trigger_callback=on_activate)
    assert not ptt.is_active

    ptt.trigger()
    assert ptt.is_active
    assert len(callback_fired) == 1

    ptt.release()
    assert not ptt.is_active


def test_wake_word_rejects_silence_and_noise():
    """Verify that silence and random noise do not trigger activation."""
    detector = WakeWordDetector(wake_word="aton", cooldown_seconds=0.1)

    # 1. Pure silence
    silence = np.zeros(1280, dtype=np.int16).tobytes()
    assert detector.process_pcm_chunk(silence) is False

    # 2. Random low-to-medium noise
    rng = np.random.default_rng(42)
    noise = rng.integers(-2000, 2000, size=1280, dtype=np.int16).tobytes()
    assert detector.process_pcm_chunk(noise) is False


def test_wake_word_vosk_detection_and_rejection(monkeypatch):
    """Verify Vosk-based recognition correctly identifies 'aton' and rejects unrelated speech."""
    detector = WakeWordDetector(wake_word="aton", cooldown_seconds=0.1)

    # Mock Vosk recognizer results
    class MockKaldiRecognizer:
        def __init__(self):
            self.result_text = ""
            self.reset_called = False

        def AcceptWaveform(self, data):
            return True

        def Result(self):
            import json
            return json.dumps({"text": self.result_text})

        def PartialResult(self):
            return '{"partial": ""}'

        def Reset(self):
            self.reset_called = True

    mock_rec = MockKaldiRecognizer()
    detector._vosk_rec = mock_rec

    dummy_pcm = np.ones(1280, dtype=np.int16).tobytes()

    # 1. Unrelated speech: "olá bom dia como vai você" -> should NOT trigger
    mock_rec.result_text = "olá bom dia como vai você"
    assert detector.process_pcm_chunk(dummy_pcm) is False
    assert not mock_rec.reset_called

    # 2. Another unrelated sentence: "reproduzir música no youtube" -> should NOT trigger
    mock_rec.result_text = "reproduzir música no youtube"
    assert detector.process_pcm_chunk(dummy_pcm) is False

    # 3. Spoken wake word: "aton" -> MUST trigger
    mock_rec.result_text = "aton"
    assert detector.process_pcm_chunk(dummy_pcm) is True
    assert mock_rec.reset_called

    # 4. Spoken with accent: "áton por favor" -> MUST trigger (after cooldown)
    time.sleep(0.15)
    mock_rec.reset_called = False
    mock_rec.result_text = "áton por favor"
    assert detector.process_pcm_chunk(dummy_pcm) is True
    assert mock_rec.reset_called

