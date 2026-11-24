"""
Gerador do ícone oficial Monolith (build/monolith.ico).
Renderiza frames multi-resolução via PyQt6 QPainter e empacota como ICO nativo do Windows.
"""

import os
import struct
import sys

from PyQt6.QtCore import Qt, QBuffer, QIODevice, QRectF, QPointF
from PyQt6.QtGui import QImage, QPainter, QColor, QPen, QLinearGradient, QBrush
from PyQt6.QtWidgets import QApplication


def render_monolith_frame(size: int) -> bytes:
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(QColor(0, 0, 0, 0))

    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    s = float(size)
    margin = max(1.0, s * 0.06)
    rect = QRectF(margin, margin, s - 2.0 * margin, s - 2.0 * margin)
    r = s * 0.24

    # Fundo Grafite/Obsidiana Monolith
    grad = QLinearGradient(0, 0, 0, s)
    grad.setColorAt(0.0, QColor("#151B2B"))
    grad.setColorAt(0.55, QColor("#0B0E17"))
    grad.setColorAt(1.0, QColor("#05070C"))
    p.setBrush(grad)

    stroke = QLinearGradient(0, 0, 0, s)
    stroke.setColorAt(0.0, QColor(255, 255, 255, 70))
    stroke.setColorAt(0.5, QColor(62, 145, 247, 130))
    stroke.setColorAt(1.0, QColor(62, 145, 247, 200))
    pen_w = max(1.0, s * 0.032)
    p.setPen(QPen(QBrush(stroke), pen_w))
    p.drawRoundedRect(rect, r, r)

    # Cápsula OLED Stealth central no topo do ícone
    cap_w = s * 0.58
    cap_h = max(4.0, s * 0.19)
    cap_r = cap_h / 2.0
    cap_rect = QRectF((s - cap_w) / 2.0, s * 0.22, cap_w, cap_h)
    p.setBrush(QColor("#000000"))
    p.setPen(QPen(QColor(255, 255, 255, 45), max(0.8, s * 0.015)))
    p.drawRoundedRect(cap_rect, cap_r, cap_r)

    # Micro indicador Safira
    dot_r = max(1.2, cap_h * 0.22)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#3E91F7"))
    p.drawEllipse(QPointF(cap_rect.left() + cap_h * 0.45, cap_rect.center().y()), dot_r, dot_r)

    # Barra sutil representando o painel inferior Monolith
    bar_w = s * 0.56
    bar_h = max(3.0, s * 0.14)
    bar_rect = QRectF((s - bar_w) / 2.0, s * 0.56, bar_w, bar_h)
    p.setBrush(QColor(62, 145, 247, 75))
    p.setPen(QPen(QColor(92, 163, 250, 175), max(0.8, s * 0.015)))
    p.drawRoundedRect(bar_rect, bar_h / 2.0, bar_h / 2.0)

    p.end()

    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return bytes(buf.data())


def build_ico(output_path: str, sizes=(16, 24, 32, 48, 64, 128, 256)):
    frames = [(sz, render_monolith_frame(sz)) for sz in sizes]
    count = len(frames)

    header = struct.pack("<HHH", 0, 1, count)
    offset = 6 + count * 16
    entries = bytearray()
    payload = bytearray()

    for sz, png_bytes in frames:
        w_byte = 0 if sz >= 256 else sz
        h_byte = 0 if sz >= 256 else sz
        entry = struct.pack(
            "<BBBBHHII",
            w_byte,
            h_byte,
            0,      # color count
            0,      # reserved
            1,      # planes
            32,     # bpp
            len(png_bytes),
            offset,
        )
        entries.extend(entry)
        payload.extend(png_bytes)
        offset += len(png_bytes)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(header)
        f.write(entries)
        f.write(payload)


if __name__ == "__main__":
    app = QApplication.instance() or QApplication(sys.argv)
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "monolith.ico")
    build_ico(out)
    print(f"Icon generated: {out} ({os.path.getsize(out)} bytes)")
