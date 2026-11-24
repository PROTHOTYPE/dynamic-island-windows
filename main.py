import os
import sys
import atexit
import ctypes
from ctypes import wintypes

# Garante que o diretório raiz do projeto esteja no sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import win32gui
import win32con
import win32event
import win32api
import winerror

from PyQt6.QtCore import (
    Qt, QTimer, QRectF, QPointF, QVariantAnimation, QEasingCurve, QEvent, QSize,
    QAbstractNativeEventFilter
)
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QFont, QPainterPath, QLinearGradient,
    QCursor, QIcon, QPixmap, QAction, QBrush
)
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QLineEdit, QPushButton, QFrame, QSystemTrayIcon, QMenu,
    QScrollArea, QSizePolicy
)

from core.system_monitor import SystemMonitor
from core.app_indexer import AppIndexer
from core.media_controller import MediaController
from core.media_session_adapter import MediaSessionAdapter
from core.task_manager import TaskManager
from core.radio_adapter import RadioAdapter
from core.wifi_manager import WiFiManager
from core.audio_adapter import AudioEndpointAdapter
from core.system_controls import SystemControlsAdapter
from core.paths import get_resource_path
from core.diagnostics import setup_diagnostics, log_info, log_exception, shutdown_diagnostics
from core.visibility_monitor import VisibilityMonitor
from ui.icons import IconFactory
from ui.theme import Theme
from ui.system_overlay import SystemOverlayManager
from ui.sliding_pager import SlidingPager, PagerIndicatorBar
from ui.launcher_bar import LauncherBar

WM_MONOLITH_ACTIVATE = win32con.WM_USER + 777


def set_taskbar_visible(visible: bool):
    """
    Oculta ou restaura a Barra de Tarefas do Windows 11 (Shell_TrayWnd).
    Regra obrigatória: preservada visível por padrão durante todo o desenvolvimento.
    """
    flag = win32con.SW_SHOW if visible else win32con.SW_HIDE
    for class_name in ("Shell_TrayWnd", "Shell_SecondaryTrayWnd"):
        try:
            hwnd = win32gui.FindWindow(class_name, None)
            if hwnd:
                win32gui.ShowWindow(hwnd, flag)
        except Exception:
            pass


class _DeviceChangeFilter(QAbstractNativeEventFilter):
    """Escuta WM_DEVICECHANGE (0x0219) e ativação de instância única fora de QWidget.nativeEvent."""

    def __init__(self, on_change_cb, on_activate_cb=None):
        super().__init__()
        self._cb = on_change_cb
        self._activate_cb = on_activate_cb

    def nativeEventFilter(self, eventType, message):
        try:
            if eventType in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == 0x0219:
                    self._cb()
                elif msg.message == WM_MONOLITH_ACTIVATE:
                    if self._activate_cb:
                        self._activate_cb()
                    return True, 0
        except Exception:
            pass
        return False, 0


