import base64
from datetime import datetime
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Callable, Dict, List, Optional, Tuple
import urllib.parse

from PySide6.QtCore import (
    QBuffer,
    QEvent,
    QFileInfo,
    QIODevice,
    QMimeData,
    QPoint,
    QPointF,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    QUrl,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QDesktopServices,
    QDrag,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QIcon,
    QImage,
    QKeyEvent,
    QKeySequence,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
    QShortcut,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextImageFormat,
    QTransform,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QColorDialog,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QSplitter,
    QTextEdit,
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


def _exec_color_dialog(dlg: QColorDialog) -> int:
    dlg.raise_()
    dlg.activateWindow()
    QTimer.singleShot(0, dlg.raise_)
    return dlg.exec()


def _pick_color_positioned(
    parent: QWidget,
    initial: QColor,
    title: str,
    sidebar: Optional[QWidget] = None,
    anchor_widget: Optional[QWidget] = None,
) -> Optional[QColor]:
    """Open an always-on-top non-native QColorDialog placed outside the docked sidebar."""
    host = sidebar if sidebar is not None else (parent.window() if parent is not None else None)
    dlg = QColorDialog(initial if initial.isValid() else QColor("#CDD6F4"), parent)
    dlg.setWindowTitle(title)
    dlg.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog, True)
    dlg.setWindowFlags(dlg.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
    dlg.setStyleSheet(
        """
        QColorDialog {
            background-color: qlineargradient(
                x1:0, y1:0, x2:0.4, y2:1,
                stop:0 #1E1E2E, stop:0.6 #282039, stop:1 #34233E
            );
            color: #CDD6F4;
            font-family: 'Segoe UI', sans-serif;
        }
        QLabel, QCheckBox, QRadioButton {
            color: #CDD6F4;
            font-size: 11px;
        }
        QLineEdit, QSpinBox {
            background-color: qlineargradient(
                x1:0, y1:0, x2:1, y2:1,
                stop:0 #2A2D3E, stop:1 #342945
            );
            border: 1px solid #363A4F;
            border-radius: 4px;
            color: #CDD6F4;
            padding: 2px 4px;
        }
        QPushButton {
            background-color: qlineargradient(
                x1:0, y1:0, x2:1, y2:1,
                stop:0 #2A2D3E, stop:1 #342945
            );
            border: 1px solid #363A4F;
            border-radius: 5px;
            color: #CDD6F4;
            padding: 4px 10px;
            font-size: 11px;
            font-weight: 600;
        }
        QPushButton:hover {
            background-color: #363A4F;
            border-color: #FAB387;
        }
        """
    )
    dlg.adjustSize()
    dlg_w = max(dlg.width(), dlg.sizeHint().width())
    dlg_h = max(dlg.height(), dlg.sizeHint().height())

    screen = None
    if host is not None and _qt_is_valid(host):
        screen = host.screen() or QGuiApplication.screenAt(host.frameGeometry().center())
    if screen is None:
        screen = QGuiApplication.primaryScreen()
    avail = screen.availableGeometry() if screen is not None else QRect(0, 0, 1920, 1080)

    dock_edge = getattr(host, "dock_edge", "right") if host is not None else "right"
    if host is not None and _qt_is_valid(host):
        host_geom = host.frameGeometry()
        if dock_edge == "left":
            target_x = host_geom.right() + 12
        elif dock_edge in ("top", "bottom"):
            if anchor_widget is not None and _qt_is_valid(anchor_widget) and anchor_widget.isVisible():
                target_x = anchor_widget.mapToGlobal(QPoint(0, 0)).x() - dlg_w // 2
            else:
                target_x = host_geom.center().x() - dlg_w // 2
        else:
            target_x = host_geom.left() - dlg_w - 12
    else:
        target_x = avail.right() - dlg_w - 400
    target_x = max(avail.left() + 8, min(target_x, avail.right() - dlg_w - 8))

    if host is not None and _qt_is_valid(host) and dock_edge in ("top", "bottom"):
        host_geom = host.frameGeometry()
        if dock_edge == "top":
            target_y = host_geom.bottom() + 12
        else:
            target_y = host_geom.top() - dlg_h - 12
    elif anchor_widget is not None and _qt_is_valid(anchor_widget) and anchor_widget.isVisible():
        target_y = anchor_widget.mapToGlobal(QPoint(0, 0)).y() - 40
    elif host is not None and _qt_is_valid(host):
        target_y = host.frameGeometry().center().y() - dlg_h // 2
    else:
        target_y = avail.center().y() - dlg_h // 2
    target_y = max(avail.top() + 8, min(target_y, avail.bottom() - dlg_h - 8))

    dlg.move(target_x, target_y)
    dlg.setAttribute(Qt.WidgetAttribute.WA_Moved, True)

    if _exec_color_dialog(dlg) == QDialog.DialogCode.Accepted:
        selected = dlg.selectedColor()
        if not selected.isValid():
            selected = dlg.currentColor()
        return selected if selected.isValid() else None
    return None


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
    try:
        if p.is_dir():
            return p.name or cleaned
    except OSError:
        pass
    return p.stem or p.name or cleaned


def expand_note_template_variables(
    text: str,
    clipboard_text: Optional[str] = None,
    now: Optional[datetime] = None,
) -> str:
    """Expands {{date}}, {{time}}, {{datetime}}, and {{clipboard}} placeholders."""
    if not text:
        return ""
    dt = now or datetime.now()
    if clipboard_text is not None:
        clip_val = clipboard_text
    else:
        app = QApplication.instance()
        clip_val = app.clipboard().text() if app is not None else ""
    result = text.replace("{{date}}", dt.strftime("%Y-%m-%d"))
    result = result.replace("{{time}}", dt.strftime("%H:%M"))
    result = result.replace("{{datetime}}", dt.strftime("%Y-%m-%d %H:%M"))
    result = result.replace("{{clipboard}}", clip_val)
    return result


def _normalize_shortcut_target(target: str) -> str:
    cleaned = str(target or "").strip().strip('"')
    if not cleaned:
        return ""
    if cleaned.lower().startswith(("http://", "https://")):
        parsed = urllib.parse.urlsplit(cleaned)
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        path = parsed.path or ""
        if path == "/":
            path = ""
        return urllib.parse.urlunsplit(
            (scheme, netloc, path, parsed.query, parsed.fragment)
        )
    return os.path.normcase(os.path.normpath(cleaned))


def unwrap_windows_shortcut(path_str: str) -> Tuple[str, str]:
    """Resolves .url and .lnk Windows shortcuts to (derived_title, resolved_target)."""
    raw = str(path_str or "").strip().strip('"')
    if not raw:
        return "", ""
    p = Path(raw)
    suffix = p.suffix.lower()

    if suffix == ".url":
        title = p.stem or p.name or raw
        try:
            if p.is_file():
                raw_bytes = p.read_bytes()
                if raw_bytes.startswith((b"\xff\xfe", b"\xfe\xff")):
                    text = raw_bytes.decode("utf-16", errors="ignore")
                else:
                    text = raw_bytes.decode("utf-8", errors="ignore")
                match = re.search(
                    r"^\s*URL\s*=\s*(.+?)\s*$",
                    text,
                    flags=re.IGNORECASE | re.MULTILINE,
                )
                if match and match.group(1).strip():
                    return title, match.group(1).strip()
        except OSError:
            pass
        return title, raw

    if suffix == ".lnk":
        title = p.stem or p.name or raw
        try:
            sym = QFileInfo(raw).symLinkTarget()
            if sym:
                return title, str(Path(sym))
        except Exception:
            pass
        try:
            if p.is_file():
                data = p.read_bytes()
                candidates: List[str] = []
                utf16_text = data.decode("utf-16-le", errors="ignore")
                for m in re.findall(r"https?://[^\x00\r\n\"\s]{4,}", utf16_text):
                    candidates.append(m.strip())
                for m in re.findall(rb"https?://[^\x00\r\n\"\s]{4,}", data):
                    candidates.append(m.decode("ascii", errors="ignore").strip())
                for m in re.findall(
                    r"[A-Za-z]:\\[^\x00\r\n\"<>|]{2,}", utf16_text
                ):
                    candidates.append(m.strip())
                for m in re.findall(
                    rb"[A-Za-z]:\\[^\x00\r\n\"<>|]{2,}", data
                ):
                    candidates.append(m.decode("cp1252", errors="ignore").strip())

                valid_urls = [
                    c for c in candidates if c.lower().startswith(("http://", "https://"))
                ]
                if valid_urls:
                    return title, valid_urls[0]

                file_paths = []
                dir_paths = []
                for cand in candidates:
                    try:
                        cp = Path(cand)
                        if cp.is_file():
                            file_paths.append(str(cp))
                        elif cp.is_dir():
                            dir_paths.append(str(cp))
                    except OSError:
                        pass
                if file_paths:
                    return title, file_paths[0]
                if dir_paths:
                    return title, dir_paths[0]
                # Prefer a path with a file extension over bare dir strings if none exist on disk.
                for cand in candidates:
                    if Path(cand).suffix:
                        return title, str(Path(cand))
                if candidates:
                    return title, str(Path(candidates[0]))
        except OSError:
            pass
        return title, raw

    try:
        if p.is_dir():
            return (p.name or raw), raw
    except OSError:
        pass
    return (p.stem or p.name or raw), raw


def extract_shortcut_candidates_from_mime(
    mime: Optional[QMimeData],
) -> List[Tuple[str, str, str]]:
    """Extracts unique (title, target, category) shortcut tuples from external MIME data."""
    if mime is None:
        return []
    if mime.hasFormat(_SHORTCUT_MIME_TYPE) and not mime.hasUrls() and not mime.hasText():
        return []

    raw_items: List[Tuple[str, str, str]] = []

    if mime.hasUrls():
        for url in mime.urls():
            if url.isLocalFile():
                local_path = str(Path(url.toLocalFile()))
                title, resolved = unwrap_windows_shortcut(local_path)
                is_web = resolved.lower().startswith(("http://", "https://"))
                if not is_web:
                    resolved = str(Path(resolved))
                prefer_folder = False
                if not is_web:
                    try:
                        prefer_folder = Path(resolved).is_dir()
                    except OSError:
                        prefer_folder = False
                cat = _infer_category(resolved, prefer_folder=prefer_folder)
                raw_items.append((title or _derive_title(resolved), resolved, cat))
            else:
                raw_url = url.toString().strip()
                if raw_url.lower().startswith(("http://", "https://")):
                    raw_items.append((_derive_title(raw_url), raw_url, "url"))

    if not raw_items and mime.hasText():
        for raw_line in mime.text().splitlines():
            cleaned = raw_line.strip().strip('"')
            if not cleaned:
                continue
            if cleaned.lower().startswith(("http://", "https://")):
                raw_items.append((_derive_title(cleaned), cleaned, "url"))
                continue
            if len(cleaned) < 4096:
                try:
                    p = Path(cleaned)
                    is_candidate = (
                        p.is_absolute()
                        or p.exists()
                        or cleaned.lower().endswith((".lnk", ".url"))
                    )
                except OSError:
                    is_candidate = False
                if is_candidate:
                    title, resolved = unwrap_windows_shortcut(cleaned)
                    is_web = resolved.lower().startswith(("http://", "https://"))
                    if not is_web:
                        resolved = str(Path(resolved))
                    prefer_folder = False
                    if not is_web:
                        try:
                            prefer_folder = Path(resolved).is_dir()
                        except OSError:
                            prefer_folder = False
                    cat = _infer_category(resolved, prefer_folder=prefer_folder)
                    raw_items.append((title or _derive_title(resolved), resolved, cat))

    deduped: List[Tuple[str, str, str]] = []
    seen_norm = set()
    for title, target, cat in raw_items:
        norm = _normalize_shortcut_target(target)
        if not norm or norm in seen_norm:
            continue
        seen_norm.add(norm)
        deduped.append((title, target, cat))
    return deduped


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
                background-color: qlineargradient(
                    x1:0, y1:0, x2:0.4, y2:1,
                    stop:0 #1E1E2E, stop:0.6 #282039, stop:1 #34233E
                );
                color: #CDD6F4;
                font-family: 'Segoe UI', sans-serif;
            }
            QLabel {
                color: #CDD6F4;
                font-size: 12px;
            }
            QLineEdit {
                background-color: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #2A2D3E, stop:1 #342945
                );
                border: 1px solid #363A4F;
                border-radius: 5px;
                padding: 6px 8px;
                color: #CDD6F4;
                font-size: 12px;
            }
            QLineEdit:focus {
                border-color: #FAB387;
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


_SHORTCUT_MIME_TYPE = "application/x-f9sidebar-shortcut-id"
_NOTE_IMAGE_MIME_TYPE = "application/x-f9sidebar-note-image"
_CHECK_UNCHECKED = "☐ "
_CHECK_CHECKED = "☑ "
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}
_DATA_URI_IMAGE_RE = re.compile(r"data:image/[a-zA-Z0-9+.-]+;base64,([A-Za-z0-9+/=\s]+)")


def _register_data_uri_images(doc: QTextDocument, html_text: str) -> None:
    """Decode embedded data-URI images and register them on a QTextDocument."""
    for match in _DATA_URI_IMAGE_RE.finditer(html_text or ""):
        uri = match.group(0)
        b64_payload = re.sub(r"\s+", "", match.group(1))
        try:
            raw = base64.b64decode(b64_payload, validate=False)
        except Exception:
            continue
        img = QImage.fromData(raw)
        if not img.isNull():
            doc.addResource(
                QTextDocument.ResourceType.ImageResource, QUrl(uri), img
            )


