"""Tests for AMR configuration module."""

from src.config import Settings


def test_settings_default_values():
    """Verify that default settings load as expected."""
    settings = Settings(GEMINI_API_KEY="test_key")
    assert settings.gemini_api_key == "test_key"
    assert settings.amr_wake_word == "aton"
    assert settings.audio_sample_rate == 16000
    assert settings.conversation_timeout_seconds == 12
