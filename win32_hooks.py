import base64
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
from PySide6.QtCore import (
    QAbstractNativeEventFilter,
    QBuffer,
    QIODevice,
    QMimeData,
    QObject,
    QTimer,
    Signal,
)
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QApplication

WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_NOREPEAT = 0x4000
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004

VK_F9 = 0x78
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_LMENU = 0xA4
VK_RMENU = 0xA5
VK_C = 0x43
VK_V = 0x56
KEYEVENTF_KEYUP = 0x0002

HOTKEY_TOGGLE = 1      # F9
HOTKEY_CAPTURE = 2     # Ctrl + F9
HOTKEY_SWITCH = 3      # Shift + F9
HOTKEY_PIN = 4         # Ctrl + Shift + F9
HOTKEY_PASTE_LAST = 5  # Ctrl + Alt + F9

ABM_NEW = 0x00000000
ABM_REMOVE = 0x00000001
ABM_QUERYPOS = 0x00000002
ABM_SETPOS = 0x00000003

ABE_LEFT = 0
ABE_TOP = 1
ABE_RIGHT = 2
ABE_BOTTOM = 3

APPBAR_EDGE_MAP = {
    "left": ABE_LEFT,
    "top": ABE_TOP,
    "right": ABE_RIGHT,
    "bottom": ABE_BOTTOM,
}

WM_APPBAR_CALLBACK = 0x0409
GWL_STYLE = -16
GWL_EXSTYLE = -20
WS_CHILD = 0x40000000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
SW_MAXIMIZE = 3
SW_RESTORE = 9
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
DWMWA_EXTENDED_FRAME_BOUNDS = 9

_IGNORED_WINDOW_CLASSES = {
    "Progman",
    "WorkerW",
    "Shell_TrayWnd",
    "Shell_SecondaryTrayWnd",
    "Windows.UI.Core.CoreWindow",
    "XamlExplorerHostIslandWindow",
    "TopLevelWindowForOverflowXamlIsland",
    "DV2ControlHost",
    "MsgrIMEWindowClass",
    "SysShadow",
}


class APPBARDATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uCallbackMessage", wintypes.UINT),
        ("uEdge", wintypes.UINT),
        ("rc", wintypes.RECT),
        ("lParam", wintypes.LPARAM),
    ]


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
    sig_toggle_pin = Signal()
    sig_paste_last_clip = Signal()
    sig_clip_captured = Signal(str, str)  # (content, source_type: 'text'|'url'|'path'|'image')

    def __init__(self, parent=None):
        super().__init__(parent)
        self.user32 = ctypes.windll.user32
        self.shell32 = ctypes.windll.shell32
        self.dwmapi = getattr(ctypes.windll, "dwmapi", None)
        self.hwnd: int = 0
        self.last_active_hwnd: int = 0
        self.hotkeys_paused: bool = False
        self.appbar_registered: bool = False
        self.appbar_hwnd: int = 0
        self.appbar_edge: str = "right"
        self._pushed_windows: dict[int, dict] = {}
        self._force_window_push_in_tests: bool = False
        self._paste_seq: int = 0
        self._paste_backup_mime: QMimeData | None = None
        self._filter = _NativeHotkeyFilter(self._on_wm_hotkey)

    def install(self, app: QApplication, window_hwnd: int) -> None:
        """Installs the event filter and registers global F9 hotkeys."""
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
            (
                HOTKEY_PIN,
                MOD_NOREPEAT | MOD_CONTROL | MOD_SHIFT,
                VK_F9,
                "Ctrl+Shift+F9",
            ),
            (
                HOTKEY_PASTE_LAST,
                MOD_NOREPEAT | MOD_CONTROL | MOD_ALT,
                VK_F9,
                "Ctrl+Alt+F9",
            ),
        ]
        for hk_id, modifiers, vk, label in bindings:
            ok = self.user32.RegisterHotKey(self.hwnd, hk_id, modifiers, vk)
            if not ok:
                print(f"[Win32HookManager] Warning: Could not register global hotkey {label}")

    def unregister_all_hotkeys(self) -> None:
        if not self.hwnd:
            return
        for hk_id in (
            HOTKEY_TOGGLE,
            HOTKEY_CAPTURE,
            HOTKEY_SWITCH,
            HOTKEY_PIN,
            HOTKEY_PASTE_LAST,
        ):
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

    @staticmethod
    def _clamp_appbar_rect(
        rc: wintypes.RECT,
        edge: str,
        phys_thickness: int,
        bounds: tuple[int, int, int, int] | None = None,
    ) -> None:
        if bounds is not None:
            rc.left, rc.top, rc.right, rc.bottom = bounds
        if edge == "left":
            rc.right = rc.left + phys_thickness
        elif edge == "right":
            rc.left = rc.right - phys_thickness
        elif edge == "top":
            rc.bottom = rc.top + phys_thickness
        elif edge == "bottom":
            rc.top = rc.bottom - phys_thickness

    @staticmethod
    def _fallback_logical_rect(
        edge: str, left: int, top: int, width: int, height: int, thickness: int
    ) -> tuple[int, int, int, int]:
        if edge in ("left", "right"):
            w = max(1, min(int(thickness), int(width)))
            x = int(left) if edge == "left" else int(left) + int(width) - w
            return (x, int(top), w, int(height))
        h = max(1, min(int(thickness), int(height)))
        y = int(top) if edge == "top" else int(top) + int(height) - h
        return (int(left), y, int(width), h)

    @staticmethod
    def _compute_remaining_rect(
        edge: str, left: int, top: int, right: int, bottom: int, thickness: int
    ) -> tuple[int, int, int, int]:
        if edge == "left":
            return (min(right - 100, left + thickness), top, right, bottom)
        if edge == "top":
            return (left, min(bottom - 100, top + thickness), right, bottom)
        if edge == "bottom":
            return (left, top, right, max(top + 100, bottom - thickness))
        return (left, top, max(left + 100, right - thickness), bottom)

    def _get_dwm_frame_padding(self, hwnd: int) -> tuple[int, int, int, int]:
        if not self.dwmapi:
            return (0, 0, 0, 0)
        rc = wintypes.RECT()
        ext = wintypes.RECT()
        if not self.user32.GetWindowRect(hwnd, ctypes.byref(rc)):
            return (0, 0, 0, 0)
        try:
            hr = self.dwmapi.DwmGetWindowAttribute(
                hwnd,
                DWMWA_EXTENDED_FRAME_BOUNDS,
                ctypes.byref(ext),
                ctypes.sizeof(ext),
            )
        except Exception:
            return (0, 0, 0, 0)
        if hr != 0:
            return (0, 0, 0, 0)
        pad_l = max(0, min(20, int(ext.left) - int(rc.left)))
        pad_t = max(0, min(20, int(ext.top) - int(rc.top)))
        pad_r = max(0, min(20, int(rc.right) - int(ext.right)))
        pad_b = max(0, min(20, int(rc.bottom) - int(ext.bottom)))
        return (pad_l, pad_t, pad_r, pad_b)

    def push_windows_for_appbar(
        self,
        sidebar_hwnd: int,
        edge: str,
        mon_rect: tuple[int, int, int, int],
        appbar_rect: tuple[int, int, int, int],
        rem_rect: tuple[int, int, int, int],
    ) -> list[int]:
        """Resizes overlapping background app windows on the monitor into rem_rect."""
        if (
            os.environ.get("QT_QPA_PLATFORM") == "offscreen"
            and not self._force_window_push_in_tests
        ):
            return []

        mon_left, mon_top, mon_right, mon_bottom = mon_rect
        candidates: list[int] = []
        seen: set[int] = set()

        def _add_candidate(h: int) -> None:
            hi = int(h or 0)
            if hi and hi not in seen:
                seen.add(hi)
                candidates.append(hi)

        if self.last_active_hwnd and self.user32.IsWindow(self.last_active_hwnd):
            _add_candidate(self.last_active_hwnd)

        for prev_hwnd in list(self._pushed_windows.keys()):
            if self.user32.IsWindow(prev_hwnd):
                _add_candidate(prev_hwnd)

        enum_handles: list[int] = []
        wndenum_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def _enum_cb(hwnd, _lparam):
            enum_handles.append(int(hwnd))
            return True

        cb_ref = wndenum_type(_enum_cb)
        try:
            self.user32.EnumWindows(cb_ref, 0)
        except Exception:
            pass
        for h in enum_handles:
            _add_candidate(h)

        our_pid = os.getpid()
        pushed: list[int] = []
        buf = ctypes.create_unicode_buffer(128)
        pid = wintypes.DWORD()

        for w in candidates:
            if w == sidebar_hwnd:
                continue
            if not self.user32.IsWindowVisible(w) or self.user32.IsIconic(w):
                continue

            if not self._force_window_push_in_tests:
                pid.value = 0
                self.user32.GetWindowThreadProcessId(w, ctypes.byref(pid))
                if pid.value == our_pid:
                    continue

            style = int(self.user32.GetWindowLongW(w, GWL_STYLE) or 0)
            ex_style = int(self.user32.GetWindowLongW(w, GWL_EXSTYLE) or 0)
            if (style & WS_CHILD) or (ex_style & (WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE)):
                continue

            cls_len = self.user32.GetClassNameW(w, buf, 128)
            cls_name = buf.value if cls_len else ""
            if cls_name in _IGNORED_WINDOW_CLASSES:
                continue

            rc = wintypes.RECT()
            if not self.user32.GetWindowRect(w, ctypes.byref(rc)):
                continue
            cur_rect = (int(rc.left), int(rc.top), int(rc.right), int(rc.bottom))
            currently_zoomed = bool(self.user32.IsZoomed(w))
            pad_l, pad_t, pad_r, pad_b = self._get_dwm_frame_padding(w)
            orig_candidate = (
                (mon_left - pad_l, mon_top - pad_t, mon_right + pad_r, mon_bottom + pad_b)
                if currently_zoomed
                else cur_rect
            )

            cx = (cur_rect[0] + cur_rect[2]) // 2
            cy = (cur_rect[1] + cur_rect[3]) // 2
            if not (mon_left <= cx <= mon_right and mon_top <= cy <= mon_bottom):
                continue

            ref_rect = (
                self._pushed_windows[w]["orig_rect"]
                if w in self._pushed_windows
                else orig_candidate
            )
            is_zoomed = currently_zoomed or bool(
                self._pushed_windows.get(w, {}).get("was_zoomed")
            )
            vis_rect = (
                ref_rect[0] + pad_l,
                ref_rect[1] + pad_t,
                ref_rect[2] - pad_r,
                ref_rect[3] - pad_b,
            )
            is_large = (vis_rect[2] - vis_rect[0]) >= int(
                (mon_right - mon_left) * 0.5
            ) and (vis_rect[3] - vis_rect[1]) >= int((mon_bottom - mon_top) * 0.5)
            overlaps_appbar = (
                vis_rect[2] > appbar_rect[0] + 2
                and vis_rect[0] < appbar_rect[2] - 2
                and vis_rect[3] > appbar_rect[1] + 2
                and vis_rect[1] < appbar_rect[3] - 2
            )
            if not (overlaps_appbar and (w == self.last_active_hwnd or is_zoomed or is_large)):
                continue

            if w not in self._pushed_windows:
                self._pushed_windows[w] = {
                    "orig_rect": orig_candidate,
                    "was_zoomed": currently_zoomed,
                }

            tx = rem_rect[0] - pad_l
            ty = rem_rect[1] - pad_t
            tw = max(200, (rem_rect[2] - rem_rect[0]) + pad_l + pad_r)
            th = max(150, (rem_rect[3] - rem_rect[1]) + pad_t + pad_b)
            self.user32.SetWindowPos(
                w, 0, tx, ty, tw, th, SWP_NOZORDER | SWP_NOACTIVATE
            )
            pushed.append(w)

        return pushed

    def restore_pushed_windows(self) -> int:
        """Restores previously pushed windows back to their original rects and maximized state."""
        restored = 0
        for w, info in list(self._pushed_windows.items()):
            if self.user32.IsWindow(w):
                ol, ot, or_, ob = info["orig_rect"]
                self.user32.SetWindowPos(
                    w,
                    0,
                    ol,
                    ot,
                    max(100, or_ - ol),
                    max(100, ob - ot),
                    SWP_NOZORDER | SWP_NOACTIVATE,
                )
                if info.get("was_zoomed") and not self.user32.IsZoomed(w):
                    self.user32.ShowWindow(w, SW_MAXIMIZE)
                restored += 1
        self._pushed_windows.clear()
        return restored

    def register_appbar(
        self,
        hwnd: int,
        edge: str,
        screen_rect: tuple[int, int, int, int],
        thickness: int,
        dpi_scale: float = 1.0,
    ) -> tuple[int, int, int, int]:
        """Registers/updates a Windows AppBar work-area reservation on the given screen edge."""
        norm_edge = (edge or "right").lower()
        if norm_edge not in APPBAR_EDGE_MAP:
            norm_edge = "right"

        left, top, width, height = (int(v) for v in screen_rect)
        scale = float(dpi_scale) if dpi_scale and dpi_scale > 0 else 1.0

        if not hwnd:
            return self._fallback_logical_rect(norm_edge, left, top, width, height, thickness)

        target_hwnd = int(hwnd)
        if self.appbar_registered and self.appbar_hwnd and self.appbar_hwnd != target_hwnd:
            self.unregister_appbar(self.appbar_hwnd)

        phys_left = int(round(left * scale))
        phys_top = int(round(top * scale))
        phys_right = int(round((left + width) * scale))
        phys_bottom = int(round((top + height) * scale))
        phys_thickness = max(1, int(round(thickness * scale)))

        abd = APPBARDATA()
        abd.cbSize = ctypes.sizeof(APPBARDATA)
        abd.hWnd = target_hwnd
        abd.uCallbackMessage = WM_APPBAR_CALLBACK
        abd.uEdge = APPBAR_EDGE_MAP[norm_edge]

        if not self.appbar_registered:
            self.shell32.SHAppBarMessage(ABM_NEW, ctypes.byref(abd))
            self.appbar_registered = True
            self.appbar_hwnd = target_hwnd

        self.appbar_edge = norm_edge
        phys_bounds = (phys_left, phys_top, phys_right, phys_bottom)
        abd.rc = wintypes.RECT(*phys_bounds)
        self._clamp_appbar_rect(abd.rc, norm_edge, phys_thickness, bounds=phys_bounds)
        self.shell32.SHAppBarMessage(ABM_QUERYPOS, ctypes.byref(abd))
        self._clamp_appbar_rect(abd.rc, norm_edge, phys_thickness, bounds=phys_bounds)
        self.shell32.SHAppBarMessage(ABM_SETPOS, ctypes.byref(abd))
        self._clamp_appbar_rect(abd.rc, norm_edge, phys_thickness, bounds=phys_bounds)

        appbar_phys = (
            int(abd.rc.left),
            int(abd.rc.top),
            int(abd.rc.right),
            int(abd.rc.bottom),
        )
        rem_phys = self._compute_remaining_rect(
            norm_edge, phys_left, phys_top, phys_right, phys_bottom, phys_thickness
        )
        self.push_windows_for_appbar(
            target_hwnd,
            norm_edge,
            (phys_left, phys_top, phys_right, phys_bottom),
            appbar_phys,
            rem_phys,
        )

        out_x = int(round(abd.rc.left / scale))
        out_y = int(round(abd.rc.top / scale))
        out_w = max(1, int(round((abd.rc.right - abd.rc.left) / scale)))
        out_h = max(1, int(round((abd.rc.bottom - abd.rc.top) / scale)))
        return (out_x, out_y, out_w, out_h)

    def unregister_appbar(
        self, hwnd: int | None = None, restore_windows: bool = True
    ) -> bool:
        """Unregisters the active Windows AppBar reservation and restores pushed windows."""
        target_hwnd = int(hwnd) if hwnd is not None else (self.appbar_hwnd or self.hwnd)
        if not self.appbar_registered or not target_hwnd:
            self.appbar_registered = False
            self.appbar_hwnd = 0
            if restore_windows and self._pushed_windows:
                self.restore_pushed_windows()
            return False

        abd = APPBARDATA()
        abd.cbSize = ctypes.sizeof(APPBARDATA)
        abd.hWnd = target_hwnd
        self.shell32.SHAppBarMessage(ABM_REMOVE, ctypes.byref(abd))
        self.appbar_registered = False
        self.appbar_hwnd = 0
        if restore_windows:
            self.restore_pushed_windows()
        return True

    def _on_wm_hotkey(self, hotkey_id: int) -> None:
        if self.hotkeys_paused:
            return
        if hotkey_id == HOTKEY_TOGGLE:
            self.sig_toggle_sidebar.emit()
        elif hotkey_id == HOTKEY_SWITCH:
            self.sig_switch_panel.emit()
        elif hotkey_id == HOTKEY_PIN:
            self.sig_toggle_pin.emit()
        elif hotkey_id == HOTKEY_PASTE_LAST:
            self.sig_paste_last_clip.emit()
        elif hotkey_id == HOTKEY_CAPTURE:
            self.capture_active_selection()

    @staticmethod
    def _decode_image_data_uri(data_uri: str) -> QImage:
        raw = (data_uri or "").strip()
        if not raw.startswith("data:image/") or "," not in raw:
            return QImage()
        try:
            b64_part = raw.split(",", 1)[1]
            return QImage.fromData(base64.b64decode(b64_part))
        except Exception:
            return QImage()

    def paste_into_active_window(self, content: str, source_type: str = "text") -> bool:
        """Places captured text or image on the clipboard, sends Ctrl+V, then restores clipboard."""
        raw = content or ""
        is_image = source_type == "image" or raw.strip().startswith("data:image/")
        img = QImage()
        if is_image:
            img = self._decode_image_data_uri(raw)
            if img.isNull():
                return False
        elif not raw:
            return False

        clipboard = QApplication.clipboard()
        self._paste_seq += 1
        seq = self._paste_seq
        if self._paste_backup_mime is None:
            self._paste_backup_mime = self._clone_mime_data(clipboard.mimeData())

        if is_image:
            clipboard.setImage(img)
        else:
            clipboard.setText(raw)

        if not (
            os.environ.get("QT_QPA_PLATFORM") == "offscreen"
            and isinstance(self.user32, ctypes.WinDLL)
        ):
            for key_vk in (VK_F9, VK_MENU, VK_LMENU, VK_RMENU):
                self.user32.keybd_event(key_vk, 0, KEYEVENTF_KEYUP, 0)
            self.user32.keybd_event(VK_CONTROL, 0, 0, 0)
            self.user32.keybd_event(VK_V, 0, 0, 0)
            self.user32.keybd_event(VK_V, 0, KEYEVENTF_KEYUP, 0)
            self.user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)

        QTimer.singleShot(120, lambda s=seq: self._finalize_paste(s))
        return True

    def _restore_clipboard(self, backup: QMimeData | None) -> None:
        clipboard = QApplication.clipboard()
        if backup is None or (not backup.formats() and not backup.hasImage()):
            clipboard.clear()
            return
        formats = set(backup.formats())
        if backup.hasImage() and not backup.hasUrls() and not backup.hasHtml():
            img = self._extract_mime_image(backup)
            if not img.isNull():
                clipboard.setImage(img)
                return
        if backup.hasText() and formats <= {"text/plain"}:
            clipboard.setText(backup.text())
            return
        clipboard.setMimeData(backup)

    def _finalize_paste(self, seq: int) -> None:
        if seq != self._paste_seq or self._paste_backup_mime is None:
            return
        backup = self._paste_backup_mime
        self._paste_backup_mime = None
        self._restore_clipboard(backup)

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

    @staticmethod
    def _encode_image_data_uri(image: QImage) -> str:
        if image is None or image.isNull():
            return ""
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buf, "PNG")
        b64 = base64.b64encode(bytes(buf.data())).decode("ascii")
        return f"data:image/png;base64,{b64}"

    @staticmethod
    def _extract_mime_image(mime: QMimeData | None) -> QImage:
        if mime is None or not mime.hasImage():
            return QImage()
        img_data = mime.imageData()
        if isinstance(img_data, QImage):
            return img_data
        if isinstance(img_data, QPixmap):
            return img_data.toImage()
        return QImage()

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

            # 3. Otherwise inspect newly copied image data from Ctrl+C
            if not captured_text and new_mime.hasImage():
                img = self._extract_mime_image(new_mime)
                if img.isNull():
                    img = clipboard.image()
                if not img.isNull():
                    captured_text = self._encode_image_data_uri(img)
                    source_type = "image"

        # 4. Fallback: capture screenshot/image already sitting on the clipboard (e.g. Win+Shift+S)
        if not captured_text and backup_mime is not None and backup_mime.hasImage():
            img = self._extract_mime_image(backup_mime)
            if not img.isNull():
                captured_text = self._encode_image_data_uri(img)
                source_type = "image"

        # Restore original clipboard contents
        self._restore_clipboard(backup_mime)

        if captured_text:
            self.sig_clip_captured.emit(captured_text, source_type)

    @staticmethod
    def _clone_mime_data(src: QMimeData) -> QMimeData:
        clone = QMimeData()
        if src is None:
            return clone
        for fmt in src.formats():
            if fmt == "application/x-qt-image":
                continue
            clone.setData(fmt, src.data(fmt))
        if src.hasImage():
            clone.setImageData(src.imageData())
        return clone