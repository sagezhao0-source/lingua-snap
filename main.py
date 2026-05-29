"""LinguaSnap — Game English Learning Assistant.

Click the floating bubble to start/stop recording, or use the system tray menu.
Transcribed text can be edited before sending to the LLM for explanation.
"""

import sys
import os
import subprocess
import traceback
import faulthandler
from datetime import datetime

# Suppress QWebEngine network service crash noise on Windows
# Suppress QWebEngine startup noise on Windows (harmless, auto-restarts)
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-gpu-sandbox"

# CRITICAL: ctranslate2 must be imported before PyQt5 to prevent a native DLL
# conflict on Windows. PyQt5's Qt5 libraries load incompatible OpenMP/MKL
# symbols that cause ctranslate2 to segfault during WhisperModel() init.
# Loading ctranslate2 first lets its C++ backend claim the symbols it needs.
import ctranslate2  # noqa: F401

from PyQt5.QtCore import Qt, QThread, QTimer, pyqtSignal, QObject
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor, QFont, QBrush, QPen
from PyQt5.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu, QAction, QMessageBox,
    QDialog, QVBoxLayout, QLabel, QLineEdit,
    QPushButton, QHBoxLayout, QTextEdit
)

from config import Config
from recorder import AudioRecorder
from transcriber import WhisperTranscriber
from llm_client import LLMClient
from tts_engine import TTSEngine
from obsidian_writer import ObsidianWriter
from context_capture import ContextBuffer, capture_context
from floating_panel import FloatingPanel, ResultCard
from settings_dialog import SettingsDialog

# ── Crash log path ──────────────────────────────────────────────────
_LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lingua-snap.log")


def _log(msg):
    """Append a timestamped message to the crash log."""
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass


def _install_excepthook():
    """Redirect unhandled Python exceptions to the log file."""
    _original = sys.excepthook

    def _handler(exc_type, exc_value, exc_tb):
        tb_lines = traceback.format_exception(exc_type, exc_value, exc_tb)
        _log("UNHANDLED EXCEPTION:\n" + "".join(tb_lines))
        if _original:
            _original(exc_type, exc_value, exc_tb)

    sys.excepthook = _handler


def _create_tray_icon(color=(255, 255, 255)):
    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QBrush(QColor(*color)))
    painter.setPen(Qt.NoPen)
    painter.drawRoundedRect(2, 2, 28, 28, 6, 6)
    painter.setPen(QPen(QColor(18, 18, 24), 1.5))
    painter.drawRoundedRect(4, 4, 24, 24, 5, 5)
    painter.setPen(QPen(QColor(220, 220, 220), 2))
    font = QFont("Segoe UI", 12, QFont.Bold)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignCenter, "LS")
    painter.end()
    return QIcon(pixmap)


# ── Game Name Dialog ───────────────────────────────────────────────

class GameNameDialog(QDialog):
    """White card modal — ask which game the user is playing."""

    CARD_STYLE = """
        QDialog {
            background-color: #ffffff;
            border: 0.5px solid #e5e5e5;
            border-radius: 12px;
        }
        QLabel {
            background: transparent;
        }
        QLineEdit {
            background-color: #F3F3F3;
            color: #1a1a1a;
            border: none;
            border-radius: 14px;
            padding: 14px 20px;
            font-family: "Segoe UI";
            font-size: 16px;
        }
        QPushButton#cancelBtn, QPushButton#okBtn {
            background: transparent;
            border: 1.5px solid #c0c0c0;
            color: #999;
            font-size: 13px;
            font-weight: bold;
            border-radius: 10px;
            font-family: "Segoe UI";
        }
        QPushButton#cancelBtn:hover {
            background: #f5f5f5;
            border-color: #888;
            color: #666;
        }
        QPushButton#okBtn {
            background: #185FA5;
            border-color: #185FA5;
            color: #fff;
        }
        QPushButton#okBtn:hover {
            background: #134b84;
            border-color: #134b84;
        }
    """

    def __init__(self, current_name="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("LinguaSnap - Notebook")
        self.setFixedSize(560, 260)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog | Qt.WindowStaysOnTopHint)
        self.setStyleSheet(self.CARD_STYLE)

        LR = 36

        def _hbox(*widgets, left=LR, right=LR):
            row = QHBoxLayout()
            row.setContentsMargins(left, 0, right, 0)
            for w in widgets:
                row.addWidget(w)
            return row

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Title ───────────────────────────────────────────────
        main_layout.addSpacing(20)
        title = QLabel("Which game are you playing?")
        title.setFont(QFont("Segoe UI", 14, 500))
        title.setStyleSheet("color: #222;")
        main_layout.addLayout(_hbox(title))

        # ── Subtitle ────────────────────────────────────────────
        main_layout.addSpacing(6)
        subtitle = QLabel("Words you look up will be saved to this notebook")
        subtitle.setFont(QFont("Segoe UI", 12))
        subtitle.setStyleSheet("color: #888;")
        main_layout.addLayout(_hbox(subtitle))

        # ── Input ───────────────────────────────────────────────
        main_layout.addSpacing(18)
        self._input = QLineEdit(current_name)
        self._input.setPlaceholderText("e.g. Baldur's Gate 3")
        self._input.setFixedHeight(52)
        self._input.selectAll()
        main_layout.addLayout(_hbox(self._input))

        # ── Buttons ─────────────────────────────────────────────
        main_layout.addSpacing(20)
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(LR, 0, LR, 0)
        btn_row.setSpacing(10)
        btn_row.addStretch()

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setObjectName("cancelBtn")
        self._cancel_btn.setFixedSize(90, 36)
        self._cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self._cancel_btn)

        self._ok_btn = QPushButton("Confirm")
        self._ok_btn.setObjectName("okBtn")
        self._ok_btn.setFixedSize(90, 36)
        self._ok_btn.setDefault(True)
        self._ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(self._ok_btn)

        main_layout.addLayout(btn_row)
        main_layout.addSpacing(20)
        self.setLayout(main_layout)

    def showEvent(self, event):
        super().showEvent(event)
        screen = QApplication.primaryScreen()
        if screen:
            geom = screen.availableGeometry()
            self.move(
                (geom.width() - self.width()) // 2,
                (geom.height() - self.height()) // 2
            )

    @property
    def game_name(self):
        return self._input.text().strip()