class _ClickableCard(QFrame):
    """Bloco clicável de destaque (usado para o acesso rápido ao Centro de Controle)."""

    def __init__(self, on_click, parent=None):
        super().__init__(parent)
        self._on_click = on_click
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            if callable(self._on_click):
                self._on_click()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class DynamicIslandWindow(QWidget):
    """
    Monolith — Painel flutuante adaptativo para Windows 11.
    - Identidade OLED Black (#000000) como padrão.
    - Navegação deslizante horizontal entre 3 painéis lineares: INÍCIO (0) -> JANELAS (1) -> SISTEMA (2).
    - Centro de Controle em destaque na primeira tela, abrindo o ControlCenterOverlay independente.
    - Mídia estritamente contextual via SMTC real (visível apenas em Playing).
    - Barra permanente de Launcher integrada na base de todas as páginas com resultados sobrepostos.
    """

    TOP_MARGIN = Theme.TOP_MARGIN
    COMPACT_W = Theme.COMPACT_W
    COMPACT_SAT_W = Theme.COMPACT_SAT_W
    COMPACT_H = Theme.COMPACT_H
    EXPANDED_W = Theme.EXPANDED_W
    EXPANDED_H = Theme.EXPANDED_H

    PAGE_HOME = 0
    PAGE_WINDOWS = 1
    PAGE_SYSTEM = 2

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Monolith")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setMouseTracking(True)

        screen_geo = self._get_screen_geometry()
        self.screen_w = screen_geo.width()
        self.screen_h = screen_geo.height()

        self.is_expanded = False
        self.is_hovered = False
        self.taskbar_hidden = False
        self._hotkey_pressed = False
        self._cc_hotkey_pressed = False
        self.visibility_state = VisibilityMonitor.DESKTOP_IDLE
        self._prev_fg_hwnd = None

        # Ordem linear: 0 = INÍCIO, 1 = JANELAS, 2 = SISTEMA
        self.active_tab_idx = 0

        # Estado do Carrossel de Janelas
        self.open_windows = []
        self.carousel_idx = 0

        atexit.register(lambda: set_taskbar_visible(True))

        # Estado contextual e métricas reais
        self.time_str = "--:--"
        self.cpu_str = "0%"
        self.right_stat_label = "RAM"
        self.right_stat_val = "0%"
        self.has_battery = False
        self.is_charging = False
        self.media_active = False
        self.media_title_short = ""
        self.media_artist_short = ""

        # Posição fixa e centralizada conforme geometria atual do monitor
        Theme.load_preferences()
        init_w = self._current_compact_width()
        init_x = self._get_centered_x(init_w)
        self.setGeometry(init_x, screen_geo.y() + self.TOP_MARGIN, init_w, self.COMPACT_H)

        # Fonte única de verdade para hardware, mídia SMTC e Centro de Controle desacoplado
        self.radio_adapter = RadioAdapter(self)
        self.wifi_manager = WiFiManager(self)
        self.audio_adapter = AudioEndpointAdapter(self)
        self.system_controls = SystemControlsAdapter(self)
        self.media_session = MediaSessionAdapter(self)
        MediaController.bind_adapter(self.media_session)

        self.overlay_manager = SystemOverlayManager(
            radio_adapter=self.radio_adapter,
            wifi_manager=self.wifi_manager,
            audio_adapter=self.audio_adapter,
            system_controls=self.system_controls,
            parent=self,
        )

        # Sinais reativos de mídia contextual (SMTC) e de estado do Centro de Controle
        self.media_session.playback_active_changed.connect(self._on_media_active_changed)
        self.media_session.session_updated.connect(self._on_media_session_updated)
        self.radio_adapter.radios_updated.connect(lambda _r: self._update_cc_hero_summary())
        self.radio_adapter.radio_state_changed.connect(lambda _k, _s: self._update_cc_hero_summary())
        self.wifi_manager.connection_status_changed.connect(lambda _s, _c: self._update_cc_hero_summary())
        self.audio_adapter.volume_changed.connect(lambda _v: self._update_cc_hero_summary())
        self.audio_adapter.mute_changed.connect(lambda _m: self._update_cc_hero_summary())
        self.audio_adapter.default_device_changed.connect(lambda _i, _n: self._update_cc_hero_summary())

        # Monitor de visibilidade contextual orientado a eventos Win32 (SetWinEventHook)
        self.visibility_monitor = VisibilityMonitor(self)
        self.visibility_monitor.state_changed.connect(self._on_visibility_state_changed)
        self.overlay_manager.overlay_opened.connect(
            lambda: self.visibility_monitor.set_interaction_flags(overlay_open=True)
        )
        self.overlay_manager.overlay_closed.connect(
            lambda: self.visibility_monitor.set_interaction_flags(overlay_open=False, edge_hovered=False)
        )

        # Animação suave de recolhimento/revelação contextual na borda superior
        self._vis_anim = QVariantAnimation(self)
        self._vis_anim.setDuration(185)
        self._vis_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._vis_anim.valueChanged.connect(self._on_vis_anim_step)

        # Animação de aparição/ocultação do card contextual de mídia
        self._media_card_anim = QVariantAnimation(self)
        self._media_card_anim.setDuration(190)
        self._media_card_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._media_card_anim.valueChanged.connect(self._on_media_card_anim_step)
        self._media_card_anim.finished.connect(self._on_media_card_anim_finished)

        # Debounce para alteração dinâmica de dispositivos (WM_DEVICECHANGE)
        self._hw_refresh_timer = QTimer(self)
        self._hw_refresh_timer.setSingleShot(True)
        self._hw_refresh_timer.setInterval(750)
        self._hw_refresh_timer.timeout.connect(self._refresh_hardware_capabilities)
        self._device_filter = _DeviceChangeFilter(
            self._hw_refresh_timer.start,
            self._on_external_activate
        )
        app_inst = QApplication.instance()
        if app_inst:
            app_inst.installNativeEventFilter(self._device_filter)

        # Reage dinamicamente a mudanças de resolução ou escala de monitor
        primary_screen = QApplication.primaryScreen()
        if primary_screen:
            primary_screen.geometryChanged.connect(self._on_screen_geometry_changed)

        # Animação fluida de expansão/recolhimento
        self.anim = QVariantAnimation(self)
        self.anim.setDuration(210)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.anim.valueChanged.connect(self._on_anim_step)
        self.anim.finished.connect(self._on_anim_finished)

        self._init_expanded_widgets()
        self._init_system_tray()
        self._refresh_stats()
        self._update_cc_hero_summary()

        # Timers de atualização periódica
        self.stats_timer = QTimer(self)
        self.stats_timer.timeout.connect(self._refresh_stats)
        self.stats_timer.start(1200)

        # Timer de janelas: só executa trabalho se o painel JANELAS (índice 1) estiver visível
        self.tasks_timer = QTimer(self)
        self.tasks_timer.timeout.connect(self._refresh_open_tasks)
        self.tasks_timer.start(2200)

        # Polling de atalho global (Alt + Espaço / Alt + C)
        self.hotkey_timer = QTimer(self)
        self.hotkey_timer.timeout.connect(self._poll_hotkey)
        self.hotkey_timer.start(60)

        # Inicialização com carência visual: mantém a cápsula totalmente visível nos primeiros 5s
        self._startup_grace = True
        self._startup_timer = QTimer(self)
        self._startup_timer.setSingleShot(True)
        self._startup_timer.setInterval(5000)
        self._startup_timer.timeout.connect(self._end_startup_grace)
        self._startup_timer.start()

        # Registra HWNDs do Monolith e inicia hooks Win32
        self._register_visibility_hwnds()
        self.visibility_monitor.start()
        self._apply_visibility_state(self.visibility_monitor.current_state(), animate=False)

    def _end_startup_grace(self):
        self._startup_grace = False
        self.visibility_monitor.evaluate_now()
        current_state = self.visibility_monitor.current_state()
        if not self.is_expanded:
            self._apply_visibility_state(current_state, animate=not Theme.reduced_motion_enabled())
        log_info(
            "Carência de inicialização encerrada (estado=%s, y=%s)",
            current_state,
            self._target_compact_y(current_state),
        )

    # ------------------------------------------ delegações do LauncherBar
    @property
    def search_input(self) -> QLineEdit:
        return self.launcher_bar.search_input

    @property
    def results(self) -> list:
        return self.launcher_bar.results

    @results.setter
    def results(self, val: list):
        self.launcher_bar.results = val

    @property
    def selected_idx(self) -> int:
        return self.launcher_bar.selected_idx

    @selected_idx.setter
    def selected_idx(self, val: int):
        self.launcher_bar.selected_idx = val

    @property
    def launcher_filter(self) -> str:
        return self.launcher_bar.launcher_filter

    @launcher_filter.setter
    def launcher_filter(self, val: str):
        self.launcher_bar.launcher_filter = val

    def is_media_satellite_visible(self) -> bool:
        """O módulo satélite só aparece contextualmente quando há reprodução SMTC efetivamente em Playing."""
        return bool(Theme.satellite_enabled and self.media_active)

    def _current_compact_width(self) -> int:
        return self.COMPACT_SAT_W if self.is_media_satellite_visible() else self.COMPACT_W

    @staticmethod
    def _get_screen_geometry():
        screen = QApplication.primaryScreen()
        return screen.geometry() if screen else QRectF(0, 0, 1920, 1080).toRect()

    def _get_centered_x(self, width: int) -> int:
        geo = self._get_screen_geometry()
        return geo.x() + (geo.width() - width) // 2

    def _get_clamped_x(self, width: int) -> int:
        return self._get_centered_x(width)

    def _register_visibility_hwnds(self):
        try:
            for w in (self, self.overlay_manager.backdrop, self.overlay_manager.panel):
                if w:
                    self.visibility_monitor.register_monolith_hwnd(int(w.winId()))
        except Exception:
            pass

    def _target_compact_y(self, state: str = None) -> int:
        geo = self._get_screen_geometry()
        st = state or self.visibility_state
        if getattr(self, "_startup_grace", False) and st in (
            VisibilityMonitor.DESKTOP_IDLE,
            VisibilityMonitor.APP_AUTO_HIDE,
        ):
            return geo.y() + self.TOP_MARGIN
        if st == VisibilityMonitor.APP_AUTO_HIDE and not self.is_expanded:
            return geo.y() - (self.COMPACT_H - 8)
        return geo.y() + self.TOP_MARGIN

    def _on_visibility_state_changed(self, new_state: str):
        self._apply_visibility_state(new_state, animate=not Theme.reduced_motion_enabled())

    def _apply_visibility_state(self, new_state: str, animate: bool = True):
        self.visibility_state = new_state
        if new_state == VisibilityMonitor.FULLSCREEN_HIDDEN and not self.is_expanded:
            self._vis_anim.stop()
            self.is_hovered = False
            self.hide()
            return

        if not self.isVisible():
            self.show()

        if self.is_expanded or self.anim.state() == QVariantAnimation.State.Running:
            return

        target_y = self._target_compact_y(new_state)
        if not animate:
            self._vis_anim.stop()
            self.move(self.x(), target_y)
            self.update()
            return

        cur_y = self.y()
        if cur_y != target_y:
            self._vis_anim.stop()
            self._vis_anim.setStartValue(float(cur_y))
            self._vis_anim.setEndValue(float(target_y))
            self._vis_anim.start()
        self.update()

    def _on_vis_anim_step(self, val: float):
        if not self.is_expanded and self.anim.state() != QVariantAnimation.State.Running:
            self.move(self.x(), int(round(float(val))))

    def _on_external_activate(self):
        """Chamado quando outra tentativa de inicialização envia WM_MONOLITH_ACTIVATE."""
        self.expand()
        self.activateWindow()
        self.raise_()

    def _refresh_hardware_capabilities(self):
        try:
            if hasattr(self, "radio_adapter") and self.radio_adapter:
                self.radio_adapter.refresh_radios()
                self.radio_adapter.refresh_tethering()
            if hasattr(self, "audio_adapter") and self.audio_adapter:
                self.audio_adapter.refresh()
            if hasattr(self, "system_controls") and self.system_controls:
                self.system_controls.refresh()
            if hasattr(self, "media_session") and self.media_session:
                self.media_session.refresh()
            self._update_cc_hero_summary()
        except Exception as e:
            log_exception("DynamicIslandWindow._refresh_hardware_capabilities", e)

    def _on_screen_geometry_changed(self, _geo=None):
        geo = self._get_screen_geometry()
        self.screen_w = geo.width()
        self.screen_h = geo.height()
        cur_w = self.EXPANDED_W if self.is_expanded else self._current_compact_width()
        target_y = (geo.y() + self.TOP_MARGIN) if self.is_expanded else self._target_compact_y()
        self.move(self._get_centered_x(cur_w), target_y)
        self.overlay_manager.panel._update_geometry()

    def toggle_control_center(self):
        """Abre ou fecha o Centro de Controle independente preservando foco e backdrop."""
        self._register_visibility_hwnds()
        if self.overlay_manager.is_open:
            self.overlay_manager.dismiss()
            return
        if self.is_expanded:
            self.collapse()
        self.overlay_manager.show_control_center()

    def _init_system_tray(self):
        """Cria o ícone na área de notificação do Windows."""
        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(IconFactory.get_icon("taskbar", 32, Theme.HEX_TEXT_PRIMARY))
        self.tray.setToolTip("Monolith")

        menu = QMenu(self)
        self.tray_menu = menu
        menu.setStyleSheet(
            f"QMenu {{ background-color: #0C0C0C; color: {Theme.HEX_TEXT_PRIMARY}; "
            f"border: 1px solid {Theme.HEX_BORDER}; border-radius: {Theme.RADIUS_CARD}px; "
            f"padding: 6px; font-family: '{Theme.FONT_FAMILY_FALLBACK}'; font-size: 11px; }}"
            f"QMenu::item {{ padding: 6px 20px; border-radius: 6px; }}"
            f"QMenu::item:selected {{ background-color: {Theme.HEX_ACCENT_MUTED}; color: #FFFFFF; }}"
        )

        act_toggle = QAction("Expandir / Recolher Monolith", self)
        act_toggle.setIcon(IconFactory.get_icon("window", 16, Theme.HEX_TEXT_PRIMARY))
        act_toggle.triggered.connect(self.toggle_expand)
        menu.addAction(act_toggle)

        act_cc = QAction("Abrir Centro de Controle (Alt+C)", self)
        act_cc.setIcon(IconFactory.get_icon("gear", 16, Theme.HEX_TEXT_SECONDARY))
        act_cc.triggered.connect(self.toggle_control_center)
        menu.addAction(act_cc)

        act_center = QAction("Centralizar na Tela", self)
        act_center.setIcon(IconFactory.get_icon("pin", 16, Theme.HEX_TEXT_SECONDARY))
        act_center.triggered.connect(self._center_island)
        menu.addAction(act_center)

        self.act_tb = QAction("Ocultar Barra de Tarefas", self)
        self.act_tb.setIcon(IconFactory.get_icon("taskbar", 16, Theme.HEX_TEXT_SECONDARY))
        self.act_tb.triggered.connect(self.toggle_taskbar)
        menu.addAction(self.act_tb)

        menu.addSeparator()

        act_quit = QAction("Encerrar", self)
        act_quit.setIcon(IconFactory.get_icon("power", 16, Theme.HEX_STATUS_DANGER_TEXT))
        act_quit.triggered.connect(self.quit_app)
        menu.addAction(act_quit)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle_expand()

    def dock_to_center(self):
        self._center_island()

    def _center_island(self):
        geo = self._get_screen_geometry()
        w = self.width()
        self.move(self._get_centered_x(w), geo.y() + self.TOP_MARGIN)
        self.update()

    def _make_keycap_label(self, text: str, is_accent: bool = False) -> QLabel:
        lbl = QLabel(text)
        lbl.setFont(Theme.get_font(8.2, QFont.Weight.DemiBold))
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bg = Theme.HEX_ACCENT_MUTED if is_accent else "rgba(255, 255, 255, 0.05)"
        brd = Theme.HEX_ACCENT_BORDER if is_accent else "rgba(255, 255, 255, 0.10)"
        col = Theme.HEX_TEXT_PRIMARY if is_accent else Theme.HEX_TEXT_SECONDARY
        lbl.setStyleSheet(
            f"QLabel {{ background-color: {bg}; color: {col}; border: 1px solid {brd}; "
            f"border-radius: 5px; padding: 2px 7px; }}"
        )
        return lbl

    # ------------------------------------------------ construção dos 3 painéis
    def _init_expanded_widgets(self):
        """
        Constrói o interior do painel Monolith com:
        - Indicador superior de páginas (Início • Janelas • Sistema)
        - SlidingPager horizontal (3 páginas sem fragmentação)
        - LauncherBar permanente na base + popup sobreposto
        """
        self.content = QWidget(self)
        self.content.setGeometry(0, 0, self.EXPANDED_W, self.EXPANDED_H)
        self.content.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.content.setStyleSheet("background: transparent;")
        self.content.hide()

        main_layout = QVBoxLayout(self.content)
        main_layout.setContentsMargins(20, 38, 20, 14)
        main_layout.setSpacing(8)

        # Barra superior discreta de posição dos painéis
        self.pager_indicator = PagerIndicatorBar(["Início", "Janelas", "Sistema"], self.content)
        self.pager_indicator.page_requested.connect(lambda idx: self._switch_tab(idx, animate=True))
        main_layout.addWidget(self.pager_indicator)

        # Navegador horizontal deslizante (SlidingPager)
        self.stack = SlidingPager(self.content)
        self.stack.currentChanged.connect(self._on_pager_index_changed)
        self.stack.progressChanged.connect(self.pager_indicator.set_progress)

        # ======================================================================
        # PÁGINA 0: INÍCIO (Centro de Controle em Destaque + Visão Geral + Mídia Contextual)
        # ======================================================================
        self.page_stage = QWidget()
        self.page_home = self.page_stage
        self.page_stage.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.page_stage.setStyleSheet("background: transparent;")
        stage_layout = QVBoxLayout(self.page_stage)
        stage_layout.setContentsMargins(0, 2, 0, 0)
        stage_layout.setSpacing(8)

        # 1. Bloco Principal de Acesso ao Centro de Controle (Protagonista na 1ª tela)
        self.cc_hero_card = _ClickableCard(self.toggle_control_center)
        self.cc_hero_card.setObjectName("cc_hero_card")
        self.cc_hero_card.setMinimumHeight(74)
        cc_layout = QHBoxLayout(self.cc_hero_card)
        cc_layout.setContentsMargins(16, 12, 16, 12)
        cc_layout.setSpacing(14)

        self.lbl_cc_hero_icon = QLabel()
        self.lbl_cc_hero_icon.setFixedSize(40, 40)
        self.lbl_cc_hero_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_cc_hero_icon.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        cc_layout.addWidget(self.lbl_cc_hero_icon)

        cc_text_col = QVBoxLayout()
        cc_text_col.setContentsMargins(0, 0, 0, 0)
        cc_text_col.setSpacing(3)

        self.lbl_cc_hero_title = QLabel("Centro de Controle")
        self.lbl_cc_hero_title.setFont(Theme.get_font(11.5, QFont.Weight.DemiBold))
        self.lbl_cc_hero_title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self.lbl_cc_hero_sub = QLabel("Wi-Fi  •  Bluetooth  •  Saída de Áudio e Volume")
        self.lbl_cc_hero_sub.setFont(Theme.get_font(9.0, QFont.Weight.Normal))
        self.lbl_cc_hero_sub.setWordWrap(True)
        self.lbl_cc_hero_sub.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        cc_text_col.addWidget(self.lbl_cc_hero_title)
        cc_text_col.addWidget(self.lbl_cc_hero_sub)
        cc_layout.addLayout(cc_text_col, stretch=1)

        self.btn_cc_open = QPushButton("Abrir Painel  ›")
        self.btn_cc_open.setFont(Theme.get_font(9.2, QFont.Weight.DemiBold))
        self.btn_cc_open.setMinimumHeight(34)
        self.btn_cc_open.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_cc_open.clicked.connect(self.toggle_control_center)
        cc_layout.addWidget(self.btn_cc_open)

        stage_layout.addWidget(self.cc_hero_card)

        # 2. Card Contextual de Mídia (OCULTO por padrão; visível somente quando SMTC == Playing)
        self.stage_media_card = QFrame()
        self.stage_media_card.setObjectName("stage_media_card")
        self.stage_media_card.setMinimumHeight(82)
        self.stage_media_card.setMaximumHeight(92)
        sm_layout = QHBoxLayout(self.stage_media_card)
        sm_layout.setContentsMargins(14, 10, 14, 10)
        sm_layout.setSpacing(14)

        self.lbl_album_art = QLabel()
        self.lbl_album_art.setFixedSize(56, 56)
        self.lbl_album_art.setPixmap(IconFactory.get_album_art_pixmap(56))
        self.lbl_album_art.setStyleSheet("border: none; background: transparent;")
        sm_layout.addWidget(self.lbl_album_art)

        meta_col = QVBoxLayout()
        meta_col.setContentsMargins(0, 2, 0, 2)
        meta_col.setSpacing(3)

        self.lbl_media_title = QLabel("")
        self.lbl_media_title.setFont(Theme.get_font(10.5, QFont.Weight.DemiBold))
        self.lbl_media_title.setWordWrap(True)

        self.lbl_media_sub = QLabel("")
        self.lbl_media_sub.setFont(Theme.get_font(8.8, QFont.Weight.Normal))

        meta_col.addWidget(self.lbl_media_title)
        meta_col.addWidget(self.lbl_media_sub)
        meta_col.addStretch()

        prog_row = QHBoxLayout()
        prog_row.setContentsMargins(0, 0, 8, 0)
        prog_row.setSpacing(0)
        self.prog_active = QFrame()
        self.prog_active.setFixedHeight(3)
        self.prog_active.setFixedWidth(72)
        self.prog_thumb = QFrame()
        self.prog_thumb.setFixedSize(7, 7)
        self.prog_rest = QFrame()
        self.prog_rest.setFixedHeight(3)
        prog_row.addWidget(self.prog_active)
        prog_row.addWidget(self.prog_thumb)
        prog_row.addWidget(self.prog_rest, stretch=1)
        meta_col.addLayout(prog_row)
        sm_layout.addLayout(meta_col, stretch=1)

        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(6)
        ctrl_row.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.btn_media_prev = QPushButton()
        self.btn_media_prev.setFixedSize(30, 30)
        self.btn_media_prev.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_media_prev.setToolTip("Faixa Anterior")
        self.btn_media_prev.clicked.connect(MediaController.prev_track)

        self.btn_media_play = QPushButton()
        self.btn_media_play.setFixedSize(38, 38)
        self.btn_media_play.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_media_play.setToolTip("Reproduzir / Pausar")
        self.btn_media_play.clicked.connect(self._on_play_pause_clicked)

        self.btn_media_next = QPushButton()
        self.btn_media_next.setFixedSize(30, 30)
        self.btn_media_next.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_media_next.setToolTip("Próxima Faixa")
        self.btn_media_next.clicked.connect(MediaController.next_track)

        ctrl_row.addWidget(self.btn_media_prev)
        ctrl_row.addWidget(self.btn_media_play)
        ctrl_row.addWidget(self.btn_media_next)
        sm_layout.addLayout(ctrl_row)

        self.stage_media_card.hide()
        stage_layout.addWidget(self.stage_media_card)

        # 3. Resumo Contextual do Sistema na Página Inicial
        self.home_metrics_row = QHBoxLayout()
        self.home_metrics_row.setSpacing(8)
        self.home_metric_cards = {}
        for m_key, m_title in [("CPU", "CPU"), ("RAM", "RAM"), ("PWR", "ENERGIA / DISCO"), ("NET", "REDE")]:
            m_card = QFrame()
            m_card.setMinimumHeight(52)
            ml = QVBoxLayout(m_card)
            ml.setContentsMargins(10, 7, 10, 7)
            ml.setSpacing(2)
            lt = QLabel(m_title)
            lt.setFont(Theme.get_font(7.8, QFont.Weight.Bold))
            lt.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            lv = QLabel("--")
            lv.setFont(Theme.get_font(11.0, QFont.Weight.DemiBold))
            lv.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            ml.addWidget(lt)
            ml.addWidget(lv)
            self.home_metrics_row.addWidget(m_card, stretch=1)
            self.home_metric_cards[m_key] = (m_card, lt, lv)
        stage_layout.addLayout(self.home_metrics_row)

        # 4. Faixa de Ações Rápidas Contextuais
        quick_strip = QHBoxLayout()
        quick_strip.setSpacing(8)

        self.stage_quick_btns = []
        quick_defs = [
            ("Janelas", "window", lambda: self._switch_tab(self.PAGE_WINDOWS)),
            ("Explorador", "folder", lambda: AppIndexer.launch("explorer")),
            ("Área de Trabalho", "desktop", self.action_show_desktop),
            ("Silenciar", "mute", self.audio_adapter.toggle_mute),
        ]
        for q_lbl, q_ic, q_fn in quick_defs:
            qb = QPushButton(f"  {q_lbl}")
            qb.setFont(Theme.get_font(9.0, QFont.Weight.Medium))
            qb.setIcon(IconFactory.get_icon(q_ic, 13, Theme.HEX_TEXT_SECONDARY))
            qb.setIconSize(QSize(13, 13))
            qb.setMinimumHeight(34)
            qb.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            qb.clicked.connect(q_fn)
            quick_strip.addWidget(qb, stretch=1)
            self.stage_quick_btns.append(qb)

        # Mantém self.health_pill compatível para telemetria silenciosa
        self.health_pill = QFrame()
        self.health_pill.hide()
        self.lbl_health_dot = QLabel("●", self.health_pill)
        self.lbl_health_text = QLabel("Sistema Estável", self.health_pill)

        stage_layout.addLayout(quick_strip)
        stage_layout.addStretch()
        self.stack.addWidget(self.page_stage)

        # ======================================================================
        # PÁGINA 1: JANELAS (Carrossel Visual em Foco + Miniaturas Sob Demanda)
        # ======================================================================
        self.page_tasks = QWidget()
        self.page_tasks.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.page_tasks.setStyleSheet("background: transparent;")
        tasks_layout = QVBoxLayout(self.page_tasks)
        tasks_layout.setContentsMargins(0, 2, 0, 0)
        tasks_layout.setSpacing(6)

        w_header = QHBoxLayout()
        self.lbl_windows_header = QLabel("JANELAS ATIVAS")
        self.lbl_windows_header.setFont(Theme.get_font(8.8, QFont.Weight.Bold))
        self.lbl_windows_header.setStyleSheet(
            f"color: {Theme.HEX_TEXT_SECONDARY}; background: transparent;"
        )
        self.lbl_windows_count = self._make_keycap_label("← → Alternar  •  ↵ Focar", False)
        w_header.addWidget(self.lbl_windows_header)
        w_header.addStretch()
        w_header.addWidget(self.lbl_windows_count)
        tasks_layout.addLayout(w_header)

        self.tasks_scroll = QScrollArea()
        self.tasks_scroll.setWidgetResizable(True)
        self.tasks_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.tasks_scroll.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.tasks_scroll.setStyleSheet(Theme.style_scroll_area())
        self.tasks_scroll.viewport().setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.tasks_scroll.viewport().setStyleSheet("background: transparent;")
        self.tasks_scroll.viewport().setAutoFillBackground(False)

        self.tasks_container = QWidget()
        self.tasks_container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.tasks_container.setStyleSheet("background: transparent;")
        self.tasks_container_layout = QVBoxLayout(self.tasks_container)
        self.tasks_container_layout.setContentsMargins(0, 0, 0, 0)
        self.tasks_container_layout.setSpacing(6)
        self.tasks_container_layout.addStretch()

        self.tasks_scroll.setWidget(self.tasks_container)
        self.tasks_container.setAutoFillBackground(False)
        tasks_layout.addWidget(self.tasks_scroll, stretch=1)
        self.stack.addWidget(self.page_tasks)

        # ======================================================================
        # PÁGINA 2: SISTEMA (Configurações + Diagnóstico + Aparência e Temas Incorporados)
        # ======================================================================
        self.page_system = QWidget()
        self.page_control = self.page_system
        self.page_appearance = self.page_system
        self.page_system.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.page_system.setStyleSheet("background: transparent;")

        sys_outer_layout = QVBoxLayout(self.page_system)
        sys_outer_layout.setContentsMargins(0, 0, 0, 0)
        sys_outer_layout.setSpacing(0)

        self.sys_scroll = QScrollArea()
        self.sys_scroll.setWidgetResizable(True)
        self.sys_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.sys_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.sys_scroll.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.sys_scroll.setStyleSheet(Theme.style_scroll_area())
        self.sys_scroll.viewport().setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.sys_scroll.viewport().setStyleSheet("background: transparent;")

        sys_inner = QWidget()
        sys_inner.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        ctrl_layout = QVBoxLayout(sys_inner)
        ctrl_layout.setContentsMargins(0, 2, 4, 4)
        ctrl_layout.setSpacing(8)

        # 1. Métricas de Diagnóstico em Tempo Real
        metrics_bar = QHBoxLayout()
        metrics_bar.setSpacing(8)
        self.badge_labels = {}
        for key, title in [("CPU", "CPU"), ("RAM", "MEMÓRIA RAM"), ("DISK", "DISCO C:"), ("NET", "REDE ATIVA")]:
            card = QFrame()
            card.setStyleSheet(Theme.style_card())
            cl = QVBoxLayout(card)
            cl.setContentsMargins(8, 6, 8, 6)
            cl.setSpacing(2)
            lbl_t = QLabel(title)
            lbl_t.setFont(Theme.get_font(7.8, QFont.Weight.Bold))
            lbl_t.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_t.setStyleSheet(f"color: {Theme.HEX_TEXT_MUTED}; border: none; background: transparent;")
            lbl_v = QLabel("0%")
            lbl_v.setFont(Theme.get_font(11.0, QFont.Weight.Bold))
            lbl_v.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_v.setStyleSheet(f"color: {Theme.HEX_TEXT_PRIMARY}; border: none; background: transparent;")
            cl.addWidget(lbl_t)
            cl.addWidget(lbl_v)
            metrics_bar.addWidget(card, stretch=1)
            self.badge_labels[key] = (lbl_t, lbl_v)
        ctrl_layout.addLayout(metrics_bar)

        # 2. Ações do Sistema e Sessão
        sys_box = QFrame()
        sys_box.setStyleSheet(Theme.style_card())
        sb_layout = QHBoxLayout(sys_box)
        sb_layout.setContentsMargins(8, 7, 8, 7)
        sb_layout.setSpacing(6)

        self.btn_taskbar = QPushButton(" Barra: Visível")
        self.btn_taskbar.setFont(Theme.get_font(8.6, QFont.Weight.DemiBold))
        self.btn_taskbar.setIcon(IconFactory.get_icon("taskbar", 12, Theme.HEX_TEXT_PRIMARY))
        self.btn_taskbar.setIconSize(QSize(12, 12))
        self.btn_taskbar.setMinimumHeight(30)
        self.btn_taskbar.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_taskbar.clicked.connect(self.toggle_taskbar)
        sb_layout.addWidget(self.btn_taskbar)

        btn_ctrl_center = QPushButton(" Controle")
        btn_ctrl_center.setFont(Theme.get_font(8.6, QFont.Weight.Medium))
        btn_ctrl_center.setIcon(IconFactory.get_icon("gear", 12, Theme.HEX_TEXT_SECONDARY))
        btn_ctrl_center.setIconSize(QSize(12, 12))
        btn_ctrl_center.setMinimumHeight(30)
        btn_ctrl_center.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_ctrl_center.setStyleSheet(Theme.style_collapse_button())
        btn_ctrl_center.clicked.connect(self.toggle_control_center)
        sb_layout.addWidget(btn_ctrl_center)

        btn_taskmgr = QPushButton(" Tarefas")
        btn_taskmgr.setFont(Theme.get_font(8.6, QFont.Weight.Medium))
        btn_taskmgr.setIcon(IconFactory.get_icon("cpu", 12, Theme.HEX_TEXT_SECONDARY))
        btn_taskmgr.setIconSize(QSize(12, 12))
        btn_taskmgr.setMinimumHeight(30)
        btn_taskmgr.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_taskmgr.setStyleSheet(Theme.style_collapse_button())
        btn_taskmgr.clicked.connect(lambda: AppIndexer.launch("taskmgr"))
        sb_layout.addWidget(btn_taskmgr)

        btn_collapse = QPushButton(" Recolher")
        btn_collapse.setFont(Theme.get_font(8.6, QFont.Weight.Medium))
        btn_collapse.setIcon(IconFactory.get_icon("close", 10, Theme.HEX_TEXT_SECONDARY))
        btn_collapse.setIconSize(QSize(10, 10))
        btn_collapse.setMinimumHeight(30)
        btn_collapse.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_collapse.setStyleSheet(Theme.style_collapse_button())
        btn_collapse.clicked.connect(self.collapse)
        sb_layout.addWidget(btn_collapse)

        btn_quit = QPushButton(" Encerrar")
        btn_quit.setFont(Theme.get_font(8.6, QFont.Weight.DemiBold))
        btn_quit.setIcon(IconFactory.get_icon("power", 10, Theme.HEX_STATUS_DANGER_TEXT))
        btn_quit.setIconSize(QSize(10, 10))
        btn_quit.setMinimumHeight(30)
        btn_quit.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_quit.setStyleSheet(Theme.style_quit_button())
        btn_quit.clicked.connect(self.quit_app)
        sb_layout.addWidget(btn_quit)

        ctrl_layout.addWidget(sys_box)

        # 3. Seção Incorporada: Personalização & Temas (OLED Black padrão + Presets)
        self.swatches_frame = QFrame()
        self.swatches_frame.setStyleSheet(Theme.style_card())
        sw_outer = QVBoxLayout(self.swatches_frame)
        sw_outer.setContentsMargins(10, 8, 10, 8)
        sw_outer.setSpacing(6)

        ap_head = QHBoxLayout()
        self.lbl_ap_title = QLabel("Tema & Identidade Visual (OLED Black Padrão)")
        self.lbl_ap_title.setFont(Theme.get_font(9.2, QFont.Weight.DemiBold))
        self.lbl_ap_title.setStyleSheet(f"color: {Theme.HEX_TEXT_PRIMARY}; border: none; background: transparent;")
        self.lbl_ap_saved = self._make_keycap_label("Salvo localmente", False)
        ap_head.addWidget(self.lbl_ap_title)
        ap_head.addStretch()
        ap_head.addWidget(self.lbl_ap_saved)
        sw_outer.addLayout(ap_head)

        # Grade em 2 linhas para que nenhum nome de preset seja truncado em 100%, 125% ou 150%
        sw_grid = QGridLayout()
        sw_grid.setContentsMargins(0, 0, 0, 0)
        sw_grid.setHorizontalSpacing(6)
        sw_grid.setVerticalSpacing(6)

        self.swatch_buttons = {}
        preset_items = list(Theme.PRESETS.items())
        for idx_p, (p_key, p_info) in enumerate(preset_items):
            sbtn = QPushButton(f" {p_info['name']}")
            sbtn.setFont(Theme.get_font(8.6, QFont.Weight.Medium))
            sbtn.setMinimumHeight(28)
            sbtn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            sbtn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            sbtn.clicked.connect(lambda checked=False, pk=p_key: self._on_select_preset(pk))
            r_idx = 0 if idx_p < 4 else 1
            c_idx = idx_p if idx_p < 4 else (idx_p - 4)
            sw_grid.addWidget(sbtn, r_idx, c_idx)
            self.swatch_buttons[p_key] = sbtn
        sw_outer.addLayout(sw_grid)
        ctrl_layout.addWidget(self.swatches_frame)

        # 4. Linha Inferior de Aparência: Cor HEX + Material do Notch & Satélite
        ap_bottom = QHBoxLayout()
        ap_bottom.setSpacing(8)

        self.hex_card = QFrame()
        self.hex_card.setStyleSheet(Theme.style_card())
        hx_layout = QVBoxLayout(self.hex_card)
        hx_layout.setContentsMargins(10, 7, 10, 7)
        hx_layout.setSpacing(4)

        lbl_hx_t = QLabel("Destaque Personalizado (HEX)")
        lbl_hx_t.setFont(Theme.get_font(8.6, QFont.Weight.DemiBold))
        lbl_hx_t.setStyleSheet(f"color: {Theme.HEX_TEXT_PRIMARY}; border: none; background: transparent;")
        hx_layout.addWidget(lbl_hx_t)

        hx_inp_row = QHBoxLayout()
        hx_inp_row.setSpacing(6)
        self.hex_preview_box = QFrame()
        self.hex_preview_box.setFixedSize(24, 24)
        self.hex_input = QLineEdit(Theme.custom_hex)
        self.hex_input.setProperty("no_pager_swipe", True)
        self.hex_input.setPlaceholderText("#EDEDED")
        self.hex_input.setMinimumHeight(26)
        self.btn_apply_hex = QPushButton("Aplicar")
        self.btn_apply_hex.setFont(Theme.get_font(8.5, QFont.Weight.DemiBold))
        self.btn_apply_hex.setMinimumHeight(26)
        self.btn_apply_hex.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_apply_hex.clicked.connect(self._on_apply_custom_hex)

        hx_inp_row.addWidget(self.hex_preview_box)
        hx_inp_row.addWidget(self.hex_input, stretch=1)
        hx_inp_row.addWidget(self.btn_apply_hex)
        hx_layout.addLayout(hx_inp_row)
        ap_bottom.addWidget(self.hex_card, stretch=5)

        self.behav_card = QFrame()
        self.behav_card.setStyleSheet(Theme.style_card())
        bh_layout = QVBoxLayout(self.behav_card)
        bh_layout.setContentsMargins(10, 7, 10, 7)
        bh_layout.setSpacing(4)

        mat_row = QHBoxLayout()
        mat_row.setSpacing(6)
        self.material_buttons = {}
        for m_key, m_info in Theme.NOTCH_MATERIALS.items():
            mbtn = QPushButton(f" {m_info['name']}")
            mbtn.setFont(Theme.get_font(8.4, QFont.Weight.Medium))
            mbtn.setMinimumHeight(25)
            mbtn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            mbtn.clicked.connect(lambda checked=False, mk=m_key: self._on_select_notch_material(mk))
            mat_row.addWidget(mbtn)
            self.material_buttons[m_key] = mbtn
        bh_layout.addLayout(mat_row)

        self.btn_toggle_satellite = QPushButton()
        self.btn_toggle_satellite.setFont(Theme.get_font(8.4, QFont.Weight.Medium))
        self.btn_toggle_satellite.setMinimumHeight(25)
        self.btn_toggle_satellite.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_toggle_satellite.clicked.connect(self._on_toggle_satellite_pref)
        bh_layout.addWidget(self.btn_toggle_satellite)

        ap_bottom.addWidget(self.behav_card, stretch=6)
        ctrl_layout.addLayout(ap_bottom)

        self.sys_scroll.setWidget(sys_inner)
        sys_outer_layout.addWidget(self.sys_scroll)
        self.stack.addWidget(self.page_system)

        main_layout.addWidget(self.stack, stretch=1)

        # ======================================================================
        # BARRA PERMANENTE DE LAUNCHER (Acessível em Início, Janelas e Sistema)
        # ======================================================================
        self.launcher_bar = LauncherBar(overlay_parent=self.content, parent=self.content)
        self.launcher_bar.app_launched.connect(self.launch_app)
        main_layout.addWidget(self.launcher_bar)

        # Mantém self.tab_buttons vazio para retrocompatibilidade caso inspecionado
        self.tab_buttons = []

        self._apply_live_theme()
        self._switch_tab(self.PAGE_HOME, animate=False)

    # ---------------------------------------------- Centro de Controle Hero
    def _update_cc_hero_summary(self):
        """Atualiza o resumo confiável exibido no bloco principal do Centro de Controle em INÍCIO."""
        try:
            if not hasattr(self, "lbl_cc_hero_sub"):
                return
            parts = []
            if hasattr(self, "radio_adapter") and self.radio_adapter:
                if self.radio_adapter.has_radio("WiFi"):
                    wifi_on = self.radio_adapter.is_wifi_on()
                    conn = self.wifi_manager.get_cached_connection() if hasattr(self, "wifi_manager") and self.wifi_manager else None
                    if wifi_on and conn and conn.get("connected") and conn.get("ssid"):
                        parts.append(f"Wi-Fi: {conn['ssid']}")
                    else:
                        parts.append(f"Wi-Fi: {'Ligado' if wifi_on else 'Desligado'}")
                if self.radio_adapter.has_radio("Bluetooth"):
                    bt_on = self.radio_adapter.is_bluetooth_on()
                    parts.append(f"Bluetooth: {'Ligado' if bt_on else 'Desligado'}")

            if hasattr(self, "audio_adapter") and self.audio_adapter:
                vol = self.audio_adapter.get_cached_volume()
                muted = self.audio_adapter.get_cached_mute()
                parts.append("Áudio: Mudo" if muted else f"Volume: {int(vol)}%")

            summary = "  •  ".join(parts) if parts else "Wi-Fi  •  Bluetooth  •  Saída de Áudio e Volume"
            self.lbl_cc_hero_sub.setText(summary)
        except Exception:
            pass

    # ------------------------------------------ Mídia Contextual via SMTC
    def _on_media_active_changed(self, active: bool):
        """Exibe ou recolhe o card de mídia exclusivamente quando há sessão SMTC em Playing."""
        self.media_active = bool(active)
        if not self.media_active:
            self.media_title_short = ""
            self.media_artist_short = ""

        # Anima a aparição ou recolhimento do card na página INÍCIO
        self._media_card_anim.stop()
        if Theme.reduced_motion_enabled() or not self.is_expanded:
            self.stage_media_card.setMaximumHeight(92 if self.media_active else 0)
            self.stage_media_card.setMinimumHeight(82 if self.media_active else 0)
            self.stage_media_card.setVisible(self.media_active)
        else:
            if self.media_active:
                self.stage_media_card.setMinimumHeight(0)
                self.stage_media_card.setMaximumHeight(0)
                self.stage_media_card.show()
                self._media_card_anim.setStartValue(0.0)
                self._media_card_anim.setEndValue(86.0)
                self._media_card_anim.start()
            else:
                cur_h = float(max(0, self.stage_media_card.height()))
                self.stage_media_card.setMinimumHeight(0)
                self._media_card_anim.setStartValue(cur_h)
                self._media_card_anim.setEndValue(0.0)
                self._media_card_anim.start()

        self._sync_compact_capsule_geometry()
        self._apply_live_theme()
        self.update()

    def _on_media_card_anim_step(self, val: float):
        h = max(0, int(round(float(val))))
        self.stage_media_card.setMaximumHeight(h)

    def _on_media_card_anim_finished(self):
        if self.media_active:
            self.stage_media_card.setMinimumHeight(82)
            self.stage_media_card.setMaximumHeight(92)
            self.stage_media_card.show()
        else:
            self.stage_media_card.setMinimumHeight(0)
            self.stage_media_card.setMaximumHeight(0)
            self.stage_media_card.hide()

    def _on_media_session_updated(self, state: dict):
        if state.get("playing"):
            app_name = MediaSessionAdapter.friendly_app_name(state.get("app", "")) or "Mídia"
            title = (state.get("title") or "").strip() or f"Reproduzindo em {app_name}"
            artist = (state.get("artist") or "").strip()
            sub = f"{artist}  •  {app_name}" if artist else f"{app_name}  •  Em reprodução"
            self.media_title_short = title if len(title) <= 14 else f"{title[:12]}…"
            self.media_artist_short = sub
            self.lbl_media_title.setText(title)
            self.lbl_media_sub.setText(sub)
        self.update()

    def _sync_compact_capsule_geometry(self):
        if not self.is_expanded and self.anim.state() != QVariantAnimation.State.Running and self._vis_anim.state() != QVariantAnimation.State.Running:
            target_w = self._current_compact_width()
            target_x = self._get_centered_x(target_w)
            target_y = self._target_compact_y()
            if abs(self.width() - target_w) > 2 or abs(self.x() - target_x) > 2:
                self.setGeometry(target_x, target_y, target_w, self.COMPACT_H)

    # ------------------------------------------------------------------ Tema
    def _apply_live_theme(self):
        """Aplica tokens visuais OLED Black e cor de destaque contextual aos componentes vivos."""
        # Bloco em destaque do Centro de Controle
        self.cc_hero_card.setStyleSheet(
            f"QFrame#cc_hero_card {{ "
            f"  background-color: rgba(255, 255, 255, 0.055); "
            f"  border: 1px solid rgba(255, 255, 255, 0.14); "
            f"  border-radius: {Theme.RADIUS_CARD}px; "
            f"}}"
            f"QFrame#cc_hero_card:hover {{ "
            f"  background-color: rgba(255, 255, 255, 0.085); "
            f"  border: 1px solid {Theme.HEX_ACCENT_BORDER_HOVER}; "
            f"}}"
        )
        self.lbl_cc_hero_icon.setStyleSheet(
            f"background-color: rgba(255, 255, 255, 0.08); "
            f"border: 1px solid rgba(255, 255, 255, 0.14); border-radius: 12px;"
        )
        self.lbl_cc_hero_icon.setPixmap(IconFactory.get_icon("gear", 20, Theme.HEX_TEXT_PRIMARY).pixmap(20, 20))
        self.lbl_cc_hero_title.setStyleSheet(f"color: {Theme.HEX_TEXT_PRIMARY}; border: none; background: transparent;")
        self.lbl_cc_hero_sub.setStyleSheet(f"color: {Theme.HEX_TEXT_SECONDARY}; border: none; background: transparent;")
        self.btn_cc_open.setStyleSheet(Theme.style_action_button_accent())

        # Card de mídia contextual
        self.stage_media_card.setStyleSheet(Theme.style_card())
        self.lbl_media_title.setStyleSheet(f"color: {Theme.HEX_TEXT_PRIMARY}; border: none; background: transparent;")
        self.lbl_media_sub.setStyleSheet(f"color: {Theme.HEX_TEXT_SECONDARY}; border: none; background: transparent;")
        self.prog_active.setStyleSheet(f"background-color: {Theme.HEX_ACCENT}; border-radius: 1px;")
        self.prog_thumb.setStyleSheet("background-color: #FFFFFF; border-radius: 3px;")
        self.prog_rest.setStyleSheet("background-color: rgba(255, 255, 255, 0.16); border-radius: 1px;")

        self.btn_media_play.setStyleSheet(Theme.style_play_circle_button())
        self.btn_media_play.setIcon(IconFactory.get_icon("pause" if self.media_active else "play", 15, Theme.HEX_TEXT_ON_ACCENT))
        self.btn_media_play.setIconSize(QSize(15, 15))

        for b_sub, ic_n in [(self.btn_media_prev, "prev"), (self.btn_media_next, "next")]:
            b_sub.setStyleSheet(Theme.style_media_transport_subtle())
            b_sub.setIcon(IconFactory.get_icon(ic_n, 13, Theme.HEX_TEXT_PRIMARY))
            b_sub.setIconSize(QSize(13, 13))

        # Métricas e ações rápidas da página INÍCIO
        for _k, (m_card, lt, lv) in self.home_metric_cards.items():
            m_card.setStyleSheet(Theme.style_card())
            lt.setStyleSheet(f"color: {Theme.HEX_TEXT_MUTED}; border: none; background: transparent;")
            lv.setStyleSheet(f"color: {Theme.HEX_TEXT_PRIMARY}; border: none; background: transparent;")

        for qb in self.stage_quick_btns:
            qb.setStyleSheet(Theme.style_dock_squircle(False))

        # Swatches de Aparência na seção SISTEMA
        for p_key, sbtn in self.swatch_buttons.items():
            p_hex = Theme.PRESETS[p_key]["hex"]
            is_sel = (Theme.current_preset == p_key)
            brd = p_hex if is_sel else "rgba(255, 255, 255, 0.10)"
            bg = Theme.HEX_ACCENT_MUTED if is_sel else "rgba(255, 255, 255, 0.035)"
            sbtn.setIcon(IconFactory.get_icon("check" if is_sel else "circle", 11, p_hex))
            sbtn.setIconSize(QSize(11, 11))
            sbtn.setStyleSheet(
                f"QPushButton {{ background-color: {bg}; color: {'#FFFFFF' if is_sel else Theme.HEX_TEXT_SECONDARY}; "
                f"border: {'1.5px' if is_sel else '1px'} solid {brd}; border-radius: 8px; padding: 3px 8px; }}"
                f"QPushButton:hover {{ border: 1px solid {p_hex}; color: #FFFFFF; }}"
            )

        self.hex_preview_box.setStyleSheet(
            f"background-color: {Theme.HEX_ACCENT}; border: 1px solid rgba(255, 255, 255, 0.35); border-radius: 6px;"
        )
        self.hex_input.setStyleSheet(
            f"QLineEdit {{ background-color: {Theme.HEX_BG_INPUT}; color: #FFFFFF; "
            f"border: 1px solid {Theme.HEX_BORDER}; border-radius: 7px; padding: 2px 8px; font-family: 'Consolas'; font-size: 10.5px; }}"
        )
        self.btn_apply_hex.setStyleSheet(Theme.style_action_button_accent())
        self._update_behavior_buttons_style()
        self.btn_taskbar.setStyleSheet(Theme.style_taskbar_toggle_button(self.taskbar_hidden))

        if hasattr(self, "launcher_bar") and self.launcher_bar:
            self.launcher_bar.apply_theme()
        if hasattr(self, "pager_indicator") and self.pager_indicator:
            self.pager_indicator.update()
        if hasattr(self, "overlay_manager") and self.overlay_manager:
            self.overlay_manager.apply_theme()
        if hasattr(self, "tray") and self.tray:
            self.tray.setIcon(IconFactory.get_icon("taskbar", 32, Theme.HEX_TEXT_PRIMARY))
        self.update()

    def _update_behavior_buttons_style(self):
        sat_on = Theme.satellite_enabled
        self.btn_toggle_satellite.setText(f" Satélite de Mídia: {'Ativo' if sat_on else 'Inativo'}")
        self.btn_toggle_satellite.setIcon(
            IconFactory.get_icon("check" if sat_on else "close", 10, Theme.HEX_TEXT_PRIMARY if sat_on else Theme.HEX_TEXT_MUTED)
        )
        self.btn_toggle_satellite.setStyleSheet(Theme.style_filter_pill(sat_on))

        for m_key, mbtn in self.material_buttons.items():
            is_sel = (Theme.notch_material == m_key)
            mbtn.setIcon(
                IconFactory.get_icon("check" if is_sel else "circle", 10, Theme.HEX_TEXT_PRIMARY if is_sel else Theme.HEX_TEXT_MUTED)
            )
            mbtn.setStyleSheet(Theme.style_filter_pill(is_sel))

    def _update_dock_styles(self):
        if hasattr(self, "pager_indicator") and self.pager_indicator:
            self.pager_indicator.set_current_index(self.active_tab_idx)

    def _update_filter_pills_style(self):
        if hasattr(self, "launcher_bar") and self.launcher_bar:
            self.launcher_bar.popup.apply_theme(self.launcher_bar.launcher_filter)

    def _set_launcher_filter(self, fid: str):
        if hasattr(self, "launcher_bar") and self.launcher_bar:
            self.launcher_bar.set_filter(fid)

    def _on_select_preset(self, preset_key: str):
        Theme.apply_preset(preset_key, save=True)
        self.hex_input.setText(Theme.custom_hex)
        self._apply_live_theme()

    def _on_apply_custom_hex(self):
        val = self.hex_input.text().strip()
        if Theme.apply_custom_hex(val, save=True):
            self.hex_input.setText(Theme.custom_hex)
            self._apply_live_theme()

    def _on_toggle_satellite_pref(self):
        Theme.satellite_enabled = not Theme.satellite_enabled
        Theme.save_preferences()
        self._update_behavior_buttons_style()
        self._sync_compact_capsule_geometry()
        self.update()

    def _on_select_notch_material(self, material_key: str):
        Theme.apply_notch_material(material_key, save=True)
        self._apply_live_theme()

    def _on_play_pause_clicked(self):
        MediaController.play_pause()
        self.update()

    # ---------------------------------------------- Navegação pelos 3 painéis
    def _switch_tab(self, idx: int, animate: bool = True):
        """
        Alterna entre os 3 painéis lineares:
        0 = INÍCIO, 1 = JANELAS, 2 = SISTEMA.
        Índices legados (>= 3) são mapeados para SISTEMA (2) para compatibilidade.
        """
        target = max(0, min(self.stack.count() - 1, int(idx)))
        self.active_tab_idx = target
        self.stack.setCurrentIndex(target, animate=animate)
        self.pager_indicator.set_current_index(target)

    def _on_pager_index_changed(self, idx: int):
        self.active_tab_idx = idx
        self.pager_indicator.set_current_index(idx)
        if idx == self.PAGE_WINDOWS:
            self._refresh_open_tasks()
        elif idx == self.PAGE_SYSTEM:
            self._refresh_stats()

    def _create_empty_state_widget(self) -> QWidget:
        """Estado vazio contextual quando não há janelas em segundo plano."""
        card = QFrame()
        card.setObjectName("empty_tasks_card")
        card.setStyleSheet(Theme.style_empty_state_card())

        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon_lbl = QLabel()
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setPixmap(IconFactory.get_icon("window", 28, Theme.HEX_TEXT_MUTED).pixmap(28, 28))
        icon_lbl.setStyleSheet("border: none; background: transparent;")
        layout.addWidget(icon_lbl)

        title_lbl = QLabel("Nenhuma janela em segundo plano")
        title_lbl.setFont(Theme.get_font(10.5, QFont.Weight.DemiBold))
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_lbl.setStyleSheet(f"color: {Theme.HEX_TEXT_PRIMARY}; border: none; background: transparent;")
        layout.addWidget(title_lbl)

        desc_lbl = QLabel("Suas janelas abertas aparecerão aqui no carrossel visual com foco e agrupamento.")
        desc_lbl.setFont(Theme.get_font(8.8, QFont.Weight.Normal))
        desc_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet(f"color: {Theme.HEX_TEXT_MUTED}; border: none; background: transparent;")
        layout.addWidget(desc_lbl)

        btn_action = QPushButton("  Pesquisar Aplicativos no Launcher")
        btn_action.setFont(Theme.get_font(9.0, QFont.Weight.DemiBold))
        btn_action.setIcon(IconFactory.get_icon("search", 12, Theme.HEX_TEXT_PRIMARY))
        btn_action.setIconSize(QSize(12, 12))
        btn_action.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_action.setStyleSheet(Theme.style_action_button_accent())
        btn_action.clicked.connect(self.launcher_bar.open_popup)
        layout.addWidget(btn_action, alignment=Qt.AlignmentFlag.AlignCenter)

        return card

    def _refresh_open_tasks(self):
        """
        Renderiza o Carrossel Visual de Janelas em Foco.
        Miniaturas capturadas estritamente sob demanda apenas quando a página JANELAS (1) está ativa.
        """
        if not self.is_expanded or self.active_tab_idx != self.PAGE_WINDOWS:
            return

        while self.tasks_container_layout.count() > 1:
            item = self.tasks_container_layout.takeAt(0)
            w = item.widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()

        self.open_windows = TaskManager.get_open_windows()
        if not self.open_windows:
            empty_widget = self._create_empty_state_widget()
            self.tasks_container_layout.insertWidget(0, empty_widget)
            return

        n = len(self.open_windows)
        if self.carousel_idx >= n:
            self.carousel_idx = 0

        carousel_wrap = QWidget()
        carousel_wrap.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        cw_layout = QVBoxLayout(carousel_wrap)
        cw_layout.setContentsMargins(0, 2, 0, 0)
        cw_layout.setSpacing(8)

        stage_row = QHBoxLayout()
        stage_row.setContentsMargins(2, 0, 2, 0)
        stage_row.setSpacing(10)
        stage_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

        if n == 1:
            slots = [(0, True)]
        elif n == 2:
            other = (self.carousel_idx + 1) % 2
            slots = [(self.carousel_idx, True), (other, False)]
        else:
            left_i = (self.carousel_idx - 1) % n
            right_i = (self.carousel_idx + 1) % n
            slots = [(left_i, False), (self.carousel_idx, True), (right_i, False)]

        for w_idx, is_center in slots:
            win = self.open_windows[w_idx]
            hwnd = win["hwnd"]
            kind = win.get("kind", "windows")
            inst_count = win.get("instance_count", 1)

            card_w = 196 if is_center else 136
            thumb_h = 104 if is_center else 80

            slot_frame = QFrame()
            slot_frame.setFixedWidth(card_w)
            slot_frame.setStyleSheet("background: transparent; border: none;")
            sf_layout = QVBoxLayout(slot_frame)
            sf_layout.setContentsMargins(0, 0 if is_center else 12, 0, 0)
            sf_layout.setSpacing(5)

            real_thumb = TaskManager.get_thumbnail_on_demand(hwnd, card_w - 14, thumb_h - 22)
            preview_pix = IconFactory.get_window_preview_pixmap(
                kind, card_w, thumb_h, is_center, Theme.HEX_ACCENT, real_thumb
            )

            btn_preview = QPushButton()
            btn_preview.setFixedSize(card_w, thumb_h)
            btn_preview.setIcon(QIcon(preview_pix))
            btn_preview.setIconSize(QSize(card_w, thumb_h))
            btn_preview.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn_preview.setStyleSheet("QPushButton { background: transparent; border: none; }")
            btn_preview.setToolTip(f"{win['app_name']} — {win['title']}")

            if is_center:
                btn_preview.clicked.connect(lambda checked=False, h=hwnd: self._focus_and_collapse(h))
            else:
                btn_preview.clicked.connect(lambda checked=False, idx_target=w_idx: self._rotate_carousel_to(idx_target))

            sf_layout.addWidget(btn_preview)

            meta_row = QHBoxLayout()
            meta_row.setContentsMargins(4, 0, 4, 0)
            meta_row.setSpacing(5)

            ic_lbl = QLabel()
            ic_lbl.setPixmap(IconFactory.get_app_pixmap(kind, 16 if is_center else 14))
            ic_lbl.setStyleSheet("background: transparent; border: none;")
            meta_row.addWidget(ic_lbl)

            name_lbl = QLabel(win["app_name"])
            name_lbl.setFont(Theme.get_font(9.2 if is_center else 8.4, QFont.Weight.DemiBold if is_center else QFont.Weight.Medium))
            name_lbl.setStyleSheet(
                f"color: {'#FFFFFF' if is_center else Theme.HEX_TEXT_SECONDARY}; background: transparent; border: none;"
            )
            meta_row.addWidget(name_lbl, stretch=1)

            count_txt = f"{inst_count} jan" if not is_center else (f"{inst_count} janelas" if inst_count > 1 else "Ativa")
            badge_lbl = self._make_keycap_label(count_txt, is_center)
            meta_row.addWidget(badge_lbl)

            if is_center:
                btn_close_w = QPushButton()
                btn_close_w.setIcon(IconFactory.get_icon("close", 9, Theme.HEX_TEXT_MUTED))
                btn_close_w.setIconSize(QSize(9, 9))
                btn_close_w.setFixedSize(18, 18)
                btn_close_w.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                btn_close_w.setToolTip("Fechar Janela")
                btn_close_w.setStyleSheet(
                    "QPushButton { background: transparent; border: none; border-radius: 4px; }"
                    "QPushButton:hover { background-color: rgba(244, 63, 94, 0.28); }"
                )
                btn_close_w.clicked.connect(lambda checked=False, h=hwnd: self._close_task(h))
                meta_row.addWidget(btn_close_w)

            sf_layout.addLayout(meta_row)
            stage_row.addWidget(slot_frame)

        cw_layout.addLayout(stage_row)

        dots_row = QHBoxLayout()
        dots_row.setSpacing(6)
        dots_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        for i in range(min(n, 8)):
            dot = QPushButton()
            is_cur = (i == self.carousel_idx)
            dot.setFixedSize(18 if is_cur else 6, 6)
            dot.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            dot_col = Theme.HEX_ACCENT if is_cur else "rgba(255, 255, 255, 0.25)"
            dot.setStyleSheet(f"QPushButton {{ background-color: {dot_col}; border: none; border-radius: 3px; }}")
            dot.clicked.connect(lambda checked=False, target=i: self._rotate_carousel_to(target))
            dots_row.addWidget(dot)

        cw_layout.addLayout(dots_row)
        self.tasks_container_layout.insertWidget(0, carousel_wrap)

    def _rotate_carousel_to(self, idx: int):
        self.carousel_idx = idx
        self._refresh_open_tasks()

    def _focus_and_collapse(self, hwnd: int):
        TaskManager.focus_window(hwnd)
        self.collapse()

    def _close_task(self, hwnd: int):
        TaskManager.close_window(hwnd)
        QTimer.singleShot(280, self._refresh_open_tasks)

    def action_show_desktop(self):
        win32api.keybd_event(win32con.VK_LWIN, 0, 0, 0)
        win32api.keybd_event(ord("D"), 0, 0, 0)
        win32api.keybd_event(ord("D"), 0, win32con.KEYEVENTF_KEYUP, 0)
        win32api.keybd_event(win32con.VK_LWIN, 0, win32con.KEYEVENTF_KEYUP, 0)
        self.collapse()

    def changeEvent(self, event):
        try:
            if event.type() == QEvent.Type.ActivationChange:
                if not self.isActiveWindow() and self.is_expanded:
                    self.collapse()
            super().changeEvent(event)
        except Exception as e:
            log_exception("DynamicIslandWindow.changeEvent", e)

    def enterEvent(self, event):
        try:
            if self.visibility_state == VisibilityMonitor.FULLSCREEN_HIDDEN:
                return
            if not self.is_expanded:
                self.is_hovered = True
                self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))
                if self.visibility_state == VisibilityMonitor.APP_AUTO_HIDE:
                    self.visibility_monitor.set_interaction_flags(edge_hovered=True)
                self.update()
        except Exception as e:
            log_exception("DynamicIslandWindow.enterEvent", e)

    def leaveEvent(self, event):
        try:
            if not self.is_expanded:
                self.is_hovered = False
                self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
                self.visibility_monitor.set_interaction_flags(edge_hovered=False)
                self.update()
        except Exception as e:
            log_exception("DynamicIslandWindow.leaveEvent", e)

    @staticmethod
    def _create_monolith_path(w: float, h: float, cap_w: float, cap_h: float, body_r: float) -> QPainterPath:
        """Gera o caminho vetorial contínuo da Silhueta Monolith fundido ao topo do monitor."""
        cx = w / 2.0
        neck_y = cap_h - 2.0
        fillet = 14.0

        c_left = max(body_r, cx - cap_w / 2.0)
        c_right = min(w - body_r, cx + cap_w / 2.0)
        b_left = 1.0
        b_right = w - 1.0
        b_bot = h - 1.0

        path = QPainterPath()
        path.moveTo(c_left, -2.0)
        path.lineTo(c_right, -2.0)
        path.lineTo(c_right, neck_y - fillet * 0.4)
        path.cubicTo(
            QPointF(c_right, neck_y),
            QPointF(c_right + fillet * 0.4, neck_y),
            QPointF(min(b_right - body_r, c_right + fillet * 1.1), neck_y)
        )
        path.lineTo(b_right - body_r, neck_y)
        path.quadTo(b_right, neck_y, b_right, neck_y + body_r)
        path.lineTo(b_right, b_bot - body_r)
        path.quadTo(b_right, b_bot, b_right - body_r, b_bot)
        path.lineTo(b_left + body_r, b_bot)
        path.quadTo(b_left, b_bot, b_left, b_bot - body_r)
        path.lineTo(b_left, neck_y + body_r)
        path.quadTo(b_left, neck_y, b_left + body_r, neck_y)
        path.lineTo(max(b_left + body_r, c_left - fillet * 1.1), neck_y)
        path.cubicTo(
            QPointF(c_left - fillet * 0.4, neck_y),
            QPointF(c_left, neck_y),
            QPointF(c_left, neck_y - fillet * 0.4)
        )
        path.lineTo(c_left, -2.0)
        path.closeSubpath()
        return path

    def _draw_stealth_dot(self, painter: QPainter, center: QPointF, active: bool = False):
        """Indicador OLED Stealth minimalista (sem brilho colorido permanente)."""
        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        if active:
            col = QColor(Theme.COLOR_ACCENT)
            col.setAlpha(210)
            painter.setBrush(col)
        else:
            painter.setBrush(QColor(130, 130, 130, 110))
        painter.drawEllipse(center, 2.3, 2.3)
        painter.restore()

    def _draw_acoustic_wave(self, painter: QPainter, center: QPointF, color: QColor, heights=(4.5, 9.0, 6.0, 9.5, 4.5)):
        painter.save()
        pen = QPen(color, 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        spacing = 3.8
        total_w = (len(heights) - 1) * spacing
        sx = center.x() - total_w / 2.0
        for i, bh in enumerate(heights):
            x = sx + i * spacing
            painter.drawLine(QPointF(x, center.y() - bh / 2.0), QPointF(x, center.y() + bh / 2.0))
        painter.restore()

    def paintEvent(self, event):
        """Renderização vetorial OLED Black (#000000) com antialiasing nítido."""
        painter = QPainter(self)
        try:
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

            w = float(self.width())
            h = float(self.height())
            notch_bg = QColor(Theme.COLOR_NOTCH_BG)
            notch_border = QColor(Theme.COLOR_NOTCH_BORDER_HOVER if self.is_hovered else Theme.COLOR_NOTCH_BORDER_IDLE)

            # ----------------------------------------------------------------------
            # MODO 1: CÁPSULA COMPACTA — OLED STEALTH (190 x 30 ou 340 x 30 com satélite)
            # ----------------------------------------------------------------------
            if not self.is_expanded and h <= self.COMPACT_H + 14:
                sat_visible = self.is_media_satellite_visible()
                r = min(13.0, h * 0.44)

                if sat_visible and w >= self.COMPACT_SAT_W - 10:
                    main_w = 142.0
                    gap = 6.0
                    sat_w = w - main_w - gap - 2.0

                    path_m = QPainterPath()
                    path_m.moveTo(1.0, -2.0)
                    path_m.lineTo(main_w, -2.0)
                    path_m.lineTo(main_w, h - r - 1.0)
                    path_m.quadTo(main_w, h - 1.0, main_w - r, h - 1.0)
                    path_m.lineTo(1.0 + r, h - 1.0)
                    path_m.quadTo(1.0, h - 1.0, 1.0, h - r - 1.0)
                    path_m.closeSubpath()

                    painter.setBrush(notch_bg)
                    painter.setPen(QPen(notch_border, 1.0))
                    painter.drawPath(path_m)

                    path_s = QPainterPath()
                    s_left = 1.0 + main_w + gap
                    s_right = s_left + sat_w
                    path_s.moveTo(s_left, -2.0)
                    path_s.lineTo(s_right, -2.0)
                    path_s.lineTo(s_right, h - r - 1.0)
                    path_s.quadTo(s_right, h - 1.0, s_right - r, h - 1.0)
                    path_s.lineTo(s_left + r, h - 1.0)
                    path_s.quadTo(s_left, h - 1.0, s_left, h - r - 1.0)
                    path_s.closeSubpath()

                    painter.setBrush(notch_bg)
                    ctx_border = QColor(255, 255, 255, 42)
                    painter.setPen(QPen(ctx_border, 1.0))
                    painter.drawPath(path_s)

                    self._draw_stealth_dot(painter, QPointF(20.0, h / 2.0), active=True)
                    painter.setFont(Theme.get_font(9.8, QFont.Weight.DemiBold))
                    painter.setPen(QColor(238, 238, 238, 235))
                    painter.drawText(QRectF(32.0, 0.0, main_w - 40.0, h), Qt.AlignmentFlag.AlignCenter, self.time_str)

                    art_pix = IconFactory.get_album_art_pixmap(20)
                    painter.drawPixmap(int(s_left + 7), int((h - 20) / 2), art_pix)
                    painter.setFont(Theme.get_font(8.6, QFont.Weight.Medium))
                    painter.setPen(QColor(Theme.HEX_TEXT_PRIMARY))
                    painter.drawText(
                        QRectF(s_left + 34.0, 0.0, sat_w - 66.0, h),
                        Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                        self.media_title_short or "Reproduzindo"
                    )
                    self._draw_acoustic_wave(painter, QPointF(s_right - 18.0, h / 2.0), Theme.COLOR_ACCENT_LIGHT, (4.5, 9.0, 6.0, 9.5, 4.5))
                    painter.restore()
                    return

                path_pill = QPainterPath()
                path_pill.moveTo(1.0, -2.0)
                path_pill.lineTo(w - 1.0, -2.0)
                path_pill.lineTo(w - 1.0, h - r - 1.0)
                path_pill.quadTo(w - 1.0, h - 1.0, w - r - 1.0, h - 1.0)
                path_pill.lineTo(r + 1.0, h - 1.0)
                path_pill.quadTo(1.0, h - 1.0, 1.0, h - r - 1.0)
                path_pill.closeSubpath()

                painter.setBrush(notch_bg)
                painter.setPen(QPen(notch_border, 1.0))
                painter.drawPath(path_pill)

                self._draw_stealth_dot(painter, QPointF(22.0, h / 2.0), active=(self.media_active or self.is_hovered))

                painter.setFont(Theme.get_font(10.0, QFont.Weight.DemiBold))
                clock_col = QColor(242, 242, 242, 242) if (self.is_hovered or self.media_active) else QColor(212, 212, 212, 208)
                painter.setPen(clock_col)
                painter.drawText(QRectF(36.0, 0.0, 78.0, h), Qt.AlignmentFlag.AlignCenter, self.time_str)

                painter.setPen(QPen(QColor(255, 255, 255, 16), 1.0))
                painter.drawLine(QPointF(122.0, h * 0.28), QPointF(122.0, h * 0.72))

                wave_heights = (5.0, 9.5, 6.5, 10.0, 5.0) if self.media_active else (3.5, 6.5, 4.5, 7.0, 3.5)
                wave_col = Theme.COLOR_ACCENT_LIGHT if self.media_active else QColor(130, 130, 130, 125)
                self._draw_acoustic_wave(painter, QPointF(154.0, h / 2.0), wave_col, wave_heights)
                painter.restore()
                return

            # ----------------------------------------------------------------------
            # MODO 2: SILHUETA MONOLITH EXPANDIDA (Superfície OLED #000000)
            # ----------------------------------------------------------------------
            cap_w = min(190.0, w - 56.0)
            cap_h = float(self.COMPACT_H)
            mono_path = self._create_monolith_path(w, h, cap_w, cap_h, Theme.RADIUS_PANEL)

            grad = QLinearGradient(0, 0, 0, h)
            grad.setColorAt(0.0, Theme.COLOR_BG_GRAD_TOP)
            grad.setColorAt(0.45, Theme.COLOR_BG_GRAD_MID)
            grad.setColorAt(1.0, Theme.COLOR_BG_GRAD_BOTTOM)
            painter.fillPath(mono_path, grad)

            b_grad = QLinearGradient(0, 0, 0, h)
            b_grad.setColorAt(0.0, QColor(255, 255, 255, 22))
            b_grad.setColorAt(0.35, QColor(255, 255, 255, 28))
            b_grad.setColorAt(1.0, QColor(255, 255, 255, 16))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QBrush(b_grad), 1.0))
            painter.drawPath(mono_path)

            cx = w / 2.0
            head_rect = QRectF(cx - cap_w / 2.0 + 4.0, 3.0, cap_w - 8.0, cap_h - 4.0)
            painter.setBrush(notch_bg)
            painter.setPen(QPen(QColor(255, 255, 255, 18), 0.8))
            painter.drawRoundedRect(head_rect, (cap_h - 4.0) / 2.0, (cap_h - 4.0) / 2.0)

            self._draw_stealth_dot(painter, QPointF(head_rect.x() + 18.0, head_rect.center().y()), active=True)
            painter.setFont(Theme.get_font(9.8, QFont.Weight.DemiBold))
            painter.setPen(QColor(240, 240, 240, 235))
            painter.drawText(QRectF(head_rect.x() + 30.0, head_rect.y(), 76.0, head_rect.height()), Qt.AlignmentFlag.AlignCenter, self.time_str)

            painter.setPen(QPen(QColor(255, 255, 255, 18), 1.0))
            painter.drawLine(QPointF(head_rect.x() + 114.0, head_rect.y() + 6.0), QPointF(head_rect.x() + 114.0, head_rect.bottom() - 6.0))
            wave_col_exp = Theme.COLOR_ACCENT_LIGHT if self.media_active else QColor(160, 160, 160, 150)
            self._draw_acoustic_wave(painter, QPointF(head_rect.x() + 146.0, head_rect.center().y()), wave_col_exp, (4.0, 8.5, 5.5, 9.0, 4.0))
            painter.restore()
        except Exception as e:
            log_exception("DynamicIslandWindow.paintEvent", e)
        finally:
            painter.end()

    def mousePressEvent(self, event):
        try:
            if event.button() == Qt.MouseButton.LeftButton:
                if self.is_expanded:
                    if event.position().y() <= self.COMPACT_H:
                        self.collapse()
                else:
                    self.expand()
        except Exception as e:
            log_exception("DynamicIslandWindow.mousePressEvent", e)

    def keyPressEvent(self, event):
        try:
            key = event.key()
            mods = event.modifiers()

            # Se o popup do Launcher estiver aberto ou com texto, trata primeiro lá
            if self.is_expanded and self.launcher_bar.handle_key(key):
                return

            if key == Qt.Key.Key_Escape:
                self.collapse()
                return

            # Atalhos Alt+1..3 ou Ctrl+1..3 para alternar entre os 3 painéis
            if mods & (Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.ControlModifier):
                key_map = {
                    Qt.Key.Key_1: self.PAGE_HOME,
                    Qt.Key.Key_2: self.PAGE_WINDOWS,
                    Qt.Key.Key_3: self.PAGE_SYSTEM,
                }
                if key in key_map:
                    self._switch_tab(key_map[key], animate=True)
                    return
                if key == Qt.Key.Key_Right:
                    self.stack.next_page(animate=True)
                    return
                if key == Qt.Key.Key_Left:
                    self.stack.prev_page(animate=True)
                    return

            if self.is_expanded and self.active_tab_idx == self.PAGE_WINDOWS and self.open_windows:
                if key == Qt.Key.Key_Right:
                    self.carousel_idx = (self.carousel_idx + 1) % len(self.open_windows)
                    self._refresh_open_tasks()
                elif key == Qt.Key.Key_Left:
                    self.carousel_idx = (self.carousel_idx - 1 + len(self.open_windows)) % len(self.open_windows)
                    self._refresh_open_tasks()
                elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                    hwnd = self.open_windows[self.carousel_idx]["hwnd"]
                    self._focus_and_collapse(hwnd)
            elif self.is_expanded:
                # Setas horizontais trocam de painel quando não há foco em campo de texto
                fw = QApplication.focusWidget()
                if not isinstance(fw, QLineEdit):
                    if key == Qt.Key.Key_Right:
                        self.stack.next_page(animate=True)
                    elif key == Qt.Key.Key_Left:
                        self.stack.prev_page(animate=True)
        except Exception as e:
            log_exception("DynamicIslandWindow.keyPressEvent", e)

    def toggle_expand(self):
        if self.is_expanded:
            self.collapse()
        else:
            self.expand()

    def expand(self):
        if self.is_expanded:
            return
        try:
            fg = win32gui.GetForegroundWindow()
            if fg and fg != int(self.winId()):
                self._prev_fg_hwnd = fg
        except Exception:
            self._prev_fg_hwnd = None

        self._vis_anim.stop()
        self.is_expanded = True
        self.is_hovered = False
        self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        self.visibility_monitor.set_interaction_flags(is_expanded=True)
        # Sempre abre na página INÍCIO (0)
        self._switch_tab(self.PAGE_HOME, animate=False)
        self._update_cc_hero_summary()
        if not self.isVisible():
            self.show()

        if Theme.reduced_motion_enabled():
            self._on_anim_step(1.0)
            self._on_anim_finished()
            return

        self.anim.stop()
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.start()

    def collapse(self):
        if not self.is_expanded:
            return
        self.is_expanded = False
        if hasattr(self, "launcher_bar") and self.launcher_bar:
            self.launcher_bar.close_popup(clear_text=True)
        self.content.hide()
        TaskManager.clear_thumbnail_cache()
        self.visibility_monitor.set_interaction_flags(is_expanded=False, edge_hovered=False)

        if self._prev_fg_hwnd and win32gui.IsWindow(self._prev_fg_hwnd):
            try:
                if win32gui.GetForegroundWindow() == int(self.winId()):
                    win32gui.SetForegroundWindow(self._prev_fg_hwnd)
            except Exception:
                pass
        self._prev_fg_hwnd = None

        if Theme.reduced_motion_enabled():
            self._on_anim_step(0.0)
            self._on_anim_finished()
            return

        self.anim.stop()
        self.anim.setStartValue(1.0)
        self.anim.setEndValue(0.0)
        self.anim.start()

    def _on_anim_step(self, progress: float):
        geo = self._get_screen_geometry()
        base_w = self._current_compact_width()
        w = int(base_w + (self.EXPANDED_W - base_w) * progress)
        h = int(self.COMPACT_H + (self.EXPANDED_H - self.COMPACT_H) * progress)
        x = self._get_centered_x(w)
        target_y = geo.y() + self.TOP_MARGIN
        self.setGeometry(x, target_y, w, h)
        self.update()

    def _on_anim_finished(self):
        if self.is_expanded:
            self.content.show()
            self.activateWindow()
            if self.active_tab_idx == self.PAGE_WINDOWS:
                self._refresh_open_tasks()
        else:
            self.visibility_monitor.evaluate_now()
            self._apply_visibility_state(self.visibility_monitor.current_state(), animate=not Theme.reduced_motion_enabled())
        self.update()

    def toggle_taskbar(self):
        self.taskbar_hidden = not self.taskbar_hidden
        set_taskbar_visible(not self.taskbar_hidden)
        if hasattr(self, "btn_taskbar") and self.btn_taskbar:
            self.btn_taskbar.setText(" Barra: Oculta" if self.taskbar_hidden else " Barra: Visível")
            self.btn_taskbar.setStyleSheet(Theme.style_taskbar_toggle_button(self.taskbar_hidden))
        if hasattr(self, "act_tb") and self.act_tb:
            self.act_tb.setText("Exibir Barra de Tarefas" if self.taskbar_hidden else "Ocultar Barra de Tarefas")

    def _update_launcher_results(self, query: str):
        if hasattr(self, "launcher_bar") and self.launcher_bar:
            self.launcher_bar.update_results(query)

    def _classify_launcher_icon(self, app: dict) -> str:
        return LauncherBar.classify_icon(app)

    def _render_launcher_rows(self):
        if hasattr(self, "launcher_bar") and self.launcher_bar:
            self.launcher_bar.render_rows()

    def launch_app(self, cmd: str):
        AppIndexer.launch(cmd)
        self.collapse()

    def _poll_hotkey(self):
        try:
            alt_down = (ctypes.windll.user32.GetAsyncKeyState(0x12) & 0x8000) != 0
            space_down = (ctypes.windll.user32.GetAsyncKeyState(0x20) & 0x8000) != 0
            c_down = (ctypes.windll.user32.GetAsyncKeyState(0x43) & 0x8000) != 0

            if alt_down and space_down:
                if not self._hotkey_pressed:
                    self._hotkey_pressed = True
                    self.toggle_expand()
            else:
                self._hotkey_pressed = False

            if alt_down and c_down:
                if not self._cc_hotkey_pressed:
                    self._cc_hotkey_pressed = True
                    self.toggle_control_center()
            else:
                self._cc_hotkey_pressed = False
        except Exception:
            pass

    def _refresh_stats(self):
        try:
            stats = SystemMonitor.get_stats()

            self.time_str = stats["time"]
            self.cpu_str = f"{int(stats['cpu'])}%"
            self.has_battery = stats["has_battery"]
            self.is_charging = stats["is_charging"]

            self._sync_compact_capsule_geometry()

            # Atualiza métricas resumidas na página INÍCIO e na página SISTEMA
            if hasattr(self, "home_metric_cards") and self.home_metric_cards:
                self.home_metric_cards["CPU"][2].setText(f"{int(stats['cpu'])}%")
                self.home_metric_cards["RAM"][2].setText(f"{stats['ram']}%")
                _, lt_pwr, lv_pwr = self.home_metric_cards["PWR"]
                if self.has_battery and stats["battery_percent"] is not None:
                    lt_pwr.setText("BATERIA")
                    chg = " ⚡" if self.is_charging else ""
                    lv_pwr.setText(f"{stats['battery_percent']}%{chg}")
                else:
                    lt_pwr.setText("DISCO C:")
                    lv_pwr.setText(f"{stats['disk_free_gb']} GB")
                self.home_metric_cards["NET"][2].setText(stats["net_str"])

            if self.is_expanded:
                self.lbl_health_text.setText(f"Estável • CPU {int(stats['cpu'])}%")
                if hasattr(self, "badge_labels") and self.badge_labels:
                    _, lbl_cpu = self.badge_labels["CPU"]
                    lbl_cpu.setText(f"{int(stats['cpu'])}%")
                    _, lbl_ram = self.badge_labels["RAM"]
                    lbl_ram.setText(f"{stats['ram']}%")
                    lbl_disk_t, lbl_disk_v = self.badge_labels["DISK"]
                    if self.has_battery and stats["battery_percent"] is not None:
                        lbl_disk_t.setText("BATERIA")
                        chg = " ⚡" if self.is_charging else ""
                        lbl_disk_v.setText(f"{stats['battery_percent']}%{chg}")
                    else:
                        lbl_disk_t.setText("DISCO C:")
                        lbl_disk_v.setText(f"{stats['disk_free_gb']} GB")
                    _, lbl_net = self.badge_labels["NET"]
                    lbl_net.setText(stats["net_str"])
            self.update()
        except Exception:
            pass

    def quit_app(self):
        """Finaliza o Monolith garantindo restauração da barra de tarefas e encerramento limpo dos adaptadores."""
        try:
            log_info("Encerrando Monolith normalmente")
            for t in (
                getattr(self, "stats_timer", None),
                getattr(self, "tasks_timer", None),
                getattr(self, "hotkey_timer", None),
                getattr(self, "_hw_refresh_timer", None),
            ):
                if t:
                    t.stop()
            if hasattr(self, "visibility_monitor") and self.visibility_monitor:
                self.visibility_monitor.stop()
            app_inst = QApplication.instance()
            if app_inst and getattr(self, "_device_filter", None):
                app_inst.removeNativeEventFilter(self._device_filter)
            set_taskbar_visible(True)
            TaskManager.clear_thumbnail_cache()
            if hasattr(self, "overlay_manager") and self.overlay_manager:
                self.overlay_manager.dismiss(immediate=True)
            if hasattr(self, "media_session") and self.media_session:
                self.media_session.shutdown()
            if hasattr(self, "radio_adapter") and self.radio_adapter:
                self.radio_adapter.shutdown()
            if hasattr(self, "tray") and self.tray:
                self.tray.hide()
        except Exception as e:
            log_exception("DynamicIslandWindow.quit_app", e)
        QApplication.quit()


