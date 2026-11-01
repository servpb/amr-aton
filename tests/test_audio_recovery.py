"""Unit tests for Aton Audio Recovery, Stream Concurrency, Watchdog Coordination, and Device Configuration."""

import queue
import threading
import time
from unittest.mock import MagicMock, patch
import numpy as np
import pytest

from src.audio.player import AudioPlayer, MAX_CONSECUTIVE_WRITE_FAILURES, FAILURE_COOLDOWN_SECONDS
from src.audio.recorder import AudioRecorder
from src.core.assistant import AMRAssistant, AssistantState
from src.config import settings


@pytest.fixture(autouse=True)
def mock_wake_detector():
    """Mock heavy Vosk speech recognition model loading during unit tests."""
    with patch("src.core.assistant.WakeWordDetector") as mock_det:
        mock_instance = MagicMock()
        mock_instance.wake_word = "aton"
        mock_det.return_value = mock_instance
        yield mock_det


@pytest.fixture
def clean_player():
    """Create AudioPlayer instance and ensure it stops cleanly after test."""
    player = AudioPlayer(sample_rate=24000)
    yield player
    player._running = False
    player.stop()


def test_invalid_stream_pointer_detection_and_discard(clean_player):
    """Test 1: Verify Invalid stream pointer [PaErrorCode -9988] is caught, stream is discarded, and worker recovers."""
    player = clean_player
    mock_stream = MagicMock()
    mock_stream.active = True
    # Simulate PortAudio invalid stream pointer error on write
    mock_stream.write.side_effect = Exception("Invalid stream pointer [PaErrorCode -9988]")

    with patch("sounddevice.OutputStream", return_value=mock_stream):
        test_audio = np.ones(100, dtype=np.float32) * 0.1
        player.play_sound(test_audio)

        time.sleep(0.25)

        assert player._stream is None
        assert player.has_error is True
        assert player._consecutive_failures == 1
        assert "PaErrorCode -9988" in (player._last_error or "")
        assert player._worker_thread.is_alive()


def test_close_during_playback_concurrency(clean_player):
    """Test 2: Verify stopping the player while playback worker is writing does not cause race conditions."""
    player = clean_player
    mock_stream = MagicMock()
    mock_stream.active = True

    def slow_write(data):
        time.sleep(0.05)
    mock_stream.write.side_effect = slow_write

    with patch("sounddevice.OutputStream", return_value=mock_stream):
        for _ in range(5):
            player.play_sound(np.zeros(200, dtype=np.float32))

        time.sleep(0.02)
        player.stop()

        assert player._stream is None
        assert player._queue.empty()
        assert not player.is_playing


def test_bounded_recovery_and_cooldown(clean_player):
    """Test 3: Verify bounded recovery: after 3 consecutive failures, enters cooldown and clears queue."""
    player = clean_player
    mock_failing_stream = MagicMock()
    mock_failing_stream.active = True
    mock_failing_stream.write.side_effect = Exception("Device disconnected [PaErrorCode -9985]")

    with patch("sounddevice.OutputStream", return_value=mock_failing_stream):
        for i in range(MAX_CONSECUTIVE_WRITE_FAILURES + 2):
            player.play_sound(np.ones(50, dtype=np.float32))

        time.sleep(0.35)

        assert player.has_error is True
        assert player.in_cooldown is True
        assert player._consecutive_failures >= MAX_CONSECUTIVE_WRITE_FAILURES
        assert player._uncertain_chunk_dropped is True
        assert player._queue.empty()

        # Any chunks sent during active cooldown must be dropped
        player.play_sound(np.ones(50, dtype=np.float32))
        assert player._queue.empty()


def test_recovery_after_cooldown_expires(clean_player):
    """Test 3b: Verify that once cooldown expires, player establishes fresh stream and resets errors."""
    player = clean_player
    player._has_error = True
    player._in_cooldown = True
    player._consecutive_failures = 3
    # Force last failure time in the past
    player._last_failure_time = time.time() - (FAILURE_COOLDOWN_SECONDS + 1.0)

    mock_healthy_stream = MagicMock()
    mock_healthy_stream.active = True

    with patch("sounddevice.OutputStream", return_value=mock_healthy_stream):
        player.play_sound(np.ones(50, dtype=np.float32))
        time.sleep(0.25)

        assert player.has_error is False
        assert player.in_cooldown is False
        assert player._consecutive_failures == 0
        assert player._total_recoveries >= 1
        mock_healthy_stream.write.assert_called()


