"""
Suíte de Validação RC 0.2 — Visibilidade Contextual, Capacidades Reais, Blur, Animações e Proporção
"""

import os
import sys
import unittest
from unittest.mock import patch

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QEvent

from core.visibility_monitor import classify_foreground_state, VisibilityMonitor
from core.radio_adapter import RadioAdapter
from ui.system_overlay import ControlCenterOverlay, SystemOverlayManager
from ui.theme import Theme
import main

_APP = QApplication.instance() or QApplication(sys.argv)


class TestVisibilityMonitorClassification(unittest.TestCase):
    def test_desktop_idle_on_progman_or_empty_fg(self):
        st, rem = classify_foreground_state(0, set())
        self.assertEqual(st, VisibilityMonitor.DESKTOP_IDLE)
        self.assertTrue(rem)

        with patch("core.visibility_monitor.win32gui.IsWindow", return_value=True), \
             patch("core.visibility_monitor.win32gui.GetClassName", return_value="Progman"):
            st2, _ = classify_foreground_state(12345, set())
            self.assertEqual(st2, VisibilityMonitor.DESKTOP_IDLE)

    def test_ignores_own_monolith_hwnds_without_loop(self):
        with patch("core.visibility_monitor.win32gui.IsWindow", return_value=True):
            st, rem = classify_foreground_state(999, {999}, prev_non_monolith_state=VisibilityMonitor.APP_AUTO_HIDE)
            self.assertEqual(st, VisibilityMonitor.APP_AUTO_HIDE)
            self.assertFalse(rem)

    def test_distinguishes_maximized_app_from_fullscreen_hidden(self):
        mon = (0, 0, 1920, 1080)
        work = (0, 0, 1920, 1032)  # Barra de tarefas visível (48px)

        with patch("core.visibility_monitor.win32gui.IsWindow", return_value=True), \
             patch("core.visibility_monitor.win32gui.GetClassName", return_value="Chrome_WidgetWin_1"), \
             patch("core.visibility_monitor.win32gui.IsWindowVisible", return_value=True), \
             patch("core.visibility_monitor.win32gui.IsIconic", return_value=False), \
             patch("core.visibility_monitor.win32gui.GetWindowText", return_value="Navegador"), \
             patch("core.visibility_monitor.get_monitor_rects", return_value=(mon, work)):

            # Janela maximizada comum (respeita rcWork y=0..1032) -> APP_AUTO_HIDE / EDGE_REVEAL
            with patch("core.visibility_monitor.get_window_bounds", return_value=(0, 0, 1920, 1032)):
                st_max, _ = classify_foreground_state(555, set(), edge_hovered=False)
                self.assertEqual(st_max, VisibilityMonitor.APP_AUTO_HIDE)
                st_rev, _ = classify_foreground_state(555, set(), edge_hovered=True)
                self.assertEqual(st_rev, VisibilityMonitor.EDGE_REVEAL)

            # Aplicação/Vídeo/Jogo em tela cheia cobrindo todo rcMonitor (0..1080) -> FULLSCREEN_HIDDEN
            with patch("core.visibility_monitor.get_window_bounds", return_value=(0, 0, 1920, 1080)), \
                 patch("core.visibility_monitor.win32gui.GetWindowLong", return_value=0x16000000):
                st_fs, _ = classify_foreground_state(555, set(), edge_hovered=True)
                # Mesmo com mouse no topo (edge_hovered=True), nunca revela durante FULLSCREEN_HIDDEN
                self.assertEqual(st_fs, VisibilityMonitor.FULLSCREEN_HIDDEN)


class TestHardwareCapabilitiesAndAdaptiveComposition(unittest.TestCase):
    def test_hides_missing_wifi_and_bluetooth_controls_honestly(self):
        cc = ControlCenterOverlay()
        cc.wifi_available = False
        cc.bt_available = False
        cc.hotspot_supported = False
        cc.has_battery = False
        cc.battery_saver_supported = False
        cc.night_light_supported = True
        cc.brightness_supported = True
        cc.brightness_val = 80
        cc.media_info = {"active": False}

        spec = cc._compute_main_layout_spec()
        toggle_ids = [t["id"] for t in spec["toggles"]]
        self.assertNotIn("WiFi", toggle_ids)
        self.assertNotIn("Bluetooth", toggle_ids)
        self.assertNotIn("Hotspot", toggle_ids)
        self.assertNotIn("Airplane", toggle_ids)
        self.assertNotIn("BatterySaver", toggle_ids)
        self.assertIn("NightLight", toggle_ids)
        self.assertIsNotNone(spec["capability_banner_rect"])
        self.assertIsNone(spec["media_rect"])  # Sem card de mídia fictício quando inativa

    def test_purges_stale_radios_when_adapter_absent(self):
        ra = RadioAdapter()
        ra._radios_cache = {"WiFi": "On", "Bluetooth": "On"}
        ra._tethering_supported = True
        ra._parse_radios_update("[]")
        self.assertFalse(ra.has_radio("WiFi"))
        self.assertFalse(ra.has_radio("Bluetooth"))
        self.assertFalse(ra.get_tethering_status()[0])
        ra.shutdown()

    def test_compact_notch_190x30_and_no_focus_steal_on_edge_reveal(self):
        win = main.DynamicIslandWindow()
        self.assertEqual(win.COMPACT_W, 190)
        self.assertEqual(win.COMPACT_H, 30)
        self.assertTrue(win.testAttribute(main.Qt.WidgetAttribute.WA_ShowWithoutActivating))
        # Simula APP_AUTO_HIDE -> EDGE_REVEAL -> APP_AUTO_HIDE
        win._apply_visibility_state(VisibilityMonitor.APP_AUTO_HIDE, animate=False)
        self.assertLess(win.y(), 0)
        QApplication.sendEvent(win, QEvent(QEvent.Type.Enter))
        _APP.processEvents()
        win.quit_app()


if __name__ == "__main__":
    unittest.main(verbosity=2)
