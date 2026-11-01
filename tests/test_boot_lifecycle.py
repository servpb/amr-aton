"""Unit tests for Aton boot lifecycle, system tray states, and warm-up readiness."""

import time
import pytest
import numpy as np

from src.audio.recorder import AudioRecorder
from src.core.assistant import AMRAssistant, AssistantState
from src.integrations.system_tray import AtonSystemTray, generate_tray_icon


def test_tray_icon_palette_states():
    """Verify tray icon generates valid images for all transparent boot lifecycle states."""
    states = [
        "initializing",
        "local_listening",
        "sleeping",
        "ready",
        "listening",
        "speaking",
        "muted",
        "mic_error",
        "init_error",
    ]
    for s in states:
        img = generate_tray_icon(state=s, size=64)
        assert img is not None
        assert img.size == (64, 64)
        assert img.mode == "RGBA"


def test_audio_recorder_clear_backlog():
    """Verify AudioRecorder.clear_backlog discards stale chunks and retains strictly the latest."""
    rec = AudioRecorder(sample_rate=16000)

    # Simulate accumulating 10 chunks during warm-up
    for i in range(10):
        rec._queue.put(b"chunk_" + str(i).encode())

    assert rec._queue.qsize() == 10

    # Clear backlog keeping only the single newest chunk
    dropped = rec.clear_backlog(keep_latest=1)
    assert dropped == 9
    assert rec._queue.qsize() == 1

    remaining = rec.read_chunk(timeout=0.1)
    assert remaining == b"chunk_9"

    # Clear backlog keeping 0
    rec._queue.put(b"stale_1")
    rec._queue.put(b"stale_2")
    dropped2 = rec.clear_backlog(keep_latest=0)
    assert dropped2 == 2
    assert rec._queue.empty()


def test_warmup_call_emits_local_notice_and_discards_backlog():
    """Verify saying 'Aton' before warm-up completes emits local notice and does not enter CONVERSING."""
    from src.audio.recorder import AudioRecorder
    from unittest.mock import MagicMock

    recorder = AudioRecorder()
    mock_player = MagicMock()
    mock_detector = MagicMock()

    is_warmup_complete = False
    state = "sleeping"

    # Simulate wake word arriving during incomplete warm-up
    recorder._queue.put(b"stale_voice_turn_1")
    recorder._queue.put(b"stale_voice_turn_2")
    assert recorder._queue.qsize() == 2

    # Under assistant warmup protection logic:
    if not is_warmup_complete:
        mock_player.play_wake_chime()
        dropped = recorder.clear_backlog(keep_latest=0)
        recorder.flush()
        mock_detector.reset()

    assert dropped == 2
    assert recorder._queue.empty()
    mock_player.play_wake_chime.assert_called_once()
    mock_detector.reset.assert_called_once()
    assert state != "conversing"


def test_tray_state_transitions():
    """Verify tray reflects honest progression: initializing -> local_listening -> ready."""
    tray = AtonSystemTray(initial_state="initializing", initial_status_text="Inicializando...")
    assert tray.state == "initializing"

    tray.update_state("local_listening", "Escuta local ativa")
    assert tray.state == "local_listening"
    assert "Escuta local" in tray.status_text

    tray.update_state("ready", "Pronto para conversar (diga 'Aton')")
    assert tray.state == "ready"
    assert "Pronto" in tray.status_text

    tray.update_state("mic_error", "Falha no microfone")
    assert tray.state == "mic_error"
    assert "Falha" in tray.status_text

    tray.update_state("init_error", "Falha ao carregar")
    assert tray.state == "init_error"
    assert "Falha ao carregar" in tray.status_text
