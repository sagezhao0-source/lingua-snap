"""Push-to-talk audio recorder using sounddevice."""

import queue
import numpy as np
import sounddevice as sd
from PyQt5.QtCore import QObject, pyqtSignal


class AudioRecorder(QObject):
    """Records microphone audio while hotkey is held.

    Uses a queue-based design: the PortAudio callback pushes audio blocks
    into a queue, and stop() drains them into a single numpy array.
    """

    recording_stopped = pyqtSignal(object)  # numpy array or None
    recorder_error = pyqtSignal(str)

    def __init__(self, sample_rate=16000, channels=1, device=None,
                 max_duration_sec=30, min_duration_sec=0.3):
        super().__init__()
        self._sample_rate = sample_rate
        self._channels = channels
        self._device = device
        self._max_duration_sec = max_duration_sec
        self._min_duration_sec = min_duration_sec
        self._queue = queue.Queue()
        self._stream = None
        self._recording = False
        self._overflow_count = 0

    def start(self):
        """Begin recording from the microphone."""
        if self._recording:
            return

        self._queue = queue.Queue()
        self._overflow_count = 0
        self._recording = True

        try:
            self._stream = sd.InputStream(
                samplerate=self._sample_rate,
                channels=self._channels,
                device=self._device,
                dtype=np.float32,
                callback=self._audio_callback
            )
            self._stream.start()
        except sd.PortAudioError as e:
            self._recording = False
            self.recorder_error.emit(f"Microphone error: {e}")

    def stop(self):
        """Stop recording and return the captured audio as a numpy array.

        Returns None if the recording was too short (likely accidental).
        """
        if not self._recording:
            return None

        self._recording = False

        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        audio = self._drain_queue()

        if audio is None:
            return None

        # Check minimum duration
        duration = len(audio) / self._sample_rate
        if duration < self._min_duration_sec:
            return None

        # Warn if we had overflows
        if self._overflow_count > 0:
            self.recorder_error.emit(
                f"Audio overflow ({self._overflow_count} blocks dropped). "
                "Try reducing system load."
            )

        self.recording_stopped.emit(audio)
        return audio

    def _audio_callback(self, indata, frames, time_info, status):
        """PortAudio callback -- called from high-priority audio thread.

        Must be fast: no I/O, no allocations beyond the copy.
        """
        if status:
            if status.input_overflow:
                self._overflow_count += 1
        if self._recording:
            # Check max duration
            current_samples = self._queue.qsize() * frames
            if current_samples < self._max_duration_sec * self._sample_rate:
                self._queue.put(indata.copy())
            else:
                self._recording = False

    def _drain_queue(self):
        """Drain the audio queue into a single numpy array."""
        blocks = []
        while True:
            try:
                block = self._queue.get_nowait()
                blocks.append(block)
            except queue.Empty:
                break

        if not blocks:
            return None

        return np.concatenate(blocks, axis=0)

    @staticmethod
    def list_input_devices():
        """Return list of available input devices."""
        devices = []
        for i, dev in enumerate(sd.query_devices()):
            if dev['max_input_channels'] > 0:
                devices.append({
                    'index': i,
                    'name': dev['name'],
                    'channels': dev['max_input_channels'],
                    'default_samplerate': dev['default_samplerate']
                })
        return devices
