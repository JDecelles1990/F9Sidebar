import ast
import operator as _op
from pathlib import Path
import sys
from typing import Callable, List, Optional

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QMimeData,
    QPoint,
    QPropertyAnimation,
    QRect,
    QRectF,
    Qt,
    QTimer,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QCursor,
    QGuiApplication,
    QKeyEvent,
    QKeySequence,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QShortcut,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QListWidget,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
import qtawesome as qta

try:
    from shiboken6 import isValid as _qt_is_valid
except ImportError:  # pragma: no cover - shiboken6 ships with PySide6
    def _qt_is_valid(obj) -> bool:
        return obj is not None

from ui.button_fx import install_button_fx
from ui.toast_popup import ToastPopup


class SunsetHorizonBar(QWidget):
    """Animated 3px shimmering sunset horizon accent bar displayed under the header."""

    _STOPS = (
        QColor("#F9E2AF"),
        QColor("#FAB387"),
        QColor("#F38BA8"),
        QColor("#CBA6F7"),
        QColor("#89B4FA"),
        QColor("#F9E2AF"),
    )

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("SunsetHorizonBar")
        self.setFixedHeight(3)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._phase = 0.0

        self.phase_anim = QVariantAnimation(self)
        self.phase_anim.setStartValue(0.0)
        self.phase_anim.setEndValue(1.0)
        self.phase_anim.setDuration(3200)
        self.phase_anim.setLoopCount(-1)
        self.phase_anim.valueChanged.connect(self._on_phase_changed)

    def _on_phase_changed(self, value) -> None:
        self._phase = float(value) % 1.0
        self.update()

    def start(self) -> None:
        if self.phase_anim.state() != QVariantAnimation.State.Running:
            self.phase_anim.start()

    def stop(self) -> None:
        if self.phase_anim.state() != QVariantAnimation.State.Stopped:
            self.phase_anim.stop()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.start()

    def hideEvent(self, event) -> None:
        self.stop()
        super().hideEvent(event)

    @classmethod
    def _sample_color(cls, t: float) -> QColor:
        u = (float(t) % 1.0) * (len(cls._STOPS) - 1)
        idx = int(u)
        frac = u - idx
        c1 = cls._STOPS[idx]
        c2 = cls._STOPS[idx + 1]
        return QColor(
            int(c1.red() + (c2.red() - c1.red()) * frac),
            int(c1.green() + (c2.green() - c1.green()) * frac),
            int(c1.blue() + (c2.blue() - c1.blue()) * frac),
        )

    def paintEvent(self, event) -> None:
        if self.width() <= 0 or self.height() <= 0:
            return
        grad = QLinearGradient(0.0, 0.0, float(self.width()), 0.0)
        for step in (0.0, 0.2, 0.4, 0.6, 0.8, 1.0):
            grad.setColorAt(step, self._sample_color(step - self._phase))

        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(grad))
            painter.drawRoundedRect(QRectF(self.rect()), 1.5, 1.5)
        finally:
            painter.end()


