"""Context capture: screenshot of foreground window + clipboard text.

Used by main.py to attach game-scene context to Obsidian word notes.
"""

import ctypes
import os
from ctypes import wintypes
from dataclasses import dataclass, field
from datetime import datetime
from threading import Lock
from typing import Optional


@dataclass
class ContextData:
    """Captured context associated with a word lookup."""
    screenshot_path: Optional[str] = None
    clipboard_text: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def has_content(self) -> bool:
        return self.screenshot_path is not None or bool(self.clipboard_text)


class ContextBuffer:
    """Thread-safe in-memory buffer for pending context.

    Context is captured before a word lookup and consumed
    when the lookup result is saved.
    """

    def __init__(self):
        self._data: Optional[ContextData] = None
        self._lock = Lock()

    def set(self, context: ContextData):
        with self._lock:
            self._data = context

    def get(self) -> Optional[ContextData]:
        with self._lock:
            return self._data

    def consume(self) -> Optional[ContextData]:
        """Get and clear the buffer atomically."""
        with self._lock:
            data = self._data
            self._data = None
            return data

    def clear(self):
        with self._lock:
            self._data = None


def _get_foreground_window_rect():
    """Get the bounding rectangle of the foreground window.

    Returns (left, top, right, bottom) or None on failure.
    """
    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        if hwnd == 0:
            return None

        rect = wintypes.RECT()
        result = ctypes.windll.user32.GetWindowRect(
            hwnd, ctypes.byref(rect)
        )
        if result == 0:
            return None

        if rect.right <= rect.left or rect.bottom <= rect.top:
            return None

        return (rect.left, rect.top, rect.right, rect.bottom)
    except Exception:
        return None


def capture_context(vault_path, subfolder, attachments_subfolder):
    """Capture screenshot of foreground window and clipboard text.

    Args:
        vault_path: Obsidian vault root path.
        subfolder: Subfolder within vault for LinguaSnap notes.
        attachments_subfolder: Subfolder for screenshots (under subfolder).

    Returns:
        ContextData with screenshot_path (relative to vault) and clipboard_text.
    """
    screenshot_path = None
    clipboard_text = None

    # 1. Screenshot of foreground window
    try:
        from PIL import ImageGrab
    except ImportError:
        ImageGrab = None

    if ImageGrab is not None and vault_path:
        try:
            rect = _get_foreground_window_rect()
            if rect is None:
                img = ImageGrab.grab()
            else:
                img = ImageGrab.grab(bbox=rect)

            # Save to vault subfolder
            attachments_dir = os.path.join(
                vault_path, subfolder, attachments_subfolder
            )
            os.makedirs(attachments_dir, exist_ok=True)

            timestamp_str = datetime.now().strftime("%Y%m%d-%H%M%S")
            filename = f"screenshot-{timestamp_str}.png"
            filepath = os.path.join(attachments_dir, filename)
            img.save(filepath, "PNG")

            # Store path relative to vault root (for Obsidian ![[links]])
            screenshot_path = os.path.join(
                subfolder, attachments_subfolder, filename
            )
        except Exception:
            screenshot_path = None

    # 2. Clipboard text
    try:
        from PyQt5.QtWidgets import QApplication
        app = QApplication.instance()
        if app is not None:
            cb = app.clipboard()
            if cb is not None:
                text = cb.text()
                if text and text.strip():
                    clipboard_text = text.strip()
    except Exception:
        clipboard_text = None

    return ContextData(
        screenshot_path=screenshot_path,
        clipboard_text=clipboard_text
    )
