"""Constrained Vosk observations; activation policy belongs to WakeWordDetector."""
import json
import logging
import math
logger = logging.getLogger(__name__)

TARGETS = {'atom', 'eaton', 'tom', 'a tom', 'a tão', 'oi atom', 'oi eaton',
           'olá atom', 'olá eaton', 'ei atom', 'ei eaton', 'oi tom', 'olá tom'}
DISTRACTORS = {'pão', 'dom', 'bom', 'oi', 'não', 'sim', 'pare', 'o', 'a', 'tão'}


def evaluate_candidate(result, allowed):
    text = str(result.get('text', '')).strip().lower()
    if text not in allowed or '[unk]' in text:
        return False, 'not_exact_target'
    words = result.get('result', [])
    if not words or [w.get('word') for w in words] != text.split():
        return False, 'missing_word_evidence'
    try:
        values = [float(w.get('conf', -1)) for w in words]
        duration = float(words[-1]['end']) - float(words[0]['start'])
        if not all(math.isfinite(v) and v >= .80 for v in values):
            return False, 'low_confidence'
        if not math.isfinite(duration) or not .18 <= duration <= 3.0:
            return False, 'duration_outside_window'
    except (ValueError, TypeError, KeyError):
        return False, 'invalid_word_evidence'
    return True, 'candidate_only'


class VoskWakeComparison:
    def __init__(self, model, factory, sample_rate, shadow_only=True):
        self.shadow_only = shadow_only
        def supported(phrase):
            return all(model.vosk_model_find_word(word) >= 0 for word in phrase.split())
        self.allowed = {phrase for phrase in TARGETS if supported(phrase)}
        if not self.allowed:
            raise ValueError('No supported acoustic targets')
        grammar = sorted(self.allowed | {p for p in DISTRACTORS if supported(p)}) + ['[unk]']
        self.recognizer = factory(model, sample_rate, json.dumps(grammar, ensure_ascii=False))
        self.recognizer.SetWords(True)
        self.final_count = 0
        self.candidate_count = 0
        self._last_partial = ''
        logger.info('[WAKE_COMPARE] initialized shadow_only=%s target_phrases=%d', self.shadow_only, len(self.allowed))

    def process(self, pcm, diagnostics=True):
        # Results are observations, not commands. No wake callback exists here.
        if not self.recognizer.AcceptWaveform(pcm):
            partial = str(json.loads(self.recognizer.PartialResult()).get('partial', ''))
            if partial and partial != self._last_partial:
                self._last_partial = partial
                if diagnostics:
                    logger.info('[WAKE_COMPARE] partial=%r shadow_only=%s', partial, self.shadow_only)
            return None
        result = json.loads(self.recognizer.Result())
        self._last_partial = ''
        text = str(result.get('text', ''))
        if not text:
            return None
        candidate, reason = evaluate_candidate(result, self.allowed)
        self.final_count += 1
        self.candidate_count += int(candidate)
        if diagnostics:
            logger.info('[WAKE_COMPARE] final=%r candidate=%s reason=%s shadow_only=%s', text, candidate, reason, self.shadow_only)
        return {'text': text, 'candidate': candidate, 'reason': reason}

    def reset(self):
        self.recognizer.Reset()
        self._last_partial = ''
