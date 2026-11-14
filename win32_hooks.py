import ctypes
from ctypes import wintypes
from pathlib import Path
from PySide6.QtCore import QAbstractNativeEventFilter, QMimeData, QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication

WM_HOTKEY = 0x0312
MOD_NOREPEAT = 0x4000
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004

VK_F9 = 0x78
VK_CONTROL = 0x11
VK_C = 0x43
KEYEVENTF_KEYUP = 0x0002

HOTKEY_TOGGLE = 1   # F9
HOTKEY_CAPTURE = 2  # Ctrl + F9
HOTKEY_SWITCH = 3   # Shift + F9


class _NativeHotkeyFilter(QAbstractNativeEventFilter):
    """Receives raw Windows WM_HOTKEY messages and forwards them to Win32HookManager."""

    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def nativeEventFilter(self, event_type, message):
        if event_type == b"windows_generic_MSG":
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY:
                self.callback(int(msg.wParam))
                return True, 0
        return False, 0


class Win32HookManager(QObject):
    sig_toggle_sidebar = Signal()
    sig_switch_panel = Signal()
    sig_clip_captured = Signal(str, str)  # (content, source_type: 'text'|'url'|'path')

    def __init__(self, parent=None):
        super().__init__(parent)
        self.user32 = ctypes.windll.user32
        self.hwnd: int = 0
        self.last_active_hwnd: int = 0
        self.hotkeys_paused: bool = False
        self._filter = _NativeHotkeyFilter(self._on_wm_hotkey)

    def install(self, app: QApplication, window_hwnd: int) -> None:
        """Installs the event filter and registers F9, Ctrl+F9, and Shift+F9."""
        self.hwnd = int(window_hwnd)
        app.installNativeEventFilter(self._filter)
        self.register_all_hotkeys()

    def register_all_hotkeys(self) -> None:
        if not self.hwnd:
            return
        bindings = [
            (HOTKEY_TOGGLE, MOD_NOREPEAT, VK_F9, "F9"),
            (HOTKEY_CAPTURE, MOD_NOREPEAT | MOD_CONTROL, VK_F9, "Ctrl+F9"),
            (HOTKEY_SWITCH, MOD_NOREPEAT | MOD_SHIFT, VK_F9, "Shift+F9"),
        ]
        for hk_id, modifiers, vk, label in bindings:
            ok = self.user32.RegisterHotKey(self.hwnd, hk_id, modifiers, vk)
            if not ok:
                print(f"[Win32HookManager] Warning: Could not register global hotkey {label}")

    def unregister_all_hotkeys(self) -> None:
        if not self.hwnd:
            return
        for hk_id in (HOTKEY_TOGGLE, HOTKEY_CAPTURE, HOTKEY_SWITCH):
            self.user32.UnregisterHotKey(self.hwnd, hk_id)

    def remember_foreground_window(self, sidebar_hwnd: int) -> None:
        """Saves the active window HWND before the sidebar takes focus."""
        fg = self.user32.GetForegroundWindow()
        if fg and fg != sidebar_hwnd:
            self.last_active_hwnd = fg

    def restore_foreground_window(self) -> None:
        """Restores focus to the window the user was working in."""
        if self.last_active_hwnd and self.user32.IsWindow(self.last_active_hwnd):
            self.user32.SetForegroundWindow(self.last_active_hwnd)

    def _on_wm_hotkey(self, hotkey_id: int) -> None:
        if self.hotkeys_paused:
            return
        if hotkey_id == HOTKEY_TOGGLE:
            self.sig_toggle_sidebar.emit()
        elif hotkey_id == HOTKEY_SWITCH:
            self.sig_switch_panel.emit()
        elif hotkey_id == HOTKEY_CAPTURE:
            self.capture_active_selection()

    def capture_active_selection(self) -> None:
        """Silently copies the active selection, classifies it, and restores the clipboard."""
        clipboard = QApplication.clipboard()
        backup_mime = self._clone_mime_data(clipboard.mimeData())

        # Clear clipboard sentinel so we can detect if Ctrl+C captured anything new
        clipboard.clear()

        # Release F9 key-down state and synthesize Ctrl+C in the active window
        self.user32.keybd_event(VK_F9, 0, KEYEVENTF_KEYUP, 0)
        self.user32.keybd_event(VK_CONTROL, 0, 0, 0)
        self.user32.keybd_event(VK_C, 0, 0, 0)
        self.user32.keybd_event(VK_C, 0, KEYEVENTF_KEYUP, 0)
        self.user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)

        # Wait 75ms for the target application to populate the Windows clipboard
        QTimer.singleShot(75, lambda: self._finalize_capture(backup_mime))

    def _finalize_capture(self, backup_mime: QMimeData) -> None:
        clipboard = QApplication.clipboard()
        new_mime = clipboard.mimeData()

        captured_text = ""
        source_type = "text"

        if new_mime is not None:
            # 1. Check if files/folders were selected in File Explorer
            if new_mime.hasUrls():
                local_paths = [u.toLocalFile() for u in new_mime.urls() if u.isLocalFile()]
                if local_paths:
                    captured_text = "\n".join(str(Path(p)) for p in local_paths)
                    source_type = "path"

            # 2. Otherwise inspect plain text / web URLs
            if not captured_text and new_mime.hasText():
                raw = new_mime.text().strip()
                if raw:
                    captured_text = raw
                    if raw.startswith(("http://", "https://")) and "\n" not in raw:
                        source_type = "url"
                    elif Path(raw).is_absolute() and Path(raw).exists():
                        source_type = "path"

        # Restore original clipboard contents
        clipboard.setMimeData(backup_mime)

        if captured_text:
            self.sig_clip_captured.emit(captured_text, source_type)

    @staticmethod
    def _clone_mime_data(src: QMimeData) -> QMimeData:
        clone = QMimeData()
        if src is None:
            return clone
        for fmt in src.formats():
            clone.setData(fmt, src.data(fmt))
        return clone