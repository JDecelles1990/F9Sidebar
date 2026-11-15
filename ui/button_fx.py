"""Animated hover / press effects applied to every QPushButton and QToolButton.

Hover:  warm yellow -> orange -> pink gradient fill, plus a rotating
        blue -> purple glowing halo painted around the button.
Press:  deeper peach -> pink -> purple gradient and an expanding glow ring pulse.

The effect is installed once as an application-wide event filter, so buttons that
are created later (shortcut tiles, note tabs, queue rows, dialogs) are covered too.
"""

import math
from typing import Dict, Optional

from PySide6.QtCore import QEasingCurve, QEvent, QObject, QRectF, QSize, Qt, QVariantAnimation
from PySide6.QtGui import QBrush, QColor, QConicalGradient, QIcon, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollBar,
    QSplitter,
    QTabBar,
    QToolButton,
    QWidget,
)

try:
    from shiboken6 import isValid as _qt_is_valid
except ImportError:  # pragma: no cover - shiboken6 ships with PySide6
    def _qt_is_valid(obj) -> bool:
        return obj is not None


HOVER_GRADIENT = (
    "qlineargradient(x1:0, y1:0, x2:1, y2:1, "
    "stop:0 #F9E2AF, stop:0.5 #FAB387, stop:1 #F5C2E7)"
)
PRESSED_GRADIENT = (
    "qlineargradient(x1:0, y1:1, x2:1, y2:0, "
    "stop:0 #FAB387, stop:0.5 #F38BA8, stop:1 #CBA6F7)"
)
GLOW_BLUE = "#89B4FA"
GLOW_PURPLE = "#CBA6F7"
HOVER_TEXT = "#1E1E2E"

HOVER_QSS = f"""
QPushButton, QToolButton {{
    background-color: {HOVER_GRADIENT};
    border: 1px solid {GLOW_PURPLE};
    color: {HOVER_TEXT};
}}
QPushButton:pressed, QToolButton:pressed {{
    background-color: {PRESSED_GRADIENT};
    border: 1px solid {GLOW_BLUE};
    color: {HOVER_TEXT};
}}
"""

# Parents whose internal helper buttons should keep their native look.
_EXCLUDED_PARENT_TYPES = (QLineEdit, QAbstractSpinBox, QComboBox, QScrollBar, QTabBar, QMenu)


