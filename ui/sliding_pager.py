"""
Navegador de painéis deslizantes horizontais do Monolith (SlidingPager).
Substitui a troca abrupta de abas por um viewport contínuo com:
- Ordem linear: INÍCIO (0) -> JANELAS (1) -> SISTEMA (2)
- Animação horizontal fluida (OutCubic, ~210 ms) respeitando movimento reduzido
- Reconhecimento contextual de arraste horizontal que não interfere com QLineEdit,
  QScrollBar, cliques em botões ou rolagem vertical
- Suporte a gesto horizontal de touchpad (wheelEvent no eixo X)
"""

import time
from PyQt6.QtCore import (
    Qt, QPointF, QRectF, QEvent, QVariantAnimation, QEasingCurve, pyqtSignal, QTimer
)
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QCursor
from PyQt6.QtWidgets import (
    QWidget, QLineEdit, QAbstractSlider, QScrollBar, QAbstractButton, QApplication
)

from ui.theme import Theme


class PagerIndicatorBar(QWidget):
    """Indicador superior discreto de posição entre os painéis (Início • Janelas • Sistema)."""

    page_requested = pyqtSignal(int)

    def __init__(self, labels: list[str], parent=None):
        super().__init__(parent)
        self._labels = list(labels)
        self._current_index = 0
        self._progress_index = 0.0
        self._hovered_idx = -1
        self.setFixedHeight(24)
        self.setMouseTracking(True)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._hit_rects: list[QRectF] = []

    def set_progress(self, fractional_index: float):
        self._progress_index = max(0.0, min(float(len(self._labels) - 1), float(fractional_index)))
        self._current_index = int(round(self._progress_index))
        self.update()

    def set_current_index(self, idx: int):
        self._current_index = max(0, min(len(self._labels) - 1, int(idx)))
        self._progress_index = float(self._current_index)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        font = Theme.get_font(8.8, QFont.Weight.DemiBold)
        p.setFont(font)
        fm = p.fontMetrics()

        spacing = 20.0
        item_widths = [float(fm.horizontalAdvance(lbl) + 22) for lbl in self._labels]
        total_w = sum(item_widths) + spacing * (len(self._labels) - 1)
        start_x = (self.width() - total_w) / 2.0
        h = float(self.height())

        self._hit_rects.clear()
        x = start_x
        for i, lbl in enumerate(self._labels):
            iw = item_widths[i]
            r = QRectF(x, 1.0, iw, h - 2.0)
            self._hit_rects.append(r)

            dist = abs(self._progress_index - float(i))
            active_ratio = max(0.0, 1.0 - dist)

            if active_ratio > 0.05:
                bg_alpha = int(round(26 * active_ratio))
                brd_alpha = int(round(48 * active_ratio))
                p.setBrush(QColor(255, 255, 255, bg_alpha))
                p.setPen(QPen(QColor(255, 255, 255, brd_alpha), 1.0))
                p.drawRoundedRect(r, 7.0, 7.0)
            elif i == self._hovered_idx:
                p.setBrush(QColor(255, 255, 255, 12))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawRoundedRect(r, 7.0, 7.0)

            # Ponto indicador minimalista + rótulo
            dot_r = 2.2
            dot_x = r.left() + 8.5
            dot_y = r.center().y()
            dot_col = QColor(Theme.HEX_TEXT_PRIMARY) if active_ratio > 0.5 else QColor(Theme.HEX_TEXT_MUTED)
            dot_col.setAlpha(int(110 + 145 * active_ratio))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(dot_col)
            p.drawEllipse(QPointF(dot_x, dot_y), dot_r, dot_r)

            txt_col = QColor(Theme.HEX_TEXT_PRIMARY) if active_ratio > 0.45 else (
                QColor(Theme.HEX_TEXT_SECONDARY) if i == self._hovered_idx else QColor(Theme.HEX_TEXT_MUTED)
            )
            p.setPen(txt_col)
            txt_rect = QRectF(r.left() + 14.0, r.top(), r.width() - 18.0, r.height())
            p.drawText(txt_rect, Qt.AlignmentFlag.AlignCenter, lbl)

            x += iw + spacing
        p.end()

    def mouseMoveEvent(self, event):
        pos = event.position()
        hov = -1
        for i, r in enumerate(self._hit_rects):
            if r.contains(pos):
                hov = i
                break
        if hov != self._hovered_idx:
            self._hovered_idx = hov
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        if self._hovered_idx != -1:
            self._hovered_idx = -1
            self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position()
            for i, r in enumerate(self._hit_rects):
                if r.contains(pos):
                    self.page_requested.emit(i)
                    event.accept()
                    return
        super().mousePressEvent(event)


