"""Unit tests for the Gemini Live API client and prompts."""

import pytest
from src.core.live_client import GeminiLiveClient
from src.core.prompts import AMR_SYSTEM_INSTRUCTION


def test_amr_system_instruction_content():
    """Verify system instruction contains essential guidelines."""
    assert "Aton" in AMR_SYSTEM_INSTRUCTION
    assert "Português do Brasil" in AMR_SYSTEM_INSTRUCTION
    assert "Duas Camadas" in AMR_SYSTEM_INSTRUCTION
    assert "senhor" in AMR_SYSTEM_INSTRUCTION


def test_live_client_initialization():
    """Verify GeminiLiveClient initializes with proper defaults and custom parameters."""
    client = GeminiLiveClient(
        api_key="mock_key",
        model="gemini-2.0-flash-exp",
        voice_name="Aoede",
    )
    assert client.api_key == "mock_key"
    assert client.model == "gemini-2.0-flash-exp"
    assert client.voice_name == "Aoede"
    assert not client.is_connected


@pytest.mark.asyncio
async def test_live_client_connect_fallback():
    """Verify connect method safely handles unconfigured/simulated mode."""
    client = GeminiLiveClient(api_key="")
    connected = await client.connect()
    assert connected is True
    assert client.is_connected is True
    # Test sending text prompt does not crash in fallback
    await client.send_text_prompt("Teste de saudacao")
    # Test sending audio chunk does not crash in fallback
    await client.send_audio_chunk(b"\x00" * 2560)
    # Test receive stream terminates cleanly when session is None
    chunks = [c async for c in client.receive_stream()]
    assert len(chunks) == 0
    await client.disconnect()
    assert client.is_connected is False