# ── Edit Dialog ────────────────────────────────────────────────────

class EditTranscriptionDialog(QDialog):
    """White card modal — confirm/correct transcribed text before lookup."""

    CARD_STYLE = """
        QDialog {
            background-color: #ffffff;
            border: 0.5px solid #e5e5e5;
            border-radius: 12px;
        }
        QLabel {
            background: transparent;
        }
        QLineEdit {
            background-color: #F3F3F3;
            color: #1a1a1a;
            border: none;
            border-radius: 14px;
            padding: 14px 20px;
            font-family: "Segoe UI";
        }
        QPushButton {
            font-family: "Segoe UI";
        }
        QPushButton#retryBtn, QPushButton#cancelBtn, QPushButton#lookupBtn {
            background: transparent;
            border: 1.5px solid #c0c0c0;
            color: #999;
            font-size: 16px;
            font-weight: bold;
            border-radius: 10px;
        }
        QPushButton#retryBtn:hover, QPushButton#cancelBtn:hover, QPushButton#lookupBtn:hover {
            background: #f5f5f5;
            border-color: #888;
            color: #666;
        }
    """

    def __init__(self, transcribed_text, parent=None):
        super().__init__(parent)
        self.setWindowTitle("LinguaSnap - Confirm")
        self.setFixedSize(800, 320)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog | Qt.WindowStaysOnTopHint)
        self.setStyleSheet(self.CARD_STYLE)

        LR = 40

        def _sep():
            """Return a 1px faint-gray line."""
            line = QLabel()
            line.setFixedHeight(1)
            line.setStyleSheet("background: #e5e5e5;")
            return line

        def _hbox(*widgets, left=LR, right=LR):
            """Wrap widget(s) in a QHBoxLayout with left/right margins."""
            row = QHBoxLayout()
            row.setContentsMargins(left, 0, right, 0)
            for w in widgets:
                row.addWidget(w)
            return row

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Title ───────────────────────────────────────────────
        main_layout.addSpacing(16)
        title = QLabel("Confirm transcription")
        title.setFont(QFont("Segoe UI", 14, 500))
        title.setStyleSheet("color: #222;")
        main_layout.addLayout(_hbox(title))

        # ── Subtitle ────────────────────────────────────────────
        main_layout.addSpacing(8)
        subtitle = QLabel("Edit if the word was misheard")
        subtitle.setFont(QFont("Segoe UI", 13))
        subtitle.setStyleSheet("color: #888;")
        main_layout.addLayout(_hbox(subtitle))

        # ── Line ────────────────────────────────────────────────
        main_layout.addSpacing(16)
        main_layout.addLayout(_hbox(_sep()))

        # ── Input ───────────────────────────────────────────────
        main_layout.addSpacing(24)
        self._text_edit = QLineEdit(transcribed_text)
        self._text_edit.setFont(QFont("Segoe UI", 17))
        self._text_edit.selectAll()
        self._text_edit.setFixedHeight(76)
        main_layout.addLayout(_hbox(self._text_edit))

        # ── Line ────────────────────────────────────────────────
        main_layout.addSpacing(24)
        main_layout.addLayout(_hbox(_sep()))

        # ── Buttons ─────────────────────────────────────────────
        main_layout.addSpacing(20)
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(LR, 0, LR, 0)
        btn_row.setSpacing(8)
        btn_row.addStretch()

        self._retry_btn = QPushButton("\u21BB")  # ↻
        self._retry_btn.setObjectName("retryBtn")
        self._retry_btn.setToolTip("Re-record")
        self._retry_btn.setFixedSize(40, 40)
        self._retry_btn.clicked.connect(self._on_retry)
        btn_row.addWidget(self._retry_btn)

        self._cancel_btn = QPushButton("\u2715")  # ✕
        self._cancel_btn.setObjectName("cancelBtn")
        self._cancel_btn.setToolTip("Cancel")
        self._cancel_btn.setFixedSize(40, 40)
        self._cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self._cancel_btn)

        self._ok_btn = QPushButton("\u2315")  # ⌕
        self._ok_btn.setObjectName("lookupBtn")
        self._ok_btn.setToolTip("Look up")
        self._ok_btn.setFixedSize(40, 40)
        self._ok_btn.setDefault(True)
        self._ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(self._ok_btn)

        main_layout.addLayout(btn_row)
        main_layout.addSpacing(20)
        self.setLayout(main_layout)

        self._retry_requested = False

    def showEvent(self, event):
        """Center on screen."""
        super().showEvent(event)
        screen = QApplication.primaryScreen()
        if screen:
            geom = screen.availableGeometry()
            self.move(
                (geom.width() - self.width()) // 2,
                (geom.height() - self.height()) // 2
            )

    def _on_retry(self):
        self._retry_requested = True
        self.reject()

    @property
    def edited_text(self):
        return self._text_edit.text().strip()

    @property
    def retry_requested(self):
        return self._retry_requested


