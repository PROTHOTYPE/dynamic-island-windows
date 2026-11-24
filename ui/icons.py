from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QPen, QPainterPath, QBrush
from PyQt6.QtCore import Qt, QRectF, QPointF


def _screen_dpr() -> float:
    """DPR real do monitor principal (1.0, 1.25, 1.5...) com piso 2x para supersampling nítido."""
    try:
        from PyQt6.QtGui import QGuiApplication
        scr = QGuiApplication.primaryScreen()
        if scr:
            return max(2.0, float(scr.devicePixelRatio()))
    except Exception:
        pass
    return 2.0


class IconFactory:
    """
    Fábrica de Ícones Vetoriais Nativos - PROTO-TYPE Dynamic Island
    Renderiza glifos vetoriais geométricos de alta definição com antialiasing,
    sem recorrer a emojis, arquivos de imagem externos ou fontes proprietárias.
    """

    _cache = {}

    @classmethod
    def get_icon(cls, name: str, size: int = 16, color: str = "#e4e4e7") -> QIcon:
        key = f"{name}_{size}_{color}_2x"
        if key in cls._cache:
            return cls._cache[key]

        dpr = 2
        pix = QPixmap(size * dpr, size * dpr)
        pix.setDevicePixelRatio(float(dpr))
        pix.fill(QColor(0, 0, 0, 0))

        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        c = QColor(color)
        pen = QPen(c, 1.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)

        s = float(size)

        if name == "search":
            p.drawEllipse(QRectF(s * 0.16, s * 0.16, s * 0.50, s * 0.50))
            p.drawLine(QPointF(s * 0.54, s * 0.54), QPointF(s * 0.82, s * 0.82))

        elif name == "home":
            # Telhado
            path = QPainterPath()
            path.moveTo(s * 0.15, s * 0.50)
            path.lineTo(s * 0.50, s * 0.18)
            path.lineTo(s * 0.85, s * 0.50)
            p.drawPath(path)
            # Corpo da casa
            p.drawRect(QRectF(s * 0.26, s * 0.48, s * 0.48, s * 0.36))

        elif name == "play":
            p.setBrush(QBrush(c))
            p.setPen(Qt.PenStyle.NoPen)
            path = QPainterPath()
            path.moveTo(s * 0.28, s * 0.20)
            path.lineTo(s * 0.78, s * 0.50)
            path.lineTo(s * 0.28, s * 0.80)
            path.closeSubpath()
            p.drawPath(path)

        elif name == "pause":
            p.setBrush(QBrush(c))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(QRectF(s * 0.24, s * 0.20, s * 0.18, s * 0.60), 1.5, 1.5)
            p.drawRoundedRect(QRectF(s * 0.58, s * 0.20, s * 0.18, s * 0.60), 1.5, 1.5)

        elif name == "next":
            p.setBrush(QBrush(c))
            p.setPen(Qt.PenStyle.NoPen)
            path = QPainterPath()
            path.moveTo(s * 0.20, s * 0.25)
            path.lineTo(s * 0.60, s * 0.50)
            path.lineTo(s * 0.20, s * 0.75)
            path.closeSubpath()
            p.drawPath(path)
            p.drawRoundedRect(QRectF(s * 0.68, s * 0.25, s * 0.14, s * 0.50), 1.0, 1.0)

        elif name == "prev":
            p.setBrush(QBrush(c))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(QRectF(s * 0.18, s * 0.25, s * 0.14, s * 0.50), 1.0, 1.0)
            path = QPainterPath()
            path.moveTo(s * 0.80, s * 0.25)
            path.lineTo(s * 0.40, s * 0.50)
            path.lineTo(s * 0.80, s * 0.75)
            path.closeSubpath()
            p.drawPath(path)

        elif name == "volume":
            path = QPainterPath()
            path.moveTo(s * 0.18, s * 0.38)
            path.lineTo(s * 0.35, s * 0.38)
            path.lineTo(s * 0.52, s * 0.22)
            path.lineTo(s * 0.52, s * 0.78)
            path.lineTo(s * 0.35, s * 0.62)
            path.lineTo(s * 0.18, s * 0.62)
            path.closeSubpath()
            p.setBrush(QBrush(c))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawPath(path)
            p.setPen(pen)
            p.drawArc(QRectF(s * 0.45, s * 0.30, s * 0.32, s * 0.40), -45 * 16, 90 * 16)

        elif name == "mute":
            path = QPainterPath()
            path.moveTo(s * 0.18, s * 0.38)
            path.lineTo(s * 0.35, s * 0.38)
            path.lineTo(s * 0.52, s * 0.22)
            path.lineTo(s * 0.52, s * 0.78)
            path.lineTo(s * 0.35, s * 0.62)
            path.lineTo(s * 0.18, s * 0.62)
            path.closeSubpath()
            p.setBrush(QBrush(c))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawPath(path)
            p.setPen(pen)
            p.drawLine(QPointF(s * 0.65, s * 0.38), QPointF(s * 0.85, s * 0.62))
            p.drawLine(QPointF(s * 0.85, s * 0.38), QPointF(s * 0.65, s * 0.62))

        elif name == "music":
            # Nota musical estilizada
            path = QPainterPath()
            path.moveTo(s * 0.38, s * 0.25)
            path.lineTo(s * 0.75, s * 0.18)
            path.lineTo(s * 0.75, s * 0.60)
            p.drawPath(path)
            p.setBrush(QBrush(c))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QRectF(s * 0.22, s * 0.56, s * 0.22, s * 0.20))
            p.drawEllipse(QRectF(s * 0.58, s * 0.52, s * 0.22, s * 0.20))

        elif name == "window":
            p.drawRoundedRect(QRectF(s * 0.15, s * 0.18, s * 0.70, s * 0.64), 2.5, 2.5)
            p.drawLine(QPointF(s * 0.15, s * 0.38), QPointF(s * 0.85, s * 0.38))

        elif name == "terminal":
            p.drawRoundedRect(QRectF(s * 0.14, s * 0.16, s * 0.72, s * 0.68), 2.5, 2.5)
            p.drawLine(QPointF(s * 0.28, s * 0.38), QPointF(s * 0.42, s * 0.50))
            p.drawLine(QPointF(s * 0.42, s * 0.50), QPointF(s * 0.28, s * 0.62))
            p.drawLine(QPointF(s * 0.48, s * 0.62), QPointF(s * 0.68, s * 0.62))

        elif name == "code":
            p.drawLine(QPointF(s * 0.38, s * 0.32), QPointF(s * 0.22, s * 0.50))
            p.drawLine(QPointF(s * 0.22, s * 0.50), QPointF(s * 0.38, s * 0.68))
            p.drawLine(QPointF(s * 0.62, s * 0.32), QPointF(s * 0.78, s * 0.50))
            p.drawLine(QPointF(s * 0.78, s * 0.50), QPointF(s * 0.62, s * 0.68))

        elif name == "folder":
            path = QPainterPath()
            path.moveTo(s * 0.15, s * 0.30)
            path.lineTo(s * 0.40, s * 0.30)
            path.lineTo(s * 0.50, s * 0.40)
            path.lineTo(s * 0.85, s * 0.40)
            path.lineTo(s * 0.85, s * 0.75)
            path.lineTo(s * 0.15, s * 0.75)
            path.closeSubpath()
            p.drawPath(path)

        elif name == "taskbar":
            p.drawRoundedRect(QRectF(s * 0.14, s * 0.16, s * 0.72, s * 0.68), 2.5, 2.5)
            p.drawLine(QPointF(s * 0.14, s * 0.66), QPointF(s * 0.86, s * 0.66))

        elif name == "desktop":
            p.drawRoundedRect(QRectF(s * 0.15, s * 0.18, s * 0.70, s * 0.50), 2.0, 2.0)
            p.drawLine(QPointF(s * 0.50, s * 0.68), QPointF(s * 0.50, s * 0.82))
            p.drawLine(QPointF(s * 0.32, s * 0.82), QPointF(s * 0.68, s * 0.82))

        elif name == "close":
            p.drawLine(QPointF(s * 0.25, s * 0.25), QPointF(s * 0.75, s * 0.75))
            p.drawLine(QPointF(s * 0.75, s * 0.25), QPointF(s * 0.25, s * 0.75))

        elif name == "power":
            p.drawArc(QRectF(s * 0.20, s * 0.20, s * 0.60, s * 0.60), 30 * 16, 300 * 16)
            p.drawLine(QPointF(s * 0.50, s * 0.14), QPointF(s * 0.50, s * 0.48))

        elif name == "globe":
            p.drawEllipse(QRectF(s * 0.18, s * 0.18, s * 0.64, s * 0.64))
            p.drawEllipse(QRectF(s * 0.34, s * 0.18, s * 0.32, s * 0.64))
            p.drawLine(QPointF(s * 0.18, s * 0.50), QPointF(s * 0.82, s * 0.50))

        elif name == "gear":
            # Roda dentada concêntrica
            p.drawEllipse(QRectF(s * 0.30, s * 0.30, s * 0.40, s * 0.40))
            for angle in (0, 45, 90, 135):
                rad = angle * 3.14159 / 180.0
                dx = 0.38 * s * 0.5
                dy = 0.38 * s * 0.5
                p.drawLine(
                    QPointF(s * 0.5 + dx, s * 0.5 + dy),
                    QPointF(s * 0.5 - dx, s * 0.5 - dy)
                )

        elif name == "cpu":
            # Chip microprocessador
            p.drawRect(QRectF(s * 0.26, s * 0.26, s * 0.48, s * 0.48))
            # Pinos externos
            p.drawLine(QPointF(s * 0.38, s * 0.14), QPointF(s * 0.38, s * 0.26))
            p.drawLine(QPointF(s * 0.62, s * 0.14), QPointF(s * 0.62, s * 0.26))
            p.drawLine(QPointF(s * 0.38, s * 0.74), QPointF(s * 0.38, s * 0.86))
            p.drawLine(QPointF(s * 0.62, s * 0.74), QPointF(s * 0.62, s * 0.86))
            p.drawLine(QPointF(s * 0.14, s * 0.38), QPointF(s * 0.26, s * 0.38))
            p.drawLine(QPointF(s * 0.14, s * 0.62), QPointF(s * 0.26, s * 0.62))
            p.drawLine(QPointF(s * 0.74, s * 0.38), QPointF(s * 0.86, s * 0.38))
            p.drawLine(QPointF(s * 0.74, s * 0.62), QPointF(s * 0.86, s * 0.62))

        elif name == "ram":
            # Pente de memória
            p.drawRect(QRectF(s * 0.18, s * 0.34, s * 0.64, s * 0.32))
            p.drawLine(QPointF(s * 0.26, s * 0.66), QPointF(s * 0.26, s * 0.78))
            p.drawLine(QPointF(s * 0.42, s * 0.66), QPointF(s * 0.42, s * 0.78))
            p.drawLine(QPointF(s * 0.58, s * 0.66), QPointF(s * 0.58, s * 0.78))
            p.drawLine(QPointF(s * 0.74, s * 0.66), QPointF(s * 0.74, s * 0.78))

        elif name == "disk":
            # Cilindro de disco
            p.drawEllipse(QRectF(s * 0.20, s * 0.20, s * 0.60, s * 0.24))
            p.drawArc(QRectF(s * 0.20, s * 0.40, s * 0.60, s * 0.24), 180 * 16, 180 * 16)
            p.drawArc(QRectF(s * 0.20, s * 0.60, s * 0.60, s * 0.24), 180 * 16, 180 * 16)
            p.drawLine(QPointF(s * 0.20, s * 0.32), QPointF(s * 0.20, s * 0.72))
            p.drawLine(QPointF(s * 0.80, s * 0.32), QPointF(s * 0.80, s * 0.72))

        elif name == "network":
            # Ondas de rede / Wi-Fi
            p.drawArc(QRectF(s * 0.16, s * 0.22, s * 0.68, s * 0.68), 45 * 16, 90 * 16)
            p.drawArc(QRectF(s * 0.28, s * 0.38, s * 0.44, s * 0.44), 45 * 16, 90 * 16)
            p.setBrush(QBrush(c))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QRectF(s * 0.44, s * 0.68, s * 0.12, s * 0.12))

        elif name == "star":
            # Estrela de favoritos
            path = QPainterPath()
            points = [
                QPointF(s * 0.50, s * 0.14),
                QPointF(s * 0.61, s * 0.37),
                QPointF(s * 0.86, s * 0.37),
                QPointF(s * 0.66, s * 0.53),
                QPointF(s * 0.74, s * 0.78),
                QPointF(s * 0.50, s * 0.63),
                QPointF(s * 0.26, s * 0.78),
                QPointF(s * 0.34, s * 0.53),
                QPointF(s * 0.14, s * 0.37),
                QPointF(s * 0.39, s * 0.37),
            ]
            path.moveTo(points[0])
            for pt in points[1:]:
                path.lineTo(pt)
            path.closeSubpath()
            p.drawPath(path)

        elif name == "grid":
            g = s * 0.12
            m = s * 0.16
            sq = (s - 2 * m - g) / 2.0
            p.drawRoundedRect(QRectF(m, m, sq, sq), 1.8, 1.8)
            p.drawRoundedRect(QRectF(m + sq + g, m, sq, sq), 1.8, 1.8)
            p.drawRoundedRect(QRectF(m, m + sq + g, sq, sq), 1.8, 1.8)
            p.drawRoundedRect(QRectF(m + sq + g, m + sq + g, sq, sq), 1.8, 1.8)

        elif name == "moon":
            path = QPainterPath()
            path.addEllipse(QRectF(s * 0.18, s * 0.18, s * 0.64, s * 0.64))
            cut = QPainterPath()
            cut.addEllipse(QRectF(s * 0.36, s * 0.08, s * 0.60, s * 0.60))
            p.drawPath(path.subtracted(cut))

        elif name == "sun":
            p.drawEllipse(QRectF(s * 0.32, s * 0.32, s * 0.36, s * 0.36))
            p.drawLine(QPointF(s * 0.50, s * 0.12), QPointF(s * 0.50, s * 0.22))
            p.drawLine(QPointF(s * 0.50, s * 0.78), QPointF(s * 0.50, s * 0.88))
            p.drawLine(QPointF(s * 0.12, s * 0.50), QPointF(s * 0.22, s * 0.50))
            p.drawLine(QPointF(s * 0.78, s * 0.50), QPointF(s * 0.88, s * 0.50))

        elif name == "clock":
            p.drawEllipse(QRectF(s * 0.16, s * 0.16, s * 0.68, s * 0.68))
            p.drawLine(QPointF(s * 0.50, s * 0.50), QPointF(s * 0.50, s * 0.30))
            p.drawLine(QPointF(s * 0.50, s * 0.50), QPointF(s * 0.66, s * 0.58))

        elif name == "palette":
            p.drawEllipse(QRectF(s * 0.16, s * 0.16, s * 0.68, s * 0.68))
            p.setBrush(QBrush(c))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(s * 0.38, s * 0.38), 1.6, 1.6)
            p.drawEllipse(QPointF(s * 0.62, s * 0.38), 1.6, 1.6)
            p.drawEllipse(QPointF(s * 0.38, s * 0.60), 1.6, 1.6)

        elif name == "check":
            pen_c = QPen(c, 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen_c)
            p.drawLine(QPointF(s * 0.24, s * 0.52), QPointF(s * 0.44, s * 0.72))
            p.drawLine(QPointF(s * 0.44, s * 0.72), QPointF(s * 0.78, s * 0.30))

        else:
            p.setBrush(QBrush(c))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QRectF(s * 0.35, s * 0.35, s * 0.30, s * 0.30))

        p.end()

        icon = QIcon(pix)
        cls._cache[key] = icon
        return icon

    @classmethod
    def get_app_pixmap(cls, kind: str, size: int = 24) -> QPixmap:
        """Renderiza ícones vetoriais coloridos ricos em HiDPI para aplicativos e categorias."""
        from PyQt6.QtGui import QLinearGradient
        key = f"app_pix_{kind}_{size}_2x"
        if key in cls._cache:
            return cls._cache[key]

        dpr = 2
        pix = QPixmap(size * dpr, size * dpr)
        pix.setDevicePixelRatio(float(dpr))
        pix.fill(QColor(0, 0, 0, 0))
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        w = h = float(size)
        rect = QRectF(1.0, 1.0, w - 2.0, h - 2.0)
        r = w * 0.24

        if kind == "folder":
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#D97706"))
            p.drawRoundedRect(QRectF(w * 0.08, h * 0.16, w * 0.42, h * 0.30), 2.5, 2.5)
            grad = QLinearGradient(QPointF(0, h * 0.25), QPointF(0, h * 0.86))
            grad.setColorAt(0.0, QColor("#FCD34D"))
            grad.setColorAt(1.0, QColor("#F59E0B"))
            p.setBrush(grad)
            p.drawRoundedRect(QRectF(w * 0.08, h * 0.26, w * 0.84, h * 0.60), 3.5, 3.5)

        elif kind in ("edge", "globe", "web", "search"):
            grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
            grad.setColorAt(0.0, QColor("#34D399"))
            grad.setColorAt(0.5, QColor("#06B6D4"))
            grad.setColorAt(1.0, QColor("#2563EB"))
            p.setBrush(grad)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(rect.adjusted(1, 1, -1, -1))
            p.setBrush(QColor("#171717"))
            p.drawEllipse(QRectF(w * 0.36, h * 0.34, w * 0.32, h * 0.32))

        elif kind == "vscode":
            p.setPen(QPen(QColor("#38BDF8"), 2.3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            p.setBrush(Qt.BrushStyle.NoBrush)
            path = QPainterPath()
            path.moveTo(w * 0.72, h * 0.18)
            path.lineTo(w * 0.24, h * 0.64)
            path.lineTo(w * 0.14, h * 0.50)
            path.lineTo(w * 0.72, h * 0.82)
            path.lineTo(w * 0.84, h * 0.72)
            path.lineTo(w * 0.84, h * 0.28)
            path.closeSubpath()
            p.drawPath(path)

        elif kind == "media":
            grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
            grad.setColorAt(0.0, QColor("#FB923C"))
            grad.setColorAt(1.0, QColor("#E11D48"))
            p.setBrush(grad)
            p.setPen(QPen(QColor(255, 255, 255, 45), 0.8))
            p.drawRoundedRect(rect, r, r)
            tri = QPainterPath()
            tri.moveTo(w * 0.38, h * 0.28)
            tri.lineTo(w * 0.72, h * 0.50)
            tri.lineTo(w * 0.38, h * 0.72)
            tri.closeSubpath()
            p.setBrush(QColor(255, 255, 255, 245))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawPath(tri)

        elif kind == "photos":
            grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
            grad.setColorAt(0.0, QColor("#818CF8"))
            grad.setColorAt(1.0, QColor("#4F46E5"))
            p.setBrush(grad)
            p.setPen(QPen(QColor(255, 255, 255, 45), 0.8))
            p.drawRoundedRect(rect, r, r)
            p.setBrush(QColor("#FDE047"))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QRectF(w * 0.60, h * 0.24, w * 0.16, h * 0.16))
            mtn = QPainterPath()
            mtn.moveTo(w * 0.16, h * 0.78)
            mtn.lineTo(w * 0.42, h * 0.44)
            mtn.lineTo(w * 0.62, h * 0.65)
            mtn.lineTo(w * 0.74, h * 0.52)
            mtn.lineTo(w * 0.86, h * 0.78)
            mtn.closeSubpath()
            p.setBrush(QColor(255, 255, 255, 215))
            p.drawPath(mtn)

        elif kind == "terminal":
            grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
            grad.setColorAt(0.0, QColor("#334155"))
            grad.setColorAt(1.0, QColor("#171717"))
            p.setBrush(grad)
            p.setPen(QPen(QColor(255, 255, 255, 50), 0.8))
            p.drawRoundedRect(rect, r, r)
            p.setPen(QPen(QColor("#38BDF8"), 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(QPointF(w * 0.28, h * 0.36), QPointF(w * 0.44, h * 0.50))
            p.drawLine(QPointF(w * 0.44, h * 0.50), QPointF(w * 0.28, h * 0.64))
            p.drawLine(QPointF(w * 0.50, h * 0.64), QPointF(w * 0.70, h * 0.64))

        else:  # windows / default app
            grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
            grad.setColorAt(0.0, QColor("#60A5FA"))
            grad.setColorAt(1.0, QColor("#2563EB"))
            p.setBrush(grad)
            p.setPen(QPen(QColor(255, 255, 255, 50), 0.8))
            p.drawRoundedRect(rect, r, r)
            p.setBrush(QColor(255, 255, 255, 240))
            p.setPen(Qt.PenStyle.NoPen)
            m, g = w * 0.24, w * 0.06
            sq = (w - 2 * m - g) / 2.0
            p.drawRoundedRect(QRectF(m, m, sq, sq), 1.2, 1.2)
            p.drawRoundedRect(QRectF(m + sq + g, m, sq, sq), 1.2, 1.2)
            p.drawRoundedRect(QRectF(m, m + sq + g, sq, sq), 1.2, 1.2)
            p.drawRoundedRect(QRectF(m + sq + g, m + sq + g, sq, sq), 1.2, 1.2)

        p.end()
        cls._cache[key] = pix
        return pix

    @classmethod
    def get_app_icon(cls, kind: str, size: int = 24) -> QIcon:
        return QIcon(cls.get_app_pixmap(kind, size))

    @classmethod
    def get_album_art_pixmap(cls, size: int = 84) -> QPixmap:
        from PyQt6.QtGui import QLinearGradient
        key = f"album_art_{size}"
        if key in cls._cache:
            return cls._cache[key]

        d = _screen_dpr()
        pix = QPixmap(int(size * d), int(size * d))
        pix.setDevicePixelRatio(d)
        pix.fill(QColor(0, 0, 0, 0))
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(1.0, 1.0, size - 2.0, size - 2.0)
        r = 12.0 if size > 40 else (size / 2.0)

        path = QPainterPath()
        path.addRoundedRect(rect, r, r)
        p.setClipPath(path)

        grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
        grad.setColorAt(0.0, QColor("#181818"))
        grad.setColorAt(0.55, QColor("#242424"))
        grad.setColorAt(1.0, QColor("#080808"))
        p.fillRect(rect, grad)

        w_path = QPainterPath()
        w_path.moveTo(rect.left(), rect.bottom())
        w_path.cubicTo(
            QPointF(rect.left() + rect.width() * 0.3, rect.top() + rect.height() * 0.4),
            QPointF(rect.left() + rect.width() * 0.7, rect.top() + rect.height() * 0.6),
            QPointF(rect.right(), rect.top() + rect.height() * 0.25)
        )
        w_path.lineTo(rect.right(), rect.bottom())
        w_path.closeSubpath()
        p.fillPath(w_path, QColor(255, 255, 255, 38))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 120), 1.3))
        p.drawPath(w_path)

        p.setClipping(False)
        p.setPen(QPen(QColor(255, 255, 255, 38), 1.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect, r, r)
        p.end()

        cls._cache[key] = pix
        return pix

    @classmethod
    def get_window_preview_pixmap(cls, kind: str, w: int, h: int, is_focused: bool, accent_hex: str, real_thumb=None) -> QPixmap:
        """Renderiza o cartão de pré-visualização visual de janela (DWM sob demanda ou representação vetorial)."""
        from PyQt6.QtGui import QLinearGradient
        d = _screen_dpr()
        pix = QPixmap(int(w * d), int(h * d))
        pix.setDevicePixelRatio(d)
        pix.fill(QColor(0, 0, 0, 0))
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        accent = QColor(accent_hex)
        margin = 6.0 if is_focused else 2.0
        rect = QRectF(margin, margin, w - 2 * margin, h - 2 * margin)
        r = 11.0

        if is_focused:
            for i in range(4, 0, -1):
                sp = i * 1.4
                a = int(48 * (1.0 - i / 5.0))
                p.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), a), 1.8))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(rect.adjusted(-sp, -sp, sp, sp), r + sp * 0.4, r + sp * 0.4)

        grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        grad.setColorAt(0.0, QColor("#1A1A1A") if is_focused else QColor("#131313"))
        grad.setColorAt(1.0, QColor("#0D0D0D") if is_focused else QColor("#0A0A0A"))
        p.setBrush(grad)
        p.setPen(QPen(accent if is_focused else QColor(255, 255, 255, 32), 1.8 if is_focused else 1.0))
        p.drawRoundedRect(rect, r, r)

        # Barra de título da miniatura
        header_h = 16.0
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 12))
        p.drawRoundedRect(QRectF(rect.x() + 1, rect.y() + 1, rect.width() - 2, header_h), r - 1, r - 1)
        dot_y = rect.y() + header_h / 2.0
        p.setBrush(QColor("#64748B"))
        p.drawEllipse(QPointF(rect.x() + 9, dot_y), 2.0, 2.0)
        p.setBrush(QColor("#475569"))
        p.drawEllipse(QPointF(rect.x() + 16, dot_y), 2.0, 2.0)
        p.setBrush(QColor(255, 255, 255, 65))
        p.drawRoundedRect(QRectF(rect.x() + 25, dot_y - 1.8, 32, 3.6), 1.8, 1.8)

        body = QRectF(rect.x() + 5, rect.y() + header_h + 3, rect.width() - 10, rect.height() - header_h - 8)

        if real_thumb is not None and not real_thumb.isNull():
            clip = QPainterPath()
            clip.addRoundedRect(body, 6.0, 6.0)
            p.save()
            p.setClipPath(clip)
            p.drawPixmap(body.toRect(), real_thumb)
            p.restore()
        elif kind == "folder":
            p.setBrush(QColor(255, 255, 255, 18))
            for i in range(4):
                p.drawRoundedRect(QRectF(body.x() + 4, body.y() + 5 + i * 11, 16, 3.5), 1.5, 1.5)
            for i in range(3):
                fy = body.y() + 5 + i * 15
                p.setBrush(QColor("#F59E0B"))
                p.drawRoundedRect(QRectF(body.x() + 28, fy, 11, 8), 2, 2)
                p.setBrush(QColor(255, 255, 255, 65))
                p.drawRoundedRect(QRectF(body.x() + 44, fy + 2, 38 - (i * 5), 3.5), 1.5, 1.5)
        elif kind in ("vscode", "terminal"):
            lines = [
                (0, 26, "#38BDF8"),
                (8, 44, "#94A3B8"),
                (14, 34, "#818CF8"),
                (14, 50, "#34D399"),
                (8, 28, "#F472B6"),
            ]
            for i, (ind, lw, hc) in enumerate(lines):
                ly = body.y() + 5 + i * 9
                if ly + 4 < body.bottom():
                    p.setBrush(QColor(hc))
                    p.drawRoundedRect(QRectF(body.x() + 8 + ind, ly, lw, 3.5), 1.5, 1.5)
        elif kind == "media":
            mg = QLinearGradient(body.topLeft(), body.bottomLeft())
            mg.setColorAt(0.0, QColor("#252525"))
            mg.setColorAt(0.6, QColor("#4C1D95"))
            mg.setColorAt(1.0, QColor("#7C2D12"))
            p.setBrush(mg)
            p.drawRoundedRect(body, 6.0, 6.0)
            tri = QPainterPath()
            cx, cy = body.center().x(), body.center().y()
            tri.moveTo(cx - 5, cy - 7)
            tri.lineTo(cx + 8, cy)
            tri.lineTo(cx - 5, cy + 7)
            tri.closeSubpath()
            p.setBrush(QColor(255, 255, 255, 220))
            p.drawPath(tri)
        else:  # edge / web / default
            clip = QPainterPath()
            clip.addRoundedRect(body, 6.0, 6.0)
            p.save()
            p.setClipPath(clip)
            bg = QLinearGradient(body.topLeft(), body.bottomRight())
            bg.setColorAt(0.0, QColor("#161616"))
            bg.setColorAt(0.6, accent.darker(155))
            bg.setColorAt(1.0, QColor("#0A0A0A"))
            p.fillRect(body, bg)
            wp = QPainterPath()
            wp.moveTo(body.left(), body.bottom())
            wp.cubicTo(
                QPointF(body.left() + body.width() * 0.3, body.top() + body.height() * 0.4),
                QPointF(body.left() + body.width() * 0.7, body.top() + body.height() * 0.6),
                QPointF(body.right(), body.top() + body.height() * 0.25)
            )
            wp.lineTo(body.right(), body.bottom())
            wp.closeSubpath()
            p.fillPath(wp, QColor(accent.red(), accent.green(), accent.blue(), 85))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(accent.lighter(140), 1.2))
            p.drawPath(wp)
            p.restore()

        p.end()
        return pix

    @staticmethod
    def paint_glyph(p: QPainter, name: str, rect: QRectF, color: QColor, stroke_w: float = 1.6):
        """Desenha glifo vetorial nítido centrado em `rect` usando coordenadas lógicas Qt."""
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        cx = rect.center().x()
        cy = rect.center().y()
        s = min(rect.width(), rect.height())
        x0 = cx - s / 2.0
        y0 = cy - s / 2.0
        pen = QPen(color, stroke_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)

        if name == "close":
            d = s * 0.24
            p.drawLine(QPointF(cx - d, cy - d), QPointF(cx + d, cy + d))
            p.drawLine(QPointF(cx + d, cy - d), QPointF(cx - d, cy + d))

        elif name == "back":
            d = s * 0.22
            p.drawLine(QPointF(cx + d * 0.3, cy - d), QPointF(cx - d * 0.7, cy))
            p.drawLine(QPointF(cx - d * 0.7, cy), QPointF(cx + d * 0.3, cy + d))

        elif name == "chevron":
            d = s * 0.20
            p.drawLine(QPointF(cx - d * 0.3, cy - d), QPointF(cx + d * 0.6, cy))
            p.drawLine(QPointF(cx + d * 0.6, cy), QPointF(cx - d * 0.3, cy + d))

        elif name == "gear":
            import math
            p.drawEllipse(QPointF(cx, cy), s * 0.16, s * 0.16)
            r_in, r_out = s * 0.26, s * 0.36
            for deg in range(0, 360, 45):
                rad = math.radians(deg)
                p.drawLine(
                    QPointF(cx + r_in * math.cos(rad), cy + r_in * math.sin(rad)),
                    QPointF(cx + r_out * math.cos(rad), cy + r_out * math.sin(rad)),
                )

        elif name == "refresh":
            r = s * 0.29
            arc_r = QRectF(cx - r, cy - r, r * 2.0, r * 2.0)
            p.drawArc(arc_r, 35 * 16, 285 * 16)
            p.drawLine(QPointF(cx + r * 0.55, cy - r * 0.72), QPointF(cx + r * 0.92, cy - r * 0.35))
            p.drawLine(QPointF(cx + r * 0.92, cy - r * 0.35), QPointF(cx + r * 0.48, cy - r * 0.24))

        elif name == "wifi":
            p.drawArc(QRectF(x0 + s * 0.14, y0 + s * 0.22, s * 0.72, s * 0.72), 45 * 16, 90 * 16)
            p.drawArc(QRectF(x0 + s * 0.27, y0 + s * 0.37, s * 0.46, s * 0.46), 45 * 16, 90 * 16)
            p.setBrush(color)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(cx, y0 + s * 0.72), max(1.4, s * 0.065), max(1.4, s * 0.065))

        elif name == "bluetooth":
            dx = s * 0.16
            dy = s * 0.30
            path = QPainterPath()
            path.moveTo(cx - dx * 0.8, cy - dy * 0.45)
            path.lineTo(cx + dx, cy + dy * 0.45)
            path.lineTo(cx, cy + dy)
            path.lineTo(cx, cy - dy)
            path.lineTo(cx + dx, cy - dy * 0.45)
            path.lineTo(cx - dx * 0.8, cy + dy * 0.45)
            p.drawPath(path)

        elif name == "airplane":
            path = QPainterPath()
            path.moveTo(cx, y0 + s * 0.16)
            path.lineTo(cx, y0 + s * 0.84)
            p.drawPath(path)
            p.drawLine(QPointF(x0 + s * 0.20, cy + s * 0.02), QPointF(cx, cy - s * 0.14))
            p.drawLine(QPointF(x0 + s * 0.80, cy + s * 0.02), QPointF(cx, cy - s * 0.14))
            p.drawLine(QPointF(cx - s * 0.14, y0 + s * 0.78), QPointF(cx + s * 0.14, y0 + s * 0.78))

        elif name == "nightlight":
            outer = QPainterPath()
            outer.addEllipse(QRectF(x0 + s * 0.20, y0 + s * 0.20, s * 0.60, s * 0.60))
            cut = QPainterPath()
            cut.addEllipse(QRectF(x0 + s * 0.38, y0 + s * 0.12, s * 0.54, s * 0.54))
            p.setBrush(color)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawPath(outer.subtracted(cut))

        elif name == "battery_saver":
            p.drawRoundedRect(QRectF(x0 + s * 0.22, y0 + s * 0.30, s * 0.50, s * 0.40), 2.5, 2.5)
            p.drawLine(QPointF(x0 + s * 0.74, y0 + s * 0.42), QPointF(x0 + s * 0.74, y0 + s * 0.58))
            p.setBrush(color)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(QRectF(x0 + s * 0.28, y0 + s * 0.37, s * 0.24, s * 0.26), 1.2, 1.2)

        elif name == "hotspot":
            p.drawArc(QRectF(x0 + s * 0.18, y0 + s * 0.22, s * 0.64, s * 0.64), -35 * 16, 250 * 16)
            p.drawLine(QPointF(cx, cy), QPointF(cx, y0 + s * 0.78))
            p.setBrush(color)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(cx, cy), s * 0.08, s * 0.08)

        elif name == "volume":
            body = QPainterPath()
            body.moveTo(x0 + s * 0.20, y0 + s * 0.39)
            body.lineTo(x0 + s * 0.34, y0 + s * 0.39)
            body.lineTo(x0 + s * 0.50, y0 + s * 0.24)
            body.lineTo(x0 + s * 0.50, y0 + s * 0.76)
            body.lineTo(x0 + s * 0.34, y0 + s * 0.61)
            body.lineTo(x0 + s * 0.20, y0 + s * 0.61)
            body.closeSubpath()
            p.setBrush(color)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawPath(body)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawArc(QRectF(x0 + s * 0.44, y0 + s * 0.31, s * 0.30, s * 0.38), -45 * 16, 90 * 16)
            p.drawArc(QRectF(x0 + s * 0.42, y0 + s * 0.21, s * 0.42, s * 0.58), -45 * 16, 90 * 16)

        elif name == "mute":
            body = QPainterPath()
            body.moveTo(x0 + s * 0.18, y0 + s * 0.39)
            body.lineTo(x0 + s * 0.32, y0 + s * 0.39)
            body.lineTo(x0 + s * 0.48, y0 + s * 0.24)
            body.lineTo(x0 + s * 0.48, y0 + s * 0.76)
            body.lineTo(x0 + s * 0.32, y0 + s * 0.61)
            body.lineTo(x0 + s * 0.18, y0 + s * 0.61)
            body.closeSubpath()
            p.setBrush(color)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawPath(body)
            p.setPen(pen)
            p.drawLine(QPointF(x0 + s * 0.60, y0 + s * 0.38), QPointF(x0 + s * 0.82, y0 + s * 0.62))
            p.drawLine(QPointF(x0 + s * 0.82, y0 + s * 0.38), QPointF(x0 + s * 0.60, y0 + s * 0.62))

        elif name == "brightness":
            import math
            p.drawEllipse(QPointF(cx, cy), s * 0.17, s * 0.17)
            r_in, r_out = s * 0.27, s * 0.37
            for deg in range(0, 360, 45):
                rad = math.radians(deg)
                p.drawLine(
                    QPointF(cx + r_in * math.cos(rad), cy + r_in * math.sin(rad)),
                    QPointF(cx + r_out * math.cos(rad), cy + r_out * math.sin(rad)),
                )

        elif name == "headphones":
            p.drawArc(QRectF(x0 + s * 0.20, y0 + s * 0.20, s * 0.60, s * 0.56), 0, 180 * 16)
            p.setBrush(color)
            p.drawRoundedRect(QRectF(x0 + s * 0.18, y0 + s * 0.48, s * 0.14, s * 0.28), 3.0, 3.0)
            p.drawRoundedRect(QRectF(x0 + s * 0.68, y0 + s * 0.48, s * 0.14, s * 0.28), 3.0, 3.0)

        elif name == "screen":
            p.drawRoundedRect(QRectF(x0 + s * 0.16, y0 + s * 0.22, s * 0.68, s * 0.46), 2.5, 2.5)
            p.drawLine(QPointF(cx, y0 + s * 0.68), QPointF(cx, y0 + s * 0.80))
            p.drawLine(QPointF(x0 + s * 0.34, y0 + s * 0.80), QPointF(x0 + s * 0.66, y0 + s * 0.80))

        elif name == "speaker":
            p.drawRoundedRect(QRectF(x0 + s * 0.26, y0 + s * 0.16, s * 0.48, s * 0.68), 3.0, 3.0)
            p.drawEllipse(QPointF(cx, y0 + s * 0.58), s * 0.12, s * 0.12)
            p.setBrush(color)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(cx, y0 + s * 0.32), s * 0.05, s * 0.05)

        elif name == "music":
            p.drawLine(QPointF(x0 + s * 0.38, y0 + s * 0.26), QPointF(x0 + s * 0.74, y0 + s * 0.18))
            p.drawLine(QPointF(x0 + s * 0.38, y0 + s * 0.26), QPointF(x0 + s * 0.38, y0 + s * 0.66))
            p.drawLine(QPointF(x0 + s * 0.74, y0 + s * 0.18), QPointF(x0 + s * 0.74, y0 + s * 0.58))
            p.setBrush(color)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(x0 + s * 0.30, y0 + s * 0.68), s * 0.11, s * 0.09)
            p.drawEllipse(QPointF(x0 + s * 0.66, y0 + s * 0.60), s * 0.11, s * 0.09)

        elif name == "play":
            tri = QPainterPath()
            tri.moveTo(x0 + s * 0.30, y0 + s * 0.22)
            tri.lineTo(x0 + s * 0.78, cy)
            tri.lineTo(x0 + s * 0.30, y0 + s * 0.78)
            tri.closeSubpath()
            p.setBrush(color)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawPath(tri)

        elif name == "pause":
            p.setBrush(color)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(QRectF(x0 + s * 0.26, y0 + s * 0.22, s * 0.17, s * 0.56), 1.5, 1.5)
            p.drawRoundedRect(QRectF(x0 + s * 0.57, y0 + s * 0.22, s * 0.17, s * 0.56), 1.5, 1.5)

        elif name == "next":
            tri = QPainterPath()
            tri.moveTo(x0 + s * 0.22, y0 + s * 0.26)
            tri.lineTo(x0 + s * 0.60, cy)
            tri.lineTo(x0 + s * 0.22, y0 + s * 0.74)
            tri.closeSubpath()
            p.setBrush(color)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawPath(tri)
            p.drawRoundedRect(QRectF(x0 + s * 0.66, y0 + s * 0.26, s * 0.12, s * 0.48), 1.2, 1.2)

        elif name == "prev":
            tri = QPainterPath()
            tri.moveTo(x0 + s * 0.78, y0 + s * 0.26)
            tri.lineTo(x0 + s * 0.40, cy)
            tri.lineTo(x0 + s * 0.78, y0 + s * 0.74)
            tri.closeSubpath()
            p.setBrush(color)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawPath(tri)
            p.drawRoundedRect(QRectF(x0 + s * 0.22, y0 + s * 0.26, s * 0.12, s * 0.48), 1.2, 1.2)

        elif name == "check":
            p.drawLine(QPointF(x0 + s * 0.22, cy), QPointF(x0 + s * 0.42, y0 + s * 0.70))
            p.drawLine(QPointF(x0 + s * 0.42, y0 + s * 0.70), QPointF(x0 + s * 0.78, y0 + s * 0.28))

        else:
            p.setBrush(color)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(cx, cy), s * 0.12, s * 0.12)

        p.restore()
