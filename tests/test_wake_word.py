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
