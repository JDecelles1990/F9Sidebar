import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import urllib.parse

from PySide6.QtCore import QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QIcon, QKeyEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
import qtawesome as qta

from icon_provider import get_shortcut_icon

try:
    from shiboken6 import isValid as _qt_is_valid
except ImportError:  # pragma: no cover - shiboken6 ships with PySide6
    def _qt_is_valid(obj) -> bool:
        return obj is not None


def _safe_qta_icon(icon_name: str, color: str) -> QIcon:
    try:
        return qta.icon(icon_name or "fa5s.sticky-note", color=color)
    except Exception:
        return qta.icon("fa5s.sticky-note", color=color)


def _infer_category(target: str, prefer_folder: bool = False) -> str:
    cleaned = target.strip()
    if cleaned.lower().startswith(("http://", "https://")):
        return "url"
    if prefer_folder:
        return "folder"
    try:
        if cleaned and Path(cleaned).is_dir():
            return "folder"
    except OSError:
        pass
    return "app"


def _derive_title(target: str) -> str:
    cleaned = target.strip()
    if cleaned.lower().startswith(("http://", "https://")):
        parsed = urllib.parse.urlparse(cleaned)
        return parsed.netloc or cleaned
    p = Path(cleaned)
    return p.stem or p.name or cleaned


class ShortcutDialog(QDialog):
    """Modal dialog for creating or editing a shortcut tile."""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        title: str = "",
        target: str = "",
        category: str = "app",
        is_edit: bool = False,
    ):
        super().__init__(parent)
        self._prefer_folder = category == "folder"
        self.setWindowTitle("Edit Shortcut" if is_edit else "Add Shortcut")
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.setModal(True)
        self.setMinimumWidth(340)

        self._setup_styles()
        self._build_ui(title, target)

    def _setup_styles(self) -> None:
        self.setStyleSheet(
            """
            QDialog {
                background-color: #1E1E2E;
                color: #CDD6F4;
                font-family: 'Segoe UI', sans-serif;
            }
            QLabel {
                color: #CDD6F4;
                font-size: 12px;
            }
            QLineEdit {
                background-color: #2A2D3E;
                border: 1px solid #363A4F;
                border-radius: 5px;
                padding: 6px 8px;
                color: #CDD6F4;
                font-size: 12px;
            }
            QLineEdit:focus {
                border-color: #89B4FA;
            }
            QPushButton {
                background-color: #2A2D3E;
                border: 1px solid #363A4F;
                border-radius: 5px;
                color: #CDD6F4;
                padding: 5px 10px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #363A4F;
                border-color: #89B4FA;
            }
            """
        )

    def _build_ui(self, title: str, target: str) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        form = QFormLayout()
        form.setSpacing(8)

        self.title_input = QLineEdit(title)
        self.title_input.setPlaceholderText("Display title (e.g. GitHub, Projects)")
        form.addRow("Title:", self.title_input)

        self.target_input = QLineEdit(target)
        self.target_input.setPlaceholderText("Path to .exe / folder, or https:// URL")
        self.target_input.textChanged.connect(self._on_target_changed)
        form.addRow("Target:", self.target_input)

        root.addLayout(form)

        browse_row = QHBoxLayout()
        browse_row.setSpacing(6)

        self.btn_browse_file = QPushButton("Browse File...")
        self.btn_browse_file.clicked.connect(self._browse_file)
        browse_row.addWidget(self.btn_browse_file)

        self.btn_browse_folder = QPushButton("Browse Folder...")
        self.btn_browse_folder.clicked.connect(self._browse_folder)
        browse_row.addWidget(self.btn_browse_folder)

        browse_row.addStretch(1)
        root.addLayout(browse_row)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        root.addWidget(self.button_box)

        self._update_ok_state()

    def _on_target_changed(self, text: str) -> None:
        cleaned = text.strip()
        if cleaned.lower().startswith(("http://", "https://")):
            self._prefer_folder = False
        elif cleaned:
            try:
                self._prefer_folder = Path(cleaned).is_dir()
            except OSError:
                self._prefer_folder = False
        self._update_ok_state()

    def _update_ok_state(self) -> None:
        ok_btn = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_btn is not None:
            ok_btn.setEnabled(bool(self.target_input.text().strip()))

    def _browse_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Application or File",
            "",
            "Executables & Files (*.exe *.lnk *.bat *.cmd *.*);;All Files (*)",
        )
        if path:
            self._prefer_folder = False
            self.target_input.setText(path)
            if not self.title_input.text().strip():
                self.title_input.setText(Path(path).stem or Path(path).name)

    def _browse_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder:
            self._prefer_folder = True
            self.target_input.setText(folder)
            if not self.title_input.text().strip():
                self.title_input.setText(Path(folder).name or folder)

    def get_data(self) -> Tuple[str, str, str]:
        target = self.target_input.text().strip()
        title = self.title_input.text().strip() or _derive_title(target)
        category = _infer_category(target, prefer_folder=self._prefer_folder)
        return title, target, category


