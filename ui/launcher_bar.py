"""
Barra permanente de Launcher e Pesquisa (LauncherBar) + Popup contextual sobreposto.
Substitui a antiga página dedicada de Launcher e o dock inferior de abas, permanecendo
acessível em qualquer painel (Início, Janelas ou Sistema) sem abandonar a página atual.
"""

from PyQt6.QtCore import Qt, QEvent, QSize, pyqtSignal
from PyQt6.QtGui import QCursor, QFont
from PyQt6.QtWidgets import (
    QWidget, QFrame, QHBoxLayout, QVBoxLayout, QLineEdit, QLabel, QPushButton
)

from core.app_indexer import AppIndexer
from ui.icons import IconFactory
from ui.theme import Theme


class LauncherOverlayPopup(QFrame):
    """Painel sobreposto de resultados do Launcher ancorado logo acima da barra inferior."""

    app_launched = pyqtSignal(str)
    filter_changed = pyqtSignal(str)
    dismiss_requested = pyqtSignal()

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("launcher_overlay_popup")
        self.setProperty("no_pager_swipe", True)
        self.hide()

        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(12, 10, 12, 10)
        self._main_layout.setSpacing(6)

        # Cabeçalho compacto com filtros rápidos + dica de teclado
        hdr = QHBoxLayout()
        hdr.setContentsMargins(0, 0, 0, 2)
        hdr.setSpacing(6)

        self.filter_buttons: list[tuple[str, QPushButton]] = []
        for f_id, f_title, f_ic in [
            ("all", "Todos", "grid"),
            ("fav", "Favoritos", "star"),
            ("sys", "Sistema", "clock"),
        ]:
            fbtn = QPushButton(f" {f_title}")
            fbtn.setFont(Theme.get_font(8.8, QFont.Weight.Medium))
            fbtn.setIcon(IconFactory.get_icon(f_ic, 11, Theme.HEX_TEXT_SECONDARY))
            fbtn.setIconSize(QSize(11, 11))
            fbtn.setMinimumHeight(24)
            fbtn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            fbtn.clicked.connect(lambda checked=False, fid=f_id: self.filter_changed.emit(fid))
            hdr.addWidget(fbtn)
            self.filter_buttons.append((f_id, fbtn))

        hdr.addStretch()
        self.lbl_hint = QLabel("↑↓ Navegar  •  ↵ Abrir  •  Esc Fechar")
        self.lbl_hint.setFont(Theme.get_font(8.5, QFont.Weight.Normal))
        hdr.addWidget(self.lbl_hint)
        self._main_layout.addLayout(hdr)

        # Container das linhas de resultado
        self.rows_container = QWidget()
        self.rows_container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.rows_layout = QVBoxLayout(self.rows_container)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(4)
        self._main_layout.addWidget(self.rows_container)

        self.apply_theme("all")

    def apply_theme(self, active_filter: str = "all"):
        self.setStyleSheet(
            f"QFrame#launcher_overlay_popup {{ "
            f"  background-color: #0B0B0B; "
            f"  border: 1px solid rgba(255, 255, 255, 0.14); "
            f"  border-radius: 14px; "
            f"}}"
        )
        self.lbl_hint.setStyleSheet(
            f"color: {Theme.HEX_TEXT_MUTED}; border: none; background: transparent;"
        )
        for fid, fbtn in self.filter_buttons:
            fbtn.setStyleSheet(Theme.style_filter_pill(fid == active_filter))


