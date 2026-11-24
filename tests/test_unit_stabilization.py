"""
Testes Unitários — Etapa de Estabilização e Portabilidade (PROTO-TYPE Monolith)
Sem dependência de hardware de rádio ou rede.
"""

import os
import sys
import unittest
import xml.etree.ElementTree as ET

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from PyQt6.QtWidgets import QApplication
from ui.theme import Theme
from ui.system_overlay import ControlCenterOverlay
from core.radio_adapter import RadioAdapter
from core.wifi_manager import _generate_wifi_profile_xml, _generate_open_profile_xml

_APP = QApplication.instance() or QApplication(sys.argv)


class TestThemeAndOledStealth(unittest.TestCase):
    def setUp(self):
        Theme.apply_preset("sapphire", save=False)
        Theme.apply_notch_material("oled_black", save=False)

    def test_oled_stealth_materials(self):
        Theme.apply_notch_material("oled_black", save=False)
        self.assertEqual(Theme.HEX_NOTCH_BG, "#000000")
        self.assertEqual(Theme.COLOR_NOTCH_BG.red(), 0)
        self.assertEqual(Theme.COLOR_NOTCH_BORDER_IDLE.name(), "#000000")

        Theme.apply_notch_material("obsidian_graphite", save=False)
        self.assertEqual(Theme.HEX_NOTCH_BG, "#101116")
        self.assertEqual(Theme.COLOR_NOTCH_BG.red(), 16)

    def test_wcag_perceptual_tokens(self):
        Theme.apply_custom_hex("#FACC15", save=False)
        self.assertEqual(Theme.HEX_TEXT_ON_ACCENT.lower(), "#060911")
        Theme.apply_preset("ruby", save=False)
        self.assertEqual(Theme.HEX_TEXT_ON_ACCENT.lower(), "#ffffff")
        self.assertNotEqual(Theme.HEX_ACCENT.lower(), Theme.COLOR_ACCENT_HOVER.name().lower())


class TestPortabilityAdapters(unittest.TestCase):
    def test_radio_json_normalization_handles_ps51_single_object(self):
        single = '{"name":"Wi-Fi","kind":"WiFi","state":"On"}'
        res_single = RadioAdapter.normalize_radios_payload(single)
        self.assertEqual(len(res_single), 1)
        self.assertEqual(res_single[0]["kind"], "WiFi")

        empty = "[]"
        self.assertEqual(RadioAdapter.normalize_radios_payload(empty), [])

        multi = '[{"kind":"WiFi","state":"On"},{"kind":"Bluetooth","state":"Off"}]'
        res_multi = RadioAdapter.normalize_radios_payload(multi)
        self.assertEqual(len(res_multi), 2)

    def test_wifi_xml_escaping_and_wpa2_wpa3(self):
        ssid = 'Rede & <Casa> "5G"'
        pwd = 'Sen<ha>&123"!\''
        xml_wpa2 = _generate_wifi_profile_xml(ssid, pwd, security="WPA2-Personal")
        xml_wpa3 = _generate_wifi_profile_xml(ssid, pwd, security="WPA3-Personal")
        xml_open = _generate_open_profile_xml(ssid)

        root2 = ET.fromstring(xml_wpa2)
        root3 = ET.fromstring(xml_wpa3)
        root_open = ET.fromstring(xml_open)

        ns = {"w": "http://www.microsoft.com/networking/WLAN/profile/v1"}
        self.assertEqual(root2.find(".//w:authentication", ns).text, "WPA2PSK")
        self.assertEqual(root2.find(".//w:keyMaterial", ns).text, pwd)
        self.assertEqual(root3.find(".//w:authentication", ns).text, "WPA3SAE")
        self.assertEqual(root_open.find(".//w:authentication", ns).text, "open")


class TestControlCenterOverlayLayoutAndDPI(unittest.TestCase):
    def test_logical_geometry_no_dpi_double_scaling(self):
        overlay = ControlCenterOverlay()
        screen = _APP.primaryScreen()
        avail_h = screen.availableGeometry().height() if screen else 1032
        self.assertEqual(overlay.width(), ControlCenterOverlay.PANEL_W)
        self.assertLessEqual(overlay.height(), ControlCenterOverlay.PANEL_H)
        self.assertLessEqual(overlay.height(), avail_h)
        overlay.close()

    def test_grid_symmetry_and_footer_clearance(self):
        overlay = ControlCenterOverlay()
        overlay.resize(overlay.PANEL_W, overlay.PANEL_H)

        # Simetria esquerda == direita (24px)
        left_card = overlay._rect_toggle(0)
        right_card = overlay._rect_toggle(1)
        self.assertAlmostEqual(left_card.left(), 24.0, places=2)
        self.assertAlmostEqual(overlay.width() - right_card.right(), 24.0, places=2)

        # Nenhum card de Wi-Fi ou Áudio pode invadir o rodapé
        overlay.wifi_networks = [
            {"ssid": f"Net_{i}", "signal": 80, "bars": 4, "security": "WPA2-Personal", "is_secure": True, "is_connected": (i == 0)}
            for i in range(10)
        ]
        overlay.selected_ssid = "Net_1"
        footer = overlay._rect_footer_btn()
        for _, rect in overlay._get_wifi_card_rects():
            self.assertLess(rect.bottom(), footer.top())

        overlay.audio_devices = [
            {"id": f"id_{i}", "name": f"Device {i}", "is_default": (i == 0), "icon_type": "speaker"}
            for i in range(10)
        ]
        for _, rect in overlay._get_audio_device_rects():
            self.assertLess(rect.bottom(), footer.top())
        overlay.close()

    def test_audio_flyout_renders_without_cjk_fallback_in_close_icon(self):
        import inspect
        src = inspect.getsource(ControlCenterOverlay._paint_audio_flyout)
        self.assertIn("_draw_round_icon_btn", src)
        overlay = ControlCenterOverlay()
        overlay.current_view = 2
        overlay.resize(overlay.PANEL_W, overlay.PANEL_H)
        overlay.show()
        _APP.processEvents()
        pix = overlay.grab()
        self.assertFalse(pix.isNull())
        overlay.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
