"""Audio player for PCM audio streaming and system chimes using a threaded audio queue with thread-safe lifecycle and recovery."""

import asyncio
import logging
from pathlib import Path
import queue
import threading
import time
from typing import Any, Optional
import numpy as np

logger = logging.getLogger(__name__)

try:
    import sounddevice as sd
except ImportError:
    sd = None  # type: ignore

MAX_CONSECUTIVE_WRITE_FAILURES = 3
FAILURE_COOLDOWN_SECONDS = 5.0


class AudioPlayer:
    """Manages thread-safe playback of streaming audio from Gemini Live and system sounds."""

    def __init__(
        self,
        sample_rate: int = 24000,
        device_index: Optional[int] = None,
    ):
        self.sample_rate = sample_rate
        self.device_index = device_index
        self._is_playing = False
        self._stream: Optional[Any] = None
        self._queue: queue.Queue[Optional[np.ndarray]] = queue.Queue()
        self._running = True

        # Synchronization & Recovery State
        self._stream_lock = threading.RLock()
        self._consecutive_failures: int = 0
        self._total_recoveries: int = 0
        self._last_error: Optional[str] = None
        self._last_failure_time: float = 0.0
        self._in_cooldown: bool = False
        self._has_error: bool = False
        self._uncertain_chunk_dropped: bool = False

        # Start dedicated audio playback worker thread
        self._worker_thread = threading.Thread(target=self._playback_worker, daemon=True, name="AtonAudioPlayerWorker")
        self._worker_thread.start()

    def _discard_stream_unlocked(self) -> None:
        """Safely stop, close, and release the active stream handle without raising exceptions."""
        if self._stream is not None:
            try:
                self._stream.stop()
            except Exception:
                pass
            try:
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    def _ensure_stream(self) -> bool:
        """Ensure the continuous output stream is open, active, and valid.
        
        Must be called with self._stream_lock acquired.
        Returns:
            bool: True if stream is open and ready to accept audio writes; False otherwise.
        """
        if sd is None:
            return False

        now = time.time()
        # Cooldown check: do not hammer PortAudio if in failure cooldown
        if self._in_cooldown:
            if now - self._last_failure_time < FAILURE_COOLDOWN_SECONDS:
                return False
            logger.info("Período de cooldown expirado. Tentando restabelecer OutputStream...")
            self._in_cooldown = False

        # Check existing stream
        if self._stream is not None:
            try:
                # Pa_IsStreamActive can raise PortAudioError: Invalid stream pointer [PaErrorCode -9988]
                if bool(self._stream.active):
                    return True
            except Exception as exc:
                logger.debug(f"Verificação de stream ativo falhou ({exc}). Descartando stream corrompido.")
                self._discard_stream_unlocked()

        # Open fresh stream
        try:
            self._discard_stream_unlocked()
            self._stream = sd.OutputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="float32",
                device=self.device_index,
            )
            self._stream.start()
            self._has_error = False
            return True
        except Exception as exc:
            self._handle_failure_unlocked(exc)
            return False

    def _handle_failure_unlocked(self, exc: Exception) -> None:
        """Handle stream write or open failure with bounded retries and cooldown.
        
        Must be called with self._stream_lock acquired.
        """
        self._discard_stream_unlocked()
        self._consecutive_failures += 1
        self._last_failure_time = time.time()
        self._last_error = str(exc)
        self._has_error = True
        self._is_playing = False

        if self._consecutive_failures >= MAX_CONSECUTIVE_WRITE_FAILURES:
            self._in_cooldown = True
            logger.warning(
                f"⚠️ [AUDIO_PLAYER_ERROR] Falha persistente na saída de áudio ({exc}). "
                f"Descartando fila e aguardando {FAILURE_COOLDOWN_SECONDS}s para recuperação."
            )
            # Purge stale queued audio so we don't accumulate or replay outdated speech
            dropped = self.clear_queue()
            if dropped > 0:
                self._uncertain_chunk_dropped = True
                logger.info(f"Descartados {dropped} trechos de áudio antigos após falha de saída.")
        else:
            logger.warning(
                f"⚠️ [AUDIO_PLAYER_RECOVERING] Erro no stream de saída ({exc}). "
                f"Tentativa {self._consecutive_failures}/{MAX_CONSECUTIVE_WRITE_FAILURES}..."
            )

    def _playback_worker(self) -> None:
        """Worker thread that continuously pulls audio chunks from the queue and writes to sounddevice."""
        while self._running:
            try:
                audio_data = self._queue.get(timeout=0.1)
                if audio_data is None:
                    continue

                with self._stream_lock:
                    if not self._running:
                        break

                    ready = self._ensure_stream()
                    if not ready or self._stream is None:
                        # Output stream unavailable or in cooldown: drop chunk and mark uncertain
                        self._uncertain_chunk_dropped = True
                        self._is_playing = False
                        continue

                    self._is_playing = True
                    try:
                        self._stream.write(audio_data)
                        if self._consecutive_failures > 0:
                            logger.info("✅ [AUDIO_PLAYER_RECOVERED] Saída de áudio restabelecida com sucesso.")
                            self._total_recoveries += 1
                        self._consecutive_failures = 0
                        self._has_error = False
                    except Exception as exc:
                        self._handle_failure_unlocked(exc)
                    finally:
                        self._is_playing = False

            except queue.Empty:
                self._is_playing = False
                continue
            except Exception as worker_exc:
                logger.error(f"Unexpected error in audio playback worker: {worker_exc}")
                self._is_playing = False

    def clear_queue(self) -> int:
        """Drain all queued audio chunks and return count of dropped chunks."""
        dropped = 0
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
                dropped += 1
            except queue.Empty:
                break
        return dropped

    def prepare_for_subsystem_reinit(self) -> None:
        """Safely close and release output stream before PortAudio re-initialization."""
        with self._stream_lock:
            logger.info("Preparando AudioPlayer para reinicialização do PortAudio...")
            self.clear_queue()
            self._discard_stream_unlocked()
            self._is_playing = False

    def on_subsystem_reinitialized(self) -> None:
        """Reset internal error counters and prepare for fresh stream creation."""
        with self._stream_lock:
            self._discard_stream_unlocked()
            self._consecutive_failures = 0
            self._has_error = False
            self._in_cooldown = False
            logger.info("AudioPlayer pronto após reinicialização do subsistema de áudio.")

    def generate_chime(
        self,
        frequency_hz: float = 880.0,
        duration_seconds: float = 0.15,
        fade_ratio: float = 0.2,
    ) -> np.ndarray:
        """Synthesize a clean sine wave chime with smooth attack and decay envelope."""
        total_samples = int(self.sample_rate * duration_seconds)
        if total_samples <= 0:
            return np.zeros(0, dtype=np.float32)

        t = np.linspace(0, duration_seconds, total_samples, endpoint=False, dtype=np.float32)
        sine_wave = np.sin(2.0 * np.pi * frequency_hz * t, dtype=np.float32)

        fade_samples = int(total_samples * fade_ratio)
        if fade_samples > 0:
            fade_in = np.linspace(0.0, 1.0, fade_samples, dtype=np.float32)
            fade_out = np.linspace(1.0, 0.0, fade_samples, dtype=np.float32)
            sine_wave[:fade_samples] *= fade_in
            sine_wave[-fade_samples:] *= fade_out

        return sine_wave * 0.5

    def play_sound(self, audio_data: np.ndarray, blocking: bool = False) -> None:
        """Queue a numpy array of audio samples for playback."""
        if audio_data is not None and len(audio_data) > 0:
            # If in hard cooldown failure, check if cooldown window has expired
            if self._has_error and self._in_cooldown:
                now = time.time()
                if now - self._last_failure_time >= FAILURE_COOLDOWN_SECONDS:
                    self._in_cooldown = False
                else:
                    self._uncertain_chunk_dropped = True
                    return
            self._queue.put(audio_data.astype(np.float32))

    def play_wake_chime(self) -> None:
        """Play a crisp double-tone chime indicating Aton has awakened."""
        tone1 = self.generate_chime(frequency_hz=660.0, duration_seconds=0.08)
        silence = np.zeros(int(self.sample_rate * 0.02), dtype=np.float32)
        tone2 = self.generate_chime(frequency_hz=880.0, duration_seconds=0.12)
        full_chime = np.concatenate([tone1, silence, tone2])
        self.play_sound(full_chime)

    def play_sleep_chime(self) -> None:
        """Play a descending double-tone chime indicating Aton is sleeping."""
        tone1 = self.generate_chime(frequency_hz=880.0, duration_seconds=0.08)
        silence = np.zeros(int(self.sample_rate * 0.02), dtype=np.float32)
        tone2 = self.generate_chime(frequency_hz=587.0, duration_seconds=0.12)
        full_chime = np.concatenate([tone1, silence, tone2])
        self.play_sound(full_chime)

    def play_greeting(self) -> None:
        """Play immediate natural spoken greeting from Aoede."""
        assets_dir = Path(__file__).parent / "assets"
        greeting_file = assets_dir / "greeting_aoede.pcm"
        if greeting_file.exists():
            pcm_data = greeting_file.read_bytes()
            self.play_pcm_bytes(pcm_data)
        else:
            self.play_wake_chime()

    def play_pcm_bytes(self, pcm_bytes: bytes, dtype: str = "int16") -> None:
        """Queue raw PCM bytes received from Gemini Live API."""
        if not pcm_bytes:
            return
        audio_array = np.frombuffer(pcm_bytes, dtype=dtype)
        if dtype == "int16":
            audio_float = audio_array.astype(np.float32) / 32768.0
        else:
            audio_float = audio_array.astype(np.float32)
        self.play_sound(audio_float)

    def stop(self) -> None:
        """Immediately stop playback, clear pending audio queue, and safely close stream."""
        with self._stream_lock:
            self.clear_queue()
            self._discard_stream_unlocked()
            self._is_playing = False
            if sd is not None:
                try:
                    sd.stop()
                except Exception as exc:
                    logger.debug(f"Error stopping sounddevice: {exc}")

    @property
    def is_playing(self) -> bool:
        """Check if audio is currently playing or queued for output."""
        if self._has_error and self._in_cooldown:
            return False
        return self._is_playing or not self._queue.empty()

    @property
    def is_healthy(self) -> bool:
        """Check if audio player is healthy and operational."""
        return sd is not None and not self._has_error and not self._in_cooldown

    @property
    def has_error(self) -> bool:
        """Check if audio player currently has an active unrecovered error."""
        return self._has_error

    @property
    def in_cooldown(self) -> bool:
        """Check if audio player is currently in failure backoff cooldown."""
        return self._in_cooldown
