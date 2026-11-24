"""
Testes de Integração — Etapa de Estabilização e Portabilidade (PROTO-TYPE Monolith)
Verifica:
- Inicialização centralizada da cápsula em resoluções variadas
- Integração DynamicIslandWindow <-> SystemOverlayManager <-> ControlCenterOverlay
- Propagação de tema em tempo real e material OLED Stealth
- Ausência de dados simulados em bateria/controles
- Sintaxe do iniciar.vbs e integridade da Barra de Tarefas nativa
"""

import os
import re
import sys
import unittest
import win32gui

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from PyQt6.QtWidgets import QApplication
from ui.theme import Theme
from core.task_manager import TaskManager
from core.system_monitor import SystemMonitor
from main import DynamicIslandWindow

_APP = QApplication.instance() or QApplication(sys.argv)


class TestStabilizationIntegration(unittest.TestCase):
    def setUp(self):
        Theme.apply_preset("sapphire", save=False)
        Theme.apply_notch_material("oled_black", save=False)
        Theme.satellite_enabled = True
        self.win = DynamicIslandWindow()
        self.win.show()
        _APP.processEvents()

    def tearDown(self):
        try:
            self.win.overlay_manager.dismiss()
            self.win.radio_adapter.shutdown()
            self.win.close()
        except Exception:
            pass

    def test_capsule_fixed_centered_on_monitor(self):
        geo = self.win._get_screen_geometry()
        expected_x = geo.x() + (geo.width() - self.win.width()) // 2
        self.assertEqual(self.win.x(), expected_x)
        self.assertEqual(self.win.y(), geo.y() + self.win.TOP_MARGIN)

    def test_overlay_open_close_and_theme_propagation(self):
        # Abre Centro de Controle pela janela principal
        self.win.toggle_control_center()
        _APP.processEvents()
        self.assertTrue(self.win.overlay_manager.is_open)
        self.assertTrue(self.win.overlay_manager.panel.isVisible())

        # Troca tema na ilha -> deve propagar em tempo real para o overlay
        self.win._on_select_preset("ruby")
        _APP.processEvents()
        self.assertEqual(Theme.HEX_ACCENT.lower(), "#f43f5e")
        self.assertIn("#f43f5e", self.win.overlay_manager.panel.password_input.styleSheet().lower())

        # Fecha pelo toggle
        self.win.toggle_control_center()
        _APP.processEvents()
        self.assertFalse(self.win.overlay_manager.is_open)

        # Restaura preset padrão
        Theme.apply_preset("sapphire", save=True)
        self.win._apply_live_theme()

    def test_no_fake_battery_or_simulated_media(self):
        stats = SystemMonitor.get_stats()
        if not stats["has_battery"]:
            self.assertIsNone(stats["battery_percent"])
            self.assertIsNone(stats["is_charging"])
        self.assertFalse(hasattr(self.win, "simulated_media_active"))
        self.assertFalse(hasattr(self.win, "btn_toggle_sim_media"))

    def test_on_demand_thumbnails_cleared_on_collapse(self):
        TaskManager.clear_thumbnail_cache()
        self.assertEqual(len(TaskManager._thumbnail_cache), 0)
        self.win.expand()
        self.win.anim.stop()
        self.win.resize(self.win.EXPANDED_W, self.win.EXPANDED_H)
        self.win.content.show()
        self.win._switch_tab(0)
        _APP.processEvents()
        self.assertEqual(len(TaskManager._thumbnail_cache), 0)
        self.win.collapse()
        self.win.anim.stop()
        _APP.processEvents()
        self.assertEqual(len(TaskManager._thumbnail_cache), 0)

    def test_vbs_startup_syntax_and_taskbar_preserved(self):
        vbs_path = os.path.join(BASE_DIR, "iniciar.vbs")
        with open(vbs_path, "r", encoding="utf-8") as f:
            vbs_content = f.read()
        self.assertRegex(vbs_content, r"Set\s+fso\s*=\s*CreateObject")
        self.assertFalse(re.search(r"^\s*fso\s*=\s*CreateObject", vbs_content, re.MULTILINE))

        hwnd_tb = win32gui.FindWindow("Shell_TrayWnd", None)
        if hwnd_tb:
            self.assertTrue(bool(win32gui.IsWindowVisible(hwnd_tb)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
