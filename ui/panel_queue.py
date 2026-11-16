import base64
import html
from typing import Callable, Dict, List, Optional

from PySide6.QtCore import QBuffer, QEvent, QIODevice, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import (
    QFontMetrics,
    QImage,
    QKeyEvent,
    QKeySequence,
    QPixmap,
    QShortcut,
    QTextCursor,
    QTextDocument,
    QTextImageFormat,
    QTextLayout,
    QTextOption,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
import qtawesome as qta


try:
    from shiboken6 import isValid as _qt_is_valid
except ImportError:  # pragma: no cover - shiboken6 ships with PySide6
    def _qt_is_valid(obj) -> bool:
        return obj is not None


def _decode_image_data_uri(data_uri: str) -> QImage:
    raw = (data_uri or "").strip()
    if not raw.startswith("data:image/") or "," not in raw:
        return QImage()
    try:
        b64_part = raw.split(",", 1)[1]
        img_bytes = base64.b64decode(b64_part)
        return QImage.fromData(img_bytes)
    except Exception:
        return QImage()


def _encode_image_data_uri(image: QImage) -> str:
    if image is None or image.isNull():
        return ""
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buf, "PNG")
    b64 = base64.b64encode(bytes(buf.data())).decode("ascii")
    return f"data:image/png;base64,{b64}"


class ElidedTwoLineLabel(QLabel):
    """Displays up to 2 wrapped lines with right-elision and full text in tooltip."""

    def __init__(self, text: str = "", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._full_text = text or ""
        self.setWordWrap(False)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.setToolTip(self._full_text)
        self._update_height_bounds()
        self._update_elision()

    def set_full_text(self, text: str) -> None:
        self._full_text = text or ""
        self.setToolTip(self._full_text)
        self._update_height_bounds()
        self._update_elision()

    def full_text(self) -> str:
        return self._full_text

    def sizeHint(self) -> QSize:
        fm = QFontMetrics(self.font())
        lines = 2 if "\n" in super().text() else 1
        height = max(fm.lineSpacing() * lines + 4, fm.lineSpacing() + 4)
        return QSize(120, height)

    def minimumSizeHint(self) -> QSize:
        fm = QFontMetrics(self.font())
        return QSize(40, fm.lineSpacing() + 4)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_elision()

    def _update_height_bounds(self) -> None:
        fm = QFontMetrics(self.font())
        self.setMaximumHeight(fm.lineSpacing() * 2 + 6)

    def _update_elision(self) -> None:
        avail_width = self.width() - 2
        if avail_width <= 20:
            avail_width = 210
        elided = self._elide_two_lines(self._full_text, avail_width)
        super().setText(elided)
        fm = QFontMetrics(self.font())
        line_count = 2 if "\n" in elided else 1
        self.setFixedHeight(fm.lineSpacing() * line_count + 4)

    def _elide_two_lines(self, text: str, max_width: int) -> str:
        normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not normalized:
            return ""

        # QTextLayout uses Unicode line separator for explicit line breaks inside a block.
        layout_source = normalized.replace("\n", "\u2028")
        text_option = QTextOption()
        text_option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)

        layout = QTextLayout(layout_source, self.font())
        layout.setTextOption(text_option)
        layout.beginLayout()

        line1 = layout.createLine()
        if not line1.isValid():
            layout.endLayout()
            return ""
        line1.setLineWidth(max_width)

        line2 = layout.createLine()
        if line2.isValid():
            line2.setLineWidth(max_width)

        layout.endLayout()

        l1_end = line1.textStart() + line1.textLength()
        l1_text = layout_source[line1.textStart():l1_end].rstrip("\u2028 ")

        if not line2.isValid():
            if l1_end < len(layout_source):
                fm = QFontMetrics(self.font())
                return fm.elidedText(l1_text + "\u2026", Qt.TextElideMode.ElideRight, max_width)
            return l1_text

        l2_start = line2.textStart()
        l2_end = l2_start + line2.textLength()
        l2_raw = layout_source[l2_start:l2_end].rstrip("\u2028 ")

        fm = QFontMetrics(self.font())
        if l2_end < len(layout_source):
            l2_text = fm.elidedText(l2_raw + "\u2026", Qt.TextElideMode.ElideRight, max_width)
        else:
            l2_text = fm.elidedText(l2_raw, Qt.TextElideMode.ElideRight, max_width)

        return f"{l1_text}\n{l2_text}" if l2_text else l1_text


