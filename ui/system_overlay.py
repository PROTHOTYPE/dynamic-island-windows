"""
Monolith — ui/system_overlay.py (RC 0.2)
Centro de Controle desacoplado com:
- BackdropDimWidget: captura rápida pré-exibição com desfoque Gaussiano real do desktop + vinheta
  escura elegante (nunca tela cinza uniforme; fallback limpo em falha de captura).
- ControlCenterOverlay: superfície de vidro escuro obsidiana com cantos suaves, animações nativas
  Qt (abertura deslizante, recolhimento suave, transição animada para flyouts e feedback tátil),
  capacidades reais de hardware (oculta rádios/bateria inexistentes sem controles enganosos),
  tipografia sem truncamento e ícones 100% vetoriais DPI-aware.
- SystemOverlayManager: ciclo de vida, Z-order, propagação de tema em tempo real e restauração de foco.
"""

import ctypes
from ctypes import c_int, byref, wintypes

import win32gui

from PyQt6.QtCore import (
    Qt, QRectF, QPointF, QPoint, QTimer, QObject, pyqtSignal, QUrl,
    QVariantAnimation, QPropertyAnimation, QParallelAnimationGroup, QEasingCurve
)
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QFontMetricsF, QPainterPath,
    QLinearGradient, QRadialGradient, QCursor, QMouseEvent,
    QKeyEvent, QDesktopServices, QPixmap
)
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLineEdit, QGraphicsScene, QGraphicsPixmapItem, QGraphicsBlurEffect
)

from core.diagnostics import log_exception
from core.media_controller import MediaController
from ui.icons import IconFactory
from ui.theme import Theme

# Constantes DWM nativas (mantidas para compatibilidade de diagnóstico)
DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWA_SYSTEMBACKDROP_TYPE = 38
DWMSBT_TRANSIENTWINDOW = 3

try:
    dwmapi = ctypes.windll.dwmapi
except Exception:
    dwmapi = None


def apply_dwm_acrylic(hwnd: int) -> bool:
    """Aplica modo escuro DWM seguro ao HWND (evita tela cinza em janelas layered fullscreen)."""
    if not dwmapi or not hwnd:
        return False
    try:
        h_wnd = wintypes.HWND(int(hwnd))
        dark = c_int(1)
        hr = dwmapi.DwmSetWindowAttribute(h_wnd, wintypes.DWORD(DWMWA_USE_IMMERSIVE_DARK_MODE), byref(dark), 4)
        return hr == 0
    except Exception:
        return False


