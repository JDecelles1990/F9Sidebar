import threading
from pathlib import Path
from typing import Callable, Dict, Optional
import urllib.parse
import urllib.request

from PySide6.QtCore import QFileInfo, QObject, QRunnable, QThreadPool, Qt, Signal
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import QFileIconProvider
import qtawesome as qta


_FAVICON_URL_TEMPLATE = "https://www.google.com/s2/favicons?sz=64&domain_url={url}"
_lock = threading.Lock()
_in_flight_keys: set[tuple[int, str]] = set()
_pending_tasks: set[tuple["_FaviconFetchTask", "_FaviconSignals"]] = set()
_file_icon_provider: Optional[QFileIconProvider] = None


class _FaviconSignals(QObject):
    finished = Signal(int, str)


class _FaviconFetchTask(QRunnable):
    """Background runnable that downloads a website favicon and saves it as a PNG."""

    def __init__(
        self,
        shortcut_id: int,
        target_url: str,
        dest_path: Path,
        signals: _FaviconSignals,
    ):
        super().__init__()
        self.setAutoDelete(False)
        self.shortcut_id = shortcut_id
        self.target_url = target_url
        self.dest_path = dest_path
        self.signals = signals
        self._key = (shortcut_id, str(dest_path))

    def run(self) -> None:
        saved_path = ""
        try:
            encoded_url = urllib.parse.quote(self.target_url, safe="")
            request_url = _FAVICON_URL_TEMPLATE.format(url=encoded_url)
            req = urllib.request.Request(
                request_url,
                headers={"User-Agent": "F9Sidebar/1.0"},
            )
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                data = resp.read()

            if data:
                image = QImage.fromData(data)
                if not image.isNull():
                    self.dest_path.parent.mkdir(parents=True, exist_ok=True)
                    if image.save(str(self.dest_path), "PNG"):
                        saved_path = str(self.dest_path)
        except Exception:
            pass
        finally:
            with _lock:
                _in_flight_keys.discard(self._key)
            try:
                self.signals.finished.emit(self.shortcut_id, saved_path)
            except RuntimeError:
                pass


def _get_file_icon_provider() -> QFileIconProvider:
    global _file_icon_provider
    if _file_icon_provider is None:
        _file_icon_provider = QFileIconProvider()
    return _file_icon_provider


def _is_valid_image_file(path: Path) -> bool:
    if not path.is_file():
        return False
    pixmap = QPixmap(str(path))
    return not pixmap.isNull()


def get_shortcut_icon(
    shortcut_dict: Dict,
    icons_dir: Path | str,
    on_favicon_ready: Optional[Callable[[int, str], None]] = None,
) -> QIcon:
    """Returns a native icon for app/folder shortcuts or a cached/async favicon for URLs."""
    shortcut_id = int(shortcut_dict.get("id", 0))
    target = str(shortcut_dict.get("target", "")).strip()
    category = str(shortcut_dict.get("category", "app")).lower().strip()
    custom_icon_path = str(shortcut_dict.get("icon_path", "")).strip()

    if custom_icon_path:
        custom_file = Path(custom_icon_path)
        if _is_valid_image_file(custom_file):
            return QIcon(str(custom_file))

    is_url = category == "url" or target.startswith(("http://", "https://"))
    if is_url:
        icons_root = Path(icons_dir)
        cache_path = icons_root / f"{shortcut_id}.png" if shortcut_id > 0 else None

        if cache_path is not None and _is_valid_image_file(cache_path):
            return QIcon(str(cache_path))

        if cache_path is not None and target:
            key = (shortcut_id, str(cache_path))
            should_start = False
            with _lock:
                if key not in _in_flight_keys:
                    _in_flight_keys.add(key)
                    should_start = True

            if should_start:
                signals = _FaviconSignals()
                task = _FaviconFetchTask(shortcut_id, target, cache_path, signals)
                entry = (task, signals)
                with _lock:
                    _pending_tasks.add(entry)

                def _on_done(sid: int, saved: str, _entry=entry) -> None:
                    with _lock:
                        _pending_tasks.discard(_entry)
                    if saved and on_favicon_ready is not None:
                        on_favicon_ready(sid, saved)

                signals.finished.connect(_on_done, Qt.ConnectionType.QueuedConnection)
                QThreadPool.globalInstance().start(task)

        return qta.icon("fa5s.globe", color="#89B4FA")

    # App or folder target -> native Windows icon via QFileIconProvider
    if target:
        native_icon = _get_file_icon_provider().icon(QFileInfo(target))
        if not native_icon.isNull() and not native_icon.pixmap(22, 22).isNull():
            return native_icon

    if category == "folder":
        return qta.icon("fa5s.folder", color="#89B4FA")
    return qta.icon("fa5s.cube", color="#89B4FA")
