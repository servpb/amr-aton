"""Conservative local speech-onset gate, independent of command transcription."""
class LocalBargeInGate:
    def __init__(self, frames_required=8, probability=.65, minimum_rms=100, warmup_seconds=.5):
        self.frames_required=frames_required
        self.probability=probability
        self.minimum_rms=minimum_rms
        self.warmup_seconds=warmup_seconds
        self.reset()

    def reset(self):
        self._playing=False
        self._started=0.0
        self._consecutive=0
        self._fired=False

    def update(self, *, playing, probability, rms, now):
        if not playing:
            self.reset()
            return False
        if not self._playing:
            self._playing=True
            self._started=now
        if self._fired or now-self._started < self.warmup_seconds:
            return False
        if probability >= self.probability and rms >= self.minimum_rms:
            self._consecutive+=1
        else:
            self._consecutive=0
        if self._consecutive < self.frames_required:
            return False
        self._fired=True
        return True
