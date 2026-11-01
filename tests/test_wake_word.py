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

    # 2b. Substring and everyday vocabulary false-positive regression checks:
    everyday_false_positives = [
        "já vai para a tomada",
        "a tomar café",
        "a tomar escuta",
        "a bom",
        "o pão",
        "comprei pão na padaria",
        "passou batom",
        "ela vende avon",
        "adão e eva",
        "o tom da conversa foi sério",
        "física do átomo",
        "sanduíche de atum",
        "a reunião de negócios teve um tom agradável e produtivo",
        "no tom certo",
        "tom de voz",
        "tomara que venha",
        "não eram as habilidades atom",
    ]
    for sentence in everyday_false_positives:
        mock_rec.result_text = sentence
        assert detector.process_pcm_chunk(dummy_pcm) is False, f"Falha: disparou indevidamente para '{sentence}'"
        assert not mock_rec.reset_called

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

    # 4b. Deliberate direct greetings: "oi aton", "olá aton" -> MUST trigger
    time.sleep(0.15)
    mock_rec.reset_called = False
    mock_rec.result_text = "oi aton"
    assert detector.process_pcm_chunk(dummy_pcm) is True
    assert mock_rec.reset_called

    # 4c. Secondary acoustic variants (accepted in final result ONLY by exact match):
    # 'tom', 'oi tom', 'atom', 'oi atom', 'átom'
    acoustic_exact_success = ["tom", "oi tom", "atom", "oi atom", "átom", "olá átom"]
    for acoustic_variant in acoustic_exact_success:
        time.sleep(0.15)
        mock_rec.reset_called = False
        mock_rec.result_text = acoustic_variant
        assert detector.process_pcm_chunk(dummy_pcm) is True, f"Falha: não disparou para '{acoustic_variant}'"
        assert mock_rec.reset_called

    # 4d. Partial result handling: strict deterministic criteria
    # Mock PartialResult
    class MockPartialRecognizer(MockKaldiRecognizer):
        def __init__(self, partial_text):
            super().__init__()
            self.partial_text = partial_text

        def AcceptWaveform(self, data):
            return False  # Force partial evaluation

        def PartialResult(self):
            import json
            return json.dumps({"partial": self.partial_text})

    # Partial with conversation fragment or secondary variants: MUST NOT trigger in partial!
    for partial_str in ["o pão", "batom", "a bom", "o tom", "comprei batom", "tom", "oi tom", "atom", "átom"]:
        time.sleep(0.15)
        detector._vosk_rec = MockPartialRecognizer(partial_str)
        assert detector.process_pcm_chunk(dummy_pcm) is False, f"Falha: disparou indevidamente no parcial para '{partial_str}'"

    # Partial with exact strict canonical keyword: "aton", "áton", "oi aton" -> MUST trigger
    time.sleep(0.15)
    detector._vosk_rec = MockPartialRecognizer("aton")
    assert detector.process_pcm_chunk(dummy_pcm) is True

    # Restore mock for remaining tests
    detector._vosk_rec = mock_rec

    # 5. Stop command ("pare" / "parar") detection while listening
    mock_rec.reset_called = False
    mock_rec.result_text = "qual a previsão do tempo"
    assert detector.detect_stop_command(dummy_pcm) is False
    assert not mock_rec.reset_called

    mock_rec.result_text = "pare"
    assert detector.detect_stop_command(dummy_pcm) is True
    assert mock_rec.reset_called