class LauncherBar(QWidget):
    """
    Barra inferior permanente de pesquisa de aplicativos.
    Integra campo de busca, atalhos rápidos e controle do popup de resultados sobreposto.
    """

    app_launched = pyqtSignal(str)

    def __init__(self, overlay_parent: QWidget, parent: QWidget | None = None):
        super().__init__(parent)
        self.setProperty("no_pager_swipe", True)
        self.setMinimumHeight(40)
        self.setMaximumHeight(42)

        self._overlay_parent = overlay_parent
        self.popup = LauncherOverlayPopup(overlay_parent)
        self.popup.app_launched.connect(self._on_launch)
        self.popup.filter_changed.connect(self.set_filter)

        self.results: list[dict] = []
        self.selected_idx: int = 0
        self.launcher_filter: str = "all"

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 0)
        layout.setSpacing(8)

        # Campo de pesquisa integrado
        self.search_input = QLineEdit()
        self.search_input.setProperty("no_pager_swipe", True)
        self.search_input.setPlaceholderText("Pesquisar aplicativos ou comandos...")
        self.search_input.setMinimumHeight(36)
        self.search_input.setFont(Theme.get_font(9.8, QFont.Weight.Normal))
        self.search_input.textChanged.connect(self._on_text_changed)
        self.search_input.installEventFilter(self)

        self.search_icon_lbl = QLabel(self.search_input)
        self.search_icon_lbl.setGeometry(11, 10, 16, 16)
        self.search_icon_lbl.setStyleSheet("border: none; background: transparent;")
        self.search_icon_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        layout.addWidget(self.search_input, stretch=1)

        # Botão discreto para abrir/fechar a lista de aplicativos mesmo sem digitar
        self.btn_browse = QPushButton("  Aplicativos")
        self.btn_browse.setProperty("no_pager_swipe", True)
        self.btn_browse.setFont(Theme.get_font(9.0, QFont.Weight.DemiBold))
        self.btn_browse.setIcon(IconFactory.get_icon("grid", 12, Theme.HEX_TEXT_SECONDARY))
        self.btn_browse.setIconSize(QSize(12, 12))
        self.btn_browse.setMinimumHeight(36)
        self.btn_browse.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_browse.clicked.connect(self.toggle_popup)
        layout.addWidget(self.btn_browse)

        self.apply_theme()
        self.update_results("", show_popup=False)

    # ------------------------------------------------------------------ theme
    def apply_theme(self):
        self.search_input.setStyleSheet(Theme.style_search_input())
        self.search_icon_lbl.setPixmap(
            IconFactory.get_icon("search", 15, Theme.HEX_TEXT_SECONDARY).pixmap(15, 15)
        )
        is_open = self.popup.isVisible()
        self.btn_browse.setStyleSheet(Theme.style_dock_squircle(is_open))
        self.btn_browse.setIcon(
            IconFactory.get_icon("grid", 12, Theme.HEX_TEXT_PRIMARY if is_open else Theme.HEX_TEXT_SECONDARY)
        )
        self.popup.apply_theme(self.launcher_filter)
        self.render_rows()

    # ---------------------------------------------------------- popup control
    def is_popup_open(self) -> bool:
        return self.popup.isVisible()

    def open_popup(self):
        self.update_results(self.search_input.text(), show_popup=True)
        self._reposition_popup()
        self.popup.show()
        self.popup.raise_()
        self.apply_theme()

    def close_popup(self, clear_text: bool = False):
        if clear_text and self.search_input.text():
            self.search_input.blockSignals(True)
            self.search_input.clear()
            self.search_input.blockSignals(False)
            self.update_results("", show_popup=False)
        self.popup.hide()
        self.search_input.clearFocus()
        self.apply_theme()

    def toggle_popup(self):
        if self.popup.isVisible():
            self.close_popup(clear_text=False)
        else:
            self.open_popup()
            self.search_input.setFocus()

    def _reposition_popup(self):
        if not self._overlay_parent:
            return
        pw = self._overlay_parent.width()
        ph = self._overlay_parent.height()
        margin_x = 20
        row_count = max(1, min(4, len(self.results)))
        popup_h = 46 + row_count * 40
        bar_top = ph - self.height() - 18
        popup_y = max(44, bar_top - popup_h - 6)
        self.popup.setGeometry(margin_x, popup_y, max(200, pw - 2 * margin_x), popup_h)

    # --------------------------------------------------------- search & rows
    def set_filter(self, fid: str):
        self.launcher_filter = fid
        self.popup.apply_theme(fid)
        self.update_results(self.search_input.text(), show_popup=True)

    def _on_text_changed(self, text: str):
        stripped = text.strip()
        self.update_results(text, show_popup=bool(stripped) or self.popup.isVisible())
        if not stripped and not self.search_input.hasFocus():
            self.popup.hide()

    def update_results(self, query: str, show_popup: bool = False):
        raw = AppIndexer.search(query)
        if self.launcher_filter == "sys":
            filtered = [
                r for r in raw
                if "sistema" in r.get("category", "").lower() or "util" in r.get("category", "").lower()
            ]
            self.results = (filtered if filtered else raw)[:4]
        elif self.launcher_filter == "fav":
            fav_names = {"explorador", "configurações", "navegador", "vs code", "terminal", "gerenciador"}
            filtered = [r for r in raw if any(k in r.get("name", "").lower() for k in fav_names)]
            self.results = (filtered if filtered else raw)[:4]
        else:
            self.results = raw[:4]
        self.selected_idx = 0
        self.render_rows()
        if show_popup:
            self._reposition_popup()
            if not self.popup.isVisible():
                self.popup.show()
                self.popup.raise_()
                self.btn_browse.setStyleSheet(Theme.style_dock_squircle(True))

    @staticmethod
    def classify_icon(app: dict) -> str:
        if app.get("type") in ("web", "search"):
            return "edge"
        name_l = app.get("name", "").lower()
        cmd_l = app.get("cmd", "").lower()
        if "code" in name_l or "code" in cmd_l:
            return "vscode"
        if "explor" in name_l or "pasta" in name_l or "explorer" in cmd_l:
            return "folder"
        if any(k in name_l for k in ("edge", "chrome", "firefox", "navegador")):
            return "edge"
        if any(k in name_l for k in ("vlc", "spotify", "mídia", "stremio", "vídeo")):
            return "media"
        if any(k in name_l for k in ("terminal", "powershell", "cmd")):
            return "terminal"
        if any(k in name_l for k in ("foto", "paint", "imagem")):
            return "photos"
        return "windows"

    def render_rows(self):
        layout = self.popup.rows_layout
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()

        for idx, app in enumerate(self.results[:4]):
            is_sel = (idx == self.selected_idx)
            row_frame = QFrame()
            row_frame.setMinimumHeight(36)
            bg = Theme.HEX_ACCENT_MUTED if is_sel else "rgba(255, 255, 255, 0.04)"
            brd = Theme.HEX_ACCENT_BORDER if is_sel else Theme.HEX_BORDER
            row_frame.setStyleSheet(
                f"QFrame {{ background-color: {bg}; border: 1px solid {brd}; border-radius: 10px; }}"
                f"QFrame:hover {{ background-color: {Theme.HEX_BG_CARD_HOVER}; border: 1px solid {Theme.HEX_ACCENT_BORDER}; }}"
            )

            rl = QHBoxLayout(row_frame)
            rl.setContentsMargins(10, 2, 10, 2)
            rl.setSpacing(10)

            if is_sel:
                bar = QFrame()
                bar.setFixedSize(3, 18)
                bar.setStyleSheet(f"background-color: {Theme.HEX_ACCENT}; border: none; border-radius: 1px;")
                rl.addWidget(bar)

            ic_kind = self.classify_icon(app)
            ic_lbl = QLabel()
            ic_lbl.setPixmap(IconFactory.get_app_pixmap(ic_kind, 20))
            ic_lbl.setStyleSheet("border: none; background: transparent;")
            rl.addWidget(ic_lbl)

            cmd = app["cmd"]
            btn_main = QPushButton(f"{app['name']}   •   {app['category']}")
            btn_main.setFont(Theme.get_font(9.5, QFont.Weight.DemiBold if is_sel else QFont.Weight.Medium))
            btn_main.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn_main.setStyleSheet(
                f"QPushButton {{ background: transparent; border: none; text-align: left; "
                f"color: {'#FFFFFF' if is_sel else Theme.HEX_TEXT_PRIMARY}; }}"
            )
            btn_main.clicked.connect(lambda checked=False, c=cmd: self._on_launch(c))
            rl.addWidget(btn_main, stretch=1)

            kbd_lbl = QLabel("↵ Abrir" if is_sel else f"#{idx + 1}")
            kbd_lbl.setFont(Theme.get_font(8.2, QFont.Weight.DemiBold))
            kbd_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            kbd_lbl.setStyleSheet(
                f"QLabel {{ background-color: {'rgba(255,255,255,0.12)' if is_sel else 'rgba(255,255,255,0.05)'}; "
                f"color: {Theme.HEX_TEXT_PRIMARY if is_sel else Theme.HEX_TEXT_SECONDARY}; "
                f"border: 1px solid {Theme.HEX_BORDER}; border-radius: 5px; padding: 2px 7px; }}"
            )
            rl.addWidget(kbd_lbl)

            layout.addWidget(row_frame)

    def _on_launch(self, cmd: str):
        self.close_popup(clear_text=True)
        self.app_launched.emit(cmd)

    # ------------------------------------------------------- keyboard handling
    def handle_key(self, key: int) -> bool:
        """Processa navegação por teclado quando o campo de busca está focado ou o popup está aberto."""
        if key == Qt.Key.Key_Escape:
            if self.popup.isVisible() or bool(self.search_input.text().strip()):
                self.close_popup(clear_text=True)
                return True
            return False

        active = self.popup.isVisible() or self.search_input.hasFocus() or bool(self.search_input.text().strip())
        if not active:
            return False

        if not self.results:
            return False

        if key == Qt.Key.Key_Down:
            if not self.popup.isVisible():
                self.open_popup()
            else:
                self.selected_idx = (self.selected_idx + 1) % len(self.results)
                self.render_rows()
            return True
        if key == Qt.Key.Key_Up:
            if not self.popup.isVisible():
                self.open_popup()
            else:
                self.selected_idx = (self.selected_idx - 1 + len(self.results)) % len(self.results)
                self.render_rows()
            return True
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if 0 <= self.selected_idx < len(self.results):
                self._on_launch(self.results[self.selected_idx]["cmd"])
                return True
        return False

    def eventFilter(self, obj, event):
        if obj is self.search_input:
            if event.type() == QEvent.Type.KeyPress:
                if event.key() in (Qt.Key.Key_Down, Qt.Key.Key_Up, Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Escape):
                    if self.handle_key(event.key()):
                        return True
        return super().eventFilter(obj, event)
