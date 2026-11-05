"""Configuration management for AMR Assistant using Pydantic Settings."""

from pathlib import Path
from typing import Any, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root directory (src/config.py is 1 level below root in src/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent


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
    gemini_vision_model: str = Field(default="gemini-3-flash-preview", alias="GEMINI_VISION_MODEL")
    gemini_voice_name: str = Field(default="Aoede", alias="GEMINI_VOICE_NAME")

    # Multi-LLM foundation: not connected to the live runtime yet.
    multi_llm_enabled: bool = Field(default=False, alias="MULTI_LLM_ENABLED")

    # Groq synthetic text pilot; never enabled automatically.
    groq_api_key: str = Field(default="", repr=False, alias="GROQ_API_KEY")
    groq_free_plan_verified: bool = Field(default=False, alias="GROQ_FREE_PLAN_VERIFIED")
    groq_enabled: bool = Field(default=True, alias="GROQ_ENABLED")
    groq_model: str = Field(default="openai/gpt-oss-20b", alias="GROQ_MODEL")
    groq_timeout_seconds: float = Field(default=15.0, alias="GROQ_TIMEOUT_SECONDS")

    # OpenRouter & NVIDIA Nemotron Configuration (Planning & Deep Reasoning)
    openrouter_api_key: str = Field(default="", repr=False, alias="OPENROUTER_API_KEY")
    openrouter_enabled: bool = Field(default=True, alias="OPENROUTER_ENABLED")
    openrouter_model: str = Field(default="nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free", alias="OPENROUTER_MODEL")
    openrouter_timeout_seconds: float = Field(default=25.0, alias="OPENROUTER_TIMEOUT_SECONDS")

    # NVIDIA NIM & Nemotron Official Direct API (https://build.nvidia.com)
    nvidia_api_key: str = Field(default="", repr=False, alias="NVIDIA_API_KEY")
    nvidia_enabled: bool = Field(default=True, alias="NVIDIA_ENABLED")
    nvidia_model: str = Field(default="nvidia/llama-3.1-nemotron-70b-instruct", alias="NVIDIA_MODEL")
    nvidia_endpoint: str = Field(default="https://integrate.api.nvidia.com/v1/chat/completions", alias="NVIDIA_ENDPOINT")

    # Wake Word & Audio Engine Settings
    amr_wake_word: str = Field(default="aton", alias="AMR_WAKE_WORD")
    audio_input_device_index: Optional[int] = Field(default=None, alias="AUDIO_INPUT_DEVICE_INDEX")
    audio_output_device_index: Optional[int] = Field(default=None, alias="AUDIO_OUTPUT_DEVICE_INDEX")
    audio_sample_rate: int = Field(default=16000, alias="AUDIO_SAMPLE_RATE")
    continuous_conversation_enabled: bool = Field(default=False, alias="CONTINUOUS_CONVERSATION_ENABLED")
    conversation_timeout_seconds: int = Field(default=12, alias="CONVERSATION_TIMEOUT_SECONDS")
    conversation_max_seconds: int = Field(default=120, ge=15, le=1800, alias="CONVERSATION_MAX_SECONDS")
    voice_connect_timeout_seconds: float = Field(default=12, ge=1, le=60, alias="VOICE_CONNECT_TIMEOUT_SECONDS")
    wake_diagnostics: bool = Field(default=False, alias="WAKE_DIAGNOSTICS")
    wake_directed_enabled: bool = Field(default=False, alias="WAKE_DIRECTED_ENABLED")
    audio_aec_enabled: bool = Field(default=False, alias="AUDIO_AEC_ENABLED")
    audio_aec_delay_ms: Optional[int] = Field(default=None, ge=0, le=500, alias="AUDIO_AEC_DELAY_MS")

    # Smart TV & Local IoT Configuration (Phase 2)
    smart_tv_ip: Optional[str] = Field(default=None, alias="SMART_TV_IP")
    smart_tv_brand: str = Field(default="auto", alias="SMART_TV_BRAND")
    smart_tv_mac: Optional[str] = Field(default=None, alias="SMART_TV_MAC")

    # Fire TV control over the local network
    fire_tv_ip: str = Field(default="", alias="FIRE_TV_IP")
    fire_tv_adb_path: str = Field(default="", alias="FIRE_TV_ADB_PATH")
    fire_tv_app_wait_seconds: float = Field(default=4.0, alias="FIRE_TV_APP_WAIT_SECONDS")
    fire_tv_expected_mac: str = Field(default="24:CE:33:E2:0F:9E", alias="FIRE_TV_EXPECTED_MAC")
    fire_tv_expected_serial: str = Field(default="G071CQ2042741DJK", alias="FIRE_TV_EXPECTED_SERIAL")
    fire_tv_expected_model: str = Field(default="AFTSS", alias="FIRE_TV_EXPECTED_MODEL")
    fire_tv_discovery_enabled: bool = Field(default=True, alias="FIRE_TV_DISCOVERY_ENABLED")
    fire_tv_discovery_subnet: str = Field(default="", alias="FIRE_TV_DISCOVERY_SUBNET")
    fire_tv_discovery_timeout_seconds: float = Field(default=15.0, alias="FIRE_TV_DISCOVERY_TIMEOUT_SECONDS")
    fire_tv_discovery_concurrency: int = Field(default=16, alias="FIRE_TV_DISCOVERY_CONCURRENCY")
    fire_tv_discovery_min_interval_seconds: float = Field(default=30.0, alias="FIRE_TV_DISCOVERY_MIN_INTERVAL_SECONDS")

    # Android Phone Finder & Smart Lights (Phase 2)
    android_phone_ip: Optional[str] = Field(default=None, alias="ANDROID_PHONE_IP")
    android_phone_port: int = Field(default=8080, alias="ANDROID_PHONE_PORT")
    smart_lights_bridge_ip: Optional[str] = Field(default=None, alias="SMART_LIGHTS_BRIDGE_IP")

    # Mobile Gateway & Tailscale Remote Access (Phase 3)
    gateway_enabled: bool = Field(default=True, alias="GATEWAY_ENABLED")
    gateway_host: str = Field(default="0.0.0.0", alias="GATEWAY_HOST")
    gateway_port: int = Field(default=8443, alias="GATEWAY_PORT")
    gateway_api_token: str = Field(default="", alias="GATEWAY_API_TOKEN")

    # Network Discovery & Authorized Devices (Phase 11)
    network_discovery_enabled: bool = Field(default=True, alias="NETWORK_DISCOVERY_ENABLED")
    pairing_pin_expiry_seconds: int = Field(default=300, alias="PAIRING_PIN_EXPIRY_SECONDS")
    devices_db_path: str = Field(default="amr_memory.db", alias="DEVICES_DB_PATH")


    # Google Workspace & Calendar (Phase 4)
    google_calendar_credentials_path: str = Field(default="credentials.json", alias="GOOGLE_CALENDAR_CREDENTIALS_PATH")
    google_calendar_token_path: str = Field(default="token.json", alias="GOOGLE_CALENDAR_TOKEN_PATH")
    google_calendar_tokens_dir: str = Field(default="tokens", alias="GOOGLE_CALENDAR_TOKENS_DIR")
    google_calendar_default_account: str = Field(default="", alias="GOOGLE_CALENDAR_DEFAULT_ACCOUNT")
    google_calendar_id: str = Field(default="primary", alias="GOOGLE_CALENDAR_ID")
    google_calendar_timezone: str = Field(default="America/Fortaleza", alias="GOOGLE_CALENDAR_TIMEZONE")

    # Gmail Integration (Phase 4)
    gmail_credentials_path: str = Field(default="credentials.json", alias="GMAIL_CREDENTIALS_PATH")
    gmail_token_path: str = Field(default="token.json", alias="GMAIL_TOKEN_PATH")
    gmail_tokens_dir: str = Field(default="tokens", alias="GMAIL_TOKENS_DIR")

    # YouTube Integration (Multi-Account & Multi-Channel OAuth 2.0 Desktop)
    youtube_credentials_path: str = Field(default="credentials.json", alias="YOUTUBE_CREDENTIALS_PATH")
    youtube_tokens_dir: str = Field(default="tokens", alias="YOUTUBE_TOKENS_DIR")

    # Google Tasks Integration (Phase 4)
    google_tasks_credentials_path: str = Field(default="credentials.json", alias="GOOGLE_TASKS_CREDENTIALS_PATH")
    google_tasks_token_path: str = Field(default="token.json", alias="GOOGLE_TASKS_TOKEN_PATH")
    google_tasks_default_list: str = Field(default="@default", alias="GOOGLE_TASKS_DEFAULT_LIST")

    # Long-term Semantic Memory (Phase 5)
    memory_db_path: str = Field(default="amr_memory.db", alias="MEMORY_DB_PATH")

    # Second Brain - Supabase Cloud & pgvector
    supabase_url: str = Field(default="", alias="SUPABASE_URL")
    supabase_key: str = Field(default="", alias="SUPABASE_KEY")
    supabase_service_role_key: str = Field(default="", alias="SUPABASE_SERVICE_ROLE_KEY")

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

    def get_gmail_credentials_file(self) -> Path:
        """Return resolved Path for Gmail OAuth2 client credentials.json."""
        p = Path(self.gmail_credentials_path)
        return p if p.is_absolute() else (PROJECT_ROOT / p).resolve()

    def get_gmail_token_file(self) -> Path:
        """Return resolved Path for legacy/single Gmail OAuth2 user token.json."""
        p = Path(self.gmail_token_path)
        return p if p.is_absolute() else (PROJECT_ROOT / p).resolve()

    def get_gmail_tokens_dir(self) -> Path:
        """Return resolved directory Path for multi-account Gmail tokens and index."""
        p = Path(self.gmail_tokens_dir)
        return p if p.is_absolute() else (PROJECT_ROOT / p).resolve()

    def get_youtube_credentials_file(self) -> Path:
        """Return resolved Path for YouTube OAuth2 client credentials.json."""
        p = Path(self.youtube_credentials_path)
        return p if p.is_absolute() else (PROJECT_ROOT / p).resolve()

    def get_youtube_tokens_dir(self) -> Path:
        """Return resolved directory Path for multi-account/multi-channel YouTube tokens and index."""
        p = Path(self.youtube_tokens_dir)
        return p if p.is_absolute() else (PROJECT_ROOT / p).resolve()


settings = Settings()


def get_settings() -> Settings:
    """Return the active singleton settings instance."""
    return settings
