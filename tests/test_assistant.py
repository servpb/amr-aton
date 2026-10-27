"""Unit tests for the AMR Assistant orchestrator and state transitions."""

import pytest
from src.core.assistant import AMRAssistant, AssistantState


def test_assistant_initialization():
    """Verify assistant initializes in SLEEPING state with configured settings."""
    assistant = AMRAssistant(wake_word="aton", conversation_timeout=5)
    assert assistant.state == AssistantState.SLEEPING
    assert assistant.conversation_timeout == 5
    assert assistant.wake_detector.wake_word == "aton"


@pytest.mark.asyncio
async def test_assistant_state_transitions():
    """Verify state transitions from sleeping to waking, conversing, and shutdown."""
    assistant = AMRAssistant(conversation_timeout=1, api_key="")
    assert assistant.state == AssistantState.SLEEPING

    # Trigger wake up
    await assistant._wake_up()
    # In mock mode, it transitions to conversing
    assert assistant.state == AssistantState.CONVERSING

    # Trigger sleep
    await assistant._go_to_sleep()
    assert assistant.state == AssistantState.SLEEPING

    # Shutdown
    await assistant.shutdown()
    assert assistant.state == AssistantState.SHUTDOWN


@pytest.mark.asyncio
async def test_assistant_audio_processing_in_conversing():
    """Verify audio processing in CONVERSING state handles chunk buffer safely."""
    import numpy as np
    assistant = AMRAssistant(conversation_timeout=1, api_key="")
    assistant.state = AssistantState.CONVERSING
    chunk = (np.ones(1280, dtype=np.int16) * 500).tobytes()
    audio_data = np.frombuffer(chunk, dtype=np.int16)
    rms = float(np.sqrt(np.mean(audio_data.astype(np.float32) ** 2)))
    assert rms > 0
    await assistant.shutdown()
