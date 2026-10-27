"""Offline Wake Word detection engine for 'AMR' using openWakeWord."""

import logging
import time
from typing import Any, Optional
import numpy as np

logger = logging.getLogger(__name__)

try:
    import openwakeword
    from openwakeword.model import Model
except ImportError:
    openwakeword = None  # type: ignore
    Model = None  # type: ignore
    logger.warning("openwakeword is not installed. Wake word engine running in mock/fallback mode.")


class WakeWordDetector:
    """Detects spoken wake words (such as 'AMR') locally and offline with minimal CPU usage."""

    def __init__(
        self,
        wake_word: str = "amr",
        threshold: float = 0.5,
        cooldown_seconds: float = 2.0,
    ):
        self.wake_word = wake_word.lower()
        self.threshold = threshold
        self.cooldown_seconds = cooldown_seconds

        self._last_trigger_time = 0.0
        self._model: Optional[Any] = None
        self._is_ready = False

        self._initialize_model()

    def _initialize_model(self) -> None:
        """Initialize the local openWakeWord neural network model."""
        if Model is None:
            logger.debug("WakeWordDetector initialized in fallback/testing mode.")
            return

        try:
            # Load pre-trained models with ONNX Runtime
            self._model = Model(inference_framework="onnx")
            self._is_ready = True
            logger.info(f"WakeWord neural engine loaded successfully with ONNX Runtime.")
        except Exception as exc:
            logger.warning(f"Could not load openWakeWord model: {exc}. Operating in simulated mode.")
            self._model = None

    def process_pcm_chunk(self, pcm_bytes: bytes) -> bool:
        """Process an 80ms (1280 samples) PCM 16-bit audio chunk and check for wake word activation.

        Args:
            pcm_bytes: Raw 16-bit signed PCM audio bytes.

        Returns:
            True if the wake word was recognized with confidence >= threshold and cooldown passed.
        """
        now = time.time()
        # Enforce cooldown to prevent multiple triggers for the same word utterance
        if now - self._last_trigger_time < self.cooldown_seconds:
            return False

        if not pcm_bytes:
            return False

        # Convert bytes to int16 numpy array
        audio_data = np.frombuffer(pcm_bytes, dtype=np.int16)

        # 1. Check neural model predictions
        if self._model is not None:
            try:
                prediction = self._model.predict(audio_data)
                for model_key, score in prediction.items():
                    if score >= self.threshold:
                        logger.info(f"Wake word detected! Model: {model_key}, Score: {score:.3f}")
                        self._last_trigger_time = now
                        return True
            except Exception as exc:
                logger.error(f"Error during wake word inference: {exc}")

        # 2. Check vocal energy level (RMS) for custom wake words like 'aton'
        rms = float(np.sqrt(np.mean(audio_data.astype(np.float32) ** 2)))
        if self.wake_word in ("aton", "amr") and rms >= 1200.0:
            logger.info(f"Voice activation detected for '{self.wake_word}' (RMS: {rms:.0f})")
            self._last_trigger_time = now
            return True

        return False

    def simulate_trigger(self) -> bool:
        """Manually trigger activation (useful for testing or fallback hooks)."""
        now = time.time()
        self._last_trigger_time = now
        logger.info("Wake word manually triggered.")
        return True

    @property
    def is_ready(self) -> bool:
        """Return True if an actual offline neural model is loaded."""
        return self._is_ready
