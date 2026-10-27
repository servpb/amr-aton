"""Unit tests for the AMR Audio Engine."""

import numpy as np
import pytest
from src.audio.device_manager import (
    get_default_input_device,
    get_default_output_device,
    list_audio_devices,
)
from src.audio.player import AudioPlayer
from src.audio.recorder import AudioRecorder


def test_chime_generation():
    """Verify chime generation returns valid, smooth numpy float32 arrays."""
    player = AudioPlayer(sample_rate=16000)
    duration = 0.1
    chime = player.generate_chime(frequency_hz=440.0, duration_seconds=duration)

    assert isinstance(chime, np.ndarray)
    assert chime.dtype == np.float32
    assert len(chime) == int(16000 * duration)
    # Check that amplitude is bounded
    assert np.max(np.abs(chime)) <= 1.0
    # Check smooth envelope: ends should be very close to zero
    assert abs(chime[0]) < 0.05
    assert abs(chime[-1]) < 0.05


def test_player_lifecycle():
    """Verify player initialization and stop."""
    player = AudioPlayer()
    assert player.sample_rate == 24000
    player.play_greeting()
    player.stop()
    assert not player._is_playing
    assert not player.is_playing


def test_recorder_initialization():
    """Verify recorder initializes with appropriate audio parameters."""
    recorder = AudioRecorder(sample_rate=16000, channels=1, chunk_size=1280)
    assert recorder.sample_rate == 16000
    assert recorder.channels == 1
    assert recorder.chunk_size == 1280
    assert not recorder.is_recording
    assert recorder.read_chunk(timeout=0.01) is None


def test_recorder_flush():
    """Verify recorder flush clears buffered chunks."""
    recorder = AudioRecorder()
    recorder._queue.put(b"chunk1")
    recorder._queue.put(b"chunk2")
    assert not recorder._queue.empty()
    recorder.flush()
    assert recorder._queue.empty()


def test_device_manager_functions():
    """Verify device manager functions return safe types without raising uncaught exceptions."""
    devices = list_audio_devices()
    assert isinstance(devices, list)

    default_in = get_default_input_device()
    assert default_in is None or isinstance(default_in, dict)

    default_out = get_default_output_device()
    assert default_out is None or isinstance(default_out, dict)
