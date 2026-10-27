"""Main AMR Assistant orchestrator and state machine."""

import asyncio
from enum import Enum
import logging
import time
from typing import Optional
import numpy as np

from src.audio.player import AudioPlayer
from src.audio.push_to_talk import PushToTalk
from src.audio.recorder import AudioRecorder
from src.audio.wake_word import WakeWordDetector
from src.config import settings
from src.core.live_client import GeminiLiveClient
from src.integrations.mobile_gateway import start_gateway
from src.integrations.system_tray import AtonSystemTray
from src.tools import dispatch_tool

try:
    from google.genai import types
except ImportError:
    types = None  # type: ignore

logger = logging.getLogger(__name__)


class AssistantState(str, Enum):
    """Lifecycle states of the AMR Assistant."""
    SLEEPING = "sleeping"
    WAKING = "waking"
    CONVERSING = "conversing"
    SHUTDOWN = "shutdown"


class AMRAssistant:
    """Orchestrates audio capture, wake word detection, live voice streaming, and system feedback."""

    def __init__(
        self,
        wake_word: Optional[str] = None,
        conversation_timeout: Optional[int] = None,
        api_key: Optional[str] = None,
    ):
        self.conversation_timeout = conversation_timeout or settings.conversation_timeout_seconds
        self.state = AssistantState.SLEEPING

        # Core subsystems
        self.recorder = AudioRecorder(sample_rate=settings.audio_sample_rate)
        self.player = AudioPlayer(sample_rate=24000)
        self.wake_detector = WakeWordDetector(wake_word=wake_word or settings.amr_wake_word)
        self.push_to_talk = PushToTalk(on_trigger_callback=self._on_manual_trigger)
        self.live_client = GeminiLiveClient(api_key=api_key, on_tool_call=self._handle_tool_call)

        self._last_interaction_time = 0.0
        self._last_user_speak_log = 0.0
        self._last_gemini_speak_log = 0.0
        self._running = False
        self._manual_wake_requested = False
        self._receive_task: Optional[asyncio.Task] = None
        self.gateway = None
        self.tray: Optional[AtonSystemTray] = None
        self._is_muted = False

    def _on_manual_trigger(self) -> None:
        """Callback invoked when push-to-talk hotkey or manual trigger is fired."""
        if self.state == AssistantState.SLEEPING:
            logger.info("Wake-up triggered manually (Push-to-Talk / Tecla Enter).")
            self._manual_wake_requested = True

    def _on_tray_toggle_mute(self, is_muted: bool) -> None:
        """Callback invoked when microphone mute is toggled from the system tray."""
        self._is_muted = is_muted
        logger.info(f"Microfone mudo via bandeja do sistema: {is_muted}")
        if is_muted and self.state == AssistantState.CONVERSING:
            asyncio.create_task(self._go_to_sleep())

    def _on_tray_request_briefing(self) -> None:
        """Callback invoked when daily briefing is requested from system tray."""
        logger.info("Resumo executivo disparado via bandeja do sistema.")
        async def _run_briefing():
            from src.core.memory import get_daily_briefing
            briefing = get_daily_briefing()
            logger.info(f"📋 Briefing Gerado: {briefing.get('message', '')}")
            if self.player:
                self.player.play_wake_chime()
        asyncio.create_task(_run_briefing())

    def _on_tray_exit(self) -> None:
        """Callback invoked when exit is selected from the system tray."""
        logger.info("Encerramento solicitado via bandeja do sistema.")
        self._running = False

    def _handle_tool_call(self, *args, **kwargs) -> None:
        """Callback invoked when Gemini Live requests an asynchronous tool execution."""
        if len(args) == 3:
            call_id, tool_name, tool_args = args
        elif len(args) == 2:
            call_id = ""
            tool_name, tool_args = args
        else:
            call_id = kwargs.get("call_id", "")
            tool_name = kwargs.get("tool_name", "")
            tool_args = kwargs.get("tool_args", {})

        logger.info(f"🛠️ Tool call recebido: {tool_name}({tool_args}) [ID: {call_id}]")

        async def _execute_and_reply():
            loop = asyncio.get_running_loop()
            # Execute in thread to avoid freezing audio loops
            result = await loop.run_in_executor(None, dispatch_tool, tool_name, tool_args)
            logger.info(f"🛠️ Execução da ferramenta concluída: {tool_name} -> {result.get('message', '')}")

            if self.live_client.is_connected and types is not None and call_id:
                response_item = types.FunctionResponse(
                    name=tool_name,
                    id=call_id,
                    response=result,
                )
                await self.live_client.send_tool_response([response_item])

        asyncio.create_task(_execute_and_reply())

    async def _wake_up(self) -> None:
        """Transition Aton from sleeping to active conversation state."""
        self.state = AssistantState.WAKING
        logger.info("Aton is waking up...")
        if self.tray:
            self.tray.update_state("listening", "Aton ouvindo...")
        self.player.play_wake_chime()
        self.player.play_greeting()

        # Connect to Gemini Live in pure realtime audio streaming mode
        connected = await self.live_client.connect()
        if connected:
            # Wait for greeting to finish playing before opening the microphone stream
            # to prevent acoustic echo from being sent to Gemini Live
            wait_start = time.time()
            while self.player.is_playing and (time.time() - wait_start < 4.0):
                await asyncio.sleep(0.05)

            # Flush any microphone chunks captured while the greeting was playing
            self.recorder.flush()

            self.state = AssistantState.CONVERSING
            self._last_interaction_time = time.time()
            # Start background listener for Gemini voice responses
            self._receive_task = asyncio.create_task(self._receive_gemini_audio())
            logger.info("Aton is now active and listening.")
        else:
            logger.warning("Could not connect to Gemini Live. Returning to sleep.")
            await self._go_to_sleep()

    async def _go_to_sleep(self) -> None:
        """Transition Aton back to passive sleep mode."""
        if self.state == AssistantState.SLEEPING:
            return

        logger.info("Silence timeout reached. Aton returning to sleep.")
        self.player.play_sleep_chime()

        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()

        await self.live_client.disconnect()
        self.state = AssistantState.SLEEPING
        if self.tray:
            self.tray.update_state(
                "muted" if self._is_muted else "sleeping",
                "Microfone Silenciado" if self._is_muted else "Em espera (diga 'Aton')",
            )
        logger.info("Aton is now sleeping. Say 'Aton' to activate.")

    async def _receive_gemini_audio(self) -> None:
        """Stream and play audio received from Gemini Live in real time."""
        try:
            async for pcm_chunk in self.live_client.receive_stream():
                if pcm_chunk:
                    now = time.time()
                    if now - self._last_gemini_speak_log > 2.0:
                        logger.info("🔊 Aton respondendo por voz...")
                        self._last_gemini_speak_log = now
                        if self.tray:
                            self.tray.update_state("speaking", "Aton falando...")
                    self.player.play_pcm_bytes(pcm_chunk)
                    self._last_interaction_time = now
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error(f"Error in Gemini audio receive loop: {exc}")
        finally:
            if self.tray and self.state == AssistantState.CONVERSING:
                self.tray.update_state("listening", "Aton ouvindo...")

    async def run(self) -> None:
        """Main execution loop for Aton."""
        self._running = True
        logger.info("Starting Aton Assistant audio pipeline...")

        try:
            self.recorder.start()
        except Exception as exc:
            logger.error(f"Cannot start microphone: {exc}. Audio loop will run in simulated mode.")

        logger.info(f"Aton is online and waiting for wake word ('{self.wake_detector.wake_word}').")

        # Start Mobile Gateway if enabled (Phase 3)
        if settings.gateway_enabled:
            self.gateway = await start_gateway(assistant=self)

        # Start System Tray if enabled (Phase 6)
        if settings.system_tray_enabled:
            try:
                self.tray = AtonSystemTray(
                    hud_url=f"http://localhost:{settings.gateway_port}",
                    on_toggle_mute=self._on_tray_toggle_mute,
                    on_request_briefing=self._on_tray_request_briefing,
                    on_exit=self._on_tray_exit,
                )
                self.tray.start()
            except Exception as exc:
                logger.warning(f"Could not initialize system tray: {exc}")

        try:
            while self._running:
                # If microphone is muted from tray, skip audio processing
                if self._is_muted:
                    await asyncio.sleep(0.05)
                    continue

                # Read 80ms PCM chunk from microphone
                chunk = await asyncio.get_running_loop().run_in_executor(
                    None, self.recorder.read_chunk, 0.1
                )

                now = time.time()

                if self.state == AssistantState.SLEEPING:
                    wake_triggered = self._manual_wake_requested
                    if not wake_triggered and chunk:
                        wake_triggered = self.wake_detector.process_pcm_chunk(chunk)

                    if wake_triggered:
                        self._manual_wake_requested = False
                        await self._wake_up()

                elif self.state == AssistantState.CONVERSING:
                    # If live connection disconnected, return to sleep gracefully
                    if not self.live_client.is_connected:
                        logger.info("Canal com Gemini Live finalizado. Aton retornando ao repouso.")
                        await self._go_to_sleep()
                        continue

                    # Keep conversation timer active while Aton is speaking
                    if self.player.is_playing:
                        self._last_interaction_time = now

                    if chunk:
                        # Check user voice volume level
                        audio_data = np.frombuffer(chunk, dtype=np.int16)
                        rms = float(np.sqrt(np.mean(audio_data.astype(np.float32) ** 2)))

                        # Anti-echo protection: do not send mic audio while Aton is speaking
                        # unless user speaks loudly (barge-in interruption)
                        should_stream = True
                        if self.player.is_playing and rms < 2000.0:
                            should_stream = False

                        if should_stream:
                            # Keep conversation active while user is speaking
                            if rms >= 300.0:
                                self._last_interaction_time = now
                                if now - self._last_user_speak_log > 2.0:
                                    logger.info(f"🎤 Ouvindo você falar... (RMS: {rms:.0f})")
                                    self._last_user_speak_log = now

                            # Stream microphone speech to Gemini Live
                            await self.live_client.send_audio_chunk(chunk)

                    # Check conversation timeout (user stopped talking)
                    if now - self._last_interaction_time > self.conversation_timeout:
                        await self._go_to_sleep()

                await asyncio.sleep(0.01)

        except asyncio.CancelledError:
            logger.info("Aton run loop cancelled.")
        finally:
            await self.shutdown()

    async def shutdown(self) -> None:
        """Cleanly shutdown all subsystems."""
        self._running = False
        self.state = AssistantState.SHUTDOWN
        logger.info("Shutting down Aton Assistant...")

        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()

        if self.gateway:
            await self.gateway.stop()

        if self.tray:
            self.tray.stop()

        await self.live_client.disconnect()
        self.recorder.stop()
        self.player.stop()
        logger.info("Aton shutdown complete.")