# ── Workers ────────────────────────────────────────────────────────

class TranscribeWorker(QObject):
    """Transcribes audio without calling LLM."""
    finished = pyqtSignal(str)       # transcribed text
    error = pyqtSignal(str)

    def __init__(self, audio_data, transcriber):
        super().__init__()
        self._audio_data = audio_data
        self._transcriber = transcriber

    def run(self):
        try:
            _log(f"TranscribeWorker: audio shape={self._audio_data.shape}")
            text = self._transcriber.transcribe(self._audio_data)
            _log(f"TranscribeWorker: result='{text}'")
            if not text or not text.strip():
                self.error.emit("No speech detected. Try again.")
                return
            self.finished.emit(text.strip())
        except Exception as e:
            _log(f"TranscribeWorker exception: {e}\n{traceback.format_exc()}")
            self.error.emit(str(e))


class LLMQueryWorker(QObject):
    """Queries LLM with given text (no transcription)."""
    finished = pyqtSignal(str, str)  # (explanation, word)
    error = pyqtSignal(str)

    def __init__(self, text, llm_client):
        super().__init__()
        self._text = text
        self._llm_client = llm_client

    def run(self):
        try:
            _log(f"LLMQueryWorker: querying '{self._text}'")
            explanation = self._llm_client.get_explanation(self._text)
            _log(f"LLMQueryWorker: got {len(explanation)} chars")
            if not explanation:
                self.error.emit("Failed to get explanation.")
                return
            self.finished.emit(explanation, self._text)
        except Exception as e:
            _log(f"LLMQueryWorker exception: {e}\n{traceback.format_exc()}")
            self.error.emit(str(e))


class TranslateWorker(QObject):
    """Translates selected text to Chinese via LLM."""
    finished = pyqtSignal(str)    # translated text
    error = pyqtSignal(str)

    def __init__(self, text, llm_client):
        super().__init__()
        self._text = text
        self._llm_client = llm_client

    def run(self):
        try:
            _log(f"TranslateWorker: translating '{self._text[:50]}...'")
            result = self._llm_client.translate_to_chinese(self._text)
            _log(f"TranslateWorker: got {len(result)} chars")
            if not result:
                self.error.emit("Translation failed.")
                return
            self.finished.emit(result)
        except Exception as e:
            _log(f"TranslateWorker exception: {e}\n{traceback.format_exc()}")
            self.error.emit(str(e))


# ── Translation result dialog ──────────────────────────────────────

