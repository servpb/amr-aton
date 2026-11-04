"""Constrained local stopping vocabulary. Includes unknown and negative alternatives."""
import json
STOP_COMMANDS = {'pare', 'parar', 'para', 'pode parar', 'pare de escutar',
    'parar de escutar', 'pare de falar', 'parar de falar', 'encerre a conversa',
    'encerrar a conversa', 'termine a conversa', 'encerrar conversa',
    'atom pare', 'eaton pare', 'pare atom', 'pare eaton'}
DISTRACTORS = {'não pare', 'não parar', 'não para', 'não encerre a conversa',
    'ele disse pare', 'a palavra pare', 'como parar', 'continuar', 'continue',
    'bom', 'pão', 'dom', 'sim', 'não'}


def build_stop_recognizer(model, factory, sample_rate):
    def supported(phrase):
        return all(model.vosk_model_find_word(word) >= 0 for word in phrase.split())
    commands = {p for p in STOP_COMMANDS if supported(p)}
    if not {'pare', 'parar'} & commands:
        raise ValueError('Stop vocabulary unavailable')
    phrases = sorted(commands | {p for p in DISTRACTORS if supported(p)}) + ['[unk]']
    recognizer = factory(model, sample_rate, json.dumps(phrases, ensure_ascii=False))
    recognizer.SetWords(True)
    return recognizer
