"""Semi-transparent overlay window for displaying word explanations."""

from PyQt5.QtCore import (
    Qt, QTimer, QPropertyAnimation, QPoint, pyqtProperty, pyqtSignal
)
from PyQt5.QtGui import QPainter, QColor, QFont, QPainterPath, QBrush, QPen
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QApplication


class OverlayWindow(QWidget):
    """Frameless, semi-transparent, click-through overlay window.

    Positioned at the bottom-right corner of the primary screen.
    Displays word explanation with auto-dismiss and fade animation.
    """

    dismiss_requested = pyqtSignal()

    def __init__(self, duration_sec=10, parent=None):
        super().__init__(parent)

        self._duration_ms = duration_sec * 1000
        self._opacity = 0.0

        # Window flags: frameless, topmost, no taskbar entry, no focus
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.NoFocus
            | Qt.SubWindow
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)

        self.setFixedSize(420, 320)

        # Layout
        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(24, 20, 24, 20)
        self.layout().setSpacing(8)

        # Title label (the word)
        self._title_label = QLabel()
        self._title_label.setFont(QFont("Segoe UI", 16, QFont.Bold))
        self._title_label.setStyleSheet(
            "color: #ffffff; background: transparent;"
        )
        self._title_label.setWordWrap(True)
        self.layout().addWidget(self._title_label)

        # Content label (the explanation)
        self._content_label = QLabel()
        self._content_label.setFont(QFont("Segoe UI", 11))
        self._content_label.setStyleSheet(
            "color: #e0e0e0; background: transparent;"
        )
        self._content_label.setWordWrap(True)
        self.layout().addWidget(self._content_label)

        # Auto-dismiss timer
        self._dismiss_timer = QTimer(self)
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.timeout.connect(self._on_dismiss)

        # Fade animations
        self._fade_in = QPropertyAnimation(self, b"window_opacity")
        self._fade_in.setDuration(300)
        self._fade_in.setStartValue(0.0)
        self._fade_in.setEndValue(1.0)

        self._fade_out = QPropertyAnimation(self, b"window_opacity")
        self._fade_out.setDuration(500)
        self._fade_out.setStartValue(1.0)
        self._fade_out.setEndValue(0.0)
        self._fade_out.finished.connect(self.hide)
        self._fade_out.finished.connect(self.dismiss_requested.emit)

        # Refresh topmost periodically while visible
        self._topmost_timer = QTimer(self)
        self._topmost_timer.timeout.connect(self._reassert_topmost)

    def show_with_text(self, text, word=""):
        """Display the overlay with the given explanation.

        Args:
            text: The full explanation text (markdown-flavored).
            word: The original word being explained (shown as title).
        """
        # Parse word and explanation
        if word:
            self._title_label.setText(word.capitalize())
            self._content_label.setText(text)
        else:
            # Try to extract word from the first line
            lines = text.strip().split("\n")
            self._title_label.setText(lines[0].replace("**", "")
                                      if lines else "Word")
            self._content_label.setText(text)

        # Position at bottom-right
        self._position_at_corner()

        # Animate in
        self.setWindowOpacity(0.0)
        self.show()
        self._fade_in.start()

        # Start auto-dismiss and topmost refresh
        self._dismiss_timer.start(self._duration_ms)
        self._topmost_timer.start(1000)

    def _position_at_corner(self):
        """Position the window at the bottom-right corner of the primary screen."""
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geom = screen.availableGeometry()
        x = geom.right() - self.width() - 20
        y = geom.bottom() - self.height() - 20
        self.move(x, y)

    def _reassert_topmost(self):
        """Periodically reassert topmost position (for exclusive fullscreen games)."""
        if self.isVisible():
            self.raise_()
            # Force topmost via Windows API as a fallback
            try:
                from ctypes import windll
                hwnd = int(self.winId())
                windll.user32.SetWindowPos(
                    hwnd, -1, 0, 0, 0, 0, 0x0002 | 0x0001
                )
            except Exception:
                pass

    def _on_dismiss(self):
        """Start fade-out and eventual hide."""
        self._topmost_timer.stop()
        if self.isVisible():
            self._fade_out.setStartValue(self.windowOpacity())
            self._fade_out.start()

    def paintEvent(self, event):
        """Paint rounded rectangle background."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Rounded rect background
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 16, 16)

        # Semi-transparent dark fill
        painter.setBrush(QColor(18, 18, 24, 220))
        painter.setPen(Qt.NoPen)
        painter.drawPath(path)

        # Subtle border
        painter.setBrush(Qt.NoBrush)
        pen = QPen(QColor(255, 255, 255, 30))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawPath(path)

    # Property for QPropertyAnimation
    def get_window_opacity(self):
        return self._opacity

    def set_window_opacity(self, value):
        self._opacity = value
        self.setWindowOpacity(value)

    window_opacity = pyqtProperty(
        float, get_window_opacity, set_window_opacity
    )