class SunsetFadeOverlay(QWidget):
    """Lightweight sunset-tinted veil overlay for smooth panel and tab transitions."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("SunsetFadeOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.progress = 1.0

        self.anim = QVariantAnimation(self)
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.setDuration(165)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.anim.valueChanged.connect(self._on_anim_value)
        self.anim.finished.connect(self._on_anim_finished)
        parent.installEventFilter(self)
        self.hide()

    def trigger(self, duration_ms: int = 165) -> bool:
        parent = self.parentWidget()
        if parent is None or not parent.isVisible() or parent.width() <= 0 or parent.height() <= 0:
            self.progress = 1.0
            self.hide()
            return False
        self.anim.stop()
        self.anim.setDuration(max(60, int(duration_ms)))
        self.setGeometry(parent.rect())
        self.progress = 0.0
        self.show()
        self.raise_()
        self.anim.start()
        return True

    def _on_anim_value(self, value) -> None:
        self.progress = max(0.0, min(1.0, float(value)))
        self.update()

    def _on_anim_finished(self) -> None:
        self.progress = 1.0
        self.hide()

    def eventFilter(self, obj, event) -> bool:
        if obj is self.parentWidget() and event.type() == QEvent.Type.Resize and self.isVisible():
            self.setGeometry(obj.rect())
        return super().eventFilter(obj, event)

    def paintEvent(self, event) -> None:
        remaining = max(0.0, 1.0 - self.progress)
        if remaining <= 0.01 or self.width() <= 0 or self.height() <= 0:
            return
        painter = QPainter(self)
        try:
            painter.setPen(Qt.PenStyle.NoPen)
            veil = QColor("#241E36")
            veil.setAlpha(int(175 * remaining))
            painter.fillRect(self.rect(), veil)

            glow_grad = QLinearGradient(0.0, 0.0, float(self.width()), 0.0)
            c_peach = QColor("#FAB387")
            c_pink = QColor("#F38BA8")
            c_lav = QColor("#CBA6F7")
            top_alpha = int(215 * remaining)
            for c in (c_peach, c_pink, c_lav):
                c.setAlpha(top_alpha)
            glow_grad.setColorAt(0.0, c_peach)
            glow_grad.setColorAt(0.5, c_pink)
            glow_grad.setColorAt(1.0, c_lav)
            painter.fillRect(0, 0, self.width(), 2, QBrush(glow_grad))
        finally:
            painter.end()


def _is_droppable_mime(mime: QMimeData | None) -> bool:
    """Returns True when MIME data carries external files, URLs, text, or images."""
    if mime is None:
        return False
    return bool(
        mime.hasUrls()
        or mime.hasText()
        or mime.hasImage()
        or mime.hasFormat("application/x-f9sidebar-note-image")
    )


class DroppablePanelSwitchBtn(QPushButton):
    """Panel switcher pill supporting drag-hover auto-switch and direct external drops."""

    def __init__(
        self,
        text: str,
        panel_index: int,
        on_hover_switch: Callable[[int], None],
        on_external_drop: Callable[[int, QMimeData, Qt.KeyboardModifiers], bool],
        parent: QWidget | None = None,
    ):
        super().__init__(text, parent)
        self.panel_index = int(panel_index)
        self._on_hover_switch = on_hover_switch
        self._on_external_drop = on_external_drop
        self.setAcceptDrops(True)

        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.setInterval(350)
        self._hover_timer.timeout.connect(
            lambda: self._on_hover_switch(self.panel_index)
        )

    def dragEnterEvent(self, event) -> None:
        if _is_droppable_mime(event.mimeData()):
            if not self._hover_timer.isActive():
                self._hover_timer.start()
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if _is_droppable_mime(event.mimeData()):
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dragLeaveEvent(self, event) -> None:
        self._hover_timer.stop()
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:
        self._hover_timer.stop()
        if not _is_droppable_mime(event.mimeData()):
            super().dropEvent(event)
            return
        self._on_hover_switch(self.panel_index)
        self._on_external_drop(
            self.panel_index, event.mimeData(), event.modifiers()
        )
        event.acceptProposedAction()


_MATH_BIN_OPS = {
    ast.Add: _op.add,
    ast.Sub: _op.sub,
    ast.Mult: _op.mul,
    ast.Div: _op.truediv,
    ast.FloorDiv: _op.floordiv,
    ast.Mod: _op.mod,
    ast.Pow: _op.pow,
}
_MATH_UNARY_OPS = {
    ast.UAdd: _op.pos,
    ast.USub: _op.neg,
}


def evaluate_math_query(query: str) -> Optional[str]:
    """Safely evaluates an inline arithmetic expression (or '= expr') and returns formatted result."""
    raw = (query or "").strip()
    if not raw:
        return None
    has_eq = raw.startswith("=")
    expr = raw[1:].strip() if has_eq else raw
    if not expr:
        return None
    if not has_eq:
        if not any(ch in expr for ch in "+-*/%"):
            return None
        if not all(ch.isdigit() or ch in ".+-*/%() " for ch in expr):
            return None
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        return None

    def _eval(node):
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
                raise ValueError("Invalid constant")
            return float(node.value)
        if isinstance(node, ast.UnaryOp) and type(node.op) in _MATH_UNARY_OPS:
            return _MATH_UNARY_OPS[type(node.op)](_eval(node.operand))
        if isinstance(node, ast.BinOp) and type(node.op) in _MATH_BIN_OPS:
            left = _eval(node.left)
            right = _eval(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 1000:
                raise ValueError("Exponent too large")
            if isinstance(node.op, (ast.Div, ast.FloorDiv, ast.Mod)) and right == 0:
                raise ZeroDivisionError()
            return _MATH_BIN_OPS[type(node.op)](left, right)
        raise ValueError("Unsupported AST node")

    try:
        val = _eval(tree)
    except Exception:
        return None
    if not isinstance(val, (int, float)) or abs(val) == float("inf") or val != val:
        return None
    if abs(val - round(val)) < 1e-12:
        return str(int(round(val)))
    formatted = f"{val:.6f}".rstrip("0").rstrip(".")
    return formatted if formatted != "-0" else "0"


def _resolve_startup_callbacks():
    for mod_name in ("__main__", "main"):
        mod = sys.modules.get(mod_name)
        if (
            mod is not None
            and hasattr(mod, "is_startup_enabled")
            and hasattr(mod, "set_startup_enabled")
        ):
            return mod.is_startup_enabled, mod.set_startup_enabled
    try:
        import main as app_main

        return app_main.is_startup_enabled, app_main.set_startup_enabled
    except Exception:
        return (lambda: False), (lambda _enabled: False)


class SettingsDialog(QDialog):
    """Sunset-themed Settings & Workspace Backup modal dialog."""

    ICON_CHOICES = (
        "fa5s.sticky-note",
        "fa5s.terminal",
        "fa5s.file-alt",
        "fa5s.check-square",
        "fa5s.clipboard-list",
        "fa5s.network-wired",
        "fa5s.code",
        "fa5s.bookmark",
        "fa5s.lightbulb",
        "fa5s.folder",
        "fa5s.bug",
        "fa5s.server",
        "fa5s.rocket",
        "fa5s.star",
    )

    def __init__(
        self,
        sidebar: "SidebarWindow",
        startup_getter: Optional[Callable[[], bool]] = None,
        startup_setter: Optional[Callable[[bool], bool]] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent or sidebar)
        self.sidebar = sidebar
        default_get, default_set = _resolve_startup_callbacks()
        self._get_startup_cb = startup_getter or default_get
        self._set_startup_cb = startup_setter or default_set
        self._initial_startup = bool(self._get_startup_cb())
        self.tab_rows: List[tuple[int, QLineEdit, QComboBox]] = []

        self.setWindowTitle("F9Sidebar Settings & Backup")
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.setModal(True)
        self.resize(440, 580)

        self._setup_styles()
        self._build_ui()

    def _setup_styles(self) -> None:
        self.setStyleSheet(
            """
            QDialog {
                background-color: qlineargradient(
                    x1:0, y1:0, x2:0.4, y2:1,
                    stop:0 #1E1E2E, stop:0.6 #282039, stop:1 #35233D
                );
                color: #CDD6F4;
                font-family: 'Segoe UI', sans-serif;
            }
            QLabel {
                color: #CDD6F4;
                font-size: 12px;
            }
            QLabel#SettingsSection {
                color: #FAB387;
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 0.5px;
                text-transform: uppercase;
                margin-top: 6px;
            }
            QLineEdit, QSpinBox, QComboBox {
                background-color: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #2A2D3E, stop:1 #342945
                );
                border: 1px solid #363A4F;
                border-radius: 5px;
                padding: 4px 8px;
                color: #CDD6F4;
                font-size: 12px;
            }
            QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
                border-color: #FAB387;
            }
            QCheckBox {
                color: #CDD6F4;
                font-size: 12px;
                spacing: 6px;
            }
            QPushButton {
                background-color: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #2A2D3E, stop:1 #342945
                );
                border: 1px solid #363A4F;
                border-radius: 5px;
                color: #CDD6F4;
                padding: 5px 10px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #363A4F;
                border-color: #FAB387;
            }
            QScrollArea {
                background-color: rgba(30, 30, 46, 0.55);
                border: 1px solid #363A4F;
                border-radius: 6px;
            }
            """
        )

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(8)

        lbl_appear = QLabel("Window & Appearance")
        lbl_appear.setObjectName("SettingsSection")
        root.addWidget(lbl_appear)

        form = QFormLayout()
        form.setSpacing(6)

        self.cmb_dock_edge = QComboBox()
        for edge in ("right", "bottom", "left", "top"):
            self.cmb_dock_edge.addItem(edge.capitalize(), edge)
        idx_edge = self.cmb_dock_edge.findData(self.sidebar.dock_edge)
        if idx_edge >= 0:
            self.cmb_dock_edge.setCurrentIndex(idx_edge)
        form.addRow("Dock Edge:", self.cmb_dock_edge)

        dim_row = QHBoxLayout()
        dim_row.setSpacing(6)
        self.spin_width = QSpinBox()
        self.spin_width.setRange(
            SidebarWindow.MIN_SIDEBAR_WIDTH, SidebarWindow.MAX_SIDEBAR_WIDTH
        )
        self.spin_width.setSuffix(" px")
        self.spin_width.setValue(int(self.sidebar.sidebar_width))
        dim_row.addWidget(QLabel("W:"))
        dim_row.addWidget(self.spin_width, 1)

        self.spin_height = QSpinBox()
        self.spin_height.setRange(
            SidebarWindow.MIN_SIDEBAR_HEIGHT, SidebarWindow.MAX_SIDEBAR_HEIGHT
        )
        self.spin_height.setSuffix(" px")
        self.spin_height.setValue(int(self.sidebar.sidebar_height))
        dim_row.addWidget(QLabel("H:"))
        dim_row.addWidget(self.spin_height, 1)
        form.addRow("Size (L/R | T/B):", dim_row)

        self.spin_opacity = QSpinBox()
        self.spin_opacity.setRange(40, 100)
        self.spin_opacity.setSuffix("%")
        self.spin_opacity.setValue(int(self.sidebar.sidebar_opacity))
        form.addRow("Opacity:", self.spin_opacity)

        root.addLayout(form)

        sys_row = QHBoxLayout()
        sys_row.setSpacing(12)
        self.chk_startup = QCheckBox("Launch at Windows Startup")
        self.chk_startup.setChecked(self._initial_startup)
        sys_row.addWidget(self.chk_startup)

        self.chk_pause_hotkeys = QCheckBox("Pause Global Hotkeys")
        self.chk_pause_hotkeys.setChecked(
            bool(getattr(self.sidebar.hooks, "hotkeys_paused", False))
        )
        sys_row.addWidget(self.chk_pause_hotkeys)
        root.addLayout(sys_row)

        tabs_hdr = QHBoxLayout()
        lbl_tabs = QLabel("9 Canonical Note Tabs")
        lbl_tabs.setObjectName("SettingsSection")
        tabs_hdr.addWidget(lbl_tabs)
        tabs_hdr.addStretch(1)
        self.btn_reset_tabs = QPushButton("Reset 9 Tab Names & Icons")
        self.btn_reset_tabs.clicked.connect(self.reset_tab_inputs_to_defaults)
        tabs_hdr.addWidget(self.btn_reset_tabs)
        root.addLayout(tabs_hdr)

        tabs_scroll = QScrollArea()
        tabs_scroll.setWidgetResizable(True)
        tabs_container = QWidget()
        tabs_layout = QVBoxLayout(tabs_container)
        tabs_layout.setContentsMargins(6, 6, 6, 6)
        tabs_layout.setSpacing(5)

        for idx, tab in enumerate(self.sidebar.db.get_note_tabs()):
            row_lay = QHBoxLayout()
            row_lay.setSpacing(6)
            lbl = QLabel(f"Ctrl+{idx + 1}")
            lbl.setFixedWidth(42)
            row_lay.addWidget(lbl)

            name_edit = QLineEdit(str(tab.get("tab_name", "")))
            row_lay.addWidget(name_edit, 1)

            icon_cmb = QComboBox()
            icon_cmb.setEditable(True)
            for ico in self.ICON_CHOICES:
                icon_cmb.addItem(ico)
            icon_val = str(tab.get("icon_name", "fa5s.sticky-note"))
            icon_cmb.setCurrentText(icon_val)
            icon_cmb.setFixedWidth(145)
            row_lay.addWidget(icon_cmb)

            tabs_layout.addLayout(row_lay)
            self.tab_rows.append((int(tab["id"]), name_edit, icon_cmb))

        tabs_scroll.setWidget(tabs_container)
        root.addWidget(tabs_scroll, 1)

        lbl_bak = QLabel("Workspace Backup (.zip)")
        lbl_bak.setObjectName("SettingsSection")
        root.addWidget(lbl_bak)

        bak_row = QHBoxLayout()
        bak_row.setSpacing(8)
        self.btn_export_backup = QPushButton("Export Backup (.zip)...")
        self.btn_export_backup.clicked.connect(lambda: self.export_backup())
        bak_row.addWidget(self.btn_export_backup)

        self.btn_import_backup = QPushButton("Import Backup (.zip)...")
        self.btn_import_backup.clicked.connect(lambda: self.import_backup())
        bak_row.addWidget(self.btn_import_backup)
        root.addLayout(bak_row)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.accepted.connect(self._on_accept)
        self.button_box.rejected.connect(self.reject)
        root.addWidget(self.button_box)

    def reset_tab_inputs_to_defaults(self) -> None:
        from database import DEFAULT_NOTE_TABS

        for idx, (_tid, name_edit, icon_cmb) in enumerate(self.tab_rows):
            if idx < len(DEFAULT_NOTE_TABS):
                def_name, def_icon, _ = DEFAULT_NOTE_TABS[idx]
                name_edit.setText(def_name)
                icon_cmb.setCurrentText(def_icon)

    def export_backup(self, file_path: Optional[str] = None) -> Optional[Path]:
        self.sidebar.flush_pending_state()
        chosen = file_path
        if chosen is None:
            chosen, _ = QFileDialog.getSaveFileName(
                self,
                "Export Workspace Backup",
                "F9Sidebar_backup.zip",
                "Zip Archive (*.zip)",
            )
        if not chosen:
            return None
        return self.sidebar.db.export_workspace_backup(chosen)

    def import_backup(self, file_path: Optional[str] = None) -> bool:
        chosen = file_path
        if chosen is None:
            chosen, _ = QFileDialog.getOpenFileName(
                self,
                "Import Workspace Backup",
                "",
                "Zip Archive (*.zip)",
            )
        if not chosen:
            return False
        if hasattr(self.sidebar.panel_hub, "save_timer"):
            self.sidebar.panel_hub.save_timer.stop()
        ok = self.sidebar.db.import_workspace_backup(chosen)
        if ok:
            tabs = self.sidebar.db.get_note_tabs()
            for idx, (_tid, name_edit, icon_cmb) in enumerate(self.tab_rows):
                if idx < len(tabs):
                    name_edit.setText(str(tabs[idx].get("tab_name", "")))
                    icon_cmb.setCurrentText(str(tabs[idx].get("icon_name", "")))
            self.sidebar.refresh_views()
        return ok

    def apply_settings(self) -> None:
        for tid, name_edit, icon_cmb in self.tab_rows:
            self.sidebar.db.update_note_tab_meta(
                tid, name_edit.text(), icon_cmb.currentText()
            )
        edge = self.cmb_dock_edge.currentData()
        if edge:
            self.sidebar.set_dock_edge(str(edge))
        self.sidebar.set_sidebar_dimensions(
            self.spin_width.value(),
            self.spin_height.value(),
            persist=True,
            update_appbar=True,
        )
        self.sidebar.set_sidebar_opacity(self.spin_opacity.value())
        if hasattr(self.sidebar.hooks, "hotkeys_paused"):
            self.sidebar.hooks.hotkeys_paused = self.chk_pause_hotkeys.isChecked()
        if self._set_startup_cb is not None and self.chk_startup.isChecked() != self._initial_startup:
            self._set_startup_cb(self.chk_startup.isChecked())
        self.sidebar.refresh_views()

    def _on_accept(self) -> None:
        self.apply_settings()
        self.accept()


class SidebarWindow(QWidget):
    sig_request_restore_focus = Signal()
    sig_profile_changed = Signal(str)
    sig_dock_edge_changed = Signal(str)
    sig_appbar_toggled = Signal(bool)
    sig_opacity_changed = Signal(int)

    DOCK_EDGES = ("right", "bottom", "left", "top")
    DOCK_EDGE_SYMBOLS = {
        "right": "↦",
        "left": "↤",
        "top": "↥",
        "bottom": "↧",
    }
    DOCK_EDGE_BORDERS = {
        "right": "border-left: 1px solid #363A4F;",
        "left": "border-right: 1px solid #363A4F;",
        "top": "border-bottom: 1px solid #363A4F;",
        "bottom": "border-top: 1px solid #363A4F;",
    }
    MIN_SIDEBAR_WIDTH = 320
    MAX_SIDEBAR_WIDTH = 720
    DEFAULT_SIDEBAR_WIDTH = 380
    MIN_SIDEBAR_HEIGHT = 260
    MAX_SIDEBAR_HEIGHT = 680
    DEFAULT_SIDEBAR_HEIGHT = 360
    RESIZE_GRIP_MARGIN = 7

    def __init__(self, db_manager, hook_manager):
        super().__init__()
        self.db = db_manager
        self.hooks = hook_manager
        self.sidebar_width = self.DEFAULT_SIDEBAR_WIDTH
        self.sidebar_height = self.DEFAULT_SIDEBAR_HEIGHT
        self.dock_edge = "right"
        self.appbar_enabled = False
        self.is_pinned = False
        self._is_closing = False
        self._restoring_state = False
        self._resizing_edge = False
        self._current_calc_result: Optional[str] = None
        self._drag_hover_active = False
        self._drag_peek_opened = False
        self._last_appbar_rect: QRect | None = None
        self.sidebar_opacity = 100
        self.unread_clips = 0
        self.toast = ToastPopup()
        self.destroyed.connect(
            lambda *_args, t=self.toast: t.close() if _qt_is_valid(t) else None
        )

        self._opacity_save_timer = QTimer(self)
        self._opacity_save_timer.setSingleShot(True)
        self._opacity_save_timer.setInterval(200)
        self._opacity_save_timer.timeout.connect(self._persist_opacity_setting)

        self._edge_drag_timer = QTimer(self)
        self._edge_drag_timer.setInterval(120)
        self._edge_drag_timer.timeout.connect(self._check_edge_drag_peek)

        self.setWindowTitle("F9Sidebar")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAcceptDrops(True)
        self.setMouseTracking(True)

        self._setup_styles()
        self._build_ui()
        self._setup_animation()
        self._restore_persisted_state()
        self.refresh_views()
        self._edge_drag_timer.start()

        self.settings_shortcut = QShortcut(QKeySequence("Ctrl+,"), self)
        self.settings_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self.settings_shortcut.activated.connect(self.open_settings_dialog)

        self._sidebar_shortcuts: List[QShortcut] = []
        for seq, handler in (
            ("Ctrl+F", self.focus_search_bar),
            ("Ctrl+Shift+Up", lambda: self.set_dock_edge("top")),
            ("Ctrl+Shift+Down", lambda: self.set_dock_edge("bottom")),
            ("Ctrl+Shift+Left", lambda: self.set_dock_edge("left")),
            ("Ctrl+Shift+Right", lambda: self.set_dock_edge("right")),
            ("Ctrl+Shift+I", self.open_settings_dialog),
            ("Ctrl+Shift+1", lambda: self.switch_to_panel(0)),
            ("Ctrl+Shift+!", lambda: self.switch_to_panel(0)),
            ("Ctrl+Shift+2", lambda: self.switch_to_panel(1)),
            ("Ctrl+Shift+@", lambda: self.switch_to_panel(1)),
            ("Ctrl+Shift+P", lambda: self.set_profile("personal")),
            ("Ctrl+Shift+W", lambda: self.set_profile("work")),
        ):
            sc = QShortcut(QKeySequence(seq), self)
            sc.setContext(Qt.ShortcutContext.WindowShortcut)
            sc.activated.connect(handler)
            self._sidebar_shortcuts.append(sc)

        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
            install_button_fx(app)

    def _setup_styles(self) -> None:
        edge_border = self.DOCK_EDGE_BORDERS.get(
            self.dock_edge, self.DOCK_EDGE_BORDERS["right"]
        )
        self.setStyleSheet(
            f"""
            QWidget#SidebarRoot {{
                background-color: qlineargradient(
                    x1:0, y1:0, x2:0.35, y2:1,
                    stop:0 #1E1E2E,
                    stop:0.5 #241E36,
                    stop:0.85 #2D213C,
                    stop:1 #35233D
                );
                {edge_border}
                color: #CDD6F4;
                font-family: 'Segoe UI', sans-serif;
            }}
            QLineEdit#OmniSearch {{
                background-color: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #2A2D3E, stop:1 #332944
                );
                border: 1px solid #363A4F;
                border-radius: 6px;
                padding: 6px 10px;
                color: #CDD6F4;
                font-size: 13px;
                selection-background-color: #FAB387;
                selection-color: #1E1E2E;
            }}
            QLineEdit#OmniSearch:focus {{
                border: 1px solid #FAB387;
                background-color: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #2E2B42, stop:1 #392B4A
                );
            }}
            QPushButton#HeaderBtn, QPushButton#PillBtn {{
                background-color: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #2A2D3E, stop:1 #342944
                );
                border: 1px solid #363A4F;
                border-radius: 6px;
                color: #CDD6F4;
                padding: 5px 8px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton#HeaderBtn:hover, QPushButton#PillBtn:hover {{
                background-color: #363A4F;
            }}
            QPushButton#HeaderBtn:focus, QPushButton#PillBtn:focus {{
                border: 1px solid #FAB387;
            }}
            QPushButton#HeaderBtn:checked, QPushButton#PillBtn:checked {{
                background-color: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #F9E2AF, stop:0.48 #FAB387, stop:1 #F38BA8
                );
                color: #1E1E2E;
                border-color: #CBA6F7;
            }}
            QPushButton#HeaderBtn:checked:focus, QPushButton#PillBtn:checked:focus {{
                border: 2px solid #F9E2AF;
            }}
            QPushButton#CalcBadge {{
                background-color: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #F9E2AF, stop:0.5 #FAB387, stop:1 #F38BA8
                );
                border: 1px solid #CBA6F7;
                border-radius: 6px;
                color: #1E1E2E;
                padding: 4px 8px;
                font-size: 12px;
                font-weight: 700;
            }}
            QListWidget {{
                background-color: qlineargradient(
                    x1:0, y1:0, x2:0.5, y2:1,
                    stop:0 #2A2D3E, stop:1 #322944
                );
                border: 1px solid #363A4F;
                border-radius: 6px;
                color: #CDD6F4;
                padding: 4px;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 7px;
                margin: 2px 1px;
            }}
            QScrollBar::handle:vertical {{
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 #FAB387, stop:0.5 #F38BA8, stop:1 #CBA6F7
                );
                border-radius: 3px;
                min-height: 24px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: transparent;
                height: 0px;
            }}
            QScrollBar:horizontal {{
                background: transparent;
                height: 7px;
                margin: 1px 2px;
            }}
            QScrollBar::handle:horizontal {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #F9E2AF, stop:0.5 #FAB387, stop:1 #F38BA8
                );
                border-radius: 3px;
                min-width: 24px;
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
                background: transparent;
                width: 0px;
            }}
            """
        )
        self.setObjectName("SidebarRoot")

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(10)

        # --- Row 1: Omni-Bar Search + Calc + Profile + Edge + AppBar + Pin + Settings ---
        top_row = QHBoxLayout()
        top_row.setSpacing(4)

        self.search_input = QLineEdit()
        self.search_input.setObjectName("OmniSearch")
        self.search_input.setPlaceholderText("Search, =calc, or launch... (Ctrl+F)")
        self.search_input.setToolTip("Search shortcuts, notes, clips, or calculate with =... (Ctrl+F)")
        self.search_input.textChanged.connect(self.refresh_views)
        self.search_input.returnPressed.connect(self._on_omni_enter_pressed)
        top_row.addWidget(self.search_input, 1)

        self.calc_badge = QPushButton("")
        self.calc_badge.setObjectName("CalcBadge")
        self.calc_badge.setCursor(Qt.CursorShape.PointingHandCursor)
        self.calc_badge.setToolTip("Click or press Enter to copy calculated result")
        self.calc_badge.clicked.connect(self._copy_calc_result)
        self.calc_badge.hide()
        top_row.addWidget(self.calc_badge)

        self.btn_profile = QPushButton("WORK")
        self.btn_profile.setObjectName("PillBtn")
        self.btn_profile.setToolTip(
            "Toggle Work (Ctrl+Shift+W) / Personal (Ctrl+Shift+P) Profile"
        )
        self.btn_profile.clicked.connect(self._toggle_profile)
        top_row.addWidget(self.btn_profile)

        self.btn_dock_edge = QPushButton(self.DOCK_EDGE_SYMBOLS[self.dock_edge])
        self.btn_dock_edge.setObjectName("HeaderBtn")
        self.btn_dock_edge.setToolTip(
            "Dock Edge: Right (Ctrl+Shift+Arrows, Click to cycle, Right-click for menu)"
        )
        self.btn_dock_edge.clicked.connect(self.cycle_dock_edge)
        self.btn_dock_edge.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.btn_dock_edge.customContextMenuRequested.connect(self._show_dock_edge_menu)
        top_row.addWidget(self.btn_dock_edge)

        self.btn_appbar = QPushButton()
        self.btn_appbar.setObjectName("HeaderBtn")
        self.btn_appbar.setCheckable(True)
        self.btn_appbar.setIcon(qta.icon("fa5s.window-restore", color="#CDD6F4"))
        self.btn_appbar.setToolTip(
            "Windows AppBar Dock Mode (push maximized windows aside)"
        )
        self.btn_appbar.toggled.connect(self.set_appbar_mode)
        top_row.addWidget(self.btn_appbar)

        self.btn_pin = QPushButton()
        self.btn_pin.setObjectName("HeaderBtn")
        self.btn_pin.setCheckable(True)
        self.btn_pin.setIcon(qta.icon("fa5s.thumbtack", color="#CDD6F4"))
        self.btn_pin.setToolTip("Pin sidebar open & dock edge (Ctrl+Shift+F9)")
        self.btn_pin.toggled.connect(self._on_pin_toggled)
        top_row.addWidget(self.btn_pin)

        self.btn_settings = QPushButton()
        self.btn_settings.setObjectName("HeaderBtn")
        self.btn_settings.setIcon(qta.icon("fa5s.cog", color="#CDD6F4"))
        self.btn_settings.setToolTip("Settings & Workspace Backup (Ctrl+Shift+I / Ctrl+,)")
        self.btn_settings.clicked.connect(self.open_settings_dialog)
        top_row.addWidget(self.btn_settings)

        root_layout.addLayout(top_row)

        # --- Row 2: Panel Switcher Bar (Shift+F9) ---
        nav_row = QHBoxLayout()
        nav_row.setSpacing(6)

        self.btn_panel_hub = DroppablePanelSwitchBtn(
            "1. Notes",
            panel_index=0,
            on_hover_switch=self.switch_to_panel,
            on_external_drop=self._handle_panel_button_drop,
        )
        self.btn_panel_hub.setObjectName("PillBtn")
        self.btn_panel_hub.setToolTip("Switch to 1. Notes (Ctrl+Shift+1)")
        self.btn_panel_hub.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.btn_panel_hub.setMinimumHeight(26)
        self.btn_panel_hub.setCheckable(True)
        self.btn_panel_hub.setChecked(True)
        self.btn_panel_hub.clicked.connect(lambda: self.switch_to_panel(0))

        self.btn_panel_queue = DroppablePanelSwitchBtn(
            "2. Clip Queue (0)",
            panel_index=1,
            on_hover_switch=self.switch_to_panel,
            on_external_drop=self._handle_panel_button_drop,
        )
        self.btn_panel_queue.setObjectName("PillBtn")
        self.btn_panel_queue.setToolTip("Switch to 2. Clip Queue (Ctrl+Shift+2)")
        self.btn_panel_queue.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.btn_panel_queue.setMinimumHeight(26)
        self.btn_panel_queue.setCheckable(True)
        self.btn_panel_queue.clicked.connect(lambda: self.switch_to_panel(1))

        nav_row.addWidget(self.btn_panel_hub, 1)
        nav_row.addWidget(self.btn_panel_queue, 1)
        root_layout.addLayout(nav_row)

        self.horizon_bar = SunsetHorizonBar(self)
        root_layout.addWidget(self.horizon_bar)

        # --- Main Body: QStackedWidget for Panel 1 & Panel 2 ---
        self.stack = QStackedWidget()
        self._load_panels()
        self.panel_transition = SunsetFadeOverlay(self.stack)
        root_layout.addWidget(self.stack, 1)

    def _load_panels(self) -> None:
        """Loads PanelHub and PanelQueue if built, or falls back to live test views."""
        # Panel 1: Hub
        try:
            from ui.panel_hub import PanelHub
            self.panel_hub = PanelHub(self.db, self)
        except ImportError:
            self.panel_hub = QWidget()
            lay1 = QVBoxLayout(self.panel_hub)
            lbl1 = QLabel(
                "Panel 1: Shortcuts & Vertical Notes Hub\n\n"
                "Ready for Antigravity IDE to generate ui/panel_hub.py.\n"
                "Press Shift+F9 to view Panel 2 (Ctrl+F9 Clip Queue)."
            )
            lbl1.setWordWrap(True)
            lbl1.setStyleSheet("color: #A6ADC8; padding: 12px;")
            lay1.addWidget(lbl1)
            lay1.addStretch()

        # Panel 2: Clip Queue
        try:
            from ui.panel_queue import PanelQueue
            self.panel_queue = PanelQueue(self.db, self)
        except ImportError:
            self.panel_queue = QWidget()
            lay2 = QVBoxLayout(self.panel_queue)
            info = QLabel("Highlight text/files anywhere and press Ctrl+F9:")
            info.setStyleSheet("color: #A6ADC8; font-size: 12px;")
            self._fallback_list = QListWidget()
            lay2.addWidget(info)
            lay2.addWidget(self._fallback_list, 1)

        self.stack.addWidget(self.panel_hub)
        self.stack.addWidget(self.panel_queue)

    def _setup_animation(self) -> None:
        self.anim = QPropertyAnimation(self, b"geometry")
        self.anim.setDuration(140)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.anim.finished.connect(self._on_anim_finished)

    # --- Show / Hide & Active-Monitor Positioning ---
    def _unregister_appbar_if_needed(self, restore_windows: bool = True) -> None:
        if getattr(self.hooks, "appbar_registered", False):
            try:
                self.hooks.unregister_appbar(
                    int(self.winId()), restore_windows=restore_windows
                )
            except TypeError:
                self.hooks.unregister_appbar(int(self.winId()))

    def _compute_hide_rect(self, curr: QRect) -> QRect:
        edge = self.dock_edge
        if edge == "left":
            return QRect(curr.left() - curr.width(), curr.top(), curr.width(), curr.height())
        if edge == "top":
            return QRect(curr.left(), curr.top() - curr.height(), curr.width(), curr.height())
        if edge == "bottom":
            return QRect(curr.left(), curr.bottom() + 1, curr.width(), curr.height())
        return QRect(curr.right() + 1, curr.top(), curr.width(), curr.height())

    def _compute_edge_rects(self, bound_rect: QRect) -> tuple[QRect, QRect]:
        edge = self.dock_edge
        if edge == "left":
            w = min(self.sidebar_width, bound_rect.width())
            end_rect = QRect(bound_rect.left(), bound_rect.top(), w, bound_rect.height())
        elif edge == "top":
            h = min(self.sidebar_height, bound_rect.height())
            end_rect = QRect(bound_rect.left(), bound_rect.top(), bound_rect.width(), h)
        elif edge == "bottom":
            h = min(self.sidebar_height, bound_rect.height())
            end_rect = QRect(
                bound_rect.left(), bound_rect.bottom() - h + 1, bound_rect.width(), h
            )
        else:
            w = min(self.sidebar_width, bound_rect.width())
            end_rect = QRect(
                bound_rect.right() - w + 1, bound_rect.top(), w, bound_rect.height()
            )
        return self._compute_hide_rect(end_rect), end_rect

    def _get_clean_available_geometry(self, screen) -> QRect:
        avail = (
            screen.availableGeometry() if screen is not None else QRect(0, 0, 1920, 1080)
        )
        if (
            self._last_appbar_rect is not None
            and screen is not None
            and screen.geometry().contains(self._last_appbar_rect.center())
        ):
            avail = avail.united(self._last_appbar_rect)
        return avail

    def _resolve_target_rects(self, screen) -> tuple[QRect, QRect]:
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        self._unregister_appbar_if_needed(restore_windows=not self.appbar_enabled)
        avail = self._get_clean_available_geometry(screen)
        start_rect, end_rect = self._compute_edge_rects(avail)
        if self.appbar_enabled and hasattr(self.hooks, "register_appbar"):
            thickness = (
                self.sidebar_width
                if self.dock_edge in ("left", "right")
                else self.sidebar_height
            )
            dpi_scale = float(screen.devicePixelRatio()) if screen is not None else 1.0
            rx, ry, rw, rh = self.hooks.register_appbar(
                int(self.winId()),
                self.dock_edge,
                (avail.x(), avail.y(), avail.width(), avail.height()),
                thickness,
                dpi_scale=dpi_scale,
            )
            end_rect = QRect(rx, ry, rw, rh)
            self._last_appbar_rect = QRect(end_rect)
            self._save_pinned_screen(screen)
            start_rect = self._compute_hide_rect(end_rect)
        return start_rect, end_rect

    def _save_pinned_screen(self, screen) -> None:
        if (
            self._restoring_state
            or screen is None
            or not hasattr(self.db, "update_global_settings")
        ):
            return
        center = screen.geometry().center()
        screen_name = screen.name() if hasattr(screen, "name") else ""
        self.db.update_global_settings(
            {
                "pinned_screen_name": screen_name,
                "pinned_screen_center": [int(center.x()), int(center.y())],
            }
        )

    def get_pinned_screen(self):
        """Resolves the remembered pinned monitor, falling back to cursor or primary screen."""
        saved_name = (
            self.db.get_global_setting("pinned_screen_name", "")
            if hasattr(self.db, "get_global_setting")
            else ""
        )
        saved_center = (
            self.db.get_global_setting("pinned_screen_center", None)
            if hasattr(self.db, "get_global_setting")
            else None
        )
        screen_by_pt = None
        if isinstance(saved_center, list) and len(saved_center) == 2:
            screen_by_pt = QGuiApplication.screenAt(
                QPoint(int(saved_center[0]), int(saved_center[1]))
            )
            if screen_by_pt is not None and (
                not saved_name or screen_by_pt.name() == saved_name
            ):
                return screen_by_pt
        if saved_name:
            for scr in QGuiApplication.screens():
                if scr.name() == saved_name:
                    return scr
        if screen_by_pt is not None:
            return screen_by_pt
        return QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()

    def _restore_persisted_state(self) -> None:
        """Restores global window settings and initial per-profile active panel."""
        if not hasattr(self.db, "get_global_setting"):
            return
        self._restoring_state = True
        try:
            self.btn_profile.setText(str(getattr(self.db, "profile", "work")).upper())

            saved_edge = str(self.db.get_global_setting("dock_edge", "right")).lower()
            if saved_edge in self.DOCK_EDGES:
                self.set_dock_edge(saved_edge)

            saved_w = self.db.get_global_setting("sidebar_width", self.DEFAULT_SIDEBAR_WIDTH)
            saved_h = self.db.get_global_setting("sidebar_height", self.DEFAULT_SIDEBAR_HEIGHT)
            try:
                self.set_sidebar_dimensions(
                    int(saved_w), int(saved_h), persist=False, update_appbar=False
                )
            except (TypeError, ValueError):
                self.set_sidebar_dimensions(
                    self.DEFAULT_SIDEBAR_WIDTH,
                    self.DEFAULT_SIDEBAR_HEIGHT,
                    persist=False,
                    update_appbar=False,
                )

            saved_opacity = self.db.get_global_setting("sidebar_opacity", 100)
            try:
                self.set_sidebar_opacity(int(saved_opacity))
            except (TypeError, ValueError):
                self.set_sidebar_opacity(100)

            saved_pin = bool(self.db.get_global_setting("is_pinned", False))
            self.set_appbar_mode(saved_pin)

            if hasattr(self.db, "get_workspace_setting"):
                saved_panel = self.db.get_workspace_setting("active_panel", 0)
                if saved_panel in (0, 1):
                    self.switch_to_panel(int(saved_panel))
        finally:
            self._restoring_state = False

    def _persist_opacity_setting(self) -> None:
        if hasattr(self.db, "set_global_setting"):
            self.db.set_global_setting("sidebar_opacity", int(self.sidebar_opacity))

    def flush_pending_state(self) -> None:
        """Flushes any debounced settings or active note edits to storage."""
        if self._opacity_save_timer.isActive():
            self._opacity_save_timer.stop()
            self._persist_opacity_setting()
        if hasattr(self.panel_hub, "flush_pending_save"):
            self.panel_hub.flush_pending_save()

    @staticmethod
    def _exec_menu(menu: QMenu, global_pos):
        return menu.exec(global_pos)

    @staticmethod
    def _exec_dialog(dlg: QDialog) -> int:
        return dlg.exec()

    def set_sidebar_dimensions(
        self,
        width: Optional[int] = None,
        height: Optional[int] = None,
        persist: bool = True,
        update_appbar: bool = True,
    ) -> tuple[int, int]:
        """Updates clamped sidebar width/height, reflows grid columns, and optionally syncs AppBar."""
        if width is not None:
            self.sidebar_width = max(
                self.MIN_SIDEBAR_WIDTH, min(self.MAX_SIDEBAR_WIDTH, int(width))
            )
        if height is not None:
            self.sidebar_height = max(
                self.MIN_SIDEBAR_HEIGHT, min(self.MAX_SIDEBAR_HEIGHT, int(height))
            )
        if hasattr(self, "panel_hub") and hasattr(
            self.panel_hub, "update_grid_columns_for_width"
        ):
            self.panel_hub.update_grid_columns_for_width(self.sidebar_width)
        if self.isVisible() and not self._is_closing:
            screen = (
                self.screen()
                or QGuiApplication.screenAt(self.frameGeometry().center())
                or QGuiApplication.primaryScreen()
            )
            if update_appbar:
                _, end_rect = self._resolve_target_rects(screen)
            else:
                avail = self._get_clean_available_geometry(screen)
                _, end_rect = self._compute_edge_rects(avail)
            self.anim.stop()
            self.setGeometry(end_rect)
        if (
            persist
            and not self._restoring_state
            and hasattr(self.db, "update_global_settings")
        ):
            self.db.update_global_settings(
                {
                    "sidebar_width": int(self.sidebar_width),
                    "sidebar_height": int(self.sidebar_height),
                }
            )
        return (self.sidebar_width, self.sidebar_height)

    def reset_sidebar_dimensions(self) -> tuple[int, int]:
        """Resets sidebar width and height back to 380x360 defaults."""
        return self.set_sidebar_dimensions(
            self.DEFAULT_SIDEBAR_WIDTH,
            self.DEFAULT_SIDEBAR_HEIGHT,
            persist=True,
            update_appbar=True,
        )

    def _is_on_resize_border(self, local_pos: QPoint) -> bool:
        m = self.RESIZE_GRIP_MARGIN
        if self.dock_edge == "left":
            return (self.width() - m) <= local_pos.x() <= self.width()
        if self.dock_edge == "top":
            return (self.height() - m) <= local_pos.y() <= self.height()
        if self.dock_edge == "bottom":
            return 0 <= local_pos.y() <= m
        return 0 <= local_pos.x() <= m

    def open_settings_dialog(self) -> Optional[SettingsDialog]:
        """Opens the Sunset-themed Settings & Backup modal dialog with pin protection."""
        self.flush_pending_state()
        dlg_holder: dict[str, Optional[SettingsDialog]] = {"dlg": None}
        was_pinned = self.is_pinned
        self.is_pinned = True
        try:
            dlg = SettingsDialog(self)
            dlg_holder["dlg"] = dlg
            self._exec_dialog(dlg)
        finally:
            self.is_pinned = was_pinned
        return dlg_holder["dlg"]

    def _copy_calc_result(self) -> bool:
        if self._current_calc_result is None:
            return False
        QApplication.clipboard().setText(self._current_calc_result)
        self.calc_badge.setText(f"✓ {self._current_calc_result}")
        QTimer.singleShot(
            800,
            lambda: self.calc_badge.setText(f"= {self._current_calc_result}")
            if _qt_is_valid(self)
            and _qt_is_valid(self.calc_badge)
            and self._current_calc_result is not None
            else None,
        )
        return True

    def _on_omni_enter_pressed(self) -> bool:
        if self._current_calc_result is not None:
            return self._copy_calc_result()
        query = self.search_input.text().strip()
        if not query:
            return False
        if self.stack.currentIndex() == 0:
            shortcuts = self.db.get_shortcuts(
                query, sort_by_usage=getattr(self.panel_hub, "auto_sort_usage", False)
            )
            if shortcuts and hasattr(self.panel_hub, "_launch_shortcut"):
                self.panel_hub._launch_shortcut(shortcuts[0])
                return True
            if hasattr(self.panel_hub, "cycle_note_search_match"):
                return bool(self.panel_hub.cycle_note_search_match(query))
            return False
        clips = self.db.get_clips(query)
        if clips and hasattr(self.panel_queue, "copy_single_clip"):
            self.panel_queue.copy_single_clip(clips[0])
            return True
        return False

    def _show_dock_edge_menu(self, pos) -> None:
        menu = QMenu(self)
        edge_actions = {}
        for edge in ("right", "left", "top", "bottom"):
            act = QAction(edge.capitalize(), menu)
            act.setCheckable(True)
            act.setChecked(self.dock_edge == edge)
            act.triggered.connect(lambda _chk=False, e=edge: self.set_dock_edge(e))
            menu.addAction(act)
            edge_actions[act] = edge
        chosen = self._exec_menu(menu, self.btn_dock_edge.mapToGlobal(pos))
        if chosen in edge_actions and chosen.isChecked() is False:
            # Handled cleanly by triggered signal when clicked; fallback if mocked exec returns action
            self.set_dock_edge(edge_actions[chosen])

    def set_dock_edge(self, edge: str) -> None:
        norm = (edge or "right").lower()
        if norm not in self.DOCK_EDGES:
            raise ValueError(f"Unsupported dock edge: {edge!r}")
        self.dock_edge = norm
        if hasattr(self, "btn_dock_edge"):
            self.btn_dock_edge.setText(self.DOCK_EDGE_SYMBOLS[norm])
            self.btn_dock_edge.setToolTip(
                f"Dock Edge: {norm.capitalize()} (Ctrl+Shift+Arrows, Click to cycle, Right-click for menu)"
            )
        self._setup_styles()
        if hasattr(self.panel_hub, "set_dock_orientation"):
            self.panel_hub.set_dock_orientation(horizontal=(norm in ("top", "bottom")))
        if self.isVisible() and not self._is_closing:
            screen = (
                self.screen()
                or QGuiApplication.screenAt(self.frameGeometry().center())
                or QGuiApplication.primaryScreen()
            )
            _, end_rect = self._resolve_target_rects(screen)
            self.anim.stop()
            self.setGeometry(end_rect)
        if not self._restoring_state and hasattr(self.db, "set_global_setting"):
            self.db.set_global_setting("dock_edge", self.dock_edge)
        self.sig_dock_edge_changed.emit(self.dock_edge)

    def cycle_dock_edge(self) -> str:
        idx = self.DOCK_EDGES.index(self.dock_edge) if self.dock_edge in self.DOCK_EDGES else 0
        next_edge = self.DOCK_EDGES[(idx + 1) % len(self.DOCK_EDGES)]
        self.set_dock_edge(next_edge)
        return next_edge

    def set_appbar_mode(self, enabled: bool) -> None:
        enabled = bool(enabled)
        self.appbar_enabled = enabled
        self.is_pinned = enabled
        icon_color = "#1E1E2E" if enabled else "#CDD6F4"
        for btn_name, icon_name in (
            ("btn_appbar", "fa5s.window-restore"),
            ("btn_pin", "fa5s.thumbtack"),
        ):
            btn = getattr(self, btn_name, None)
            if btn is not None:
                btn.blockSignals(True)
                btn.setChecked(enabled)
                btn.blockSignals(False)
                btn.setIcon(qta.icon(icon_name, color=icon_color))
        if self.isVisible() and not self._is_closing:
            screen = (
                self.screen()
                or QGuiApplication.screenAt(self.frameGeometry().center())
                or QGuiApplication.primaryScreen()
            )
            _, end_rect = self._resolve_target_rects(screen)
            self.anim.stop()
            self.setGeometry(end_rect)
        elif not enabled:
            self._unregister_appbar_if_needed(restore_windows=True)
        if not self._restoring_state and hasattr(self.db, "set_global_setting"):
            self.db.set_global_setting("is_pinned", self.is_pinned)
        self.sig_appbar_toggled.emit(self.appbar_enabled)

    def toggle_sidebar(self) -> None:
        if self.isVisible() and not self._is_closing:
            self.hide_sidebar(restore_focus=True)
        else:
            self.show_sidebar()

    def show_sidebar(self, target_screen=None, activate: bool = True) -> None:
        self.hooks.remember_foreground_window(int(self.winId()))
        self._is_closing = False

        is_dragging = bool(
            hasattr(self.hooks, "is_mouse_dragging") and self.hooks.is_mouse_dragging()
        )
        should_activate = bool(activate) and not is_dragging

        screen = (
            target_screen
            or QGuiApplication.screenAt(QCursor.pos())
            or QGuiApplication.primaryScreen()
        )
        start_rect, end_rect = self._resolve_target_rects(screen)

        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, not should_activate)
        self.setGeometry(start_rect)
        self.setWindowOpacity(self.sidebar_opacity / 100.0)
        self.show()
        self.raise_()
        if should_activate:
            self._drag_peek_opened = False
            self.activateWindow()
            self.search_input.setFocus()
            self.search_input.selectAll()
        else:
            self._drag_peek_opened = True

        self.anim.stop()
        self.anim.setStartValue(start_rect)
        self.anim.setEndValue(end_rect)
        self.anim.start()

    def _is_point_near_dock_edge(
        self, pos: QPoint, avail: QRect, margin: int = 10
    ) -> bool:
        edge = (self.dock_edge or "right").lower()
        x = int(pos.x())
        y = int(pos.y())
        in_y_band = (avail.top() - margin) <= y <= (avail.bottom() + margin)
        in_x_band = (avail.left() - margin) <= x <= (avail.right() + margin)
        if edge == "left":
            return in_y_band and (avail.left() - margin) <= x <= (avail.left() + margin)
        if edge == "top":
            return in_x_band and (avail.top() - margin) <= y <= (avail.top() + margin)
        if edge == "bottom":
            return in_x_band and (avail.bottom() - margin) <= y <= (avail.bottom() + margin)
        return in_y_band and (avail.right() - margin) <= x <= (avail.right() + margin)

    def _check_edge_drag_peek(self, cursor_pos: QPoint | None = None) -> bool:
        is_dragging = bool(
            hasattr(self.hooks, "is_mouse_dragging") and self.hooks.is_mouse_dragging()
        )
        pos = cursor_pos if cursor_pos is not None else QCursor.pos()
        if not self.isVisible() or self._is_closing:
            if is_dragging:
                screen = (
                    QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
                )
                avail = self._get_clean_available_geometry(screen)
                if self._is_point_near_dock_edge(pos, avail):
                    self._drag_peek_opened = True
                    self.show_sidebar(target_screen=screen, activate=False)
                    return True
            return False

        if (
            self._drag_peek_opened
            and not is_dragging
            and not self._drag_hover_active
            and not self.is_pinned
            and not self.appbar_enabled
        ):
            if not self.frameGeometry().contains(pos):
                self._drag_peek_opened = False
                self.hide_sidebar(restore_focus=False)
                return False
        return True

    def _handle_panel_button_drop(
        self, panel_index: int, mime_data: QMimeData, modifiers: Qt.KeyboardModifiers
    ) -> bool:
        self._drag_hover_active = False
        idx = 1 if int(panel_index) == 1 else 0
        self.switch_to_panel(idx)
        if idx == 0 and hasattr(self.panel_hub, "handle_external_shortcut_drop"):
            self.panel_hub.handle_external_shortcut_drop(mime_data, modifiers)
            return True
        if idx == 1 and hasattr(self.panel_queue, "handle_external_drop"):
            self.panel_queue.handle_external_drop(mime_data, modifiers)
            return True
        return False

    def hide_sidebar(self, restore_focus: bool = True) -> None:
        if not self.isVisible() or self._is_closing:
            return
        self._is_closing = True
        self._unregister_appbar_if_needed()

        curr = self.geometry()
        end_rect = self._compute_hide_rect(curr)

        self.anim.stop()
        self.anim.setStartValue(curr)
        self.anim.setEndValue(end_rect)
        self.anim.start()

        if restore_focus:
            self.hooks.restore_foreground_window()

    def _on_anim_finished(self) -> None:
        if self._is_closing:
            self.hide()
            self._is_closing = False

    # --- Panel & Profile Actions ---
    def switch_to_panel(self, index: int) -> None:
        clamped_idx = 1 if int(index) == 1 else 0
        prev_idx = self.stack.currentIndex()
        self.stack.setCurrentIndex(clamped_idx)
        self.btn_panel_hub.setChecked(clamped_idx == 0)
        self.btn_panel_queue.setChecked(clamped_idx == 1)
        if clamped_idx == 1:
            self.unread_clips = 0
        if not self._restoring_state and hasattr(self.db, "set_workspace_setting"):
            self.db.set_workspace_setting("active_panel", clamped_idx)
        self.refresh_views()
        if (
            not self._restoring_state
            and prev_idx != clamped_idx
            and hasattr(self, "panel_transition")
        ):
            self.panel_transition.trigger(165)

    def toggle_panel(self) -> None:
        next_idx = 1 if self.stack.currentIndex() == 0 else 0
        self.switch_to_panel(next_idx)

    def focus_search_bar(self) -> None:
        """Focuses the Omni-Bar search input and highlights existing query text."""
        self.search_input.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.search_input.selectAll()

    def set_profile(self, profile: str) -> bool:
        """Switches explicitly to 'work' or 'personal' SQLite profile."""
        target = "personal" if str(profile or "").lower().strip() == "personal" else "work"
        if getattr(self.db, "profile", "work") == target:
            self.btn_profile.setText(target.upper())
            return False
        self.db.switch_profile(target)
        if hasattr(self.db, "set_global_setting"):
            self.db.set_global_setting("active_profile", target)
        self.btn_profile.setText(target.upper())
        self.unread_clips = 0
        saved_panel = (
            self.db.get_workspace_setting("active_panel", 0)
            if hasattr(self.db, "get_workspace_setting")
            else 0
        )
        panel_idx = 1 if saved_panel == 1 else 0
        self._restoring_state = True
        try:
            self.switch_to_panel(panel_idx)
        finally:
            self._restoring_state = False
        self.sig_profile_changed.emit(target)
        return True

    def _toggle_profile(self) -> None:
        new_prof = "personal" if self.db.profile == "work" else "work"
        self.set_profile(new_prof)

    def set_sidebar_opacity(self, percent: int) -> int:
        """Sets window opacity clamped between 40% and 100% and syncs PanelHub's slider."""
        clamped = max(40, min(100, int(percent)))
        self.sidebar_opacity = clamped
        self.setWindowOpacity(clamped / 100.0)
        if hasattr(self, "panel_hub") and hasattr(self.panel_hub, "sync_opacity_slider"):
            self.panel_hub.sync_opacity_slider(clamped)
        if not self._restoring_state:
            self._opacity_save_timer.start()
        self.sig_opacity_changed.emit(clamped)
        return clamped

    def toggle_pin(self) -> bool:
        """Toggles sidebar pin and AppBar dock state (opening first if hidden while unpinned)."""
        new_state = not self.is_pinned
        self.set_appbar_mode(new_state)
        if new_state and (not self.isVisible() or self._is_closing):
            self.show_sidebar()
        return self.is_pinned

    def _on_pin_toggled(self, checked: bool) -> None:
        self.set_appbar_mode(bool(checked))

    def paste_last_captured_clip(self) -> bool:
        """Pastes the most recently Ctrl+F9 captured item into the active window."""
        latest = self.db.get_latest_clip() if hasattr(self.db, "get_latest_clip") else None
        if latest is None:
            clips = self.db.get_clips("")
            latest = clips[-1] if clips else None
        if not latest:
            return False
        content = str(latest.get("content", ""))
        source_type = str(latest.get("source_type", "text"))
        if hasattr(self.hooks, "paste_into_active_window"):
            return bool(self.hooks.paste_into_active_window(content, source_type))
        return False

    def on_new_clip_captured(self, content: str, source_type: str) -> None:
        was_hidden = not self.isVisible()
        clip_id = self.db.add_clip(content, source_type)
        if clip_id == -1:
            return
        if self.stack.currentIndex() != 1 or was_hidden:
            self.unread_clips += 1
        self.refresh_views()
        if was_hidden:
            queue_count = len(self.db.get_clips(""))
            self.toast.show_toast(content, source_type, queue_count)

    def refresh_views(self) -> None:
        raw_query = self.search_input.text().strip()
        calc_res = evaluate_math_query(raw_query)
        self._current_calc_result = calc_res
        if calc_res is not None:
            self.calc_badge.setText(f"= {calc_res}")
            self.calc_badge.show()
        else:
            self.calc_badge.hide()

        filter_query = "" if raw_query.startswith("=") else raw_query
        clips = self.db.get_clips(filter_query)
        badge = f" +{self.unread_clips}" if self.unread_clips > 0 else ""
        self.btn_panel_queue.setText(f"2. Clip Queue ({len(clips)}{badge})")

        # Update fallback list or real panels if they implement refresh(query)
        if hasattr(self, "_fallback_list"):
            self._fallback_list.clear()
            for c in clips:
                prefix = "[✓]" if c["is_checked"] else "[ ]"
                self._fallback_list.addItem(f"{prefix} ({c['source_type']}) {c['content'][:60]}")

        for panel in (self.panel_hub, self.panel_queue):
            if hasattr(panel, "refresh"):
                panel.refresh(filter_query)

    # --- Keyboard & Auto-Hide Events ---
    def _resolve_window_shortcut_action(self, event: QKeyEvent):
        mods = event.modifiers() & (
            Qt.KeyboardModifier.ControlModifier
            | Qt.KeyboardModifier.ShiftModifier
            | Qt.KeyboardModifier.AltModifier
        )
        key = event.key()
        ctrl_only = mods == Qt.KeyboardModifier.ControlModifier
        ctrl_shift = mods == (
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier
        )
        no_mod = mods == Qt.KeyboardModifier.NoModifier

        if ctrl_only and key == Qt.Key.Key_F:
            return self.focus_search_bar
        if ctrl_shift and key == Qt.Key.Key_Up:
            return lambda: self.set_dock_edge("top")
        if ctrl_shift and key == Qt.Key.Key_Down:
            return lambda: self.set_dock_edge("bottom")
        if ctrl_shift and key == Qt.Key.Key_Left:
            return lambda: self.set_dock_edge("left")
        if ctrl_shift and key == Qt.Key.Key_Right:
            return lambda: self.set_dock_edge("right")
        if ctrl_shift and key == Qt.Key.Key_I:
            return self.open_settings_dialog
        if ctrl_shift and key in (Qt.Key.Key_1, Qt.Key.Key_Exclam):
            return lambda: self.switch_to_panel(0)
        if ctrl_shift and key in (Qt.Key.Key_2, Qt.Key.Key_At):
            return lambda: self.switch_to_panel(1)
        if ctrl_shift and key == Qt.Key.Key_P:
            return lambda: self.set_profile("personal")
        if ctrl_shift and key == Qt.Key.Key_W:
            return lambda: self.set_profile("work")

        if self.stack.currentIndex() == 0 and hasattr(self, "panel_hub"):
            if ctrl_shift and key == Qt.Key.Key_H:
                return self.panel_hub.apply_highlight_color
            if ctrl_shift and key == Qt.Key.Key_C:
                return self.panel_hub.apply_text_color
            if no_mod and key == Qt.Key.Key_F5:
                return self.panel_hub.run_note_script
            if ctrl_only and key == Qt.Key.Key_F5:
                return lambda: self.panel_hub.run_highlighted_script(False)
            if ctrl_shift and key == Qt.Key.Key_F5:
                return lambda: self.panel_hub.run_highlighted_script(True)
        return None

    def eventFilter(self, obj, event) -> bool:
        if (
            self.isVisible()
            and isinstance(obj, QWidget)
            and obj.window() is self
            and isinstance(event, QKeyEvent)
        ):
            if event.type() == QEvent.Type.ShortcutOverride:
                if self._resolve_window_shortcut_action(event) is not None:
                    event.accept()
                    return True
            elif event.type() == QEvent.Type.KeyPress and not event.isAutoRepeat():
                action = self._resolve_window_shortcut_action(event)
                if action is not None:
                    action()
                    event.accept()
                    return True
                if (
                    event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                    and not (
                        event.modifiers()
                        & (
                            Qt.KeyboardModifier.ControlModifier
                            | Qt.KeyboardModifier.AltModifier
                            | Qt.KeyboardModifier.ShiftModifier
                        )
                    )
                ):
                    focus_widget = QApplication.focusWidget()
                    if (
                        focus_widget is not None
                        and obj is focus_widget
                        and self.isAncestorOf(focus_widget)
                        and focus_widget.window() is self
                    ):
                        if isinstance(focus_widget, QAbstractButton):
                            if focus_widget.isEnabled():
                                focus_widget.click()
                            return True
                        if isinstance(focus_widget, QComboBox):
                            if focus_widget.isEnabled() and not focus_widget.isEditable():
                                focus_widget.showPopup()
                            return True
                        if isinstance(focus_widget, QListWidget):
                            item = focus_widget.currentItem()
                            if item is not None:
                                row_widget = focus_widget.itemWidget(item)
                                if row_widget is not None and hasattr(row_widget, "checkbox"):
                                    row_widget.checkbox.click()
                                    return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            if self.search_input.text():
                self.search_input.clear()
            else:
                self.hide_sidebar(restore_focus=True)
            event.accept()
            return
        super().keyPressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._is_on_resize_border(event.position().toPoint())
        ):
            self.reset_sidebar_dimensions()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._is_on_resize_border(event.position().toPoint())
        ):
            self._resizing_edge = True
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._resizing_edge:
            gpos = event.globalPosition().toPoint()
            screen = (
                self.screen()
                or QGuiApplication.screenAt(self.frameGeometry().center())
                or QGuiApplication.primaryScreen()
            )
            avail = self._get_clean_available_geometry(screen)
            if self.dock_edge == "right":
                self.set_sidebar_dimensions(
                    width=avail.right() - gpos.x() + 1,
                    persist=False,
                    update_appbar=False,
                )
            elif self.dock_edge == "left":
                self.set_sidebar_dimensions(
                    width=gpos.x() - avail.left() + 1,
                    persist=False,
                    update_appbar=False,
                )
            elif self.dock_edge == "top":
                self.set_sidebar_dimensions(
                    height=gpos.y() - avail.top() + 1,
                    persist=False,
                    update_appbar=False,
                )
            elif self.dock_edge == "bottom":
                self.set_sidebar_dimensions(
                    height=avail.bottom() - gpos.y() + 1,
                    persist=False,
                    update_appbar=False,
                )
            event.accept()
            return

        if self._is_on_resize_border(event.position().toPoint()):
            cursor = (
                Qt.CursorShape.SizeVerCursor
                if self.dock_edge in ("top", "bottom")
                else Qt.CursorShape.SizeHorCursor
            )
            self.setCursor(cursor)
        else:
            self.unsetCursor()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._resizing_edge:
            self._resizing_edge = False
            self.set_sidebar_dimensions(
                self.sidebar_width,
                self.sidebar_height,
                persist=True,
                update_appbar=True,
            )
            self.unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def dragEnterEvent(self, event) -> None:
        if _is_droppable_mime(event.mimeData()):
            self._drag_hover_active = True
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if _is_droppable_mime(event.mimeData()):
            self._drag_hover_active = True
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dragLeaveEvent(self, event) -> None:
        self._drag_hover_active = False
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:
        self._drag_hover_active = False
        if _is_droppable_mime(event.mimeData()):
            if self._handle_panel_button_drop(
                self.stack.currentIndex(), event.mimeData(), event.modifiers()
            ):
                event.acceptProposedAction()
                return
        super().dropEvent(event)

    def changeEvent(self, event: QEvent) -> None:
        if (
            event.type() == QEvent.Type.WindowDeactivate
            and not self.is_pinned
            and not self.appbar_enabled
            and self.isVisible()
            and not self._is_closing
        ):
            is_dragging = self._drag_hover_active or bool(
                hasattr(self.hooks, "is_mouse_dragging")
                and self.hooks.is_mouse_dragging()
            )
            if is_dragging:
                self._drag_peek_opened = True
            else:
                self.hide_sidebar(restore_focus=False)
        super().changeEvent(event)

    def closeEvent(self, event) -> None:
        if hasattr(self, "horizon_bar"):
            self.horizon_bar.stop()
        if hasattr(self, "_edge_drag_timer") and self._edge_drag_timer.isActive():
            self._edge_drag_timer.stop()
        self.flush_pending_state()
        self._unregister_appbar_if_needed()
        super().closeEvent(event)