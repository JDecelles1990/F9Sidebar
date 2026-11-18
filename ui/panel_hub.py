import base64
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Callable, Dict, List, Optional, Tuple
import urllib.parse

from PySide6.QtCore import (
    QBuffer,
    QEvent,
    QFileInfo,
    QIODevice,
    QMimeData,
    QPoint,
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
    QGuiApplication,
    QIcon,
    QImage,
    QKeyEvent,
    QKeySequence,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
    QShortcut,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextImageFormat,
    QTransform,
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
            background-color: #1E1E2E;
            color: #CDD6F4;
            font-family: 'Segoe UI', sans-serif;
        }
        QLabel, QCheckBox, QRadioButton {
            color: #CDD6F4;
            font-size: 11px;
        }
        QLineEdit, QSpinBox {
            background-color: #2A2D3E;
            border: 1px solid #363A4F;
            border-radius: 4px;
            color: #CDD6F4;
            padding: 2px 4px;
        }
        QPushButton {
            background-color: #2A2D3E;
            border: 1px solid #363A4F;
            border-radius: 5px;
            color: #CDD6F4;
            padding: 4px 10px;
            font-size: 11px;
            font-weight: 600;
        }
        QPushButton:hover {
            background-color: #363A4F;
            border-color: #89B4FA;
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


class _ImagePreviewCanvas(QWidget):
    """Interactive image preview supporting crop marquee selection and freehand drawing."""

    def __init__(
        self,
        image: QImage,
        on_image_modified: Optional[Callable[[], None]] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._image = image
        self._on_image_modified = on_image_modified
        self._draw_mode = False
        self.pen_color = QColor("#F38BA8")
        self.pen_width = 3
        self._crop_rect: Optional[QRect] = None
        self._drag_origin_img: Optional[QPoint] = None
        self._last_draw_pt: Optional[QPoint] = None
        self.setMinimumSize(280, 180)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def set_image(self, image: QImage, clear_crop: bool = True) -> None:
        self._image = image
        if clear_crop:
            self._crop_rect = None
        self.update()

    def set_draw_mode(self, enabled: bool) -> None:
        self._draw_mode = bool(enabled)

    def set_pen_color(self, color: QColor) -> None:
        if color.isValid():
            self.pen_color = QColor(color)

    def get_crop_rect(self) -> Optional[QRect]:
        return self._crop_rect

    def clear_crop_rect(self) -> None:
        self._crop_rect = None
        self.update()

    def _image_target_rect(self) -> QRect:
        bounds = self.rect().adjusted(6, 6, -6, -6)
        if bounds.width() <= 0 or bounds.height() <= 0 or self._image.isNull():
            return QRect()
        scaled_size = self._image.size().scaled(
            bounds.size(), Qt.AspectRatioMode.KeepAspectRatio
        )
        x = bounds.x() + (bounds.width() - scaled_size.width()) // 2
        y = bounds.y() + (bounds.height() - scaled_size.height()) // 2
        return QRect(x, y, scaled_size.width(), scaled_size.height())

    def _widget_to_image_point(self, pt: QPoint) -> Optional[QPoint]:
        target = self._image_target_rect()
        if target.isEmpty() or self._image.isNull():
            return None
        rx = max(0.0, min(1.0, (pt.x() - target.x()) / max(1, target.width())))
        ry = max(0.0, min(1.0, (pt.y() - target.y()) / max(1, target.height())))
        ix = min(self._image.width() - 1, max(0, int(round(rx * self._image.width()))))
        iy = min(self._image.height() - 1, max(0, int(round(ry * self._image.height()))))
        return QPoint(ix, iy)

    def _image_rect_to_widget(self, img_rect: QRect) -> QRectF:
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

    def _draw_segment(self, start: QPoint, end: QPoint) -> None:
        if self._image.isNull():
            return
        painter = QPainter(self._image)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            pen = QPen(
                self.pen_color,
                self.pen_width,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            )
            painter.setPen(pen)
            if start == end:
                painter.drawPoint(start)
            else:
                painter.drawLine(start, end)
        finally:
            painter.end()
        self.update()
        if self._on_image_modified is not None:
            self._on_image_modified()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        try:
            painter.fillRect(self.rect(), QColor("#181825"))
            painter.setPen(QPen(QColor("#363A4F"), 1))
            painter.drawRect(self.rect().adjusted(0, 0, -1, -1))

            target = self._image_target_rect()
            if target.isEmpty() or self._image.isNull():
                return

            painter.fillRect(target, QColor("#2A2D3E"))
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            painter.drawImage(target, self._image)

            if self._crop_rect is not None and self._crop_rect.isValid():
                overlay = self._image_rect_to_widget(self._crop_rect)
                painter.setPen(QPen(QColor("#89B4FA"), 2, Qt.PenStyle.DashLine))
                painter.setBrush(QColor(137, 180, 250, 35))
                painter.drawRect(overlay)
        finally:
            painter.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            img_pt = self._widget_to_image_point(event.position().toPoint())
            if img_pt is not None:
                if self._draw_mode:
                    self._last_draw_pt = img_pt
                    self._draw_segment(img_pt, img_pt)
                else:
                    self._drag_origin_img = img_pt
                    self._crop_rect = None
                    self.update()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton:
            img_pt = self._widget_to_image_point(event.position().toPoint())
            if img_pt is not None:
                if self._draw_mode and self._last_draw_pt is not None:
                    self._draw_segment(self._last_draw_pt, img_pt)
                    self._last_draw_pt = img_pt
                elif not self._draw_mode and self._drag_origin_img is not None:
                    self._crop_rect = QRect(self._drag_origin_img, img_pt).normalized()
                    self.update()
                event.accept()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            img_pt = self._widget_to_image_point(event.position().toPoint())
            if self._draw_mode:
                if self._last_draw_pt is not None and img_pt is not None:
                    self._draw_segment(self._last_draw_pt, img_pt)
                self._last_draw_pt = None
            else:
                if self._drag_origin_img is not None and img_pt is not None:
                    rect = QRect(self._drag_origin_img, img_pt).normalized()
                    self._crop_rect = (
                        rect if rect.width() >= 4 and rect.height() >= 4 else None
                    )
                    self.update()
                self._drag_origin_img = None
            event.accept()
            return
        super().mouseReleaseEvent(event)


class ImageEditDialog(QDialog):
    """Modal editor to resize, rotate, flip, crop, filter, annotate, or delete an image."""

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
        self._orig_w = max(16, min(2400, int(initial_width or image.width() or 16)))
        self._orig_h = max(16, min(2400, int(initial_height or image.height() or 16)))
        self._aspect_ratio = self._orig_w / max(1, self._orig_h)
        self.delete_requested = False
        self._updating_spins = False

        self.setWindowTitle("Edit & Resize Image")
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowMinimizeButtonHint
        )
        self.setModal(True)
        self.setMinimumWidth(380)

        self._setup_styles()
        self._build_ui()
        self._update_info_label()

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
            QLabel#ImageMetaLabel {
                color: #A6ADC8;
                font-size: 11px;
                font-weight: 600;
            }
            QSpinBox {
                background-color: #2A2D3E;
                border: 1px solid #363A4F;
                border-radius: 5px;
                padding: 3px 6px;
                color: #CDD6F4;
                font-size: 12px;
            }
            QSpinBox:focus {
                border-color: #89B4FA;
            }
            QCheckBox {
                color: #CDD6F4;
                font-size: 12px;
                spacing: 6px;
            }
            QPushButton {
                background-color: #2A2D3E;
                border: 1px solid #363A4F;
                border-radius: 5px;
                color: #CDD6F4;
                padding: 4px 8px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #363A4F;
                border-color: #89B4FA;
            }
            QPushButton:checked {
                background-color: #89B4FA;
                border-color: #89B4FA;
                color: #1E1E2E;
            }
            QPushButton#DangerBtn {
                color: #F38BA8;
                border-color: #513544;
            }
            QPushButton#DangerBtn:hover {
                background-color: #F38BA8;
                border-color: #F38BA8;
                color: #1E1E2E;
            }
            QWidget#ImageDialogTopBar {
                background-color: #2A2D3E;
                border: 1px solid #363A4F;
                border-radius: 6px;
            }
            QLabel#ImageDialogTitle {
                color: #CDD6F4;
                font-size: 12px;
                font-weight: 700;
            }
            """
        )

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        self.top_bar = QWidget(self)
        self.top_bar.setObjectName("ImageDialogTopBar")
        self.top_bar.setFixedHeight(32)
        self.top_bar.installEventFilter(self)
        top_bar_layout = QHBoxLayout(self.top_bar)
        top_bar_layout.setContentsMargins(10, 4, 6, 4)
        top_bar_layout.setSpacing(6)

        self.lbl_title = QLabel("Edit & Resize Image")
        self.lbl_title.setObjectName("ImageDialogTitle")
        top_bar_layout.addWidget(self.lbl_title)
        top_bar_layout.addStretch(1)

        self.btn_fullscreen = QPushButton("⛶")
        self.btn_fullscreen.setFixedSize(24, 22)
        self.btn_fullscreen.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_fullscreen.setToolTip("Toggle Full Screen (Double-click top bar)")
        self.btn_fullscreen.clicked.connect(self.toggle_fullscreen)
        top_bar_layout.addWidget(self.btn_fullscreen)
        root.addWidget(self.top_bar)

        self.canvas = _ImagePreviewCanvas(
            self._working_image,
            on_image_modified=self._on_canvas_modified,
            parent=self,
        )
        root.addWidget(self.canvas, 1)

        info_row = QHBoxLayout()
        self.lbl_info = QLabel()
        self.lbl_info.setObjectName("ImageMetaLabel")
        info_row.addWidget(self.lbl_info)
        info_row.addStretch(1)
        hint = QLabel("Drag preview to select crop area")
        hint.setObjectName("ImageMetaLabel")
        info_row.addWidget(hint)
        root.addLayout(info_row)

        # Resize controls
        size_row = QHBoxLayout()
        size_row.setSpacing(6)
        size_row.addWidget(QLabel("W:"))
        self.spin_width = QSpinBox()
        self.spin_width.setRange(16, 2400)
        self.spin_width.setSuffix(" px")
        self.spin_width.setValue(self._orig_w)
        self.spin_width.valueChanged.connect(self._on_width_changed)
        size_row.addWidget(self.spin_width)

        size_row.addWidget(QLabel("H:"))
        self.spin_height = QSpinBox()
        self.spin_height.setRange(16, 2400)
        self.spin_height.setSuffix(" px")
        self.spin_height.setValue(self._orig_h)
        self.spin_height.valueChanged.connect(self._on_height_changed)
        size_row.addWidget(self.spin_height)

        self.chk_aspect = QCheckBox("Lock aspect ratio")
        self.chk_aspect.setChecked(True)
        self.chk_aspect.toggled.connect(self._on_aspect_toggled)
        size_row.addWidget(self.chk_aspect)
        size_row.addStretch(1)
        root.addLayout(size_row)

        # Size presets row
        preset_row = QHBoxLayout()
        preset_row.setSpacing(6)
        self.btn_scale_50 = QPushButton("50%")
        self.btn_scale_50.clicked.connect(lambda: self.apply_scale_preset(0.5))
        preset_row.addWidget(self.btn_scale_50)

        self.btn_scale_75 = QPushButton("75%")
        self.btn_scale_75.clicked.connect(lambda: self.apply_scale_preset(0.75))
        preset_row.addWidget(self.btn_scale_75)

        self.btn_scale_100 = QPushButton("100%")
        self.btn_scale_100.clicked.connect(lambda: self.apply_scale_preset(1.0))
        preset_row.addWidget(self.btn_scale_100)

        self.btn_fit_sidebar = QPushButton("Fit (280px)")
        self.btn_fit_sidebar.clicked.connect(lambda: self.fit_to_width(280))
        preset_row.addWidget(self.btn_fit_sidebar)
        preset_row.addStretch(1)
        root.addLayout(preset_row)

        # Transform & Crop row
        transform_row = QHBoxLayout()
        transform_row.setSpacing(6)
        self.btn_rotate_left = QPushButton("⟲ 90°")
        self.btn_rotate_left.clicked.connect(lambda: self.rotate_image(-90))
        transform_row.addWidget(self.btn_rotate_left)

        self.btn_rotate_right = QPushButton("⟳ 90°")
        self.btn_rotate_right.clicked.connect(lambda: self.rotate_image(90))
        transform_row.addWidget(self.btn_rotate_right)

        self.btn_flip_h = QPushButton("Flip H")
        self.btn_flip_h.clicked.connect(lambda: self.flip_image(horizontal=True))
        transform_row.addWidget(self.btn_flip_h)

        self.btn_flip_v = QPushButton("Flip V")
        self.btn_flip_v.clicked.connect(lambda: self.flip_image(horizontal=False))
        transform_row.addWidget(self.btn_flip_v)

        self.btn_crop = QPushButton("Crop")
        self.btn_crop.clicked.connect(self.crop_to_selection)
        transform_row.addWidget(self.btn_crop)
        transform_row.addStretch(1)
        root.addLayout(transform_row)

        # Filters, Annotate, Replace & Reset row
        tools_row = QHBoxLayout()
        tools_row.setSpacing(6)
        self.btn_grayscale = QPushButton("Grayscale")
        self.btn_grayscale.clicked.connect(self.apply_grayscale)
        tools_row.addWidget(self.btn_grayscale)

        self.btn_invert = QPushButton("Invert")
        self.btn_invert.clicked.connect(self.apply_invert)
        tools_row.addWidget(self.btn_invert)

        self.btn_draw = QPushButton("Draw")
        self.btn_draw.setCheckable(True)
        self.btn_draw.toggled.connect(self.canvas.set_draw_mode)
        tools_row.addWidget(self.btn_draw)

        self.btn_draw_color = QPushButton("Color")
        self.btn_draw_color.clicked.connect(self._pick_draw_color)
        tools_row.addWidget(self.btn_draw_color)

        self.btn_replace = QPushButton("Replace...")
        self.btn_replace.clicked.connect(lambda: self.replace_image())
        tools_row.addWidget(self.btn_replace)

        self.btn_reset = QPushButton("Reset")
        self.btn_reset.clicked.connect(self.reset_image)
        tools_row.addWidget(self.btn_reset)
        tools_row.addStretch(1)
        root.addLayout(tools_row)

        # Footer: Delete + OK/Cancel
        footer_row = QHBoxLayout()
        self.btn_delete = QPushButton("Delete Image")
        self.btn_delete.setObjectName("DangerBtn")
        self.btn_delete.clicked.connect(self._on_delete_clicked)
        footer_row.addWidget(self.btn_delete)
        footer_row.addStretch(1)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        footer_row.addWidget(self.button_box)
        root.addLayout(footer_row)

    def _on_canvas_modified(self) -> None:
        self._update_info_label()

    def _update_info_label(self) -> None:
        w, h = self.get_target_size()
        src_w = self._working_image.width()
        src_h = self._working_image.height()
        self.lbl_info.setText(f"{w} × {h} px  (source: {src_w} × {src_h})")

    def _on_width_changed(self, val: int) -> None:
        if self._updating_spins:
            return
        if self.chk_aspect.isChecked():
            self._updating_spins = True
            try:
                new_h = max(16, min(2400, int(round(val / max(1e-6, self._aspect_ratio)))))
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
                new_w = max(16, min(2400, int(round(val * max(1e-6, self._aspect_ratio)))))
                self.spin_width.setValue(new_w)
            finally:
                self._updating_spins = False
        self._update_info_label()

    def _on_aspect_toggled(self, checked: bool) -> None:
        if checked:
            self._aspect_ratio = self.spin_width.value() / max(1, self.spin_height.value())

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
            self.canvas.set_pen_color(chosen)
            if not self.btn_draw.isChecked():
                self.btn_draw.setChecked(True)

    def _on_delete_clicked(self) -> None:
        self.delete_requested = True
        self.accept()

    def set_target_size(self, width: int, height: Optional[int] = None) -> None:
        w = max(16, min(2400, int(width)))
        if height is None:
            h = max(16, min(2400, int(round(w / max(1e-6, self._aspect_ratio)))))
        else:
            h = max(16, min(2400, int(height)))
            self._aspect_ratio = w / max(1, h)
        self._updating_spins = True
        try:
            self.spin_width.setValue(w)
            self.spin_height.setValue(h)
        finally:
            self._updating_spins = False
        self._update_info_label()

    def apply_scale_preset(self, factor: float) -> None:
        base_w = max(1, self._working_image.width())
        base_h = max(1, self._working_image.height())
        self.set_target_size(int(round(base_w * factor)), int(round(base_h * factor)))

    def fit_to_width(self, max_width: int = 280) -> None:
        self.set_target_size(max_width)

    def rotate_image(self, degrees: int) -> None:
        transform = QTransform().rotate(degrees)
        self._working_image = self._working_image.transformed(
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
        sx = -1 if horizontal else 1
        sy = 1 if horizontal else -1
        transform = QTransform().scale(sx, sy)
        self._working_image = self._working_image.transformed(
            transform, Qt.TransformationMode.SmoothTransformation
        ).convertToFormat(QImage.Format.Format_ARGB32)
        self.canvas.set_image(self._working_image, clear_crop=True)

    def crop_image(self, rect: QRect) -> bool:
        bounded = rect.normalized().intersected(self._working_image.rect())
        if bounded.width() < 4 or bounded.height() < 4:
            return False
        self._working_image = self._working_image.copy(bounded)
        self.canvas.set_image(self._working_image, clear_crop=True)
        self.set_target_size(bounded.width(), bounded.height())
        return True

    def crop_to_selection(self) -> bool:
        rect = self.canvas.get_crop_rect()
        if rect is None:
            return False
        return self.crop_image(rect)

    def apply_grayscale(self) -> None:
        self._working_image = (
            self._working_image.convertToFormat(QImage.Format.Format_Grayscale8)
            .convertToFormat(QImage.Format.Format_ARGB32)
        )
        self.canvas.set_image(self._working_image, clear_crop=False)

    def apply_invert(self) -> None:
        img = self._working_image.copy()
        img.invertPixels(QImage.InvertMode.InvertRgb)
        self._working_image = img
        self.canvas.set_image(self._working_image, clear_crop=False)

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
        self._working_image = self._original_image.copy()
        self.delete_requested = False
        self.btn_draw.setChecked(False)
        self.canvas.set_image(self._working_image, clear_crop=True)
        self.set_target_size(self._orig_w, self._orig_h)

    def get_target_size(self) -> Tuple[int, int]:
        return self.spin_width.value(), self.spin_height.value()

    def get_result_image(self) -> QImage:
        w, h = self.get_target_size()
        if w != self._working_image.width() or h != self._working_image.height():
            return self._working_image.scaled(
                w,
                h,
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        return self._working_image.copy()

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
        else:
            self.setWindowState(self.windowState() | Qt.WindowState.WindowMaximized)
            self.showMaximized()
        return self.is_fullscreen_mode()

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
        """Replace the selected image at img_cursor with a resized/edited QImage."""
        if new_image.isNull():
            return ""
        final_w = int(width) if width is not None and width > 0 else new_image.width()
        final_h = int(height) if height is not None and height > 0 else new_image.height()
        scaled = new_image
        if final_w != new_image.width() or final_h != new_image.height():
            scaled = new_image.scaled(
                final_w,
                final_h,
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )

        data_uri = self._encode_image_data_uri(scaled)
        self._has_rich_formatting = True
        self.document().addResource(
            QTextDocument.ResourceType.ImageResource, QUrl(data_uri), scaled
        )
        new_fmt = QTextImageFormat()
        new_fmt.setName(data_uri)
        new_fmt.setWidth(float(scaled.width()))
        new_fmt.setHeight(float(scaled.height()))

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
            img_cursor, dlg.get_result_image(), target_w, target_h
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
        menu.exec(event.globalPos())

    def insert_image(self, image: QImage) -> str:
        """Scale image if wider than 280px, register resource, and insert inline."""
        if image.isNull():
            return ""
        max_width = 280
        if image.width() > max_width:
            image = image.scaledToWidth(
                max_width, Qt.TransformationMode.SmoothTransformation
            )
        data_uri = self._encode_image_data_uri(image)
        self._has_rich_formatting = True
        self.document().addResource(
            QTextDocument.ResourceType.ImageResource, QUrl(data_uri), image
        )
        img_fmt = QTextImageFormat()
        img_fmt.setName(data_uri)
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
                background-color: #1E1E2E;
                color: #CDD6F4;
                font-family: 'Segoe UI', sans-serif;
            }
            QListWidget, QTextEdit {
                background-color: #2A2D3E;
                border: 1px solid #363A4F;
                border-radius: 6px;
                color: #CDD6F4;
                padding: 4px;
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
                background-color: #89B4FA;
                border-color: #89B4FA;
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
                background-color: #1E1E2E;
                color: #CDD6F4;
            }
            QSplitter::handle {
                background-color: #363A4F;
                height: 3px;
                width: 3px;
                border-radius: 1px;
                margin: 2px 2px;
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
            QPushButton#AddShortcutBtn:focus {
                border: 1px solid #89B4FA;
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
            QToolButton#ShortcutTile:focus {
                border: 1px solid #89B4FA;
            }
            QToolButton#ShortcutTile:pressed {
                background-color: #45475A;
            }
            QTextEdit#NoteEditor {
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
            QTextEdit#NoteEditor:focus {
                border-color: #89B4FA;
            }
            QPushButton#FmtBtn, QPushButton#ActionPillBtn, QPushButton#AutoSortBtn {
                background-color: #2A2D3E;
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
                border-color: #89B4FA;
            }
            QPushButton#FmtBtn:focus, QPushButton#ActionPillBtn:focus, QPushButton#AutoSortBtn:focus {
                border: 1px solid #89B4FA;
            }
            QPushButton#FmtBtn:checked, QPushButton#AutoSortBtn:checked {
                background-color: #89B4FA;
                border-color: #89B4FA;
                color: #1E1E2E;
            }
            QPushButton#FmtBtn:checked:focus, QPushButton#AutoSortBtn:checked:focus {
                border: 2px solid #CDD6F4;
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
            QPushButton#CopyAllBtn:focus {
                border: 1px solid #89B4FA;
            }
            QSlider#OpacitySlider::groove:horizontal {
                background-color: #2A2D3E;
                border: 1px solid #363A4F;
                height: 6px;
                border-radius: 3px;
            }
            QSlider#OpacitySlider::sub-page:horizontal {
                background-color: #89B4FA;
                border: 1px solid #89B4FA;
                height: 6px;
                border-radius: 3px;
            }
            QSlider#OpacitySlider::handle:horizontal {
                background-color: #CDD6F4;
                border: 1px solid #89B4FA;
                width: 12px;
                height: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }
            QSlider#OpacitySlider::handle:horizontal:hover {
                background-color: #89B4FA;
                border-color: #CDD6F4;
            }
            QSlider#OpacitySlider::handle:horizontal:focus {
                border: 2px solid #CDD6F4;
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
                padding: 2px;
            }
            QToolButton#NoteTabBtn:hover {
                background-color: #363A4F;
            }
            QToolButton#NoteTabBtn:focus {
                border: 1px solid #89B4FA;
            }
            QToolButton#NoteTabBtn:checked {
                background-color: #89B4FA;
                border-color: #89B4FA;
            }
            QToolButton#NoteTabBtn:checked:focus {
                border: 2px solid #CDD6F4;
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
        self.btn_color.setToolTip("Change Text Color")
        self.btn_color.clicked.connect(lambda: self.apply_text_color())
        fmt_toolbar.addWidget(self.btn_color)

        self.btn_highlight = QPushButton("🖍️")
        self.btn_highlight.setObjectName("FmtBtn")
        self.btn_highlight.setFixedSize(26, 24)
        self.btn_highlight.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_highlight.setToolTip("Highlight Text Color (Right-click to clear highlight)")
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
        self.btn_run_script.setToolTip("Execute selected text or current line & capture output (Ctrl+Enter)")
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
            self.grid_layout.addWidget(hint, 0, 0, 1, self.GRID_COLUMNS)
            return

        for idx, shortcut in enumerate(shortcuts):
            row = idx // self.GRID_COLUMNS
            col = idx % self.GRID_COLUMNS
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
                "QScrollArea#GridScroll { background-color: #2A2D3E; "
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
            "border: 2px solid #89B4FA; background-color: #363A4F; border-radius: 6px;"
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
            btn.setToolTip(f"{tab_name}{shortcut_hint}")
            btn.setIcon(_safe_qta_icon(icon_name, "#1E1E2E" if is_active else "#A6ADC8"))

            self.tab_button_group.addButton(btn, tid)
            self.rail_layout.addWidget(btn)
            self._tab_buttons[tid] = (btn, icon_name)

        if active_tab is not None:
            self.lbl_note_tab.setText(str(active_tab.get("tab_name", "Notes")))
            self._set_editor_content_silently(
                str(active_tab.get("content") or ""),
                str(active_tab.get("rich_content") or ""),
            )

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

    def run_inline_script(self) -> str:
        """Execute selected text or current line in shell and append output inline."""
        cursor = self.note_editor.textCursor()
        if cursor.hasSelection():
            cmd = cursor.selectedText().replace("\u2029", "\n").strip()
            insert_pos = cursor.selectionEnd()
        else:
            cmd = cursor.block().text().strip()
            cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
            insert_pos = cursor.position()

        if not cmd:
            return ""

        try:
            proc = subprocess.run(
                cmd,
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
        QApplication.clipboard().setText(self.note_editor.toPlainText())
        self.btn_copy_all.setText("Copied!")
        QTimer.singleShot(800, self._restore_copy_all_label)

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
        if (
            self.isVisible()
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
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
