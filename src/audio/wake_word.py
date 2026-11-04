"""Offline Wake Word detection engine for 'Aton' using Vosk and openWakeWord."""

import json
import logging
import time
from typing import Any, Optional
import numpy as np
from src.config import settings

logger = logging.getLogger(__name__)

openwakeword = None  # type: ignore
Model = None  # type: ignore

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
        sample_rate: int = 16000,
    ):
        self.sample_rate = sample_rate
        self._diagnostics_until = time.monotonic() + 120 if settings.wake_diagnostics else 0.0
        self.last_rms = 0.0
        self.processed_chunks = 0
        self.accepted_count = 0
        self.last_decision = "no_audio"
        self.wake_word = wake_word.lower()
        self.threshold = threshold
        self.cooldown_seconds = cooldown_seconds

        self._last_trigger_time = 0.0
        self._last_partial_text = ""
        self._model: Optional[Any] = None
        self._vosk_model: Optional[Any] = None
        self._vosk_rec: Optional[Any] = None
        self._comparison = None
        self._stop_rec = None
        self._stop_grammar_active = False
        self.stop_processed_chunks = 0
        self._last_stop_debug = ""
        self._stop_partial = ""
        self._stop_partial_since = 0.0
        self._directed = None
        self._is_ready = False

        self._initialize_model()

    def _initialize_model(self) -> None:
        """Initialize local Vosk offline speech recognizer for Portuguese."""
        # 1. Initialize Vosk offline speech recognizer for Portuguese
        if VoskModel is not None:
            try:
                if vosk is not None:
                    vosk.SetLogLevel(-1)
                self._vosk_model = VoskModel(lang="pt")
                self._vosk_rec = KaldiRecognizer(self._vosk_model, self.sample_rate)
                self._stop_rec = KaldiRecognizer(self._vosk_model, self.sample_rate)
                if settings.wake_directed_enabled:
                    try:
                        from src.audio.stop_commands import build_stop_recognizer
                        self._stop_rec = build_stop_recognizer(self._vosk_model, KaldiRecognizer, self.sample_rate)
                        self._stop_grammar_active = True
                        logger.info('[VOICE_STOP] constrained_recognizer_enabled=true')
                    except Exception as exc:
                        logger.warning('[VOICE_STOP] constrained unavailable, general retained: %s', type(exc).__name__)
                if hasattr(self._vosk_rec, "SetWords"):
                    try:
                        self._vosk_rec.SetWords(True)
                    except Exception:
                        pass
                if settings.wake_directed_enabled:
                    try:
                        from src.audio.wake_comparison import VoskWakeComparison
                        self._directed = VoskWakeComparison(self._vosk_model, KaldiRecognizer, self.sample_rate, shadow_only=False)
                        logger.info('[DIRECTED_WAKE] experimental_enabled=true')
                    except Exception as exc:
                        self._directed = None
                        logger.warning('[DIRECTED_WAKE] unavailable, original detector retained: %s', type(exc).__name__)
                self._is_ready = True
                logger.info("Vosk offline speech recognition engine loaded successfully for 'aton'.")
            except Exception as e:
                logger.warning(f"Could not load Vosk Portuguese model: {e}")
                self._vosk_rec = None

    def process_pcm_chunk(self, pcm_bytes: bytes) -> bool:
        """Process an 80ms (1280 samples) PCM 16-bit audio chunk and check for wake word activation.

        Args:
            pcm_bytes: Raw 16-bit signed PCM audio bytes.

        Returns:
            True if the wake word ('Aton') was recognized and cooldown passed.
        """
        now = time.time()
        # Enforce cooldown to prevent multiple triggers for the same word utterance
        if now - self._last_trigger_time < self.cooldown_seconds:
            return False

        if not pcm_bytes:
            return False

        self.processed_chunks += 1
        if self._comparison is not None and time.monotonic() < self._diagnostics_until:
            try:
                self._comparison.process(pcm_bytes)
            except Exception as exc:
                logger.warning('[WAKE_COMPARE] disabled error=%s', type(exc).__name__)
                self._comparison = None
        if self._directed is not None:
            try:
                data = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32)
                self.last_rms = float(np.sqrt(np.mean(data ** 2))) if len(data) else 0.0
                observation = self._directed.process(pcm_bytes, diagnostics=time.monotonic() < self._diagnostics_until)
                if observation is None:
                    return False
                self.last_decision = 'directed_' + observation['reason']
                if not observation['candidate']:
                    return False
                self.accepted_count += 1
                self._last_trigger_time = now
                self.last_decision = 'accepted_directed_final'
                logger.info('[VOICE_WAKE] accepted detector=directed final=true')
                self.reset()
                return True
            except Exception as exc:
                self._directed = None
                logger.warning('[DIRECTED_WAKE] error=%s, returning to original detector', type(exc).__name__)
        # 1. Check Vosk offline recognizer for exact spoken keyword ("aton")
        if self._vosk_rec is not None:
            try:
                text = ""
                is_final = False
                audio_data = np.frombuffer(pcm_bytes, dtype=np.int16)
                rms = float(np.sqrt(np.mean(audio_data.astype(np.float32) ** 2))) if len(audio_data) > 0 else 0.0

                self.last_rms = rms

                if self._vosk_rec.AcceptWaveform(pcm_bytes):
                    res = json.loads(self._vosk_rec.Result())
                    text = res.get("text", "").lower().strip()
                    is_final = True
                else:
                    partial = json.loads(self._vosk_rec.PartialResult())
                    text = partial.get("partial", "").lower().strip()

                if text:
                    if is_final:
                        self._last_partial_text = ""
                        if time.monotonic() < self._diagnostics_until:
                            logger.info("[VOICE_DIAGNOSTIC] final=%r rms=%.0f", text, rms)
                    elif text != self._last_partial_text:
                        self._last_partial_text = text
                        if time.monotonic() < self._diagnostics_until:
                            logger.info("[VOICE_DIAGNOSTIC] partial=%r rms=%.0f", text, rms)

                    strict_wake_tokens = (
                        {
                            "aton",
                            "áton",
                            "atón",
                            "atão",
                            "atao",
                        }
                        if self.wake_word in ("aton", "amr")
                        else {self.wake_word}
                    )
                    strict_direct_phrases = (
                        (
                            "oi aton",
                            "olá aton",
                            "ei aton",
                            "ok aton",
                            "opa aton",
                            "alô aton",
                            "oi a tão",
                            "olá a tão",
                            "ei a tão",
                            "ok a tão",
                            "opa a tão",
                            "alô a tão",
                            "olá tão",
                            "oi tão",
                            "ei tão",
                            "ok tão",
                            "opa tão",
                            "alô tão",
                        )
                        if self.wake_word in ("aton", "amr")
                        else ()
                    )

                    # Variantes fonéticas secundárias (aceitas EXCLUSIVAMENTE em resultado final consolidado,
                    # por correspondência exata do texto com a palavra isolada ou saudação explícita).
                    # Jamais aceitas em parciais nem por presença avulsa em frases maiores.
                    acoustic_exact_final_phrases = (
                        {
                            "a tão",
                            "eaton",
                            "oi eaton",
                            "olá eaton",
                            "ei eaton",
                            "tom",
                            "oi tom",
                            "ei tom",
                            "olá tom",
                            "ok tom",
                            "opa tom",
                            "alô tom",
                            "atom",
                            "oi atom",
                            "ei atom",
                            "olá atom",
                            "ok atom",
                            "opa atom",
                            "alô atom",
                            "átom",
                            "oi átom",
                            "ei átom",
                            "olá átom",
                            "ok átom",
                            "opa átom",
                            "alô átom",
                        }
                        if self.wake_word in ("aton", "amr")
                        else set()
                    )

                    words_in_text = text.split()
                    should_trigger = False

                    canonical_greetings = tuple(
                        f"{greeting} {token}"
                        for greeting in ("oi", "olá", "ei", "ok", "opa", "alô")
                        for token in strict_wake_tokens
                    )
                    # Ambiguous phonetic forms require exact FINAL text, never substrings.
                    acoustic_finals = acoustic_exact_final_phrases | set(strict_direct_phrases)
                    if is_final:
                        starts_canonical = words_in_text[0] in strict_wake_tokens or any(
                            text == phrase or text.startswith(phrase + " ")
                            for phrase in canonical_greetings
                        )
                        should_trigger = (starts_canonical and len(words_in_text) <= 6) or text in acoustic_finals
                    else:
                        should_trigger = text in strict_wake_tokens or text in canonical_greetings

                    self.last_decision = "accepted_final" if should_trigger and is_final else (
                        "accepted_partial" if should_trigger else "rejected_final" if is_final else "awaiting_final"
                    )
                    if should_trigger:
                        self.accepted_count += 1
                        logger.info("[VOICE_WAKE] accepted final=%s words=%d", is_final, len(words_in_text))
                        self._last_trigger_time = now
                        self._vosk_rec.Reset()
                        return True
            except Exception as e:
                self.last_decision = "recognizer_error"
                logger.warning("[VOICE_WAKE] recognizer error: %s", type(e).__name__)

        # 2. Check custom openWakeWord model ONLY if a model matching self.wake_word is loaded
        if self._model is not None:
            try:
                audio_data = np.frombuffer(pcm_bytes, dtype=np.int16)
                prediction = self._model.predict(audio_data)
                for model_key, score in prediction.items():
                    if self.wake_word in model_key.lower() and score >= self.threshold:
                        logger.info(f"Wake word detected via openWakeWord! Model: {model_key}, Score: {score:.3f}")
                        self._last_trigger_time = now
                        return True
            except Exception as exc:
                logger.error(f"Error during wake word inference: {exc}")

        return False

    def detect_stop_command(self, pcm_bytes: bytes) -> bool:
        """Feed every conversational chunk, including silence, to a separate recognizer."""
        rec = self._stop_rec if self._stop_rec is not None else self._vosk_rec
        if not pcm_bytes or rec is None:
            return False
        self.stop_processed_chunks += 1
        try:
            final = rec.AcceptWaveform(pcm_bytes)
            result = json.loads(rec.Result() if final else rec.PartialResult())
            text = ' '.join(str(result.get('text' if final else 'partial', '')).lower().split())
            if time.monotonic() < self._diagnostics_until and text and (final or text != self._last_stop_debug):
                self._last_stop_debug = text
                logger.info('[STOP_DIAGNOSTIC] final=%s text=%r', final, text)
            from src.audio.stop_commands import STOP_COMMANDS
            commands = STOP_COMMANDS | {'aton pare', 'aton para', 'aton parar', 'pare aton', 'para aton'}
            if text not in commands:
                self._stop_partial = ''
                self._stop_partial_since = 0.0
                return False
            if final and self._stop_grammar_active:
                import math
                words = result.get('result', [])
                if not words:
                    return False
                confidence = [float(w.get('conf', -1)) for w in words]
                if not all(math.isfinite(v) and v >= 0.80 for v in confidence):
                    return False
            if not final:
                # Partial hypotheses cannot end a session. Local speech-onset handles
                # fast playback pause while final recognition/tool intent decides sleep.
                return False
            logger.info('[VOICE_STOP] accepted final=%s', final)
            self._last_trigger_time = time.time()
            rec.Reset()
            self._stop_partial = ''
            self._stop_partial_since = 0.0
            return True
        except Exception as exc:
            logger.warning('[VOICE_STOP] recognizer error=%s', type(exc).__name__)
            return False

    def detect_confirmation_intent(self, pcm_bytes: bytes) -> Optional[str]:
        """Evaluate a final spoken utterance for explicit confirmation ('affirm') or cancellation ('cancel').

        Strict anti-false-positive rules:
        - Evaluates ONLY finalized Vosk utterances (`AcceptWaveform == True`), never partial hypotheses.
        - Rejects utterances longer than 5 words or containing hesitation/contradiction words.
        - Checks per-word confidence >= 0.80 when provided by Vosk.
        - Cancellation words always take precedence over affirmative words.

        Returns:
            'affirm', 'cancel', or None.
        """
        if not pcm_bytes or self._vosk_rec is None:
            return None

        try:
            if not self._vosk_rec.AcceptWaveform(pcm_bytes):
                return None

            res = json.loads(self._vosk_rec.Result() or "{}")
            text = str(res.get("text", "")).lower().strip()
            if not text:
                return None

            tokens = [t.strip(".,!?;:\"'") for t in text.split() if t.strip(".,!?;:\"'")]
            if not tokens or len(tokens) > 5:
                return None

            doubt_tokens = {
                "talvez",
                "acho",
                "espera",
                "espere",
                "mas",
                "porem",
                "porém",
                "duvida",
                "dúvida",
                "ainda",
                "calma",
                "depois",
            }
            cancel_tokens = {
                "nao",
                "não",
                "cancela",
                "cancelar",
                "cancele",
                "nunca",
                "jamais",
                "negativo",
                "abortar",
                "desistir",
                "pare",
                "parar",
            }
            affirm_tokens = {
                "sim",
                "confirmo",
                "confirmar",
                "confirmado",
                "autorizo",
                "autorizar",
                "autorizado",
                "pode",
                "prosseguir",
            }

            token_set = set(tokens)
            # Cancellation always wins immediately
            if token_set & cancel_tokens:
                logger.info(f"🛑 Cancelamento verbal de confirmação detectado pelo Vosk: '{text}'")
                self._vosk_rec.Reset()
                return "cancel"

            # Reject if any doubt/contradiction word is present
            if token_set & doubt_tokens:
                logger.info(f"⚠️ Resposta ambígua ignorada para confirmação: '{text}'")
                return None

            if token_set & affirm_tokens:
                word_entries = res.get("result", [])
                if isinstance(word_entries, list) and word_entries:
                    for w_info in word_entries:
                        if isinstance(w_info, dict):
                            w_str = str(w_info.get("word", "")).lower().strip()
                            conf = float(w_info.get("conf", 1.0))
                            if w_str in affirm_tokens and conf < 0.80:
                                logger.info(
                                    f"⚠️ Confiança insuficiente ({conf:.2f} < 0.80) na palavra '{w_str}' em '{text}'."
                                )
                                return None

                logger.info(f"✅ Confirmação verbal ('{text}') validada pelo Vosk.")
                self._vosk_rec.Reset()
                return "affirm"
        except Exception as exc:
            logger.debug(f"Vosk confirmation intent processing error: {exc}")

        return None

    def start_diagnostics(self, seconds: float = 60) -> None:
        """User-triggered transcription diagnostics; no audio recording."""
        self._diagnostics_until = time.monotonic() + min(60, max(1, seconds))
        self.reset()
        try:
            if self._vosk_model is not None and KaldiRecognizer is not None:
                from src.audio.wake_comparison import VoskWakeComparison
                self._comparison = VoskWakeComparison(self._vosk_model, KaldiRecognizer, self.sample_rate)
        except Exception as exc:
            self._comparison = None
            logger.warning('[WAKE_COMPARE] unavailable error=%s', type(exc).__name__)
        logger.info("[VOICE_TEST] started duration_seconds=%.0f", min(60, max(1, seconds)))

    def reset(self, include_stop: bool = True) -> None:
        """Reset wake state; echo drainage must not cut the separate stop stream."""
        if include_stop:
            self._stop_partial = ''
            self._stop_partial_since = 0.0
            if self._stop_rec is not None:
                self._stop_rec.Reset()
        self._last_partial_text = ""
        if self._comparison is not None:
            self._comparison.reset()
        if self._directed is not None:
            self._directed.reset()
        if self._vosk_rec is not None:
            try:
                self._vosk_rec.Reset()
            except Exception:
                pass

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