class DraggableShortcutTile(QToolButton):
    """Shortcut icon tile supporting click launch, drag reordering, and external drops."""

    def __init__(
        self,
        shortcut_id: int,
        on_drop_reorder: Callable[[int, int], None],
        on_external_drop: Optional[Callable[[QMimeData, Qt.KeyboardModifiers], None]] = None,
        on_drag_hover_state: Optional[Callable[[bool], None]] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.shortcut_id = int(shortcut_id)
        self._on_drop_reorder = on_drop_reorder
        self._on_external_drop = on_external_drop
        self._on_drag_hover_state = on_drag_hover_state
        self._drag_start_pos: Optional[QPoint] = None
        self.setAcceptDrops(True)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if (
            event.buttons() & Qt.MouseButton.LeftButton
            and self._drag_start_pos is not None
            and (event.position().toPoint() - self._drag_start_pos).manhattanLength()
            >= QApplication.startDragDistance()
        ):
            self.setDown(False)
            self._drag_start_pos = None
            drag = QDrag(self)
            mime = QMimeData()
            mime.setData(_SHORTCUT_MIME_TYPE, str(self.shortcut_id).encode("utf-8"))
            drag.setMimeData(mime)
            pixmap = self.icon().pixmap(22, 22)
            if not pixmap.isNull():
                drag.setPixmap(pixmap)
            drag.exec(Qt.DropAction.MoveAction)
            return
        super().mouseMoveEvent(event)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasFormat(_SHORTCUT_MIME_TYPE):
            event.acceptProposedAction()
            return
        if extract_shortcut_candidates_from_mime(event.mimeData()):
            if self._on_drag_hover_state is not None:
                self._on_drag_hover_state(True)
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasFormat(_SHORTCUT_MIME_TYPE):
            event.acceptProposedAction()
            return
        if extract_shortcut_candidates_from_mime(event.mimeData()):
            if self._on_drag_hover_state is not None:
                self._on_drag_hover_state(True)
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dragLeaveEvent(self, event) -> None:
        if self._on_drag_hover_state is not None:
            self._on_drag_hover_state(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:
        if self._on_drag_hover_state is not None:
            self._on_drag_hover_state(False)
        if event.mimeData().hasFormat(_SHORTCUT_MIME_TYPE):
            raw = bytes(event.mimeData().data(_SHORTCUT_MIME_TYPE)).decode("utf-8", errors="ignore")
            try:
                source_id = int(raw)
            except ValueError:
                return
            if source_id != self.shortcut_id:
                self._on_drop_reorder(source_id, self.shortcut_id)
            event.acceptProposedAction()
            return
        if (
            self._on_external_drop is not None
            and extract_shortcut_candidates_from_mime(event.mimeData())
        ):
            self._on_external_drop(event.mimeData(), event.modifiers())
            event.acceptProposedAction()
            return
        super().dropEvent(event)


class DroppableGridScrollArea(QScrollArea):
    """Scroll area accepting external files, folders, shortcuts, and URLs into the grid."""

    def __init__(
        self,
        on_external_drop: Callable[[QMimeData, Qt.KeyboardModifiers], None],
        on_drag_hover_state: Optional[Callable[[bool], None]] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._on_external_drop = on_external_drop
        self._on_drag_hover_state = on_drag_hover_state
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event) -> None:
        if extract_shortcut_candidates_from_mime(event.mimeData()):
            if self._on_drag_hover_state is not None:
                self._on_drag_hover_state(True)
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if extract_shortcut_candidates_from_mime(event.mimeData()):
            if self._on_drag_hover_state is not None:
                self._on_drag_hover_state(True)
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dragLeaveEvent(self, event) -> None:
        if self._on_drag_hover_state is not None:
            self._on_drag_hover_state(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:
        if self._on_drag_hover_state is not None:
            self._on_drag_hover_state(False)
        if extract_shortcut_candidates_from_mime(event.mimeData()):
            self._on_external_drop(event.mimeData(), event.modifiers())
            event.acceptProposedAction()
            return
        super().dropEvent(event)


class _AnnotationItem:
    """Editable, movable, and resizable vector annotation layered onto an image canvas."""

    def __init__(
        self,
        kind: str,
        color: Optional[QColor] = None,
        stroke_width: int = 3,
        points: Optional[List[QPointF]] = None,
        start: Optional[QPointF] = None,
        end: Optional[QPointF] = None,
        rect: Optional[QRectF] = None,
        text: str = "",
        font_px: int = 18,
        block_size: int = 10,
    ):
        self.kind = str(kind).lower().strip()
        self.color = QColor(color) if color is not None and color.isValid() else QColor("#F38BA8")
        self.stroke_width = max(1, int(stroke_width))
        self.points: List[QPointF] = [QPointF(p) for p in (points or [])]
        self.start = QPointF(start) if start is not None else QPointF()
        self.end = QPointF(end) if end is not None else QPointF()
        self.rect = QRectF(rect).normalized() if rect is not None else QRectF()
        self.text = str(text or "")
        self.font_px = max(8, int(font_px))
        self.block_size = max(2, int(block_size))

    def clone(self) -> "_AnnotationItem":
        return _AnnotationItem(
            kind=self.kind,
            color=self.color,
            stroke_width=self.stroke_width,
            points=self.points,
            start=self.start,
            end=self.end,
            rect=self.rect,
            text=self.text,
            font_px=self.font_px,
            block_size=self.block_size,
        )

    def bounding_rect(self) -> QRectF:
        if self.kind in ("pen", "highlighter"):
            if not self.points:
                return QRectF()
            min_x = min(p.x() for p in self.points)
            max_x = max(p.x() for p in self.points)
            min_y = min(p.y() for p in self.points)
            max_y = max(p.y() for p in self.points)
            if (max_x - min_x) < 10.0:
                cx = (min_x + max_x) / 2.0
                min_x, max_x = cx - 5.0, cx + 5.0
            if (max_y - min_y) < 10.0:
                cy = (min_y + max_y) / 2.0
                min_y, max_y = cy - 5.0, cy + 5.0
            return QRectF(min_x, min_y, max_x - min_x, max_y - min_y)
        if self.kind in ("line", "arrow"):
            r = QRectF(self.start, self.end).normalized()
            if r.width() < 10.0:
                r.setLeft(r.center().x() - 5.0)
                r.setWidth(10.0)
            if r.height() < 10.0:
                r.setTop(r.center().y() - 5.0)
                r.setHeight(10.0)
            return r
        return QRectF(self.rect).normalized()

    def translate(self, dx: float, dy: float) -> None:
        if self.kind in ("pen", "highlighter"):
            self.points = [QPointF(p.x() + dx, p.y() + dy) for p in self.points]
        elif self.kind in ("line", "arrow"):
            self.start = QPointF(self.start.x() + dx, self.start.y() + dy)
            self.end = QPointF(self.end.x() + dx, self.end.y() + dy)
        else:
            self.rect = QRectF(self.rect).translated(dx, dy)

    def resize_from_snapshot(
        self, orig: "_AnnotationItem", orig_rect: QRectF, new_rect: QRectF
    ) -> None:
        nr = QRectF(new_rect).normalized()
        if nr.width() < 6.0:
            nr.setWidth(6.0)
        if nr.height() < 6.0:
            nr.setHeight(6.0)
        ow = max(1.0, orig_rect.width())
        oh = max(1.0, orig_rect.height())

        if self.kind in ("pen", "highlighter"):
            self.points = [
                QPointF(
                    nr.left() + ((p.x() - orig_rect.left()) / ow) * nr.width(),
                    nr.top() + ((p.y() - orig_rect.top()) / oh) * nr.height(),
                )
                for p in orig.points
            ]
        elif self.kind in ("line", "arrow"):
            self.start = QPointF(
                nr.left() + ((orig.start.x() - orig_rect.left()) / ow) * nr.width(),
                nr.top() + ((orig.start.y() - orig_rect.top()) / oh) * nr.height(),
            )
            self.end = QPointF(
                nr.left() + ((orig.end.x() - orig_rect.left()) / ow) * nr.width(),
                nr.top() + ((orig.end.y() - orig_rect.top()) / oh) * nr.height(),
            )
        elif self.kind == "text":
            self.rect = nr
            scale = nr.height() / max(1.0, orig_rect.height())
            self.font_px = max(8, min(240, int(round(orig.font_px * scale))))
        else:
            self.rect = nr

    @staticmethod
    def _point_segment_distance(pt: QPointF, a: QPointF, b: QPointF) -> float:
        abx = b.x() - a.x()
        aby = b.y() - a.y()
        len_sq = abx * abx + aby * aby
        if len_sq <= 1e-6:
            return math.hypot(pt.x() - a.x(), pt.y() - a.y())
        t = max(0.0, min(1.0, ((pt.x() - a.x()) * abx + (pt.y() - a.y()) * aby) / len_sq))
        px = a.x() + t * abx
        py = a.y() + t * aby
        return math.hypot(pt.x() - px, pt.y() - py)

    def hit_test(self, img_pt: QPointF, tolerance: float = 8.0) -> bool:
        if self.kind in ("line", "arrow"):
            tol = max(float(tolerance), float(self.stroke_width) + 4.0)
            return self._point_segment_distance(img_pt, self.start, self.end) <= tol
        if self.kind in ("pen", "highlighter"):
            eff_w = (
                max(16.0, self.stroke_width * 4.0)
                if self.kind == "highlighter"
                else float(self.stroke_width)
            )
            tol = max(float(tolerance), eff_w / 2.0 + 4.0)
            if not self.bounding_rect().adjusted(-tol, -tol, tol, tol).contains(img_pt):
                return False
            if len(self.points) == 1:
                p0 = self.points[0]
                return math.hypot(img_pt.x() - p0.x(), img_pt.y() - p0.y()) <= tol
            if len(self.points) <= 400:
                return any(
                    self._point_segment_distance(img_pt, self.points[i], self.points[i + 1]) <= tol
                    for i in range(len(self.points) - 1)
                )
            return True
        return (
            self.bounding_rect()
            .adjusted(-tolerance, -tolerance, tolerance, tolerance)
            .contains(img_pt)
        )

    def paint_on(self, target_img: QImage) -> QImage:
        if target_img.isNull():
            return target_img
        if self.kind in ("pen", "highlighter"):
            pts = [p.toPoint() for p in self.points]
            return _ImagePreviewCanvas._render_path_on_image(
                target_img,
                pts,
                self.color,
                self.stroke_width,
                is_highlighter=(self.kind == "highlighter"),
            )
        if self.kind in ("line", "arrow"):
            return _ImagePreviewCanvas._render_shape_on_image(
                target_img,
                self.kind,
                self.start.toPoint(),
                self.end.toPoint(),
                self.color,
                self.stroke_width,
            )
        if self.kind in ("rect", "ellipse"):
            r = self.rect.normalized().toRect()
            return _ImagePreviewCanvas._render_shape_on_image(
                target_img,
                self.kind,
                r.topLeft(),
                r.bottomRight(),
                self.color,
                self.stroke_width,
            )
        if self.kind == "pixelate":
            pix = _ImagePreviewCanvas._render_pixelated_on_image(
                target_img, self.rect.normalized().toRect(), block_size=self.block_size
            )
            return pix if pix is not None else target_img
        if self.kind == "text":
            if not self.text.strip():
                return target_img
            out = target_img.convertToFormat(QImage.Format.Format_ARGB32).copy()
            draw_color = QColor(self.color)
            draw_color.setAlpha(255)
            painter = QPainter(out)
            try:
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
                font = QFont("Segoe UI", -1, QFont.Weight.Bold)
                font.setPixelSize(max(8, self.font_px))
                painter.setFont(font)
                r = QRectF(self.rect).normalized()
                flags = (
                    Qt.AlignmentFlag.AlignLeft
                    | Qt.AlignmentFlag.AlignVCenter
                    | Qt.TextFlag.TextDontClip
                )
                shadow = QColor("#11111B")
                shadow.setAlpha(200)
                painter.setPen(shadow)
                painter.drawText(r.translated(1.0, 1.0), flags, self.text)
                painter.setPen(draw_color)
                painter.drawText(r, flags, self.text)
            finally:
                painter.end()
            return out
        return target_img


class _ImagePreviewCanvas(QWidget):
    """Interactive full-screen image canvas with layer move/resize handles, Alt+Drag pan, highlighter, shapes, text, pixelate, eyedropper, and zoom."""

    VALID_TOOLS = (
        "select",
        "crop",
        "pen",
        "highlighter",
        "line",
        "arrow",
        "rect",
        "ellipse",
        "text",
        "pixelate",
        "eyedropper",
    )

    def __init__(
        self,
        image: QImage,
        on_image_modified: Optional[Callable[[], None]] = None,
        on_before_modify: Optional[Callable[[], None]] = None,
        on_text_requested: Optional[Callable[[QPoint], None]] = None,
        on_color_sampled: Optional[Callable[[QColor], None]] = None,
        on_zoom_changed: Optional[Callable[[float], None]] = None,
        on_selection_changed: Optional[Callable[[Optional[int]], None]] = None,
        on_edit_text_item: Optional[Callable[[int], None]] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._base_image = image.convertToFormat(QImage.Format.Format_ARGB32)
        self._items: List[_AnnotationItem] = []
        self._selected_index: Optional[int] = None
        self._image = self._base_image.copy()

        self._on_image_modified = on_image_modified
        self._on_before_modify = on_before_modify
        self._on_text_requested = on_text_requested
        self._on_color_sampled = on_color_sampled
        self._on_zoom_changed = on_zoom_changed
        self._on_selection_changed = on_selection_changed
        self._on_edit_text_item = on_edit_text_item

        self.tool_mode = "crop"
        self._draw_mode = False
        self.pen_color = QColor("#F38BA8")
        self.pen_width = 3
        self._zoom_factor = 1.0
        self._pan_offset = QPoint(0, 0)

        self._crop_rect: Optional[QRect] = None
        self._drag_origin_img: Optional[QPoint] = None
        self._drag_current_img: Optional[QPoint] = None
        self._stroke_base_image: Optional[QImage] = None
        self._stroke_points: List[QPoint] = []
        self._last_draw_pt: Optional[QPoint] = None
        self._panning = False
        self._pan_last_pos: Optional[QPoint] = None
        self._render_cache_key: Optional[Tuple[int, int, int, float]] = None
        self._render_cache_image: Optional[QImage] = None

        self._interaction: Optional[str] = None
        self._active_handle: Optional[str] = None
        self._orig_item_snapshot: Optional[_AnnotationItem] = None
        self._orig_item_bounds: Optional[QRectF] = None
        self._move_origin_img: Optional[QPointF] = None
        self._drag_undo_pushed = False

        self.setMinimumSize(320, 220)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def get_image(self) -> QImage:
        return self._image

    def get_state_snapshot(
        self,
    ) -> Tuple[QImage, List[_AnnotationItem], Optional[int]]:
        return (
            self._base_image.copy(),
            [it.clone() for it in self._items],
            self._selected_index,
        )

    def restore_state_snapshot(
        self,
        base_image: QImage,
        items: List[_AnnotationItem],
        selected_index: Optional[int],
    ) -> None:
        self._base_image = base_image.convertToFormat(QImage.Format.Format_ARGB32).copy()
        self._items = [it.clone() for it in items]
        self._selected_index = (
            selected_index
            if selected_index is not None and 0 <= selected_index < len(self._items)
            else None
        )
        self._crop_rect = None
        self._interaction = None
        self._recompose(notify=False)
        if self._on_selection_changed is not None:
            self._on_selection_changed(self._selected_index)

    def set_image(self, image: QImage, clear_crop: bool = True) -> None:
        self._base_image = image.convertToFormat(QImage.Format.Format_ARGB32).copy()
        self._items.clear()
        self._selected_index = None
        self._image = self._base_image.copy()
        self._render_cache_key = None
        self._render_cache_image = None
        self._stroke_base_image = None
        self._stroke_points = []
        self._last_draw_pt = None
        self._drag_origin_img = None
        self._drag_current_img = None
        self._interaction = None
        if clear_crop:
            self._crop_rect = None
        self.update()
        if self._on_selection_changed is not None:
            self._on_selection_changed(None)

    def _recompose(self, notify: bool = True) -> None:
        composed = self._base_image.copy()
        for item in self._items:
            composed = item.paint_on(composed)
        self._image = composed
        self._render_cache_key = None
        self._render_cache_image = None
        self.update()
        if notify and self._on_image_modified is not None:
            self._on_image_modified()

    def flatten_items(self) -> QImage:
        """Bakes active vector items into _base_image cleanly before bitmap transforms."""
        if self._items:
            self._recompose(notify=False)
            self._base_image = self._image.copy()
            self._items.clear()
        self._selected_index = None
        self.update()
        return self._base_image

    def add_item(self, item: _AnnotationItem, select: bool = True) -> int:
        self._items.append(item)
        idx = len(self._items) - 1
        if select:
            self._selected_index = idx
        self._recompose(notify=True)
        if select and self._on_selection_changed is not None:
            self._on_selection_changed(self._selected_index)
        return idx

    def get_selected_item(self) -> Optional[_AnnotationItem]:
        if self._selected_index is not None and 0 <= self._selected_index < len(self._items):
            return self._items[self._selected_index]
        return None

    def select_item(self, idx: Optional[int]) -> None:
        new_idx = (
            int(idx)
            if idx is not None and 0 <= int(idx) < len(self._items)
            else None
        )
        if new_idx != self._selected_index:
            self._selected_index = new_idx
            self.update()
            if self._on_selection_changed is not None:
                self._on_selection_changed(self._selected_index)

    def delete_selected_item(self) -> bool:
        if self._selected_index is None or not (0 <= self._selected_index < len(self._items)):
            return False
        self._items.pop(self._selected_index)
        self._selected_index = None
        self._recompose(notify=True)
        if self._on_selection_changed is not None:
            self._on_selection_changed(None)
        return True

    def set_tool_mode(self, mode: str) -> None:
        norm = str(mode or "crop").lower().strip()
        if norm not in self.VALID_TOOLS:
            norm = "crop"
        self.tool_mode = norm
        self._draw_mode = norm not in ("crop", "select")
        self._drag_origin_img = None
        self._drag_current_img = None
        self._last_draw_pt = None
        self._interaction = None
        if norm != "crop":
            self._crop_rect = None
        self.setCursor(self._default_tool_cursor())
        self.update()

    def _default_tool_cursor(self) -> Qt.CursorShape:
        if self.tool_mode == "text":
            return Qt.CursorShape.IBeamCursor
        if self.tool_mode == "select":
            return Qt.CursorShape.ArrowCursor
        return Qt.CursorShape.CrossCursor

    def set_draw_mode(self, enabled: bool) -> None:
        self.set_tool_mode("pen" if enabled else "crop")

    def set_pen_color(self, color: QColor) -> None:
        if color.isValid():
            self.pen_color = QColor(color)

    def set_pen_width(self, width: int) -> None:
        self.pen_width = max(1, min(80, int(width)))

    def get_crop_rect(self) -> Optional[QRect]:
        return self._crop_rect

    def clear_crop_rect(self) -> None:
        self._crop_rect = None
        self.update()

    def set_zoom(self, factor: float) -> float:
        clamped = max(0.25, min(6.0, float(factor)))
        self._zoom_factor = clamped
        if abs(clamped - 1.0) < 1e-4:
            self._pan_offset = QPoint(0, 0)
        self.update()
        if self._on_zoom_changed is not None:
            self._on_zoom_changed(self._zoom_factor)
        return self._zoom_factor

    def zoom_in(self) -> float:
        return self.set_zoom(self._zoom_factor * 1.2)

    def zoom_out(self) -> float:
        return self.set_zoom(self._zoom_factor / 1.2)

    def reset_zoom(self) -> float:
        self._pan_offset = QPoint(0, 0)
        return self.set_zoom(1.0)

    def get_visible_image_center(self) -> QPoint:
        pt = self._widget_to_image_point(self.rect().center())
        if pt is not None:
            return pt
        return QPoint(
            max(0, self._base_image.width() // 2),
            max(0, self._base_image.height() // 2),
        )

    def _image_target_rect(self) -> QRect:
        bounds = self.rect().adjusted(8, 8, -8, -8)
        if bounds.width() <= 0 or bounds.height() <= 0 or self._image.isNull():
            return QRect()
        base_size = self._image.size().scaled(
            bounds.size(), Qt.AspectRatioMode.KeepAspectRatio
        )
        zw = max(1, int(round(base_size.width() * self._zoom_factor)))
        zh = max(1, int(round(base_size.height() * self._zoom_factor)))
        x = bounds.x() + (bounds.width() - zw) // 2 + self._pan_offset.x()
        y = bounds.y() + (bounds.height() - zh) // 2 + self._pan_offset.y()
        return QRect(x, y, zw, zh)

    def _widget_to_image_float(
        self, pt: QPointF, clamp: bool = True
    ) -> Optional[QPointF]:
        target = self._image_target_rect()
        if target.isEmpty() or self._image.isNull():
            return None
        ix = ((pt.x() - target.x()) / max(1, target.width())) * self._image.width()
        iy = ((pt.y() - target.y()) / max(1, target.height())) * self._image.height()
        if clamp:
            ix = max(0.0, min(float(self._image.width()), ix))
            iy = max(0.0, min(float(self._image.height()), iy))
        return QPointF(ix, iy)

    def _widget_to_image_point(self, pt: QPoint) -> Optional[QPoint]:
        target = self._image_target_rect()
        if target.isEmpty() or self._image.isNull():
            return None
        rx = max(0.0, min(1.0, (pt.x() - target.x()) / max(1, target.width())))
        ry = max(0.0, min(1.0, (pt.y() - target.y()) / max(1, target.height())))
        ix = min(
            self._image.width() - 1,
            max(0, int(rx * self._image.width())),
        )
        iy = min(
            self._image.height() - 1,
            max(0, int(ry * self._image.height())),
        )
        return QPoint(ix, iy)

    def _image_float_point_to_widget(self, img_pt: QPointF) -> QPointF:
        target = self._image_target_rect()
        if target.isEmpty() or self._image.isNull():
            return QPointF()
        sx = target.width() / max(1, self._image.width())
        sy = target.height() / max(1, self._image.height())
        return QPointF(target.x() + img_pt.x() * sx, target.y() + img_pt.y() * sy)

    def _image_point_to_widget(self, img_pt: QPoint) -> QPointF:
        target = self._image_target_rect()
        if target.isEmpty() or self._image.isNull():
            return QPointF()
        sx = target.width() / max(1, self._image.width())
        sy = target.height() / max(1, self._image.height())
        return QPointF(
            target.x() + (img_pt.x() + 0.5) * sx,
            target.y() + (img_pt.y() + 0.5) * sy,
        )

    def _image_rect_to_widget(self, img_rect: QRect) -> QRectF:
        return self._image_rect_to_widget_f(QRectF(img_rect))

    def _image_rect_to_widget_f(self, img_rect: QRectF) -> QRectF:
        target = self._image_target_rect()
        if target.isEmpty() or self._image.isNull():
            return QRectF()
        sx = target.width() / max(1, self._image.width())
        sy = target.height() / max(1, self._image.height())
        return QRectF(
            target.x() + img_rect.x() * sx,
            target.y() + img_rect.y() * sy,
            img_rect.width() * sx,
            img_rect.height() * sy,
        )

    def _img_hit_tolerance(self) -> float:
        target = self._image_target_rect()
        if target.isEmpty() or self._image.isNull():
            return 8.0
        return max(8.0, 10.0 * (self._image.width() / max(1, target.width())))

    def get_handle_widget_rects(self, item: _AnnotationItem) -> Dict[str, QRectF]:
        """Returns 10x10 widget-space handle rects for moving/resizing an annotation item."""
        half = 5.0
        if item.kind in ("line", "arrow"):
            p1 = self._image_float_point_to_widget(item.start)
            p2 = self._image_float_point_to_widget(item.end)
            return {
                "p_start": QRectF(p1.x() - half, p1.y() - half, half * 2, half * 2),
                "p_end": QRectF(p2.x() - half, p2.y() - half, half * 2, half * 2),
            }
        wrect = self._image_rect_to_widget_f(item.bounding_rect())
        if wrect.isNull():
            return {}
        cx = wrect.center().x()
        cy = wrect.center().y()
        coords = {
            "nw": QPointF(wrect.left(), wrect.top()),
            "n": QPointF(cx, wrect.top()),
            "ne": QPointF(wrect.right(), wrect.top()),
            "e": QPointF(wrect.right(), cy),
            "se": QPointF(wrect.right(), wrect.bottom()),
            "s": QPointF(cx, wrect.bottom()),
            "sw": QPointF(wrect.left(), wrect.bottom()),
            "w": QPointF(wrect.left(), cy),
        }
        return {
            name: QRectF(pt.x() - half, pt.y() - half, half * 2, half * 2)
            for name, pt in coords.items()
        }

    def _hit_test_handle(self, widget_pt: QPointF) -> Optional[str]:
        item = self.get_selected_item()
        if item is None:
            return None
        for name, hrect in self.get_handle_widget_rects(item).items():
            if hrect.adjusted(-4.0, -4.0, 4.0, 4.0).contains(widget_pt):
                return name
        return None

    def _find_item_at_point(self, img_pt: QPointF) -> Optional[int]:
        tol = self._img_hit_tolerance()
        for idx in range(len(self._items) - 1, -1, -1):
            if self._items[idx].hit_test(img_pt, tolerance=tol):
                return idx
        return None

    @staticmethod
    def _handle_cursor(name: str) -> Qt.CursorShape:
        if name in ("nw", "se"):
            return Qt.CursorShape.SizeFDiagCursor
        if name in ("ne", "sw"):
            return Qt.CursorShape.SizeBDiagCursor
        if name in ("n", "s"):
            return Qt.CursorShape.SizeVerCursor
        if name in ("e", "w"):
            return Qt.CursorShape.SizeHorCursor
        return Qt.CursorShape.SizeAllCursor

    @staticmethod
    def _render_path_on_image(
        base_img: QImage,
        points: List[QPoint],
        color: QColor,
        width: int,
        is_highlighter: bool = False,
    ) -> QImage:
        out = base_img.convertToFormat(QImage.Format.Format_ARGB32).copy()
        if out.isNull() or not points:
            return out
        draw_color = QColor(color)
        stroke_w = max(1, int(width))
        if is_highlighter:
            draw_color.setAlpha(95)
            stroke_w = max(16, stroke_w * 4)
        else:
            draw_color.setAlpha(255)

        painter = QPainter(out)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            if len(points) == 1:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(draw_color)
                r = max(1.0, stroke_w / 2.0)
                painter.drawEllipse(QPointF(points[0]), r, r)
            else:
                path = QPainterPath()
                path.moveTo(QPointF(points[0]))
                for pt in points[1:]:
                    path.lineTo(QPointF(pt))
                pen = QPen(
                    draw_color,
                    stroke_w,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                    Qt.PenJoinStyle.RoundJoin,
                )
                painter.setPen(pen)
                painter.drawPath(path)
        finally:
            painter.end()
        return out

    @staticmethod
    def _render_shape_on_image(
        base_img: QImage,
        kind: str,
        start: QPoint,
        end: QPoint,
        color: QColor,
        width: int,
    ) -> QImage:
        out = base_img.convertToFormat(QImage.Format.Format_ARGB32).copy()
        if out.isNull():
            return out
        draw_color = QColor(color)
        draw_color.setAlpha(255)
        stroke_w = max(1, int(width))

        painter = QPainter(out)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            pen = QPen(
                draw_color,
                stroke_w,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            )
            painter.setPen(pen)
            if kind == "line":
                painter.drawLine(QPointF(start), QPointF(end))
            elif kind == "arrow":
                dx = float(end.x() - start.x())
                dy = float(end.y() - start.y())
                length = math.hypot(dx, dy)
                if length >= 1.0:
                    angle = math.atan2(dy, dx)
                    head_len = min(max(10.0, stroke_w * 4.0), max(10.0, length * 0.65))
                    spread = math.radians(28)
                    p1 = QPointF(
                        end.x() - head_len * math.cos(angle - spread),
                        end.y() - head_len * math.sin(angle - spread),
                    )
                    p2 = QPointF(
                        end.x() - head_len * math.cos(angle + spread),
                        end.y() - head_len * math.sin(angle + spread),
                    )
                    shaft_end = QPointF(
                        end.x() - (head_len * 0.55) * math.cos(angle),
                        end.y() - (head_len * 0.55) * math.sin(angle),
                    )
                    painter.drawLine(QPointF(start), shaft_end)
                    painter.setBrush(draw_color)
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.drawPolygon(QPolygonF([QPointF(end), p1, p2]))
                else:
                    painter.drawPoint(start)
            elif kind == "rect":
                rect = QRect(start, end).normalized()
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(rect)
            elif kind == "ellipse":
                rect = QRect(start, end).normalized()
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(rect)
        finally:
            painter.end()
        return out

    @staticmethod
    def _render_pixelated_on_image(
        base_img: QImage, rect: QRect, block_size: int = 10
    ) -> Optional[QImage]:
        bounded = rect.normalized().intersected(base_img.rect())
        if bounded.width() < 4 or bounded.height() < 4:
            return None
        out = base_img.convertToFormat(QImage.Format.Format_ARGB32).copy()
        sub = out.copy(bounded)
        bsize = max(2, int(block_size))
        tiny = sub.scaled(
            max(1, bounded.width() // bsize),
            max(1, bounded.height() // bsize),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        mosaic = tiny.scaled(
            bounded.size(),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        painter = QPainter(out)
        try:
            painter.drawImage(bounded.topLeft(), mosaic)
        finally:
            painter.end()
        return out

    def _draw_segment(self, start: QPoint, end: QPoint) -> None:
        if self._image.isNull():
            return
        pts = [start] if start == end else [start, end]
        is_hl = self.tool_mode == "highlighter"
        self._base_image = self._render_path_on_image(
            self._base_image, pts, self.pen_color, self.pen_width, is_highlighter=is_hl
        )
        self._recompose(notify=True)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        try:
            painter.fillRect(self.rect(), QColor("#141320"))
            painter.setPen(QPen(QColor("#363A4F"), 1))
            painter.drawRect(self.rect().adjusted(0, 0, -1, -1))

            target = self._image_target_rect()
            if target.isEmpty() or self._image.isNull():
                return

            painter.fillRect(target, QColor("#2A2D3E"))
            dpr = max(1.0, float(self.devicePixelRatioF()))
            phys_w = max(1, int(round(target.width() * dpr)))
            phys_h = max(1, int(round(target.height() * dpr)))
            if phys_w < self._image.width() or phys_h < self._image.height():
                cache_key = (int(self._image.cacheKey()), phys_w, phys_h, dpr)
                if self._render_cache_key != cache_key or self._render_cache_image is None:
                    scaled = self._image.scaled(
                        phys_w,
                        phys_h,
                        Qt.AspectRatioMode.IgnoreAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                    scaled.setDevicePixelRatio(dpr)
                    self._render_cache_key = cache_key
                    self._render_cache_image = scaled
                painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
                painter.drawImage(target, self._render_cache_image)
            else:
                use_smooth = phys_w <= int(self._image.width() * 1.5)
                painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, use_smooth)
                painter.drawImage(target, self._image)

            if self._crop_rect is not None and self._crop_rect.isValid():
                overlay = self._image_rect_to_widget(self._crop_rect)
                box_color = (
                    QColor("#F38BA8")
                    if self.tool_mode == "pixelate"
                    else QColor("#89B4FA")
                )
                painter.setPen(QPen(box_color, 2, Qt.PenStyle.DashLine))
                fill_color = QColor(box_color)
                fill_color.setAlpha(40)
                painter.setBrush(fill_color)
                painter.drawRect(overlay)

                dim_txt = f"{self._crop_rect.width()} × {self._crop_rect.height()}"
                badge_rect = QRectF(overlay.left(), max(4.0, overlay.top() - 22.0), 104, 18)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(24, 24, 37, 210))
                painter.drawRoundedRect(badge_rect, 4, 4)
                painter.setPen(QColor("#F9E2AF"))
                painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, dim_txt)

            if (
                self._interaction == "draw_shape"
                and self.tool_mode in ("line", "arrow", "rect", "ellipse")
                and self._drag_origin_img is not None
                and self._drag_current_img is not None
            ):
                p_start = self._image_point_to_widget(self._drag_origin_img)
                p_end = self._image_point_to_widget(self._drag_current_img)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                preview_pen = QPen(self.pen_color, max(1, self.pen_width), Qt.PenStyle.DashLine)
                painter.setPen(preview_pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                if self.tool_mode in ("line", "arrow"):
                    painter.drawLine(p_start, p_end)
                elif self.tool_mode == "rect":
                    painter.drawRect(QRectF(p_start, p_end).normalized())
                elif self.tool_mode == "ellipse":
                    painter.drawEllipse(QRectF(p_start, p_end).normalized())

            # Selection bounding box & resize handles for active vector item
            sel_item = self.get_selected_item()
            if sel_item is not None:
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                if sel_item.kind in ("line", "arrow"):
                    p1 = self._image_float_point_to_widget(sel_item.start)
                    p2 = self._image_float_point_to_widget(sel_item.end)
                    painter.setPen(QPen(QColor("#F9E2AF"), 1.5, Qt.PenStyle.DashLine))
                    painter.drawLine(p1, p2)
                else:
                    wbox = self._image_rect_to_widget_f(sel_item.bounding_rect())
                    painter.setPen(QPen(QColor("#F9E2AF"), 1.5, Qt.PenStyle.DashLine))
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawRect(wbox.adjusted(-2.0, -2.0, 2.0, 2.0))

                painter.setPen(QPen(QColor("#181624"), 1.5))
                painter.setBrush(QColor("#FAB387"))
                for hrect in self.get_handle_widget_rects(sel_item).values():
                    painter.drawRoundedRect(hrect, 2.0, 2.0)
        finally:
            painter.end()

    def wheelEvent(self, event: QWheelEvent) -> None:
        delta = event.angleDelta().y()
        if delta > 0:
            self.zoom_in()
            event.accept()
            return
        if delta < 0:
            self.zoom_out()
            event.accept()
            return
        super().wheelEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            img_pt_f = self._widget_to_image_float(event.position())
            if img_pt_f is not None:
                hit_idx = self._find_item_at_point(img_pt_f)
                if (
                    hit_idx is not None
                    and self._items[hit_idx].kind == "text"
                    and self._on_edit_text_item is not None
                ):
                    self.select_item(hit_idx)
                    self._on_edit_text_item(hit_idx)
                    event.accept()
                    return
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        alt_held = bool(event.modifiers() & Qt.KeyboardModifier.AltModifier)
        if event.button() in (
            Qt.MouseButton.MiddleButton,
            Qt.MouseButton.RightButton,
        ) or (event.button() == Qt.MouseButton.LeftButton and alt_held):
            self._panning = True
            self._pan_last_pos = event.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return

        if event.button() == Qt.MouseButton.LeftButton:
            pos_f = event.position()
            # 1. Resize handle hit on currently selected item takes highest priority
            handle_name = self._hit_test_handle(pos_f)
            sel_item = self.get_selected_item()
            if handle_name is not None and sel_item is not None:
                self._interaction = "resize"
                self._active_handle = handle_name
                self._orig_item_snapshot = sel_item.clone()
                self._orig_item_bounds = sel_item.bounding_rect()
                self._drag_undo_pushed = False
                self.setCursor(self._handle_cursor(handle_name))
                event.accept()
                return

            img_pt_f = self._widget_to_image_float(pos_f)
            if img_pt_f is None:
                super().mousePressEvent(event)
                return

            # 2. Clicking inside the currently selected item starts moving it
            if sel_item is not None and sel_item.hit_test(
                img_pt_f, tolerance=self._img_hit_tolerance()
            ):
                self._interaction = "move"
                self._orig_item_snapshot = sel_item.clone()
                self._move_origin_img = img_pt_f
                self._drag_undo_pushed = False
                self.setCursor(Qt.CursorShape.SizeAllCursor)
                event.accept()
                return

            # 3. In select mode, hit-test all items top-to-bottom to pick & move one
            if self.tool_mode == "select":
                hit_idx = self._find_item_at_point(img_pt_f)
                self.select_item(hit_idx)
                if hit_idx is not None:
                    self._interaction = "move"
                    self._orig_item_snapshot = self._items[hit_idx].clone()
                    self._move_origin_img = img_pt_f
                    self._drag_undo_pushed = False
                    self.setCursor(Qt.CursorShape.SizeAllCursor)
                event.accept()
                return

            # Clicking elsewhere starts a fresh tool operation
            self.select_item(None)
            img_pt = self._widget_to_image_point(pos_f.toPoint())
            if img_pt is not None:
                if self.tool_mode == "text":
                    if self._on_text_requested is not None:
                        self._on_text_requested(img_pt)
                    event.accept()
                    return
                if self.tool_mode == "eyedropper":
                    if not self._image.isNull() and self._image.rect().contains(img_pt):
                        sampled = self._image.pixelColor(img_pt)
                        if sampled.isValid():
                            self.set_pen_color(sampled)
                            if self._on_color_sampled is not None:
                                self._on_color_sampled(sampled)
                    event.accept()
                    return
                if self.tool_mode in ("pen", "highlighter"):
                    if self._on_before_modify is not None:
                        self._on_before_modify()
                    self._interaction = "draw_path"
                    self._stroke_points = [img_pt]
                    self._last_draw_pt = img_pt
                    new_item = _AnnotationItem(
                        kind=self.tool_mode,
                        color=self.pen_color,
                        stroke_width=self.pen_width,
                        points=[QPointF(img_pt)],
                    )
                    self.add_item(new_item, select=True)
                elif self.tool_mode in ("line", "arrow", "rect", "ellipse"):
                    self._interaction = "draw_shape"
                    self._drag_origin_img = img_pt
                    self._drag_current_img = img_pt
                    self.update()
                else:
                    # crop or pixelate marquee
                    self._interaction = "marquee"
                    self._drag_origin_img = img_pt
                    self._crop_rect = None
                    self.update()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._panning and self._pan_last_pos is not None:
            cur = event.position().toPoint()
            self._pan_offset += cur - self._pan_last_pos
            self._pan_last_pos = cur
            self.update()
            event.accept()
            return

        if (event.buttons() & Qt.MouseButton.LeftButton) and self._interaction in (
            "move",
            "resize",
        ):
            cur_f = self._widget_to_image_float(event.position(), clamp=True)
            if (
                cur_f is not None
                and self._selected_index is not None
                and 0 <= self._selected_index < len(self._items)
                and self._orig_item_snapshot is not None
            ):
                if (
                    self._interaction == "move"
                    and self._move_origin_img is not None
                ):
                    dx = cur_f.x() - self._move_origin_img.x()
                    dy = cur_f.y() - self._move_origin_img.y()
                    if abs(dx) >= 0.5 or abs(dy) >= 0.5:
                        if not self._drag_undo_pushed:
                            # Temporarily restore pre-drag item so undo snapshot records original coords
                            self._items[self._selected_index] = self._orig_item_snapshot.clone()
                            self._recompose(notify=False)
                            if self._on_before_modify is not None:
                                self._on_before_modify()
                            self._drag_undo_pushed = True
                        moved = self._orig_item_snapshot.clone()
                        moved.translate(dx, dy)
                        self._items[self._selected_index] = moved
                        self._recompose(notify=True)
                elif (
                    self._interaction == "resize"
                    and self._active_handle is not None
                    and self._orig_item_bounds is not None
                ):
                    if not self._drag_undo_pushed:
                        self._items[self._selected_index] = self._orig_item_snapshot.clone()
                        self._recompose(notify=False)
                        if self._on_before_modify is not None:
                            self._on_before_modify()
                        self._drag_undo_pushed = True
                    resized = self._orig_item_snapshot.clone()
                    if self._active_handle == "p_start":
                        resized.start = cur_f
                    elif self._active_handle == "p_end":
                        resized.end = cur_f
                    else:
                        ob = self._orig_item_bounds
                        left, top, right, bottom = ob.left(), ob.top(), ob.right(), ob.bottom()
                        hname = self._active_handle
                        if "w" in hname:
                            left = min(right - 6.0, cur_f.x())
                        if "e" in hname:
                            right = max(left + 6.0, cur_f.x())
                        if "n" in hname:
                            top = min(bottom - 6.0, cur_f.y())
                        if "s" in hname:
                            bottom = max(top + 6.0, cur_f.y())
                        resized.resize_from_snapshot(
                            self._orig_item_snapshot,
                            ob,
                            QRectF(left, top, right - left, bottom - top),
                        )
                    self._items[self._selected_index] = resized
                    self._recompose(notify=True)
            event.accept()
            return

        if event.buttons() & Qt.MouseButton.LeftButton:
            img_pt = self._widget_to_image_point(event.position().toPoint())
            if img_pt is not None:
                if (
                    self._interaction == "draw_path"
                    and self.tool_mode in ("pen", "highlighter")
                    and self._selected_index is not None
                    and 0 <= self._selected_index < len(self._items)
                ):
                    if not self._stroke_points or self._stroke_points[-1] != img_pt:
                        self._stroke_points.append(img_pt)
                        self._items[self._selected_index].points.append(QPointF(img_pt))
                        self._recompose(notify=True)
                    self._last_draw_pt = img_pt
                elif (
                    self._interaction == "draw_shape"
                    and self.tool_mode in ("line", "arrow", "rect", "ellipse")
                    and self._drag_origin_img is not None
                ):
                    self._drag_current_img = img_pt
                    self.update()
                elif self._interaction == "marquee" and self._drag_origin_img is not None:
                    self._crop_rect = QRect(self._drag_origin_img, img_pt).normalized()
                    self.update()
                event.accept()
                return

        # Hover cursor feedback when not dragging
        if event.modifiers() & Qt.KeyboardModifier.AltModifier:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            hname = self._hit_test_handle(event.position())
            if hname is not None:
                self.setCursor(self._handle_cursor(hname))
            else:
                img_pt_f = self._widget_to_image_float(event.position())
                sel_item = self.get_selected_item()
                if (
                    img_pt_f is not None
                    and (
                        (
                            sel_item is not None
                            and sel_item.hit_test(img_pt_f, tolerance=self._img_hit_tolerance())
                        )
                        or (
                            self.tool_mode == "select"
                            and self._find_item_at_point(img_pt_f) is not None
                        )
                    )
                ):
                    self.setCursor(Qt.CursorShape.SizeAllCursor)
                else:
                    self.setCursor(self._default_tool_cursor())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._panning and event.button() in (
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.MiddleButton,
            Qt.MouseButton.RightButton,
        ):
            self._panning = False
            self._pan_last_pos = None
            self.setCursor(
                Qt.CursorShape.OpenHandCursor
                if (event.modifiers() & Qt.KeyboardModifier.AltModifier)
                else self._default_tool_cursor()
            )
            event.accept()
            return

        if event.button() == Qt.MouseButton.LeftButton:
            if self._interaction in ("move", "resize"):
                self._interaction = None
                self._active_handle = None
                self._orig_item_snapshot = None
                self._orig_item_bounds = None
                self._move_origin_img = None
                self._drag_undo_pushed = False
                self.setCursor(self._default_tool_cursor())
                event.accept()
                return

            img_pt = self._widget_to_image_point(event.position().toPoint())
            if self._interaction == "draw_path" and self.tool_mode in ("pen", "highlighter"):
                if (
                    img_pt is not None
                    and self._selected_index is not None
                    and 0 <= self._selected_index < len(self._items)
                    and (not self._stroke_points or self._stroke_points[-1] != img_pt)
                ):
                    self._stroke_points.append(img_pt)
                    self._items[self._selected_index].points.append(QPointF(img_pt))
                    self._recompose(notify=True)
                self._stroke_points = []
                self._last_draw_pt = None
            elif (
                self._interaction == "draw_shape"
                and self.tool_mode in ("line", "arrow", "rect", "ellipse")
                and self._drag_origin_img is not None
            ):
                end_pt = img_pt or self._drag_current_img or self._drag_origin_img
                if end_pt != self._drag_origin_img:
                    if self._on_before_modify is not None:
                        self._on_before_modify()
                    if self.tool_mode in ("line", "arrow"):
                        shape_item = _AnnotationItem(
                            kind=self.tool_mode,
                            color=self.pen_color,
                            stroke_width=self.pen_width,
                            start=QPointF(self._drag_origin_img),
                            end=QPointF(end_pt),
                        )
                    else:
                        shape_item = _AnnotationItem(
                            kind=self.tool_mode,
                            color=self.pen_color,
                            stroke_width=self.pen_width,
                            rect=QRectF(QRect(self._drag_origin_img, end_pt).normalized()),
                        )
                    self._drag_origin_img = None
                    self._drag_current_img = None
                    self._interaction = None
                    self.add_item(shape_item, select=True)
                    event.accept()
                    return
                self._drag_origin_img = None
                self._drag_current_img = None
                self.update()
            elif self.tool_mode == "pixelate":
                if self._drag_origin_img is not None and img_pt is not None:
                    rect = QRect(self._drag_origin_img, img_pt).normalized()
                    if rect.width() >= 4 and rect.height() >= 4:
                        if _ImagePreviewCanvas._render_pixelated_on_image(self._image, rect) is not None:
                            if self._on_before_modify is not None:
                                self._on_before_modify()
                            self._crop_rect = None
                            self._drag_origin_img = None
                            self._interaction = None
                            self.add_item(
                                _AnnotationItem(kind="pixelate", rect=QRectF(rect), block_size=10),
                                select=True,
                            )
                            event.accept()
                            return
                self._crop_rect = None
                self._drag_origin_img = None
                self.update()
            else:
                if self._drag_origin_img is not None and img_pt is not None:
                    rect = QRect(self._drag_origin_img, img_pt).normalized()
                    self._crop_rect = (
                        rect if rect.width() >= 4 and rect.height() >= 4 else None
                    )
                    self.update()
                self._drag_origin_img = None
            self._interaction = None
            event.accept()
            return
        super().mouseReleaseEvent(event)


class ImageEditDialog(QDialog):
    """Full-screen studio editor with top-bar emoji controls, undo/redo, highlighter, shapes, text, and filters."""

    MAX_UNDO_STEPS = 40
    MAX_DISPLAY_DIM = 3840
    COLOR_PRESETS = (
        ("🔴", "#F38BA8", "Sunset Coral Red"),
        ("🟠", "#FAB387", "Sunset Peach"),
        ("🟡", "#F9E2AF", "Highlighter Yellow"),
        ("🟢", "#A6E3A1", "Mint Green"),
        ("🔵", "#89B4FA", "Sky Blue"),
        ("🟣", "#CBA6F7", "Lavender Purple"),
        ("⚪", "#FFFFFF", "White"),
    )
    TOOL_HINTS = {
        "select": "🖱️ Select: Click & drag items to move or resize with handles (Alt+Drag to pan)",
        "crop": "✂️ Crop: Drag area then click ✂️ (Alt+Drag to pan)",
        "pen": "🖊️ Pen: Drag to draw; drag handles to resize (Alt+Drag to pan)",
        "highlighter": "🖍️ Highlighter: Drag to highlight; drag handles to resize",
        "line": "📏 Line: Drag line; drag endpoints to adjust",
        "arrow": "➡️ Arrow: Drag arrow; drag endpoints to adjust",
        "rect": "🔲 Rectangle: Drag box; use handles to move/resize",
        "ellipse": "⭕ Ellipse: Drag circle/oval; use handles to move/resize",
        "text": "🔤 Text: Click image to place text or click 📝 button",
        "pixelate": "🫧 Pixelate: Drag area to redact; use handles to adjust",
        "eyedropper": "💧 Eyedropper: Click image to sample a color",
    }

    def __init__(
        self,
        image: QImage,
        initial_width: Optional[int] = None,
        initial_height: Optional[int] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._original_image = image.convertToFormat(QImage.Format.Format_ARGB32)
        self._working_image = self._original_image.copy()
        self._orig_w = max(16, min(self.MAX_DISPLAY_DIM, int(initial_width or image.width() or 16)))
        self._orig_h = max(16, min(self.MAX_DISPLAY_DIM, int(initial_height or image.height() or 16)))
        self._aspect_ratio = self._orig_w / max(1, self._orig_h)
        self.delete_requested = False
        self._updating_spins = False
        self._syncing_item_controls = False
        self._user_picked_color = False
        self._initial_fullscreen_applied = False
        self._undo_stack: List[
            Tuple[QImage, List[_AnnotationItem], Optional[int], int, int, float]
        ] = []
        self._redo_stack: List[
            Tuple[QImage, List[_AnnotationItem], Optional[int], int, int, float]
        ] = []

        self.setWindowTitle("✨ Full Screen Image Editor")
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowMinimizeButtonHint
        )
        self.setModal(True)
        self.setMinimumSize(640, 420)
        self.resize(960, 640)
        self.setWindowState(
            self.windowState()
            | Qt.WindowState.WindowFullScreen
            | Qt.WindowState.WindowMaximized
        )

        self._setup_styles()
        self._build_ui()
        self._setup_shortcuts()
        self._update_info_label()
        self._update_undo_redo_buttons()

    def _setup_styles(self) -> None:
        self.setStyleSheet(
            """
            QDialog {
                background-color: qlineargradient(
                    x1:0, y1:0, x2:0.4, y2:1,
                    stop:0 #181624, stop:0.6 #241D35, stop:1 #30213B
                );
                color: #CDD6F4;
                font-family: 'Segoe UI Emoji', 'Segoe UI', sans-serif;
            }
            QLabel {
                color: #CDD6F4;
                font-size: 12px;
            }
            QLabel#ImageMetaLabel {
                color: #FAB387;
                font-size: 11px;
                font-weight: 600;
            }
            QLabel#ImageToolHint {
                color: #F9E2AF;
                font-size: 11px;
                font-weight: 600;
            }
            QSpinBox {
                background-color: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #2A2D3E, stop:1 #342945
                );
                border: 1px solid #45475A;
                border-radius: 5px;
                padding: 2px 5px;
                color: #CDD6F4;
                font-size: 11px;
            }
            QSpinBox:focus {
                border-color: #FAB387;
            }
            QCheckBox {
                color: #CDD6F4;
                font-size: 12px;
                spacing: 4px;
            }
            QWidget#ImageDialogTopBar {
                background-color: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #242136, stop:0.5 #2F2640, stop:1 #3B2846
                );
                border: 1px solid #45475A;
                border-radius: 8px;
            }
            QPushButton {
                background-color: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #2A2D3E, stop:1 #342945
                );
                border: 1px solid #45475A;
                border-radius: 6px;
                color: #CDD6F4;
                padding: 3px 7px;
                font-size: 13px;
                font-weight: 600;
                min-height: 24px;
            }
            QPushButton:hover {
                background-color: #3B3654;
                border-color: #FAB387;
            }
            QPushButton:disabled {
                color: #585B70;
                border-color: #2A2D3E;
            }
            QPushButton:checked {
                background-color: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #F9E2AF, stop:0.5 #FAB387, stop:1 #F38BA8
                );
                border-color: #F9E2AF;
                color: #1E1E2E;
            }
            QPushButton#ApplyEmojiBtn {
                background-color: #2A3D34;
                border-color: #A6E3A1;
            }
            QPushButton#ApplyEmojiBtn:hover {
                background-color: #A6E3A1;
                color: #1E1E2E;
            }
            QPushButton#DangerBtn {
                color: #F38BA8;
                border-color: #6B3C4E;
            }
            QPushButton#DangerBtn:hover {
                background-color: #F38BA8;
                border-color: #F38BA8;
                color: #1E1E2E;
            }
            QPushButton#ColorDotBtn {
                padding: 2px 4px;
                min-width: 24px;
                font-size: 12px;
            }
            """
        )

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        self.canvas = _ImagePreviewCanvas(
            self._working_image,
            on_image_modified=self._on_canvas_modified,
            on_before_modify=self._push_undo_state,
            on_text_requested=self._on_canvas_text_requested,
            on_color_sampled=self._on_color_sampled,
            on_zoom_changed=self._on_zoom_changed,
            on_selection_changed=self._on_canvas_selection_changed,
            on_edit_text_item=self._on_edit_text_item,
            parent=self,
        )

        # All action/tool buttons live in self.top_bar using emojis
        self.top_bar = QWidget(self)
        self.top_bar.setObjectName("ImageDialogTopBar")
        self.top_bar.installEventFilter(self)
        top_vbox = QVBoxLayout(self.top_bar)
        top_vbox.setContentsMargins(8, 6, 8, 6)
        top_vbox.setSpacing(6)

        # Row 1: Undo/Redo, Tools (Crop, Pen, Highlighter, Shapes, Text, Pixelate, Eyedropper) + Session Actions
        row1 = QHBoxLayout()
        row1.setSpacing(4)

        self.btn_undo = QPushButton("↩️")
        self.btn_undo.setToolTip("Undo (Ctrl+Z)")
        self.btn_undo.clicked.connect(self.undo)
        row1.addWidget(self.btn_undo)

        self.btn_redo = QPushButton("↪️")
        self.btn_redo.setToolTip("Redo (Ctrl+Y / Ctrl+Shift+Z)")
        self.btn_redo.clicked.connect(self.redo)
        row1.addWidget(self.btn_redo)

        self.btn_reset = QPushButton("♻️")
        self.btn_reset.setToolTip("Reset Image to Original")
        self.btn_reset.clicked.connect(self.reset_image)
        row1.addWidget(self.btn_reset)

        self._tool_group = QButtonGroup(self)
        self._tool_group.setExclusive(True)
        self._tool_buttons: Dict[str, QPushButton] = {}

        def _make_tool_btn(
            emoji: str, mode: str, tooltip: str, checked: bool = False
        ) -> QPushButton:
            btn = QPushButton(emoji)
            btn.setCheckable(True)
            btn.setChecked(checked)
            btn.setToolTip(tooltip)
            self._tool_group.addButton(btn)
            self._tool_buttons[mode] = btn
            return btn

        self.btn_tool_select = _make_tool_btn(
            "🖱️", "select", "Select, Move & Resize Drawn Items (Delete removes item)"
        )
        self.btn_tool_select.clicked.connect(lambda: self.select_tool("select"))
        row1.addWidget(self.btn_tool_select)

        self.btn_tool_crop = _make_tool_btn(
            "✂️", "crop", "Crop Tool (Drag area on canvas, click again to crop)", checked=True
        )
        self.btn_crop = self.btn_tool_crop
        self.btn_tool_crop.clicked.connect(self._on_crop_clicked)
        row1.addWidget(self.btn_tool_crop)

        self.btn_draw = _make_tool_btn("🖊️", "pen", "Freehand Pen Tool")
        self.btn_draw.clicked.connect(lambda: self.select_tool("pen"))
        row1.addWidget(self.btn_draw)

        self.btn_highlighter = _make_tool_btn(
            "🖍️", "highlighter", "Highlighter Marker Tool"
        )
        self.btn_highlighter.clicked.connect(lambda: self.select_tool("highlighter"))
        row1.addWidget(self.btn_highlighter)

        self.btn_tool_line = _make_tool_btn("📏", "line", "Straight Line Tool")
        self.btn_tool_line.clicked.connect(lambda: self.select_tool("line"))
        row1.addWidget(self.btn_tool_line)

        self.btn_tool_arrow = _make_tool_btn("➡️", "arrow", "Arrow Annotation Tool")
        self.btn_tool_arrow.clicked.connect(lambda: self.select_tool("arrow"))
        row1.addWidget(self.btn_tool_arrow)

        self.btn_tool_rect = _make_tool_btn("🔲", "rect", "Rectangle Outline Tool")
        self.btn_tool_rect.clicked.connect(lambda: self.select_tool("rect"))
        row1.addWidget(self.btn_tool_rect)

        self.btn_tool_ellipse = _make_tool_btn("⭕", "ellipse", "Circle / Ellipse Tool")
        self.btn_tool_ellipse.clicked.connect(lambda: self.select_tool("ellipse"))
        row1.addWidget(self.btn_tool_ellipse)

        self.btn_tool_text = _make_tool_btn("🔤", "text", "Text Tool (Click image to place)")
        self.btn_tool_text.clicked.connect(lambda: self.select_tool("text"))
        row1.addWidget(self.btn_tool_text)

        self.btn_add_text = QPushButton("📝")
        self.btn_add_text.setToolTip("Add Text Box to Image (Movable & Resizable)")
        self.btn_add_text.clicked.connect(lambda: self.prompt_and_add_text())
        row1.addWidget(self.btn_add_text)

        self.btn_tool_pixelate = _make_tool_btn(
            "🫧", "pixelate", "Pixelate / Redact Area Tool (Drag box)"
        )
        self.btn_tool_pixelate.clicked.connect(lambda: self.select_tool("pixelate"))
        row1.addWidget(self.btn_tool_pixelate)

        self.btn_tool_eyedropper = _make_tool_btn(
            "💧", "eyedropper", "Eyedropper Color Picker (Click image)"
        )
        self.btn_tool_eyedropper.clicked.connect(lambda: self.select_tool("eyedropper"))
        row1.addWidget(self.btn_tool_eyedropper)

        row1.addStretch(1)

        self.btn_copy_image = QPushButton("📋")
        self.btn_copy_image.setToolTip("Copy Edited Image to Clipboard (Ctrl+C)")
        self.btn_copy_image.clicked.connect(self.copy_image_to_clipboard)
        row1.addWidget(self.btn_copy_image)

        self.btn_export_image = QPushButton("💾")
        self.btn_export_image.setToolTip("Save Edited Image to File...")
        self.btn_export_image.clicked.connect(lambda: self.export_image_to_file())
        row1.addWidget(self.btn_export_image)

        self.btn_replace = QPushButton("📂")
        self.btn_replace.setToolTip("Replace Image from File...")
        self.btn_replace.clicked.connect(lambda: self.replace_image())
        row1.addWidget(self.btn_replace)

        self.btn_delete = QPushButton("🗑️")
        self.btn_delete.setObjectName("DangerBtn")
        self.btn_delete.setToolTip("Delete Image from Note")
        self.btn_delete.clicked.connect(self._on_delete_clicked)
        row1.addWidget(self.btn_delete)

        self.btn_fullscreen = QPushButton("🖥️")
        self.btn_fullscreen.setToolTip("Toggle Full Screen / Windowed (F11 / Double-click bar)")
        self.btn_fullscreen.clicked.connect(self.toggle_fullscreen)
        row1.addWidget(self.btn_fullscreen)

        self.btn_apply = QPushButton("✅")
        self.btn_apply.setObjectName("ApplyEmojiBtn")
        self.btn_apply.setToolTip("Save & Apply Changes (Ctrl+S)")
        self.btn_apply.clicked.connect(self.accept)
        row1.addWidget(self.btn_apply)

        self.btn_cancel = QPushButton("❌")
        self.btn_cancel.setToolTip("Cancel Changes (Esc)")
        self.btn_cancel.clicked.connect(self.reject)
        row1.addWidget(self.btn_cancel)

        top_vbox.addLayout(row1)

        # Row 2: Color Swatches, Stroke Width, Transforms, Filters, Size & Presets, Zoom & Status
        row2 = QHBoxLayout()
        row2.setSpacing(4)

        self.btn_draw_color = QPushButton("🎨")
        self.btn_draw_color.setToolTip("Pick Custom Color")
        self.btn_draw_color.clicked.connect(self._pick_draw_color)
        row2.addWidget(self.btn_draw_color)

        self.color_preset_buttons: List[QPushButton] = []
        for emoji, hex_color, tip in self.COLOR_PRESETS:
            cbtn = QPushButton(emoji)
            cbtn.setObjectName("ColorDotBtn")
            cbtn.setToolTip(f"{tip} ({hex_color})")
            cbtn.clicked.connect(
                lambda _chk=False, col=hex_color: self._apply_preset_color(col)
            )
            row2.addWidget(cbtn)
            self.color_preset_buttons.append(cbtn)

        self.spin_pen_width = QSpinBox()
        self.spin_pen_width.setRange(1, 80)
        self.spin_pen_width.setValue(3)
        self.spin_pen_width.setPrefix("🖌️ ")
        self.spin_pen_width.setSuffix("px")
        self.spin_pen_width.setToolTip("Stroke Size (px)")
        self.spin_pen_width.valueChanged.connect(self._on_pen_width_changed)
        row2.addWidget(self.spin_pen_width)

        self.btn_rotate_left = QPushButton("🔄")
        self.btn_rotate_left.setToolTip("Rotate 90° Counter-Clockwise")
        self.btn_rotate_left.clicked.connect(lambda: self.rotate_image(-90))
        row2.addWidget(self.btn_rotate_left)

        self.btn_rotate_right = QPushButton("🔃")
        self.btn_rotate_right.setToolTip("Rotate 90° Clockwise")
        self.btn_rotate_right.clicked.connect(lambda: self.rotate_image(90))
        row2.addWidget(self.btn_rotate_right)

        self.btn_flip_h = QPushButton("↔️")
        self.btn_flip_h.setToolTip("Flip Horizontal")
        self.btn_flip_h.clicked.connect(lambda: self.flip_image(horizontal=True))
        row2.addWidget(self.btn_flip_h)

        self.btn_flip_v = QPushButton("↕️")
        self.btn_flip_v.setToolTip("Flip Vertical")
        self.btn_flip_v.clicked.connect(lambda: self.flip_image(horizontal=False))
        row2.addWidget(self.btn_flip_v)

        self.btn_grayscale = QPushButton("🌗")
        self.btn_grayscale.setToolTip("Convert to Grayscale")
        self.btn_grayscale.clicked.connect(self.apply_grayscale)
        row2.addWidget(self.btn_grayscale)

        self.btn_invert = QPushButton("☯️")
        self.btn_invert.setToolTip("Invert Colors")
        self.btn_invert.clicked.connect(self.apply_invert)
        row2.addWidget(self.btn_invert)

        self.btn_brightness = QPushButton("☀️")
        self.btn_brightness.setToolTip("Brighten & Enhance Contrast")
        self.btn_brightness.clicked.connect(lambda: self.apply_brightness_boost(20))
        row2.addWidget(self.btn_brightness)

        row2.addWidget(QLabel("📐"))
        self.spin_width = QSpinBox()
        self.spin_width.setRange(16, self.MAX_DISPLAY_DIM)
        self.spin_width.setSuffix("px")
        self.spin_width.setValue(self._orig_w)
        self.spin_width.valueChanged.connect(self._on_width_changed)
        row2.addWidget(self.spin_width)

        self.spin_height = QSpinBox()
        self.spin_height.setRange(16, self.MAX_DISPLAY_DIM)
        self.spin_height.setSuffix("px")
        self.spin_height.setValue(self._orig_h)
        self.spin_height.valueChanged.connect(self._on_height_changed)
        row2.addWidget(self.spin_height)

        self.chk_aspect = QCheckBox("🔒")
        self.chk_aspect.setToolTip("Lock Aspect Ratio")
        self.chk_aspect.setChecked(True)
        self.chk_aspect.toggled.connect(self._on_aspect_toggled)
        row2.addWidget(self.chk_aspect)

        self.btn_scale_50 = QPushButton("🔹50%")
        self.btn_scale_50.setToolTip("Scale to 50%")
        self.btn_scale_50.clicked.connect(lambda: self.apply_scale_preset(0.5))
        row2.addWidget(self.btn_scale_50)

        self.btn_scale_75 = QPushButton("🔸75%")
        self.btn_scale_75.setToolTip("Scale to 75%")
        self.btn_scale_75.clicked.connect(lambda: self.apply_scale_preset(0.75))
        row2.addWidget(self.btn_scale_75)

        self.btn_scale_100 = QPushButton("💯")
        self.btn_scale_100.setToolTip("Scale to 100% Source Size")
        self.btn_scale_100.clicked.connect(lambda: self.apply_scale_preset(1.0))
        row2.addWidget(self.btn_scale_100)

        self.btn_fit_sidebar = QPushButton("📱280")
        self.btn_fit_sidebar.setToolTip("Fit to Sidebar Width (280px)")
        self.btn_fit_sidebar.clicked.connect(lambda: self.fit_to_width(280))
        row2.addWidget(self.btn_fit_sidebar)

        self.btn_zoom_out = QPushButton("🔍➖")
        self.btn_zoom_out.setToolTip("Zoom Out (Mouse Wheel Down)")
        self.btn_zoom_out.clicked.connect(self.canvas.zoom_out)
        row2.addWidget(self.btn_zoom_out)

        self.btn_zoom_reset = QPushButton("🎯")
        self.btn_zoom_reset.setToolTip("Reset Zoom & Pan to 100%")
        self.btn_zoom_reset.clicked.connect(self.canvas.reset_zoom)
        row2.addWidget(self.btn_zoom_reset)

        self.btn_zoom_in = QPushButton("🔍➕")
        self.btn_zoom_in.setToolTip("Zoom In (Mouse Wheel Up)")
        self.btn_zoom_in.clicked.connect(self.canvas.zoom_in)
        row2.addWidget(self.btn_zoom_in)

        row2.addStretch(1)

        self.lbl_tool_hint = QLabel(self.TOOL_HINTS["crop"])
        self.lbl_tool_hint.setObjectName("ImageToolHint")
        row2.addWidget(self.lbl_tool_hint)

        self.lbl_info = QLabel()
        self.lbl_info.setObjectName("ImageMetaLabel")
        row2.addWidget(self.lbl_info)

        top_vbox.addLayout(row2)

        root.addWidget(self.top_bar)
        root.addWidget(self.canvas, 1)

        # Hidden standard dialog button box kept for API compatibility
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.button_box.hide()

    def _setup_shortcuts(self) -> None:
        self._sc_undo = QShortcut(QKeySequence("Ctrl+Z"), self)
        self._sc_undo.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._sc_undo.activated.connect(self.undo)

        self._sc_redo = QShortcut(QKeySequence("Ctrl+Y"), self)
        self._sc_redo.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._sc_redo.activated.connect(self.redo)

        self._sc_redo_alt = QShortcut(QKeySequence("Ctrl+Shift+Z"), self)
        self._sc_redo_alt.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._sc_redo_alt.activated.connect(self.redo)

        self._sc_copy = QShortcut(QKeySequence("Ctrl+C"), self)
        self._sc_copy.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._sc_copy.activated.connect(self.copy_image_to_clipboard)

        self._sc_save = QShortcut(QKeySequence("Ctrl+S"), self)
        self._sc_save.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._sc_save.activated.connect(self.accept)

        self._sc_fullscreen = QShortcut(QKeySequence("F11"), self)
        self._sc_fullscreen.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._sc_fullscreen.activated.connect(self.toggle_fullscreen)

    def _push_undo_state(self) -> None:
        base_img, items, sel_idx = self.canvas.get_state_snapshot()
        self._working_image = self.canvas.get_image().copy()
        snapshot = (
            base_img,
            items,
            sel_idx,
            int(self.spin_width.value()),
            int(self.spin_height.value()),
            float(self._aspect_ratio),
        )
        self._undo_stack.append(snapshot)
        if len(self._undo_stack) > self.MAX_UNDO_STEPS:
            self._undo_stack.pop(0)
        self._redo_stack.clear()
        self._update_undo_redo_buttons()

    def _update_undo_redo_buttons(self) -> None:
        self.btn_undo.setEnabled(bool(self._undo_stack))
        self.btn_redo.setEnabled(bool(self._redo_stack))

    def undo(self) -> bool:
        """Restores the previous editing state (Ctrl+Z)."""
        if not self._undo_stack:
            return False
        cur_base, cur_items, cur_sel = self.canvas.get_state_snapshot()
        cur_snapshot = (
            cur_base,
            cur_items,
            cur_sel,
            int(self.spin_width.value()),
            int(self.spin_height.value()),
            float(self._aspect_ratio),
        )
        self._redo_stack.append(cur_snapshot)
        prev_base, prev_items, prev_sel, prev_w, prev_h, prev_ratio = self._undo_stack.pop()
        self._aspect_ratio = prev_ratio
        self.canvas.restore_state_snapshot(prev_base, prev_items, prev_sel)
        self._working_image = self.canvas.get_image().copy()
        self.set_target_size(prev_w, prev_h)
        self._update_undo_redo_buttons()
        self.lbl_tool_hint.setText("↩️ Undid last change")
        return True

    def redo(self) -> bool:
        """Reapplies an undone editing state (Ctrl+Y)."""
        if not self._redo_stack:
            return False
        cur_base, cur_items, cur_sel = self.canvas.get_state_snapshot()
        cur_snapshot = (
            cur_base,
            cur_items,
            cur_sel,
            int(self.spin_width.value()),
            int(self.spin_height.value()),
            float(self._aspect_ratio),
        )
        self._undo_stack.append(cur_snapshot)
        next_base, next_items, next_sel, next_w, next_h, next_ratio = self._redo_stack.pop()
        self._aspect_ratio = next_ratio
        self.canvas.restore_state_snapshot(next_base, next_items, next_sel)
        self._working_image = self.canvas.get_image().copy()
        self.set_target_size(next_w, next_h)
        self._update_undo_redo_buttons()
        self.lbl_tool_hint.setText("↪️ Redid change")
        return True

    def delete_selected_item(self) -> bool:
        if self.canvas.get_selected_item() is None:
            return False
        self._push_undo_state()
        ok = self.canvas.delete_selected_item()
        if ok:
            self.lbl_tool_hint.setText("🗑️ Removed selected item")
        return ok

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            focus_w = QApplication.focusWidget()
            if not isinstance(focus_w, (QSpinBox, QLineEdit)) and self.delete_selected_item():
                event.accept()
                return
        super().keyPressEvent(event)

    def select_tool(self, mode: str) -> None:
        norm = str(mode or "crop").lower().strip()
        if norm != "select":
            self.canvas.select_item(None)
        if (
            norm == "highlighter"
            and not self._user_picked_color
            and self.canvas.pen_color.name().lower() == "#f38ba8"
        ):
            self.canvas.set_pen_color(QColor("#F9E2AF"))
        self.canvas.set_tool_mode(norm)
        btn = self._tool_buttons.get(self.canvas.tool_mode)
        if btn is not None and not btn.isChecked():
            btn.setChecked(True)
        self.lbl_tool_hint.setText(self.TOOL_HINTS.get(self.canvas.tool_mode, ""))

    def _on_crop_clicked(self) -> None:
        if self.canvas.get_crop_rect() is not None:
            self.crop_to_selection()
        else:
            self.select_tool("crop")

    def _on_canvas_modified(self) -> None:
        self._working_image = self.canvas.get_image()
        self._update_info_label()

    def _on_canvas_selection_changed(self, idx: Optional[int]) -> None:
        item = self.canvas.get_selected_item()
        if item is not None:
            self._syncing_item_controls = True
            try:
                if item.kind not in ("pixelate", "text"):
                    self.spin_pen_width.setValue(
                        max(1, min(80, int(item.stroke_width)))
                    )
            finally:
                self._syncing_item_controls = False
            kind_label = item.kind.capitalize()
            extra = " • Double-click to edit" if item.kind == "text" else ""
            self.lbl_tool_hint.setText(
                f"🖐️ Selected {kind_label}: drag to move, drag handles to resize{extra}"
            )
        else:
            self.lbl_tool_hint.setText(self.TOOL_HINTS.get(self.canvas.tool_mode, ""))

    def _on_pen_width_changed(self, width: int) -> None:
        self.canvas.set_pen_width(width)
        if self._syncing_item_controls:
            return
        sel = self.canvas.get_selected_item()
        if sel is not None and sel.kind not in ("pixelate",):
            self._push_undo_state()
            item_ref = self.canvas.get_selected_item()
            if item_ref is not None:
                if item_ref.kind == "text":
                    item_ref.font_px = max(12, int(width) * 5)
                    font = QFont("Segoe UI", -1, QFont.Weight.Bold)
                    font.setPixelSize(item_ref.font_px)
                    metrics = QFontMetrics(font)
                    item_ref.rect = QRectF(
                        item_ref.rect.left(),
                        item_ref.rect.top(),
                        max(24.0, float(metrics.horizontalAdvance(item_ref.text) + 8)),
                        max(16.0, float(metrics.height() + 4)),
                    )
                else:
                    item_ref.stroke_width = max(1, int(width))
                self.canvas._recompose(notify=True)

    def _on_zoom_changed(self, _factor: float) -> None:
        self._update_info_label()

    def _on_color_sampled(self, color: QColor) -> None:
        if color.isValid():
            self._user_picked_color = True
            self.lbl_tool_hint.setText(f"💧 Sampled {color.name().upper()}")
            self.select_tool("pen")

    def _prompt_for_text(
        self, title: str, label: str, initial_text: str = ""
    ) -> Optional[str]:
        dlg = QInputDialog(self)
        dlg.setWindowTitle(title)
        dlg.setLabelText(label)
        dlg.setTextValue(initial_text)
        dlg.setWindowFlags(dlg.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        dlg.setStyleSheet(self.styleSheet())
        if dlg.exec() == QDialog.DialogCode.Accepted:
            return dlg.textValue()
        return None

    def prompt_and_add_text(self, text: Optional[str] = None) -> bool:
        """Prompts for text via dialog (or uses text directly) and places a movable/resizable text box."""
        chosen = (
            text
            if text is not None
            else self._prompt_for_text("📝 Add Text", "Enter text to add:")
        )
        if chosen and chosen.strip():
            return self.add_text_annotation(
                self.canvas.get_visible_image_center(),
                chosen,
                center_on_point=True,
            )
        return False

    def _on_edit_text_item(self, idx: int) -> bool:
        if not (0 <= idx < len(self.canvas._items)):
            return False
        target = self.canvas._items[idx]
        if target.kind != "text":
            return False
        updated = self._prompt_for_text(
            "🔤 Edit Text", "Update text:", initial_text=target.text
        )
        if updated is not None and updated.strip() and updated.strip() != target.text:
            clean = updated.strip()
            self._push_undo_state()
            item_ref = self.canvas._items[idx]
            item_ref.text = clean
            font = QFont("Segoe UI", -1, QFont.Weight.Bold)
            font.setPixelSize(item_ref.font_px)
            metrics = QFontMetrics(font)
            item_ref.rect = QRectF(
                item_ref.rect.left(),
                item_ref.rect.top(),
                max(24.0, float(metrics.horizontalAdvance(clean) + 8)),
                max(item_ref.rect.height(), float(metrics.height() + 4)),
            )
            self.canvas._recompose(notify=True)
            self.lbl_tool_hint.setText(f'🔤 Updated text "{clean[:24]}"')
            return True
        return False

    def _on_canvas_text_requested(self, img_pt: QPoint) -> None:
        text = self._prompt_for_text(
            "🔤 Add Text Annotation", "Enter text to place on image:"
        )
        if text and text.strip():
            self.add_text_annotation(img_pt, text)

    def add_text_annotation(
        self,
        img_pt: QPoint,
        text: str,
        color: Optional[QColor] = None,
        font_px: Optional[int] = None,
        center_on_point: bool = False,
    ) -> bool:
        clean = str(text or "").strip()
        if not clean or self._working_image.isNull():
            return False
        self._push_undo_state()
        draw_color = QColor(color or self.canvas.pen_color)
        draw_color.setAlpha(255)
        px_size = max(14, int(font_px or max(14, self.canvas.pen_width * 5)))

        font = QFont("Segoe UI", -1, QFont.Weight.Bold)
        font.setPixelSize(px_size)
        metrics = QFontMetrics(font)
        box_w = max(24.0, float(metrics.horizontalAdvance(clean) + 8))
        box_h = max(16.0, float(metrics.height() + 4))
        if center_on_point:
            max_x = max(0.0, float(self._working_image.width()) - box_w)
            max_y = max(0.0, float(self._working_image.height()) - box_h)
            left = max(0.0, min(max_x, float(img_pt.x()) - box_w / 2.0))
            top = max(0.0, min(max_y, float(img_pt.y()) - box_h / 2.0))
        else:
            left = float(img_pt.x())
            top = float(img_pt.y() - metrics.ascent())

        item = _AnnotationItem(
            kind="text",
            color=draw_color,
            stroke_width=self.canvas.pen_width,
            rect=QRectF(left, top, box_w, box_h),
            text=clean,
            font_px=px_size,
        )
        self.canvas.add_item(item, select=True)
        self._working_image = self.canvas.get_image()
        self._update_info_label()
        self.lbl_tool_hint.setText(f'🔤 Placed text "{clean[:24]}" — drag to move/resize')
        return True

    def pixelate_region(self, rect: QRect, block_size: int = 10) -> bool:
        """Pixelates/redacts the given rectangular image region (supports Ctrl+Z undo)."""
        cur_img = self.canvas.get_image()
        bounded = QRect(rect).normalized().intersected(cur_img.rect())
        if bounded.width() < 4 or bounded.height() < 4:
            return False
        self._push_undo_state()
        self.canvas.add_item(
            _AnnotationItem(kind="pixelate", rect=QRectF(bounded), block_size=block_size),
            select=True,
        )
        self._working_image = self.canvas.get_image()
        self._update_info_label()
        self.lbl_tool_hint.setText("🫧 Pixelated selected area")
        return True

    def _update_info_label(self) -> None:
        w, h = self.get_target_size()
        src_w = self._working_image.width()
        src_h = self._working_image.height()
        zoom_pct = int(round(self.canvas._zoom_factor * 100))
        self.lbl_info.setText(f"Note: {w} × {h} px  |  Full: {src_w} × {src_h} px • {zoom_pct}%")

    def _on_width_changed(self, val: int) -> None:
        if self._updating_spins:
            return
        if self.chk_aspect.isChecked():
            self._updating_spins = True
            try:
                new_h = max(16, min(self.MAX_DISPLAY_DIM, int(round(val / max(1e-6, self._aspect_ratio)))))
                self.spin_height.setValue(new_h)
            finally:
                self._updating_spins = False
        self._update_info_label()

    def _on_height_changed(self, val: int) -> None:
        if self._updating_spins:
            return
        if self.chk_aspect.isChecked():
            self._updating_spins = True
            try:
                new_w = max(16, min(self.MAX_DISPLAY_DIM, int(round(val * max(1e-6, self._aspect_ratio)))))
                self.spin_width.setValue(new_w)
            finally:
                self._updating_spins = False
        self._update_info_label()

    def _on_aspect_toggled(self, checked: bool) -> None:
        if checked:
            self._aspect_ratio = self.spin_width.value() / max(1, self.spin_height.value())

    def _apply_preset_color(self, hex_color: str) -> None:
        col = QColor(hex_color)
        if not col.isValid():
            return
        self._user_picked_color = True
        self.canvas.set_pen_color(col)
        sel = self.canvas.get_selected_item()
        if sel is not None and sel.kind not in ("pixelate",):
            self._push_undo_state()
            item_ref = self.canvas.get_selected_item()
            if item_ref is not None:
                item_ref.color = QColor(col)
                self.canvas._recompose(notify=True)
        elif self.canvas.tool_mode in ("crop", "eyedropper", "pixelate", "select"):
            self.select_tool("pen")
        self.lbl_tool_hint.setText(f"🎨 Color set to {col.name().upper()}")

    def _pick_draw_color(self) -> None:
        sidebar = None
        parent_w = self.parentWidget()
        while parent_w is not None:
            if hasattr(parent_w, "parent_sidebar"):
                sidebar = parent_w.parent_sidebar
                break
            parent_w = parent_w.parentWidget()
        chosen = _pick_color_positioned(
            self,
            self.canvas.pen_color,
            "Select Brush Color",
            sidebar=sidebar if not self.is_fullscreen_mode() else None,
            anchor_widget=self.btn_draw_color,
        )
        if chosen is not None and chosen.isValid():
            self._user_picked_color = True
            self.canvas.set_pen_color(chosen)
            sel = self.canvas.get_selected_item()
            if sel is not None and sel.kind not in ("pixelate",):
                self._push_undo_state()
                item_ref = self.canvas.get_selected_item()
                if item_ref is not None:
                    item_ref.color = QColor(chosen)
                    self.canvas._recompose(notify=True)
            elif self.canvas.tool_mode in ("crop", "eyedropper", "pixelate", "select"):
                self.select_tool("pen")

    def _on_delete_clicked(self) -> None:
        self.delete_requested = True
        self.accept()

    def set_target_size(
        self, width: int, height: Optional[int] = None, record_undo: bool = False
    ) -> None:
        if record_undo:
            self._push_undo_state()
        w = max(16, min(self.MAX_DISPLAY_DIM, int(width)))
        if height is None:
            h = max(16, min(self.MAX_DISPLAY_DIM, int(round(w / max(1e-6, self._aspect_ratio)))))
        else:
            h = max(16, min(self.MAX_DISPLAY_DIM, int(height)))
            self._aspect_ratio = w / max(1, h)
        self._updating_spins = True
        try:
            self.spin_width.setValue(w)
            self.spin_height.setValue(h)
        finally:
            self._updating_spins = False
        self._update_info_label()

    def apply_scale_preset(self, factor: float) -> None:
        self._push_undo_state()
        base_w = max(1, self._working_image.width())
        base_h = max(1, self._working_image.height())
        self.set_target_size(int(round(base_w * factor)), int(round(base_h * factor)))

    def fit_to_width(self, max_width: int = 280) -> None:
        self._push_undo_state()
        self.set_target_size(max_width)

    def rotate_image(self, degrees: int) -> None:
        self._push_undo_state()
        src = self.canvas.flatten_items()
        transform = QTransform().rotate(degrees)
        self._working_image = src.transformed(
            transform, Qt.TransformationMode.SmoothTransformation
        ).convertToFormat(QImage.Format.Format_ARGB32)
        cur_w, cur_h = self.get_target_size()
        if abs(degrees) % 180 == 90:
            self.set_target_size(cur_h, cur_w)
        else:
            self._aspect_ratio = cur_w / max(1, cur_h)
            self._update_info_label()
        self.canvas.set_image(self._working_image, clear_crop=True)

    def flip_image(self, horizontal: bool = True) -> None:
        self._push_undo_state()
        src = self.canvas.flatten_items()
        sx = -1 if horizontal else 1
        sy = 1 if horizontal else -1
        transform = QTransform().scale(sx, sy)
        self._working_image = src.transformed(
            transform, Qt.TransformationMode.SmoothTransformation
        ).convertToFormat(QImage.Format.Format_ARGB32)
        self.canvas.set_image(self._working_image, clear_crop=True)

    def crop_image(self, rect: QRect) -> bool:
        cur_img = self.canvas.get_image()
        bounded = rect.normalized().intersected(cur_img.rect())
        if bounded.width() < 4 or bounded.height() < 4:
            return False
        self._push_undo_state()
        src = self.canvas.flatten_items()
        prev_disp_w = self.spin_width.value()
        self._working_image = src.copy(bounded)
        self.canvas.set_image(self._working_image, clear_crop=True)
        if prev_disp_w <= 280 and bounded.width() > 280:
            disp_w = 280
            disp_h = max(16, int(round(bounded.height() * (280.0 / bounded.width()))))
            self._aspect_ratio = bounded.width() / max(1, bounded.height())
            self.set_target_size(disp_w, disp_h)
        else:
            self.set_target_size(bounded.width(), bounded.height())
        return True

    def crop_to_selection(self) -> bool:
        rect = self.canvas.get_crop_rect()
        if rect is None:
            return False
        return self.crop_image(rect)

    def apply_grayscale(self) -> None:
        self._push_undo_state()
        src = self.canvas.flatten_items()
        self._working_image = (
            src.convertToFormat(QImage.Format.Format_Grayscale8)
            .convertToFormat(QImage.Format.Format_ARGB32)
        )
        self.canvas.set_image(self._working_image, clear_crop=False)

    def apply_invert(self) -> None:
        self._push_undo_state()
        img = self.canvas.flatten_items().copy()
        img.invertPixels(QImage.InvertMode.InvertRgb)
        self._working_image = img
        self.canvas.set_image(self._working_image, clear_crop=False)

    def apply_brightness_boost(self, delta: int = 20) -> None:
        """Brightens and enhances image contrast cleanly (undoable via Ctrl+Z)."""
        cur_img = self.canvas.get_image()
        if cur_img.isNull():
            return
        self._push_undo_state()
        rgba = self.canvas.flatten_items().convertToFormat(QImage.Format.Format_RGBA8888)
        buf = bytearray(rgba.constBits())
        lut = bytes(
            max(0, min(255, int(round((c - 128) * 1.1 + 128 + delta))))
            for c in range(256)
        )
        buf[0::4] = bytes(buf[0::4]).translate(lut)
        buf[1::4] = bytes(buf[1::4]).translate(lut)
        buf[2::4] = bytes(buf[2::4]).translate(lut)
        adjusted = QImage(
            bytes(buf),
            rgba.width(),
            rgba.height(),
            rgba.bytesPerLine(),
            QImage.Format.Format_RGBA8888,
        )
        self._working_image = adjusted.convertToFormat(QImage.Format.Format_ARGB32).copy()
        self.canvas.set_image(self._working_image, clear_crop=False)

    def copy_image_to_clipboard(self) -> QImage:
        res = self.get_working_image()
        QApplication.clipboard().setImage(res)
        self.lbl_tool_hint.setText("📋 Copied image to clipboard")
        return res

    def export_image_to_file(self, file_path: Optional[str] = None) -> bool:
        chosen = file_path
        if chosen is None:
            chosen, _ = QFileDialog.getSaveFileName(
                self,
                "Save Edited Image",
                "edited_image.png",
                "PNG Image (*.png);;JPEG Image (*.jpg *.jpeg);;WebP (*.webp);;BMP (*.bmp)",
            )
        if not chosen:
            return False
        ok = self.get_working_image().save(str(chosen))
        if ok:
            self.lbl_tool_hint.setText(f"💾 Saved {Path(chosen).name}")
        return bool(ok)

    def replace_image(self, file_path: Optional[str] = None) -> bool:
        chosen = file_path
        if chosen is None:
            chosen, _ = QFileDialog.getOpenFileName(
                self,
                "Select Replacement Image",
                "",
                "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp);;All Files (*)",
            )
        if not chosen:
            return False
        loaded = QImage(str(chosen))
        if loaded.isNull():
            return False
        self._push_undo_state()
        self._working_image = loaded.convertToFormat(QImage.Format.Format_ARGB32)
        self.canvas.set_image(self._working_image, clear_crop=True)
        w = self._working_image.width()
        h = self._working_image.height()
        if w > 280:
            h = int(round(h * (280.0 / w)))
            w = 280
        self.set_target_size(w, h)
        return True

    def reset_image(self) -> None:
        if (
            self.canvas.get_image() != self._original_image
            or self.get_target_size() != (self._orig_w, self._orig_h)
        ):
            self._push_undo_state()
        self._working_image = self._original_image.copy()
        self.delete_requested = False
        self.select_tool("crop")
        self.canvas.set_image(self._working_image, clear_crop=True)
        self.canvas.reset_zoom()
        self.set_target_size(self._orig_w, self._orig_h)

    def get_target_size(self) -> Tuple[int, int]:
        return self.spin_width.value(), self.spin_height.value()

    def get_working_image(self) -> QImage:
        src = self.canvas.get_image()
        self._working_image = src
        return src.copy()

    def get_result_image(self, scale_to_display: bool = True) -> QImage:
        src = self.canvas.get_image()
        self._working_image = src
        if scale_to_display:
            w, h = self.get_target_size()
            if w != src.width() or h != src.height():
                return src.scaled(
                    w,
                    h,
                    Qt.AspectRatioMode.IgnoreAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
        return src.copy()

    def is_fullscreen_mode(self) -> bool:
        return bool(
            self.windowState()
            & (Qt.WindowState.WindowMaximized | Qt.WindowState.WindowFullScreen)
        )

    def toggle_fullscreen(self) -> bool:
        if self.is_fullscreen_mode():
            self.setWindowState(
                self.windowState()
                & ~(Qt.WindowState.WindowMaximized | Qt.WindowState.WindowFullScreen)
            )
            self.showNormal()
            self.resize(960, 640)
            screen = (
                self.screen()
                or QGuiApplication.screenAt(self.frameGeometry().center())
                or QGuiApplication.primaryScreen()
            )
            if screen is not None:
                avail = screen.availableGeometry()
                self.move(
                    avail.center().x() - self.width() // 2,
                    avail.center().y() - self.height() // 2,
                )
        else:
            self.setWindowState(
                self.windowState()
                | Qt.WindowState.WindowFullScreen
                | Qt.WindowState.WindowMaximized
            )
            self.showFullScreen()
        return self.is_fullscreen_mode()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._initial_fullscreen_applied:
            self._initial_fullscreen_applied = True
            if self.is_fullscreen_mode():
                primary = QGuiApplication.primaryScreen()
                screen = (
                    self.screen()
                    or (
                        QGuiApplication.screenAt(primary.geometry().center())
                        if primary is not None
                        else None
                    )
                    or primary
                )
                if screen is not None:
                    self.setGeometry(screen.geometry())

    def eventFilter(self, obj, event) -> bool:
        if obj is self.top_bar and event.type() == QEvent.Type.MouseButtonDblClick:
            if isinstance(event, QMouseEvent) and event.button() == Qt.MouseButton.LeftButton:
                self.toggle_fullscreen()
                event.accept()
                return True
        return super().eventFilter(obj, event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if (
            event.button() == Qt.MouseButton.LeftButton
            and event.position().toPoint().y() <= self.top_bar.geometry().bottom() + 6
        ):
            self.toggle_fullscreen()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class RichNoteEditor(QTextEdit):
    """WYSIWYG rich-text editor with image paste and interactive checklists."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._has_rich_formatting = False
        self._img_drag_start_pos: Optional[QPoint] = None
        self._img_drag_source_pos: Optional[int] = None
        self._img_drag_fmt: Optional[QTextImageFormat] = None
        self.setAcceptRichText(True)
        self.setTabStopDistance(28)

    def _find_parent_hub(self):
        ancestor = self.parentWidget()
        while ancestor is not None:
            if hasattr(ancestor, "active_tab_id") and hasattr(ancestor, "_run_with_pin_guard"):
                return ancestor
            ancestor = ancestor.parentWidget()
        return None

    def has_rich_content(self) -> bool:
        return self._has_rich_formatting or "<img " in self.toHtml().lower()

    def setPlainText(self, text: str) -> None:
        self._has_rich_formatting = False
        super().setPlainText(text)

    def setHtml(self, text: str) -> None:
        self._has_rich_formatting = bool((text or "").strip())
        _register_data_uri_images(self.document(), text or "")
        super().setHtml(text)

    def mark_rich_formatting(self) -> None:
        self._has_rich_formatting = True

    @staticmethod
    def _extract_image_from_mime(source: Optional[QMimeData]) -> Optional[QImage]:
        if source is not None:
            if source.hasImage():
                img_data = source.imageData()
                image: Optional[QImage] = None
                if isinstance(img_data, QImage):
                    image = img_data
                elif isinstance(img_data, QPixmap):
                    image = img_data.toImage()
                elif isinstance(img_data, (bytes, bytearray)):
                    image = QImage.fromData(bytes(img_data))
                if image is not None and not image.isNull():
                    return image

            if source.hasUrls():
                for url in source.urls():
                    if url.isLocalFile():
                        local_path = url.toLocalFile()
                        p = Path(local_path)
                        if p.suffix.lower() in _IMAGE_EXTS and p.is_file():
                            image = QImage(str(p))
                            if not image.isNull():
                                return image

            if source.hasText():
                candidate = source.text().strip().strip('"')
                if candidate and len(candidate) < 4096:
                    try:
                        p = Path(candidate)
                        if p.suffix.lower() in _IMAGE_EXTS and p.is_file():
                            image = QImage(str(p))
                            if not image.isNull():
                                return image
                    except OSError:
                        pass

        return None

    def canInsertFromMimeData(self, source: QMimeData) -> bool:
        if source is not None and (
            source.hasUrls()
            or source.hasImage()
            or self._extract_image_from_mime(source) is not None
        ):
            return True
        return super().canInsertFromMimeData(source)

    def insertFromMimeData(self, source: QMimeData) -> None:
        if source is None:
            return
        if source.hasUrls() and source.urls():
            urls = source.urls()
            has_local = any(u.isLocalFile() for u in urls)
            if has_local or not source.hasImage():
                for idx, url in enumerate(urls):
                    if url.isLocalFile():
                        p = Path(url.toLocalFile())
                        if p.suffix.lower() in _IMAGE_EXTS and p.is_file():
                            img = QImage(str(p))
                            if not img.isNull():
                                if idx > 0:
                                    self.textCursor().insertText("\n")
                                self.insert_image(img)
                                continue
                        if idx > 0:
                            self.textCursor().insertText("\n")
                        self.textCursor().insertText(str(p))
                    else:
                        raw_url = url.toString().strip()
                        if raw_url:
                            if idx > 0:
                                self.textCursor().insertText("\n")
                            self.textCursor().insertText(raw_url)
                return

        image = self._extract_image_from_mime(source)
        if image is None and source.hasImage():
            clip_img = QApplication.clipboard().image()
            if not clip_img.isNull():
                image = clip_img
        if image is not None and not image.isNull():
            self.insert_image(image)
            return
        super().insertFromMimeData(source)

    def paste_image_from_clipboard(self) -> str:
        """Paste an image from the system clipboard if present."""
        clipboard = QApplication.clipboard()
        image = self._extract_image_from_mime(clipboard.mimeData())
        if image is None:
            clip_img = clipboard.image()
            if not clip_img.isNull():
                image = clip_img
        if image is not None and not image.isNull():
            return self.insert_image(image)
        return ""

    @staticmethod
    def _encode_image_data_uri(image: QImage) -> str:
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buf, "PNG")
        b64 = base64.b64encode(bytes(buf.data())).decode("ascii")
        return f"data:image/png;base64,{b64}"

    def _find_image_at_cursor(
        self, cursor: QTextCursor
    ) -> Optional[Tuple[QTextCursor, QTextImageFormat]]:
        doc = self.document()
        char_count = doc.characterCount()

        if cursor.hasSelection() and abs(cursor.selectionEnd() - cursor.selectionStart()) == 1:
            start = min(cursor.selectionStart(), cursor.selectionEnd())
            if 0 <= start < char_count and doc.characterAt(start) == "\ufffc":
                probe = QTextCursor(doc)
                probe.setPosition(start)
                probe.movePosition(
                    QTextCursor.MoveOperation.Right,
                    QTextCursor.MoveMode.KeepAnchor,
                    1,
                )
                if probe.charFormat().isImageFormat():
                    return probe, probe.charFormat().toImageFormat()

        pos_idx = cursor.position()
        for cand in (pos_idx, pos_idx - 1):
            if 0 <= cand < char_count and doc.characterAt(cand) == "\ufffc":
                probe = QTextCursor(doc)
                probe.setPosition(cand)
                probe.movePosition(
                    QTextCursor.MoveOperation.Right,
                    QTextCursor.MoveMode.KeepAnchor,
                    1,
                )
                if probe.charFormat().isImageFormat():
                    return probe, probe.charFormat().toImageFormat()

        return None

    def _find_image_at_pos(
        self, pos: QPoint
    ) -> Optional[Tuple[QTextCursor, QTextImageFormat]]:
        pos_cursor = self.cursorForPosition(pos)
        found = self._find_image_at_cursor(pos_cursor)
        if found is not None:
            return found

        block = pos_cursor.block()
        if block.isValid():
            block_text = block.text()
            obj_indices = [i for i, ch in enumerate(block_text) if ch == "\ufffc"]
            if len(obj_indices) == 1 and not block_text.replace("\ufffc", "").strip():
                probe = QTextCursor(self.document())
                probe.setPosition(block.position() + obj_indices[0])
                probe.movePosition(
                    QTextCursor.MoveOperation.Right,
                    QTextCursor.MoveMode.KeepAnchor,
                    1,
                )
                if probe.charFormat().isImageFormat():
                    return probe, probe.charFormat().toImageFormat()
        return None

    def _find_image_strictly_at_pos(
        self, pos: QPoint
    ) -> Optional[Tuple[int, QTextCursor, QTextImageFormat]]:
        doc = self.document()
        char_count = doc.characterCount()
        pos_cursor = self.cursorForPosition(pos)
        pos_idx = pos_cursor.position()

        for cand in (pos_idx, pos_idx - 1):
            if 0 <= cand < char_count and doc.characterAt(cand) == "\ufffc":
                probe = QTextCursor(doc)
                probe.setPosition(cand)
                probe.movePosition(
                    QTextCursor.MoveOperation.Right,
                    QTextCursor.MoveMode.KeepAnchor,
                    1,
                )
                if not probe.charFormat().isImageFormat():
                    continue
                img_fmt = probe.charFormat().toImageFormat()
                img = self._get_image_for_format(img_fmt)
                img_w = (
                    int(round(img_fmt.width()))
                    if img_fmt.width() > 0
                    else (img.width() if img is not None else 32)
                )
                img_h = (
                    int(round(img_fmt.height()))
                    if img_fmt.height() > 0
                    else (img.height() if img is not None else 32)
                )
                c_left = QTextCursor(doc)
                c_left.setPosition(cand)
                c_right = QTextCursor(doc)
                c_right.setPosition(cand + 1)
                r_left = self.cursorRect(c_left)
                r_right = self.cursorRect(c_right)
                left_x = min(r_left.left(), r_right.left()) - 6
                right_x = max(r_left.right(), r_right.right(), r_left.left() + img_w) + 6
                bottom_y = max(r_left.bottom(), r_right.bottom()) + 6
                top_y = min(r_left.top(), r_right.top(), bottom_y - img_h) - 6
                if left_x <= pos.x() <= right_x and top_y <= pos.y() <= bottom_y:
                    return cand, probe, img_fmt
        return None

    def _get_image_for_format(self, img_fmt: QTextImageFormat) -> Optional[QImage]:
        name = img_fmt.name()
        if not name:
            return None
        res = self.document().resource(
            QTextDocument.ResourceType.ImageResource, QUrl(name)
        )
        if isinstance(res, QImage) and not res.isNull():
            return res
        if isinstance(res, QPixmap) and not res.isNull():
            return res.toImage()

        match = _DATA_URI_IMAGE_RE.search(name)
        if match:
            b64_payload = re.sub(r"\s+", "", match.group(1))
            try:
                raw = base64.b64decode(b64_payload, validate=False)
                img = QImage.fromData(raw)
                if not img.isNull():
                    self.document().addResource(
                        QTextDocument.ResourceType.ImageResource, QUrl(name), img
                    )
                    return img
            except Exception:
                return None
        return None

    def update_image_at_cursor(
        self,
        img_cursor: QTextCursor,
        new_image: QImage,
        width: Optional[int] = None,
        height: Optional[int] = None,
    ) -> str:
        """Replace the selected image at img_cursor while preserving full pixel definition."""
        if new_image.isNull():
            return ""
        final_w = int(width) if width is not None and width > 0 else new_image.width()
        final_h = int(height) if height is not None and height > 0 else new_image.height()
        stored = new_image

        data_uri = self._encode_image_data_uri(stored)
        self._has_rich_formatting = True
        self.document().addResource(
            QTextDocument.ResourceType.ImageResource, QUrl(data_uri), stored
        )
        new_fmt = QTextImageFormat()
        new_fmt.setName(data_uri)
        new_fmt.setWidth(float(final_w))
        new_fmt.setHeight(float(final_h))

        img_cursor.beginEditBlock()
        try:
            img_cursor.insertImage(new_fmt)
        finally:
            img_cursor.endEditBlock()
        self.setTextCursor(img_cursor)
        return data_uri

    @staticmethod
    def _decode_data_uri_image(data_uri: str) -> Optional[QImage]:
        match = _DATA_URI_IMAGE_RE.search(data_uri or "")
        if not match:
            return None
        b64_payload = re.sub(r"\s+", "", match.group(1))
        try:
            raw = base64.b64decode(b64_payload, validate=False)
        except Exception:
            return None
        img = QImage.fromData(raw)
        return img if not img.isNull() else None

    def insert_image_with_format(
        self,
        image: QImage,
        data_uri: str = "",
        width: Optional[int] = None,
        height: Optional[int] = None,
        at_position: Optional[int] = None,
    ) -> str:
        """Insert a QImage preserving explicit dimensions at target or current cursor."""
        if image.isNull():
            return ""
        final_uri = data_uri or self._encode_image_data_uri(image)
        self._has_rich_formatting = True
        self.document().addResource(
            QTextDocument.ResourceType.ImageResource, QUrl(final_uri), image
        )
        fmt = QTextImageFormat()
        fmt.setName(final_uri)
        final_w = int(width) if width is not None and width > 0 else image.width()
        final_h = int(height) if height is not None and height > 0 else image.height()
        fmt.setWidth(float(final_w))
        fmt.setHeight(float(final_h))

        if at_position is not None:
            max_pos = max(0, self.document().characterCount() - 1)
            cursor = QTextCursor(self.document())
            cursor.setPosition(max(0, min(int(at_position), max_pos)))
            cursor.insertImage(fmt)
            self.setTextCursor(cursor)
        else:
            self.textCursor().insertImage(fmt)
        return final_uri

    def move_image_within_note(
        self,
        source_char_pos: int,
        target_char_pos: int,
        copy_only: bool = False,
    ) -> bool:
        """Move (or copy when copy_only=True) an inline image within this document."""
        doc = self.document()
        char_count = doc.characterCount()
        if not (0 <= source_char_pos < char_count) or doc.characterAt(source_char_pos) != "\ufffc":
            return False

        src_cursor = QTextCursor(doc)
        src_cursor.setPosition(source_char_pos)
        src_cursor.movePosition(
            QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, 1
        )
        if not src_cursor.charFormat().isImageFormat():
            return False

        img_fmt = src_cursor.charFormat().toImageFormat()
        image = self._get_image_for_format(img_fmt)
        if image is None or image.isNull():
            return False

        w = int(round(img_fmt.width())) if img_fmt.width() > 0 else image.width()
        h = int(round(img_fmt.height())) if img_fmt.height() > 0 else image.height()
        data_uri = img_fmt.name() or self._encode_image_data_uri(image)
        doc.addResource(QTextDocument.ResourceType.ImageResource, QUrl(data_uri), image)

        new_fmt = QTextImageFormat()
        new_fmt.setName(data_uri)
        new_fmt.setWidth(float(w))
        new_fmt.setHeight(float(h))

        max_pos = max(0, char_count - 1)
        clamped_target = max(0, min(int(target_char_pos), max_pos))
        if not copy_only and clamped_target in (source_char_pos, source_char_pos + 1):
            return True

        edit_cursor = QTextCursor(doc)
        edit_cursor.beginEditBlock()
        try:
            if copy_only:
                edit_cursor.setPosition(clamped_target)
                edit_cursor.insertImage(new_fmt)
            elif clamped_target > source_char_pos:
                edit_cursor.setPosition(clamped_target)
                edit_cursor.insertImage(new_fmt)
                edit_cursor.setPosition(source_char_pos)
                edit_cursor.movePosition(
                    QTextCursor.MoveOperation.Right,
                    QTextCursor.MoveMode.KeepAnchor,
                    1,
                )
                edit_cursor.removeSelectedText()
            else:
                edit_cursor.setPosition(source_char_pos)
                edit_cursor.movePosition(
                    QTextCursor.MoveOperation.Right,
                    QTextCursor.MoveMode.KeepAnchor,
                    1,
                )
                edit_cursor.removeSelectedText()
                edit_cursor.setPosition(clamped_target)
                edit_cursor.insertImage(new_fmt)
        finally:
            edit_cursor.endEditBlock()

        self._has_rich_formatting = True
        self.setTextCursor(edit_cursor)
        return True

    @staticmethod
    def _exec_image_dialog(dlg: ImageEditDialog) -> int:
        return dlg.exec()

    def edit_image_at_cursor(
        self,
        img_cursor: Optional[QTextCursor] = None,
        img_fmt: Optional[QTextImageFormat] = None,
    ) -> bool:
        """Open ImageEditDialog for the target (or cursor) inline image."""
        if img_cursor is None or img_fmt is None:
            found = self._find_image_at_cursor(self.textCursor())
            if found is None:
                return False
            img_cursor, img_fmt = found

        image = self._get_image_for_format(img_fmt)
        if image is None or image.isNull():
            return False

        init_w = int(round(img_fmt.width())) if img_fmt.width() > 0 else image.width()
        init_h = int(round(img_fmt.height())) if img_fmt.height() > 0 else image.height()

        dlg = ImageEditDialog(
            image, initial_width=init_w, initial_height=init_h, parent=self
        )

        result_holder = {"accepted": False}

        def _run_dialog() -> None:
            if self._exec_image_dialog(dlg) == QDialog.DialogCode.Accepted:
                result_holder["accepted"] = True

        ancestor = self.parentWidget()
        pin_guard = None
        while ancestor is not None:
            if hasattr(ancestor, "_run_with_pin_guard"):
                pin_guard = ancestor._run_with_pin_guard
                break
            ancestor = ancestor.parentWidget()

        if pin_guard is not None:
            pin_guard(_run_dialog)
        else:
            _run_dialog()

        if not result_holder["accepted"]:
            return False

        if dlg.delete_requested:
            img_cursor.beginEditBlock()
            try:
                img_cursor.removeSelectedText()
            finally:
                img_cursor.endEditBlock()
            self.setTextCursor(img_cursor)
            return True

        target_w, target_h = dlg.get_target_size()
        self.update_image_at_cursor(
            img_cursor, dlg.get_working_image(), target_w, target_h
        )
        return True

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        self._img_drag_start_pos = None
        if event.button() == Qt.MouseButton.LeftButton:
            found = self._find_image_at_pos(event.position().toPoint())
            if found is not None:
                img_cursor, img_fmt = found
                self.setTextCursor(img_cursor)
                self.edit_image_at_cursor(img_cursor, img_fmt)
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event) -> None:
        menu = self.createStandardContextMenu()
        found_img = (
            self._find_image_at_pos(event.pos())
            or self._find_image_at_cursor(self.textCursor())
        )
        clipboard = QApplication.clipboard()
        has_clip_img = (
            self._extract_image_from_mime(clipboard.mimeData()) is not None
            or not clipboard.image().isNull()
        )
        if found_img is not None or has_clip_img:
            menu.addSeparator()
        if found_img is not None:
            img_cursor, img_fmt = found_img
            act_edit_img = menu.addAction("Edit / Resize Image...")
            act_edit_img.triggered.connect(
                lambda checked=False, c=QTextCursor(img_cursor), f=QTextImageFormat(
                    img_fmt
                ): self.edit_image_at_cursor(c, f)
            )
            hub = self._find_parent_hub()
            if hub is not None and hasattr(hub, "move_image_to_tab"):
                tabs = hub.db.get_note_tabs()
                other_tabs = [t for t in tabs if int(t["id"]) != hub.active_tab_id]
                if other_tabs:
                    move_menu = menu.addMenu("Move Image to Tab")
                    img_pos = min(img_cursor.selectionStart(), img_cursor.selectionEnd())
                    for idx, tab in enumerate(tabs):
                        tid = int(tab["id"])
                        if tid == hub.active_tab_id:
                            continue
                        tname = str(tab.get("tab_name", f"Tab {tid}"))
                        hint = f" (Ctrl+{idx + 1})" if idx < 9 else ""
                        act = move_menu.addAction(f"{tname}{hint}")
                        act.triggered.connect(
                            lambda checked=False, target_id=tid, p=img_pos, h=hub: h.move_image_to_tab(
                                target_id, source_char_pos=p
                            )
                        )
        if has_clip_img:
            act_paste_img = menu.addAction("Paste Image")
            act_paste_img.triggered.connect(self.paste_image_from_clipboard)

        menu.addSeparator()
        act_timestamp = menu.addAction("Insert Timestamp (Ctrl+Shift+T)")
        act_timestamp.triggered.connect(lambda: self.insert_timestamp())

        act_code = menu.addAction("Toggle Code Block (Ctrl+Shift+K)")
        act_code.triggered.connect(lambda: self.toggle_code_block())

        tpl_menu = menu.addMenu("Insert Template Variable")
        for tok, desc in (
            ("{{date}}", "{{date}} — Current Date"),
            ("{{time}}", "{{time}} — Current Time"),
            ("{{datetime}}", "{{datetime}} — Date & Time"),
            ("{{clipboard}}", "{{clipboard}} — Clipboard Text"),
        ):
            act_tok = tpl_menu.addAction(desc)
            act_tok.triggered.connect(
                lambda _chk=False, t=tok: self.insert_template_variable(t)
            )

        hub = self._find_parent_hub()
        if hub is not None and hasattr(hub, "export_active_note"):
            menu.addSeparator()
            act_export = menu.addAction("Export Note (.md / .html / .txt)...")
            act_export.triggered.connect(lambda: hub.export_active_note())
            act_import = menu.addAction("Import File into Note...")
            act_import.triggered.connect(lambda: hub.import_into_active_note())

        menu.exec(event.globalPos())

    def insert_timestamp(self, now: Optional[datetime] = None) -> str:
        """Inserts formatted timestamp at cursor position and returns it."""
        stamp = (now or datetime.now()).strftime("%Y-%m-%d %H:%M")
        self.textCursor().insertText(stamp)
        return stamp

    def insert_template_variable(self, token: str) -> str:
        """Inserts a dynamic template placeholder such as {{date}} at the cursor."""
        self.textCursor().insertText(token)
        return token

    def toggle_code_block(self) -> bool:
        """Toggles monospace dark code-block styling on selected or current paragraph(s)."""
        doc = self.document()
        cursor = self.textCursor()
        start_block_num = doc.findBlock(cursor.selectionStart()).blockNumber()
        end_block_num = doc.findBlock(cursor.selectionEnd()).blockNumber()

        first_block = doc.findBlockByNumber(start_block_num)
        bg_color = first_block.blockFormat().background().color().name().lower()
        enabling = bg_color != "#181526"

        blk_fmt = QTextBlockFormat()
        char_fmt = QTextCharFormat()
        if enabling:
            blk_fmt.setBackground(QColor("#181526"))
            blk_fmt.setLeftMargin(6)
            blk_fmt.setRightMargin(6)
            blk_fmt.setTopMargin(4)
            blk_fmt.setBottomMargin(4)
            char_fmt.setFontFamilies(["Consolas", "Courier New", "monospace"])
            char_fmt.setForeground(QColor("#F9E2AF"))
            self.mark_rich_formatting()
        else:
            blk_fmt.setBackground(QBrush(Qt.BrushStyle.NoBrush))
            blk_fmt.setLeftMargin(0)
            blk_fmt.setRightMargin(0)
            blk_fmt.setTopMargin(0)
            blk_fmt.setBottomMargin(0)
            char_fmt.setFontFamilies(["Consolas", "Segoe UI", "monospace"])
            char_fmt.setForeground(QColor("#CDD6F4"))

        edit_cur = QTextCursor(doc)
        edit_cur.beginEditBlock()
        try:
            for bnum in range(start_block_num, end_block_num + 1):
                blk = doc.findBlockByNumber(bnum)
                if not blk.isValid():
                    continue
                bcur = QTextCursor(blk)
                bcur.setBlockFormat(blk_fmt)
                bcur.movePosition(
                    QTextCursor.MoveOperation.EndOfBlock,
                    QTextCursor.MoveMode.KeepAnchor,
                )
                bcur.mergeCharFormat(char_fmt)
        finally:
            edit_cur.endEditBlock()
        self.mergeCurrentCharFormat(char_fmt)
        return enabling

    def insert_image(self, image: QImage) -> str:
        """Store image at full resolution (up to 3840px), display at <=280px width inline."""
        if image.isNull():
            return ""
        max_stored_dim = 3840
        stored = image
        if stored.width() > max_stored_dim or stored.height() > max_stored_dim:
            stored = stored.scaled(
                max_stored_dim,
                max_stored_dim,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        disp_w = stored.width()
        disp_h = stored.height()
        if disp_w > 280:
            disp_h = max(1, int(round(disp_h * (280.0 / disp_w))))
            disp_w = 280

        data_uri = self._encode_image_data_uri(stored)
        self._has_rich_formatting = True
        self.document().addResource(
            QTextDocument.ResourceType.ImageResource, QUrl(data_uri), stored
        )
        img_fmt = QTextImageFormat()
        img_fmt.setName(data_uri)
        img_fmt.setWidth(float(disp_w))
        img_fmt.setHeight(float(disp_h))
        self.textCursor().insertImage(img_fmt)
        return data_uri

    def toggle_checklist_selection(self) -> None:
        """Toggle ☐ / ☑ checklist prefix on selected or current line(s)."""
        doc = self.document()
        cursor = self.textCursor()
        start_block = doc.findBlock(cursor.selectionStart()).blockNumber()
        end_block = doc.findBlock(cursor.selectionEnd()).blockNumber()

        edit_cursor = QTextCursor(doc)
        edit_cursor.beginEditBlock()
        try:
            for block_num in range(start_block, end_block + 1):
                block = doc.findBlockByNumber(block_num)
                if not block.isValid():
                    continue
                block_text = block.text()
                line_cursor = QTextCursor(block)
                if block_text.startswith((_CHECK_UNCHECKED, _CHECK_CHECKED)):
                    line_cursor.movePosition(
                        QTextCursor.MoveOperation.Right,
                        QTextCursor.MoveMode.KeepAnchor,
                        2,
                    )
                    line_cursor.removeSelectedText()
                else:
                    line_cursor.insertText(_CHECK_UNCHECKED)
        finally:
            edit_cursor.endEditBlock()

    def toggle_checklist_at_line(self, block_number: int) -> bool:
        """Toggle between ☐ and ☑ at the beginning of the given block number."""
        block = self.document().findBlockByNumber(block_number)
        if not block.isValid():
            return False
        text = block.text()
        if text.startswith(_CHECK_UNCHECKED):
            replacement = "☑"
        elif text.startswith(_CHECK_CHECKED):
            replacement = "☐"
        else:
            return False

        cursor = QTextCursor(block)
        cursor.movePosition(
            QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, 1
        )
        cursor.insertText(replacement)
        return True

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            pos_cursor = self.cursorForPosition(event.position().toPoint())
            block = pos_cursor.block()
            if (
                block.isValid()
                and block.text().startswith((_CHECK_UNCHECKED, _CHECK_CHECKED))
                and pos_cursor.positionInBlock() <= 1
            ):
                self._img_drag_start_pos = None
                self.toggle_checklist_at_line(block.blockNumber())
                event.accept()
                return

            strict_hit = self._find_image_strictly_at_pos(event.position().toPoint())
            if strict_hit is not None:
                cand, img_cursor, img_fmt = strict_hit
                self._img_drag_start_pos = event.position().toPoint()
                self._img_drag_source_pos = cand
                self._img_drag_fmt = QTextImageFormat(img_fmt)
                self.setTextCursor(img_cursor)
                event.accept()
                return
            self._img_drag_start_pos = None
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if (
            (event.buttons() & Qt.MouseButton.LeftButton)
            and self._img_drag_start_pos is not None
            and self._img_drag_source_pos is not None
            and self._img_drag_fmt is not None
            and (event.position().toPoint() - self._img_drag_start_pos).manhattanLength()
            >= QApplication.startDragDistance()
        ):
            img_fmt = self._img_drag_fmt
            source_pos = self._img_drag_source_pos
            self._img_drag_start_pos = None
            image = self._get_image_for_format(img_fmt)
            if image is not None and not image.isNull():
                w = int(round(img_fmt.width())) if img_fmt.width() > 0 else image.width()
                h = int(round(img_fmt.height())) if img_fmt.height() > 0 else image.height()
                data_uri = img_fmt.name() or self._encode_image_data_uri(image)
                hub = self._find_parent_hub()
                payload = {
                    "data_uri": data_uri,
                    "width": w,
                    "height": h,
                    "source_char_pos": int(source_pos),
                    "source_tab_id": hub.active_tab_id if hub is not None else None,
                }
                mime = QMimeData()
                mime.setData(
                    _NOTE_IMAGE_MIME_TYPE, json.dumps(payload).encode("utf-8")
                )
                mime.setImageData(image)

                drag = QDrag(self)
                drag.setMimeData(mime)
                preview = QPixmap.fromImage(image).scaled(
                    96,
                    96,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                if not preview.isNull():
                    drag.setPixmap(preview)
                    drag.setHotSpot(QPoint(preview.width() // 2, preview.height() // 2))
                drag.exec(
                    Qt.DropAction.MoveAction | Qt.DropAction.CopyAction,
                    Qt.DropAction.MoveAction,
                )
                event.accept()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._img_drag_start_pos = None
        super().mouseReleaseEvent(event)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasFormat(_NOTE_IMAGE_MIME_TYPE):
            self.setTextCursor(self.cursorForPosition(event.position().toPoint()))
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasFormat(_NOTE_IMAGE_MIME_TYPE):
            self.setTextCursor(self.cursorForPosition(event.position().toPoint()))
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:
        if event.mimeData().hasFormat(_NOTE_IMAGE_MIME_TYPE):
            try:
                raw = bytes(event.mimeData().data(_NOTE_IMAGE_MIME_TYPE)).decode(
                    "utf-8", errors="ignore"
                )
                payload = json.loads(raw)
            except Exception:
                payload = {}

            drop_pos = self.cursorForPosition(event.position().toPoint()).position()
            copy_only = (
                bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
                or event.proposedAction() == Qt.DropAction.CopyAction
            )
            source_tab_id = payload.get("source_tab_id")
            source_char_pos = payload.get("source_char_pos")
            data_uri = str(payload.get("data_uri") or "")
            width = payload.get("width")
            height = payload.get("height")

            hub = self._find_parent_hub()
            cur_tab_id = hub.active_tab_id if hub is not None else None

            if (
                source_tab_id is not None
                and cur_tab_id is not None
                and int(source_tab_id) == int(cur_tab_id)
                and source_char_pos is not None
            ):
                self.move_image_within_note(
                    int(source_char_pos), drop_pos, copy_only=copy_only
                )
            else:
                img = self._decode_data_uri_image(data_uri)
                if img is None:
                    img = self._extract_image_from_mime(event.mimeData())
                if img is not None and not img.isNull():
                    self.insert_image_with_format(
                        img,
                        data_uri=data_uri,
                        width=int(width) if width else img.width(),
                        height=int(height) if height else img.height(),
                        at_position=drop_pos,
                    )
                    if (
                        not copy_only
                        and hub is not None
                        and source_tab_id is not None
                        and source_char_pos is not None
                    ):
                        hub._remove_image_from_tab_storage(
                            int(source_tab_id), int(source_char_pos), data_uri=data_uri
                        )
                        hub.save_timer.stop()
                        hub._save_active_note()
            event.acceptProposedAction()
            return
        super().dropEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if (
            event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
            and not (event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        ):
            cursor = self.textCursor()
            if not cursor.hasSelection():
                block = cursor.block()
                block_text = block.text()
                if block_text.startswith((_CHECK_UNCHECKED, _CHECK_CHECKED)):
                    if not block_text[2:].strip():
                        # Exit checklist mode when pressing Enter on an empty checklist item.
                        clear_cursor = QTextCursor(block)
                        clear_cursor.movePosition(
                            QTextCursor.MoveOperation.Right,
                            QTextCursor.MoveMode.KeepAnchor,
                            2,
                        )
                        clear_cursor.removeSelectedText()
                    else:
                        cursor.insertText(f"\n{_CHECK_UNCHECKED}")
                    event.accept()
                    return
        super().keyPressEvent(event)


class NoteHistoryDialog(QDialog):
    """Modal version browser allowing preview and restoration of saved note versions."""

    def __init__(
        self,
        history_rows: List[Dict],
        tab_name: str,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.history_rows = history_rows
        self.selected_history_id: Optional[int] = None
        self.setWindowTitle(f"Note History — {tab_name}")
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.setModal(True)
        self.resize(360, 380)

        self._setup_styles()
        self._build_ui()

    def _setup_styles(self) -> None:
        self.setStyleSheet(
            """
            QDialog {
                background-color: qlineargradient(
                    x1:0, y1:0, x2:0.4, y2:1,
                    stop:0 #1E1E2E, stop:0.6 #282039, stop:1 #34233E
                );
                color: #CDD6F4;
                font-family: 'Segoe UI', sans-serif;
            }
            QListWidget, QTextEdit {
                background-color: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #2A2D3E, stop:1 #342945
                );
                border: 1px solid #363A4F;
                border-radius: 6px;
                color: #CDD6F4;
                padding: 4px;
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
                background-color: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #F9E2AF, stop:0.5 #FAB387, stop:1 #F5C2E7
                );
                border-color: #CBA6F7;
                color: #1E1E2E;
            }
            """
        )

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        self.list_widget = QListWidget()
        for row in self.history_rows:
            preview = " ".join(str(row.get("content") or "").split())
            if len(preview) > 42:
                preview = preview[:41] + "…"
            if not preview and row.get("rich_content"):
                preview = "[Rich content / image]"
            ts = str(row.get("created_at") or "")
            item = QListWidgetItem(f"{ts}  |  {preview or '(empty)'}")
            item.setData(Qt.ItemDataRole.UserRole, dict(row))
            self.list_widget.addItem(item)
        self.list_widget.currentItemChanged.connect(self._on_selection_changed)
        root.addWidget(self.list_widget, 1)

        self.preview_edit = QTextEdit()
        self.preview_edit.setReadOnly(True)
        root.addWidget(self.preview_edit, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self.btn_restore = QPushButton("Restore Version")
        self.btn_restore.setEnabled(False)
        self.btn_restore.clicked.connect(self._on_restore)
        btn_row.addWidget(self.btn_restore)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.reject)
        btn_row.addWidget(btn_close)
        root.addLayout(btn_row)

        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

    def _on_selection_changed(self, current: Optional[QListWidgetItem], _prev) -> None:
        if current is None:
            self.btn_restore.setEnabled(False)
            self.preview_edit.clear()
            return
        data = current.data(Qt.ItemDataRole.UserRole) or {}
        rich = str(data.get("rich_content") or "")
        if rich.strip():
            _register_data_uri_images(self.preview_edit.document(), rich)
            self.preview_edit.setHtml(rich)
        else:
            self.preview_edit.setPlainText(str(data.get("content") or ""))
        self.btn_restore.setEnabled(True)

    def _on_restore(self) -> None:
        item = self.list_widget.currentItem()
        if item is None:
            return
        data = item.data(Qt.ItemDataRole.UserRole) or {}
        self.selected_history_id = int(data["id"])
        self.accept()


class DroppableNoteTabBtn(QToolButton):
    """Bottom note tab button accepting dragged images, external items, and hover switching."""

    def __init__(
        self,
        tab_id: int,
        on_image_dropped: Callable[[int, bytes, bool], None],
        on_drag_hover_switch: Callable[[int], None],
        on_external_dropped: Optional[Callable[[int, QMimeData], bool]] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.tab_id = int(tab_id)
        self._on_image_dropped = on_image_dropped
        self._on_drag_hover_switch = on_drag_hover_switch
        self._on_external_dropped = on_external_dropped
        self.setAcceptDrops(True)

        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.setInterval(350)
        self._hover_timer.timeout.connect(
            lambda: self._on_drag_hover_switch(self.tab_id)
        )

    @staticmethod
    def _is_droppable_mime(mime: Optional[QMimeData]) -> bool:
        if mime is None:
            return False
        if mime.hasFormat(_NOTE_IMAGE_MIME_TYPE):
            return True
        if mime.hasFormat(_SHORTCUT_MIME_TYPE) and not mime.hasUrls() and not mime.hasText():
            return False
        return bool(mime.hasUrls() or mime.hasText() or mime.hasImage())

    def dragEnterEvent(self, event) -> None:
        if self._is_droppable_mime(event.mimeData()):
            if not self._hover_timer.isActive():
                self._hover_timer.start()
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if self._is_droppable_mime(event.mimeData()):
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dragLeaveEvent(self, event) -> None:
        self._hover_timer.stop()
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:
        self._hover_timer.stop()
        if event.mimeData().hasFormat(_NOTE_IMAGE_MIME_TYPE):
            raw = bytes(event.mimeData().data(_NOTE_IMAGE_MIME_TYPE))
            copy_only = (
                bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
                or event.proposedAction() == Qt.DropAction.CopyAction
            )
            self._on_image_dropped(self.tab_id, raw, copy_only)
            event.acceptProposedAction()
            return
        if self._on_external_dropped is not None and self._is_droppable_mime(
            event.mimeData()
        ):
            self._on_drag_hover_switch(self.tab_id)
            self._on_external_dropped(self.tab_id, event.mimeData())
            event.acceptProposedAction()
            return
        super().dropEvent(event)


class PanelHub(QWidget):
    """Panel 1: 6-column Shortcut Grid (top) + Horizontal-Tab Notes Editor (bottom)."""

    GRID_COLUMNS = 6
    TILE_SIZE = 38
    TILE_ICON_SIZE = 22

    def __init__(self, db_manager, parent_sidebar):
        super().__init__(parent_sidebar)
        self.db = db_manager
        self.parent_sidebar = parent_sidebar
        self.current_query = ""
        self.grid_columns = self.GRID_COLUMNS
        self.auto_sort_usage = False
        self.active_tab_id: Optional[int] = None
        self._active_profile: str = getattr(self.db, "profile", "work")
        self._loading_note = False
        self._restoring_state = False
        self._last_highlight_color = QColor("#F9E2AF")
        self._last_flashed_shortcut_id: Optional[int] = None
        self._shortcut_buttons: Dict[int, QToolButton] = {}
        self._tab_buttons: Dict[int, tuple[QToolButton, str]] = {}
        self._tab_shortcuts: List[QShortcut] = []
        self._editor_shortcuts: List[QShortcut] = []

        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(500)
        self.save_timer.timeout.connect(self._save_active_note)

        self.setObjectName("PanelHub")
        self._setup_styles()
        self._build_ui()
        self._setup_shortcuts()
        self.restore_workspace_settings()
        self.refresh("")

    def _setup_styles(self) -> None:
        self.setStyleSheet(
            """
            QWidget#PanelHub {
                background-color: transparent;
                color: #CDD6F4;
            }
            QSplitter::handle {
                background-color: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #363A4F, stop:0.5 #584B70, stop:1 #363A4F
                );
                height: 3px;
                width: 3px;
                border-radius: 1px;
                margin: 2px 2px;
            }
            QSplitter::handle:hover {
                background-color: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #F9E2AF, stop:0.5 #FAB387, stop:1 #F38BA8
                );
            }
            QLabel#SectionTitle {
                color: #FAB387;
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 0.4px;
                text-transform: uppercase;
            }
            QLabel#EmptyHint {
                color: #A6ADC8;
                font-size: 12px;
                padding: 8px;
            }
            QPushButton#AddShortcutBtn {
                background-color: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #2A2D3E, stop:1 #352946
                );
                border: 1px solid #363A4F;
                border-radius: 5px;
                color: #CDD6F4;
                font-size: 14px;
                font-weight: 700;
                padding: 0px;
            }
            QPushButton#AddShortcutBtn:hover {
                background-color: #FAB387;
                border-color: #F9E2AF;
                color: #1E1E2E;
            }
            QPushButton#AddShortcutBtn:focus {
                border: 1px solid #FAB387;
            }
            QScrollArea#GridScroll {
                background-color: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #2A2D3E, stop:0.6 #2F2942, stop:1 #352946
                );
                border: 1px solid #363A4F;
                border-radius: 6px;
            }
            QWidget#GridContainer {
                background-color: transparent;
            }
            QToolButton#ShortcutTile {
                background-color: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #1E1E2E, stop:1 #2A2238
                );
                border: 1px solid #363A4F;
                border-radius: 6px;
                padding: 4px;
            }
            QToolButton#ShortcutTile:hover {
                background-color: #363A4F;
                border-color: #FAB387;
            }
            QToolButton#ShortcutTile:focus {
                border: 1px solid #FAB387;
            }
            QToolButton#ShortcutTile:pressed {
                background-color: #45375A;
            }
            QTextEdit#NoteEditor {
                background-color: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #2A2D3E, stop:0.6 #2F2942, stop:1 #352946
                );
                border: 1px solid #363A4F;
                border-radius: 6px;
                color: #CDD6F4;
                padding: 8px;
                font-family: 'Consolas', 'Segoe UI', monospace;
                font-size: 12px;
                selection-background-color: #FAB387;
                selection-color: #1E1E2E;
            }
            QTextEdit#NoteEditor:focus {
                border-color: #FAB387;
            }
            QPushButton#FmtBtn, QPushButton#ActionPillBtn, QPushButton#AutoSortBtn {
                background-color: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #2A2D3E, stop:1 #342945
                );
                border: 1px solid #363A4F;
                border-radius: 5px;
                color: #CDD6F4;
                padding: 2px 7px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton#FmtBtn {
                padding: 0px;
                font-size: 12px;
            }
            QPushButton#FmtBtn:hover, QPushButton#ActionPillBtn:hover, QPushButton#AutoSortBtn:hover {
                background-color: #363A4F;
                border-color: #FAB387;
            }
            QPushButton#FmtBtn:focus, QPushButton#ActionPillBtn:focus, QPushButton#AutoSortBtn:focus {
                border: 1px solid #FAB387;
            }
            QPushButton#FmtBtn:checked, QPushButton#AutoSortBtn:checked {
                background-color: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #F9E2AF, stop:0.5 #FAB387, stop:1 #F38BA8
                );
                border-color: #CBA6F7;
                color: #1E1E2E;
            }
            QPushButton#FmtBtn:checked:focus, QPushButton#AutoSortBtn:checked:focus {
                border: 2px solid #F9E2AF;
            }
            QLabel#NoteTabLabel {
                color: #F9E2AF;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton#CopyAllBtn {
                background-color: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #2A2D3E, stop:1 #342945
                );
                border: 1px solid #363A4F;
                border-radius: 5px;
                color: #CDD6F4;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton#CopyAllBtn:hover {
                background-color: #FAB387;
                border-color: #F9E2AF;
                color: #1E1E2E;
            }
            QPushButton#CopyAllBtn:focus {
                border: 1px solid #FAB387;
            }
            QSlider#OpacitySlider::groove:horizontal {
                background-color: #2A2D3E;
                border: 1px solid #363A4F;
                height: 6px;
                border-radius: 3px;
            }
            QSlider#OpacitySlider::sub-page:horizontal {
                background-color: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #F9E2AF, stop:0.45 #FAB387, stop:0.75 #F38BA8, stop:1 #CBA6F7
                );
                border: 1px solid #FAB387;
                height: 6px;
                border-radius: 3px;
            }
            QSlider#OpacitySlider::handle:horizontal {
                background-color: #F9E2AF;
                border: 1px solid #FAB387;
                width: 12px;
                height: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }
            QSlider#OpacitySlider::handle:horizontal:hover {
                background-color: #FAB387;
                border-color: #F9E2AF;
            }
            QSlider#OpacitySlider::handle:horizontal:focus {
                border: 2px solid #F9E2AF;
            }
            QWidget#NoteRail {
                background-color: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #2A2D3E, stop:0.6 #2F2942, stop:1 #352946
                );
                border: 1px solid #363A4F;
                border-radius: 6px;
            }
            QToolButton#NoteTabBtn {
                background-color: transparent;
                border: 1px solid transparent;
                border-radius: 5px;
                padding: 2px;
            }
            QToolButton#NoteTabBtn:hover {
                background-color: #363A4F;
            }
            QToolButton#NoteTabBtn:focus {
                border: 1px solid #FAB387;
            }
            QToolButton#NoteTabBtn:checked {
                background-color: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #F9E2AF, stop:0.5 #FAB387, stop:1 #F38BA8
                );
                border-color: #CBA6F7;
            }
            QToolButton#NoteTabBtn:checked:focus {
                border: 2px solid #F9E2AF;
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

        self.btn_auto_sort = QPushButton("Usage")
        self.btn_auto_sort.setObjectName("AutoSortBtn")
        self.btn_auto_sort.setCheckable(True)
        self.btn_auto_sort.setFixedHeight(24)
        self.btn_auto_sort.setIcon(qta.icon("fa5s.sort-amount-down", color="#CDD6F4"))
        self.btn_auto_sort.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_auto_sort.setToolTip("Auto-sort shortcuts by launch frequency")
        self.btn_auto_sort.toggled.connect(self._on_auto_sort_toggled)
        grid_header.addWidget(self.btn_auto_sort)

        self.btn_add_shortcut = QPushButton("+")
        self.btn_add_shortcut.setObjectName("AddShortcutBtn")
        self.btn_add_shortcut.setFixedSize(24, 24)
        self.btn_add_shortcut.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add_shortcut.setToolTip("Add Shortcut (+)")
        self.btn_add_shortcut.clicked.connect(self._on_add_shortcut)
        grid_header.addWidget(self.btn_add_shortcut)
        top_layout.addLayout(grid_header)

        self.grid_scroll = DroppableGridScrollArea(
            on_external_drop=self.handle_external_shortcut_drop,
            on_drag_hover_state=self._set_grid_drop_highlight,
        )
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

        # === Bottom Section: WYSIWYG Notes Editor + Formatting Bar + Bottom Tab Bar ===
        bottom_widget = QWidget()
        bottom_widget.setMinimumHeight(180)
        bottom_layout = QVBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(0, 4, 0, 0)
        bottom_layout.setSpacing(6)

        fmt_toolbar = QHBoxLayout()
        fmt_toolbar.setSpacing(4)

        self.btn_bold = QPushButton("B")
        self.btn_bold.setObjectName("FmtBtn")
        self.btn_bold.setCheckable(True)
        self.btn_bold.setFixedSize(26, 24)
        self.btn_bold.setStyleSheet("font-weight: 800;")
        self.btn_bold.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_bold.setToolTip("Bold (Ctrl+B)")
        self.btn_bold.clicked.connect(self.toggle_bold)
        fmt_toolbar.addWidget(self.btn_bold)

        self.btn_italic = QPushButton("I")
        self.btn_italic.setObjectName("FmtBtn")
        self.btn_italic.setCheckable(True)
        self.btn_italic.setFixedSize(26, 24)
        self.btn_italic.setStyleSheet("font-style: italic;")
        self.btn_italic.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_italic.setToolTip("Italic (Ctrl+I)")
        self.btn_italic.clicked.connect(self.toggle_italic)
        fmt_toolbar.addWidget(self.btn_italic)

        self.btn_underline = QPushButton("U")
        self.btn_underline.setObjectName("FmtBtn")
        self.btn_underline.setCheckable(True)
        self.btn_underline.setFixedSize(26, 24)
        self.btn_underline.setStyleSheet("text-decoration: underline;")
        self.btn_underline.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_underline.setToolTip("Underline (Ctrl+U)")
        self.btn_underline.clicked.connect(self.toggle_underline)
        fmt_toolbar.addWidget(self.btn_underline)

        self.btn_color = QPushButton()
        self.btn_color.setObjectName("FmtBtn")
        self.btn_color.setFixedSize(26, 24)
        self.btn_color.setIcon(qta.icon("fa5s.palette", color="#89B4FA"))
        self.btn_color.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_color.setToolTip("Change Text Color (Ctrl+Shift+C)")
        self.btn_color.clicked.connect(lambda: self.apply_text_color())
        fmt_toolbar.addWidget(self.btn_color)

        self.btn_highlight = QPushButton("🖍️")
        self.btn_highlight.setObjectName("FmtBtn")
        self.btn_highlight.setFixedSize(26, 24)
        self.btn_highlight.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_highlight.setToolTip(
            "Highlight Text Color (Ctrl+Shift+H • Right-click to clear)"
        )
        self.btn_highlight.clicked.connect(lambda: self.apply_highlight_color())
        self.btn_highlight.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.btn_highlight.customContextMenuRequested.connect(
            lambda _pos: self.clear_highlight_color()
        )
        fmt_toolbar.addWidget(self.btn_highlight)

        self.btn_checklist = QPushButton()
        self.btn_checklist.setObjectName("FmtBtn")
        self.btn_checklist.setFixedSize(26, 24)
        self.btn_checklist.setIcon(qta.icon("fa5s.check-square", color="#CDD6F4"))
        self.btn_checklist.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_checklist.setToolTip("Toggle Checklist Item (☐ / ☑)")
        self.btn_checklist.clicked.connect(self.toggle_checklist)
        fmt_toolbar.addWidget(self.btn_checklist)

        self.btn_image = QPushButton()
        self.btn_image.setObjectName("FmtBtn")
        self.btn_image.setFixedSize(26, 24)
        self.btn_image.setIcon(qta.icon("fa5s.image", color="#CDD6F4"))
        self.btn_image.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_image.setToolTip("Insert Image...")
        self.btn_image.clicked.connect(lambda: self.insert_image_from_file())
        fmt_toolbar.addWidget(self.btn_image)

        fmt_toolbar.addStretch(1)

        self.btn_run_script = QPushButton("▶ Run")
        self.btn_run_script.setObjectName("ActionPillBtn")
        self.btn_run_script.setFixedHeight(24)
        self.btn_run_script.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_run_script.setToolTip(
            "Run Code — F5: Note | Ctrl+F5: Highlighted | Ctrl+Shift+F5: Highlighted → Clip Queue"
        )
        self.btn_run_script.clicked.connect(self.run_inline_script)
        fmt_toolbar.addWidget(self.btn_run_script)

        self.btn_history = QPushButton("History")
        self.btn_history.setObjectName("ActionPillBtn")
        self.btn_history.setFixedHeight(24)
        self.btn_history.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_history.setToolTip("View & restore saved note versions")
        self.btn_history.clicked.connect(self._on_open_history)
        fmt_toolbar.addWidget(self.btn_history)

        bottom_layout.addLayout(fmt_toolbar)

        self.note_editor = RichNoteEditor()
        self.note_editor.setObjectName("NoteEditor")
        self.note_editor.setPlaceholderText("Write rich notes, paste images, checklists, or run commands... (auto-saved)")
        self.note_editor.textChanged.connect(self._on_note_text_changed)
        self.note_editor.currentCharFormatChanged.connect(self._sync_format_buttons)
        from ui.sidebar_window import SunsetFadeOverlay

        self.note_tab_transition = SunsetFadeOverlay(self.note_editor)
        bottom_layout.addWidget(self.note_editor, 1)

        note_toolbar = QHBoxLayout()
        note_toolbar.setSpacing(6)

        self.lbl_note_tab = QLabel("Scratchpad")
        self.lbl_note_tab.setObjectName("NoteTabLabel")
        note_toolbar.addWidget(self.lbl_note_tab)
        note_toolbar.addStretch(1)

        self.lbl_opacity = QLabel("100%")
        self.lbl_opacity.setObjectName("NoteTabLabel")
        self.lbl_opacity.setMinimumWidth(34)
        self.lbl_opacity.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        note_toolbar.addWidget(self.lbl_opacity)

        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setObjectName("OpacitySlider")
        self.opacity_slider.setRange(40, 100)
        self.opacity_slider.setSingleStep(1)
        self.opacity_slider.setPageStep(5)
        self.opacity_slider.setValue(100)
        self.opacity_slider.setFixedWidth(86)
        self.opacity_slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self.opacity_slider.setToolTip("Sidebar Opacity (40% – 100%)")
        self.opacity_slider.valueChanged.connect(self._on_opacity_slider_changed)
        note_toolbar.addWidget(self.opacity_slider)

        self.btn_copy_all = QPushButton("Copy All")
        self.btn_copy_all.setObjectName("CopyAllBtn")
        self.btn_copy_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_copy_all.setToolTip("Copy entire note tab to clipboard")
        self.btn_copy_all.clicked.connect(self._on_copy_all)
        note_toolbar.addWidget(self.btn_copy_all)

        bottom_layout.addLayout(note_toolbar)

        self.rail_widget = QWidget()
        self.rail_widget.setObjectName("NoteRail")
        self.rail_widget.setFixedHeight(36)
        self.rail_layout = QHBoxLayout(self.rail_widget)
        self.rail_layout.setContentsMargins(6, 3, 6, 3)
        self.rail_layout.setSpacing(6)
        self.rail_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter)

        self.tab_button_group = QButtonGroup(self)
        self.tab_button_group.setExclusive(True)
        self.tab_button_group.idClicked.connect(self._on_note_tab_clicked)

        bottom_layout.addWidget(self.rail_widget)

        self.splitter.addWidget(top_widget)
        self.splitter.addWidget(bottom_widget)
        self.splitter.setSizes([155, 350])
        self.splitter.splitterMoved.connect(self._on_splitter_moved)
        root.addWidget(self.splitter, 1)

    def _splitter_state_key(self) -> str:
        if self.splitter.orientation() == Qt.Orientation.Horizontal:
            return "hub_splitter_horizontal"
        return "hub_splitter_vertical"

    def _apply_saved_splitter_sizes(self) -> None:
        horizontal = self.splitter.orientation() == Qt.Orientation.Horizontal
        default_sizes = [320, 680] if horizontal else [155, 350]
        key = self._splitter_state_key()
        saved = (
            self.db.get_workspace_setting(key, None)
            if hasattr(self.db, "get_workspace_setting")
            else None
        )
        if (
            isinstance(saved, list)
            and len(saved) == 2
            and all(isinstance(v, (int, float)) and int(v) > 0 for v in saved)
        ):
            self.splitter.setSizes([int(saved[0]), int(saved[1])])
        else:
            self.splitter.setSizes(default_sizes)

    def _on_splitter_moved(self, _pos: int, _index: int) -> None:
        if self._restoring_state or not hasattr(self.db, "set_workspace_setting"):
            return
        sizes = [int(v) for v in self.splitter.sizes()]
        if len(sizes) == 2 and sum(sizes) > 0:
            self.db.set_workspace_setting(self._splitter_state_key(), sizes)

    def restore_workspace_settings(self) -> None:
        """Restores per-profile PanelHub state from workspace_state."""
        if not hasattr(self.db, "get_workspace_setting"):
            return
        self._restoring_state = True
        try:
            saved_sort = bool(self.db.get_workspace_setting("auto_sort_usage", False))
            self.auto_sort_usage = saved_sort
            self.btn_auto_sort.blockSignals(True)
            self.btn_auto_sort.setChecked(saved_sort)
            self.btn_auto_sort.blockSignals(False)
            self.btn_auto_sort.setIcon(
                qta.icon(
                    "fa5s.sort-amount-down",
                    color="#1E1E2E" if saved_sort else "#CDD6F4",
                )
            )

            saved_tab = self.db.get_workspace_setting("active_tab_id", None)
            tabs = self.db.get_note_tabs()
            tab_ids = [int(t["id"]) for t in tabs]
            if isinstance(saved_tab, int) and saved_tab in tab_ids:
                self.active_tab_id = saved_tab
            elif tab_ids:
                self.active_tab_id = tab_ids[0]

            self._apply_saved_splitter_sizes()
        finally:
            self._restoring_state = False

    def flush_pending_save(self) -> None:
        """Flushes any debounced active note edit immediately to SQLite."""
        if self.save_timer.isActive():
            self.save_timer.stop()
            self._save_active_note()

    def set_dock_orientation(self, horizontal: bool) -> None:
        """Arranges shortcuts and notes horizontally (top/bottom dock) or vertically (left/right dock)."""
        target = Qt.Orientation.Horizontal if horizontal else Qt.Orientation.Vertical
        if self.splitter.orientation() != target:
            self.splitter.setOrientation(target)
        self._apply_saved_splitter_sizes()
        self.update_grid_columns_for_width()

    @classmethod
    def compute_grid_columns(cls, avail_width: int) -> int:
        return max(4, min(12, int((max(180, int(avail_width)) + 8) // 56)))

    def update_grid_columns_for_width(self, total_width: Optional[int] = None) -> int:
        """Recomputes shortcut grid column count (4-12) and reflows tiles if changed."""
        if total_width is not None:
            avail = int(total_width) - 24
        elif (
            self.parent_sidebar is not None
            and self.splitter.orientation() == Qt.Orientation.Vertical
        ):
            avail = int(getattr(self.parent_sidebar, "sidebar_width", 380)) - 24
        else:
            avail = max(332, self.grid_scroll.width() - 16)
        new_cols = self.compute_grid_columns(avail)
        if new_cols != self.grid_columns:
            self.grid_columns = new_cols
            self._refresh_shortcuts_grid()
        return self.grid_columns

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if (
            self.isVisible()
            and self.splitter.orientation() == Qt.Orientation.Vertical
            and self.width() > 0
        ):
            self.update_grid_columns_for_width(self.width() + 24)

    def refresh(self, search_query: str = "") -> None:
        self.current_query = search_query or ""
        current_profile = getattr(self.db, "profile", "work")
        profile_switched = current_profile != self._active_profile

        if profile_switched:
            # Avoid flushing previous profile's text into the newly selected DB.
            self.save_timer.stop()
            self._active_profile = current_profile
            self.active_tab_id = None
            self.restore_workspace_settings()
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

        cols = max(1, int(getattr(self, "grid_columns", self.GRID_COLUMNS)))
        self._shortcut_buttons.clear()
        shortcuts = self.db.get_shortcuts(
            self.current_query, sort_by_usage=self.auto_sort_usage
        )

        if not shortcuts:
            hint = QLabel(
                "No matching shortcuts"
                if self.current_query
                else "No shortcuts yet. Click + to add an app, folder, or URL."
            )
            hint.setObjectName("EmptyHint")
            hint.setWordWrap(True)
            self.grid_layout.addWidget(hint, 0, 0, 1, cols)
            return

        for idx, shortcut in enumerate(shortcuts):
            row = idx // cols
            col = idx % cols
            tile = self._create_shortcut_tile(shortcut)
            self._shortcut_buttons[int(shortcut["id"])] = tile
            self.grid_layout.addWidget(tile, row, col)

    def _create_shortcut_tile(self, shortcut: Dict) -> DraggableShortcutTile:
        sid = int(shortcut["id"])
        title = str(shortcut.get("title", ""))
        target = str(shortcut.get("target", ""))
        use_count = int(shortcut.get("use_count") or 0)

        btn = DraggableShortcutTile(
            sid,
            on_drop_reorder=self._reorder_shortcut_ids,
            on_external_drop=self.handle_external_shortcut_drop,
            on_drag_hover_state=self._set_grid_drop_highlight,
            parent=self.grid_container,
        )
        btn.setObjectName("ShortcutTile")
        btn.setFixedSize(self.TILE_SIZE, self.TILE_SIZE)
        btn.setIconSize(QSize(self.TILE_ICON_SIZE, self.TILE_ICON_SIZE))
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        btn.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        tip = f"{title}\n{target}" if title and target else (title or target)
        if use_count > 0:
            tip = f"{tip} ({use_count} uses)"
        btn.setToolTip(tip)
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

    def _on_auto_sort_toggled(self, checked: bool) -> None:
        self.auto_sort_usage = bool(checked)
        icon_color = "#1E1E2E" if self.auto_sort_usage else "#CDD6F4"
        self.btn_auto_sort.setIcon(qta.icon("fa5s.sort-amount-down", color=icon_color))
        if not self._restoring_state and hasattr(self.db, "set_workspace_setting"):
            self.db.set_workspace_setting("auto_sort_usage", self.auto_sort_usage)
        self._refresh_shortcuts_grid()

    def move_shortcut(self, from_index: int, to_index: int) -> bool:
        """Reorder a shortcut from from_index to to_index and persist sort_order."""
        shortcuts = self.db.get_shortcuts("", sort_by_usage=False)
        if not (0 <= from_index < len(shortcuts) and 0 <= to_index < len(shortcuts)):
            return False
        if from_index == to_index:
            return False

        ordered_ids = [int(s["id"]) for s in shortcuts]
        moved = ordered_ids.pop(from_index)
        ordered_ids.insert(to_index, moved)
        self.db.reorder_shortcuts(ordered_ids)

        if self.auto_sort_usage:
            self.btn_auto_sort.setChecked(False)
        else:
            self._refresh_shortcuts_grid()
        return True

    def _reorder_shortcut_ids(self, source_id: int, target_id: int) -> None:
        shortcuts = self.db.get_shortcuts("", sort_by_usage=False)
        id_list = [int(s["id"]) for s in shortcuts]
        if source_id not in id_list or target_id not in id_list:
            return
        self.move_shortcut(id_list.index(source_id), id_list.index(target_id))

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

        if "id" in shortcut:
            self.db.increment_shortcut_usage(int(shortcut["id"]))

        if category == "url" or target.startswith(("http://", "https://")):
            QDesktopServices.openUrl(QUrl(target))
        else:
            try:
                os.startfile(target)
            except Exception:
                QDesktopServices.openUrl(QUrl.fromLocalFile(target))

        if self.auto_sort_usage:
            self._refresh_shortcuts_grid()

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

    def _set_grid_drop_highlight(self, active: bool) -> None:
        if active:
            self.grid_scroll.setStyleSheet(
                "QScrollArea#GridScroll { "
                "background-color: qlineargradient("
                "x1:0, y1:0, x2:1, y2:1, stop:0 #2D263E, stop:1 #3E2A48); "
                "border: 2px dashed #89B4FA; border-radius: 6px; }"
            )
        else:
            self.grid_scroll.setStyleSheet("")

    def flash_shortcut_tile(self, shortcut_id: int) -> bool:
        """Briefly highlights a shortcut tile border to acknowledge add/duplicate drop."""
        sid = int(shortcut_id)
        self._last_flashed_shortcut_id = sid
        btn = self._shortcut_buttons.get(sid)
        if btn is None or not _qt_is_valid(btn):
            return False
        flash_qss = (
            "border: 2px solid #89B4FA; "
            "background-color: qlineargradient("
            "x1:0, y1:0, x2:1, y2:1, stop:0 #FAB387, stop:1 #F38BA8); "
            "border-radius: 6px;"
        )
        btn.setStyleSheet(flash_qss)
        QTimer.singleShot(
            700,
            lambda b=btn, q=flash_qss: self._clear_tile_flash(b, q),
        )
        return True

    @staticmethod
    def _clear_tile_flash(btn: QToolButton, expected_qss: str) -> None:
        if _qt_is_valid(btn) and btn.styleSheet() == expected_qss:
            btn.setStyleSheet("")

    def handle_external_shortcut_drop(
        self,
        mime: Optional[QMimeData],
        modifiers: Qt.KeyboardModifiers = Qt.KeyboardModifier.NoModifier,
    ) -> List[int]:
        """Handles external drops of files, folders, .lnk/.url shortcuts, and URLs."""
        candidates = extract_shortcut_candidates_from_mime(mime)
        if not candidates:
            return []

        existing = self.db.get_shortcuts("", sort_by_usage=False)
        existing_map: Dict[str, int] = {}
        for s in existing:
            norm = _normalize_shortcut_target(str(s.get("target", "")))
            if norm and norm not in existing_map:
                existing_map[norm] = int(s["id"])

        added_ids: List[int] = []
        duplicate_ids: List[int] = []
        shift_held = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)

        for title, target, category in candidates:
            norm_key = _normalize_shortcut_target(target)
            if norm_key and norm_key in existing_map:
                dup_id = existing_map[norm_key]
                if dup_id not in duplicate_ids:
                    duplicate_ids.append(dup_id)
                continue

            if shift_held:
                saved_id: Optional[int] = None

                def _open_edit_before_save(
                    t=title, tgt=target, cat=category
                ) -> None:
                    nonlocal saved_id
                    dlg = ShortcutDialog(
                        self, title=t, target=tgt, category=cat, is_edit=False
                    )
                    if dlg.exec() == QDialog.DialogCode.Accepted:
                        dlg_title, dlg_target, dlg_category = dlg.get_data()
                        if dlg_target:
                            edited_norm = _normalize_shortcut_target(dlg_target)
                            if edited_norm and edited_norm in existing_map:
                                dup = existing_map[edited_norm]
                                if dup not in duplicate_ids:
                                    duplicate_ids.append(dup)
                                return
                            new_sid = self.db.add_shortcut(
                                dlg_title, dlg_target, category=dlg_category
                            )
                            if new_sid != -1:
                                saved_id = int(new_sid)
                                if edited_norm:
                                    existing_map[edited_norm] = saved_id

                self._run_with_pin_guard(_open_edit_before_save)
                if saved_id is not None:
                    added_ids.append(saved_id)
            else:
                new_sid = self.db.add_shortcut(title, target, category=category)
                if new_sid != -1:
                    int_sid = int(new_sid)
                    added_ids.append(int_sid)
                    if norm_key:
                        existing_map[norm_key] = int_sid

        if added_ids:
            self._refresh_shortcuts_grid()
            for sid in added_ids:
                self.flash_shortcut_tile(sid)

        for dup_id in duplicate_ids:
            self.flash_shortcut_tile(dup_id)

        return added_ids

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

        matching_tids = set(self.get_matching_note_tab_ids(self.current_query))

        active_tab = None
        for idx, tab in enumerate(tabs):
            tid = int(tab["id"])
            icon_name = str(tab.get("icon_name", "fa5s.sticky-note"))
            tab_name = str(tab.get("tab_name", f"Tab {tid}"))
            is_active = tid == self.active_tab_id
            if is_active:
                active_tab = tab

            btn = DroppableNoteTabBtn(
                tid,
                on_image_dropped=self._on_image_dropped_on_tab,
                on_drag_hover_switch=self._on_note_tab_drag_hover,
                on_external_dropped=self._on_external_dropped_on_tab,
                parent=self.rail_widget,
            )
            btn.setObjectName("NoteTabBtn")
            btn.setCheckable(True)
            btn.setChecked(is_active)
            btn.setFixedSize(28, 28)
            btn.setIconSize(QSize(15, 15))
            btn.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            shortcut_hint = f" (Ctrl+{idx + 1})" if idx < 9 else ""
            match_hint = " — Search Match" if tid in matching_tids else ""
            btn.setToolTip(f"{tab_name}{shortcut_hint}{match_hint}")
            if is_active:
                icon_color = "#1E1E2E"
            elif tid in matching_tids:
                icon_color = "#FAB387"
            else:
                icon_color = "#A6ADC8"
            btn.setIcon(_safe_qta_icon(icon_name, icon_color))
            if tid in matching_tids and not is_active:
                btn.setStyleSheet(
                    "QToolButton#NoteTabBtn { "
                    "border: 1px solid #FAB387; "
                    "background-color: rgba(250, 179, 135, 0.20); "
                    "border-radius: 5px; }"
                )

            self.tab_button_group.addButton(btn, tid)
            self.rail_layout.addWidget(btn)
            self._tab_buttons[tid] = (btn, icon_name)

        if active_tab is not None:
            self.lbl_note_tab.setText(str(active_tab.get("tab_name", "Notes")))
            self._set_editor_content_silently(
                str(active_tab.get("content") or ""),
                str(active_tab.get("rich_content") or ""),
            )
        self._highlight_editor_search_matches(self.current_query)

    def get_matching_note_tab_ids(self, query: Optional[str] = None) -> List[int]:
        """Returns IDs of note tabs whose title or content matches query."""
        q = (self.current_query if query is None else query).strip()
        if not q or q.startswith("="):
            return []
        q_low = q.lower()
        tabs = self.db.get_note_tabs()
        matched: List[int] = []
        active_plain = self.note_editor.toPlainText() if hasattr(self, "note_editor") else ""
        for tab in tabs:
            tid = int(tab["id"])
            title = str(tab.get("tab_name") or "").lower()
            body = (
                active_plain
                if (self.active_tab_id is not None and tid == int(self.active_tab_id))
                else str(tab.get("content") or "")
            ).lower()
            if q_low in body or q_low in title:
                matched.append(tid)
        return matched

    def _highlight_editor_search_matches(self, query: str) -> int:
        """Highlights all case-insensitive occurrences of query inside note_editor."""
        q = (query or "").strip()
        if not q or q.startswith("="):
            self.note_editor.setExtraSelections([])
            return 0
        doc = self.note_editor.document()
        selections: List[QTextEdit.ExtraSelection] = []
        hl_fmt = QTextCharFormat()
        hl_fmt.setBackground(QColor("#FAB387"))
        hl_fmt.setForeground(QColor("#1E1E2E"))
        cursor = QTextCursor(doc)
        cursor.setPosition(0)
        while True:
            found = doc.find(q, cursor)
            if found.isNull():
                break
            sel = QTextEdit.ExtraSelection()
            sel.cursor = found
            sel.format = hl_fmt
            selections.append(sel)
            if found.selectionEnd() <= cursor.position():
                break
            cursor = found
        self.note_editor.setExtraSelections(selections)
        return len(selections)

    def cycle_note_search_match(self, query: Optional[str] = None) -> bool:
        """Jumps to the next matching search occurrence across all 9 Note Tabs."""
        q = (self.current_query if query is None else query).strip()
        if not q or q.startswith("="):
            return False
        matching_tids = self.get_matching_note_tab_ids(q)
        if not matching_tids:
            return False

        if self.active_tab_id in matching_tids:
            doc = self.note_editor.document()
            found_cursor = doc.find(q, self.note_editor.textCursor())
            if not found_cursor.isNull():
                self.note_editor.setTextCursor(found_cursor)
                return True
            if len(matching_tids) == 1:
                wrap_cursor = doc.find(q, 0)
                if not wrap_cursor.isNull():
                    self.note_editor.setTextCursor(wrap_cursor)
                return True
            next_idx = (matching_tids.index(self.active_tab_id) + 1) % len(matching_tids)
            target_tid = matching_tids[next_idx]
        else:
            target_tid = matching_tids[0]

        self._on_note_tab_drag_hover(target_tid)
        found = self.note_editor.document().find(q, 0)
        if not found.isNull():
            self.note_editor.setTextCursor(found)
        return True

    def _set_editor_text_silently(self, content: str) -> None:
        self._set_editor_content_silently(content, "")

    def _set_editor_content_silently(self, content: str, rich_content: str = "") -> None:
        if rich_content.strip():
            if self.note_editor.has_rich_content() and self.note_editor.toHtml() == rich_content:
                return
        elif not self.note_editor.has_rich_content() and self.note_editor.toPlainText() == content:
            return

        self._loading_note = True
        try:
            if rich_content.strip():
                self.note_editor.setHtml(rich_content)
            else:
                self.note_editor.setPlainText(content)
        finally:
            self._loading_note = False
            self._sync_format_buttons(self.note_editor.currentCharFormat())

    def _on_note_tab_clicked(self, tab_id: int) -> None:
        if tab_id == self.active_tab_id:
            return

        if self.save_timer.isActive():
            self.save_timer.stop()
            self._save_active_note()

        self.active_tab_id = tab_id
        if not self._restoring_state and hasattr(self.db, "set_workspace_setting"):
            self.db.set_workspace_setting("active_tab_id", int(tab_id))
        for tid, (btn, icon_name) in self._tab_buttons.items():
            is_active = tid == tab_id
            btn.setIcon(_safe_qta_icon(icon_name, "#1E1E2E" if is_active else "#A6ADC8"))

        tabs = {int(t["id"]): t for t in self.db.get_note_tabs()}
        selected = tabs.get(tab_id)
        if selected is not None:
            self.lbl_note_tab.setText(str(selected.get("tab_name", "Notes")))
            self._set_editor_content_silently(
                str(selected.get("content") or ""),
                str(selected.get("rich_content") or ""),
            )
        self._highlight_editor_search_matches(self.current_query)
        if not self._restoring_state and hasattr(self, "note_tab_transition"):
            self.note_tab_transition.trigger(140)

    def _on_note_tab_drag_hover(self, tab_id: int) -> None:
        btn_entry = self._tab_buttons.get(int(tab_id))
        if btn_entry is not None:
            btn_entry[0].setChecked(True)
        self._on_note_tab_clicked(int(tab_id))

    def _on_external_dropped_on_tab(
        self, target_tab_id: int, mime_data: Optional[QMimeData]
    ) -> bool:
        target_tid = int(target_tab_id)
        if mime_data is None or target_tid not in self._tab_buttons:
            return False
        if target_tid != self.active_tab_id:
            self._on_note_tab_drag_hover(target_tid)

        doc = self.note_editor.document()
        plain = self.note_editor.toPlainText()
        has_img = "<img " in self.note_editor.toHtml().lower()
        end_cursor = QTextCursor(doc)
        end_cursor.movePosition(QTextCursor.MoveOperation.End)
        if (plain.strip() or has_img) and not plain.endswith("\n"):
            end_cursor.insertText("\n")
        self.note_editor.setTextCursor(end_cursor)
        self.note_editor.insertFromMimeData(mime_data)
        self.save_timer.stop()
        self._save_active_note()
        return True

    def _append_image_to_active_editor(
        self, image: QImage, data_uri: str, width: int, height: int
    ) -> str:
        doc = self.note_editor.document()
        plain = self.note_editor.toPlainText()
        has_img = "<img " in self.note_editor.toHtml().lower()
        end_pos = max(0, doc.characterCount() - 1)
        end_cursor = QTextCursor(doc)
        end_cursor.setPosition(end_pos)
        if (plain.strip() or has_img) and not plain.endswith("\n"):
            end_cursor.insertText("\n")
            end_pos = max(0, doc.characterCount() - 1)
        return self.note_editor.insert_image_with_format(
            image, data_uri=data_uri, width=width, height=height, at_position=end_pos
        )

    def _remove_image_from_tab_storage(
        self, tab_id: int, source_char_pos: int, data_uri: str = ""
    ) -> bool:
        target_tid = int(tab_id)
        if target_tid == self.active_tab_id:
            doc = self.note_editor.document()
            if (
                0 <= source_char_pos < doc.characterCount()
                and doc.characterAt(source_char_pos) == "\ufffc"
            ):
                cur = QTextCursor(doc)
                cur.setPosition(source_char_pos)
                cur.movePosition(
                    QTextCursor.MoveOperation.Right,
                    QTextCursor.MoveMode.KeepAnchor,
                    1,
                )
                cur.removeSelectedText()
                self.save_timer.stop()
                self._save_active_note()
                return True
            return False

        tabs = {int(t["id"]): t for t in self.db.get_note_tabs()}
        tab = tabs.get(target_tid)
        if tab is None:
            return False
        rich = str(tab.get("rich_content") or "")
        plain = str(tab.get("content") or "")
        doc = QTextDocument()
        if rich.strip():
            _register_data_uri_images(doc, rich)
            doc.setHtml(rich)
        else:
            doc.setPlainText(plain)

        remove_pos: Optional[int] = None
        if (
            0 <= source_char_pos < doc.characterCount()
            and doc.characterAt(source_char_pos) == "\ufffc"
        ):
            probe = QTextCursor(doc)
            probe.setPosition(source_char_pos)
            probe.movePosition(
                QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, 1
            )
            if not data_uri or probe.charFormat().toImageFormat().name() == data_uri:
                remove_pos = source_char_pos

        if remove_pos is None:
            candidates = [
                idx
                for idx in range(doc.characterCount())
                if doc.characterAt(idx) == "\ufffc"
            ]
            if data_uri:
                for idx in candidates:
                    probe = QTextCursor(doc)
                    probe.setPosition(idx)
                    probe.movePosition(
                        QTextCursor.MoveOperation.Right,
                        QTextCursor.MoveMode.KeepAnchor,
                        1,
                    )
                    if probe.charFormat().toImageFormat().name() == data_uri:
                        remove_pos = idx
                        break
            if remove_pos is None and candidates:
                remove_pos = min(candidates, key=lambda idx: abs(idx - source_char_pos))

        if remove_pos is None:
            return False

        edit_cur = QTextCursor(doc)
        edit_cur.setPosition(remove_pos)
        edit_cur.movePosition(
            QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, 1
        )
        edit_cur.removeSelectedText()

        new_plain = doc.toPlainText()
        has_img = "<img " in doc.toHtml().lower()
        new_rich = "" if (not new_plain.strip() and not has_img) else (doc.toHtml() if rich.strip() else "")
        self.db.update_note_content(target_tid, new_plain, rich_content=new_rich)
        return True

    def move_image_to_tab(
        self,
        target_tab_id: int,
        source_char_pos: Optional[int] = None,
        copy_only: bool = False,
    ) -> bool:
        """Move (or copy) an inline image from the active note into target_tab_id."""
        target_tid = int(target_tab_id)
        if target_tid not in self._tab_buttons:
            return False

        doc = self.note_editor.document()
        if source_char_pos is not None:
            cand = int(source_char_pos)
            if not (0 <= cand < doc.characterCount()) or doc.characterAt(cand) != "\ufffc":
                return False
            img_cursor = QTextCursor(doc)
            img_cursor.setPosition(cand)
            img_cursor.movePosition(
                QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, 1
            )
            if not img_cursor.charFormat().isImageFormat():
                return False
            img_fmt = img_cursor.charFormat().toImageFormat()
        else:
            found = self.note_editor._find_image_at_cursor(self.note_editor.textCursor())
            if found is None:
                return False
            img_cursor, img_fmt = found
            cand = min(img_cursor.selectionStart(), img_cursor.selectionEnd())

        image = self.note_editor._get_image_for_format(img_fmt)
        if image is None or image.isNull():
            return False
        w = int(round(img_fmt.width())) if img_fmt.width() > 0 else image.width()
        h = int(round(img_fmt.height())) if img_fmt.height() > 0 else image.height()
        data_uri = img_fmt.name() or self.note_editor._encode_image_data_uri(image)

        if target_tid == self.active_tab_id:
            moved = self.note_editor.move_image_within_note(
                cand, max(0, doc.characterCount() - 1), copy_only=copy_only
            )
            if moved:
                self.save_timer.stop()
                self._save_active_note()
            return moved

        if not copy_only:
            img_cursor.beginEditBlock()
            try:
                img_cursor.removeSelectedText()
            finally:
                img_cursor.endEditBlock()

        self.save_timer.stop()
        self._save_active_note()

        btn_entry = self._tab_buttons.get(target_tid)
        if btn_entry is not None:
            btn_entry[0].setChecked(True)
        self._on_note_tab_clicked(target_tid)

        self._append_image_to_active_editor(image, data_uri, w, h)
        self.save_timer.stop()
        self._save_active_note()
        return True

    def _on_image_dropped_on_tab(
        self, target_tab_id: int, raw_payload: bytes, copy_only: bool = False
    ) -> bool:
        try:
            payload = json.loads(raw_payload.decode("utf-8", errors="ignore"))
        except Exception:
            return False

        target_tid = int(target_tab_id)
        if target_tid not in self._tab_buttons:
            return False

        source_tab_id = payload.get("source_tab_id")
        source_char_pos = payload.get("source_char_pos")
        data_uri = str(payload.get("data_uri") or "")
        width = payload.get("width")
        height = payload.get("height")

        if (
            source_tab_id is not None
            and int(source_tab_id) == self.active_tab_id
            and source_char_pos is not None
        ):
            return self.move_image_to_tab(
                target_tid, source_char_pos=int(source_char_pos), copy_only=copy_only
            )

        image = self.note_editor._decode_data_uri_image(data_uri)
        if image is None or image.isNull():
            return False

        if not copy_only and source_tab_id is not None and source_char_pos is not None:
            self._remove_image_from_tab_storage(
                int(source_tab_id), int(source_char_pos), data_uri=data_uri
            )

        if target_tid != self.active_tab_id:
            btn_entry = self._tab_buttons.get(target_tid)
            if btn_entry is not None:
                btn_entry[0].setChecked(True)
            self._on_note_tab_clicked(target_tid)

        w = int(width) if width else image.width()
        h = int(height) if height else image.height()
        self._append_image_to_active_editor(image, data_uri, w, h)
        self.save_timer.stop()
        self._save_active_note()
        return True

    def _on_note_text_changed(self) -> None:
        if self._loading_note or self.active_tab_id is None:
            return
        self.save_timer.start()

    def _save_active_note(self) -> None:
        if self.active_tab_id is None:
            return
        plain_text = self.note_editor.toPlainText()
        has_img = "<img " in self.note_editor.toHtml().lower()
        if not plain_text.strip() and not has_img:
            rich_html = ""
        elif self.note_editor.has_rich_content():
            rich_html = self.note_editor.toHtml()
        else:
            rich_html = ""
        self.db.update_note_content(
            self.active_tab_id,
            plain_text,
            rich_content=rich_html,
        )

    def _sync_format_buttons(self, fmt: QTextCharFormat) -> None:
        self.btn_bold.blockSignals(True)
        self.btn_italic.blockSignals(True)
        self.btn_underline.blockSignals(True)
        try:
            self.btn_bold.setChecked(fmt.fontWeight() >= QFont.Weight.Bold)
            self.btn_italic.setChecked(fmt.fontItalic())
            self.btn_underline.setChecked(fmt.fontUnderline())
        finally:
            self.btn_bold.blockSignals(False)
            self.btn_italic.blockSignals(False)
            self.btn_underline.blockSignals(False)

    def _merge_char_format(self, fmt: QTextCharFormat) -> None:
        self.note_editor.mark_rich_formatting()
        cursor = self.note_editor.textCursor()
        if not cursor.hasSelection():
            self.note_editor.mergeCurrentCharFormat(fmt)
        else:
            cursor.mergeCharFormat(fmt)
            self.note_editor.mergeCurrentCharFormat(fmt)
        self.note_editor.setFocus()
        self._sync_format_buttons(self.note_editor.currentCharFormat())
        if not self._loading_note and self.active_tab_id is not None:
            self.save_timer.start()

    def toggle_bold(self) -> None:
        """Toggle bold formatting on selection or future typing."""
        is_bold = self.note_editor.fontWeight() >= QFont.Weight.Bold
        fmt = QTextCharFormat()
        fmt.setFontWeight(QFont.Weight.Normal if is_bold else QFont.Weight.Bold)
        self._merge_char_format(fmt)

    def toggle_italic(self) -> None:
        """Toggle italic formatting on selection or future typing."""
        fmt = QTextCharFormat()
        fmt.setFontItalic(not self.note_editor.fontItalic())
        self._merge_char_format(fmt)

    def toggle_underline(self) -> None:
        """Toggle underline formatting on selection or future typing."""
        fmt = QTextCharFormat()
        fmt.setFontUnderline(not self.note_editor.fontUnderline())
        self._merge_char_format(fmt)

    def apply_text_color(self, color: Optional[QColor] = None) -> None:
        """Apply chosen foreground color (or open QColorDialog if omitted)."""
        chosen = color
        if chosen is None:
            initial = self.note_editor.textColor()
            def _pick() -> None:
                nonlocal chosen
                chosen = _pick_color_positioned(
                    self,
                    initial,
                    "Select Text Color",
                    sidebar=self.parent_sidebar,
                    anchor_widget=self.btn_color,
                )
            self._run_with_pin_guard(_pick)
        if chosen is not None and chosen.isValid():
            fmt = QTextCharFormat()
            fmt.setForeground(chosen)
            self._merge_char_format(fmt)

    def apply_highlight_color(self, color: Optional[QColor] = None) -> None:
        """Apply chosen highlight (background) color, or open QColorDialog if omitted."""
        chosen = color
        if chosen is None:
            bg_brush = self.note_editor.currentCharFormat().background()
            if (
                bg_brush.style() != Qt.BrushStyle.NoBrush
                and bg_brush.color().isValid()
                and bg_brush.color().alpha() > 0
            ):
                initial = bg_brush.color()
            else:
                initial = self._last_highlight_color

            def _pick() -> None:
                nonlocal chosen
                chosen = _pick_color_positioned(
                    self,
                    initial,
                    "Select Highlight Color",
                    sidebar=self.parent_sidebar,
                    anchor_widget=self.btn_highlight,
                )

            self._run_with_pin_guard(_pick)
        if chosen is not None and chosen.isValid():
            self._last_highlight_color = QColor(chosen)
            fmt = QTextCharFormat()
            fmt.setBackground(chosen)
            self._merge_char_format(fmt)

    def clear_highlight_color(self) -> None:
        """Remove background highlight color from selection or current typing format."""
        fmt = QTextCharFormat()
        fmt.setBackground(QBrush(Qt.BrushStyle.NoBrush))
        self._merge_char_format(fmt)

    def toggle_checklist(self) -> None:
        """Toggle checklist markers (☐ / ☑) on the selected or active line(s)."""
        self.note_editor.toggle_checklist_selection()
        self.note_editor.setFocus()

    def insert_image_from_file(self, file_path: Optional[str] = None) -> str:
        """Open file picker (or use given path) and embed the selected image inline."""
        chosen = file_path
        if chosen is None:
            def _pick() -> None:
                nonlocal chosen
                chosen, _ = QFileDialog.getOpenFileName(
                    self,
                    "Select Image",
                    "",
                    "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp);;All Files (*)",
                )

            self._run_with_pin_guard(_pick)

        if not chosen:
            return ""

        image = QImage(str(chosen))
        if image.isNull():
            return ""

        data_uri = self.note_editor.insert_image(image)
        self.note_editor.setFocus()
        if data_uri and not self._loading_note and self.active_tab_id is not None:
            self.save_timer.start()
        return data_uri

    def _execute_script_command(self, cmd: str) -> str:
        """Runs single-line or multi-line shell code and returns captured output."""
        cleaned = (cmd or "").strip()
        if not cleaned:
            return ""
        tmp_path: Optional[str] = None
        try:
            if "\n" in cleaned:
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".cmd", delete=False, encoding="utf-8"
                ) as tf:
                    tf.write("@echo off\r\n" + cleaned.replace("\n", "\r\n") + "\r\n")
                    tmp_path = tf.name
                proc = subprocess.run(
                    ["cmd", "/c", tmp_path],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
            else:
                proc = subprocess.run(
                    cleaned,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
            combined = "\n".join(
                part.rstrip()
                for part in (proc.stdout, proc.stderr)
                if part and part.strip()
            ).strip()
            if not combined:
                combined = (
                    f"[exit code {proc.returncode}]"
                    if proc.returncode != 0
                    else "(no output)"
                )
        except subprocess.TimeoutExpired:
            combined = "[Timed out after 10s]"
        except Exception as exc:
            combined = f"[Execution error: {exc}]"
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
        return combined

    def run_note_script(self) -> str:
        """Execute all code in the current Note (F5) and append output inline."""
        raw = self.note_editor.toPlainText()
        cmd = raw.split("\n>>> Output:\n", 1)[0].strip()
        if not cmd:
            return ""
        combined = self._execute_script_command(cmd)
        out_cursor = QTextCursor(self.note_editor.document())
        out_cursor.movePosition(QTextCursor.MoveOperation.End)
        out_cursor.insertText(f"\n>>> Output:\n{combined}", QTextCharFormat())
        self.note_editor.setTextCursor(out_cursor)

        self.save_timer.stop()
        self._save_active_note()
        return combined

    def run_highlighted_script(self, output_to_clip_queue_only: bool = False) -> str:
        """Execute highlighted/selected code (Ctrl+F5 to note, Ctrl+Shift+F5 to Clip Queue only)."""
        cursor = self.note_editor.textCursor()
        if not cursor.hasSelection():
            return ""
        cmd = cursor.selectedText().replace("\u2029", "\n").strip()
        if not cmd:
            return ""
        combined = self._execute_script_command(cmd)

        if output_to_clip_queue_only:
            source_type = (
                "url" if combined.startswith(("http://", "https://")) else "text"
            )
            if self.parent_sidebar is not None and hasattr(
                self.parent_sidebar, "on_new_clip_captured"
            ):
                self.parent_sidebar.on_new_clip_captured(combined, source_type)
            elif hasattr(self.db, "add_clip"):
                self.db.add_clip(combined, source_type)
            return combined

        insert_pos = cursor.selectionEnd()
        out_cursor = QTextCursor(self.note_editor.document())
        out_cursor.setPosition(insert_pos)
        out_cursor.insertText(f"\n>>> Output:\n{combined}", QTextCharFormat())
        self.note_editor.setTextCursor(out_cursor)

        self.save_timer.stop()
        self._save_active_note()
        return combined

    def run_inline_script(self) -> str:
        """Execute selected text or current line in shell and append output inline."""
        cursor = self.note_editor.textCursor()
        if cursor.hasSelection():
            return self.run_highlighted_script(output_to_clip_queue_only=False)
        cmd = cursor.block().text().strip()
        if not cmd:
            return ""
        cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
        insert_pos = cursor.position()
        combined = self._execute_script_command(cmd)

        out_cursor = QTextCursor(self.note_editor.document())
        out_cursor.setPosition(insert_pos)
        out_cursor.insertText(f"\n>>> Output:\n{combined}", QTextCharFormat())
        self.note_editor.setTextCursor(out_cursor)

        self.save_timer.stop()
        self._save_active_note()
        return combined

    def restore_note_from_history(self, history_id: int) -> bool:
        """Restore a historical snapshot by id and refresh editor contents."""
        restored = self.db.restore_note_version(history_id)
        if restored is None:
            return False
        if int(restored["id"]) == self.active_tab_id:
            self._set_editor_content_silently(
                str(restored.get("content") or ""),
                str(restored.get("rich_content") or ""),
            )
        else:
            self._refresh_note_tabs()
        return True

    def _on_open_history(self) -> None:
        if self.active_tab_id is None:
            return
        if self.save_timer.isActive():
            self.save_timer.stop()
            self._save_active_note()

        history_rows = self.db.get_note_history(self.active_tab_id)
        tab_name = self.lbl_note_tab.text()

        def _open_dialog() -> None:
            dlg = NoteHistoryDialog(history_rows, tab_name, self)
            if (
                dlg.exec() == QDialog.DialogCode.Accepted
                and dlg.selected_history_id is not None
            ):
                self.restore_note_from_history(dlg.selected_history_id)

        self._run_with_pin_guard(_open_dialog)

    def _on_copy_all(self) -> None:
        clipboard = QApplication.clipboard()
        prior_clip = clipboard.text()
        expanded = expand_note_template_variables(
            self.note_editor.toPlainText(), clipboard_text=prior_clip
        )
        clipboard.setText(expanded)
        self.btn_copy_all.setText("Copied!")
        QTimer.singleShot(800, self._restore_copy_all_label)

    def export_active_note(self, file_path: Optional[str] = None) -> bool:
        """Exports the active note tab to Markdown, HTML, or plain text."""
        self.flush_pending_save()
        chosen = file_path
        if chosen is None:
            default_name = f"{(self.lbl_note_tab.text() or 'note').strip()}.md"

            def _pick() -> None:
                nonlocal chosen
                chosen, _ = QFileDialog.getSaveFileName(
                    self,
                    "Export Note",
                    default_name,
                    "Markdown (*.md);;HTML (*.html);;Text (*.txt)",
                )

            self._run_with_pin_guard(_pick)

        if not chosen:
            return False
        dest = Path(chosen)
        payload = (
            self.note_editor.toHtml()
            if dest.suffix.lower() == ".html"
            else self.note_editor.toPlainText()
        )
        dest.write_text(payload, encoding="utf-8")
        return True

    def import_into_active_note(self, file_path: Optional[str] = None) -> bool:
        """Imports a .md, .txt, or .html file into the active note tab."""
        chosen = file_path
        if chosen is None:

            def _pick() -> None:
                nonlocal chosen
                chosen, _ = QFileDialog.getOpenFileName(
                    self,
                    "Import File into Note",
                    "",
                    "Notes (*.md *.txt *.html);;All Files (*)",
                )

            self._run_with_pin_guard(_pick)

        if not chosen:
            return False
        src = Path(chosen)
        if not src.is_file():
            return False
        raw = src.read_text(encoding="utf-8", errors="replace")
        if src.suffix.lower() == ".html" and "<" in raw:
            _register_data_uri_images(self.note_editor.document(), raw)
            if not self.note_editor.toPlainText().strip():
                self.note_editor.setHtml(raw)
            else:
                cur = self.note_editor.textCursor()
                cur.movePosition(QTextCursor.MoveOperation.End)
                cur.insertHtml(raw)
                self.note_editor.setTextCursor(cur)
        else:
            existing = self.note_editor.toPlainText()
            cur = self.note_editor.textCursor()
            cur.movePosition(QTextCursor.MoveOperation.End)
            prefix = "\n" if (existing.strip() and not existing.endswith("\n")) else ""
            cur.insertText(prefix + raw)
            self.note_editor.setTextCursor(cur)
        self.save_timer.stop()
        self._save_active_note()
        return True

    def _restore_copy_all_label(self) -> None:
        if _qt_is_valid(self) and _qt_is_valid(self.btn_copy_all):
            self.btn_copy_all.setText("Copy All")

    def sync_opacity_slider(self, percent: int) -> None:
        clamped = max(40, min(100, int(percent)))
        self.opacity_slider.blockSignals(True)
        self.opacity_slider.setValue(clamped)
        self.opacity_slider.blockSignals(False)
        self.lbl_opacity.setText(f"{clamped}%")

    def _on_opacity_slider_changed(self, value: int) -> None:
        clamped = max(40, min(100, int(value)))
        self.lbl_opacity.setText(f"{clamped}%")
        if (
            self.parent_sidebar is not None
            and hasattr(self.parent_sidebar, "set_sidebar_opacity")
        ):
            self.parent_sidebar.set_sidebar_opacity(clamped)
        else:
            win = self.window()
            if win is not None:
                win.setWindowOpacity(clamped / 100.0)

    def set_opacity_percent(self, percent: int) -> int:
        clamped = max(40, min(100, int(percent)))
        if self.opacity_slider.value() == clamped:
            self._on_opacity_slider_changed(clamped)
        else:
            self.opacity_slider.setValue(clamped)
        return clamped

    def _setup_shortcuts(self) -> None:
        self._tab_shortcuts.clear()
        for idx in range(9):
            shortcut = QShortcut(QKeySequence(f"Ctrl+{idx + 1}"), self)
            shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
            shortcut.setEnabled(self.isVisible())
            shortcut.activated.connect(lambda i=idx: self.switch_to_tab_index(i))
            self._tab_shortcuts.append(shortcut)

        self._editor_shortcuts.clear()
        for seq, handler in (
            ("Ctrl+B", self.toggle_bold),
            ("Ctrl+I", self.toggle_italic),
            ("Ctrl+U", self.toggle_underline),
            ("Ctrl+Shift+T", self.note_editor.insert_timestamp),
            ("Ctrl+Shift+K", self.note_editor.toggle_code_block),
            ("Ctrl+Shift+H", lambda: self.apply_highlight_color()),
            ("Ctrl+Shift+C", lambda: self.apply_text_color()),
            ("F5", self.run_note_script),
            ("Ctrl+F5", lambda: self.run_highlighted_script(False)),
            ("Ctrl+Shift+F5", lambda: self.run_highlighted_script(True)),
            ("Ctrl+Return", self.run_inline_script),
            ("Ctrl+Enter", self.run_inline_script),
        ):
            sc = QShortcut(QKeySequence(seq), self)
            sc.setContext(Qt.ShortcutContext.WindowShortcut)
            sc.setEnabled(self.isVisible())
            sc.activated.connect(handler)
            self._editor_shortcuts.append(sc)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        for shortcut in self._tab_shortcuts + self._editor_shortcuts:
            shortcut.setEnabled(True)

    def hideEvent(self, event) -> None:
        for shortcut in self._tab_shortcuts + self._editor_shortcuts:
            shortcut.setEnabled(False)
        super().hideEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        mods = event.modifiers() & (
            Qt.KeyboardModifier.ControlModifier
            | Qt.KeyboardModifier.ShiftModifier
            | Qt.KeyboardModifier.AltModifier
        )
        if (
            self.isVisible()
            and mods == Qt.KeyboardModifier.ControlModifier
            and Qt.Key.Key_1 <= event.key() <= Qt.Key.Key_9
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