def _blur_desktop_pixmap(raw_pix: QPixmap, radius: float = 11.0) -> QPixmap | None:
    """Aplica desfoque Gaussiano rápido em downscale 1/4 usando QGraphicsBlurEffect nativo."""
    if raw_pix is None or raw_pix.isNull():
        return None
    try:
        target_w = max(160, raw_pix.width() // 4)
        target_h = max(90, raw_pix.height() // 4)
        small = raw_pix.scaled(
            target_w,
            target_h,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        scene = QGraphicsScene()
        item = QGraphicsPixmapItem(small)
        eff = QGraphicsBlurEffect()
        eff.setBlurRadius(radius)
        eff.setBlurHints(QGraphicsBlurEffect.BlurHint.PerformanceHint)
        item.setGraphicsEffect(eff)
        scene.addItem(item)

        blurred = QPixmap(small.size())
        blurred.fill(Qt.GlobalColor.transparent)
        p = QPainter(blurred)
        scene.render(p, QRectF(blurred.rect()), QRectF(small.rect()))
        p.end()
        return blurred
    except Exception:
        return None


class BackdropDimWidget(QWidget):
    """Overlay externo com desfoque real do conteúdo subjacente e escurecimento escuro limpo."""

    clicked_outside = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.acrylic_enabled = False
        self._blurred_bg: QPixmap | None = None
        self.setWindowTitle("Monolith Overlay")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self._update_geometry()

    def _update_geometry(self):
        screen = QApplication.primaryScreen()
        if screen:
            self.setGeometry(screen.geometry())
        else:
            self.setGeometry(0, 0, 1920, 1080)

    def prepare_blurred_snapshot(self):
        """Captura instantâneo do desktop antes de exibir o scrim (zero tela cinza uniforme)."""
        self._blurred_bg = None
        self.acrylic_enabled = False
        try:
            screen = QApplication.primaryScreen()
            if screen:
                raw = screen.grabWindow(0)
                if not raw.isNull():
                    blurred = _blur_desktop_pixmap(raw, radius=11.0)
                    if blurred and not blurred.isNull():
                        self._blurred_bg = blurred
                        self.acrylic_enabled = True
        except Exception as e:
            log_exception("BackdropDimWidget.prepare_blurred_snapshot", e)
            self._blurred_bg = None
            self.acrylic_enabled = False

    def clear_snapshot(self):
        self._blurred_bg = None
        self.acrylic_enabled = False

    def showEvent(self, event):
        try:
            super().showEvent(event)
            self._update_geometry()
            hwnd = int(self.winId())
            if hwnd:
                apply_dwm_acrylic(hwnd)
        except Exception as e:
            log_exception("BackdropDimWidget.showEvent", e)

    def paintEvent(self, event):
        p = QPainter(self)
        try:
            p.save()
            rect = self.rect()
            if self._blurred_bg is not None and not self._blurred_bg.isNull():
                p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
                p.drawPixmap(rect, self._blurred_bg)
                # Vinheta escura translúcida preservando contraste e formas desfocadas
                p.fillRect(rect, QColor(8, 8, 8, 162))
            else:
                # Fallback escuro limpo (nunca cinza lavado)
                p.fillRect(rect, QColor(7, 7, 7, 195))
            p.restore()
        except Exception as e:
            log_exception("BackdropDimWidget.paintEvent", e)
        finally:
            p.end()

    def mousePressEvent(self, event: QMouseEvent):
        try:
            self.clicked_outside.emit()
        except Exception as e:
            log_exception("BackdropDimWidget.mousePressEvent", e)


class ControlCenterOverlay(QWidget):
    """
    Painel do Centro de Controle Monolith:
    - Visão 0: Painel Principal adaptativo (conectividade real, sliders, saída de áudio e mídia contextual)
    - Visão 1: Flyout Wi-Fi (somente quando há adaptador Wi-Fi físico)
    - Visão 2: Flyout Saída de Áudio (endpoints CoreAudio reais)
    """

    dismiss_requested = pyqtSignal()

    PANEL_W = 460
    PANEL_H = 576
    CORNER_R = 20.0
    _PAD = 24.0
    _MEDIA_PLAYING_STATUS = "Em reprodução ativa"

    def __init__(self, radio_adapter=None, wifi_manager=None, audio_adapter=None, system_controls=None, parent=None):
        super().__init__(parent)
        self.radio_adapter = radio_adapter
        self.wifi_manager = wifi_manager
        self.audio_adapter = audio_adapter
        self.system_controls = system_controls

        self.setWindowTitle("Monolith — Centro de Controle")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)

        # 0 = Principal, 1 = Wi-Fi Flyout, 2 = Audio Flyout
        self.current_view = 0
        self._dragging_slider = None  # "vol" | "bri" | None
        self._hovered_id = None
        self._pressed_id = None

        # Transição animada entre visões/flyouts
        self._flyout_progress = 1.0
        self._flyout_dir = 1
        self._view_anim = QVariantAnimation(self)
        self._view_anim.setDuration(190)
        self._view_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._view_anim.valueChanged.connect(self._on_view_anim_step)

        # Rádios (Wi-Fi, Bluetooth e Hotspot — iniciados honestamente como inexistentes até descoberta real)
        self.wifi_available = False
        self.bt_available = False
        self.wifi_state = "Unavailable"
        self.bt_state = "Unavailable"
        self.wifi_pending = False
        self.bt_pending = False
        self.radio_busy = False
        self.radio_comm_error = ""
        self.access_status = "Allowed"

        self.hotspot_supported = False
        self.hotspot_active = False
        self.hotspot_state = "Unavailable"

        # Wi-Fi
        self.wifi_networks = []
        self.connected_network = None
        self.selected_ssid = None
        self.wifi_scanning = False
        self.connecting_ssid = None
        self.connection_status_msg = ""
        self.connection_has_error = False
        self.location_permission_denied = False

        # Áudio
        self.audio_devices = []
        self.default_audio_name = "Sem saída de áudio"
        self.default_audio_id = ""
        self.volume_val = 100
        self.is_muted = False

        # Telemetria / Controles de Sistema (dados reais)
        self.has_battery = False
        self.battery_percent = None
        self.is_charging = None
        self.battery_saver_supported = False
        self.battery_saver_active = False
        self.night_light_supported = False
        self.night_light_active = False
        self.brightness_supported = False
        self.brightness_val = None

        # Mídia real
        self.media_info = MediaController.get_active_media()

        # Timer leve ativo apenas enquanto o painel está aberto
        self._live_timer = QTimer(self)
        self._live_timer.timeout.connect(self._refresh_live_context)

        # Campo de senha inline embutido
        self.password_input = QLineEdit(self)
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.returnPressed.connect(self._submit_selected_wifi_password)
        self._update_password_style(has_error=False)
        self.password_input.hide()

        self._connect_signals()
        self._update_geometry()

    def _open_uri(self, uri: str):
        QDesktopServices.openUrl(QUrl(uri))

    def apply_theme(self):
        """Reaplica o tema ativo em tempo real ao overlay e aos controles filhos."""
        self._update_password_style(has_error=self.connection_has_error)
        self.update()

    def _update_password_style(self, has_error: bool = False):
        border_col = "#F43F5E" if has_error else Theme.HEX_ACCENT
        self.password_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {Theme.HEX_BG_INPUT};
                color: {Theme.HEX_TEXT_PRIMARY};
                border: 1.2px solid {border_col};
                border-radius: 8px;
                padding: 4px 10px;
                font-family: '{Theme.FONT_FAMILY_FALLBACK}';
                font-size: 13px;
            }}
        """)

    def _connect_signals(self):
        if self.radio_adapter:
            self.radio_adapter.radio_state_changed.connect(self.on_radio_state_changed)
            self.radio_adapter.radios_updated.connect(self.on_radios_updated)
            self.radio_adapter.access_status_received.connect(self.on_access_status)
            self.radio_adapter.tethering_updated.connect(self.on_tethering_updated)
            if hasattr(self.radio_adapter, "radio_error"):
                self.radio_adapter.radio_error.connect(self.on_radio_error)
            self._sync_radios_from_adapter()

        if self.wifi_manager:
            self.wifi_manager.scan_finished.connect(self.on_wifi_scan_finished)
            self.wifi_manager.current_connection_updated.connect(self.on_wifi_conn_updated)
            self.wifi_manager.connection_status_changed.connect(self.on_wifi_status_changed)
            self.wifi_manager.wifi_available_changed.connect(self.on_wifi_available_changed)
            self.wifi_manager.wifi_error.connect(self.on_wifi_error)
            self.wifi_available = self.wifi_available or self.wifi_manager.is_wifi_available()

        if self.audio_adapter:
            self.audio_adapter.devices_updated.connect(self.on_audio_devices_updated)
            self.audio_adapter.default_device_changed.connect(self.on_default_audio_changed)
            self.audio_adapter.volume_changed.connect(self.on_volume_changed)
            self.audio_adapter.mute_changed.connect(self.on_mute_changed)
            self.audio_adapter.open_settings_requested.connect(self._open_uri)
            self.audio_devices = self.audio_adapter.get_cached_devices()
            def_dev = self.audio_adapter.get_cached_default()
            if def_dev and def_dev.get("name"):
                self.default_audio_id = def_dev.get("id", "")
                self.default_audio_name = def_dev.get("name", "Sem saída de áudio")
            self.volume_val = self.audio_adapter.get_cached_volume()
            self.is_muted = self.audio_adapter.is_muted()

        if self.system_controls:
            self.system_controls.state_updated.connect(self.on_system_controls_updated)
            self.system_controls.open_settings_requested.connect(self._open_uri)
            self.on_system_controls_updated(self.system_controls.get_state())

    def _sync_radios_from_adapter(self):
        if not self.radio_adapter:
            return
        cached = self.radio_adapter.get_cached_radios()
        self.wifi_available = "WiFi" in cached
        self.bt_available = "Bluetooth" in cached
        self.wifi_state = cached.get("WiFi", "Unavailable")
        self.bt_state = cached.get("Bluetooth", "Unavailable")
        sup, act, st = self.radio_adapter.get_tethering_status()
        self.hotspot_supported = sup
        self.hotspot_active = act
        self.hotspot_state = st

    # Callbacks de Sistema
    def on_system_controls_updated(self, state: dict):
        self.has_battery = bool(state.get("has_battery", False))
        self.battery_percent = state.get("battery_percent")
        self.is_charging = state.get("is_charging")
        self.battery_saver_supported = bool(state.get("battery_saver_supported", False))
        self.battery_saver_active = bool(state.get("battery_saver_active", False))
        self.night_light_supported = bool(state.get("night_light_supported", False))
        self.night_light_active = bool(state.get("night_light_active", False))
        self.brightness_supported = bool(state.get("brightness_supported", False))
        self.brightness_val = state.get("brightness_val")
        self._update_geometry()
        self.update()

    # Callbacks de Rádio
    def on_radio_state_changed(self, kind: str, state: str):
        self.radio_comm_error = ""
        if kind == "WiFi":
            self.wifi_available = (state != "Unavailable")
            self.wifi_state = state
            self.wifi_pending = False
            if not self.wifi_available:
                self.wifi_networks = []
                self.connected_network = None
                self.selected_ssid = None
                if self.current_view == 1:
                    self._switch_view(0)
        elif kind == "Bluetooth":
            self.bt_available = (state != "Unavailable")
            self.bt_state = state
            self.bt_pending = False
        self.radio_busy = False
        self._update_geometry()
        self.update()

    def on_radios_updated(self, radios: list):
        self.radio_comm_error = ""
        seen = {r.get("kind"): r.get("state") for r in radios if isinstance(r, dict)}
        self.wifi_available = "WiFi" in seen
        self.bt_available = "Bluetooth" in seen
        self.wifi_state = seen.get("WiFi", "Unavailable")
        self.bt_state = seen.get("Bluetooth", "Unavailable")
        if not self.wifi_available:
            self.wifi_networks = []
            self.connected_network = None
            self.selected_ssid = None
            if self.current_view == 1:
                self._switch_view(0)
        self.wifi_pending = False
        self.bt_pending = False
        self.radio_busy = False
        self._update_geometry()
        self.update()

    def on_radio_error(self, err_msg: str):
        self.radio_comm_error = err_msg or "Falha temporária de comunicação"
        self.wifi_pending = False
        self.bt_pending = False
        self.radio_busy = False
        self.update()

    def on_access_status(self, status: str):
        self.access_status = status
        self.update()

    def on_tethering_updated(self, supported: bool, active: bool, state: str):
        self.hotspot_supported = supported and self.wifi_available
        self.hotspot_active = active if self.hotspot_supported else False
        self.hotspot_state = state if self.hotspot_supported else "Unavailable"
        self._update_geometry()
        self.update()

    def on_wifi_available_changed(self, avail: bool):
        self.wifi_available = bool(avail)
        if not avail:
            self.wifi_scanning = False
            self.wifi_networks = []
            self.connected_network = None
            self.selected_ssid = None
            if self.current_view == 1:
                self._switch_view(0)
        self._update_geometry()
        self.update()

    # Callbacks de Wi-Fi
    def on_wifi_scan_finished(self, nets: list):
        self.wifi_networks = nets if self.wifi_available else []
        self.wifi_scanning = False
        self.location_permission_denied = False
        self.update()

    def on_wifi_conn_updated(self, conn: dict):
        self.connected_network = conn if (conn and conn.get("ssid")) else None
        self.update()

    def on_wifi_status_changed(self, ssid: str, status: str):
        if status == "Connecting":
            self.connecting_ssid = ssid
            self.connection_status_msg = f"Conectando a {ssid}..."
            self.connection_has_error = False
        elif status == "Connected":
            self.connecting_ssid = None
            self.connection_status_msg = "Conectado com sucesso!"
            self.connection_has_error = False
            self.selected_ssid = None
            self.password_input.clear()
            self.password_input.hide()
            if self.wifi_manager and self.wifi_available:
                self.wifi_manager.start_scan()
        elif status == "Failed":
            self.connecting_ssid = None
            self.connection_status_msg = "Falha na autenticação: senha incorreta ou tempo esgotado."
            self.connection_has_error = True
            self._update_password_style(has_error=True)
        self.update()

    def on_wifi_error(self, err_msg: str):
        msg_l = err_msg.lower()
        if "permissão de localização" in msg_l or "denied" in msg_l:
            self.location_permission_denied = True
        self.wifi_scanning = False
        self.connection_status_msg = err_msg
        self.update()

    # Callbacks de Áudio
    def on_audio_devices_updated(self, devs: list):
        self.audio_devices = devs
        if not devs:
            self.default_audio_name = "Sem saída de áudio"
            self.default_audio_id = ""
        self.update()

    def on_default_audio_changed(self, dev_id: str, dev_name: str):
        self.default_audio_id = dev_id
        self.default_audio_name = dev_name if dev_name else "Sem saída de áudio"
        self.update()

    def on_volume_changed(self, val: int):
        self.volume_val = val
        self.update()

    def on_mute_changed(self, m: bool):
        self.is_muted = m
        self.update()

    # ==========================================================================
    # MOTOR DE CAPACIDADES REAIS & COMPOSIÇÃO ADAPTATIVA (SEM ÁREAS MORTAS)
    # ==========================================================================

    def _build_real_toggles(self) -> list[dict]:
        """Monta exclusivamente os controles reais disponíveis neste computador."""
        items = []
        perm_denied = self.access_status in ("DeniedByUser", "DeniedBySystem")

        if self.wifi_available:
            wifi_on = (self.wifi_state == "On")
            if perm_denied:
                sub = "Permissão negada"
            elif self.wifi_pending:
                sub = "Alternando..."
            elif wifi_on and self.connected_network and self.connected_network.get("ssid"):
                sub = self.connected_network.get("ssid")
            else:
                sub = "Ativado" if wifi_on else "Desativado"
            items.append({
                "id": "WiFi",
                "name": "Wi-Fi",
                "sub": sub,
                "active": wifi_on and not perm_denied,
                "pending": self.wifi_pending,
                "glyph": "wifi",
                "chevron": True,
            })

        if self.bt_available:
            bt_on = (self.bt_state == "On")
            if perm_denied:
                sub = "Permissão negada"
            elif self.bt_pending:
                sub = "Alternando..."
            else:
                sub = "Ativado" if bt_on else "Desativado"
            items.append({
                "id": "Bluetooth",
                "name": "Bluetooth",
                "sub": sub,
                "active": bt_on and not perm_denied,
                "pending": self.bt_pending,
                "glyph": "bluetooth",
                "chevron": False,
            })

        if self.wifi_available or self.bt_available:
            items.append({
                "id": "Airplane",
                "name": "Modo Avião",
                "sub": "Ajustes do sistema",
                "active": False,
                "pending": False,
                "glyph": "airplane",
                "chevron": False,
            })

        if self.hotspot_supported and self.wifi_available:
            items.append({
                "id": "Hotspot",
                "name": "Hotspot",
                "sub": "Ativado" if self.hotspot_active else "Desativado",
                "active": self.hotspot_active,
                "pending": False,
                "glyph": "hotspot",
                "chevron": False,
            })

        if self.night_light_supported:
            items.append({
                "id": "NightLight",
                "name": "Luz Noturna",
                "sub": "Ativada" if self.night_light_active else "Desativada",
                "active": self.night_light_active,
                "pending": False,
                "glyph": "nightlight",
                "chevron": False,
            })

        if self.has_battery and self.battery_saver_supported:
            items.append({
                "id": "BatterySaver",
                "name": "Economia",
                "sub": "Ativada" if self.battery_saver_active else "Desativada",
                "active": self.battery_saver_active,
                "pending": False,
                "glyph": "battery_saver",
                "chevron": False,
            })

        return items

    def _compute_main_layout_spec(self) -> dict:
        """Calcula posicionamento vertical lógico sem cortes nem áreas vazias."""
        w = float(self.width() or self.PANEL_W)
        pad = self._PAD
        cw = w - 2.0 * pad
        gap = 10.0

        y = 84.0
        spec = {
            "toggles": [],
            "capability_banner_rect": None,
            "capability_banner_text": "",
            "vol_rect": None,
            "bri_rect": None,
            "bri_note_rect": None,
            "audio_pill_rect": None,
            "media_rect": None,
            "total_h": 340,
        }

        # Banner honesto quando não há adaptadores físicos Wi-Fi / Bluetooth
        no_radios = (not self.wifi_available and not self.bt_available)
        if no_radios:
            banner_msg = (
                self.radio_comm_error
                if self.radio_comm_error
                else "Wi-Fi e Bluetooth indisponíveis (sem adaptador físico neste computador)"
            )
            spec["capability_banner_rect"] = QRectF(pad, y, cw, 34.0)
            spec["capability_banner_text"] = banner_msg
            y += 44.0

        toggles = self._build_real_toggles()
        if toggles:
            row_h = 56.0
            n = len(toggles)
            col_w = (cw - gap) / 2.0
            for idx, item in enumerate(toggles):
                is_last_odd = (n % 2 == 1 and idx == n - 1)
                r_idx = idx // 2
                c_idx = idx % 2
                tx = pad + (0.0 if is_last_odd else c_idx * (col_w + gap))
                tw = cw if is_last_odd else col_w
                ty = y + r_idx * (row_h + gap)
                item["rect"] = QRectF(tx, ty, tw, row_h)
                spec["toggles"].append(item)
            rows = (n + 1) // 2
            y += rows * row_h + max(0, rows - 1) * gap + 14.0
        elif not no_radios and self.radio_comm_error:
            spec["capability_banner_rect"] = QRectF(pad, y, cw, 34.0)
            spec["capability_banner_text"] = self.radio_comm_error
            y += 44.0

        # Slider de Volume Master
        spec["vol_rect"] = QRectF(pad, y, cw, 50.0)
        y += 60.0

        # Controle de Brilho (somente completo quando monitor/WMI suporta DDC/CI ou WMI)
        if self.brightness_supported and self.brightness_val is not None:
            spec["bri_rect"] = QRectF(pad, y, cw, 50.0)
            y += 60.0
        else:
            spec["bri_note_rect"] = QRectF(pad, y, cw, 30.0)
            y += 40.0

        # Seletor de Saída de Áudio
        audio_h = 52.0
        spec["audio_pill_rect"] = QRectF(pad, y, cw, audio_h)
        y += audio_h + 12.0

        # Card de Mídia apenas quando há reprodução real ativa
        if bool(self.media_info.get("active", False)):
            spec["media_rect"] = QRectF(pad, y, cw, 82.0)
            y += 94.0

        spec["total_h"] = max(280, min(self.PANEL_H, int(round(y + 10.0))))
        return spec

    def target_geometry(self, view: int | None = None) -> tuple[int, int, int, int]:
        """Calcula a geometria lógica final do painel no monitor principal."""
        v = self.current_view if view is None else view
        screen = QApplication.primaryScreen()
        avail = screen.availableGeometry() if screen else QRectF(0, 0, 1920, 1032).toRect()
        w = self.PANEL_W
        if v == 0:
            desired_h = self._compute_main_layout_spec()["total_h"]
        else:
            desired_h = 500
        h = min(self.PANEL_H, desired_h, max(280, avail.height() - 24))
        x = max(avail.left() + 8, avail.right() - w - 20)
        y = max(avail.top() + 10, min(avail.top() + 18, avail.bottom() - h - 8))
        return int(x), int(y), int(w), int(h)

    def _update_geometry(self):
        """Usa estritamente coordenadas lógicas Qt (sem dupla multiplicação por DPI)."""
        x, y, w, h = self.target_geometry()
        if self.x() != x or self.y() != y or self.width() != w or self.height() != h:
            self.setGeometry(x, y, w, h)

    # Hitboxes mantidas compatíveis e sincronizadas 1:1 com a geometria pintada
    def _rect_header_back(self) -> QRectF:
        return QRectF(20.0, 18.0, 34.0, 34.0)

    def _rect_header_gear(self) -> QRectF:
        return QRectF(float(self.width()) - 96.0, 18.0, 34.0, 34.0)

    def _rect_header_refresh(self) -> QRectF:
        return QRectF(float(self.width()) - 96.0, 18.0, 34.0, 34.0)

    def _rect_header_close(self) -> QRectF:
        return QRectF(float(self.width()) - 54.0, 18.0, 34.0, 34.0)

    def _rect_toggle(self, idx: int) -> QRectF:
        toggles = self._compute_main_layout_spec()["toggles"]
        if 0 <= idx < len(toggles):
            return toggles[idx]["rect"]
        gap = 10.0
        col_w = (float(self.width()) - 2.0 * self._PAD - gap) / 2.0
        row_h = 56.0
        r_idx = idx // 2
        c_idx = idx % 2
        return QRectF(self._PAD + c_idx * (col_w + gap), 84.0 + r_idx * (row_h + gap), col_w, row_h)

    def _rect_vol_slider(self) -> QRectF:
        return self._compute_main_layout_spec()["vol_rect"]

    def _rect_bri_slider(self) -> QRectF:
        bri = self._compute_main_layout_spec()["bri_rect"]
        return bri if bri is not None else QRectF(0, 0, 0, 0)

    def _rect_audio_pill(self) -> QRectF:
        return self._compute_main_layout_spec()["audio_pill_rect"]

    def _rect_media_card(self) -> QRectF:
        mr = self._compute_main_layout_spec()["media_rect"]
        return mr if mr is not None else QRectF(0, 0, 0, 0)

    def _rect_media_controls(self) -> tuple[QRectF, QRectF, QRectF]:
        mr = self._rect_media_card()
        if mr.isEmpty():
            return (QRectF(), QRectF(), QRectF())
        cx = mr.right() - 112.0
        cy = mr.top() + (mr.height() - 36.0) / 2.0
        return (
            QRectF(cx, cy, 30.0, 36.0),
            QRectF(cx + 34.0, cy, 36.0, 36.0),
            QRectF(cx + 74.0, cy, 30.0, 36.0),
        )

    def _rect_footer_btn(self) -> QRectF:
        return QRectF(20.0, float(self.height()) - 40.0, float(self.width()) - 40.0, 30.0)

    def _rect_audio_vol_slider(self) -> QRectF:
        return QRectF(22.0, 74.0, float(self.width()) - 44.0, 50.0)

    def _get_audio_device_rects(self) -> list[tuple[dict, QRectF]]:
        w = float(self.width())
        max_bottom = float(self.height()) - 46.0
        list_y = 158.0
        items = []
        for dev in self.audio_devices:
            if list_y + 58.0 > max_bottom:
                break
            items.append((dev, QRectF(22.0, list_y, w - 44.0, 58.0)))
            list_y += 66.0
        return items

    def _get_wifi_card_rects(self) -> list[tuple[dict, QRectF]]:
        w = float(self.width())
        max_bottom = float(self.height()) - 46.0
        list_y = 110.0 if self.location_permission_denied else 86.0
        items = []
        for net in self.wifi_networks[:6]:
            is_sel = (self.selected_ssid == net["ssid"])
            card_h = 156.0 if (is_sel and net.get("is_secure")) else 56.0
            if list_y + card_h > max_bottom:
                break
            items.append((net, QRectF(22.0, list_y, w - 44.0, card_h)))
            list_y += card_h + 8.0
        return items

    # ==========================================================================
    # TRANSIÇÕES DE FLYOUT & CICLO DE VIDA
    # ==========================================================================

    def _switch_view(self, target_view: int):
        if target_view == self.current_view:
            return
        self._flyout_dir = 1 if target_view > self.current_view else -1
        self.current_view = target_view
        if target_view != 1:
            self.selected_ssid = None
            self.password_input.hide()
        self._update_geometry()

        if Theme.reduced_motion_enabled():
            self._flyout_progress = 1.0
            self.update()
            return

        self._view_anim.stop()
        self._view_anim.setStartValue(0.0)
        self._view_anim.setEndValue(1.0)
        self._view_anim.start()

    def _on_view_anim_step(self, val: float):
        self._flyout_progress = float(val)
        self.update()

    def showEvent(self, event):
        try:
            super().showEvent(event)
            self._update_geometry()
            hwnd = int(self.winId())
            if hwnd:
                apply_dwm_acrylic(hwnd)
            self.activateWindow()
            self.setFocus()
            self._refresh_live_context()
            self._live_timer.start(1500)
            if self.wifi_manager and self.wifi_available:
                self.wifi_manager.start_scan()
            if self.audio_adapter:
                self.audio_adapter.refresh()
            if self.radio_adapter:
                self.radio_adapter.refresh_radios()
                self.radio_adapter.refresh_tethering()
            if self.system_controls:
                self.system_controls.refresh()
        except Exception as e:
            log_exception("ControlCenterOverlay.showEvent", e)

    def hideEvent(self, event):
        try:
            self._live_timer.stop()
            self._dragging_slider = None
            self._hovered_id = None
            self._pressed_id = None
            self.password_input.hide()
            self.current_view = 0
            self._flyout_progress = 1.0
        except Exception as e:
            log_exception("ControlCenterOverlay.hideEvent", e)
        super().hideEvent(event)

    def _refresh_live_context(self):
        try:
            self.media_info = MediaController.get_active_media()
            if self.system_controls:
                self.system_controls.refresh()
            self._update_geometry()
            self.update()
        except Exception as e:
            log_exception("ControlCenterOverlay._refresh_live_context", e)

    def keyPressEvent(self, event: QKeyEvent):
        try:
            if event.key() == Qt.Key.Key_Escape:
                if self.current_view != 0:
                    self._switch_view(0)
                else:
                    self.dismiss_requested.emit()
            else:
                super().keyPressEvent(event)
        except Exception as e:
            log_exception("ControlCenterOverlay.keyPressEvent", e)

    def _submit_selected_wifi_password(self):
        try:
            if self.current_view == 1 and self.selected_ssid and self.wifi_manager and self.wifi_available:
                pwd = self.password_input.text().strip()
                self.wifi_manager.connect_network(self.selected_ssid, pwd)
        except Exception as e:
            log_exception("ControlCenterOverlay._submit_selected_wifi_password", e)

    def _hit_test_id(self, mx: float, my: float) -> str | None:
        if self._rect_header_close().contains(mx, my):
            return "close"
        if self.current_view == 0:
            if self._rect_header_gear().contains(mx, my):
                return "gear"
            for t in self._compute_main_layout_spec()["toggles"]:
                if t["rect"].contains(mx, my):
                    return f"toggle:{t['id']}"
            if self._rect_vol_slider().contains(mx, my):
                return "slider:vol"
            bri_r = self._rect_bri_slider()
            if not bri_r.isEmpty() and bri_r.contains(mx, my):
                return "slider:bri"
            if self._rect_audio_pill().contains(mx, my):
                return "audio_pill"
            prev_r, play_r, next_r = self._rect_media_controls()
            if not prev_r.isEmpty():
                if prev_r.contains(mx, my):
                    return "media:prev"
                if play_r.contains(mx, my):
                    return "media:play"
                if next_r.contains(mx, my):
                    return "media:next"
        elif self.current_view == 1:
            if self._rect_header_back().contains(mx, my):
                return "back"
            if self._rect_header_refresh().contains(mx, my):
                return "refresh"
            if self._rect_footer_btn().contains(mx, my):
                return "footer"
            for idx, (_, r) in enumerate(self._get_wifi_card_rects()):
                if r.contains(mx, my):
                    return f"wifi:{idx}"
        elif self.current_view == 2:
            if self._rect_header_back().contains(mx, my):
                return "back"
            if self._rect_audio_vol_slider().contains(mx, my):
                return "slider:vol"
            if self._rect_footer_btn().contains(mx, my):
                return "footer"
            for idx, (_, r) in enumerate(self._get_audio_device_rects()):
                if r.contains(mx, my):
                    return f"audiodev:{idx}"
        return None

    def mousePressEvent(self, event: QMouseEvent):
        try:
            if event.button() != Qt.MouseButton.LeftButton:
                return
            mx = event.position().x()
            my = event.position().y()
            self._pressed_id = self._hit_test_id(mx, my)
            self.update()

            if self._rect_header_close().contains(mx, my):
                self.dismiss_requested.emit()
                event.accept()
                return

            if self.current_view == 1:
                self._handle_wifi_flyout_clicks(mx, my)
                event.accept()
                return

            if self.current_view == 2:
                self._handle_audio_flyout_clicks(mx, my)
                event.accept()
                return

            if self._rect_header_gear().contains(mx, my):
                self._open_uri("ms-settings:")
                event.accept()
                return

            if self._rect_audio_pill().contains(mx, my):
                if self.audio_adapter:
                    self.audio_adapter.refresh()
                self._switch_view(2)
                event.accept()
                return

            if self._handle_media_card_clicks(mx, my):
                event.accept()
                return

            if self._handle_main_toggle_clicks(mx, my):
                event.accept()
                return

            self._handle_slider_press(mx, my)
            event.accept()
        except Exception as e:
            log_exception("ControlCenterOverlay.mousePressEvent", e)

    def mouseMoveEvent(self, event: QMouseEvent):
        try:
            mx = event.position().x()
            my = event.position().y()
            if self._dragging_slider == "vol":
                vr = self._rect_audio_vol_slider() if self.current_view == 2 else self._rect_vol_slider()
                self._apply_volume_from_x(mx, vr)
                event.accept()
                return
            if self._dragging_slider == "bri" and self.brightness_supported:
                self._apply_brightness_from_x(mx, self._rect_bri_slider())
                event.accept()
                return
            hit = self._hit_test_id(mx, my)
            if hit != self._hovered_id:
                self._hovered_id = hit
                self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor if hit else Qt.CursorShape.ArrowCursor))
                self.update()
        except Exception as e:
            log_exception("ControlCenterOverlay.mouseMoveEvent", e)

    def mouseReleaseEvent(self, event: QMouseEvent):
        try:
            self._dragging_slider = None
            if self._pressed_id is not None:
                self._pressed_id = None
                self.update()
        except Exception as e:
            log_exception("ControlCenterOverlay.mouseReleaseEvent", e)
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event):
        try:
            if self._hovered_id is not None:
                self._hovered_id = None
                self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
                self.update()
        except Exception:
            pass
        super().leaveEvent(event)

    def _handle_media_card_clicks(self, mx: float, my: float) -> bool:
        prev_r, play_r, next_r = self._rect_media_controls()
        if prev_r.isEmpty():
            return False
        if prev_r.contains(mx, my):
            MediaController.prev_track()
            QTimer.singleShot(150, self._refresh_live_context)
            return True
        if play_r.contains(mx, my):
            MediaController.play_pause()
            QTimer.singleShot(150, self._refresh_live_context)
            return True
        if next_r.contains(mx, my):
            MediaController.next_track()
            QTimer.singleShot(150, self._refresh_live_context)
            return True
        return False

    def _handle_main_toggle_clicks(self, mx: float, my: float) -> bool:
        for t in self._compute_main_layout_spec()["toggles"]:
            tr = t["rect"]
            t_id = t["id"]
            if tr.contains(mx, my):
                if t_id == "WiFi" and self.wifi_available and mx >= (tr.right() - 34.0):
                    if self.wifi_manager:
                        self.wifi_scanning = True
                        self.wifi_manager.start_scan()
                    self._switch_view(1)
                    return True
                self._dispatch_toggle(t_id)
                return True
        return False

    def _dispatch_toggle(self, t_id: str):
        if self.access_status in ("DeniedByUser", "DeniedBySystem") and t_id in ("WiFi", "Bluetooth"):
            self._open_uri("ms-settings:privacy-radios")
            return

        if self.radio_busy and t_id in ("WiFi", "Bluetooth"):
            return

        if t_id == "WiFi":
            if not self.wifi_available:
                return
            self.wifi_pending = True
            self.radio_busy = True
            self.update()
            if self.radio_adapter:
                self.radio_adapter.toggle_radio("WiFi")

        elif t_id == "Bluetooth":
            if not self.bt_available:
                return
            self.bt_pending = True
            self.radio_busy = True
            self.update()
            if self.radio_adapter:
                self.radio_adapter.toggle_radio("Bluetooth")

        elif t_id == "Airplane":
            self._open_uri("ms-settings:network-airplanemode")
        elif t_id == "NightLight":
            if self.night_light_supported and self.system_controls:
                self.system_controls.open_night_light_settings()
        elif t_id == "BatterySaver":
            if self.has_battery and self.battery_saver_supported and self.system_controls:
                self.system_controls.open_battery_saver_settings()
        elif t_id == "Hotspot":
            if self.hotspot_supported and self.wifi_available and self.radio_adapter:
                self.radio_adapter.toggle_tethering()

    def _apply_volume_from_x(self, mx: float, vol_r: QRectF):
        ratio = max(0.0, min(1.0, (mx - vol_r.left()) / max(1.0, vol_r.width())))
        new_vol = int(round(ratio * 100))
        self.volume_val = new_vol
        if self.audio_adapter:
            self.audio_adapter.set_volume(new_vol)
        self.update()

    def _apply_brightness_from_x(self, mx: float, bri_r: QRectF):
        if not self.brightness_supported:
            return
        ratio = max(0.0, min(1.0, (mx - bri_r.left()) / max(1.0, bri_r.width())))
        new_bri = int(round(ratio * 100))
        self.brightness_val = new_bri
        if self.system_controls:
            self.system_controls.set_brightness(new_bri)
        self.update()

    def _handle_slider_press(self, mx: float, my: float):
        vol_r = self._rect_vol_slider()
        if vol_r.contains(mx, my):
            if mx <= vol_r.left() + 42.0:
                if self.audio_adapter:
                    self.audio_adapter.toggle_mute()
                else:
                    self.is_muted = not self.is_muted
                    self.update()
                return
            self._dragging_slider = "vol"
            self._apply_volume_from_x(mx, vol_r)
            return

        bri_r = self._rect_bri_slider()
        if not bri_r.isEmpty() and bri_r.contains(mx, my) and self.brightness_supported:
            self._dragging_slider = "bri"
            self._apply_brightness_from_x(mx, bri_r)

    def _handle_wifi_flyout_clicks(self, mx: float, my: float):
        if self._rect_header_back().contains(mx, my):
            self._switch_view(0)
            return

        if self._rect_header_refresh().contains(mx, my):
            if self.wifi_manager and self.wifi_available:
                self.wifi_scanning = True
                self.wifi_manager.start_scan()
            self.update()
            return

        w = float(self.width())
        if self.location_permission_denied and QRectF(22.0, 68.0, w - 44.0, 34.0).contains(mx, my):
            self._open_uri("ms-settings:privacy-location")
            return

        if self._rect_footer_btn().contains(mx, my):
            self._open_uri("ms-settings:network-wifi")
            return

        for net, card_r in self._get_wifi_card_rects():
            if not card_r.contains(mx, my):
                continue
            is_sel = (self.selected_ssid == net["ssid"])
            if is_sel and net.get("is_secure"):
                btn_conn = QRectF(card_r.right() - 100.0, card_r.top() + 112.0, 88.0, 30.0)
                btn_canc = QRectF(card_r.right() - 198.0, card_r.top() + 112.0, 88.0, 30.0)
                if btn_conn.contains(mx, my):
                    self._submit_selected_wifi_password()
                    return
                if btn_canc.contains(mx, my):
                    self.selected_ssid = None
                    self.password_input.clear()
                    self.password_input.hide()
                    self.update()
                    return
            else:
                if net.get("is_connected"):
                    return
                if net.get("is_secure"):
                    self.selected_ssid = net["ssid"]
                    self.password_input.clear()
                    self.connection_has_error = False
                    self._update_password_style(has_error=False)
                    self.password_input.setGeometry(
                        int(card_r.left() + 14.0), int(card_r.top() + 66.0),
                        int(card_r.width() - 28.0), 34
                    )
                    self.password_input.show()
                    self.password_input.setFocus()
                else:
                    if self.wifi_manager and self.wifi_available:
                        self.wifi_manager.connect_network(net["ssid"])
                self.update()
                return

    def _handle_audio_flyout_clicks(self, mx: float, my: float):
        if self._rect_header_back().contains(mx, my):
            self._switch_view(0)
            return

        vol_r = self._rect_audio_vol_slider()
        if vol_r.contains(mx, my):
            if mx <= vol_r.left() + 42.0:
                if self.audio_adapter:
                    self.audio_adapter.toggle_mute()
                else:
                    self.is_muted = not self.is_muted
                    self.update()
                return
            self._dragging_slider = "vol"
            self._apply_volume_from_x(mx, vol_r)
            return

        for dev, card_r in self._get_audio_device_rects():
            if card_r.contains(mx, my):
                if self.audio_adapter:
                    self.audio_adapter.set_default_device(dev["id"])
                return

        if self._rect_footer_btn().contains(mx, my):
            self._open_uri("ms-settings:sound")

    # ==========================================================================
    # AUXILIARES VETORIAIS SEGUROS (ZERO PIXELAÇÃO / ZERO VAZAMENTO QPainter)
    # ==========================================================================

    @staticmethod
    def _draw_round_icon_btn(
        p: QPainter, rect: QRectF, icon_name_or_glyph: str,
        icon_color: QColor, border_color: QColor = None, fill_color: QColor = None,
        hovered: bool = False, pressed: bool = False
    ):
        p.save()
        bg = fill_color or (
            QColor(255, 255, 255, 28) if pressed else (
                QColor(255, 255, 255, 20) if hovered else QColor(255, 255, 255, 11)
            )
        )
        brd = border_color or QColor(255, 255, 255, 42 if hovered else 22)
        p.setPen(QPen(brd, 1.0))
        p.setBrush(bg)
        p.drawRoundedRect(rect, rect.height() / 2.0, rect.height() / 2.0)

        glyph_map = {
            chr(0xE711): "close",
            chr(0xE713): "gear",
            chr(0xE76B): "back",
            chr(0xE72C): "refresh",
        }
        vname = glyph_map.get(icon_name_or_glyph, icon_name_or_glyph)
        if len(vname) > 1 or vname.isascii():
            IconFactory.paint_glyph(p, vname, rect.adjusted(7.0, 7.0, -7.0, -7.0), icon_color, stroke_w=1.65)
        else:
            p.setFont(QFont("Segoe Fluent Icons", 10))
            p.setPen(icon_color)
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, icon_name_or_glyph)
        p.restore()

    @staticmethod
    def _draw_clipped_slider_fill(p: QPainter, rect: QRectF, ratio: float, radius: float, fill_color: QColor):
        if ratio <= 0.0:
            return
        p.save()
        clip_path = QPainterPath()
        clip_path.addRoundedRect(rect, radius, radius)
        p.setClipPath(clip_path)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(fill_color)
        fill_w = rect.width() * max(0.0, min(1.0, ratio))
        p.drawRect(QRectF(rect.left(), rect.top(), fill_w, rect.height()))
        p.restore()

    # ==========================================================================
    # PINTURA VIDRO ESCURO OBSIDIANA (SEM TRUNCAMENTO / ANIMADA)
    # ==========================================================================

    def paintEvent(self, event):
        p = QPainter(self)
        try:
            p.save()
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

            w = float(self.width())
            h = float(self.height())
            r = self.CORNER_R
            rect = QRectF(0.0, 0.0, w, h)
            acc_col = QColor(Theme.COLOR_ACCENT)

            # Vidro escuro obsidiana translúcido (profundidade sobre fundo real desfocado)
            bg = QLinearGradient(0, 0, 0, h)
            bg.setColorAt(0.0, QColor(19, 19, 19, 224))
            bg.setColorAt(0.45, QColor(13, 13, 13, 232))
            bg.setColorAt(1.0, QColor(8, 8, 8, 240))
            p.setBrush(bg)

            stroke = QLinearGradient(0, 0, 0, h)
            stroke.setColorAt(0.0, QColor(255, 255, 255, 42))
            stroke.setColorAt(0.35, QColor(255, 255, 255, 16))
            stroke.setColorAt(0.85, QColor(acc_col.red(), acc_col.green(), acc_col.blue(), 68))
            stroke.setColorAt(1.0, QColor(acc_col.red(), acc_col.green(), acc_col.blue(), 118))
            p.setPen(QPen(QBrush(stroke), 1.0))
            p.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), r, r)

            # Realça conteúdo durante transição animada de flyout
            if self._flyout_progress < 1.0:
                dx = (1.0 - self._flyout_progress) * 26.0 * float(self._flyout_dir)
                p.setOpacity(max(0.15, self._flyout_progress))
                p.translate(dx, 0.0)

            if self.current_view == 1:
                self._paint_wifi_flyout(p, w, h, acc_col)
            elif self.current_view == 2:
                self._paint_audio_flyout(p, w, h, acc_col)
            else:
                self._paint_main_view(p, w, acc_col)

            p.restore()
        except Exception as e:
            log_exception("ControlCenterOverlay.paintEvent", e)
        finally:
            p.end()

    def _paint_main_view(self, p: QPainter, w: float, acc_col: QColor):
        p.save()
        spec = self._compute_main_layout_spec()
        pad = self._PAD

        # Cabeçalho limpo sem colisão de textos
        has_radios = self.wifi_available or self.bt_available
        sub_header = "Conectividade, Áudio & Sistema" if has_radios else "Áudio, Monitor & Sistema"
        header_right_reserve = 108.0

        if self.has_battery and self.battery_percent is not None:
            bat_txt = f"{self.battery_percent}% AC" if self.is_charging else f"{self.battery_percent}%"
            bat_col = QColor("#F59E0B") if (not self.is_charging and self.battery_percent <= 20) else QColor("#22C55E")
        else:
            bat_txt = "AC"
            bat_col = QColor(Theme.HEX_TEXT_SECONDARY)

        f_bat = Theme.get_font(8.2, QFont.Weight.Bold)
        fm_bat = QFontMetricsF(f_bat)
        bat_w = max(40.0, fm_bat.horizontalAdvance(bat_txt) + 20.0)
        bat_r = QRectF(w - 106.0 - bat_w, 22.0, bat_w, 26.0)
        header_right_reserve = w - bat_r.left() + 10.0

        p.setFont(Theme.get_font(13.0, QFont.Weight.Bold))
        p.setPen(QColor(Theme.HEX_TEXT_PRIMARY))
        p.drawText(QRectF(pad, 16.0, w - pad - header_right_reserve, 24.0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, "Centro de Controle")

        p.setFont(Theme.get_font(8.8, QFont.Weight.Normal))
        p.setPen(QColor(Theme.HEX_TEXT_SECONDARY))
        p.drawText(QRectF(pad, 41.0, w - pad - header_right_reserve, 18.0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, sub_header)

        p.save()
        p.setPen(QPen(QColor(255, 255, 255, 20), 1.0))
        p.setBrush(QColor(255, 255, 255, 10))
        p.drawRoundedRect(bat_r, 13.0, 13.0)
        p.setFont(f_bat)
        p.setPen(bat_col)
        p.drawText(bat_r, Qt.AlignmentFlag.AlignCenter, bat_txt)
        p.restore()

        self._draw_round_icon_btn(
            p, self._rect_header_gear(), "gear", QColor(Theme.HEX_TEXT_SECONDARY),
            hovered=(self._hovered_id == "gear"), pressed=(self._pressed_id == "gear")
        )
        self._draw_round_icon_btn(
            p, self._rect_header_close(), "close", QColor(Theme.HEX_TEXT_SECONDARY),
            hovered=(self._hovered_id == "close"), pressed=(self._pressed_id == "close")
        )

        p.setPen(QPen(QColor(255, 255, 255, 16), 1.0))
        p.drawLine(QPointF(pad, 70.0), QPointF(w - pad, 70.0))

        # Banner discreto de hardware indisponível (quando não há Wi-Fi/Bluetooth físicos)
        if spec["capability_banner_rect"] is not None:
            br = spec["capability_banner_rect"]
            p.save()
            p.setPen(QPen(QColor(255, 255, 255, 14), 1.0))
            p.setBrush(QColor(255, 255, 255, 6))
            p.drawRoundedRect(br, 10.0, 10.0)
            p.setFont(Theme.get_font(8.4, QFont.Weight.Medium))
            p.setPen(QColor(Theme.HEX_TEXT_SECONDARY))
            p.drawText(br.adjusted(12.0, 0.0, -12.0, 0.0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, spec["capability_banner_text"])
            p.restore()

        # Toggles reais disponíveis
        if spec["toggles"]:
            self._paint_quick_toggles(p, spec["toggles"], acc_col)

        # Sliders proporcionais (Volume + Brilho real quando suportado)
        self._paint_sliders(p, spec, acc_col)

        # Seletor de Saída de Áudio
        self._paint_audio_pill(p, spec["audio_pill_rect"], acc_col)

        # Card de mídia somente com sessão ativa real
        if spec["media_rect"] is not None:
            self._paint_media_card(p, spec["media_rect"], acc_col)

        p.restore()

    def _paint_quick_toggles(self, p: QPainter, toggles: list[dict], acc_col: QColor):
        p.save()
        soft_fill = QColor(Theme.COLOR_ACCENT_SOFT_FILL)
        acc_light = QColor(Theme.COLOR_ACCENT_LIGHT)
        on_acc = QColor(Theme.COLOR_TEXT_ON_ACCENT)

        for t in toggles:
            tr = t["rect"]
            is_act = t["active"]
            is_hov = (self._hovered_id == f"toggle:{t['id']}")
            is_prs = (self._pressed_id == f"toggle:{t['id']}")

            p.save()
            if is_act:
                fill = soft_fill.lighter(115) if is_hov else soft_fill
                p.setPen(QPen(acc_light, 1.1))
                p.setBrush(fill)
            else:
                alpha_bg = 22 if is_prs else (15 if is_hov else 9)
                alpha_brd = 32 if is_hov else 16
                p.setPen(QPen(QColor(255, 255, 255, alpha_brd), 1.0))
                p.setBrush(QColor(255, 255, 255, alpha_bg))
            p.drawRoundedRect(tr, 14.0, 14.0)

            circ_r = QRectF(tr.x() + 10.0, tr.y() + (tr.height() - 34.0) / 2.0, 34.0, 34.0)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(acc_col if is_act else QColor(255, 255, 255, 18))
            p.drawEllipse(circ_r)

            IconFactory.paint_glyph(
                p, t["glyph"], circ_r.adjusted(7.5, 7.5, -7.5, -7.5),
                on_acc if is_act else QColor(Theme.HEX_TEXT_PRIMARY), stroke_w=1.6
            )

            right_pad = 28.0 if t["chevron"] else 12.0
            txt_x = tr.x() + 52.0
            txt_w = max(60.0, tr.width() - 52.0 - right_pad)

            p.setFont(Theme.get_font(9.2, QFont.Weight.DemiBold))
            p.setPen(QColor(Theme.HEX_TEXT_PRIMARY))
            p.drawText(QRectF(txt_x, tr.y() + 8.0, txt_w, 20.0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, t["name"])

            p.setFont(Theme.get_font(8.0, QFont.Weight.Normal))
            p.setPen(acc_light if is_act else QColor(Theme.HEX_TEXT_SECONDARY))
            p.drawText(QRectF(txt_x, tr.y() + 28.0, txt_w, 18.0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, t["sub"])

            if t["chevron"]:
                chev_r = QRectF(tr.right() - 24.0, tr.y(), 16.0, tr.height())
                IconFactory.paint_glyph(p, "chevron", chev_r.adjusted(2, 18, -2, -18), QColor(Theme.HEX_TEXT_SECONDARY), stroke_w=1.6)
            p.restore()
        p.restore()

    def _paint_sliders(self, p: QPainter, spec: dict, acc_col: QColor):
        p.save()
        acc_light = QColor(Theme.COLOR_ACCENT_LIGHT)
        soft_fill = QColor(Theme.COLOR_ACCENT_SOFT_FILL)

        # 1. Volume Master
        vol_r = spec["vol_rect"]
        vol_hov = (self._hovered_id == "slider:vol" or self._dragging_slider == "vol")
        p.setPen(QPen(QColor(255, 255, 255, 28 if vol_hov else 16), 1.0))
        p.setBrush(QColor(255, 255, 255, 12 if vol_hov else 8))
        p.drawRoundedRect(vol_r, 14.0, 14.0)

        ratio_v = 0.0 if self.is_muted else (float(self.volume_val) / 100.0)
        self._draw_clipped_slider_fill(p, vol_r, ratio_v, 14.0, soft_fill)

        vol_icon_r = QRectF(vol_r.left() + 14.0, vol_r.top() + 13.0, 24.0, 24.0)
        IconFactory.paint_glyph(
            p, "mute" if self.is_muted else "volume", vol_icon_r,
            QColor("#F43F5E") if self.is_muted else QColor(Theme.HEX_TEXT_PRIMARY), stroke_w=1.65
        )

        p.setFont(Theme.get_font(9.2, QFont.Weight.DemiBold))
        p.setPen(QColor(Theme.HEX_TEXT_PRIMARY))
        vol_label = "Volume (Silenciado)" if self.is_muted else "Volume Master"
        p.drawText(QRectF(vol_r.left() + 46.0, vol_r.top(), vol_r.width() - 110.0, vol_r.height()), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, vol_label)

        p.setFont(Theme.get_font(9.2, QFont.Weight.Bold))
        p.setPen(acc_light)
        val_str = "0%" if self.is_muted else f"{self.volume_val}%"
        p.drawText(QRectF(vol_r.right() - 60.0, vol_r.top(), 46.0, vol_r.height()), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, val_str)

        # 2. Brilho (slider completo quando suportado; nota discreta quando indisponível)
        if spec["bri_rect"] is not None:
            bri_r = spec["bri_rect"]
            bri_hov = (self._hovered_id == "slider:bri" or self._dragging_slider == "bri")
            p.setPen(QPen(QColor(255, 255, 255, 28 if bri_hov else 16), 1.0))
            p.setBrush(QColor(255, 255, 255, 12 if bri_hov else 8))
            p.drawRoundedRect(bri_r, 14.0, 14.0)

            self._draw_clipped_slider_fill(p, bri_r, float(self.brightness_val) / 100.0, 14.0, QColor(245, 158, 11, 56))
            bri_icon_r = QRectF(bri_r.left() + 14.0, bri_r.top() + 13.0, 24.0, 24.0)
            IconFactory.paint_glyph(p, "brightness", bri_icon_r, QColor("#F59E0B"), stroke_w=1.65)

            p.setFont(Theme.get_font(9.2, QFont.Weight.DemiBold))
            p.setPen(QColor(Theme.HEX_TEXT_PRIMARY))
            p.drawText(QRectF(bri_r.left() + 46.0, bri_r.top(), bri_r.width() - 110.0, bri_r.height()), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, "Brilho da Tela")

            p.setFont(Theme.get_font(9.2, QFont.Weight.Bold))
            p.setPen(QColor("#FCD34D"))
            p.drawText(QRectF(bri_r.right() - 60.0, bri_r.top(), 46.0, bri_r.height()), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, f"{self.brightness_val}%")
        elif spec["bri_note_rect"] is not None:
            nr = spec["bri_note_rect"]
            p.setPen(QPen(QColor(255, 255, 255, 12), 1.0))
            p.setBrush(QColor(255, 255, 255, 5))
            p.drawRoundedRect(nr, 10.0, 10.0)
            IconFactory.paint_glyph(p, "brightness", QRectF(nr.left() + 10.0, nr.top() + 6.0, 18.0, 18.0), QColor(Theme.HEX_TEXT_MUTED), stroke_w=1.4)
            p.setFont(Theme.get_font(8.2, QFont.Weight.Normal))
            p.setPen(QColor(Theme.HEX_TEXT_MUTED))
            p.drawText(QRectF(nr.left() + 34.0, nr.top(), nr.width() - 48.0, nr.height()), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, "Brilho por software indisponível neste monitor")
        p.restore()

    def _paint_audio_pill(self, p: QPainter, pill_r: QRectF, acc_col: QColor):
        p.save()
        hov = (self._hovered_id == "audio_pill")
        prs = (self._pressed_id == "audio_pill")
        p.setPen(QPen(QColor(255, 255, 255, 32 if hov else 16), 1.0))
        p.setBrush(QColor(255, 255, 255, 18 if prs else (13 if hov else 8)))
        p.drawRoundedRect(pill_r, 14.0, 14.0)

        icon_kind = "speaker"
        dev_l = self.default_audio_name.lower()
        if any(k in dev_l for k in ("fone", "headphone", "headset", "tune", "wh-")):
            icon_kind = "headphones"
        elif any(k in dev_l for k in ("hdmi", "displayport", "monitor", "tv", "dell", "lg")):
            icon_kind = "screen"

        IconFactory.paint_glyph(p, icon_kind, QRectF(pill_r.left() + 13.0, pill_r.top() + 14.0, 24.0, 24.0), QColor(Theme.COLOR_ACCENT_LIGHT), stroke_w=1.6)

        p.setFont(Theme.get_font(7.6, QFont.Weight.Bold))
        p.setPen(QColor(Theme.HEX_TEXT_MUTED))
        p.drawText(QRectF(pill_r.left() + 46.0, pill_r.top() + 7.0, pill_r.width() - 78.0, 14.0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, "SAÍDA DE ÁUDIO")

        p.setFont(Theme.get_font(9.2, QFont.Weight.DemiBold))
        p.setPen(QColor(Theme.HEX_TEXT_PRIMARY))
        p.drawText(QRectF(pill_r.left() + 46.0, pill_r.top() + 22.0, pill_r.width() - 78.0, 22.0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.default_audio_name)

        IconFactory.paint_glyph(p, "chevron", QRectF(pill_r.right() - 28.0, pill_r.top() + 18.0, 16.0, 16.0), QColor(Theme.HEX_TEXT_SECONDARY), stroke_w=1.65)
        p.restore()

    def _paint_media_card(self, p: QPainter, media_r: QRectF, acc_col: QColor):
        p.save()
        p.setPen(QPen(QColor(255, 255, 255, 18), 1.0))
        p.setBrush(QColor(20, 20, 20, 232))
        p.drawRoundedRect(media_r, 16.0, 16.0)

        title_txt = self.media_info.get("title", "Áudio do Sistema")
        sub_txt = f"{self.media_info.get('app', 'Player')} • {self.media_info.get('status', self._MEDIA_PLAYING_STATUS)}"

        art_r = QRectF(media_r.left() + 14.0, media_r.top() + 14.0, 54.0, 54.0)
        p.setPen(Qt.PenStyle.NoPen)
        art_grad = QLinearGradient(art_r.topLeft(), art_r.bottomRight())
        art_grad.setColorAt(0.0, acc_col)
        art_grad.setColorAt(1.0, Theme.COLOR_ACCENT_SECONDARY)
        p.setBrush(art_grad)
        p.drawRoundedRect(art_r, 12.0, 12.0)

        IconFactory.paint_glyph(p, "music", art_r.adjusted(13, 13, -13, -13), QColor(Theme.COLOR_TEXT_ON_ACCENT), stroke_w=1.8)

        text_max_w = max(120.0, media_r.width() - 80.0 - 120.0)
        p.setFont(Theme.get_font(9.5, QFont.Weight.Bold))
        p.setPen(QColor(Theme.HEX_TEXT_PRIMARY))
        p.drawText(QRectF(media_r.left() + 80.0, media_r.top() + 18.0, text_max_w, 22.0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, title_txt)

        p.setFont(Theme.get_font(8.2, QFont.Weight.Normal))
        p.setPen(QColor(Theme.HEX_TEXT_SECONDARY))
        p.drawText(QRectF(media_r.left() + 80.0, media_r.top() + 42.0, text_max_w, 20.0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, sub_txt)

        prev_r, play_r, next_r = self._rect_media_controls()
        IconFactory.paint_glyph(p, "prev", prev_r.adjusted(6, 9, -6, -9), QColor(Theme.HEX_TEXT_PRIMARY if self._hovered_id == "media:prev" else Theme.HEX_TEXT_SECONDARY))
        IconFactory.paint_glyph(p, "pause", play_r.adjusted(7, 7, -7, -7), QColor(Theme.HEX_TEXT_PRIMARY))
        IconFactory.paint_glyph(p, "next", next_r.adjusted(6, 9, -6, -9), QColor(Theme.HEX_TEXT_PRIMARY if self._hovered_id == "media:next" else Theme.HEX_TEXT_SECONDARY))
        p.restore()

    # ==========================================================================
    # FLYOUT WI-FI (Visão 1)
    # ==========================================================================

    def _paint_wifi_flyout(self, p: QPainter, w: float, h: float, acc_col: QColor):
        p.save()
        acc_light = QColor(Theme.COLOR_ACCENT_LIGHT)
        on_acc = QColor(Theme.COLOR_TEXT_ON_ACCENT)
        soft_fill = QColor(Theme.COLOR_ACCENT_SOFT_FILL)

        self._draw_round_icon_btn(p, self._rect_header_back(), "back", QColor(Theme.HEX_TEXT_PRIMARY), hovered=(self._hovered_id == "back"))
        p.setFont(Theme.get_font(12.5, QFont.Weight.Bold))
        p.setPen(QColor(Theme.HEX_TEXT_PRIMARY))
        p.drawText(QRectF(64.0, 18.0, w - 170.0, 34.0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, "Redes Wi-Fi")

        self._draw_round_icon_btn(
            p, self._rect_header_refresh(), "refresh",
            acc_light if self.wifi_scanning else QColor(Theme.HEX_TEXT_SECONDARY),
            hovered=(self._hovered_id == "refresh")
        )
        self._draw_round_icon_btn(p, self._rect_header_close(), "close", QColor(Theme.HEX_TEXT_SECONDARY), hovered=(self._hovered_id == "close"))

        p.setPen(QPen(QColor(255, 255, 255, 16), 1.0))
        p.drawLine(QPointF(22.0, 62.0), QPointF(w - 22.0, 62.0))

        if self.location_permission_denied:
            loc_box = QRectF(22.0, 68.0, w - 44.0, 34.0)
            p.setPen(QPen(QColor(245, 158, 11, 80), 1.0))
            p.setBrush(QColor(245, 158, 11, 25))
            p.drawRoundedRect(loc_box, 8.0, 8.0)
            p.setFont(Theme.get_font(8.4, QFont.Weight.Medium))
            p.setPen(QColor("#FCD34D"))
            p.drawText(loc_box, Qt.AlignmentFlag.AlignCenter, "Localização necessária para Wi-Fi • Clique para ativar")
        elif self.connection_status_msg:
            p.setFont(Theme.get_font(8.4, QFont.Weight.Medium))
            p.setPen(QColor("#F43F5E") if self.connection_has_error else acc_light)
            p.drawText(QRectF(22.0, 64.0, w - 44.0, 18.0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.connection_status_msg)

        cards = self._get_wifi_card_rects()
        if not cards:
            p.setFont(Theme.get_font(9.2, QFont.Weight.Medium))
            p.setPen(QColor(Theme.HEX_TEXT_MUTED))
            empty_msg = "Buscando redes disponíveis..." if self.wifi_scanning else (
                "Nenhuma interface Wi-Fi física detectada neste computador."
                if not self.wifi_available
                else "Nenhuma rede Wi-Fi visível no momento."
            )
            p.drawText(QRectF(28.0, 140.0, w - 56.0, 90.0), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, empty_msg)
        else:
            for idx, (n, card_r) in enumerate(cards):
                is_sel = (self.selected_ssid == n["ssid"])
                is_hov = (self._hovered_id == f"wifi:{idx}")
                p.save()
                if n.get("is_connected"):
                    p.setPen(QPen(acc_light, 1.1))
                    p.setBrush(soft_fill)
                elif is_sel:
                    border_c = QColor("#F43F5E") if self.connection_has_error else acc_col
                    p.setPen(QPen(border_c, 1.2))
                    p.setBrush(QColor(20, 20, 20, 245))
                else:
                    p.setPen(QPen(QColor(255, 255, 255, 28 if is_hov else 14), 1.0))
                    p.setBrush(QColor(255, 255, 255, 13 if is_hov else 8))
                p.drawRoundedRect(card_r, 14.0, 14.0)

                IconFactory.paint_glyph(p, "wifi", QRectF(card_r.left() + 14.0, card_r.top() + 16.0, 22.0, 22.0), acc_light if n.get("is_connected") else QColor(Theme.HEX_TEXT_PRIMARY))

                text_w = card_r.width() - 130.0
                p.setFont(Theme.get_font(9.4, QFont.Weight.Bold))
                p.setPen(QColor(Theme.HEX_TEXT_PRIMARY))
                p.drawText(QRectF(card_r.left() + 46.0, card_r.top() + 9.0, text_w, 20.0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, n["ssid"])

                p.setFont(Theme.get_font(8.2, QFont.Weight.Normal))
                p.setPen(acc_light if n.get("is_connected") else QColor(Theme.HEX_TEXT_SECONDARY))
                sub_txt = "Conectado, seguro" if n.get("is_connected") else f"{n['security']} • {n['signal']}%"
                p.drawText(QRectF(card_r.left() + 46.0, card_r.top() + 30.0, text_w, 18.0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, sub_txt)

                if n.get("is_connected"):
                    IconFactory.paint_glyph(p, "check", QRectF(card_r.right() - 34.0, card_r.top() + 17.0, 20.0, 20.0), QColor("#22C55E"), stroke_w=1.8)
                elif is_sel and n.get("is_secure"):
                    p.setFont(Theme.get_font(8.2, QFont.Weight.Medium))
                    p.setPen(QColor("#F43F5E") if self.connection_has_error else QColor(Theme.HEX_TEXT_SECONDARY))
                    label_txt = "Senha incorreta. Digite novamente:" if self.connection_has_error else "Digite a senha da rede:"
                    p.drawText(QRectF(card_r.left() + 16.0, card_r.top() + 48.0, card_r.width() - 32.0, 18.0), Qt.AlignmentFlag.AlignLeft, label_txt)

                    btn_conn = QRectF(card_r.right() - 100.0, card_r.top() + 112.0, 88.0, 30.0)
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(acc_col)
                    p.drawRoundedRect(btn_conn, 8.0, 8.0)
                    p.setFont(Theme.get_font(8.4, QFont.Weight.Bold))
                    p.setPen(on_acc)
                    p.drawText(btn_conn, Qt.AlignmentFlag.AlignCenter, "Conectar")

                    btn_canc = QRectF(card_r.right() - 198.0, card_r.top() + 112.0, 88.0, 30.0)
                    p.setPen(QPen(QColor(255, 255, 255, 20), 1.0))
                    p.setBrush(QColor(255, 255, 255, 8))
                    p.drawRoundedRect(btn_canc, 8.0, 8.0)
                    p.setPen(QColor(Theme.HEX_TEXT_SECONDARY))
                    p.drawText(btn_canc, Qt.AlignmentFlag.AlignCenter, "Cancelar")
                else:
                    p.setFont(Theme.get_font(8.2, QFont.Weight.Normal))
                    p.setPen(QColor(Theme.HEX_TEXT_MUTED))
                    p.drawText(QRectF(card_r.right() - 78.0, card_r.top() + 6.0, 64.0, 44.0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, f"{n['bars']} barras")
                p.restore()

        p.setFont(Theme.get_font(8.4, QFont.Weight.Medium))
        p.setPen(acc_light)
        p.drawText(self._rect_footer_btn(), Qt.AlignmentFlag.AlignCenter, "Configurações avançadas de Wi-Fi do Windows")
        p.restore()

    # ==========================================================================
    # FLYOUT SAÍDA DE ÁUDIO (Visão 2)
    # ==========================================================================

    def _paint_audio_flyout(self, p: QPainter, w: float, h: float, acc_col: QColor):
        p.save()
        acc_light = QColor(Theme.COLOR_ACCENT_LIGHT)
        on_acc = QColor(Theme.COLOR_TEXT_ON_ACCENT)
        soft_fill = QColor(Theme.COLOR_ACCENT_SOFT_FILL)

        self._draw_round_icon_btn(p, self._rect_header_back(), "back", QColor(Theme.HEX_TEXT_PRIMARY), hovered=(self._hovered_id == "back"))
        p.setFont(Theme.get_font(12.5, QFont.Weight.Bold))
        p.setPen(QColor(Theme.HEX_TEXT_PRIMARY))
        p.drawText(QRectF(64.0, 18.0, w - 130.0, 34.0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, "Saída de Áudio")

        self._draw_round_icon_btn(p, self._rect_header_close(), "close", QColor(Theme.HEX_TEXT_SECONDARY), hovered=(self._hovered_id == "close"))

        p.setPen(QPen(QColor(255, 255, 255, 16), 1.0))
        p.drawLine(QPointF(22.0, 62.0), QPointF(w - 22.0, 62.0))

        # Slider Volume Master
        vol_r = self._rect_audio_vol_slider()
        p.setPen(QPen(QColor(255, 255, 255, 16), 1.0))
        p.setBrush(QColor(255, 255, 255, 8))
        p.drawRoundedRect(vol_r, 14.0, 14.0)

        ratio_v = 0.0 if self.is_muted else (float(self.volume_val) / 100.0)
        self._draw_clipped_slider_fill(p, vol_r, ratio_v, 14.0, soft_fill)

        IconFactory.paint_glyph(
            p, "mute" if self.is_muted else "volume",
            QRectF(vol_r.left() + 14.0, vol_r.top() + 13.0, 24.0, 24.0),
            QColor("#F43F5E") if self.is_muted else QColor(Theme.HEX_TEXT_PRIMARY), stroke_w=1.65
        )

        p.setFont(Theme.get_font(9.2, QFont.Weight.DemiBold))
        p.setPen(QColor(Theme.HEX_TEXT_PRIMARY))
        p.drawText(QRectF(vol_r.left() + 46.0, vol_r.top(), vol_r.width() - 110.0, vol_r.height()), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, "Volume do Dispositivo")

        p.setFont(Theme.get_font(9.2, QFont.Weight.Bold))
        p.setPen(acc_light)
        val_str = "0%" if self.is_muted else f"{self.volume_val}%"
        p.drawText(QRectF(vol_r.right() - 60.0, vol_r.top(), 46.0, vol_r.height()), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, val_str)

        p.setFont(Theme.get_font(7.8, QFont.Weight.Bold))
        p.setPen(QColor(Theme.HEX_TEXT_MUTED))
        p.drawText(QRectF(24.0, 134.0, w - 48.0, 18.0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, "DISPOSITIVOS DE REPRODUÇÃO DISPONÍVEIS")

        dev_items = self._get_audio_device_rects()
        if not dev_items:
            p.setFont(Theme.get_font(9.2, QFont.Weight.Medium))
            p.setPen(QColor(Theme.HEX_TEXT_MUTED))
            p.drawText(QRectF(28.0, 180.0, w - 56.0, 70.0), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, "Nenhum dispositivo de reprodução ativo encontrado.")
        else:
            for idx, (d, card_r) in enumerate(dev_items):
                is_def = bool(d.get("is_default", False))
                is_hov = (self._hovered_id == f"audiodev:{idx}")
                p.save()
                if is_def:
                    p.setPen(QPen(acc_light, 1.2))
                    p.setBrush(soft_fill)
                else:
                    p.setPen(QPen(QColor(255, 255, 255, 28 if is_hov else 14), 1.0))
                    p.setBrush(QColor(255, 255, 255, 13 if is_hov else 8))
                p.drawRoundedRect(card_r, 14.0, 14.0)

                radio_pt = QPointF(card_r.left() + 20.0, card_r.center().y())
                p.setPen(QPen(acc_col if is_def else QColor(255, 255, 255, 45), 1.5))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(radio_pt, 7.5, 7.5)
                if is_def:
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(acc_col)
                    p.drawEllipse(radio_pt, 4.0, 4.0)

                dev_ic = "headphones" if d.get("icon_type") == "headphones" else ("screen" if d.get("icon_type") == "screen" else "speaker")
                IconFactory.paint_glyph(p, dev_ic, QRectF(card_r.left() + 36.0, card_r.top() + 17.0, 22.0, 22.0), acc_light if is_def else QColor(Theme.HEX_TEXT_SECONDARY))

                name_max_w = card_r.width() - (146.0 if is_def else 80.0)
                p.setFont(Theme.get_font(9.2, QFont.Weight.Bold if is_def else QFont.Weight.Medium))
                p.setPen(QColor(Theme.HEX_TEXT_PRIMARY))
                p.drawText(QRectF(card_r.left() + 66.0, card_r.top() + 9.0, name_max_w, 20.0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, d["name"])

                p.setFont(Theme.get_font(8.0, QFont.Weight.Normal))
                p.setPen(acc_light if is_def else QColor(Theme.HEX_TEXT_MUTED))
                sub_dev = "Saída Padrão do Sistema" if is_def else "Disponível para reprodução"
                p.drawText(QRectF(card_r.left() + 66.0, card_r.top() + 31.0, name_max_w, 18.0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, sub_dev)

                if is_def:
                    tag_r = QRectF(card_r.right() - 68.0, card_r.top() + 18.0, 56.0, 22.0)
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(acc_col)
                    p.drawRoundedRect(tag_r, 6.0, 6.0)
                    p.setFont(Theme.get_font(7.4, QFont.Weight.Bold))
                    p.setPen(on_acc)
                    p.drawText(tag_r, Qt.AlignmentFlag.AlignCenter, "ATIVO")
                p.restore()

        p.setFont(Theme.get_font(8.4, QFont.Weight.Medium))
        p.setPen(acc_light)
        p.drawText(self._rect_footer_btn(), Qt.AlignmentFlag.AlignCenter, "Configurações de Som do Windows")
        p.restore()


class SystemOverlayManager(QObject):
    """Controlador de ciclo de vida do overlay com animações suaves e restauração de foco."""

    overlay_opened = pyqtSignal()
    overlay_closed = pyqtSignal()

    def __init__(self, radio_adapter=None, wifi_manager=None, audio_adapter=None, system_controls=None, parent=None):
        super().__init__(parent)
        self.radio_adapter = radio_adapter
        self.wifi_manager = wifi_manager
        self.audio_adapter = audio_adapter
        self.system_controls = system_controls
        self.prev_foreground_hwnd = None
        self.is_open = False
        self._anim_group = None

        self.backdrop = BackdropDimWidget()
        self.panel = ControlCenterOverlay(
            radio_adapter=self.radio_adapter,
            wifi_manager=self.wifi_manager,
            audio_adapter=self.audio_adapter,
            system_controls=self.system_controls,
        )

        self.backdrop.clicked_outside.connect(self.dismiss)
        self.panel.dismiss_requested.connect(self.dismiss)

    def apply_theme(self):
        """Propaga mudanças de cor/tema em tempo real ao painel aberto ou fechado."""
        self.panel.apply_theme()

    def _stop_anims(self):
        if self._anim_group:
            try:
                self._anim_group.stop()
                self._anim_group.deleteLater()
            except Exception:
                pass
            self._anim_group = None

    def show_control_center(self):
        if self.is_open:
            return

        self._stop_anims()
        try:
            self.prev_foreground_hwnd = win32gui.GetForegroundWindow()
        except Exception:
            self.prev_foreground_hwnd = None

        # Prepara o desfoque antes de exibir o backdrop (zero tela cinza)
        self.backdrop.prepare_blurred_snapshot()

        tx, ty, tw, th = self.panel.target_geometry()
        reduced = Theme.reduced_motion_enabled()

        if reduced:
            self.backdrop.setWindowOpacity(1.0)
            self.panel.setWindowOpacity(1.0)
            self.panel.setGeometry(tx, ty, tw, th)
            self.backdrop.show()
            self.panel.show()
            self.panel.raise_()
            self.panel.activateWindow()
            self.panel.setFocus()
        else:
            self.backdrop.setWindowOpacity(0.0)
            self.panel.setWindowOpacity(0.0)
            self.panel.setGeometry(tx, max(0, ty - 22), tw, th)
            self.backdrop.show()
            self.panel.show()
            self.panel.raise_()
            self.panel.activateWindow()
            self.panel.setFocus()

            grp = QParallelAnimationGroup(self)
            a_bg = QPropertyAnimation(self.backdrop, b"windowOpacity", grp)
            a_bg.setDuration(200)
            a_bg.setStartValue(0.0)
            a_bg.setEndValue(1.0)
            a_bg.setEasingCurve(QEasingCurve.Type.OutCubic)

            a_op = QPropertyAnimation(self.panel, b"windowOpacity", grp)
            a_op.setDuration(210)
            a_op.setStartValue(0.0)
            a_op.setEndValue(1.0)
            a_op.setEasingCurve(QEasingCurve.Type.OutCubic)

            a_pos = QPropertyAnimation(self.panel, b"pos", grp)
            a_pos.setDuration(220)
            a_pos.setStartValue(QPoint(tx, max(0, ty - 22)))
            a_pos.setEndValue(QPoint(tx, ty))
            a_pos.setEasingCurve(QEasingCurve.Type.OutCubic)

            grp.addAnimation(a_bg)
            grp.addAnimation(a_op)
            grp.addAnimation(a_pos)
            self._anim_group = grp
            grp.start()

        self.is_open = True
        self.overlay_opened.emit()

    def dismiss(self, immediate: bool = False):
        if not self.is_open:
            return

        self.is_open = False
        self._stop_anims()

        if immediate or Theme.reduced_motion_enabled():
            self._finish_dismiss()
            return

        tx, ty, _, _ = self.panel.target_geometry()
        grp = QParallelAnimationGroup(self)

        a_bg = QPropertyAnimation(self.backdrop, b"windowOpacity", grp)
        a_bg.setDuration(170)
        a_bg.setStartValue(self.backdrop.windowOpacity())
        a_bg.setEndValue(0.0)
        a_bg.setEasingCurve(QEasingCurve.Type.InCubic)

        a_op = QPropertyAnimation(self.panel, b"windowOpacity", grp)
        a_op.setDuration(170)
        a_op.setStartValue(self.panel.windowOpacity())
        a_op.setEndValue(0.0)
        a_op.setEasingCurve(QEasingCurve.Type.InCubic)

        a_pos = QPropertyAnimation(self.panel, b"pos", grp)
        a_pos.setDuration(175)
        a_pos.setStartValue(self.panel.pos())
        a_pos.setEndValue(QPoint(tx, max(0, ty - 18)))
        a_pos.setEasingCurve(QEasingCurve.Type.InCubic)

        grp.addAnimation(a_bg)
        grp.addAnimation(a_op)
        grp.addAnimation(a_pos)
        grp.finished.connect(self._finish_dismiss)
        self._anim_group = grp
        grp.start()

    def _finish_dismiss(self):
        self._stop_anims()
        self.panel.hide()
        self.backdrop.hide()
        self.backdrop.clear_snapshot()
        self.panel.setWindowOpacity(1.0)
        self.backdrop.setWindowOpacity(1.0)
        self.overlay_closed.emit()

        if self.prev_foreground_hwnd and win32gui.IsWindow(self.prev_foreground_hwnd):
            try:
                win32gui.SetForegroundWindow(self.prev_foreground_hwnd)
            except Exception:
                pass
        self.prev_foreground_hwnd = None

    def toggle(self):
        if self.is_open:
            self.dismiss()
        else:
            self.show_control_center()
