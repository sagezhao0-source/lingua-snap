"""Global hotkey listener using the keyboard library.

Tracks individual key states to detect when a multi-key combo
is fully pressed (start recording) and when it breaks (stop recording).
"""

from PyQt5.QtCore import QObject, pyqtSignal, QThread


class HotkeyListener(QObject):
    """Listens for a global hotkey combo using low-level Windows hooks.

    Emits separate signals for combo press and release, enabling
    push-to-talk behavior. Runs on a dedicated QThread.
    """

    hotkey_pressed = pyqtSignal()
    hotkey_released = pyqtSignal()
    hotkey_error = pyqtSignal(str)
    context_capture_triggered = pyqtSignal()

    def __init__(self, hotkey_str="ctrl+shift+f", context_hotkey_str=None):
        super().__init__()
        self._hotkey_str = hotkey_str
        self._context_hotkey_str = context_hotkey_str
        self._running = False
        self._thread = None

    def start(self):
        """Start the hotkey listener on a dedicated thread."""
        if self._running:
            return

        self._running = True
        self._thread = QThread()
        self.moveToThread(self._thread)
        self._thread.started.connect(self._run)
        self._thread.start()

    def _run(self):
        """Main loop running on the hotkey thread.

        Uses a global keyboard hook to track individual key states
        and detect when the full combo is pressed/released.
        Supports a second combo for context capture.
        """
        try:
            import keyboard

            key_map = {
                "ctrl": "ctrl", "control": "ctrl",
                "shift": "shift",
                "alt": "alt",
                "win": "windows", "cmd": "windows", "windows": "windows",
            }

            # Parse main combo
            parts = self._hotkey_str.lower().split("+")
            self._combo_keys = set()
            for p in parts:
                normalized = key_map.get(p, p)
                self._combo_keys.add(normalized)

            # Parse context combo (if configured)
            self._context_combo_keys = set()
            if self._context_hotkey_str:
                context_parts = self._context_hotkey_str.lower().split("+")
                for p in context_parts:
                    normalized = key_map.get(p, p)
                    self._context_combo_keys.add(normalized)

            # All tracked keys = union of both combos
            self._all_tracked_keys = (
                self._combo_keys | self._context_combo_keys
            )

            self._pressed_keys = set()
            self._combo_active = False
            self._context_fired = False

            keyboard.hook(self._hook_callback)
            keyboard.wait()

        except ImportError:
            self.hotkey_error.emit(
                "keyboard library not installed. Run: pip install keyboard"
            )
        except PermissionError:
            self.hotkey_error.emit(
                "Administrator privileges required for global hotkeys. "
                "Please run as administrator."
            )
        except Exception as e:
            self.hotkey_error.emit(f"Hotkey error: {e}")
        finally:
            self._running = False

    def _hook_callback(self, event):
        """Global keyboard hook callback.

        Tracks which keys are pressed and detects combo state transitions
        for both the main (push-to-talk) and context capture combos.
        """
        # Normalize the key name
        key_name = event.name.lower() if event.name else ""
        # Also check scan_code for modifier mapping
        if event.scan_code in (29, 361):  # Left/Right Control
            key_name = "ctrl"
        elif event.scan_code in (42, 54):  # Left/Right Shift
            key_name = "shift"
        elif event.scan_code in (56, 364):  # Left/Right Alt
            key_name = "alt"

        if key_name not in self._all_tracked_keys:
            return

        if event.event_type == "down":
            self._pressed_keys.add(key_name)

            # Main combo (push-to-talk): activates when all keys held
            if (not self._combo_active
                    and self._combo_keys.issubset(self._pressed_keys)):
                self._combo_active = True
                self.hotkey_pressed.emit()

            # Context capture combo: fires once per key-down cycle
            if (self._context_combo_keys
                    and not self._context_fired
                    and self._context_combo_keys.issubset(
                        self._pressed_keys)):
                self._context_fired = True
                self.context_capture_triggered.emit()

        elif event.event_type == "up":
            self._pressed_keys.discard(key_name)

            # Main combo ends when any required key is released
            if self._combo_active:
                self._combo_active = False
                self.hotkey_released.emit()

            # Reset context combo debounce when keys no longer satisfy it
            if self._context_fired and not self._context_combo_keys.issubset(
                    self._pressed_keys):
                self._context_fired = False

    def stop(self):
        """Stop the hotkey listener and clean up."""
        self._running = False
        try:
            import keyboard
            keyboard.unhook_all()
        except Exception:
            pass

        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(1000)

    def update_hotkey(self, new_hotkey, new_context_hotkey=None):
        """Update the hotkey combo(s) (stops and restarts listener)."""
        self._hotkey_str = new_hotkey
        if new_context_hotkey is not None:
            self._context_hotkey_str = new_context_hotkey
        was_running = self._running
        if was_running:
            self.stop()
        if was_running:
            self.start()
