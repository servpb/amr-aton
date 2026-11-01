"""Audio recorder for capturing microphone input in real time."""

import asyncio
import logging
import queue
from typing import Any, AsyncGenerator, Optional
import numpy as np

logger = logging.getLogger(__name__)

try:
    import sounddevice as sd
except ImportError:
    sd = None  # type: ignore


class AudioRecorder:
    """Captures audio from the microphone in PCM chunks suitable for Gemini Live and wake word engines."""

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        chunk_size: int = 1280,  # 80ms at 16kHz, ideal chunk size for openWakeWord & Gemini
        device_index: Optional[int] = None,
    ):
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_size = chunk_size
        self.device_index = device_index

        self._queue: queue.Queue[bytes] = queue.Queue()
        self._stream: Optional[Any] = None
        self._is_recording = False
        self._last_callback_time: float = 0.0

    def _audio_callback(self, indata: np.ndarray, frames: int, time_info: Any, status: Any) -> None:
        """Callback invoked by sounddevice for each new block of audio samples."""
        if status:
            logger.debug(f"Audio input status: {status}")
        import time
        self._last_callback_time = time.time()
        # Ensure 16-bit PCM byte representation
        pcm_bytes = indata.astype(np.int16).tobytes()
        self._queue.put(pcm_bytes)

    def start(self) -> None:
        """Start recording from the selected audio input device."""
        if self._is_recording:
            return

        if sd is None:
            logger.warning("Cannot start recording: sounddevice is not available.")
            return

        try:
            import time
            self._last_callback_time = time.time()
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype="int16",
                blocksize=self.chunk_size,
                device=self.device_index,
                callback=self._audio_callback,
            )
            self._stream.start()
            self._is_recording = True
            logger.info("Microphone recording started.")
        except Exception as exc:
            logger.error(f"Failed to open microphone input stream: {exc}")
            raise

    def restart(self, reinit_portaudio: bool = False) -> None:
        """Restart microphone stream. Only re-initializes PortAudio if explicitly requested or if soft restart fails."""
        logger.info(f"Restarting microphone stream (reinit_portaudio={reinit_portaudio})...")
        self.stop()
        if reinit_portaudio and sd is not None:
            try:
                if hasattr(sd, "_terminate") and hasattr(sd, "_initialize"):
                    sd._terminate()
                    sd._initialize()
            except Exception as exc:
                logger.debug(f"PortAudio re-init notice: {exc}")
        self.start()

    def is_healthy(self) -> bool:
        """Return True if stream is active and receiving audio callbacks from the OS driver."""
        if not self._is_recording or self._stream is None:
            return False
        import time
        if hasattr(self._stream, "active"):
            try:
                if not self._stream.active:
                    return False
            except Exception:
                return False
        if self._last_callback_time > 0 and (time.time() - self._last_callback_time > 6.0):
            return False
        return True

    def stop(self) -> None:
        """Stop recording and release the audio stream."""
        if not self._is_recording:
            return

        self._is_recording = False
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as exc:
                logger.warning(f"Error while closing audio input stream: {exc}")
            finally:
                self._stream = None
        logger.info("Microphone recording stopped.")

    def read_chunk(self, timeout: float = 0.5) -> Optional[bytes]:
        """Read a single chunk of PCM bytes from the queue (blocking with timeout)."""
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def drain_available_chunks(self, first_chunk: bytes, max_extra_chunks: int = 4) -> bytes:
        """Coalesce immediately available queued chunks to prevent microphone buffer lag."""
        chunks = [first_chunk]
        # If queue accumulated an abnormal backlog (>20 chunks = 1.6s), drop oldest to stay real-time
        while self._queue.qsize() > 20:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

        for _ in range(max_extra_chunks):
            try:
                nxt = self._queue.get_nowait()
                if nxt:
                    chunks.append(nxt)
            except queue.Empty:
                break
        return b"".join(chunks)

    def clear_backlog(self, keep_latest: int = 1) -> int:
        """Drop accumulated backlog and keep only the latest real-time chunks.

        Returns the number of dropped chunks. Useful during background warm-up
        to ensure no stale audio is retained or processed later.
        """
        items = []
        while not self._queue.empty():
            try:
                items.append(self._queue.get_nowait())
            except queue.Empty:
                break

        dropped = 0
        if items:
            if keep_latest > 0:
                keep = items[-keep_latest:]
                dropped = len(items) - len(keep)
                for chunk in keep:
                    self._queue.put(chunk)
            else:
                dropped = len(items)
        return dropped

    def flush(self) -> None:
        """Clear all buffered audio chunks from the recording queue."""
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

    async def stream_audio(self) -> AsyncGenerator[bytes, None]:
        """Async generator yielding chunks of PCM audio as they arrive from the microphone."""
        loop = asyncio.get_running_loop()
        while self._is_recording:
            try:
                chunk = await loop.run_in_executor(None, self.read_chunk, 0.1)
                if chunk is not None:
                    yield chunk
            except Exception as exc:
                logger.error(f"Error in audio streaming loop: {exc}")
                break

    @property
    def is_recording(self) -> bool:
        """Check if recorder is currently running."""
        return self._is_recording
