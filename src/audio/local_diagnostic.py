"""Explicit, bounded local recording. Disabled until the user starts a test."""
import json
from pathlib import Path
import threading
import time
import uuid
import wave
import numpy as np


class LocalAudioDiagnostic:
    rate = 16000
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self._lock = threading.Lock()
        self._active = False
        self._ready = False
        self._blocks = []
        self._samples = 0
        self._limit = 0
        self._deadline = 0.0
        self.started_at = None

    def start(self, seconds=30):
        if not 1 <= seconds <= 30:
            raise ValueError('O diagnóstico deve durar de 1 a 30 segundos')
        with self._lock:
            if self._active or self._ready:
                raise RuntimeError('Há um teste em andamento ou aguardando salvamento')
            self._blocks = []
            self._samples = 0
            self._limit = round(seconds*self.rate)
            self.started_at = time.time()
            self._deadline = self.clock()+seconds
            self._active = True

    def push(self, raw, clean, reference):
        with self._lock:
            if not self._active:
                return
            if self.clock() >= self._deadline:
                self._active = False
                self._ready = True
                return
            length = min(len(raw),len(clean),len(reference),self._limit-self._samples)
            if length:
                block = np.column_stack((raw[:length],clean[:length],reference[:length])).astype('<i2')
                self._blocks.append(block)
                self._samples += length
            if self._samples >= self._limit:
                self._active = False
                self._ready = True

    @property
    def ready(self):
        with self._lock:
            if self._active and self.clock() >= self._deadline:
                self._active = False
                self._ready = True
            return self._ready

    def save(self, directory, metadata=None):
        with self._lock:
            if self._active or not self._ready:
                raise RuntimeError('Teste não concluído')
            data = np.concatenate(self._blocks) if self._blocks else np.empty((0,3),dtype='<i2')
            count = self._samples
            started = self.started_at
        directory=Path(directory)
        directory.mkdir(parents=True,exist_ok=True)
        path=directory/('aec_test_'+uuid.uuid4().hex[:12]+'.wav')
        temporary=path.with_suffix('.tmp')
        with wave.open(str(temporary),'wb') as output:
            output.setnchannels(3)
            output.setsampwidth(2)
            output.setframerate(self.rate)
            output.writeframes(data.tobytes())
        temporary.replace(path)
        info={'started_at_unix':started,'sample_rate':self.rate,'samples':count,
              'duration_seconds':count/self.rate,
              'channels':['microphone_raw','microphone_processed','speaker_reference'],
              'local_only':True,'metadata':metadata or {}}
        path.with_suffix('.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
        with self._lock:
            self._blocks.clear()
            self._ready=False
        return path
