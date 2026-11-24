"""Generate the multi-resolution Sunset Glass Windows .ico for F9Sidebar.

Usage:
    python scripts/generate_icon.py [output_ico_path] [--preview preview.png]

Uses PySide6 QPainter in offscreen mode to render crisp RGBA PNG frames at
16, 24, 32, 48, 64, 128, and 256 px and pack them into a standard Windows
ICO container (PNG-compressed frames supported natively on Windows Vista+
and by Qt's qico plugin).
"""

from __future__ import annotations

import argparse
import os
import struct
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QGuiApplication,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)

ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)
DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "assets" / "f9sidebar.ico"


def render_icon_frame(size: int) -> QImage:
    """Render a single square RGBA icon frame at the requested pixel size."""
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

    s = float(size)
    margin = max(0.75, s * 0.045)
    card_rect = QRectF(margin, margin, s - 2.0 * margin, s - 2.0 * margin)
    radius = max(3.0, s * 0.22)

    card_path = QPainterPath()
    card_path.addRoundedRect(card_rect, radius, radius)

    # 1. Sunset Cloud backdrop gradient (deep twilight violet -> rose -> sunset coral -> peach)
    backdrop = QLinearGradient(
        card_rect.left(), card_rect.top(), card_rect.right(), card_rect.bottom()
    )
    backdrop.setColorAt(0.00, QColor("#1D1633"))
    backdrop.setColorAt(0.42, QColor("#4A214B"))
    backdrop.setColorAt(0.76, QColor("#C85A5E"))
    backdrop.setColorAt(1.00, QColor("#F8AE74"))
    painter.fillPath(card_path, backdrop)

    # 2. Soft sunset horizon glow bloom (top-right / lower-right warmth)
    painter.save()
    painter.setClipPath(card_path)

    horizon_glow = QRadialGradient(
        QPointF(card_rect.right() - s * 0.16, card_rect.bottom() - s * 0.14),
        s * 0.68,
    )
    horizon_glow.setColorAt(0.0, QColor(255, 212, 148, 165))
    horizon_glow.setColorAt(0.45, QColor(242, 128, 114, 85))
    horizon_glow.setColorAt(1.0, QColor(242, 128, 114, 0))
    painter.fillRect(card_rect, horizon_glow)

    # 3. Cool twilight glass sheen (top-left depth for crisp "F9" contrast)
    cool_glow = QRadialGradient(
        QPointF(card_rect.left() + s * 0.24, card_rect.top() + s * 0.20),
        s * 0.65,
    )
    cool_glow.setColorAt(0.0, QColor(137, 180, 250, 75))
    cool_glow.setColorAt(0.55, QColor(30, 26, 48, 130))
    cool_glow.setColorAt(1.0, QColor(30, 26, 48, 0))
    painter.fillRect(card_rect, cool_glow)

    # 4. Frosted dark glass inner plate so "F9" stays legible at 16x16 in the tray
    glass_margin = max(1.0, s * 0.085)
    glass_rect = card_rect.adjusted(glass_margin, glass_margin, -glass_margin, -glass_margin)
    glass_path = QPainterPath()
    glass_path.addRoundedRect(glass_rect, max(2.0, radius * 0.72), max(2.0, radius * 0.72))

    glass_fill = QLinearGradient(
        glass_rect.left(), glass_rect.top(), glass_rect.left(), glass_rect.bottom()
    )
    glass_fill.setColorAt(0.0, QColor(24, 22, 38, 168))
    glass_fill.setColorAt(1.0, QColor(28, 22, 42, 138))
    painter.fillPath(glass_path, glass_fill)

    # 5. Signature right-docked sidebar accent bar (conveys the F9 right-edge overlay)
    bar_w = max(2.0, s * 0.095)
    bar_pad_y = max(1.5, s * 0.14)
    bar_rect = QRectF(
        glass_rect.right() - bar_w - max(1.0, s * 0.048),
        glass_rect.top() + bar_pad_y,
        bar_w,
        glass_rect.height() - 2.0 * bar_pad_y,
    )
    bar_grad = QLinearGradient(
        bar_rect.left(), bar_rect.top(), bar_rect.left(), bar_rect.bottom()
    )
    bar_grad.setColorAt(0.0, QColor("#89B4FA"))
    bar_grad.setColorAt(0.55, QColor("#F38BA8"))
    bar_grad.setColorAt(1.0, QColor("#FAB387"))
    bar_path = QPainterPath()
    bar_path.addRoundedRect(bar_rect, bar_w * 0.45, bar_w * 0.45)
    painter.fillPath(bar_path, bar_grad)

    # Subtle top glass rim highlight
    if size >= 24:
        rim_pen = QPen(QColor(255, 240, 230, 82), max(1.0, s * 0.018))
        painter.setPen(rim_pen)
        painter.drawPath(glass_path)

    painter.restore()

    # 6. Outer glass border
    border_pen = QPen(QColor(255, 228, 214, 155), max(1.0, s * 0.028))
    painter.setPen(border_pen)
    painter.drawPath(card_path)

    # 7. Crisp font-independent geometric vector "F9" monogram
    # Rendered purely with QPainterPath so it stays razor-sharp in offscreen QPA
    # and across all DPI scales from 16x16 tray icons to 256x256 Explorer tiles.
    sw = max(1.65, s * 0.072)
    y_top = s * 0.305
    y_bot = s * 0.695
    h = y_bot - y_top

    # "F" stroke path
    fx0 = s * 0.222
    fx1 = s * 0.362
    f_mid_y = y_top + h * 0.48
    f_path = QPainterPath()
    f_path.moveTo(fx0, y_bot)
    f_path.lineTo(fx0, y_top)
    f_path.lineTo(fx1, y_top)
    f_path.moveTo(fx0, f_mid_y)
    f_path.lineTo(fx0 + (fx1 - fx0) * 0.80, f_mid_y)

    # "9" stroke path (rounded upper bowl + sweeping lower tail)
    nx0 = s * 0.472
    nx1 = s * 0.622
    bowl_w = nx1 - nx0
    bowl_h = h * 0.53
    bowl_rect = QRectF(nx0, y_top, bowl_w, bowl_h)
    nine_path = QPainterPath()
    nine_path.addRoundedRect(bowl_rect, bowl_w * 0.46, bowl_w * 0.46)
    nine_path.moveTo(nx1, y_top + bowl_h * 0.52)
    nine_path.lineTo(nx1, y_top + h * 0.68)
    nine_path.cubicTo(
        nx1,
        y_bot,
        nx0 + bowl_w * 0.62,
        y_bot + s * 0.008,
        nx0 + bowl_w * 0.08,
        y_bot - s * 0.012,
    )

    glyph_path = QPainterPath()
    glyph_path.addPath(f_path)
    glyph_path.addPath(nine_path)

    # Subtle drop shadow at >= 32px for visual depth
    if size >= 32:
        shadow_pen = QPen(
            QColor(14, 10, 24, 165),
            sw,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
            Qt.PenJoinStyle.RoundJoin,
        )
        painter.save()
        painter.translate(0.0, max(1.0, s * 0.022))
        painter.setPen(shadow_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(glyph_path)
        painter.restore()

    glyph_pen = QPen(
        QColor("#FFF8F2"),
        sw,
        Qt.PenStyle.SolidLine,
        Qt.PenCapStyle.RoundCap,
        Qt.PenJoinStyle.RoundJoin,
    )
    painter.setPen(glyph_pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(glyph_path)

    painter.end()
    return image


def qimage_to_png_bytes(image: QImage) -> bytes:
    """Encode a QImage into lossless PNG bytes."""
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    ok = image.save(buf, "PNG")
    buf.close()
    if not ok:
        raise RuntimeError("Failed to encode QImage frame as PNG")
    return bytes(ba.data())


def build_ico_bytes(frames: list[tuple[int, bytes]]) -> bytes:
    """Pack (dimension, png_bytes) pairs into a standard Windows .ico file."""
    count = len(frames)
    header = struct.pack("<HHH", 0, 1, count)
    offset = 6 + 16 * count
    entries = bytearray()
    payload = bytearray()

    for dim, png_data in frames:
        width_byte = 0 if dim >= 256 else dim
        height_byte = 0 if dim >= 256 else dim
        entries.extend(
            struct.pack(
                "<BBBBHHII",
                width_byte,
                height_byte,
                0,   # color palette count (0 for PNG/32bpp)
                0,   # reserved
                1,   # color planes
                32,  # bits per pixel
                len(png_data),
                offset,
            )
        )
        payload.extend(png_data)
        offset += len(png_data)

    return header + bytes(entries) + bytes(payload)


def generate_ico(output_path: Path, preview_path: Path | None = None) -> Path:
    """Generate the multi-resolution ICO file (and optional 256px PNG preview)."""
    app = QGuiApplication.instance()
    if app is None:
        app = QGuiApplication(sys.argv[:1])

    frames: list[tuple[int, bytes]] = []
    preview_image: QImage | None = None

    for size in ICON_SIZES:
        img = render_icon_frame(size)
        if size == 256:
            preview_image = img
        frames.append((size, qimage_to_png_bytes(img)))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(build_ico_bytes(frames))

    if preview_path is not None and preview_image is not None:
        preview_path.parent.mkdir(parents=True, exist_ok=True)
        if not preview_image.save(str(preview_path), "PNG"):
            raise RuntimeError(f"Failed to save preview PNG to {preview_path}")

    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate F9Sidebar Sunset Glass .ico")
    parser.add_argument(
        "output",
        nargs="?",
        default=str(DEFAULT_OUTPUT),
        help="Destination path for the generated .ico file.",
    )
    parser.add_argument(
        "--preview",
        default=None,
        help="Optional path to also write a 256x256 PNG preview.",
    )
    args = parser.parse_args()

    out = generate_ico(
        Path(args.output).resolve(),
        Path(args.preview).resolve() if args.preview else None,
    )
    print(f"Generated {out} ({out.stat().st_size:,} bytes, sizes={ICON_SIZES})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
