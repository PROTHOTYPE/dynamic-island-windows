"""
Testes Dependentes de Hardware — Etapa de Estabilização e Portabilidade
Executa em desktop (sem Wi-Fi/BT/Bateria) e notebook (com hardware completo).
Recursos físicos ausentes são reportados como [SKIP] com justificativa, nunca como falha.
"""

import os
import sys
import time
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from PyQt6.QtCore import QCoreApplication
from core.radio_adapter import RadioAdapter
from core.wifi_manager import WiFiManager
from core.audio_adapter import AudioEndpointAdapter
from core.system_controls import SystemControlsAdapter

_APP = QCoreApplication.instance() or QCoreApplication(sys.argv)


class TestPortableHardwareAdapters(unittest.TestCase):
    def test_radio_adapter_hardware(self):
        radio = RadioAdapter()
        try:
            time.sleep(0.8)
            _APP.processEvents()
            radios = radio.get_cached_radios()
            if not radios:
                self.skipTest("Nenhum rádio Wi-Fi/Bluetooth físico presente neste computador.")
            self.assertTrue(isinstance(radios, dict))
        finally:
            radio.shutdown()

    def test_wifi_manager_hardware(self):
        wifi = WiFiManager()
        wifi.start_scan()
        for _ in range(25):
            time.sleep(0.1)
            _APP.processEvents()
            if wifi.is_wifi_available() or wifi.get_cached_networks():
                break
        if not wifi.is_wifi_available():
            self.skipTest("Interface Wi-Fi física ausente neste computador.")
        self.assertIsInstance(wifi.get_cached_networks(), list)

    def test_audio_endpoint_adapter_hardware(self):
        audio = AudioEndpointAdapter()
        for _ in range(20):
            time.sleep(0.1)
            _APP.processEvents()
            if audio.get_cached_devices():
                break
        devs = audio.get_cached_devices()
        if not devs:
            self.skipTest("Nenhum endpoint de saída de áudio ativo encontrado nesta sessão.")
        orig_vol = audio.get_cached_volume()
        audio.set_volume(orig_vol)
        _APP.processEvents()
        self.assertGreaterEqual(len(devs), 1)

    def test_system_controls_hardware(self):
        sc = SystemControlsAdapter()
        time.sleep(0.6)
        _APP.processEvents()
        st = sc.get_state()
        self.assertIn("has_battery", st)
        self.assertIn("brightness_supported", st)
        if not st["has_battery"]:
            print("\n  [INFO] Sem bateria (Desktop AC) — Battery Saver corretamente marcado como indisponível.")
        if not st["brightness_supported"]:
            print("\n  [INFO] Controle de brilho DDC/CI ou WMI indisponível neste monitor.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