class TranslationDialog(QDialog):
    """Dark-themed popup showing Chinese translation of selected text."""

    DARK_STYLE = """
        QDialog {
            background-color: #181820;
        }
        QLabel {
            color: #e0e0e0;
            background: transparent;
        }
        QPushButton {
            background-color: #2a2a38;
            color: #e0e0e0;
            border: 1px solid #444;
            border-radius: 6px;
            padding: 8px 16px;
            font-family: "Segoe UI";
            font-size: 12px;
        }
        QPushButton:hover {
            background-color: #3a3a4a;
        }
    """

    def __init__(self, original_text, translation, parent=None):
        super().__init__(parent)
        self.setWindowTitle("LinguaSnap - Chinese Translation")
        self.setMinimumWidth(350)
        self.setMaximumWidth(450)
        self.setWindowFlags(
            Qt.Dialog | Qt.WindowStaysOnTopHint
        )
        self.setStyleSheet(self.DARK_STYLE)

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        src_header = QLabel("Original:")
        src_header.setFont(QFont("Segoe UI", 10, QFont.Bold))
        src_header.setStyleSheet("color: #aaccff; background: transparent;")
        layout.addWidget(src_header)

        src_label = QLabel(original_text)
        src_label.setFont(QFont("Segoe UI", 11))
        src_label.setWordWrap(True)
        src_label.setStyleSheet("color: #ccc; background: transparent;")
        layout.addWidget(src_label)

        trans_header = QLabel("Translation:")
        trans_header.setFont(QFont("Segoe UI", 10, QFont.Bold))
        trans_header.setStyleSheet("color: #aaccff; background: transparent;")
        layout.addWidget(trans_header)

        trans_label = QLabel(translation)
        trans_label.setFont(QFont("Segoe UI", 13))
        trans_label.setWordWrap(True)
        trans_label.setStyleSheet("color: #f0f0f0; background: transparent;")
        layout.addWidget(trans_label)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

        self.setLayout(layout)


# ── Main App ───────────────────────────────────────────────────────

