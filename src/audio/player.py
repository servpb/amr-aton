"""Audio player for PCM audio streaming and system chimes using a threaded audio queue."""

import asyncio
import logging
import queue
import threading
from typing import Any, Optional
import numpy as np

logger = logging.getLogger(__name__)

try:
    import sounddevice as sd
except ImportError:
    sd = None  # type: ignore


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

        # Start dedicated audio playback worker thread
        self._worker_thread = threading.Thread(target=self._playback_worker, daemon=True)
        self._worker_thread.start()

    def _ensure_stream(self) -> None:
        """Ensure the continuous output stream is open and active."""
        if sd is None:
            return
        if self._stream is None or not self._stream.active:
            try:
                self._stream = sd.OutputStream(
                    samplerate=self.sample_rate,
                    channels=1,
                    dtype="float32",
                    device=self.device_index,
                )
                self._stream.start()
            except Exception as exc:
                logger.error(f"Error initializing audio OutputStream: {exc}")
                self._stream = None

    def _playback_worker(self) -> None:
        """Worker thread that continuously pulls audio chunks from the queue and writes to sounddevice."""
        while self._running:
            try:
                audio_data = self._queue.get(timeout=0.1)
                if audio_data is None:
                    continue

                self._is_playing = True
                self._ensure_stream()
                if self._stream is not None:
                    self._stream.write(audio_data)
                elif sd is not None:
                    sd.play(audio_data, samplerate=self.sample_rate, device=self.device_index)
                    sd.wait()
                self._is_playing = False
            except queue.Empty:
                self._is_playing = False
                continue
            except Exception as exc:
                logger.error(f"Error in audio playback worker: {exc}")
                self._is_playing = False

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
        from pathlib import Path
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
        """Immediately stop playback and clear pending audio."""
        # Clear queue
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

        if sd is not None:
            try:
                sd.stop()
            except Exception as exc:
                logger.warning(f"Error stopping sounddevice: {exc}")
        self._is_playing = False

    @property
    def is_playing(self) -> bool:
        """Check if audio is currently playing or queued for output."""
        return self._is_playing or not self._queue.empty()