def test_discard_stale_audio_on_failure(clean_player):
    """Test 4: Verify stale audio is discarded when stream fails so old speech is not replayed later."""
    player = clean_player
    for _ in range(10):
        player.play_sound(np.ones(100, dtype=np.float32))

    with player._stream_lock:
        player._handle_failure_unlocked(Exception("Buffer underrun [PaErrorCode -9988]"))

    with player._stream_lock:
        player._handle_failure_unlocked(Exception("Buffer underrun [PaErrorCode -9988]"))
        player._handle_failure_unlocked(Exception("Buffer underrun [PaErrorCode -9988]"))

    assert player.clear_queue() == 0
    assert player._queue.empty()
    assert player._uncertain_chunk_dropped is True


def test_device_index_configuration_propagation():
    """Test 5: Verify assistant propagates AUDIO_INPUT_DEVICE_INDEX and AUDIO_OUTPUT_DEVICE_INDEX to components."""
    with patch("sounddevice.OutputStream"), patch("sounddevice.InputStream"):
        assistant = AMRAssistant(input_device_index=2, output_device_index=5, api_key="")
        try:
            assert assistant.input_device_index == 2
            assert assistant.output_device_index == 5
            assert assistant.recorder.device_index == 2
            assert assistant.player.device_index == 5
        finally:
            assistant.player.stop()
            assistant.recorder.stop()

        with patch.object(settings, "audio_input_device_index", 1), \
             patch.object(settings, "audio_output_device_index", 4):
            assistant_default = AMRAssistant(api_key="")
            try:
                assert assistant_default.recorder.device_index == 1
                assert assistant_default.player.device_index == 4
            finally:
                assistant_default.player.stop()
                assistant_default.recorder.stop()


def test_mic_watchdog_soft_restart_preserves_player():
    """Test 6: Verify soft watchdog restart of microphone does not terminate PortAudio or invalidate player."""
    recorder = AudioRecorder()
    mock_in_stream = MagicMock()
    mock_in_stream.active = True
    recorder._stream = mock_in_stream
    recorder._is_recording = True

    try:
        with patch("sounddevice._terminate") as mock_terminate, \
             patch("sounddevice.InputStream", return_value=mock_in_stream):
            
            recorder.restart(reinit_portaudio=False)

            mock_terminate.assert_not_called()
            assert recorder.is_recording is True
    finally:
        recorder.stop()


def test_coordinated_audio_subsystem_recovery():
    """Test 7: Verify assistant.recover_audio_subsystem safely prepares player before terminating PortAudio."""
    with patch("sounddevice.OutputStream"), patch("sounddevice.InputStream"):
        assistant = AMRAssistant(api_key="")
        try:
            with patch.object(assistant.player, "prepare_for_subsystem_reinit") as mock_prep_player, \
                 patch.object(assistant.player, "on_subsystem_reinitialized") as mock_post_player, \
                 patch.object(assistant.recorder, "stop") as mock_stop_rec, \
                 patch.object(assistant.recorder, "start") as mock_start_rec, \
                 patch("sounddevice._terminate") as mock_sd_term, \
                 patch("sounddevice._initialize") as mock_sd_init:

                success = assistant.recover_audio_subsystem(reason="test_recovery")
                assert success is True

                mock_prep_player.assert_called_once()
                mock_stop_rec.assert_called_once()
                mock_sd_term.assert_called_once()
                mock_sd_init.assert_called_once()
                mock_start_rec.assert_called_once()
                mock_post_player.assert_called_once()
        finally:
            assistant.player.stop()
            assistant.recorder.stop()


@pytest.mark.asyncio
async def test_tray_state_not_speaking_when_audio_output_failed():
    """Test 8: Verify tray icon displays 'audio_error' and not 'speaking' if player has failed."""
    mock_tray = MagicMock()
    with patch("sounddevice.OutputStream"), patch("sounddevice.InputStream"):
        assistant = AMRAssistant(tray=mock_tray, api_key="")
        
        try:
            assistant.player._has_error = True
            assistant.player._in_cooldown = True

            mock_client = MagicMock()
            async def mock_stream():
                yield b"\x00" * 320
            mock_client.receive_stream = mock_stream
            assistant._live_client = mock_client

            await assistant._receive_gemini_audio()

            for call in mock_tray.update_state.call_args_list:
                state_arg = call[0][0]
                assert state_arg != "speaking", "Tray should not indicate speaking when player is in error state!"
            
            mock_tray.update_state.assert_any_call("audio_error", "Falha na saída de áudio (recuperando...)")
        finally:
            assistant.player.stop()
            assistant.recorder.stop()
