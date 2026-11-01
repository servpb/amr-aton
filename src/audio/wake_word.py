"""Offline Wake Word detection engine for 'Aton' using Vosk and openWakeWord."""

import json
import logging
import time
from typing import Any, Optional
import numpy as np

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
        """Initialize local Vosk offline speech recognizer for Portuguese."""
        # 1. Initialize Vosk offline speech recognizer for Portuguese
        if VoskModel is not None:
            try:
                if vosk is not None:
                    vosk.SetLogLevel(-1)
                self._vosk_model = VoskModel(lang="pt")
                self._vosk_rec = KaldiRecognizer(self._vosk_model, 16000)
                if hasattr(self._vosk_rec, "SetWords"):
                    try:
                        self._vosk_rec.SetWords(True)
                    except Exception:
                        pass
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

        # 1. Check Vosk offline recognizer for exact spoken keyword ("aton")
        if self._vosk_rec is not None:
            try:
                text = ""
                is_final = False
                if self._vosk_rec.AcceptWaveform(pcm_bytes):
                    res = json.loads(self._vosk_rec.Result())
                    text = res.get("text", "").lower().strip()
                    is_final = True
                else:
                    partial = json.loads(self._vosk_rec.PartialResult())
                    text = partial.get("partial", "").lower().strip()

                if text:
                    if is_final:
                        logger.info(f"🎧 [Escuta Offline] Transcrito: '{text}'")

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
                        )
                        if self.wake_word in ("aton", "amr")
                        else ()
                    )

                    # Variantes fonéticas secundárias (aceitas EXCLUSIVAMENTE em resultado final consolidado,
                    # por correspondência exata do texto com a palavra isolada ou saudação explícita).
                    # Jamais aceitas em parciais nem por presença avulsa em frases maiores.
                    acoustic_exact_final_phrases = (
                        {
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

                    if is_final:
                        # Resultado consolidado pelo Vosk ao término da locução
                        has_wake_token = any(w in strict_wake_tokens for w in words_in_text)
                        has_direct_phrase = any(p in text for p in strict_direct_phrases)

                        # Rejeita discursos longos (ex: TV, rádio ou conversas com >6 palavras)
                        if (has_wake_token or has_direct_phrase) and len(words_in_text) <= 6:
                            should_trigger = True
                        elif text in acoustic_exact_final_phrases:
                            # Variantes fonéticas aceitas unicamente por correspondência exata
                            should_trigger = True
                    else:
                        # Resultado parcial transitório: critério estrito e determinístico
                        # Só dispara se o texto parcial for estritamente a palavra-chave canônica ou saudação direta oficial
                        # Variantes como 'tom', 'atom' e 'átom' são 100% rejeitadas em parciais
                        if text in strict_wake_tokens or text in strict_direct_phrases:
                            should_trigger = True

                    if should_trigger:
                        logger.info(
                            f"Wake word 'Aton' detected via offline speech recognition! Spoken: '{text}' (final={is_final})"
                        )
                        self._last_trigger_time = now
                        self._vosk_rec.Reset()
                        return True
            except Exception as e:
                logger.debug(f"Vosk keyword processing error: {e}")

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
        """Detect spoken stop command ('pare' / 'parar') locally to immediately stop listening.

        Args:
            pcm_bytes: Raw 16-bit signed PCM audio bytes.

        Returns:
            True if the user spoke 'pare' or 'parar'.
        """
        if not pcm_bytes or self._vosk_rec is None:
            return False

        try:
            text = ""
            if self._vosk_rec.AcceptWaveform(pcm_bytes):
                res = json.loads(self._vosk_rec.Result())
                text = res.get("text", "").lower().strip()
            else:
                partial = json.loads(self._vosk_rec.PartialResult())
                text = partial.get("partial", "").lower().strip()

            if text:
                words = set(text.split())
                stop_tokens = {"pare", "parar"}
                stop_phrases = (
                    "aton pare",
                    "aton para",
                    "aton parar",
                    "pare aton",
                    "para aton",
                    "pare de escutar",
                    "parar de escutar",
                    "pode parar",
                )
                if (words & stop_tokens) or text == "para" or any(p in text for p in stop_phrases):
                    logger.info(f"Stop command ('Pare') detected offline! Spoken: '{text}'")
                    self._last_trigger_time = time.time()
                    self._vosk_rec.Reset()
                    return True
        except Exception as e:
            logger.debug(f"Vosk stop command processing error: {e}")

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

    def reset(self) -> None:
        """Reset recognizer state buffer."""
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