def _is_monochrome_icon(icon: QIcon, size: QSize) -> bool:
    """True for single-color glyph icons (qtawesome), False for multicolor app/favicons."""
    if icon.isNull():
        return False
    if size.isEmpty():
        size = QSize(16, 16)
    img = icon.pixmap(size).toImage().convertToFormat(QImage.Format.Format_ARGB32)
    if img.isNull():
        return False
    step = max(1, max(img.width(), img.height()) // 24)
    lo = [255, 255, 255]
    hi = [0, 0, 0]
    seen = 0
    for y in range(0, img.height(), step):
        for x in range(0, img.width(), step):
            c = img.pixelColor(x, y)
            if c.alpha() < 60:
                continue
            seen += 1
            for i, v in enumerate((c.red(), c.green(), c.blue())):
                lo[i] = min(lo[i], v)
                hi[i] = max(hi[i], v)
    if seen == 0:
        return False
    return all(hi[i] - lo[i] <= 48 for i in range(3))


def _tint_icon(icon: QIcon, size: QSize, color: QColor) -> QIcon:
    if size.isEmpty():
        size = QSize(16, 16)
    src = icon.pixmap(size)
    tinted = QPixmap(src.size())
    tinted.setDevicePixelRatio(src.devicePixelRatio())
    tinted.fill(Qt.GlobalColor.transparent)
    painter = QPainter(tinted)
    try:
        painter.drawPixmap(0, 0, src)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(tinted.rect(), color)
    finally:
        painter.end()
    return QIcon(tinted)


class GlowHalo(QWidget):
    """Mouse-transparent sibling painted beneath a button: rotating blue->purple glow."""

    MARGIN = 10

    def __init__(self, button: QWidget):
        super().__init__(button.parentWidget())
        self._button = button
        self._angle = 0.0
        self._pulse = 1.0  # 1.0 == no pulse ring visible
        self.setObjectName("FxGlowHalo")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setStyleSheet("background: transparent; border: none;")

        self.spin_anim = QVariantAnimation(self)
        self.spin_anim.setStartValue(0.0)
        self.spin_anim.setEndValue(360.0)
        self.spin_anim.setDuration(1800)
        self.spin_anim.setLoopCount(-1)
        self.spin_anim.valueChanged.connect(self._on_spin)

        self.pulse_anim = QVariantAnimation(self)
        self.pulse_anim.setStartValue(0.0)
        self.pulse_anim.setEndValue(1.0)
        self.pulse_anim.setDuration(420)
        self.pulse_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.pulse_anim.valueChanged.connect(self._on_pulse)

        self.sync_geometry()

    def _on_spin(self, value) -> None:
        self._angle = float(value)
        self.update()

    def _on_pulse(self, value) -> None:
        self._pulse = float(value)
        self.update()

    def start(self) -> None:
        self.show()
        self.sync_geometry()
        self.spin_anim.start()

    def stop(self) -> None:
        self.spin_anim.stop()
        self.pulse_anim.stop()

    def pulse(self) -> None:
        self.pulse_anim.stop()
        self._pulse = 0.0
        self.pulse_anim.start()

    def sync_geometry(self) -> None:
        btn = self._button
        if not _qt_is_valid(btn) or btn.parentWidget() is not self.parentWidget():
            return
        m = self.MARGIN
        self.setGeometry(btn.geometry().adjusted(-m, -m, m, m))
        self.stackUnder(btn)

    def _ring_gradient(self, center, alpha: int) -> QConicalGradient:
        grad = QConicalGradient(center, self._angle)
        blue = QColor(GLOW_BLUE)
        purple = QColor(GLOW_PURPLE)
        blue.setAlpha(max(0, min(255, alpha)))
        purple.setAlpha(max(0, min(255, alpha)))
        grad.setColorAt(0.0, blue)
        grad.setColorAt(0.5, purple)
        grad.setColorAt(1.0, blue)
        return grad

    def paintEvent(self, event) -> None:
        m = float(self.MARGIN)
        inner = QRectF(m, m, self.width() - 2 * m, self.height() - 2 * m)
        if inner.width() <= 0 or inner.height() <= 0:
            return
        center = inner.center()
        radius = min(7.0, inner.height() / 2.0)
        breath = 0.8 + 0.2 * math.sin(math.radians(self._angle * 2.0))
        if self._pulse < 1.0:
            breath = min(1.25, breath + 0.45 * (1.0 - self._pulse))

        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for spread, alpha, width in (
                (1.0, 235, 1.8),
                (2.6, 160, 1.8),
                (4.2, 105, 1.8),
                (5.8, 60, 1.8),
                (7.4, 28, 1.8),
            ):
                pen = QPen(QBrush(self._ring_gradient(center, int(alpha * breath))), width)
                painter.setPen(pen)
                painter.drawRoundedRect(
                    inner.adjusted(-spread, -spread, spread, spread),
                    radius + spread,
                    radius + spread,
                )

            if self._pulse < 1.0:
                spread = 1.5 + self._pulse * (m - 2.0)
                alpha = int(255 * (1.0 - self._pulse))
                pen = QPen(QBrush(self._ring_gradient(center, alpha)), 2.6)
                painter.setPen(pen)
                painter.drawRoundedRect(
                    inner.adjusted(-spread, -spread, spread, spread),
                    radius + spread,
                    radius + spread,
                )
        finally:
            painter.end()


class _FxState:
    __slots__ = ("orig_qss", "applied_qss", "orig_icon", "hover_icon_key", "halo")

    def __init__(self) -> None:
        self.orig_qss = ""
        self.applied_qss = ""
        self.orig_icon: Optional[QIcon] = None
        self.hover_icon_key: Optional[int] = None
        self.halo: Optional[GlowHalo] = None


class ButtonFxManager(QObject):
    """Application-wide event filter driving the hover gradient, glow halo, and press pulse."""

    _WATCHED = {
        QEvent.Type.Enter,
        QEvent.Type.Leave,
        QEvent.Type.Hide,
        QEvent.Type.MouseButtonPress,
        QEvent.Type.Move,
        QEvent.Type.Resize,
        QEvent.Type.EnabledChange,
    }

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._states: Dict[int, _FxState] = {}

    # --- public helpers (also used by tests) ---
    def is_active(self, button: QWidget) -> bool:
        return id(button) in self._states

    def halo_for(self, button: QWidget) -> Optional[GlowHalo]:
        state = self._states.get(id(button))
        return state.halo if state is not None else None

    @staticmethod
    def is_eligible(button: QWidget) -> bool:
        if not isinstance(button, (QPushButton, QToolButton)):
            return False
        if not _qt_is_valid(button) or not button.isEnabled() or not button.isVisible():
            return False
        if button.property("fxDisabled"):
            return False
        parent = button.parentWidget()
        if parent is not None and isinstance(parent, _EXCLUDED_PARENT_TYPES):
            return False
        return True

    def activate(self, button: QWidget) -> bool:
        key = id(button)
        existing = self._states.get(key)
        if existing is not None:
            if existing.halo is not None and _qt_is_valid(existing.halo):
                existing.halo.sync_geometry()
            return True
        if not self.is_eligible(button):
            return False

        state = _FxState()
        state.orig_qss = button.styleSheet()
        base = state.orig_qss.strip()
        if base and "{" not in base:
            type_sel = "QPushButton" if isinstance(button, QPushButton) else "QToolButton"
            base = f"{type_sel} {{ {base} }}"
        state.applied_qss = f"{base}\n{HOVER_QSS}" if base else HOVER_QSS
        button.setStyleSheet(state.applied_qss)

        icon = button.icon()
        if not icon.isNull() and _is_monochrome_icon(icon, button.iconSize()):
            state.orig_icon = QIcon(icon)
            button.setIcon(_tint_icon(icon, button.iconSize(), QColor(HOVER_TEXT)))
            state.hover_icon_key = button.icon().cacheKey()

        parent = button.parentWidget()
        if parent is not None and not isinstance(parent, QSplitter):
            state.halo = GlowHalo(button)
            state.halo.start()

        if not button.property("fxHooked"):
            button.setProperty("fxHooked", True)
            button.destroyed.connect(lambda *_args, k=key: self._on_destroyed(k))

        self._states[key] = state
        return True

    def deactivate(self, button: QWidget) -> None:
        state = self._states.pop(id(button), None)
        if state is None:
            return
        if _qt_is_valid(button):
            if button.styleSheet() == state.applied_qss:
                button.setStyleSheet(state.orig_qss)
            if (
                state.orig_icon is not None
                and button.icon().cacheKey() == state.hover_icon_key
            ):
                button.setIcon(state.orig_icon)
        self._dispose_halo(state)

    def _on_destroyed(self, key: int) -> None:
        state = self._states.pop(key, None)
        if state is not None:
            self._dispose_halo(state)

    @staticmethod
    def _dispose_halo(state: _FxState) -> None:
        halo = state.halo
        state.halo = None
        if halo is not None and _qt_is_valid(halo):
            halo.stop()
            halo.hide()
            halo.deleteLater()

    # --- event filter ---
    def eventFilter(self, obj, event) -> bool:
        etype = event.type()
        if etype not in self._WATCHED or not isinstance(obj, (QPushButton, QToolButton)):
            return False

        if etype == QEvent.Type.Enter:
            self.activate(obj)
        elif etype in (QEvent.Type.Leave, QEvent.Type.Hide):
            self.deactivate(obj)
        elif etype == QEvent.Type.EnabledChange:
            if not obj.isEnabled():
                self.deactivate(obj)
        else:
            state = self._states.get(id(obj))
            if state is not None and state.halo is not None and _qt_is_valid(state.halo):
                if etype == QEvent.Type.MouseButtonPress:
                    if event.button() == Qt.MouseButton.LeftButton:
                        state.halo.pulse()
                else:
                    state.halo.sync_geometry()
        return False


_MANAGER: Optional[ButtonFxManager] = None


def install_button_fx(app: Optional[QApplication] = None) -> Optional[ButtonFxManager]:
    """Install the shared button effect manager once per QApplication."""
    global _MANAGER
    app = app or QApplication.instance()
    if app is None:
        return None
    if _MANAGER is not None and _qt_is_valid(_MANAGER):
        return _MANAGER
    _MANAGER = ButtonFxManager(app)
    app.installEventFilter(_MANAGER)
    return _MANAGER