class SlidingPager(QWidget):
    """
    Container de páginas horizontais com animação contínua e suporte a gestos contextuais.
    Compatível com a interface essencial de QStackedWidget (addWidget, currentIndex, setCurrentIndex, count, widget).
    """

    currentChanged = pyqtSignal(int)
    progressChanged = pyqtSignal(float)  # índice fracionário durante animação/arraste (0.0 .. 2.0)

    DRAG_LOCK_PX = 14.0
    DRAG_DIRECTION_RATIO = 1.65
    COMMIT_FRACTION = 0.22
    VELOCITY_COMMIT_PX_S = 420.0
    ANIM_DURATION_MS = 210

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._pages: list[QWidget] = []
        self._current_index: int = 0
        self._offset_px: float = 0.0  # deslocamento do strip (negativo = avançou para a direita)

        # Estado de gesto contextual
        self._tracking_press = False
        self._dragging_horiz = False
        self._locked_vertical = False
        self._press_global = QPointF()
        self._start_offset = 0.0
        self._press_time = 0.0
        self._pressed_child: QWidget | None = None

        # Cooldown de gesto de touchpad
        self._wheel_accum_x = 0.0
        self._last_wheel_step_ts = 0.0

        self._anim = QVariantAnimation(self)
        self._anim.setDuration(self.ANIM_DURATION_MS)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_anim_value)
        self._anim.finished.connect(self._on_anim_finished)

        app = QApplication.instance()
        if app:
            app.installEventFilter(self)

    # ---------------------------------------------------- QStackedWidget API
    def addWidget(self, page: QWidget) -> int:
        page.setParent(self)
        page.show()
        self._pages.append(page)
        self._layout_pages()
        return len(self._pages) - 1

    def count(self) -> int:
        return len(self._pages)

    def widget(self, idx: int) -> QWidget | None:
        if 0 <= idx < len(self._pages):
            return self._pages[idx]
        return None

    def currentIndex(self) -> int:
        return self._current_index

    def currentWidget(self) -> QWidget | None:
        return self.widget(self._current_index)

    def setCurrentIndex(self, idx: int, animate: bool = True):
        if not self._pages:
            return
        target = max(0, min(len(self._pages) - 1, int(idx)))
        changed = (target != self._current_index)
        self._current_index = target
        target_offset = -float(target * max(1, self.width()))

        self._anim.stop()
        if not animate or Theme.reduced_motion_enabled() or not self.isVisible() or abs(self._offset_px - target_offset) < 1.0:
            self._offset_px = target_offset
            self._layout_pages()
            self._emit_progress()
            if changed:
                self.currentChanged.emit(self._current_index)
            return

        for p in self._pages:
            p.show()
        self._anim.setDuration(self.ANIM_DURATION_MS)
        self._anim.setStartValue(float(self._offset_px))
        self._anim.setEndValue(float(target_offset))
        self._anim.start()
        if changed:
            self.currentChanged.emit(self._current_index)

    def next_page(self, animate: bool = True):
        if self._current_index < len(self._pages) - 1:
            self.setCurrentIndex(self._current_index + 1, animate=animate)

    def prev_page(self, animate: bool = True):
        if self._current_index > 0:
            self.setCurrentIndex(self._current_index - 1, animate=animate)

    # --------------------------------------------------------- layout & anim
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._anim.state() != QVariantAnimation.State.Running and not self._dragging_horiz:
            self._offset_px = -float(self._current_index * max(1, self.width()))
        self._layout_pages()

    def _on_anim_value(self, val):
        self._offset_px = float(val)
        self._layout_pages()
        self._emit_progress()

    def _on_anim_finished(self):
        self._offset_px = -float(self._current_index * max(1, self.width()))
        self._layout_pages()
        self._emit_progress()

    def _emit_progress(self):
        w = max(1.0, float(self.width()))
        frac = -self._offset_px / w
        self.progressChanged.emit(max(0.0, min(float(max(0, len(self._pages) - 1)), frac)))

    def _layout_pages(self):
        w = max(1, self.width())
        h = max(1, self.height())
        base_x = int(round(self._offset_px))
        for i, page in enumerate(self._pages):
            px = base_x + i * w
            page.setGeometry(px, 0, w, h)
            # Mantém visíveis todas as páginas que intersectam o viewport (ou durante transição)
            intersects = (px + w > 0) and (px < w)
            if intersects or i == self._current_index:
                if not page.isVisible():
                    page.show()
            else:
                if page.isVisible() and self._anim.state() != QVariantAnimation.State.Running and not self._dragging_horiz:
                    page.hide()

    # ------------------------------------------------ contextual gesture filter
    def _is_excluded_target(self, w: QWidget | None) -> bool:
        """Não inicia arraste de página quando o foco é caixa de texto, barra de rolagem ou controle com drag próprio."""
        cur = w
        while cur is not None and cur is not self:
            if isinstance(cur, (QLineEdit, QAbstractSlider, QScrollBar)):
                return True
            if bool(cur.property("no_pager_swipe")):
                return True
            cur = cur.parentWidget()
        return False

    def _belongs_to_pager(self, w: QWidget | None) -> bool:
        cur = w
        while cur is not None:
            if cur is self:
                return True
            cur = cur.parentWidget()
        return False

    def eventFilter(self, obj, event):
        if not self.isVisible() or len(self._pages) <= 1 or not isinstance(obj, QWidget):
            return False

        et = event.type()
        if et == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            if not self._belongs_to_pager(obj) or self._is_excluded_target(obj):
                return False
            self._tracking_press = True
            self._dragging_horiz = False
            self._locked_vertical = False
            self._press_global = event.globalPosition()
            self._start_offset = float(self._offset_px)
            self._press_time = time.monotonic()
            self._pressed_child = obj
            return False

        if et == QEvent.Type.MouseMove and self._tracking_press:
            if self._locked_vertical:
                return False
            delta = event.globalPosition() - self._press_global
            dx = float(delta.x())
            dy = float(delta.y())

            if not self._dragging_horiz:
                # Se moveu verticalmente primeiro, preserva scroll vertical e cancela rastreio horizontal
                if abs(dy) > 10.0 and abs(dy) >= abs(dx):
                    self._locked_vertical = True
                    return False
                if abs(dx) >= self.DRAG_LOCK_PX and abs(dx) >= abs(dy) * self.DRAG_DIRECTION_RATIO:
                    self._dragging_horiz = True
                    self._anim.stop()
                    for p in self._pages:
                        p.show()
                    # Desarma eventual botão pressionado para não disparar clique ao soltar o arraste
                    if isinstance(self._pressed_child, QAbstractButton):
                        self._pressed_child.setDown(False)

            if self._dragging_horiz:
                w = float(max(1, self.width()))
                min_off = -float((len(self._pages) - 1) * w)
                max_off = 0.0
                raw = self._start_offset + dx
                # Resistência elástica suave nas extremidades
                if raw > max_off:
                    raw = max_off + (raw - max_off) * 0.25
                elif raw < min_off:
                    raw = min_off + (raw - min_off) * 0.25
                self._offset_px = raw
                self._layout_pages()
                self._emit_progress()
                return True

        if et == QEvent.Type.MouseButtonRelease and self._tracking_press:
            was_dragging = self._dragging_horiz
            self._tracking_press = False
            self._dragging_horiz = False
            self._locked_vertical = False
            self._pressed_child = None
            if was_dragging:
                delta = event.globalPosition() - self._press_global
                dx = float(delta.x())
                dt = max(0.015, time.monotonic() - self._press_time)
                vx = dx / dt
                w = float(max(1, self.width()))

                target = self._current_index
                if dx <= -w * self.COMMIT_FRACTION or vx <= -self.VELOCITY_COMMIT_PX_S:
                    target = min(len(self._pages) - 1, self._current_index + 1)
                elif dx >= w * self.COMMIT_FRACTION or vx >= self.VELOCITY_COMMIT_PX_S:
                    target = max(0, self._current_index - 1)
                self.setCurrentIndex(target, animate=True)
                return True

        if et == QEvent.Type.Wheel and self._belongs_to_pager(obj):
            if self._is_excluded_target(obj):
                return False
            ad = event.angleDelta()
            ax, ay = float(ad.x()), float(ad.y())
            if abs(ax) > abs(ay) * 1.5 and abs(ax) > 8.0:
                now = time.monotonic()
                if now - self._last_wheel_step_ts < 0.32:
                    return True
                self._wheel_accum_x += ax
                if self._wheel_accum_x <= -90.0:
                    self._wheel_accum_x = 0.0
                    self._last_wheel_step_ts = now
                    self.next_page(animate=True)
                    return True
                if self._wheel_accum_x >= 90.0:
                    self._wheel_accum_x = 0.0
                    self._last_wheel_step_ts = now
                    self.prev_page(animate=True)
                    return True
            else:
                self._wheel_accum_x = 0.0

        return False
