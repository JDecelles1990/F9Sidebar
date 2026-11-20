"""App-wide Sunset-themed animated hover tooltip popup for F9Sidebar.

Intercepts QEvent.Type.ToolTip across the entire QApplication (buttons, tiles,
note tabs, queue rows, dialogs, image editor top bar) without modifying any
button widgets, button stylesheets, or button_fx.py.

Visual design:
- Deep twilight plum -> warm dusk -> sunset rose surface gradient (#231B33 -> #342240 -> #452842)
- Warm sunset cream text (#FFF3E6) with Sunset Gold (#F9E2AF) shortcut badges
  and soft rose-lavender (#F5C2E7) secondary lines
- Animated shimmering Sunset border & top horizon strip (#F9E2AF -> #FAB387 -> #F38BA8 -> #CBA6F7)
- Soft multi-layer breathing outer Sunset aura glow
- Smooth fade-in + 6px lift slide transition on appear, smooth glide across
  adjacent controls, and smooth fade-out on dismiss
"""

import html
import math
import re
from typing import Optional, Tuple

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QObject,
    QPoint,
    QPropertyAnimation,
    QRectF,
    Qt,
    QTimer,
    QVariantAnimation,
)
from PySide6.QtGui import (
    QColor,
    QConicalGradient,
    QCursor,
    QGuiApplication,
    QHelpEvent,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QTextDocument,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QHBoxLayout,
    QLabel,
    QToolTip,
    QWidget,
)

try:
    from shiboken6 import isValid as _qt_is_valid
except ImportError:  # pragma: no cover - shiboken6 ships with PySide6
    def _qt_is_valid(obj) -> bool:
        return obj is not None


# Sunset Tooltip Palette
TOOLTIP_BG_START = "#231B33"
TOOLTIP_BG_MID = "#342240"
TOOLTIP_BG_END = "#452842"

TOOLTIP_GOLD = "#F9E2AF"
TOOLTIP_PEACH = "#FAB387"
TOOLTIP_CORAL = "#F38BA8"
TOOLTIP_MAUVE = "#CBA6F7"

TOOLTIP_TEXT_PRIMARY = "#FFF3E6"
TOOLTIP_TEXT_ACCENT = "#F9E2AF"
TOOLTIP_TEXT_SECONDARY = "#F5C2E7"

FALLBACK_QTOOLTIP_QSS = f"""
QToolTip {{
    background-color: qlineargradient(
        x1:0, y1:0, x2:1, y2:1,
        stop:0 {TOOLTIP_BG_START}, stop:0.55 {TOOLTIP_BG_MID}, stop:1 {TOOLTIP_BG_END}
    );
    color: {TOOLTIP_TEXT_PRIMARY};
    border: 1px solid {TOOLTIP_PEACH};
    border-radius: 8px;
    padding: 5px 9px;
    font-family: 'Segoe UI', sans-serif;
    font-size: 12px;
    font-weight: 600;
}}
"""

_PAREN_HINT_RE = re.compile(r"(\([^()]{1,96}\))")


def format_tooltip_html(raw_text: str, max_chars: int = 320) -> str:
    """Formats plain tooltip text into Sunset-styled rich HTML safely."""
    text = (raw_text or "").strip()
    if not text:
        return ""
    if len(text) > max_chars:
        text = text[: max_chars - 1].rstrip() + "…"

    lines = text.splitlines()
    rendered_lines = []
    for idx, line in enumerate(lines):
        escaped = html.escape(line)
        if idx == 0:
            styled = _PAREN_HINT_RE.sub(
                rf'<span style="color:{TOOLTIP_TEXT_ACCENT}; font-weight:700;">\1</span>',
                escaped,
            )
            rendered_lines.append(
                f'<span style="color:{TOOLTIP_TEXT_PRIMARY}; font-weight:600;">{styled}</span>'
            )
        else:
            rendered_lines.append(
                f'<span style="color:{TOOLTIP_TEXT_SECONDARY}; font-size:11px; font-weight:500;">{escaped}</span>'
            )
    return "<br>".join(rendered_lines)


