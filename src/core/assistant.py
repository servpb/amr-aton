"""Main AMR Assistant orchestrator and state machine."""

import asyncio
import ctypes
from enum import Enum
import logging
import threading
import time
from typing import Any, Optional
import numpy as np

from src.audio.player import AudioPlayer
from src.audio.push_to_talk import PushToTalk
from src.audio.recorder import AudioRecorder
from src.audio.wake_word import WakeWordDetector
from src.config import settings
from src.integrations.system_tray import AtonSystemTray

logger = logging.getLogger(__name__)


def _dispatch_tool_lazy(tool_name: str, tool_args: dict) -> dict:
    """Lazy import and dispatch of the 68 Aton tools."""
    from src.tools import dispatch_tool
    return dispatch_tool(tool_name, tool_args)


def _get_genai_types() -> Any:
    """Lazy load google.genai types."""
    try:
        from google.genai import types
        return types
    except ImportError:
        return None


def _get_youtube_service_lazy() -> Any:
    """Lazy access to YouTube confirmation service."""
    try:
        from src.integrations.youtube_service import get_youtube_service
        return get_youtube_service()
    except Exception:
        return None


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
        tray: Optional[AtonSystemTray] = None,
        t_boot_start: Optional[float] = None,
    ):
        self.conversation_timeout = conversation_timeout or settings.conversation_timeout_seconds
        self.state = AssistantState.SLEEPING
        self._api_key = api_key

        # Boot & performance telemetry clocks
        self._t_boot_start: float = t_boot_start if t_boot_start is not None else time.perf_counter()
        self._t1_local_ready: float = 0.0
        self._t2_conv_ready: float = 0.0
        self._t_wake_turn_start: float = 0.0
        self._first_spoken_logged: bool = False
        self._first_tool_logged: bool = False

        # Fast core subsystems (lightweight, zero tool imports on main thread)
        self.recorder = AudioRecorder(sample_rate=settings.audio_sample_rate)
        self.player = AudioPlayer(sample_rate=24000)
        self.wake_detector = WakeWordDetector(wake_word=wake_word or settings.amr_wake_word)
        self.push_to_talk = PushToTalk(on_trigger_callback=self._on_manual_trigger)

        # Secondary components initialized via background warm-up
        self._live_client: Optional[Any] = None
        self._is_warmup_complete: bool = False
        self._warmup_error: Optional[str] = None
        self._warmup_thread: Optional[threading.Thread] = None

        self._last_interaction_time = 0.0
        self._last_user_speak_log = 0.0
        self._last_gemini_speak_log = 0.0
        self._last_playback_end_time = 0.0
        self._was_playing = False
        self._active_tool_calls = 0
        self._running = False
        self._manual_wake_requested = False
        self._receive_task: Optional[asyncio.Task] = None
        self.gateway = None
        self.tray: Optional[AtonSystemTray] = tray
        self._is_muted = False

    @property
    def live_client(self) -> Any:
        """Provide transparent access to GeminiLiveClient once warm-up completes."""
        return self._live_client

    def _start_background_warmup(self) -> None:
        """Launch background warm-up worker in a dedicated thread with reduced priority."""
        if self._is_warmup_complete or (self._warmup_thread and self._warmup_thread.is_alive()):
            return

        def _worker():
            # Lower thread priority on Windows so audio loop in main thread is never starved
            try:
                # THREAD_PRIORITY_BELOW_NORMAL = -1
                ctypes.windll.kernel32.SetThreadPriority(ctypes.windll.kernel32.GetCurrentThread(), -1)
            except Exception:
                pass

            logger.info("⏳ Iniciando pré-aquecimento de ferramentas e cliente Gemini em segundo plano...")
            t_warmup_start = time.perf_counter()

            try:
                # 1. Lazy load Gemini Live Client
                from src.core.live_client import GeminiLiveClient
                self._live_client = GeminiLiveClient(api_key=self._api_key, on_tool_call=self._handle_tool_call)

                # 2. Lazy load and test tool dispatcher
                from src.tools import dispatch_tool  # Pre-import all 68 tools
                _ = dispatch_tool

                # 3. Invalidate any stale in-memory YouTube confirmations
                yt_svc = _get_youtube_service_lazy()
                if yt_svc is not None and hasattr(yt_svc, "reset_session"):
                    yt_svc.reset_session()

                self._is_warmup_complete = True
                self._warmup_error = None
                self._t2_conv_ready = time.perf_counter()
                elapsed_total = (self._t2_conv_ready - self._t_boot_start) * 1000.0
                elapsed_warmup = (self._t2_conv_ready - t_warmup_start) * 1000.0
                logger.info(
                    f"🚀 [BOOT_METRIC] T2_conversation_ready_ms: {elapsed_total:.1f}ms "
                    f"(Warmup interno levou {elapsed_warmup:.1f}ms - todos os 68 módulos prontos)"
                )

                if self.tray and self.state == AssistantState.SLEEPING:
                    self.tray.update_state(
                        "ready",
                        "Pronto para conversar (diga 'Aton')",
                    )
            except Exception as exc:
                self._warmup_error = str(exc)
                logger.error(f"❌ Falha no pré-aquecimento de componentes secundários: {exc}")
                if self.tray:
                    self.tray.update_state(
                        "init_error",
                        f"Falha ao carregar componentes: {exc}",
                    )

        self._warmup_thread = threading.Thread(target=_worker, daemon=True, name="AtonWarmupWorker")
        self._warmup_thread.start()

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

    def _on_tray_retry_init(self) -> None:
        """Callback invoked when retry warm-up is requested from system tray."""
        logger.info("Bandeja solicitou nova tentativa de carregamento de componentes...")
        if self.tray:
            self.tray.update_state("local_listening", "Tentando recarregar componentes...")
        self._is_warmup_complete = False
        self._start_background_warmup()

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

        if tool_name in ("stop_listening", "parar_escuta"):
            logger.info("🛑 Encerramento de escuta acionado por comando de voz ('Pare').")
            asyncio.create_task(self._go_to_sleep())
            return

        async def _execute_and_reply():
            self._active_tool_calls += 1
            self._last_interaction_time = time.time()
            try:
                loop = asyncio.get_running_loop()
                # Execute in thread to avoid freezing audio loops
                result = await loop.run_in_executor(None, _dispatch_tool_lazy, tool_name, tool_args)
                logger.info(f"🛠️ Execução da ferramenta concluída: {tool_name} -> {result.get('message', '')}")
                self._last_interaction_time = time.time()

                if not self._first_tool_logged and self._t_wake_turn_start > 0:
                    t4 = time.perf_counter()
                    logger.info(
                        f"🛠️ [PERF_METRIC] T4_first_tool_completed_ms: {(t4 - self._t_wake_turn_start) * 1000:.1f}ms "
                        f"(ferramenta: {tool_name})"
                    )
                    self._first_tool_logged = True

                types_mod = _get_genai_types()
                if self.live_client and self.live_client.is_connected and types_mod is not None and call_id:
                    response_item = types_mod.FunctionResponse(
                        name=tool_name,
                        id=call_id,
                        response=result,
                    )
                    await self.live_client.send_tool_response([response_item])
                    self._last_interaction_time = time.time()
            finally:
                self._active_tool_calls = max(0, self._active_tool_calls - 1)
                self._last_interaction_time = time.time()

        asyncio.create_task(_execute_and_reply())

    async def _wake_up(self) -> None:
        """Transition Aton from sleeping to active conversation state."""
        if not self._is_warmup_complete or self.live_client is None:
            logger.warning("Tentativa de despertar ignorada: warm-up ainda incompleto.")
            return

        self.state = AssistantState.WAKING
        logger.info("Aton is waking up...")
        if self.tray:
            self.tray.update_state("listening", "Aton ouvindo...")

        # Start WebSocket handshake in parallel with audio chime + greeting for measured low latency
        t_conn_start = time.perf_counter()
        connect_task = asyncio.create_task(self.live_client.connect())
        self.player.play_wake_chime()
        self.player.play_greeting()

        connected = await connect_task
        t_conn_elapsed = (time.perf_counter() - t_conn_start) * 1000.0
        logger.info(f"🌐 [PERF_METRIC] Gemini Live WebSocket handshake: {t_conn_elapsed:.1f}ms (sucesso={connected})")

        if connected:
            # Brief wait if greeting is still finishing to avoid acoustic echo
            wait_start = time.time()
            while self.player.is_playing and (time.time() - wait_start < 0.8):
                await asyncio.sleep(0.03)

            # Flush any microphone chunks captured while the greeting was playing
            self.recorder.flush()
            self.wake_detector.reset()

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

        logger.info("Returning to sleep (stop listening).")
        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()

        # Stop any ongoing speech playback immediately before sleep chime
        self.player.stop()
        self.player.play_sleep_chime()

        if self.live_client is not None:
            await self.live_client.disconnect()
        self.recorder.flush()
        self.wake_detector.reset()
        try:
            from src.core.target_context import get_target_context
            get_target_context().clear()
        except Exception as e:
            logger.debug(f"Could not clear target context on sleep: {e}")
        self.state = AssistantState.SLEEPING
        if self.tray:
            status = "Microfone Silenciado" if self._is_muted else (
                "Pronto para conversar (diga 'Aton')" if self._is_warmup_complete else "Escuta local ativa"
            )
            state_key = "muted" if self._is_muted else (
                "ready" if self._is_warmup_complete else "local_listening"
            )
            self.tray.update_state(state_key, status)
        logger.info("Aton is now sleeping. Say 'Aton' to activate.")

    async def _receive_gemini_audio(self) -> None:
        """Stream and play audio received from Gemini Live in real time."""
        if not self.live_client:
            return
        try:
            async for pcm_chunk in self.live_client.receive_stream():
                if pcm_chunk:
                    now = time.time()
                    if not self._first_spoken_logged and self._t_wake_turn_start > 0:
                        t3 = time.perf_counter()
                        logger.info(
                            f"🔊 [PERF_METRIC] T3_first_spoken_response_ms: {(t3 - self._t_wake_turn_start) * 1000:.1f}ms"
                        )
                        self._first_spoken_logged = True

                    if now - self._last_gemini_speak_log > 2.0:
                        logger.info("🔊 Aton respondendo por voz...")
                        self._last_gemini_speak_log = now
                        if self.tray:
                            self.tray.update_state("speaking", "Aton falando...")
                    self.player.play_pcm_bytes(pcm_chunk)
                    try:
                        yt_svc = _get_youtube_service_lazy()
                        if yt_svc is not None and hasattr(yt_svc, "confirmations"):
                            yt_svc.confirmations.notify_voice_playback_started()
                    except Exception:
                        pass
                    self._last_interaction_time = now
                    self._last_playback_end_time = now
                    self._was_playing = True
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

        # 1. Start audio recorder (microphone)
        try:
            self.recorder.start()
        except Exception as exc:
            logger.error(f"Cannot start microphone: {exc}. Audio loop will run in simulated mode.")
            if self.tray:
                self.tray.update_state("mic_error", "Falha no microfone ao inicializar")

        # 2. Record T1 metric: local listening is now operational
        self._t1_local_ready = time.perf_counter()
        elapsed_t1 = (self._t1_local_ready - self._t_boot_start) * 1000.0
        logger.info(
            f"🎙️ [BOOT_METRIC] T1_local_listening_ready_ms: {elapsed_t1:.1f}ms "
            f"(microfone aberto e escuta local '{self.wake_detector.wake_word}' ativa)"
        )

        # 3. Transition tray to local_listening immediately
        if self.tray:
            self.tray.update_state(
                "local_listening",
                "Escuta local ativa (carregando componentes)...",
            )

        # 4. Launch background warm-up for heavy secondary tools and Gemini Live
        self._start_background_warmup()

        # 5. Start Mobile Gateway if enabled (Phase 3)
        if settings.gateway_enabled:
            try:
                from src.integrations.mobile_gateway import start_gateway
                self.gateway = await start_gateway(assistant=self)
            except Exception as exc:
                logger.warning(f"Could not start mobile gateway: {exc}")

        last_mic_retry = time.time()

        try:
            while self._running:
                # Watchdog: if microphone failed to open or stopped delivering audio after Windows boot/resume, restart it
                if not self.recorder.is_healthy() and (time.time() - last_mic_retry > 6.0):
                    last_mic_retry = time.time()
                    if self.tray:
                        self.tray.update_state("mic_error", "Falha no microfone (tentando reconectar...)")
                    try:
                        self.recorder.restart()
                        logger.info("Microphone stream recovered via watchdog.")
                        if self.tray:
                            status_str = (
                                "Pronto para conversar (diga 'Aton')"
                                if self._is_warmup_complete
                                else "Escuta local ativa (carregando componentes)..."
                            )
                            state_str = "ready" if self._is_warmup_complete else "local_listening"
                            self.tray.update_state(state_str, status_str)
                    except Exception as exc:
                        logger.debug(f"Microphone watchdog retry failed: {exc}")

                # If microphone is muted from tray, skip audio processing
                if self._is_muted:
                    await asyncio.sleep(0.05)
                    continue

                # Continuous backlog discard while secondary components are warming up
                if not self._is_warmup_complete:
                    self.recorder.clear_backlog(keep_latest=1)

                # Read 80ms PCM chunk from microphone and monitor audio loop jitter
                t_read_start = time.perf_counter()
                chunk = await asyncio.get_running_loop().run_in_executor(
                    None, self.recorder.read_chunk, 0.1
                )
                t_read_elapsed = time.perf_counter() - t_read_start
                if t_read_elapsed > 0.25:
                    logger.warning(
                        f"⚠️ [AUDIO_LOOP_JITTER] Leitura do microfone demorou {t_read_elapsed * 1000:.1f}ms "
                        f"(warmup_complete={self._is_warmup_complete})"
                    )

                now = time.time()

                if self.state == AssistantState.SLEEPING:
                    wake_triggered = self._manual_wake_requested
                    if not wake_triggered and chunk:
                        if hasattr(self.recorder, "drain_available_chunks"):
                            chunk = self.recorder.drain_available_chunks(chunk, max_extra_chunks=2)
                        wake_triggered = self.wake_detector.process_pcm_chunk(chunk)

                    if wake_triggered:
                        self._manual_wake_requested = False
                        # If called before secondary components have finished warming up:
                        if not self._is_warmup_complete:
                            logger.info(
                                "⏳ [CHAMADA_EM_WARMUP] 'Aton' chamado antes da prontidão total. "
                                "Emitindo retorno sonoro local imediato e descartando fila antiga."
                            )
                            self.player.play_wake_chime()
                            self.recorder.clear_backlog(keep_latest=0)
                            self.recorder.flush()
                            self.wake_detector.reset()
                            continue

                        # Full conversation readiness: start conversation turn
                        self._t_wake_turn_start = time.perf_counter()
                        await self._wake_up()

                elif self.state == AssistantState.CONVERSING:
                    # If live connection disconnected, return to sleep gracefully
                    if not self.live_client or not self.live_client.is_connected:
                        logger.info("Canal com Gemini Live finalizado. Aton retornando ao repouso.")
                        await self._go_to_sleep()
                        continue

                    # Keep conversation timer active while Aton is speaking or executing background tools
                    if self.player.is_playing or self._active_tool_calls > 0:
                        self._last_interaction_time = now

                    if self.player.is_playing:
                        # Strict speaker echo suppression: while Aton is speaking through the speakers,
                        # NEVER stream loudspeaker audio back into Gemini Live (prevents self-interruption).
                        self._was_playing = True
                        self._last_playback_end_time = now
                        if chunk:
                            audio_data = np.frombuffer(chunk, dtype=np.int16)
                            rms = float(np.sqrt(np.mean(audio_data.astype(np.float32) ** 2)))
                            if rms >= 2200.0 and self.wake_detector.detect_stop_command(chunk):
                                logger.info("🛑 Comando 'Pare' detectado! Parando de escutar imediatamente.")
                                await self._go_to_sleep()
                                continue
                    elif self._was_playing or (now - self._last_playback_end_time < 0.45):
                        # Flush buffered loudspeaker echo captured while Aton was speaking
                        self.recorder.flush()
                        self.wake_detector.reset()
                        self._last_interaction_time = now
                        if now - self._last_playback_end_time >= 0.45:
                            self._was_playing = False
                        self.recorder.flush()
                        self.wake_detector.reset()
                        self._last_interaction_time = now
                        if now - self._last_playback_end_time >= 0.45:
                            self._was_playing = False
                            try:
                                get_youtube_service().confirmations.notify_voice_playback_completed_cleanly()
                            except Exception:
                                pass
                    elif chunk:
                        # Coalesce any queued microphone chunks so audio streaming stays strictly real-time
                        if hasattr(self.recorder, "drain_available_chunks"):
                            chunk = self.recorder.drain_available_chunks(chunk, max_extra_chunks=4)

                        audio_data = np.frombuffer(chunk, dtype=np.int16)
                        rms = float(np.sqrt(np.mean(audio_data.astype(np.float32) ** 2)))

                        # Check local offline stop command ("Pare" / "Parar") only when voice energy is present
                        if rms >= 350.0 and self.wake_detector.detect_stop_command(chunk):
                            logger.info("🛑 Comando 'Pare' detectado! Parando de escutar imediatamente.")
                            await self._go_to_sleep()
                            continue

                        # Keep conversation active while user is speaking
                        if rms >= 300.0:
                            self._last_interaction_time = now
                            if now - self._last_user_speak_log > 2.0:
                                logger.info(f"🎤 Ouvindo você falar... (RMS: {rms:.0f})")
                                self._last_user_speak_log = now

                            # Evaluate out-of-band voice confirmation/cancellation when a YouTube write proposal is pending
                            try:
                                yt_confirm = get_youtube_service().confirmations
                                if yt_confirm.get_active_pending_confirmation() is not None:
                                    intent = self.wake_detector.detect_confirmation_intent(chunk)
                                    if intent == "affirm":
                                        yt_confirm.record_user_affirmative_turn(source="voice")
                                    elif intent == "cancel":
                                        yt_confirm.cancel_active_proposal("Operação cancelada verbalmente pelo usuário.")
                            except Exception as exc:
                                logger.debug(f"Confirmation intent check error: {exc}")

                        # Stream microphone speech to Gemini Live immediately
                        await self.live_client.send_audio_chunk(chunk)

                    # Check conversation timeout (user stopped talking)
                    if now - self._last_interaction_time > self.conversation_timeout:
                        await self._go_to_sleep()

                await asyncio.sleep(0)

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

        if self.live_client is not None:
            await self.live_client.disconnect()
        self.recorder.stop()
        self.player.stop()
        logger.info("Aton shutdown complete.")
