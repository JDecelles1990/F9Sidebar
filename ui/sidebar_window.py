from PySide6.QtCore import QEasingCurve, QEvent, QPropertyAnimation, QRect, Qt, Signal
from PySide6.QtGui import QAction, QCursor, QGuiApplication, QKeyEvent
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QListWidget,
    QMenu,
    QPushButton,
    QSizePolicy,
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


class SidebarWindow(QWidget):
    sig_request_restore_focus = Signal()
    sig_profile_changed = Signal(str)
    sig_dock_edge_changed = Signal(str)
    sig_appbar_toggled = Signal(bool)

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

    def __init__(self, db_manager, hook_manager):
        super().__init__()
        self.db = db_manager
        self.hooks = hook_manager
        self.sidebar_width = 380
        self.sidebar_height = 360
        self.dock_edge = "right"
        self.appbar_enabled = False
        self.is_pinned = False
        self._is_closing = False
        self._last_appbar_rect: QRect | None = None
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
                background-color: #1E1E2E;
                {edge_border}
                color: #CDD6F4;
                font-family: 'Segoe UI', sans-serif;
            }}
            QLineEdit#OmniSearch {{
                background-color: #2A2D3E;
                border: 1px solid #363A4F;
                border-radius: 6px;
                padding: 6px 10px;
                color: #CDD6F4;
                font-size: 13px;
            }}
            QLineEdit#OmniSearch:focus {{
                border: 1px solid #89B4FA;
            }}
            QPushButton#HeaderBtn, QPushButton#PillBtn {{
                background-color: #2A2D3E;
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
                border: 1px solid #89B4FA;
            }}
            QPushButton#HeaderBtn:checked, QPushButton#PillBtn:checked {{
                background-color: #89B4FA;
                color: #1E1E2E;
                border-color: #89B4FA;
            }}
            QPushButton#HeaderBtn:checked:focus, QPushButton#PillBtn:checked:focus {{
                border: 2px solid #CDD6F4;
            }}
            QListWidget {{
                background-color: #2A2D3E;
                border: 1px solid #363A4F;
                border-radius: 6px;
                color: #CDD6F4;
                padding: 4px;
            }}
            """
        )
        self.setObjectName("SidebarRoot")

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(10)

        # --- Row 1: Omni-Bar Search + Profile + Dock Edge + AppBar + Pin ---
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

        self.btn_dock_edge = QPushButton(self.DOCK_EDGE_SYMBOLS[self.dock_edge])
        self.btn_dock_edge.setObjectName("HeaderBtn")
        self.btn_dock_edge.setToolTip(
            "Dock Edge: Right (Click to cycle edge, Right-click for menu)"
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
        self.btn_pin.setToolTip("Pin sidebar open (disable auto-hide on focus loss)")
        self.btn_pin.toggled.connect(self._on_pin_toggled)
        top_row.addWidget(self.btn_pin)

        root_layout.addLayout(top_row)

        # --- Row 2: Panel Switcher Bar (Shift+F9) ---
        nav_row = QHBoxLayout()
        nav_row.setSpacing(6)

        self.btn_panel_hub = QPushButton("1. Hub (Shortcuts & Notes)")
        self.btn_panel_hub.setObjectName("PillBtn")
        self.btn_panel_hub.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.btn_panel_hub.setMinimumHeight(26)
        self.btn_panel_hub.setCheckable(True)
        self.btn_panel_hub.setChecked(True)
        self.btn_panel_hub.clicked.connect(lambda: self.switch_to_panel(0))

        self.btn_panel_queue = QPushButton("2. Clip Queue (0)")
        self.btn_panel_queue.setObjectName("PillBtn")
        self.btn_panel_queue.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.btn_panel_queue.setMinimumHeight(26)
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
            start_rect = self._compute_hide_rect(end_rect)
        return start_rect, end_rect

    @staticmethod
    def _exec_menu(menu: QMenu, global_pos):
        return menu.exec(global_pos)

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
                f"Dock Edge: {norm.capitalize()} (Click to cycle edge, Right-click for menu)"
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
        self.sig_appbar_toggled.emit(self.appbar_enabled)

    def toggle_sidebar(self) -> None:
        if self.isVisible() and not self._is_closing:
            self.hide_sidebar(restore_focus=True)
        else:
            self.show_sidebar()

    def show_sidebar(self) -> None:
        self.hooks.remember_foreground_window(int(self.winId()))
        self._is_closing = False

        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        start_rect, end_rect = self._resolve_target_rects(screen)

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
        self.set_appbar_mode(bool(checked))

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
    def eventFilter(self, obj, event) -> bool:
        if (
            self.isVisible()
            and event.type() == QEvent.Type.KeyPress
            and isinstance(event, QKeyEvent)
            and not event.isAutoRepeat()
            and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
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

    def changeEvent(self, event: QEvent) -> None:
        if (
            event.type() == QEvent.Type.WindowDeactivate
            and not self.is_pinned
            and not self.appbar_enabled
            and self.isVisible()
            and not self._is_closing
        ):
            self.hide_sidebar(restore_focus=False)
        super().changeEvent(event)

    def closeEvent(self, event) -> None:
        self._unregister_appbar_if_needed()
        super().closeEvent(event)