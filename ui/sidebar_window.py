from PySide6.QtCore import QEasingCurve, QEvent, QPropertyAnimation, QRect, Qt, Signal
from PySide6.QtGui import QCursor, QGuiApplication, QKeyEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
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

from ui.toast_popup import ToastPopup


class SidebarWindow(QWidget):
    sig_request_restore_focus = Signal()
    sig_profile_changed = Signal(str)

    def __init__(self, db_manager, hook_manager):
        super().__init__()
        self.db = db_manager
        self.hooks = hook_manager
        self.sidebar_width = 380
        self.is_pinned = False
        self._is_closing = False
        self.unread_clips = 0
        self.toast = ToastPopup()
        self.destroyed.connect(
            lambda *_args, t=self.toast: t.close() if _qt_is_valid(t) else None
        )

        self.setWindowTitle("F9Sidebar")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self._setup_styles()
        self._build_ui()
        self._setup_animation()
        self.refresh_views()

    def _setup_styles(self) -> None:
        self.setStyleSheet(
            """
            QWidget#SidebarRoot {
                background-color: #1E1E2E;
                border-left: 1px solid #363A4F;
                color: #CDD6F4;
                font-family: 'Segoe UI', sans-serif;
            }
            QLineEdit#OmniSearch {
                background-color: #2A2D3E;
                border: 1px solid #363A4F;
                border-radius: 6px;
                padding: 6px 10px;
                color: #CDD6F4;
                font-size: 13px;
            }
            QLineEdit#OmniSearch:focus {
                border: 1px solid #89B4FA;
            }
            QPushButton#HeaderBtn, QPushButton#PillBtn {
                background-color: #2A2D3E;
                border: 1px solid #363A4F;
                border-radius: 6px;
                color: #CDD6F4;
                padding: 5px 8px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton#HeaderBtn:hover, QPushButton#PillBtn:hover {
                background-color: #363A4F;
            }
            QPushButton#HeaderBtn:checked, QPushButton#PillBtn:checked {
                background-color: #89B4FA;
                color: #1E1E2E;
                border-color: #89B4FA;
            }
            QListWidget {
                background-color: #2A2D3E;
                border: 1px solid #363A4F;
                border-radius: 6px;
                color: #CDD6F4;
                padding: 4px;
            }
            """
        )
        self.setObjectName("SidebarRoot")

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(10)

        # --- Row 1: Omni-Bar Search + Pin + Profile ---
        top_row = QHBoxLayout()
        top_row.setSpacing(6)

        self.search_input = QLineEdit()
        self.search_input.setObjectName("OmniSearch")
        self.search_input.setPlaceholderText("Search shortcuts, notes & clips... (F9)")
        self.search_input.textChanged.connect(self.refresh_views)
        top_row.addWidget(self.search_input, 1)

        self.btn_profile = QPushButton("WORK")
        self.btn_profile.setObjectName("PillBtn")
        self.btn_profile.setToolTip("Toggle Work / Personal SQLite Profile")
        self.btn_profile.clicked.connect(self._toggle_profile)
        top_row.addWidget(self.btn_profile)

        self.btn_pin = QPushButton()
        self.btn_pin.setObjectName("HeaderBtn")
        self.btn_pin.setCheckable(True)
        self.btn_pin.setIcon(qta.icon("fa5s.thumbtack", color="#CDD6F4"))
        self.btn_pin.setToolTip("Pin sidebar open (disable auto-hide on focus loss)")
        self.btn_pin.toggled.connect(self._on_pin_toggled)
        top_row.addWidget(self.btn_pin)

        root_layout.addLayout(top_row)

        # --- Row 2: Panel Switcher Bar (Shift+F9) ---
        nav_row = QHBoxLayout()
        nav_row.setSpacing(6)

        self.btn_panel_hub = QPushButton("1. Hub (Shortcuts & Notes)")
        self.btn_panel_hub.setObjectName("PillBtn")
        self.btn_panel_hub.setCheckable(True)
        self.btn_panel_hub.setChecked(True)
        self.btn_panel_hub.clicked.connect(lambda: self.switch_to_panel(0))

        self.btn_panel_queue = QPushButton("2. Clip Queue (0)")
        self.btn_panel_queue.setObjectName("PillBtn")
        self.btn_panel_queue.setCheckable(True)
        self.btn_panel_queue.clicked.connect(lambda: self.switch_to_panel(1))

        nav_row.addWidget(self.btn_panel_hub, 1)
        nav_row.addWidget(self.btn_panel_queue, 1)
        root_layout.addLayout(nav_row)

        # --- Main Body: QStackedWidget for Panel 1 & Panel 2 ---
        self.stack = QStackedWidget()
        self._load_panels()
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
    def toggle_sidebar(self) -> None:
        if self.isVisible() and not self._is_closing:
            self.hide_sidebar(restore_focus=True)
        else:
            self.show_sidebar()

    def show_sidebar(self) -> None:
        self.hooks.remember_foreground_window(int(self.winId()))
        self._is_closing = False

        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        avail = screen.availableGeometry()

        start_rect = QRect(avail.right() + 1, avail.top(), self.sidebar_width, avail.height())
        end_rect = QRect(
            avail.right() - self.sidebar_width + 1,
            avail.top(),
            self.sidebar_width,
            avail.height(),
        )

        self.setGeometry(start_rect)
        self.show()
        self.raise_()
        self.activateWindow()
        self.search_input.setFocus()
        self.search_input.selectAll()

        self.anim.stop()
        self.anim.setStartValue(start_rect)
        self.anim.setEndValue(end_rect)
        self.anim.start()

    def hide_sidebar(self, restore_focus: bool = True) -> None:
        if not self.isVisible() or self._is_closing:
            return
        self._is_closing = True

        curr = self.geometry()
        end_rect = QRect(curr.right() + 1, curr.top(), self.sidebar_width, curr.height())

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
        self.stack.setCurrentIndex(index)
        self.btn_panel_hub.setChecked(index == 0)
        self.btn_panel_queue.setChecked(index == 1)
        if index == 1:
            self.unread_clips = 0
        self.refresh_views()

    def toggle_panel(self) -> None:
        next_idx = 1 if self.stack.currentIndex() == 0 else 0
        self.switch_to_panel(next_idx)

    def _toggle_profile(self) -> None:
        new_prof = "personal" if self.db.profile == "work" else "work"
        self.db.switch_profile(new_prof)
        self.btn_profile.setText(new_prof.upper())
        self.unread_clips = 0
        self.refresh_views()
        self.sig_profile_changed.emit(new_prof)

    def _on_pin_toggled(self, checked: bool) -> None:
        self.is_pinned = checked
        icon_color = "#1E1E2E" if checked else "#CDD6F4"
        self.btn_pin.setIcon(qta.icon("fa5s.thumbtack", color=icon_color))

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
        query = self.search_input.text().strip()
        clips = self.db.get_clips(query)
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
                panel.refresh(query)

    # --- Keyboard & Auto-Hide Events ---
    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            if self.search_input.text():
                self.search_input.clear()
            else:
                self.hide_sidebar(restore_focus=True)
            event.accept()
            return
        super().keyPressEvent(event)

    def changeEvent(self, event: QEvent) -> None:
        if (
            event.type() == QEvent.Type.WindowDeactivate
            and not self.is_pinned
            and self.isVisible()
            and not self._is_closing
        ):
            self.hide_sidebar(restore_focus=False)
        super().changeEvent(event)