def main():
    console_mode = "--console" in sys.argv
    setup_diagnostics(console_mode=console_mode)
    atexit.register(shutdown_diagnostics)

    mutex = win32event.CreateMutex(None, False, "Monolith_SingleInstance_Mutex")
    if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
        log_info("Instância já em execução detectada. Enviando sinal de ativação...")
        try:
            hwnd = win32gui.FindWindow(None, "Monolith")
            if hwnd:
                win32gui.PostMessage(hwnd, WM_MONOLITH_ACTIVATE, 0, 0)
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                win32gui.SetForegroundWindow(hwnd)
        except Exception as e:
            log_exception("main.activate_existing", e)
        return

    app = QApplication(sys.argv)
    app.setApplicationName("Monolith")
    app.setApplicationDisplayName("Monolith")
    app.setQuitOnLastWindowClosed(False)
    ico_path = get_resource_path("build", "monolith.ico")
    if os.path.exists(ico_path):
        app.setWindowIcon(QIcon(ico_path))
    else:
        app.setWindowIcon(IconFactory.get_icon("taskbar", 32, Theme.HEX_TEXT_PRIMARY))

    win = DynamicIslandWindow()
    if win.visibility_state != VisibilityMonitor.FULLSCREEN_HIDDEN:
        win.show()
    log_info("Monolith iniciado com sucesso (geometria=%s, estado=%s)", win.geometry(), win.visibility_state)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
