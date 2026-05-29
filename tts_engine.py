"""Text-to-speech engine using Windows SAPI5 via pyttsx3."""

from PyQt5.QtCore import QObject, pyqtSignal, QThread


class _TTSWorker(QThread):
    """Dedicated thread for pyttsx3 speech synthesis."""

    def __init__(self, text, rate=150, parent=None):
        super().__init__(parent)
        self._text = text
        self._rate = rate

    def run(self):
        try:
            import pyttsx3
            engine = pyttsx3.init(driverName='sapi5')
            engine.setProperty('rate', self._rate)
            engine.say(self._text)
            engine.runAndWait()
        except Exception:
            pass  # Silently fail TTS; speech is a nice-to-have


class TTSEngine(QObject):
    """Non-blocking TTS engine for Windows.

    Each speak() call runs on a dedicated QThread so it never blocks
    the Qt event loop or other processing.
    """

    tts_done = pyqtSignal()
    tts_error = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._current_worker = None
        self._rate = 150

    def speak(self, text):
        """Speak text asynchronously. Cancels any in-progress speech."""
        if not text:
            return

        # Cancel any in-progress speech
        self.stop()

        self._current_worker = _TTSWorker(text, self._rate)
        self._current_worker.finished.connect(self._on_done)
        self._current_worker.start()

    def stop(self):
        """Stop current speech if any."""
        worker = self._current_worker
        if worker is not None:
            self._current_worker = None
            if worker.isRunning():
                worker.terminate()
                worker.wait(500)

    def set_rate(self, rate):
        """Set speech rate (words per minute, default 150)."""
        self._rate = rate

    def _on_done(self):
        self._current_worker = None
        self.tts_done.emit()
