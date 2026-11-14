from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget
import qtawesome as qta


class ToastPopup(QWidget):
    """Non-activating corner pill notification for silent Ctrl+F9 captures."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("ToastPopup")
        self.setWindowFlags(
            Qt.WindowType.ToolTip
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide)

        self._setup_styles()
        self._build_ui()

    def _setup_styles(self) -> None:
        self.setStyleSheet(
            """
            QWidget#ToastPopup {
                background-color: #2A2D3E;
                border: 1px solid #89B4FA;
                border-radius: 14px;
                color: #CDD6F4;
                font-family: 'Segoe UI', sans-serif;
            }
            QLabel#ToastText {
                color: #CDD6F4;
                font-size: 12px;
                font-weight: 600;
                background-color: transparent;
            }
            QLabel#ToastIcon {
                background-color: transparent;
            }
            """
        )

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 14, 8)
        layout.setSpacing(8)

        self.icon_label = QLabel()
        self.icon_label.setObjectName("ToastIcon")
        self.icon_label.setFixedSize(16, 16)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.icon_label)

        self.text_label = QLabel()
        self.text_label.setObjectName("ToastText")
        layout.addWidget(self.text_label)

    @staticmethod
    def _icon_for_source(source_type: str):
        if source_type == "url":
            return qta.icon("fa5s.link", color="#89B4FA")
        if source_type == "path":
            return qta.icon("fa5s.folder-open", color="#89B4FA")
        return qta.icon("fa5s.align-left", color="#CDD6F4")

    @staticmethod
    def _truncate_preview(content: str, max_chars: int = 42) -> str:
        collapsed = " ".join((content or "").strip().split())
        if len(collapsed) <= max_chars:
            return collapsed
        return collapsed[: max_chars - 1].rstrip() + "…"

    def show_toast(
        self,
        content: str,
        source_type: str,
        queue_count: int,
        duration_ms: int = 1200,
    ) -> None:
        preview = self._truncate_preview(content)
        self.icon_label.setPixmap(self._icon_for_source(source_type).pixmap(16, 16))
        self.text_label.setText(f"Clipped (#{queue_count}): {preview}")
        self.adjustSize()

        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        if screen is not None:
            avail = screen.availableGeometry()
            x = avail.right() - self.width() - 16
            y = avail.bottom() - self.height() - 16
            self.move(x, y)

        self.show()
        self.raise_()
        self.hide_timer.start(duration_ms)