class PanelHub(QWidget):
    """Panel 1: 6-column Shortcut Grid (top) + Vertical-Tab Notes Editor (bottom)."""

    GRID_COLUMNS = 6
    TILE_SIZE = 38
    TILE_ICON_SIZE = 22

    def __init__(self, db_manager, parent_sidebar):
        super().__init__(parent_sidebar)
        self.db = db_manager
        self.parent_sidebar = parent_sidebar
        self.current_query = ""
        self.active_tab_id: Optional[int] = None
        self._active_profile: str = getattr(self.db, "profile", "work")
        self._loading_note = False
        self._shortcut_buttons: Dict[int, QToolButton] = {}
        self._tab_buttons: Dict[int, tuple[QToolButton, str]] = {}
        self._tab_shortcuts: List[QShortcut] = []

        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(500)
        self.save_timer.timeout.connect(self._save_active_note)

        self.setObjectName("PanelHub")
        self._setup_styles()
        self._build_ui()
        self._setup_shortcuts()
        self.refresh("")

    def _setup_styles(self) -> None:
        self.setStyleSheet(
            """
            QWidget#PanelHub {
                background-color: #1E1E2E;
                color: #CDD6F4;
            }
            QSplitter::handle {
                background-color: #363A4F;
                height: 3px;
                border-radius: 1px;
                margin: 2px 0px;
            }
            QSplitter::handle:hover {
                background-color: #89B4FA;
            }
            QLabel#SectionTitle {
                color: #A6ADC8;
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 0.4px;
                text-transform: uppercase;
            }
            QLabel#EmptyHint {
                color: #6C7086;
                font-size: 12px;
                padding: 8px;
            }
            QPushButton#AddShortcutBtn {
                background-color: #2A2D3E;
                border: 1px solid #363A4F;
                border-radius: 5px;
                color: #CDD6F4;
                font-size: 14px;
                font-weight: 700;
                padding: 0px;
            }
            QPushButton#AddShortcutBtn:hover {
                background-color: #89B4FA;
                border-color: #89B4FA;
                color: #1E1E2E;
            }
            QScrollArea#GridScroll {
                background-color: #2A2D3E;
                border: 1px solid #363A4F;
                border-radius: 6px;
            }
            QWidget#GridContainer {
                background-color: transparent;
            }
            QToolButton#ShortcutTile {
                background-color: #1E1E2E;
                border: 1px solid #363A4F;
                border-radius: 6px;
                padding: 4px;
            }
            QToolButton#ShortcutTile:hover {
                background-color: #363A4F;
                border-color: #89B4FA;
            }
            QToolButton#ShortcutTile:pressed {
                background-color: #45475A;
            }
            QPlainTextEdit#NoteEditor {
                background-color: #2A2D3E;
                border: 1px solid #363A4F;
                border-radius: 6px;
                color: #CDD6F4;
                padding: 8px;
                font-family: 'Consolas', 'Segoe UI', monospace;
                font-size: 12px;
                selection-background-color: #89B4FA;
                selection-color: #1E1E2E;
            }
            QPlainTextEdit#NoteEditor:focus {
                border-color: #89B4FA;
            }
            QLabel#NoteTabLabel {
                color: #A6ADC8;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton#CopyAllBtn {
                background-color: #2A2D3E;
                border: 1px solid #363A4F;
                border-radius: 5px;
                color: #CDD6F4;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton#CopyAllBtn:hover {
                background-color: #89B4FA;
                border-color: #89B4FA;
                color: #1E1E2E;
            }
            QWidget#NoteRail {
                background-color: #2A2D3E;
                border: 1px solid #363A4F;
                border-radius: 6px;
            }
            QToolButton#NoteTabBtn {
                background-color: transparent;
                border: 1px solid transparent;
                border-radius: 5px;
                padding: 3px;
            }
            QToolButton#NoteTabBtn:hover {
                background-color: #363A4F;
            }
            QToolButton#NoteTabBtn:checked {
                background-color: #89B4FA;
                border-color: #89B4FA;
            }
            """
        )

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.setChildrenCollapsible(False)

        # === Top Section: Compact Icon-Only Launcher Grid ===
        top_widget = QWidget()
        top_widget.setMinimumHeight(96)
        top_layout = QVBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 4)
        top_layout.setSpacing(6)

        grid_header = QHBoxLayout()
        grid_header.setSpacing(6)
        lbl_shortcuts = QLabel("Shortcuts")
        lbl_shortcuts.setObjectName("SectionTitle")
        grid_header.addWidget(lbl_shortcuts)
        grid_header.addStretch(1)

        self.btn_add_shortcut = QPushButton("+")
        self.btn_add_shortcut.setObjectName("AddShortcutBtn")
        self.btn_add_shortcut.setFixedSize(24, 24)
        self.btn_add_shortcut.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add_shortcut.setToolTip("Add Shortcut (+)")
        self.btn_add_shortcut.clicked.connect(self._on_add_shortcut)
        grid_header.addWidget(self.btn_add_shortcut)
        top_layout.addLayout(grid_header)

        self.grid_scroll = QScrollArea()
        self.grid_scroll.setObjectName("GridScroll")
        self.grid_scroll.setWidgetResizable(True)
        self.grid_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.grid_container = QWidget()
        self.grid_container.setObjectName("GridContainer")
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setContentsMargins(8, 8, 8, 8)
        self.grid_layout.setSpacing(8)
        self.grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        self.grid_scroll.setWidget(self.grid_container)
        top_layout.addWidget(self.grid_scroll, 1)

        # === Bottom Section: Notes Editor + Right-Edge Vertical Icon Rail ===
        bottom_widget = QWidget()
        bottom_widget.setMinimumHeight(140)
        bottom_layout = QHBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(0, 4, 0, 0)
        bottom_layout.setSpacing(6)

        editor_col = QVBoxLayout()
        editor_col.setContentsMargins(0, 0, 0, 0)
        editor_col.setSpacing(6)

        self.note_editor = QPlainTextEdit()
        self.note_editor.setObjectName("NoteEditor")
        self.note_editor.setPlaceholderText("Write quick notes... (auto-saved)")
        self.note_editor.textChanged.connect(self._on_note_text_changed)
        editor_col.addWidget(self.note_editor, 1)

        note_toolbar = QHBoxLayout()
        note_toolbar.setSpacing(6)

        self.lbl_note_tab = QLabel("Scratchpad")
        self.lbl_note_tab.setObjectName("NoteTabLabel")
        note_toolbar.addWidget(self.lbl_note_tab)
        note_toolbar.addStretch(1)

        self.btn_copy_all = QPushButton("Copy All")
        self.btn_copy_all.setObjectName("CopyAllBtn")
        self.btn_copy_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_copy_all.setToolTip("Copy entire note tab to clipboard")
        self.btn_copy_all.clicked.connect(self._on_copy_all)
        note_toolbar.addWidget(self.btn_copy_all)

        editor_col.addLayout(note_toolbar)
        bottom_layout.addLayout(editor_col, 1)

        self.rail_widget = QWidget()
        self.rail_widget.setObjectName("NoteRail")
        self.rail_widget.setFixedWidth(36)
        self.rail_layout = QVBoxLayout(self.rail_widget)
        self.rail_layout.setContentsMargins(2, 4, 2, 4)
        self.rail_layout.setSpacing(6)
        self.rail_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        self.tab_button_group = QButtonGroup(self)
        self.tab_button_group.setExclusive(True)
        self.tab_button_group.idClicked.connect(self._on_note_tab_clicked)

        bottom_layout.addWidget(self.rail_widget)

        self.splitter.addWidget(top_widget)
        self.splitter.addWidget(bottom_widget)
        self.splitter.setSizes([185, 320])
        root.addWidget(self.splitter, 1)

    def refresh(self, search_query: str = "") -> None:
        self.current_query = search_query or ""
        current_profile = getattr(self.db, "profile", "work")
        profile_switched = current_profile != self._active_profile

        if profile_switched:
            # Avoid flushing previous profile's text into the newly selected DB.
            self.save_timer.stop()
            self._active_profile = current_profile
            self.active_tab_id = None
        elif self.save_timer.isActive():
            self.save_timer.stop()
            self._save_active_note()

        self._refresh_shortcuts_grid()
        self._refresh_note_tabs()

    def _refresh_shortcuts_grid(self) -> None:
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        self._shortcut_buttons.clear()
        shortcuts = self.db.get_shortcuts(self.current_query)

        if not shortcuts:
            hint = QLabel(
                "No matching shortcuts"
                if self.current_query
                else "No shortcuts yet. Click + to add an app, folder, or URL."
            )
            hint.setObjectName("EmptyHint")
            hint.setWordWrap(True)
            self.grid_layout.addWidget(hint, 0, 0, 1, self.GRID_COLUMNS)
            return

        for idx, shortcut in enumerate(shortcuts):
            row = idx // self.GRID_COLUMNS
            col = idx % self.GRID_COLUMNS
            tile = self._create_shortcut_tile(shortcut)
            self._shortcut_buttons[int(shortcut["id"])] = tile
            self.grid_layout.addWidget(tile, row, col)

    def _create_shortcut_tile(self, shortcut: Dict) -> QToolButton:
        sid = int(shortcut["id"])
        title = str(shortcut.get("title", ""))
        target = str(shortcut.get("target", ""))

        btn = QToolButton(self.grid_container)
        btn.setObjectName("ShortcutTile")
        btn.setFixedSize(self.TILE_SIZE, self.TILE_SIZE)
        btn.setIconSize(QSize(self.TILE_ICON_SIZE, self.TILE_ICON_SIZE))
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip(f"{title}\n{target}" if title and target else (title or target))
        btn.setIcon(
            get_shortcut_icon(
                shortcut,
                self.db.icons_dir,
                on_favicon_ready=self._on_favicon_ready,
            )
        )
        btn.clicked.connect(lambda checked=False, s=dict(shortcut): self._launch_shortcut(s))
        btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        btn.customContextMenuRequested.connect(
            lambda pos, b=btn, s=dict(shortcut): self._show_shortcut_menu(b, pos, s)
        )
        return btn

    def _on_favicon_ready(self, shortcut_id: int, icon_path: str) -> None:
        if not _qt_is_valid(self):
            return
        btn = self._shortcut_buttons.get(shortcut_id)
        if btn is not None and _qt_is_valid(btn):
            icon = QIcon(icon_path)
            if not icon.isNull():
                btn.setIcon(icon)

    def _launch_shortcut(self, shortcut: Dict) -> None:
        target = str(shortcut.get("target", "")).strip()
        category = str(shortcut.get("category", "app")).lower().strip()
        if not target:
            return

        if category == "url" or target.startswith(("http://", "https://")):
            QDesktopServices.openUrl(QUrl(target))
            return

        try:
            os.startfile(target)
        except Exception:
            QDesktopServices.openUrl(QUrl.fromLocalFile(target))

    def _run_with_pin_guard(self, func) -> None:
        sidebar = self.parent_sidebar
        if sidebar is not None and hasattr(sidebar, "is_pinned"):
            was_pinned = sidebar.is_pinned
            sidebar.is_pinned = True
            try:
                func()
            finally:
                sidebar.is_pinned = was_pinned
        else:
            func()

    def _on_add_shortcut(self) -> None:
        def _open_dialog() -> None:
            dlg = ShortcutDialog(self)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                title, target, category = dlg.get_data()
                if target:
                    self.db.add_shortcut(title, target, category=category)
                    self._refresh_shortcuts_grid()

        self._run_with_pin_guard(_open_dialog)

    def _show_shortcut_menu(self, btn: QToolButton, pos, shortcut: Dict) -> None:
        def _open_menu() -> None:
            menu = QMenu(btn)
            menu.setStyleSheet(
                """
                QMenu {
                    background-color: #2A2D3E;
                    border: 1px solid #363A4F;
                    color: #CDD6F4;
                    padding: 4px;
                }
                QMenu::item {
                    padding: 6px 16px;
                    border-radius: 4px;
                }
                QMenu::item:selected {
                    background-color: #89B4FA;
                    color: #1E1E2E;
                }
                """
            )
            act_edit = menu.addAction("Edit")
            act_delete = menu.addAction("Delete")
            chosen = menu.exec(btn.mapToGlobal(pos))
            if chosen == act_edit:
                self._edit_shortcut(shortcut)
            elif chosen == act_delete:
                self._delete_shortcut(int(shortcut["id"]))

        self._run_with_pin_guard(_open_menu)

    def _edit_shortcut(self, shortcut: Dict) -> None:
        sid = int(shortcut["id"])
        old_target = str(shortcut.get("target", ""))

        dlg = ShortcutDialog(
            self,
            title=str(shortcut.get("title", "")),
            target=old_target,
            category=str(shortcut.get("category", "app")),
            is_edit=True,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        title, target, category = dlg.get_data()
        if not target:
            return

        if target != old_target:
            cached_png = Path(self.db.icons_dir) / f"{sid}.png"
            cached_png.unlink(missing_ok=True)

        if hasattr(self.db, "update_shortcut"):
            self.db.update_shortcut(sid, title, target, category)
        else:
            with self.db._connect() as conn:
                conn.execute(
                    """
                    UPDATE shortcuts
                    SET title = ?, target = ?, category = ?
                    WHERE id = ?
                    """,
                    (title, target, category, sid),
                )
        self._refresh_shortcuts_grid()

    def _delete_shortcut(self, shortcut_id: int) -> None:
        if hasattr(self.db, "delete_shortcut"):
            self.db.delete_shortcut(shortcut_id)
        else:
            with self.db._connect() as conn:
                conn.execute("DELETE FROM shortcuts WHERE id = ?", (shortcut_id,))

        cached_png = Path(self.db.icons_dir) / f"{shortcut_id}.png"
        cached_png.unlink(missing_ok=True)
        self._refresh_shortcuts_grid()

    def _refresh_note_tabs(self) -> None:
        tabs = self.db.get_note_tabs()

        for btn in list(self.tab_button_group.buttons()):
            self.tab_button_group.removeButton(btn)
        while self.rail_layout.count():
            item = self.rail_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._tab_buttons.clear()

        if not tabs:
            self.active_tab_id = None
            self.lbl_note_tab.setText("Notes")
            self._set_editor_text_silently("")
            return

        tab_ids = [int(t["id"]) for t in tabs]
        if self.active_tab_id not in tab_ids:
            self.active_tab_id = tab_ids[0]

        active_tab = None
        for idx, tab in enumerate(tabs):
            tid = int(tab["id"])
            icon_name = str(tab.get("icon_name", "fa5s.sticky-note"))
            tab_name = str(tab.get("tab_name", f"Tab {tid}"))
            is_active = tid == self.active_tab_id
            if is_active:
                active_tab = tab

            btn = QToolButton(self.rail_widget)
            btn.setObjectName("NoteTabBtn")
            btn.setCheckable(True)
            btn.setChecked(is_active)
            btn.setFixedSize(30, 30)
            btn.setIconSize(QSize(16, 16))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            shortcut_hint = f" (Ctrl+{idx + 1})" if idx < 4 else ""
            btn.setToolTip(f"{tab_name}{shortcut_hint}")
            btn.setIcon(_safe_qta_icon(icon_name, "#1E1E2E" if is_active else "#A6ADC8"))

            self.tab_button_group.addButton(btn, tid)
            self.rail_layout.addWidget(btn)
            self._tab_buttons[tid] = (btn, icon_name)

        self.rail_layout.addStretch(1)

        if active_tab is not None:
            self.lbl_note_tab.setText(str(active_tab.get("tab_name", "Notes")))
            self._set_editor_text_silently(str(active_tab.get("content") or ""))

    def _set_editor_text_silently(self, content: str) -> None:
        if self.note_editor.toPlainText() == content:
            return
        self._loading_note = True
        try:
            self.note_editor.setPlainText(content)
        finally:
            self._loading_note = False

    def _on_note_tab_clicked(self, tab_id: int) -> None:
        if tab_id == self.active_tab_id:
            return

        if self.save_timer.isActive():
            self.save_timer.stop()
            self._save_active_note()

        self.active_tab_id = tab_id
        for tid, (btn, icon_name) in self._tab_buttons.items():
            is_active = tid == tab_id
            btn.setIcon(_safe_qta_icon(icon_name, "#1E1E2E" if is_active else "#A6ADC8"))

        tabs = {int(t["id"]): t for t in self.db.get_note_tabs()}
        selected = tabs.get(tab_id)
        if selected is not None:
            self.lbl_note_tab.setText(str(selected.get("tab_name", "Notes")))
            self._set_editor_text_silently(str(selected.get("content") or ""))

    def _on_note_text_changed(self) -> None:
        if self._loading_note or self.active_tab_id is None:
            return
        self.save_timer.start()

    def _save_active_note(self) -> None:
        if self.active_tab_id is None:
            return
        self.db.update_note_content(self.active_tab_id, self.note_editor.toPlainText())

    def _on_copy_all(self) -> None:
        QApplication.clipboard().setText(self.note_editor.toPlainText())
        self.btn_copy_all.setText("Copied!")
        QTimer.singleShot(800, self._restore_copy_all_label)

    def _restore_copy_all_label(self) -> None:
        if _qt_is_valid(self) and _qt_is_valid(self.btn_copy_all):
            self.btn_copy_all.setText("Copy All")

    def _setup_shortcuts(self) -> None:
        self._tab_shortcuts.clear()
        for idx in range(4):
            shortcut = QShortcut(QKeySequence(f"Ctrl+{idx + 1}"), self)
            shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
            shortcut.setEnabled(self.isVisible())
            shortcut.activated.connect(lambda i=idx: self.switch_to_tab_index(i))
            self._tab_shortcuts.append(shortcut)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        for shortcut in self._tab_shortcuts:
            shortcut.setEnabled(True)

    def hideEvent(self, event) -> None:
        for shortcut in self._tab_shortcuts:
            shortcut.setEnabled(False)
        super().hideEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if (
            self.isVisible()
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
            and Qt.Key.Key_1 <= event.key() <= Qt.Key.Key_4
        ):
            self.switch_to_tab_index(event.key() - Qt.Key.Key_1)
            event.accept()
            return
        super().keyPressEvent(event)

    def switch_to_tab_index(self, index: int) -> None:
        tabs = self.db.get_note_tabs()
        if not (0 <= index < len(tabs)):
            return
        target_id = int(tabs[index]["id"])
        btn_entry = self._tab_buttons.get(target_id)
        if btn_entry is not None:
            btn_entry[0].setChecked(True)
        self._on_note_tab_clicked(target_id)