class ClipRowWidget(QWidget):
    """Custom row widget for a single clip entry inside the QListWidget."""

    def __init__(
        self,
        clip_data: Dict,
        on_checked: Callable[[int, bool], None],
        on_send_notes: Callable[[Dict, QPushButton], None],
        on_delete: Callable[[int], None],
        on_send_menu: Optional[Callable[[Dict, QPushButton, object], None]] = None,
        on_quick_copy: Optional[Callable[[Dict, "ClipRowWidget"], None]] = None,
        on_edit_saved: Optional[Callable[[int, str], None]] = None,
        on_edit_image: Optional[Callable[[int, str], None]] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.clip_data = dict(clip_data)
        self.clip_id = int(clip_data["id"])
        self.content = str(clip_data["content"])
        self.source_type = str(clip_data.get("source_type", "text"))
        if self.content.strip().startswith("data:image/"):
            self.source_type = "image"
        self.is_checked = bool(clip_data.get("is_checked", 0))
        self._on_quick_copy = on_quick_copy
        self._on_edit_saved = on_edit_saved
        self._on_edit_image = on_edit_image
        self._is_editing = False

        self.setObjectName("ClipRowWidget")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)

        # 1. Checkbox synced to db.set_clip_checked
        self.checkbox = QCheckBox()
        self.checkbox.setObjectName("ClipCheckBox")
        self.checkbox.setChecked(self.is_checked)
        self.checkbox.setToolTip("Select clip for batch copy")
        self.checkbox.toggled.connect(self._handle_toggled)
        self._on_checked_cb = on_checked
        layout.addWidget(self.checkbox)

        # 2. Source-type qtawesome icon + optional thumbnail preview for image clips
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(20, 20)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.icon_label.setPixmap(self._icon_for_source(self.source_type).pixmap(14, 14))
        layout.addWidget(self.icon_label)

        self.thumb_label = QLabel(self)
        self.thumb_label.setObjectName("ClipThumbLabel")
        self.thumb_label.setFixedSize(44, 30)
        self.thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.thumb_label.hide()
        layout.addWidget(self.thumb_label)

        display_text = self.content
        tooltip_text = self.content
        if self.source_type == "image":
            img = _decode_image_data_uri(self.content)
            if not img.isNull():
                pix = QPixmap.fromImage(img).scaled(
                    42,
                    28,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self.thumb_label.setPixmap(pix)
                self.thumb_label.show()
                self.icon_label.hide()
                display_text = f"Image ({img.width()}×{img.height()} px)"
                tooltip_text = (
                    f"Captured Image ({img.width()}×{img.height()} px)\n"
                    "Click 📋 to copy • Double-click or ✎ to edit"
                )
            else:
                display_text = "Captured Image"
                tooltip_text = "Captured Image"

        self.setToolTip(tooltip_text)

        # 3. 2-line elided text preview + hidden inline editor (full text/info in tooltip)
        self.preview_label = ElidedTwoLineLabel(display_text, self)
        self.preview_label.setToolTip(tooltip_text)
        layout.addWidget(self.preview_label, 1)

        self.inline_edit = QLineEdit(self)
        self.inline_edit.setObjectName("ClipInlineEdit")
        self.inline_edit.hide()
        self.inline_edit.installEventFilter(self)
        layout.addWidget(self.inline_edit, 1)

        # 4. Quick-copy button
        self.btn_copy = QPushButton("📋")
        self.btn_copy.setObjectName("RowActionBtn")
        self.btn_copy.setFixedSize(24, 26)
        self.btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_copy.setToolTip("Quick copy clip to clipboard")
        self.btn_copy.clicked.connect(self.trigger_quick_copy)
        layout.addWidget(self.btn_copy)

        # 5. Inline edit button
        self.btn_edit = QPushButton("✎")
        self.btn_edit.setObjectName("RowActionBtn")
        self.btn_edit.setFixedSize(24, 26)
        self.btn_edit.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_edit.setToolTip("Edit clip (Double-click row)")
        self.btn_edit.clicked.connect(self._on_edit_btn_clicked)
        layout.addWidget(self.btn_edit)

        # 6. Promote / Send to Notes button
        self.btn_send_notes = QPushButton("→")
        self.btn_send_notes.setObjectName("RowActionBtn")
        self.btn_send_notes.setFixedSize(26, 26)
        self.btn_send_notes.setCursor(Qt.CursorShape.PointingHandCursor)
        if self.source_type in ("url", "path"):
            self.btn_send_notes.setToolTip(
                "Promote to Shortcut or Note (→) | Right-click for options"
            )
        else:
            self.btn_send_notes.setToolTip(
                "Send to Active Note (→) | Right-click to pick note tab (Ctrl+1..9)"
            )
        self.btn_send_notes.clicked.connect(
            lambda: on_send_notes(self.clip_data, self.btn_send_notes)
        )
        if on_send_menu is not None:
            self.btn_send_notes.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            self.btn_send_notes.customContextMenuRequested.connect(
                lambda pos: on_send_menu(self.clip_data, self.btn_send_notes, pos)
            )
        layout.addWidget(self.btn_send_notes)

        # 7. Delete button
        self.btn_delete = QPushButton("×")
        self.btn_delete.setObjectName("RowDeleteBtn")
        self.btn_delete.setFixedSize(24, 26)
        self.btn_delete.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_delete.setToolTip("Delete clip (×)")
        self.btn_delete.clicked.connect(lambda: on_delete(self.clip_id))
        layout.addWidget(self.btn_delete)

    def _handle_toggled(self, checked: bool) -> None:
        self.is_checked = checked
        self._on_checked_cb(self.clip_id, checked)

    def trigger_quick_copy(self) -> None:
        if self._on_quick_copy is not None:
            self._on_quick_copy(self.clip_data, self)

    def is_editing(self) -> bool:
        return self._is_editing

    def _on_edit_btn_clicked(self) -> None:
        if self.is_editing():
            self.commit_inline_edit()
        else:
            self.start_inline_edit()

    def start_inline_edit(self) -> None:
        if self.source_type == "image":
            if self._on_edit_image is not None:
                self._on_edit_image(self.clip_id, self.content)
            return
        self._is_editing = True
        self.inline_edit.setText(self.content)
        self.preview_label.hide()
        self.inline_edit.show()
        self.inline_edit.setFocus()
        self.inline_edit.selectAll()
        self.btn_edit.setText("✓")

    def commit_inline_edit(self) -> bool:
        if not self._is_editing:
            return False
        new_text = self.inline_edit.text().strip()
        self._is_editing = False
        self.inline_edit.hide()
        self.preview_label.show()
        self.btn_edit.setText("✎")
        if new_text and new_text != self.content:
            self.content = new_text
            if self._on_edit_saved is not None:
                self._on_edit_saved(self.clip_id, new_text)
            return True
        return False

    def cancel_inline_edit(self) -> None:
        if not self._is_editing:
            return
        self._is_editing = False
        self.inline_edit.hide()
        self.preview_label.show()
        self.btn_edit.setText("✎")

    def eventFilter(self, obj, event) -> bool:
        if obj is self.inline_edit and event.type() == QEvent.Type.KeyPress:
            if isinstance(event, QKeyEvent):
                if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                    self.commit_inline_edit()
                    event.accept()
                    return True
                if event.key() == Qt.Key.Key_Escape:
                    self.cancel_inline_edit()
                    event.accept()
                    return True
        return super().eventFilter(obj, event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.start_inline_edit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    @staticmethod
    def _icon_for_source(source_type: str):
        if source_type == "image":
            return qta.icon("fa5s.image", color="#89B4FA")
        if source_type == "url":
            return qta.icon("fa5s.link", color="#89B4FA")
        if source_type == "path":
            return qta.icon("fa5s.folder-open", color="#89B4FA")
        return qta.icon("fa5s.align-left", color="#A6ADC8")


class ClipListWidget(QListWidget):
    """QListWidget configured for InternalMove reordering of custom row widgets."""

    def __init__(
        self,
        on_rows_reordered: Callable[[], None],
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._on_rows_reordered = on_rows_reordered
        self.setObjectName("ClipList")
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setSpacing(4)

    def dropEvent(self, event) -> None:
        super().dropEvent(event)
        # Defer until Qt finishes removing the original row from QListWidget.
        QTimer.singleShot(0, self._on_rows_reordered)


class PanelQueue(QWidget):
    """Panel 2: Draggable Checkable Clip Queue & Batch-Copy Assembler."""

    JOIN_MODES = [
        ("Lines (\\n)", "\n"),
        ("Paragraphs (\\n\\n)", "\n\n"),
        ("Bullets (- )", "bullets"),
    ]

    def __init__(self, db_manager, parent_sidebar):
        super().__init__(parent_sidebar)
        self.db = db_manager
        self.parent_sidebar = parent_sidebar
        self.current_query = ""
        self._active_profile = getattr(self.db, "profile", "work")
        self._updating_ui = False
        self._restoring_state = False

        self.setObjectName("PanelQueue")
        self._setup_styles()
        self._build_ui()
        self._setup_shortcuts()
        self.restore_workspace_settings()
        self.refresh("")

    def _setup_styles(self) -> None:
        self.setStyleSheet(
            """
            QWidget#PanelQueue {
                background-color: #1E1E2E;
                color: #CDD6F4;
            }
            QCheckBox {
                color: #CDD6F4;
                font-size: 12px;
                spacing: 6px;
            }
            QCheckBox:focus {
                color: #89B4FA;
            }
            QCheckBox::indicator {
                width: 15px;
                height: 15px;
                border-radius: 4px;
                border: 1px solid #363A4F;
                background-color: #1E1E2E;
            }
            QCheckBox::indicator:hover, QCheckBox::indicator:focus {
                border-color: #89B4FA;
            }
            QCheckBox::indicator:checked {
                background-color: #89B4FA;
                border-color: #89B4FA;
            }
            QLabel#CountLabel {
                color: #A6ADC8;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton#ActionBtn {
                background-color: #2A2D3E;
                border: 1px solid #363A4F;
                border-radius: 5px;
                color: #CDD6F4;
                padding: 4px 8px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton#ActionBtn:hover:enabled {
                background-color: #363A4F;
                border-color: #89B4FA;
            }
            QPushButton#ActionBtn:focus {
                border: 1px solid #89B4FA;
            }
            QPushButton#ActionBtn:disabled {
                color: #6C7086;
                border-color: #2A2D3E;
            }
            QListWidget#ClipList {
                background-color: #1E1E2E;
                border: 1px solid #363A4F;
                border-radius: 6px;
                padding: 4px;
                outline: none;
            }
            QListWidget#ClipList::item {
                background-color: #2A2D3E;
                border: 1px solid #363A4F;
                border-radius: 6px;
                color: #CDD6F4;
            }
            QListWidget#ClipList::item:selected {
                background-color: #2A2D3E;
                border: 1px solid #89B4FA;
            }
            QListWidget#ClipList::item:hover {
                border: 1px solid #585B70;
            }
            QWidget#ClipRowWidget {
                background-color: transparent;
            }
            QLineEdit#ClipInlineEdit {
                background-color: #1E1E2E;
                border: 1px solid #89B4FA;
                border-radius: 4px;
                color: #CDD6F4;
                padding: 2px 6px;
                font-size: 12px;
            }
            QLabel#ClipThumbLabel {
                background-color: #1E1E2E;
                border: 1px solid #363A4F;
                border-radius: 4px;
            }
            QLabel {
                color: #CDD6F4;
                font-size: 12px;
                background-color: transparent;
            }
            QPushButton#RowActionBtn, QPushButton#RowDeleteBtn {
                background-color: #1E1E2E;
                border: 1px solid #363A4F;
                border-radius: 4px;
                color: #CDD6F4;
                font-size: 13px;
                font-weight: 700;
                padding: 0px;
            }
            QPushButton#RowActionBtn:hover {
                background-color: #89B4FA;
                border-color: #89B4FA;
                color: #1E1E2E;
            }
            QPushButton#RowActionBtn:focus, QPushButton#RowDeleteBtn:focus {
                border: 1px solid #89B4FA;
            }
            QPushButton#RowDeleteBtn {
                color: #A6ADC8;
            }
            QPushButton#RowDeleteBtn:hover {
                background-color: #F38BA8;
                border-color: #F38BA8;
                color: #1E1E2E;
            }
            QComboBox#JoinCombo {
                background-color: #2A2D3E;
                border: 1px solid #363A4F;
                border-radius: 6px;
                color: #CDD6F4;
                padding: 6px 10px;
                font-size: 12px;
                font-weight: 600;
            }
            QComboBox#JoinCombo:hover, QComboBox#JoinCombo:focus {
                border-color: #89B4FA;
            }
            QComboBox#JoinCombo::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox#JoinCombo QAbstractItemView {
                background-color: #2A2D3E;
                border: 1px solid #363A4F;
                color: #CDD6F4;
                selection-background-color: #89B4FA;
                selection-color: #1E1E2E;
            }
            QPushButton#PrimaryCopyBtn {
                background-color: #89B4FA;
                border: 1px solid #89B4FA;
                border-radius: 6px;
                color: #1E1E2E;
                padding: 7px 12px;
                font-size: 12px;
                font-weight: 700;
            }
            QPushButton#PrimaryCopyBtn:hover:enabled {
                background-color: #A6C8FF;
                border-color: #A6C8FF;
            }
            QPushButton#PrimaryCopyBtn:focus {
                border: 2px solid #CDD6F4;
            }
            QPushButton#PrimaryCopyBtn:disabled {
                background-color: #2A2D3E;
                border-color: #363A4F;
                color: #6C7086;
            }
            """
        )

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        # --- Top Action Header ---
        header_row = QHBoxLayout()
        header_row.setSpacing(6)

        self.chk_select_all = QCheckBox("Select All")
        self.chk_select_all.clicked.connect(self._on_select_all_clicked)
        header_row.addWidget(self.chk_select_all)

        self.lbl_count = QLabel("0 clips")
        self.lbl_count.setObjectName("CountLabel")
        header_row.addWidget(self.lbl_count)

        header_row.addStretch(1)

        self.btn_clear_checked = QPushButton("Clear Checked")
        self.btn_clear_checked.setObjectName("ActionBtn")
        self.btn_clear_checked.setToolTip("Delete all checked clips from the queue")
        self.btn_clear_checked.clicked.connect(self._on_clear_checked)
        header_row.addWidget(self.btn_clear_checked)

        self.btn_clear_all = QPushButton("Clear All")
        self.btn_clear_all.setObjectName("ActionBtn")
        self.btn_clear_all.setToolTip("Delete all clips from the queue")
        self.btn_clear_all.clicked.connect(self._on_clear_all)
        header_row.addWidget(self.btn_clear_all)

        root.addLayout(header_row)

        # --- Draggable Checkable Queue ---
        self.list_widget = ClipListWidget(on_rows_reordered=self._on_rows_reordered, parent=self)
        root.addWidget(self.list_widget, 1)

        # --- Bottom Batch-Copy Assembler Bar ---
        bottom_bar = QHBoxLayout()
        bottom_bar.setSpacing(8)

        self.cmb_join_format = QComboBox()
        self.cmb_join_format.setObjectName("JoinCombo")
        self.cmb_join_format.setToolTip("Choose separator format when copying selected clips")
        for label, mode_value in self.JOIN_MODES:
            self.cmb_join_format.addItem(label, mode_value)
        self.cmb_join_format.currentIndexChanged.connect(self._on_join_format_changed)
        bottom_bar.addWidget(self.cmb_join_format, 1)

        self.btn_copy_selected = QPushButton("Copy Selected (0)")
        self.btn_copy_selected.setObjectName("PrimaryCopyBtn")
        self.btn_copy_selected.setToolTip("Join checked clips in visual order and copy (Ctrl+C)")
        self.btn_copy_selected.clicked.connect(self.copy_selected_clips)
        bottom_bar.addWidget(self.btn_copy_selected, 1)

        root.addLayout(bottom_bar)

    def _setup_shortcuts(self) -> None:
        self.copy_shortcut = QShortcut(QKeySequence("Ctrl+C"), self)
        self.copy_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self.copy_shortcut.setEnabled(False)
        self.copy_shortcut.activated.connect(self._on_ctrl_c)

        if self.parent_sidebar and hasattr(self.parent_sidebar, "search_input"):
            search_input = self.parent_sidebar.search_input
            if search_input is not None:
                search_input.installEventFilter(self)

    def eventFilter(self, obj, event) -> bool:
        if (
            self.isVisible()
            and isinstance(obj, QLineEdit)
            and not obj.hasSelectedText()
            and event.type() == QEvent.Type.KeyPress
            and isinstance(event, QKeyEvent)
            and event.key() == Qt.Key.Key_C
            and (event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        ):
            self.copy_selected_clips()
            return True
        return super().eventFilter(obj, event)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.copy_shortcut.setEnabled(True)

    def hideEvent(self, event) -> None:
        self.copy_shortcut.setEnabled(False)
        super().hideEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if (
            event.key() == Qt.Key.Key_C
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
            and self.isVisible()
        ):
            self.copy_selected_clips()
            event.accept()
            return
        super().keyPressEvent(event)

    def _on_ctrl_c(self) -> None:
        if self.isVisible():
            self.copy_selected_clips()

    def _on_join_format_changed(self, _index: int) -> None:
        if self._restoring_state or not hasattr(self.db, "set_workspace_setting"):
            return
        mode = self.cmb_join_format.currentData()
        if mode is not None:
            self.db.set_workspace_setting("queue_join_format", mode)

    def restore_workspace_settings(self) -> None:
        """Restores per-profile Clip Queue preferences from workspace_state."""
        if not hasattr(self.db, "get_workspace_setting"):
            return
        saved_mode = self.db.get_workspace_setting("queue_join_format", None)
        idx = self.cmb_join_format.findData(saved_mode) if saved_mode is not None else 0
        if idx < 0:
            idx = 0
        self._restoring_state = True
        try:
            self.cmb_join_format.setCurrentIndex(idx)
        finally:
            self._restoring_state = False

    def refresh(self, search_query: str = "") -> None:
        self.current_query = search_query or ""
        current_profile = getattr(self.db, "profile", "work")
        if current_profile != self._active_profile:
            self._active_profile = current_profile
            self.restore_workspace_settings()
        clips = self.db.get_clips(self.current_query)

        self._updating_ui = True
        try:
            self.list_widget.clear()
            for clip in clips:
                self._add_clip_item(clip)
        finally:
            self._updating_ui = False

        self._update_summary_controls()

    def _add_clip_item(self, clip: Dict) -> None:
        item = QListWidgetItem()
        # Omit ItemIsDropEnabled on items so drops insert between rows cleanly.
        item.setFlags(
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsDragEnabled
        )
        item.setData(Qt.ItemDataRole.UserRole, dict(clip))
        row_widget = self._create_row_widget(clip)
        item.setToolTip(row_widget.toolTip())
        min_h = 46 if row_widget.source_type == "image" else 42
        item.setSizeHint(QSize(0, max(row_widget.sizeHint().height(), min_h)))

        self.list_widget.addItem(item)
        self.list_widget.setItemWidget(item, row_widget)

    def _create_row_widget(self, clip: Dict) -> ClipRowWidget:
        return ClipRowWidget(
            clip_data=clip,
            on_checked=self._on_clip_checked,
            on_send_notes=self._on_send_to_notes,
            on_delete=self._on_delete_clip,
            on_send_menu=self._on_send_to_notes_menu,
            on_quick_copy=self.copy_single_clip,
            on_edit_saved=self._on_edit_clip_saved,
            on_edit_image=self.edit_image_clip,
            parent=self.list_widget,
        )

    def _update_summary_controls(self) -> None:
        total = self.list_widget.count()
        checked_in_view = 0

        for idx in range(total):
            item = self.list_widget.item(idx)
            data = item.data(Qt.ItemDataRole.UserRole) or {}
            if data.get("is_checked"):
                checked_in_view += 1

        all_checked = total > 0 and checked_in_view == total

        self.chk_select_all.blockSignals(True)
        self.chk_select_all.setEnabled(total > 0)
        self.chk_select_all.setChecked(all_checked)
        self.chk_select_all.setText("Deselect All" if all_checked else "Select All")
        self.chk_select_all.blockSignals(False)

        noun = "clip" if total == 1 else "clips"
        self.lbl_count.setText(f"{total} {noun}")
        self.lbl_count.setToolTip(f"{checked_in_view} checked out of {total} displayed {noun}")

        self.btn_clear_checked.setEnabled(checked_in_view > 0)
        self.btn_clear_all.setEnabled(total > 0)

        self.btn_copy_selected.setText(f"Copy Selected ({checked_in_view})")
        self.btn_copy_selected.setEnabled(checked_in_view > 0)

    def _on_clip_checked(self, clip_id: int, checked: bool) -> None:
        if self._updating_ui:
            return
        self.db.set_clip_checked(clip_id, checked)

        for idx in range(self.list_widget.count()):
            item = self.list_widget.item(idx)
            data = item.data(Qt.ItemDataRole.UserRole) or {}
            if int(data.get("id", -1)) == clip_id:
                data["is_checked"] = 1 if checked else 0
                item.setData(Qt.ItemDataRole.UserRole, data)
                break

        self._update_summary_controls()

    def _on_select_all_clicked(self, checked: bool) -> None:
        target_state = bool(checked)
        self._updating_ui = True
        try:
            for idx in range(self.list_widget.count()):
                item = self.list_widget.item(idx)
                data = item.data(Qt.ItemDataRole.UserRole) or {}
                clip_id = int(data.get("id", -1))
                if clip_id >= 0:
                    self.db.set_clip_checked(clip_id, target_state)
                    data["is_checked"] = 1 if target_state else 0
                    item.setData(Qt.ItemDataRole.UserRole, data)

                row_widget = self.list_widget.itemWidget(item)
                if isinstance(row_widget, ClipRowWidget):
                    row_widget.is_checked = target_state
                    row_widget.checkbox.blockSignals(True)
                    row_widget.checkbox.setChecked(target_state)
                    row_widget.checkbox.blockSignals(False)
        finally:
            self._updating_ui = False

        self._update_summary_controls()

    def _on_clear_checked(self) -> None:
        self.db.clear_clips(only_checked=True)
        self._sync_parent_refresh()

    def _on_clear_all(self) -> None:
        self.db.clear_clips(only_checked=False)
        self._sync_parent_refresh()

    def _on_delete_clip(self, clip_id: int) -> None:
        self.db.delete_clip(clip_id)
        self._sync_parent_refresh()

    def _get_panel_hub(self):
        if self.parent_sidebar and hasattr(self.parent_sidebar, "panel_hub"):
            return self.parent_sidebar.panel_hub
        return None

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

    @staticmethod
    def _create_styled_menu(parent: Optional[QWidget] = None) -> QMenu:
        menu = QMenu(parent)
        menu.setStyleSheet(
            """
            QMenu {
                background-color: #2A2D3E;
                border: 1px solid #363A4F;
                color: #CDD6F4;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 14px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #89B4FA;
                color: #1E1E2E;
            }
            QMenu::separator {
                height: 1px;
                background: #363A4F;
                margin: 4px 6px;
            }
            """
        )
        return menu

    @staticmethod
    def _exec_menu(menu: QMenu, global_pos):
        return menu.exec(global_pos)

    @staticmethod
    def _exec_dialog(dlg: QDialog) -> int:
        return dlg.exec()

    def promote_clip_to_note(
        self,
        content: str,
        target_tab_id: Optional[int] = None,
        btn: Optional[QPushButton] = None,
    ) -> None:
        hub = self._get_panel_hub()
        if hub is not None and hasattr(hub, "save_timer") and hub.save_timer.isActive():
            hub.save_timer.stop()
            if hasattr(hub, "_save_active_note"):
                hub._save_active_note()

        tabs = self.db.get_note_tabs()
        if not tabs:
            return

        selected_tab = None
        if target_tab_id is not None:
            for tab in tabs:
                if int(tab["id"]) == int(target_tab_id):
                    selected_tab = tab
                    break
        elif hub is not None and getattr(hub, "active_tab_id", None) is not None:
            active_id = int(hub.active_tab_id)
            for tab in tabs:
                if int(tab["id"]) == active_id:
                    selected_tab = tab
                    break

        if selected_tab is None:
            selected_tab = tabs[0]

        existing = selected_tab.get("content") or ""
        existing_rich = (selected_tab.get("rich_content") or "").strip()
        is_image = (content or "").strip().startswith("data:image/")

        if is_image:
            img = _decode_image_data_uri(content)
            if img.isNull():
                return
            w = min(280, img.width())
            h = max(1, int(round(img.height() * (w / max(1, img.width())))))
            if (
                hub is not None
                and int(selected_tab["id"]) == getattr(hub, "active_tab_id", None)
                and hasattr(hub, "_append_image_to_active_editor")
            ):
                hub._append_image_to_active_editor(img, content, w, h)
                if hasattr(hub, "save_timer"):
                    hub.save_timer.stop()
                if hasattr(hub, "_save_active_note"):
                    hub._save_active_note()
                self._flash_send_button(btn)
                return

            from ui.panel_hub import _register_data_uri_images

            doc = QTextDocument()
            if existing_rich:
                _register_data_uri_images(doc, existing_rich)
                doc.setHtml(existing_rich)
            else:
                doc.setPlainText(existing)
            doc.addResource(
                QTextDocument.ResourceType.ImageResource, QUrl(content), img
            )
            cur = QTextCursor(doc)
            cur.movePosition(QTextCursor.MoveOperation.End)
            if (doc.toPlainText().strip() or "<img " in doc.toHtml().lower()) and not doc.toPlainText().endswith("\n"):
                cur.insertText("\n")
            fmt = QTextImageFormat()
            fmt.setName(content)
            fmt.setWidth(w)
            fmt.setHeight(h)
            cur.insertImage(fmt)
            updated = doc.toPlainText()
            updated_rich = doc.toHtml()
        else:
            if existing.strip():
                separator = "" if existing.endswith("\n") else "\n"
                updated = f"{existing}{separator}{content}"
            else:
                updated = content

            updated_rich = ""
            if existing_rich:
                escaped_block = f"<p>{html.escape(content).replace(chr(10), '<br/>')}</p>"
                body_end = existing_rich.lower().rfind("</body>")
                if body_end != -1:
                    updated_rich = (
                        existing_rich[:body_end] + escaped_block + existing_rich[body_end:]
                    )
                else:
                    updated_rich = existing_rich + escaped_block

        self.db.update_note_content(
            int(selected_tab["id"]), updated, rich_content=updated_rich
        )

        if hub is not None and hasattr(hub, "refresh"):
            hub.refresh(self.current_query)

        self._flash_send_button(btn)

    def copy_single_clip(
        self, clip_data: Dict, row_widget: Optional[ClipRowWidget] = None
    ) -> None:
        """Copies a single text/URL/path or image clip directly to the clipboard."""
        content = str(clip_data.get("content", ""))
        src = str(clip_data.get("source_type", "text"))
        if src == "image" or content.strip().startswith("data:image/"):
            img = _decode_image_data_uri(content)
            if img.isNull():
                return
            QApplication.clipboard().setImage(img)
        else:
            QApplication.clipboard().setText(content)

        if row_widget is not None and hasattr(row_widget, "btn_copy"):
            self._flash_row_button(row_widget.btn_copy, "📋")

    def _on_edit_clip_saved(self, clip_id: int, new_content: str) -> None:
        if hasattr(self.db, "update_clip"):
            self.db.update_clip(clip_id, new_content)
        self._sync_parent_refresh()

    def edit_image_clip(self, clip_id: int, current_data_uri: str) -> bool:
        """Opens ImageEditDialog for an image clip and persists or deletes it."""
        img = _decode_image_data_uri(current_data_uri)
        if img.isNull():
            return False
        from ui.panel_hub import ImageEditDialog

        edited_ok = False

        def _open_editor() -> None:
            nonlocal edited_ok
            dlg = ImageEditDialog(img, parent=self)
            res = self._exec_dialog(dlg)
            if dlg.delete_requested:
                self._on_delete_clip(clip_id)
                edited_ok = True
                return
            if res == QDialog.DialogCode.Accepted:
                new_img = dlg.get_result_image()
                new_uri = _encode_image_data_uri(new_img)
                if new_uri and hasattr(self.db, "update_clip"):
                    self.db.update_clip(clip_id, new_uri, source_type="image")
                    self._sync_parent_refresh()
                    edited_ok = True

        self._run_with_pin_guard(_open_editor)
        return edited_ok

    def promote_clip_to_shortcut(
        self,
        content: str,
        source_type: str = "url",
        title: Optional[str] = None,
        use_dialog: bool = False,
        btn: Optional[QPushButton] = None,
    ) -> int:
        from ui.panel_hub import ShortcutDialog, _derive_title, _infer_category

        target = content.strip()
        if not target:
            return -1

        derived_title = (title or "").strip() or _derive_title(target)
        category = "url" if source_type == "url" else _infer_category(target)
        shortcut_id = -1

        if use_dialog:
            def _open_dialog() -> None:
                nonlocal shortcut_id
                dlg = ShortcutDialog(
                    self,
                    title=derived_title,
                    target=target,
                    category=category,
                )
                if self._exec_dialog(dlg) == QDialog.DialogCode.Accepted:
                    dlg_title, dlg_target, dlg_category = dlg.get_data()
                    if dlg_target:
                        shortcut_id = self.db.add_shortcut(
                            dlg_title, dlg_target, category=dlg_category
                        )

            self._run_with_pin_guard(_open_dialog)
        else:
            shortcut_id = self.db.add_shortcut(derived_title, target, category=category)

        if shortcut_id != -1:
            hub = self._get_panel_hub()
            if hub is not None and hasattr(hub, "refresh"):
                hub.refresh(self.current_query)
            self._flash_send_button(btn)

        return shortcut_id

    def _flash_send_button(self, btn: Optional[QPushButton]) -> None:
        self._flash_row_button(btn, "→")

    def _flash_row_button(
        self, btn: Optional[QPushButton], restore_text: str
    ) -> None:
        if btn is not None and _qt_is_valid(btn):
            btn.setText("✓")
            QTimer.singleShot(
                800, lambda b=btn, txt=restore_text: self._restore_row_button(b, txt)
            )

    @staticmethod
    def _restore_row_button(btn: QPushButton, text: str) -> None:
        if _qt_is_valid(btn):
            btn.setText(text)

    @staticmethod
    def _populate_note_tab_menu(menu: QMenu, tabs: List[Dict], prefix: str = "") -> Dict:
        """Populate a QMenu with note tab actions labeled with Ctrl+1..9 shortcuts."""
        tab_actions = {}
        for idx, tab in enumerate(tabs):
            tab_name = str(tab.get("tab_name", f"Tab {tab['id']}"))
            shortcut_hint = f" (Ctrl+{idx + 1})" if idx < 9 else ""
            act = menu.addAction(f"{prefix}{tab_name}{shortcut_hint}")
            tab_actions[act] = int(tab["id"])
        return tab_actions

    def _on_send_to_notes(self, clip_data: Dict, btn: QPushButton) -> None:
        content = str(clip_data.get("content", ""))
        source_type = str(clip_data.get("source_type", "text"))

        if source_type in ("url", "path"):
            def _open_menu() -> None:
                menu = self._create_styled_menu(btn)
                act_shortcut = menu.addAction("Add as Shortcut")
                act_shortcut_edit = menu.addAction("Add as Shortcut (Edit...)")
                menu.addSeparator()
                act_active_note = menu.addAction("Append to Active Note")

                tabs = self.db.get_note_tabs()
                tab_actions = {}
                if tabs:
                    sub = menu.addMenu("Send to Note Tab")
                    sub.setStyleSheet(menu.styleSheet())
                    tab_actions = self._populate_note_tab_menu(sub, tabs)

                chosen = self._exec_menu(menu, btn.mapToGlobal(btn.rect().bottomLeft()))
                if chosen is None:
                    return
                if chosen == act_shortcut:
                    self.promote_clip_to_shortcut(
                        content, source_type=source_type, use_dialog=False, btn=btn
                    )
                elif chosen == act_shortcut_edit:
                    self.promote_clip_to_shortcut(
                        content, source_type=source_type, use_dialog=True, btn=btn
                    )
                elif chosen == act_active_note:
                    self.promote_clip_to_note(content, target_tab_id=None, btn=btn)
                elif chosen in tab_actions:
                    self.promote_clip_to_note(
                        content, target_tab_id=tab_actions[chosen], btn=btn
                    )

            self._run_with_pin_guard(_open_menu)
            return

        self.promote_clip_to_note(content, target_tab_id=None, btn=btn)

    def _on_send_to_notes_menu(self, clip_data: Dict, btn: QPushButton, pos) -> None:
        content = str(clip_data.get("content", ""))
        source_type = str(clip_data.get("source_type", "text"))

        def _open_menu() -> None:
            menu = self._create_styled_menu(btn)
            tabs = self.db.get_note_tabs()
            tab_actions = self._populate_note_tab_menu(menu, tabs, prefix="Append to ")

            act_shortcut = None
            act_shortcut_edit = None
            if source_type in ("url", "path"):
                if tabs:
                    menu.addSeparator()
                act_shortcut = menu.addAction("Add as Shortcut")
                act_shortcut_edit = menu.addAction("Add as Shortcut (Edit...)")

            chosen = self._exec_menu(menu, btn.mapToGlobal(pos))
            if chosen is None:
                return
            if chosen in tab_actions:
                self.promote_clip_to_note(
                    content, target_tab_id=tab_actions[chosen], btn=btn
                )
            elif act_shortcut is not None and chosen == act_shortcut:
                self.promote_clip_to_shortcut(
                    content, source_type=source_type, use_dialog=False, btn=btn
                )
            elif act_shortcut_edit is not None and chosen == act_shortcut_edit:
                self.promote_clip_to_shortcut(
                    content, source_type=source_type, use_dialog=True, btn=btn
                )

        self._run_with_pin_guard(_open_menu)

    def _on_rows_reordered(self) -> None:
        ordered_items: List[tuple[int, Dict]] = []
        existing_orders: List[int] = []

        for idx in range(self.list_widget.count()):
            item = self.list_widget.item(idx)
            data = dict(item.data(Qt.ItemDataRole.UserRole) or {})
            if "id" not in data:
                continue
            ordered_items.append((idx, data))
            existing_orders.append(int(data.get("sort_order", idx + 1)))

        if ordered_items:
            if not self.current_query:
                new_orders = list(range(1, len(ordered_items) + 1))
            else:
                # Preserve existing sort slots when reordering within a filtered subset.
                new_orders = sorted(existing_orders)

            updates = []
            for (idx, data), new_order in zip(ordered_items, new_orders):
                data["sort_order"] = new_order
                item = self.list_widget.item(idx)
                item.setData(Qt.ItemDataRole.UserRole, data)
                updates.append((new_order, int(data["id"])))

                # Qt's InternalMove removes the itemWidget on moved rows; rebind if missing.
                if self.list_widget.itemWidget(item) is None:
                    row_widget = self._create_row_widget(data)
                    min_h = 46 if row_widget.source_type == "image" else 42
                    item.setSizeHint(QSize(0, max(row_widget.sizeHint().height(), min_h)))
                    self.list_widget.setItemWidget(item, row_widget)

            self._persist_clip_order(updates)

        self._update_summary_controls()

    def _persist_clip_order(self, updates: List[tuple[int, int]]) -> None:
        if not updates:
            return
        with self.db._connect() as conn:
            conn.executemany(
                "UPDATE clip_queue SET sort_order = ? WHERE id = ?",
                updates,
            )

    def _sync_parent_refresh(self) -> None:
        if self.parent_sidebar and hasattr(self.parent_sidebar, "refresh_views"):
            self.parent_sidebar.refresh_views()
        else:
            self.refresh(self.current_query)

    def copy_selected_clips(self) -> None:
        checked_items: List[tuple[str, str]] = []
        for idx in range(self.list_widget.count()):
            item = self.list_widget.item(idx)
            data = item.data(Qt.ItemDataRole.UserRole) or {}
            if data.get("is_checked"):
                raw_content = str(data.get("content", ""))
                src = str(data.get("source_type", "text"))
                if raw_content.strip().startswith("data:image/"):
                    src = "image"
                checked_items.append((src, raw_content))

        if not checked_items:
            return

        if all(src == "image" for src, _ in checked_items):
            img = _decode_image_data_uri(checked_items[0][1])
            if not img.isNull():
                QApplication.clipboard().setImage(img)
        else:
            selected_contents = [
                "[Image]" if src == "image" else content
                for src, content in checked_items
            ]
            mode = self.cmb_join_format.currentData()
            if mode == "bullets":
                combined = "\n".join(f"- {text}" for text in selected_contents)
            elif mode == "\n\n":
                combined = "\n\n".join(selected_contents)
            else:
                combined = "\n".join(selected_contents)
            QApplication.clipboard().setText(combined)

        if self.parent_sidebar and hasattr(self.parent_sidebar, "hide_sidebar"):
            self.parent_sidebar.hide_sidebar(restore_focus=True)
