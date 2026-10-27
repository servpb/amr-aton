"""Configuration management for AMR Assistant using Pydantic Settings."""

from typing import Any, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Google AI Studio Configuration
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    gemini_live_model: str = Field(default="gemini-2.0-flash-exp", alias="GEMINI_LIVE_MODEL")
    gemini_voice_name: str = Field(default="Aoede", alias="GEMINI_VOICE_NAME")

    # Wake Word & Audio Engine Settings
    amr_wake_word: str = Field(default="aton", alias="AMR_WAKE_WORD")
    audio_input_device_index: Optional[int] = Field(default=None, alias="AUDIO_INPUT_DEVICE_INDEX")
    audio_output_device_index: Optional[int] = Field(default=None, alias="AUDIO_OUTPUT_DEVICE_INDEX")
    audio_sample_rate: int = Field(default=16000, alias="AUDIO_SAMPLE_RATE")
    conversation_timeout_seconds: int = Field(default=12, alias="CONVERSATION_TIMEOUT_SECONDS")

    # Smart TV & Local IoT Configuration (Phase 2)
    smart_tv_ip: Optional[str] = Field(default=None, alias="SMART_TV_IP")
    smart_tv_brand: str = Field(default="auto", alias="SMART_TV_BRAND")
    smart_tv_mac: Optional[str] = Field(default=None, alias="SMART_TV_MAC")

    # Android Phone Finder & Smart Lights (Phase 2)
    android_phone_ip: Optional[str] = Field(default=None, alias="ANDROID_PHONE_IP")
    android_phone_port: int = Field(default=8080, alias="ANDROID_PHONE_PORT")
    smart_lights_bridge_ip: Optional[str] = Field(default=None, alias="SMART_LIGHTS_BRIDGE_IP")

    # Mobile Gateway & Tailscale Remote Access (Phase 3)
    gateway_enabled: bool = Field(default=True, alias="GATEWAY_ENABLED")
    gateway_host: str = Field(default="0.0.0.0", alias="GATEWAY_HOST")
    gateway_port: int = Field(default=8443, alias="GATEWAY_PORT")
    gateway_api_token: str = Field(default="", alias="GATEWAY_API_TOKEN")

    # Google Workspace & Calendar (Phase 4)
    google_calendar_credentials_path: str = Field(default="credentials.json", alias="GOOGLE_CALENDAR_CREDENTIALS_PATH")
    google_calendar_token_path: str = Field(default="token.json", alias="GOOGLE_CALENDAR_TOKEN_PATH")
    google_calendar_id: str = Field(default="primary", alias="GOOGLE_CALENDAR_ID")

    # Gmail Integration (Phase 4)
    gmail_credentials_path: str = Field(default="credentials.json", alias="GMAIL_CREDENTIALS_PATH")
    gmail_token_path: str = Field(default="token.json", alias="GMAIL_TOKEN_PATH")

    # Google Tasks Integration (Phase 4)
    google_tasks_credentials_path: str = Field(default="credentials.json", alias="GOOGLE_TASKS_CREDENTIALS_PATH")
    google_tasks_token_path: str = Field(default="token.json", alias="GOOGLE_TASKS_TOKEN_PATH")
    google_tasks_default_list: str = Field(default="@default", alias="GOOGLE_TASKS_DEFAULT_LIST")

    # Long-term Semantic Memory (Phase 5)
    memory_db_path: str = Field(default="amr_memory.db", alias="MEMORY_DB_PATH")

    # System Tray & Background Resident (Phase 6)
    system_tray_enabled: bool = Field(default=True, alias="SYSTEM_TRAY_ENABLED")

    # System & Logging
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @field_validator(
        "audio_input_device_index",
        "audio_output_device_index",
        "smart_tv_ip",
        "smart_tv_mac",
        "android_phone_ip",
        "smart_lights_bridge_ip",
        mode="before",
    )
    @classmethod
    def empty_str_to_none(cls, v: Optional[object]) -> Optional[Any]:
        if v == "" or v is None:
            return None
        return v


settings = Settings()
