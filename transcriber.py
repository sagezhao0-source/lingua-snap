"""Speech-to-text transcription using faster-whisper (local)."""

import os
import tempfile
import numpy as np
import soundfile as sf
from PyQt5.QtCore import QObject, pyqtSignal


class WhisperTranscriber(QObject):
    """Wraps faster-whisper for local, offline speech recognition.

    The model is loaded lazily on first use (downloads ~1GB for 'tiny').
    Transcription is blocking and should run in a worker thread.
    """

    transcription_done = pyqtSignal(str)    # transcribed text
    transcription_error = pyqtSignal(str)

    def __init__(self, model_size="tiny", device="cpu", compute_type="int8"):
        super().__init__()
        self._model_size = model_size
        self._device = device
        self._compute_type = compute_type
        self._model = None
        self._model_cache_dir = os.path.join(
            os.path.expanduser("~"), ".cache", "lingua-snap", "models"
        )

    def preload(self):
        """Preload the Whisper model (call on main thread before any QThread use).

        On Windows, CTranslate2's C++ backend (Intel MKL / OpenMP) must be
        initialised on the main thread. Loading it lazily inside a QThread
        causes a native access violation that Python's excepthook cannot catch.
        """
        self._ensure_model()

    def _ensure_model(self):
        """Load the Whisper model if not already loaded."""
        if self._model is not None:
            return

        try:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(
                self._model_size,
                device=self._device,
                compute_type=self._compute_type,
                download_root=self._model_cache_dir
            )
        except Exception as e:
            raise RuntimeError(
                f"Failed to load Whisper model '{self._model_size}': {e}"
            ) from e

    def transcribe(self, audio_data):
        """Transcribe audio data to text. Blocking call.

        Args:
            audio_data: numpy array of float32 samples, shape (n_samples, channels).

        Returns:
            Transcribed text string, or empty string if nothing detected.
        """
        if audio_data is None or len(audio_data) == 0:
            return ""

        try:
            self._ensure_model()
        except RuntimeError as e:
            self.transcription_error.emit(str(e))
            return ""

        # Write audio data to temp WAV file
        tmp_path = None
        try:
            fd, tmp_path = tempfile.mkstemp(suffix=".wav")
            os.close(fd)

            # Ensure float32 for soundfile
            audio = np.asarray(audio_data, dtype=np.float32)
            # If stereo, average to mono (Whisper expects mono)
            if audio.ndim > 1 and audio.shape[1] > 1:
                audio = audio.mean(axis=1)

            sf.write(tmp_path, audio, 16000, subtype='PCM_16')

            segments, info = self._model.transcribe(
                tmp_path,
                beam_size=5,
                language="en",
                vad_filter=True,
                vad_parameters=dict(
                    min_silence_duration_ms=500,
                )
            )

            # Force iteration to collect all segments
            texts = []
            for segment in segments:
                texts.append(segment.text.strip())

            result = " ".join(texts).strip()

            if not result:
                return ""

            self.transcription_done.emit(result)
            return result

        except Exception as e:
            self.transcription_error.emit(f"Transcription error: {e}")
            return ""
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    def is_model_loaded(self):
        """Check if the Whisper model is loaded in memory."""
        return self._model is not None
