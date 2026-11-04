"""Optional shared duplex stream with WebRTC AEC and nonblocking playback stop.

No recordings, cloud services, or speaker identity inference. Only Aton output
is the reference; external TV/audio is not cancelled by this engine.
"""
from collections import deque
import logging
import threading
import time
import numpy as np
from src.audio.player import AudioPlayer
from src.audio.recorder import AudioRecorder

logger = logging.getLogger(__name__)


class DuplexAecEngine:
    rate = 16000
    frame_size = 160  # WebRTC 10ms frames.

    def __init__(self, input_device=None, output_device=None, delay_ms=None, processor=None):
        self.input_device = input_device
        self.output_device = output_device
        self.delay_ms = delay_ms
        self._processor = processor
        self._stream = None
        self._lock = threading.Lock()
        self._output = deque()
        self._offset = 0
        self._queued_samples = 0
        self._capture = []
        self._play_until = 0.0
        self.error = None
        self.recorder = None
        self.frames_processed = 0
        self.status_events = 0
        self.raw_rms = 0.0
        self.clean_rms = 0.0
        self.reference_rms = 0.0
        from src.audio.local_diagnostic import LocalAudioDiagnostic
        self.diagnostic = LocalAudioDiagnostic()
        from src.audio.barge_in import LocalBargeInGate
        self._barge_gate = LocalBargeInGate()
        self._voice_detector = None
        self.barge_in_serial = 0
        self.user_speech_probability = 0.0

    def enqueue(self, samples):
        samples = np.asarray(samples,dtype=np.float32).reshape(-1)
        if not samples.size:
            return
        with self._lock:
            if self._queued_samples + len(samples) > self.rate * 120:
                raise RuntimeError('Fila de saída AEC excedeu 120 segundos')
            self._output.append(samples.copy())
            self._queued_samples += len(samples)

    def clear_output(self):
        # No stream writes or device close while holding this lock.
        with self._lock:
            self._output.clear()
            self._offset = 0
            self._queued_samples = 0
            self._play_until = 0.0

    def _render(self, count):
        out = np.zeros(count,dtype=np.float32)
        filled = 0
        with self._lock:
            while self._output and filled < count:
                first = self._output[0]
                length = min(count-filled,len(first)-self._offset)
                out[filled:filled+length] = first[self._offset:self._offset+length]
                self._offset += length
                self._queued_samples -= length
                filled += length
                if self._offset == len(first):
                    self._output.popleft()
                    self._offset = 0
            if filled:
                latency = self._stream.latency[1] if self._stream is not None else .05
                self._play_until = time.monotonic() + latency + count/self.rate
        return out

    def _callback(self, indata, outdata, frames, time_info, status):
        outdata.fill(0)
        if status:
            self.status_events += 1
        try:
            if frames != self.frame_size:
                raise ValueError('Tamanho de bloco duplex inesperado')
            rendered = self._render(frames)
            outdata[:,0] = rendered
            near = np.clip(np.asarray(indata[:,0])*32767,-32768,32767).astype(np.int16)
            far = np.clip(rendered*32767,-32768,32767).astype(np.int16)
            # These are the exact samples sent to this duplex output callback.
            clean = self._processor.process(near,far)
            try:
                self.diagnostic.push(near,clean,far)
            except Exception:
                # Recording failure must not interrupt normal audio processing.
                pass
            self.frames_processed += 1
            self.raw_rms = float(np.sqrt(np.mean(near.astype(np.float32)**2)))
            self.clean_rms = float(np.sqrt(np.mean(clean.astype(np.float32)**2)))
            self.reference_rms = float(np.sqrt(np.mean(far.astype(np.float32)**2)))
            if self._voice_detector is not None:
                self.user_speech_probability = float(self._voice_detector.process(clean))
                if self._barge_gate.update(playing=self.playing,
                        probability=self.user_speech_probability,rms=self.clean_rms,now=time.monotonic()):
                    self.barge_in_serial += 1
            self._capture.append(np.asarray(clean,dtype=np.int16).copy())
            if len(self._capture) == 8:
                block = np.concatenate(self._capture).reshape(-1,1)
                self._capture.clear()
                if self.recorder is not None and self.recorder._is_recording:
                    self.recorder._audio_callback(block,len(block),time_info,None)
        except Exception as exc:
            # Never pass raw self-echo to the conversational pipeline as a silent fallback.
            self.error = type(exc).__name__
            self._capture.clear()
            outdata.fill(0)

    def start(self):
        if self._stream is not None:
            self.close()
        import sounddevice as sd
        from pywebrtc_audio import AudioProcessor, VoiceDetector
        self.error = None
        self._capture.clear()
        self._voice_detector = VoiceDetector(sample_rate=self.rate)
        self._barge_gate.reset()
        self.barge_in_serial = 0
        self._processor = AudioProcessor(sample_rate=self.rate,echo_cancellation=True,
            noise_suppression=True,auto_gain_control=False,stream_delay_ms=0)
        stream = sd.Stream(samplerate=self.rate,blocksize=self.frame_size,channels=(1,1),
            dtype='float32',device=(self.input_device,self.output_device),latency='low',callback=self._callback)
        self._stream = stream
        try:
            delay = self.delay_ms
            if delay is None:
                delay = round(sum(stream.latency)*1000)
            self._processor.stream_delay_ms = max(0,min(500,int(delay)))
            stream.start()
            logger.info('[LOCAL_BARGE_IN] speech_onset_gate_active=true')
            logger.info('[AEC] shared_duplex_active=true rate=%d block_ms=10 delay_ms=%d',
                        self.rate,self._processor.stream_delay_ms)
        except Exception:
            self.close()
            raise

    def close(self):
        stream,self._stream = self._stream,None
        if stream is not None:
            try:
                stream.abort()
            finally:
                stream.close()
        self.clear_output()
        self._capture.clear()

    @property
    def playing(self):
        with self._lock:
            return self._queued_samples > 0 or time.monotonic() < self._play_until


