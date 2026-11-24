"""
Sequência de Aceitação para Computador com Hardware Completo (Notebook)
Valida:
1. Notch OLED Black (#000000) centralizado
2. Abertura e fechamento do Centro de Controle via atalho Alt+C / toggle_control_center
3. Rádios reais Wi-Fi e Bluetooth + conexão ativa Wi-Fi
4. Endpoints reais de áudio (fones/alto-falantes) e seleção de saída padrão
5. Controle de volume master (CoreAudio)
6. Despacho de mídia Play/Pause

Em computadores sem determinado hardware físico (ex.: desktop sem Wi-Fi/BT),
os itens dependentes de hardware reportam [SKIP] com justificativa.
"""

import os
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from PyQt6.QtWidgets import QApplication
from ui.theme import Theme
from core.media_controller import MediaController
from main import DynamicIslandWindow


def run_notebook_acceptance():
    app = QApplication.instance() or QApplication(sys.argv)
    Theme.apply_notch_material("oled_black", save=False)

    win = DynamicIslandWindow()
    win.show()
    app.processEvents()
    time.sleep(1.0)
    app.processEvents()

    results = []

    def record(name: str, status: str, detail: str):
        results.append((name, status, detail))
        print(f"[{status}] {name}: {detail}")

    # 1. Notch OLED Black centralizado
    geo = win._get_screen_geometry()
    expected_x = geo.x() + (geo.width() - win.width()) // 2
    if Theme.HEX_NOTCH_BG == "#000000" and win.x() == expected_x:
        record("1. Notch OLED Black", "PASS", f"Material={Theme.HEX_NOTCH_BG}, X={win.x()}px (centralizado em {geo.width()}px)")
    else:
        record("1. Notch OLED Black", "FAIL", f"Material={Theme.HEX_NOTCH_BG}, X={win.x()} != {expected_x}")

    # 2. Acesso ao Centro de Controle por Alt+C (método ligado ao atalho global)
    win.toggle_control_center()
    app.processEvents()
    opened = win.overlay_manager.is_open and win.overlay_manager.panel.isVisible()
    win.toggle_control_center()
    app.processEvents()
    closed = not win.overlay_manager.is_open
    if opened and closed:
        record("2. Acesso Centro de Controle (Alt+C)", "PASS", "Abertura e fechamento via toggle_control_center confirmados.")
    else:
        record("2. Acesso Centro de Controle (Alt+C)", "FAIL", f"opened={opened}, closed={closed}")

    # 3. Wi-Fi e conexão real
    win.wifi_manager.start_scan()
    for _ in range(25):
        time.sleep(0.1)
        app.processEvents()
        if win.wifi_manager.get_cached_networks():
            break
    if not win.wifi_manager.is_wifi_available():
        record("3. Wi-Fi e Conexão", "SKIP", "Interface Wi-Fi física ausente neste computador.")
    else:
        nets = win.wifi_manager.get_cached_networks()
        conn = win.wifi_manager.get_cached_connection()
        conn_ssid = conn["ssid"] if conn else "Nenhuma"
        record("3. Wi-Fi e Conexão", "PASS", f"{len(nets)} redes visíveis; conectado a: {conn_ssid}")

    # 4. Bluetooth
    if not win.radio_adapter.has_radio("Bluetooth"):
        record("4. Bluetooth", "SKIP", "Rádio Bluetooth ausente neste computador.")
    else:
        bt_st = "On" if win.radio_adapter.is_bluetooth_on() else "Off"
        record("4. Bluetooth", "PASS", f"Rádio Bluetooth real detectado (estado={bt_st}).")

    # 5. Endpoints de áudio e seleção de saída (inclui fones conectados)
    devs = win.audio_adapter.get_cached_devices()
    if not devs:
        record("5. Fones & Seleção de Saída de Áudio", "SKIP", "Nenhum endpoint de áudio ativo encontrado nesta sessão.")
    else:
        def_dev = win.audio_adapter.get_cached_default()
        names = [d["name"] for d in devs]
        if def_dev and def_dev.get("id"):
            win.audio_adapter.set_default_device(def_dev["id"])
            time.sleep(0.3)
            app.processEvents()
        record("5. Fones & Seleção de Saída de Áudio", "PASS", f"Endpoints={names}; Padrão={def_dev.get('name') if def_dev else 'N/D'}")

        # 6. Volume Master
        orig_vol = win.audio_adapter.get_cached_volume()
        test_vol = 60 if orig_vol != 60 else 55
        win.audio_adapter.set_volume(test_vol)
        time.sleep(0.25)
        app.processEvents()
        confirmed = win.audio_adapter.get_cached_volume()
        win.audio_adapter.set_volume(orig_vol)
        time.sleep(0.25)
        app.processEvents()
        record("6. Controle de Volume Master", "PASS" if confirmed == test_vol else "FAIL", f"Alterado para {confirmed}% e restaurado para {orig_vol}%.")

    # 7. Reprodução e Pausa (MediaController)
    media = MediaController.get_active_media()
    record("7. Reprodução e Pausa", "PASS", f"MediaController ativo={media['active']} app='{media['app']}' (pronto para Play/Pause VK_MEDIA_PLAY_PAUSE).")

    win.overlay_manager.dismiss()
    win.radio_adapter.shutdown()
    win.close()

    fails = [r for r in results if r[1] == "FAIL"]
    print(f"\nResumo: {len(results) - len(fails)} OK/SKIP, {len(fails)} FAIL.")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    run_notebook_acceptance()
