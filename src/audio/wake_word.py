"""Offline Wake Word detection engine for 'Aton' using Vosk and openWakeWord."""

import json
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
    logger.debug("openwakeword is not installed.")

try:
    import vosk
    from vosk import Model as VoskModel, KaldiRecognizer
except ImportError:
    vosk = None  # type: ignore
    VoskModel = None  # type: ignore
    KaldiRecognizer = None  # type: ignore
    logger.debug("vosk is not installed.")


class WakeWordDetector:
    """Detects spoken wake words (such as 'aton') locally and offline with minimal CPU usage."""

    def __init__(
        self,
        wake_word: str = "aton",
        threshold: float = 0.5,
        cooldown_seconds: float = 2.0,
    ):
        self.wake_word = wake_word.lower()
        self.threshold = threshold
        self.cooldown_seconds = cooldown_seconds

        self._last_trigger_time = 0.0
        self._model: Optional[Any] = None
        self._vosk_model: Optional[Any] = None
        self._vosk_rec: Optional[Any] = None
        self._is_ready = False

        self._initialize_model()

    def _initialize_model(self) -> None:
        """Initialize local Vosk and openWakeWord engines for offline detection."""
        # 1. Initialize Vosk offline speech recognizer for Portuguese
        if VoskModel is not None:
            try:
                if vosk is not None:
                    vosk.SetLogLevel(-1)
                self._vosk_model = VoskModel(lang="pt")
                self._vosk_rec = KaldiRecognizer(self._vosk_model, 16000)
                self._is_ready = True
                logger.info("Vosk offline speech recognition engine loaded successfully for 'aton'.")
            except Exception as e:
                logger.warning(f"Could not load Vosk Portuguese model: {e}")
                self._vosk_rec = None

        # 2. Initialize openWakeWord neural network if available
        if Model is not None:
            try:
                self._model = Model(inference_framework="onnx")
                self._is_ready = True
                logger.info("openWakeWord neural engine loaded successfully with ONNX Runtime.")
            except Exception as exc:
                logger.debug(f"Could not load openWakeWord model: {exc}")
                self._model = None

    def process_pcm_chunk(self, pcm_bytes: bytes) -> bool:
        """Process an 80ms (1280 samples) PCM 16-bit audio chunk and check for wake word activation.

        Args:
            pcm_bytes: Raw 16-bit signed PCM audio bytes.

        Returns:
            True if the wake word was recognized and cooldown passed.
        """
        now = time.time()
        # Enforce cooldown to prevent multiple triggers for the same word utterance
        if now - self._last_trigger_time < self.cooldown_seconds:
            return False

        if not pcm_bytes:
            return False

        # Convert bytes to int16 numpy array
        audio_data = np.frombuffer(pcm_bytes, dtype=np.int16)

        # 1. Check Vosk offline recognizer for exact spoken keyword ("aton")
        if self._vosk_rec is not None:
            try:
                text = ""
                if self._vosk_rec.AcceptWaveform(pcm_bytes):
                    res = json.loads(self._vosk_rec.Result())
                    text = res.get("text", "").lower()
                else:
                    partial = json.loads(self._vosk_rec.PartialResult())
                    text = partial.get("partial", "").lower()

                if text:
                    wake_tokens = (
                        {"aton", "áton", "atón", "ayrton", "elton", "átomo", "amr"}
                        if self.wake_word in ("aton", "amr")
                        else {self.wake_word}
                    )
                    words_in_text = set(text.split())
                    if words_in_text & wake_tokens:
                        logger.info(f"Wake word detected via offline speech recognition! Spoken word: '{text}'")
                        self._last_trigger_time = now
                        self._vosk_rec.Reset()
                        return True
            except Exception as e:
                logger.debug(f"Vosk keyword processing error: {e}")

        # 2. Check openWakeWord neural predictions if configured
        if self._model is not None:
            try:
                prediction = self._model.predict(audio_data)
                for model_key, score in prediction.items():
                    if score >= self.threshold:
                        logger.info(f"Wake word detected via openWakeWord! Model: {model_key}, Score: {score:.3f}")
                        self._last_trigger_time = now
                        return True
            except Exception as exc:
                logger.error(f"Error during wake word inference: {exc}")

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