class AecRecorder(AudioRecorder):
    def __init__(self, engine):
        super().__init__(sample_rate=engine.rate,device_index=engine.input_device)
        self.engine = engine
        engine.recorder = self

    def start(self):
        self._is_recording = True
        self._last_callback_time = 0.0
        self.received_chunks = 0
        try:
            self.engine.start()
            self._stream = self.engine._stream
        except Exception:
            self._is_recording = False
            self._stream = None
            raise

    def stop(self):
        self._is_recording = False
        self.engine.close()
        self._stream = None
        self.flush()

    def restart(self,reinit_portaudio=False):
        # Engine owns both directions. No global PortAudio termination.
        self.stop()
        self.start()

    def is_healthy(self):
        return self.engine.error is None and super().is_healthy()


class AecPlayer(AudioPlayer):
    def __init__(self,engine):
        # Reuse synthesis/PCM conversion methods without starting an OutputStream worker.
        self.engine = engine
        self.sample_rate = 24000
        self.device_index = engine.output_device
        self._uncertain_chunk_dropped = False

    def play_sound(self,audio_data,blocking=False):
        if audio_data is None or len(audio_data) == 0:
            return
        data = np.asarray(audio_data,dtype=np.float32).reshape(-1)
        # 24kHz Gemini PCM -> shared 16kHz hardware stream. Linear pilot resampler.
        count = max(1,round(len(data)*self.engine.rate/self.sample_rate))
        converted = np.interp(np.arange(count)*self.sample_rate/self.engine.rate,
                              np.arange(len(data)),data).astype(np.float32)
        self.engine.enqueue(converted)

    def stop(self):
        # At most an already-buffered hardware tail remains; no waiting for a long write.
        self.engine.clear_output()

    def clear_queue(self):
        self.engine.clear_output()
        return 0

    def prepare_for_subsystem_reinit(self):
        self.engine.close()

    def on_subsystem_reinitialized(self):
        pass  # Recorder already restarted the shared engine.

    @property
    def is_playing(self):
        return self.engine.playing

    @property
    def is_healthy(self):
        return self.engine.error is None and self.engine._stream is not None

    @property
    def has_error(self):
        return self.engine.error is not None

    @property
    def in_cooldown(self):
        return False


def create_aec_pair(input_device=None,output_device=None,delay_ms=None):
    engine=DuplexAecEngine(input_device,output_device,delay_ms)
    return AecRecorder(engine),AecPlayer(engine)