class LinguaSnapApp(QApplication):
    """Main application — tray menu recording + edit transcription + LLM."""

    def __init__(self, argv):
        super().__init__(argv)
        self.setQuitOnLastWindowClosed(False)

        self._config = Config()
        self._busy = False
        self._recording = False
        self._panel = None
        self._context_buffer = ContextBuffer()
        self._pending_save = {}

        self._setup_tray()
        self._setup_components()
        self._setup_panel()
        self._connect_signals()

        # Show floating bubble
        self._panel.show()
        self._panel.raise_()
        QTimer.singleShot(500, self._panel.raise_)

        # Prompt for game name on startup (journal mode)
        QTimer.singleShot(800, self._prompt_game_name)

    # ── Setup ──────────────────────────────────────────────────

    def _setup_tray(self):
        self._tray_icon = QSystemTrayIcon(self)
        self._idle_icon = _create_tray_icon((255, 255, 255))
        self._rec_icon = _create_tray_icon((255, 80, 80))
        self._busy_icon = _create_tray_icon((100, 180, 255))
        self._tray_icon.setIcon(self._idle_icon)
        self._tray_icon.setToolTip("LinguaSnap - English Learning Assistant")

        menu = QMenu()

        self._status_action = menu.addAction("LinguaSnap Ready")
        self._status_action.setEnabled(False)

        menu.addSeparator()

        self._record_action = menu.addAction("🎤 Record Word")
        self._record_action.triggered.connect(self._on_tray_record)

        self._stop_action = menu.addAction("⏹ Stop && Look Up")
        self._stop_action.setEnabled(False)
        self._stop_action.triggered.connect(self._on_tray_stop)

        menu.addSeparator()

        mic_action = menu.addAction("Test Microphone")
        mic_action.triggered.connect(self._test_microphone)

        config_action = menu.addAction("Open Config")
        config_action.triggered.connect(self._open_config)

        settings_action = menu.addAction("Settings")
        settings_action.triggered.connect(self._open_settings)

        change_game_action = menu.addAction("Change Game...")
        change_game_action.triggered.connect(self._prompt_game_name)

        menu.addSeparator()

        quit_action = menu.addAction("Quit")
        quit_action.triggered.connect(self._on_quit)

        self._tray_icon.setContextMenu(menu)
        self._tray_icon.show()

    def _setup_panel(self):
        self._panel = FloatingPanel()
        self._result_card = ResultCard()

    def _setup_components(self):
        self._recorder = AudioRecorder(
            sample_rate=self._config.get("sample_rate", 16000),
            max_duration_sec=self._config.get("max_recording_sec", 30),
            min_duration_sec=self._config.get("min_recording_sec", 0.3)
        )
        self._transcriber = WhisperTranscriber(
            model_size=self._config.whisper_model_size,
            device=self._config.whisper_device,
            compute_type=self._config.whisper_compute_type
        )
        # Preload model on main thread — avoids CTranslate2 native crash
        # when initialising its C++ backend inside a QThread on Windows.
        _log("Preloading Whisper model on main thread...")
        self._transcriber.preload()
        _log("Whisper model loaded OK")
        self._llm_client = LLMClient(
            base_url=self._config.llm_base_url,
            api_key=self._config.llm_api_key,
            model=self._config.llm_model
        )
        self._tts = TTSEngine()
        self._tts.set_rate(self._config.get("tts_rate", 150))
        self._obsidian = ObsidianWriter(
            vault_path=self._config.obsidian_vault_path,
            subfolder=self._config.obsidian_subfolder,
            include_game_name=self._config.get(
                "obsidian.include_game_name", False
            ),
            game_name=self._config.obsidian_game_name,
            save_mode=self._config.obsidian_save_mode,
            attachments_subfolder=self._config.obsidian_attachments_subfolder
        )

        if not self._config.llm_api_key:
            self._tray_icon.showMessage(
                "LinguaSnap",
                "API key not configured. Edit config.json.",
                QSystemTrayIcon.Warning,
                5000
            )

    def _connect_signals(self):
        self._recorder.recorder_error.connect(self._on_error)
        # Wire floating panel clicks to recording
        self._panel.record_start.connect(self._on_panel_record)
        self._panel.record_stop.connect(self._on_panel_stop)
        # Wire result card signals
        self._result_card.read_text.connect(self._on_read_text)
        self._result_card.translate_requested.connect(self._on_translate_requested)
        self._result_card.card_closed.connect(self._on_card_closed)
        self._result_card.dismiss_requested.connect(self._on_card_closed)
        self._result_card.save_note.connect(self._on_save_note)
        self._panel.type_input_requested.connect(self._on_type_input)

    def _on_panel_record(self):
        """Floating panel clicked: start recording."""
        self._on_tray_record()

    def _on_panel_stop(self):
        """Floating panel clicked during recording: stop and process."""
        self._on_tray_stop()

    def _on_type_input(self):
        """Keyboard action bubble clicked — show a text input dialog."""
        if self._busy:
            return
        dialog = QDialog(None)
        dialog.setWindowTitle("LinguaSnap — Type a word")
        dialog.setFixedSize(420, 180)
        dialog.setWindowFlags(
            Qt.FramelessWindowHint | Qt.Dialog | Qt.WindowStaysOnTopHint
        )
        dialog.setStyleSheet("""
            QDialog {
                background-color: #ffffff;
                border: 0.5px solid #e5e5e5;
                border-radius: 12px;
            }
            QLabel { background: transparent; color: #222;
                     font-family: "Segoe UI"; font-size: 14px; font-weight: 500; }
            QLineEdit {
                background-color: #F3F3F3; color: #1a1a1a;
                border: none; border-radius: 10px;
                padding: 10px 16px; font-family: "Segoe UI"; font-size: 16px;
            }
            QPushButton {
                font-family: "Segoe UI"; font-size: 13px; font-weight: bold;
                border-radius: 8px; padding: 6px 16px;
            }
            QPushButton#cancelBtn {
                background: transparent; border: 1.5px solid #c0c0c0; color: #999;
            }
            QPushButton#cancelBtn:hover { background: #f5f5f5; border-color: #888; color: #666; }
            QPushButton#lookupBtn {
                background: #185FA5; border: none; color: #fff;
            }
            QPushButton#lookupBtn:hover { background: #134b84; }
        """)

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 18, 24, 18)
        layout.setSpacing(12)

        title = QLabel("Type a word or phrase to look up")
        layout.addWidget(title)

        inp = QLineEdit()
        inp.setPlaceholderText("e.g. serendipity")
        inp.setFixedHeight(44)
        layout.addWidget(inp)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        cancel = QPushButton("Cancel")
        cancel.setObjectName("cancelBtn")
        cancel.setFixedSize(80, 32)
        cancel.clicked.connect(dialog.reject)
        btn_row.addWidget(cancel)

        ok = QPushButton("Look Up")
        ok.setObjectName("lookupBtn")
        ok.setFixedSize(80, 32)
        ok.setDefault(True)
        ok.clicked.connect(dialog.accept)
        btn_row.addWidget(ok)

        layout.addLayout(btn_row)
        dialog.setLayout(layout)

        # Center on screen
        screen = QApplication.primaryScreen()
        if screen:
            geom = screen.availableGeometry()
            dialog.move(
                (geom.width() - dialog.width()) // 2,
                (geom.height() - dialog.height()) // 2
            )

        inp.setFocus()
        if dialog.exec_() == QDialog.Accepted:
            text = inp.text().strip()
            if text:
                self._query_llm(text)

    # ── Tray recording ─────────────────────────────────────────

    def _on_tray_record(self):
        """Tray 'Record Word' clicked: start recording."""
        if self._busy:
            return

        _log("START RECORDING")
        self._recording = True
        self._recorder.start()
        self._tray_icon.setIcon(self._rec_icon)
        self._status_action.setText("Recording... Speak now")
        self._record_action.setEnabled(False)
        self._stop_action.setEnabled(True)
        self._panel.set_recording()

        self._tray_icon.showMessage(
            "LinguaSnap",
            "Recording... Click Stop when done.",
            QSystemTrayIcon.Information,
            2000
        )

    def _on_tray_stop(self):
        """Tray 'Stop & Look Up' clicked: stop recording, transcribe."""
        if not self._recording:
            return

        _log("STOP RECORDING")
        self._recording = False
        audio_data = self._recorder.stop()
        self._tray_icon.setIcon(self._busy_icon)
        self._status_action.setText("Transcribing...")
        self._record_action.setEnabled(False)
        self._stop_action.setEnabled(False)
        self._panel.set_processing()

        if audio_data is None:
            self._reset_after_recording()
            self._status_action.setText("Recording too short")
            self._panel.set_idle()
            return

        self._busy = True
        self._run_transcribe(audio_data)

    def _run_transcribe(self, audio_data):
        """Run transcription in worker thread."""
        _log(f"Transcribing audio, samples={len(audio_data)}")
        self._thread = QThread()
        self._worker = TranscribeWorker(audio_data, self._transcriber)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_transcribed)
        self._worker.error.connect(self._on_transcribe_error)
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)
        self._thread.finished.connect(self._thread.deleteLater)

        self._thread.start()

    def _on_transcribed(self, text):
        """Transcription done — show edit dialog."""
        _log(f"Transcription result: '{text}'")
        self._busy = False
        self._reset_after_recording()
        self._tray_icon.setIcon(self._idle_icon)

        dialog = EditTranscriptionDialog(text)
        result = dialog.exec_()

        if result == QDialog.Accepted:
            edited = dialog.edited_text
            if edited:
                self._query_llm(edited)
            else:
                self._status_action.setText("Text was empty, cancelled")
                self._panel.set_idle()
        elif dialog.retry_requested:
            self._status_action.setText("Re-record...")
            self._panel.set_idle()
            QTimer.singleShot(300, self._on_tray_record)
        else:
            self._status_action.setText("Cancelled")
            self._panel.set_idle()

    def _on_transcribe_error(self, error_msg):
        _log(f"Transcription error: {error_msg}")
        self._busy = False
        self._reset_after_recording()
        self._tray_icon.setIcon(self._idle_icon)
        self._panel.set_idle()

        if "No speech detected" in error_msg:
            self._status_action.setText("No speech detected")
            return

        self._status_action.setText(f"Error: {error_msg}")
        self._result_card.show_result(
            word="Error", ipa="", pos="",
            definition=error_msg, etymology="", examples=[]
        )

    def _query_llm(self, text):
        """Send edited text to LLM in worker thread."""
        _log(f"Querying LLM: '{text}'")
        self._busy = True
        self._tray_icon.setIcon(self._busy_icon)
        self._status_action.setText(f"Looking up: {text}")
        self._panel.set_processing()

        self._thread = QThread()
        self._worker = LLMQueryWorker(text, self._llm_client)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_llm_result)
        self._worker.error.connect(self._on_llm_error)
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)
        self._thread.finished.connect(self._thread.deleteLater)

        self._thread.start()

    def _on_llm_result(self, explanation, word):
        """LLM query done — parse and show structured result."""
        _log(f"LLM result for '{word}': {explanation[:80]}...")
        self._busy = False
        self._tray_icon.setIcon(self._idle_icon)
        self._panel.set_idle()

        # Parse structured fields from LLM markdown output
        fields = self._parse_llm_response(explanation)

        # Show in result card (standalone, bubble stays visible)
        self._result_card.show_result(
            word=word,
            ipa=fields.get("ipa", ""),
            pos=fields.get("pos", ""),
            definition=fields.get("definition", ""),
            etymology=fields.get("etymology", ""),
            examples=fields.get("examples", []),
            raw_explanation=explanation,
        )

        # Defer saving — user can add notes before clicking "Save to Obsidian"
        self._pending_save = {
            "word": word,
            "explanation": explanation,
        }
        self._status_action.setText(f"Looked up: {word}")

    @staticmethod
    def _parse_llm_response(text):
        """Extract structured fields from the LLM markdown response.

        Expected format:
        **Pronunciation**: /IPA/
        **Definition**: [POS] — [definition]
        **Etymology**: [origin]
        **Examples**:
        1. [sentence]
        2. [sentence]
        3. [sentence]
        """
        import re
        result = {"ipa": "", "pos": "", "definition": "", "etymology": "", "examples": []}

        # Pronunciation
        m = re.search(r'\*\*Pronunciation\*\*\s*:\s*(.+?)(?:\n|$)', text)
        if m:
            result["ipa"] = m.group(1).strip()

        # Definition — extract POS badge and definition text
        m = re.search(r'\*\*Definition\*\*\s*:\s*(.+?)(?:\n\*\*|\n\n|\n(?:[2-9]|\d{2})\.|\Z)', text, re.DOTALL)
        if m:
            raw = m.group(1).strip()
            # Try to extract [POS] prefix
            pos_m = re.match(r'\[?\(?(\w+\.?)\)?\]?\s*(?:[-—–]\s*)?(.*)', raw)
            if pos_m:
                result["pos"] = pos_m.group(1).strip()
                result["definition"] = pos_m.group(2).strip()
            else:
                result["definition"] = raw

        # Etymology
        m = re.search(r'\*\*Etymology\*\*\s*:\s*(.+?)(?:\n\*\*|\n\n|\Z)', text, re.DOTALL)
        if m:
            result["etymology"] = m.group(1).strip()

        # Examples
        m = re.search(r'\*\*Examples?\*\*\s*:?\s*\n(.*?)(?:\Z)', text, re.DOTALL)
        if m:
            lines = m.group(1).strip().split("\n")
            for line in lines:
                line = line.strip()
                # Match "1. sentence" or "1) sentence"
                if re.match(r'\d+[\.\)]\s+', line):
                    sentence = re.sub(r'^\d+[\.\)]\s+', '', line).strip()
                    if sentence:
                        result["examples"].append(sentence)
                elif line:
                    result["examples"].append(line)

        return result

    def _on_llm_error(self, error_msg):
        _log(f"LLM error: {error_msg}")
        self._busy = False
        self._tray_icon.setIcon(self._idle_icon)
        self._panel.set_idle()
        self._result_card.show_result(
            word="Error", ipa="", pos="",
            definition=error_msg, etymology="", examples=[]
        )
        self._status_action.setText(f"Error: {error_msg}")

    # ── Read / Translate (right-click context menu) ─────────────

    def _on_read_text(self, text):
        """User right-clicked 'Read' on selected text."""
        _log(f"Read text: '{text[:40]}...'")
        self._tts.speak(text)

    def _on_card_closed(self):
        """Result card closed or dismissed — reset panel state."""
        self._reset_after_recording()
        self._panel.set_idle()
        self._busy = False
        self._pending_save = {}
        self._status_action.setText("Ready")
        self._tray_icon.setIcon(self._idle_icon)

    def _on_save_note(self, word, note_html, images_json):
        """User clicked 'Save to Obsidian' — flush note + word to vault."""
        import json as _json
        pending = getattr(self, '_pending_save', {})
        explanation = pending.get("explanation", "")
        context = self._context_buffer.consume()

        images = _json.loads(images_json) if images_json else []

        # Build note content
        note_parts = []
        if note_html:
            note_parts.append(f"**Notes**\n\n{note_html}")
        if images:
            for img in images:
                note_parts.append(f"![{img.get('name', 'image')}]({img.get('dataUrl', '')})")

        note_text = "\n\n".join(note_parts)
        full_explanation = explanation
        if note_text:
            full_explanation = f"{explanation}\n\n---\n{note_text}"

        filepath = self._obsidian.save_word(word, full_explanation, context=context)
        if filepath:
            self._status_action.setText(f"Saved: {word}")
        else:
            self._status_action.setText(f"Note saved: {word}")

        self._pending_save = {}
        self._result_card.hide()
        self._panel.set_idle()
        self._busy = False
        self._tray_icon.setIcon(self._idle_icon)

    def _on_translate_requested(self, text):
        """User right-clicked 'Translate to Chinese' on selected text."""
        _log(f"Translate requested: '{text[:50]}...'")
        self._status_action.setText(f"Translating...")
        self._trans_thread = QThread()
        self._trans_worker = TranslateWorker(text, self._llm_client)
        self._trans_worker.moveToThread(self._trans_thread)

        self._trans_thread.started.connect(self._trans_worker.run)
        self._trans_worker.finished.connect(self._on_translate_result)
        self._trans_worker.error.connect(self._on_translate_error)
        self._trans_worker.finished.connect(self._trans_thread.quit)
        self._trans_worker.error.connect(self._trans_thread.quit)
        self._trans_thread.finished.connect(self._trans_thread.deleteLater)

        self._trans_thread.start()

    def _on_translate_result(self, translation):
        """Show Chinese translation in a themed dialog."""
        _log(f"Translation result: '{translation[:60]}...'")
        self._status_action.setText("Translation done")
        dialog = TranslationDialog(
            self._trans_worker._text, translation
        )
        dialog.exec_()

    def _on_translate_error(self, error_msg):
        _log(f"Translation error: {error_msg}")
        self._status_action.setText(f"Translation error: {error_msg}")

    def _reset_after_recording(self):
        self._recording = False
        self._record_action.setEnabled(True)
        self._stop_action.setEnabled(False)

    # ── Context capture ────────────────────────────────────────

    def _on_context_capture(self):
        if (not self._config.obsidian_enabled
                or not self._config.obsidian_vault_path):
            self._status_action.setText(
                "Obsidian not configured for context capture"
            )
            return

        try:
            context = capture_context(
                vault_path=self._config.obsidian_vault_path,
                subfolder=self._config.obsidian_subfolder,
                attachments_subfolder=(
                    self._config.obsidian_attachments_subfolder
                )
            )
            self._context_buffer.set(context)
            parts = []
            if context.screenshot_path:
                parts.append("Screenshot captured")
            if context.clipboard_text:
                preview = context.clipboard_text[:40].replace("\n", " ")
                parts.append(f"Text: {preview}...")
            self._status_action.setText(" | ".join(parts) if parts
                                         else "Context captured")
        except Exception as e:
            self._status_action.setText(f"Capture failed: {e}")

    # ── Game name prompt ───────────────────────────────────────

    def _prompt_game_name(self):
        if (not self._config.obsidian_enabled
                or self._config.obsidian_save_mode != "journal"):
            return

        current_name = self._config.obsidian_game_name
        dialog = GameNameDialog(current_name)
        if dialog.exec_() == QDialog.Accepted:
            name = dialog.game_name
            if name:
                self._config.set("obsidian.game_name", name)
                self._obsidian.update_game_name(name)
                self._status_action.setText(f"Notebook: {name}")
        elif not current_name:
            self._status_action.setText("No game name set")

    # ── Error handling ─────────────────────────────────────────

    def _on_error(self, error_msg):
        self._tray_icon.showMessage(
            "LinguaSnap Error",
            error_msg,
            QSystemTrayIcon.Critical,
            5000
        )

    # ── Utilities ──────────────────────────────────────────────

    def _test_microphone(self):
        try:
            devices = AudioRecorder.list_input_devices()
            if not devices:
                QMessageBox.warning(
                    None, "Microphone Test",
                    "No microphone detected."
                )
                return
            msg = "Available microphones:\n\n"
            for d in devices:
                msg += f"  [{d['index']}] {d['name']}\n"
            QMessageBox.information(None, "Microphone Test", msg)
        except Exception as e:
            QMessageBox.warning(None, "Microphone Test", f"Error: {e}")

    def _open_config(self):
        config_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "config.json"
        )
        if sys.platform == "win32":
            os.startfile(config_path)
        else:
            subprocess.Popen(["open", config_path])

    def _open_settings(self):
        """Open the Settings dialog and apply changes if accepted."""
        dialog = SettingsDialog(self._config)
        if dialog.exec_() == QDialog.Accepted:
            self._apply_settings(dialog)

    def _apply_settings(self, dialog):
        """Apply changed settings to running components."""
        # LLM Client
        self._llm_client.update_config(
            base_url=self._config.llm_base_url,
            api_key=self._config.llm_api_key,
            model=self._config.llm_model
        )

        # TTS Engine
        self._tts.set_rate(self._config.tts_rate)

        # Obsidian Writer
        self._obsidian.update_config(
            vault_path=self._config.obsidian_vault_path,
            subfolder=self._config.obsidian_subfolder,
            include_game_name=self._config.get(
                "obsidian.include_game_name", False
            ),
            game_name=self._config.obsidian_game_name,
            save_mode=self._config.obsidian_save_mode,
            attachments_subfolder=self._config.obsidian_attachments_subfolder
        )

        # Whisper model change requires restart
        if dialog.whisper_changed:
            reply = QMessageBox.question(
                None,
                "Restart Required",
                "Whisper model settings have changed.\n"
                "A restart is required for changes to take effect.\n\n"
                "Restart now?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            if reply == QMessageBox.Yes:
                self._on_quit()
                QTimer.singleShot(500, lambda: os.execv(
                    sys.executable, [sys.executable] + sys.argv
                ))

    def _on_quit(self):
        self._tts.stop()
        if self._panel is not None:
            self._panel.close()
        if self._result_card is not None:
            self._result_card.close()
        self._tray_icon.hide()
        self.quit()


def main():
    _install_excepthook()

    # Enable faulthandler to catch native crashes (C extension segfaults)
    # that Python's excepthook cannot see. Writes to same log file.
    try:
        faulthandler.enable(file=open(_LOG_PATH, "a", encoding="utf-8"))
    except Exception:
        pass

    # Enable high-DPI scaling BEFORE QApplication is created
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    _log("=== LinguaSnap starting ===")
    app = LinguaSnapApp(sys.argv)
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