class SunsetTooltipPopup(QWidget):
    """Frameless translucent Sunset-themed tooltip popup with glow and smooth transitions."""

    GLOW_MARGIN = 10
    CARD_RADIUS = 10.0
    MAX_TEXT_WIDTH = 330
    SLIDE_OFFSET_PX = 5
    PAD_X = 11
    PAD_TOP = 8
    PAD_BOTTOM = 7

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("SunsetTooltipPopup")
        self.setWindowFlags(
            Qt.WindowType.ToolTip
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowTransparentForInput
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._raw_text = ""
        self._shimmer_phase = 0.0
        self._is_fading_out = False

        layout = QHBoxLayout(self)
        m = self.GLOW_MARGIN
        layout.setContentsMargins(
            m + self.PAD_X, m + self.PAD_TOP, m + self.PAD_X, m + self.PAD_BOTTOM
        )
        layout.setSpacing(0)

        self.label = QLabel(self)
        self.label.setObjectName("SunsetTooltipLabel")
        self.label.setTextFormat(Qt.TextFormat.RichText)
        self.label.setWordWrap(True)
        self.label.setStyleSheet(
            f"""
            QLabel#SunsetTooltipLabel {{
                background: transparent;
                color: {TOOLTIP_TEXT_PRIMARY};
                font-family: 'Segoe UI', 'Segoe UI Emoji', sans-serif;
                font-size: 12px;
                font-weight: 600;
            }}
            """
        )
        layout.addWidget(self.label)

        self.fade_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self.fade_anim.setDuration(155)
        self.fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.fade_anim.finished.connect(self._on_fade_finished)

        self.slide_anim = QPropertyAnimation(self, b"pos", self)
        self.slide_anim.setDuration(155)
        self.slide_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.shimmer_anim = QVariantAnimation(self)
        self.shimmer_anim.setStartValue(0.0)
        self.shimmer_anim.setEndValue(1.0)
        self.shimmer_anim.setDuration(3200)
        self.shimmer_anim.setLoopCount(-1)
        self.shimmer_anim.valueChanged.connect(self._on_shimmer_tick)

        self.auto_hide_timer = QTimer(self)
        self.auto_hide_timer.setSingleShot(True)
        self.auto_hide_timer.timeout.connect(self.hide_animated)

    @property
    def raw_text(self) -> str:
        return self._raw_text

    def _on_shimmer_tick(self, value) -> None:
        self._shimmer_phase = float(value)
        if self.isVisible():
            self.update()

    def _on_fade_finished(self) -> None:
        if self._is_fading_out:
            self._is_fading_out = False
            self.hide()

    def compute_anchor_pos(
        self, target: Optional[QWidget], global_pos: QPoint
    ) -> Tuple[QPoint, bool]:
        """Computes clamped screen position above (or below) the hovered control."""
        screen = (
            QGuiApplication.screenAt(global_pos)
            or (
                target.screen()
                if target is not None and _qt_is_valid(target)
                else None
            )
            or QGuiApplication.primaryScreen()
        )
        avail = screen.availableGeometry() if screen is not None else None
        w = self.width()
        h = self.height()
        m = self.GLOW_MARGIN
        gap = 8

        is_item_viewport = (
            target is not None
            and _qt_is_valid(target)
            and isinstance(target.parentWidget(), QAbstractItemView)
        )
        if (
            target is not None
            and _qt_is_valid(target)
            and target.isVisible()
            and not is_item_viewport
            and target.height() <= 64
        ):
            top_left = target.mapToGlobal(QPoint(0, 0))
            if target.width() <= 220:
                anchor_cx = top_left.x() + target.width() // 2
            else:
                anchor_cx = global_pos.x()
            anchor_top = top_left.y()
            anchor_bottom = top_left.y() + target.height()
        else:
            anchor_cx = global_pos.x()
            anchor_top = global_pos.y() - 6
            anchor_bottom = global_pos.y() + 18

        x = anchor_cx - w // 2
        y_above = anchor_top - (h - m) - gap
        y_below = anchor_bottom - m + gap

        placed_above = True
        y = y_above
        if avail is not None:
            if y_above + m < avail.top() + 4 and (y_below + h - m) <= avail.bottom() - 4:
                y = y_below
                placed_above = False
            min_x = avail.left() - m + 4
            max_x = avail.right() - w + m - 4
            min_y = avail.top() - m + 4
            max_y = avail.bottom() - h + m - 4
            if max_x >= min_x:
                x = max(min_x, min(max_x, x))
            if max_y >= min_y:
                y = max(min_y, min(max_y, y))

        return QPoint(int(x), int(y)), placed_above

    def _fit_to_html(self, rich_html: str) -> None:
        """Sizes the label and popup cleanly without premature line wrapping."""
        self.label.ensurePolished()
        doc = QTextDocument()
        doc.setDefaultFont(self.label.font())
        doc.setDocumentMargin(0.0)
        doc.setHtml(rich_html)

        ideal_w = math.ceil(doc.idealWidth())
        target_w = max(24, min(self.MAX_TEXT_WIDTH, ideal_w)) + 4
        doc.setTextWidth(float(target_w))
        target_h = max(16, math.ceil(doc.size().height())) + 2

        self.label.setText(rich_html)
        self.label.setFixedSize(target_w, target_h)
        m = self.GLOW_MARGIN
        total_w = target_w + 2 * (m + self.PAD_X)
        total_h = target_h + (m + self.PAD_TOP) + (m + self.PAD_BOTTOM)
        self.setFixedSize(total_w, total_h)

    def show_for_widget(
        self,
        target: Optional[QWidget],
        text: str,
        global_pos: Optional[QPoint] = None,
        auto_hide_ms: int = 8000,
    ) -> None:
        clean = (text or "").strip()
        if not clean:
            return

        self._raw_text = clean
        rich_html = format_tooltip_html(clean)
        self._fit_to_html(rich_html)

        ref_pos = global_pos if global_pos is not None else QCursor.pos()
        end_pos, placed_above = self.compute_anchor_pos(target, ref_pos)

        was_visible = self.isVisible() and not self._is_fading_out and self.windowOpacity() > 0.2
        self._is_fading_out = False
        self.fade_anim.stop()
        self.slide_anim.stop()

        if was_visible:
            # Smoothly glide from previous button's tooltip to the new target
            self.slide_anim.setDuration(130)
            self.slide_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            self.slide_anim.setStartValue(self.pos())
            self.slide_anim.setEndValue(end_pos)
            self.slide_anim.start()

            if self.windowOpacity() < 0.99:
                self.fade_anim.setDuration(110)
                self.fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
                self.fade_anim.setStartValue(self.windowOpacity())
                self.fade_anim.setEndValue(1.0)
                self.fade_anim.start()
            self.raise_()
        else:
            dy = self.SLIDE_OFFSET_PX if placed_above else -self.SLIDE_OFFSET_PX
            start_pos = QPoint(end_pos.x(), end_pos.y() + dy)
            self.move(start_pos)
            self.setWindowOpacity(0.0)
            self.show()
            self.raise_()

            self.slide_anim.setDuration(155)
            self.slide_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            self.slide_anim.setStartValue(start_pos)
            self.slide_anim.setEndValue(end_pos)
            self.slide_anim.start()

            self.fade_anim.setDuration(155)
            self.fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            self.fade_anim.setStartValue(0.0)
            self.fade_anim.setEndValue(1.0)
            self.fade_anim.start()

        if self.shimmer_anim.state() != QVariantAnimation.State.Running:
            self.shimmer_anim.start()
        self.auto_hide_timer.start(max(1000, int(auto_hide_ms)))
        self.update()

    def hide_animated(self) -> None:
        self.auto_hide_timer.stop()
        if not self.isVisible() or self._is_fading_out:
            return
        self._is_fading_out = True
        self.slide_anim.stop()
        self.fade_anim.stop()
        self.fade_anim.setDuration(110)
        self.fade_anim.setEasingCurve(QEasingCurve.Type.InQuad)
        self.fade_anim.setStartValue(self.windowOpacity())
        self.fade_anim.setEndValue(0.0)
        self.fade_anim.start()

    def hide_immediately(self) -> None:
        self.auto_hide_timer.stop()
        self._is_fading_out = False
        self.slide_anim.stop()
        self.fade_anim.stop()
        self.shimmer_anim.stop()
        self.hide()

    def hideEvent(self, event) -> None:
        self.shimmer_anim.stop()
        self.auto_hide_timer.stop()
        super().hideEvent(event)

    def paintEvent(self, event) -> None:
        m = float(self.GLOW_MARGIN)
        card = QRectF(self.rect()).adjusted(m, m, -m, -m)
        if card.width() <= 2 or card.height() <= 2:
            return

        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

            # 1. Soft breathing outer Sunset glow aura (4 feathered steps)
            pulse = 0.84 + 0.16 * math.sin(self._shimmer_phase * 2.0 * math.pi)
            for expand, pen_w, alpha in (
                (1.2, 2.6, 52),
                (2.8, 4.0, 28),
                (4.6, 5.4, 13),
                (6.4, 6.8, 6),
            ):
                g = QLinearGradient(card.topLeft(), card.bottomRight())
                for stop, hx in (
                    (0.0, TOOLTIP_GOLD),
                    (0.35, TOOLTIP_PEACH),
                    (0.7, TOOLTIP_CORAL),
                    (1.0, TOOLTIP_MAUVE),
                ):
                    c = QColor(hx)
                    c.setAlpha(max(1, min(255, int(round(alpha * pulse)))))
                    g.setColorAt(stop, c)
                pen = QPen(g, pen_w)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(
                    card.adjusted(-expand, -expand, expand, expand),
                    self.CARD_RADIUS + expand,
                    self.CARD_RADIUS + expand,
                )

            # 2. Rich Sunset Twilight Card Fill + soft upper sunset sheen
            card_path = QPainterPath()
            card_path.addRoundedRect(card, self.CARD_RADIUS, self.CARD_RADIUS)
            bg_grad = QLinearGradient(card.topLeft(), card.bottomRight())
            bg_grad.setColorAt(0.0, QColor(TOOLTIP_BG_START))
            bg_grad.setColorAt(0.55, QColor(TOOLTIP_BG_MID))
            bg_grad.setColorAt(1.0, QColor(TOOLTIP_BG_END))
            painter.fillPath(card_path, bg_grad)

            # 3. Warm upper ambient glow + Luminous Top Sunset Horizon Accent Bar
            painter.save()
            painter.setClipPath(card_path)
            sheen = QLinearGradient(card.left(), card.top(), card.left(), card.top() + card.height() * 0.52)
            sheen_top = QColor(TOOLTIP_PEACH)
            sheen_top.setAlpha(int(round(28 * pulse)))
            sheen_bot = QColor(TOOLTIP_CORAL)
            sheen_bot.setAlpha(0)
            sheen.setColorAt(0.0, sheen_top)
            sheen.setColorAt(1.0, sheen_bot)
            painter.fillRect(
                QRectF(card.left(), card.top(), card.width(), card.height() * 0.52),
                sheen,
            )

            shift = self._shimmer_phase * card.width()
            bar_grad = QLinearGradient(
                card.left() - card.width() + shift,
                card.top(),
                card.right() + shift,
                card.top(),
            )
            bar_grad.setColorAt(0.0, QColor(TOOLTIP_CORAL))
            bar_grad.setColorAt(0.25, QColor(TOOLTIP_GOLD))
            bar_grad.setColorAt(0.5, QColor(TOOLTIP_PEACH))
            bar_grad.setColorAt(0.75, QColor(TOOLTIP_CORAL))
            bar_grad.setColorAt(1.0, QColor(TOOLTIP_MAUVE))
            painter.fillRect(
                QRectF(card.left(), card.top(), card.width(), 2.5),
                bar_grad,
            )
            painter.restore()

            # 4. Animated Shimmering Sunset Border
            border_grad = QConicalGradient(
                card.center(), (self._shimmer_phase * 360.0) % 360.0
            )
            border_grad.setColorAt(0.0, QColor(TOOLTIP_GOLD))
            border_grad.setColorAt(0.25, QColor(TOOLTIP_PEACH))
            border_grad.setColorAt(0.5, QColor(TOOLTIP_CORAL))
            border_grad.setColorAt(0.75, QColor(TOOLTIP_MAUVE))
            border_grad.setColorAt(1.0, QColor(TOOLTIP_GOLD))
            painter.setPen(QPen(border_grad, 1.4))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(card, self.CARD_RADIUS, self.CARD_RADIUS)
        finally:
            painter.end()


class SunsetTooltipManager(QObject):
    """Application-wide event filter replacing Qt's grey tooltips with SunsetTooltipPopup."""

    def __init__(self, app: QApplication):
        super().__init__(app)
        self.popup = SunsetTooltipPopup()
        self._current_target: Optional[QWidget] = None
        self._pending_target: Optional[QWidget] = None

        self._leave_hide_timer = QTimer(self)
        self._leave_hide_timer.setSingleShot(True)
        self._leave_hide_timer.setInterval(85)
        self._leave_hide_timer.timeout.connect(self._on_leave_timeout)

        self._glide_window_timer = QTimer(self)
        self._glide_window_timer.setSingleShot(True)
        self._glide_window_timer.setInterval(380)

        self._glide_show_timer = QTimer(self)
        self._glide_show_timer.setSingleShot(True)
        self._glide_show_timer.setInterval(110)
        self._glide_show_timer.timeout.connect(self._on_glide_show)

        # Fallback stylesheet in case any native QToolTip renders directly
        existing_qss = app.styleSheet() or ""
        if "QToolTip" not in existing_qss:
            app.setStyleSheet(existing_qss + "\n" + FALLBACK_QTOOLTIP_QSS)

    def _is_own_widget(self, obj) -> bool:
        if not _qt_is_valid(self.popup):
            return False
        return obj is self.popup or (
            isinstance(obj, QWidget) and self.popup.isAncestorOf(obj)
        )

    @staticmethod
    def _resolve_tooltip_text(widget: QWidget, local_pos: Optional[QPoint] = None) -> str:
        tip = (widget.toolTip() or "").strip()
        if tip:
            return tip
        parent = widget.parentWidget()
        if local_pos is not None and isinstance(parent, QAbstractItemView):
            idx = parent.indexAt(local_pos)
            if idx.isValid():
                role_tip = idx.data(Qt.ItemDataRole.ToolTipRole)
                if isinstance(role_tip, str) and role_tip.strip():
                    return role_tip.strip()
        return ""

    def show_tooltip(
        self, widget: QWidget, text: str, global_pos: Optional[QPoint] = None
    ) -> None:
        if not _qt_is_valid(self.popup) or not _qt_is_valid(widget):
            return
        self._leave_hide_timer.stop()
        self._glide_show_timer.stop()
        self._pending_target = None
        self._current_target = widget
        QToolTip.hideText()
        self.popup.show_for_widget(widget, text, global_pos)

    def hide_tooltip(self, immediate: bool = False) -> None:
        self._leave_hide_timer.stop()
        self._glide_show_timer.stop()
        self._pending_target = None
        self._current_target = None
        if _qt_is_valid(self.popup):
            if immediate:
                self.popup.hide_immediately()
            else:
                self.popup.hide_animated()

    def _on_leave_timeout(self) -> None:
        self._current_target = None
        if _qt_is_valid(self.popup):
            self.popup.hide_animated()

    def _on_glide_show(self) -> None:
        target = self._pending_target
        self._pending_target = None
        if target is None or not _qt_is_valid(target) or not target.isVisible():
            return
        tip = self._resolve_tooltip_text(target)
        if tip:
            self.show_tooltip(target, tip, QCursor.pos())

    def eventFilter(self, obj, event) -> bool:
        if not _qt_is_valid(self.popup) or self._is_own_widget(obj):
            return False

        etype = event.type()

        if etype == QEvent.Type.ToolTip and isinstance(obj, QWidget):
            local_pos = event.pos() if isinstance(event, QHelpEvent) else None
            tip = self._resolve_tooltip_text(obj, local_pos)
            if not tip:
                return False
            is_item_viewport = isinstance(obj.parentWidget(), QAbstractItemView)
            if (
                obj is self._current_target
                and self.popup.isVisible()
                and not self.popup._is_fading_out
                and self.popup.raw_text == tip
                and not is_item_viewport
            ):
                self._leave_hide_timer.stop()
                self.popup.auto_hide_timer.start(8000)
                event.accept()
                return True
            gpos = event.globalPos() if isinstance(event, QHelpEvent) else QCursor.pos()
            self.show_tooltip(obj, tip, gpos)
            event.accept()
            return True

        if etype == QEvent.Type.Enter and isinstance(obj, QWidget):
            if obj is self._current_target:
                self._leave_hide_timer.stop()
                if self.popup._is_fading_out:
                    tip = self._resolve_tooltip_text(obj)
                    if tip:
                        self.show_tooltip(obj, tip, QCursor.pos())
                return False
            if self.popup.isVisible() or self._glide_window_timer.isActive():
                tip = self._resolve_tooltip_text(obj)
                if tip and obj is not self._current_target:
                    self._leave_hide_timer.stop()
                    self._pending_target = obj
                    self._glide_show_timer.start()
            return False

        if etype == QEvent.Type.Leave:
            if obj is self._pending_target:
                self._glide_show_timer.stop()
                self._pending_target = None
                if self.popup.isVisible():
                    self._leave_hide_timer.start()
                return False
            if obj is self._current_target:
                self._glide_show_timer.stop()
                self._glide_window_timer.start()
                self._leave_hide_timer.start()
                return False

        if etype in (
            QEvent.Type.MouseButtonPress,
            QEvent.Type.Wheel,
            QEvent.Type.KeyPress,
        ):
            if self.popup.isVisible() or self._glide_show_timer.isActive():
                self.hide_tooltip(immediate=False)
            return False

        if etype == QEvent.Type.ApplicationDeactivate:
            self.hide_tooltip(immediate=True)
            return False

        if etype == QEvent.Type.WindowDeactivate:
            if (
                self._current_target is not None
                and _qt_is_valid(self._current_target)
                and obj is self._current_target.window()
            ):
                self.hide_tooltip(immediate=False)
            return False

        if obj is self._current_target and etype in (
            QEvent.Type.Hide,
            QEvent.Type.Destroy,
            QEvent.Type.EnabledChange,
        ):
            if etype != QEvent.Type.EnabledChange or not obj.isEnabled():
                self.hide_tooltip(immediate=(etype == QEvent.Type.Destroy))
            return False

        return False


_TOOLTIP_MANAGER: Optional[SunsetTooltipManager] = None


def install_sunset_tooltips(
    app: Optional[QApplication] = None,
) -> Optional[SunsetTooltipManager]:
    """Install the shared Sunset tooltip manager once per QApplication."""
    global _TOOLTIP_MANAGER
    app = app or QApplication.instance()
    if app is None:
        return None
    if _TOOLTIP_MANAGER is not None and _qt_is_valid(_TOOLTIP_MANAGER):
        return _TOOLTIP_MANAGER
    _TOOLTIP_MANAGER = SunsetTooltipManager(app)
    app.installEventFilter(_TOOLTIP_MANAGER)
    return _TOOLTIP_MANAGER
