"""Gemini Live API client for real-time bidirectional audio streaming using Google GenAI SDK."""

import asyncio
import logging
from typing import Any, AsyncGenerator, Callable, Optional

logger = logging.getLogger(__name__)

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None  # type: ignore
    types = None  # type: ignore
    logger.warning("google-genai SDK is not installed. Gemini Live client will run in simulated mode.")

# Disable websockets keepalive ping timeout to prevent 1011 timeout error with Google Live API
try:
    import websockets.asyncio.client
    if hasattr(websockets.asyncio.client.ClientConnection.__init__, "__kwdefaults__"):
        kwdefaults = websockets.asyncio.client.ClientConnection.__init__.__kwdefaults__
        if kwdefaults is not None:
            kwdefaults["ping_interval"] = None
            kwdefaults["ping_timeout"] = None
except Exception:
    pass

from src.config import settings
from src.core.prompts import AMR_SYSTEM_INSTRUCTION
from src.tools import ALL_ATON_TOOLS


class GeminiLiveClient:
    """Manages the real-time WebSocket session with Gemini Live API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        voice_name: Optional[str] = None,
        system_instruction: str = AMR_SYSTEM_INSTRUCTION,
        tools: Optional[list] = None,
        on_tool_call: Optional[Callable[..., Any]] = None,
    ):
        self.api_key = api_key if api_key is not None else settings.gemini_api_key
        self.model = model or settings.gemini_live_model
        self.voice_name = voice_name or settings.gemini_voice_name
        self.system_instruction = system_instruction
        self.tools = tools if tools is not None else ALL_ATON_TOOLS
        self.on_tool_call = on_tool_call

        self._client: Optional[Any] = None
        self._session: Optional[Any] = None
        self._session_ctx: Optional[Any] = None
        self._is_connected = False

    def is_configured(self) -> bool:
        """Check if API key is provided and SDK is available."""
        return bool(self.api_key and self.api_key != "your_gemini_api_key_here" and genai is not None)

    async def connect(self) -> bool:
        """Establish the bidirectional live session with Gemini."""
        if not self.is_configured():
            logger.warning("Gemini Live API key not configured. Operating in local simulated mode.")
            self._is_connected = True
            return True

        try:
            self._client = genai.Client(api_key=self.api_key, http_options={"api_version": "v1alpha"})

            # Configure live tools if provided
            live_tools = None
            if self.tools:
                live_tools = [types.Tool(function_declarations=self.tools)]

            # Configure multimodal live audio session
            config = types.LiveConnectConfig(
                response_modalities=[types.Modality.AUDIO],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=self.voice_name)
                    )
                ),
                system_instruction=types.Content(
                    parts=[types.Part.from_text(text=self.system_instruction)]
                ),
                tools=live_tools,
            )

            # Connect live session context manager
            self._session_ctx = self._client.aio.live.connect(model=self.model, config=config)
            self._session = await self._session_ctx.__aenter__()
            self._is_connected = True
            logger.info(f"Connected to Gemini Live API ({self.model}) with voice '{self.voice_name}' and {len(self.tools) if self.tools else 0} tools.")
            return True
        except Exception as exc:
            logger.error(f"Failed to connect to Gemini Live API: {exc}")
            self._is_connected = False
            return False

    async def send_audio_chunk(self, pcm_bytes: bytes) -> None:
        """Send a chunk of PCM audio from the microphone to Gemini Live."""
        if not self._is_connected or self._session is None:
            return

        try:
            mime = f"audio/pcm;rate={settings.audio_sample_rate}"
            # Send realtime raw PCM audio using the dedicated send_realtime_input method
            if hasattr(self._session, "send_realtime_input"):
                await self._session.send_realtime_input(
                    audio=types.Blob(
                        data=pcm_bytes,
                        mime_type=mime,
                    )
                )
            else:
                await self._session.send(
                    input=types.LiveClientRealtimeInput(
                        audio=types.Blob(
                            data=pcm_bytes,
                            mime_type=mime,
                        )
                    )
                )
        except Exception as exc:
            if self._is_connected:
                self._is_connected = False
                logger.warning(f"Sessao do Gemini Live desconectada: {exc}")

    async def send_text_prompt(self, text: str) -> None:
        """Send a text prompt to trigger an immediate spoken response from Gemini Live."""
        if not self._is_connected or self._session is None:
            return

        try:
            await self._session.send(
                input=types.LiveClientContent(
                    turns=[
                        types.Content(
                            role="user",
                            parts=[types.Part.from_text(text=text)],
                        )
                    ],
                    turn_complete=True,
                )
            )
        except Exception as exc:
            logger.error(f"Error sending text prompt to Gemini Live: {exc}")

    async def send_tool_response(self, function_responses: list) -> None:
        """Send the execution result of tool calls back to Gemini Live."""
        if not self._is_connected or self._session is None:
            return

        try:
            if hasattr(self._session, "send_tool_response"):
                await self._session.send_tool_response(function_responses=function_responses)
            else:
                await self._session.send(
                    input=types.LiveClientToolResponse(function_responses=function_responses)
                )
            logger.info(f"Tool response sent to Gemini Live ({len(function_responses)} item(s)).")
        except Exception as exc:
            logger.error(f"Error sending tool response to Gemini Live: {exc}")

    async def receive_stream(self) -> AsyncGenerator[bytes, None]:
        """Receive continuous audio responses and events from Gemini Live across multiple turns."""
        if not self._is_connected or self._session is None:
            return

        while self._is_connected and self._session is not None:
            try:
                async for response in self._session.receive():
                    server_content = response.server_content
                    if server_content is not None:
                        model_turn = server_content.model_turn
                        if model_turn is not None:
                            for part in model_turn.parts:
                                # Log text transcript if model provides it
                                if hasattr(part, "text") and part.text:
                                    logger.info(f"🗣️ Aton: {part.text.strip()}")
                                # Extract audio output bytes
                                if part.inline_data and part.inline_data.data:
                                    yield part.inline_data.data
                                # Handle function calls inside parts
                                if hasattr(part, "function_call") and part.function_call and self.on_tool_call:
                                    fc = part.function_call
                                    call_id = getattr(fc, "id", "") or ""
                                    call_name = getattr(fc, "name", "")
                                    call_args = getattr(fc, "args", {}) or {}
                                    try:
                                        res = self.on_tool_call(call_id, call_name, call_args)
                                        if asyncio.iscoroutine(res):
                                            asyncio.create_task(res)
                                    except TypeError:
                                        self.on_tool_call(call_name, call_args)

                        if server_content.turn_complete:
                            logger.debug("Turn complete received from Gemini Live.")
                        if server_content.interrupted:
                            logger.info("Aton fala interrompida pelo usuario.")

                    # Handle tool calling if present at response level
                    tool_call = response.tool_call
                    if tool_call and self.on_tool_call:
                        for call in tool_call.function_calls:
                            call_id = getattr(call, "id", "") or ""
                            call_name = getattr(call, "name", "")
                            call_args = getattr(call, "args", {}) or {}
                            try:
                                res = self.on_tool_call(call_id, call_name, call_args)
                                if asyncio.iscoroutine(res):
                                    asyncio.create_task(res)
                            except TypeError:
                                self.on_tool_call(call_name, call_args)

            except asyncio.CancelledError:
                logger.debug("Gemini Live receive stream cancelled.")
                break
            except Exception as exc:
                if self._is_connected:
                    self._is_connected = False
                    logger.warning(f"Canal de recebimento do Gemini Live desconectado: {exc}")
                break

    async def disconnect(self) -> None:
        """Disconnect and cleanup the Gemini Live session."""
        if not self._is_connected:
            return

        if self._session_ctx is not None:
            try:
                await self._session_ctx.__aexit__(None, None, None)
            except Exception as exc:
                logger.warning(f"Error closing Gemini Live session: {exc}")
            finally:
                self._session = None
                self._session_ctx = None

        self._is_connected = False
        logger.info("Disconnected from Gemini Live API.")

    @property
    def is_connected(self) -> bool:
        """Check if currently connected to Gemini Live."""
        return self._is_connected
