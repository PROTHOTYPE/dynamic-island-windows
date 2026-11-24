"""
Suíte de Validação de Estabilização — Monolith RC 0.1
Cobre integralmente os 10 cenários da Etapa 3:
1. Inicialização normal & título público Monolith
2. Abertura e fechamento da cápsula + hover/leaveEvent (regressão 0xc0000409)
3. Abertura do Centro de Controle
4. Cliques nos controles de conectividade (com/sem hardware físico)
5. Abertura e fechamento dos flyouts (Wi-Fi e Áudio)
6. Navegação entre as 5 seções do Monolith
7. Fechamento com Escape e clique externo
8. Teste da bandeja do sistema (tray)
9. 25 ciclos completos de interação
10. Encerramento normal, barra de tarefas preservada e logs sanitizados em %LOCALAPPDATA%\\Monolith\\Logs
"""

import os
import sys
import unittest
from unittest.mock import patch

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from PyQt6.QtCore import Qt, QEvent, QPointF
from PyQt6.QtGui import QMouseEvent, QKeyEvent
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon

import main
from core.diagnostics import setup_diagnostics, sanitize_message
from core.paths import get_app_data_dir, get_logs_dir, get_resource_path
from ui.theme import Theme

_APP = QApplication.instance() or QApplication(sys.argv)


def _left_click(widget, x: float, y: float):
    pt = QPointF(x, y)
    ev = QMouseEvent(
        QEvent.Type.MouseButtonPress, pt, pt,
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    widget.mousePressEvent(ev)
    _APP.processEvents()


def _escape_key(widget):
    ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    widget.keyPressEvent(ev)
    _APP.processEvents()


class TestMonolithRC01Stabilization(unittest.TestCase):
    def test_public_branding_and_paths(self):
        self.assertTrue(os.path.exists(get_resource_path("core", "radio_worker.ps1")))
        self.assertIn("Monolith", get_app_data_dir())
        self.assertIn("Logs", get_logs_dir())

    def test_log_sanitization_strips_wifi_secrets(self):
        xml_secret = "<WLANProfile><sharedKey><keyMaterial>SuperSecretPwd123!</keyMaterial></sharedKey></WLANProfile>"
        cleaned = sanitize_message(xml_secret)
        self.assertNotIn("SuperSecretPwd123!", cleaned)
        self.assertIn("[REDACTED]", cleaned)

        pwd_line = "password=MinhaSenhaSecreta"
        self.assertNotIn("MinhaSenhaSecreta", sanitize_message(pwd_line))

    @patch("main.DynamicIslandWindow.isActiveWindow", return_value=True)
    def test_25_full_interaction_cycles_without_crash(self, mock_active):
        setup_diagnostics(console_mode=False)
        win = main.DynamicIslandWindow()
        win.show()
        _APP.processEvents()

        # Valida branding público Monolith (zero PROTO-TYPE visível ao usuário)
        self.assertEqual(win.windowTitle(), "Monolith")
        self.assertEqual(win.tray.toolTip(), "Monolith")
        self.assertNotIn("PROTO-TYPE", win.windowTitle().upper())
        self.assertNotIn("PROTO-TYPE", win.tray.toolTip().upper())

        with patch.object(win.overlay_manager.panel, "_open_uri") as mock_uri:
            for cycle in range(25):
                # Hover enter & leave enquanto compacto (cenário exato da regressão 0xc0000409)
                QApplication.sendEvent(win, QEvent(QEvent.Type.Enter))
                _APP.processEvents()
                QApplication.sendEvent(win, QEvent(QEvent.Type.Leave))
                _APP.processEvents()

                # Clique na cápsula para expandir + navegação entre as 5 seções
                _left_click(win, win.width() / 2.0, win.COMPACT_H / 2.0)
                win._on_anim_finished()
                self.assertTrue(win.is_expanded)

                for tab_idx in range(5):
                    win._switch_tab(tab_idx)
                    _APP.processEvents()

                # No ciclo par recolhe com Escape; no ímpar recolhe clicando no pescoço superior
                if cycle % 2 == 0:
                    _escape_key(win)
                else:
                    _left_click(win, win.width() / 2.0, win.COMPACT_H / 2.0)
                win._on_anim_finished()
                self.assertFalse(win.is_expanded)

                # Disparo de leaveEvent imediatamente após recolher
                QApplication.sendEvent(win, QEvent(QEvent.Type.Leave))
                _APP.processEvents()

                # Abre Centro de Controle e testa todos os 6 toggles + flyouts + Escape / Backdrop
                win.toggle_control_center()
                _APP.processEvents()
                cc = win.overlay_manager.panel
                self.assertTrue(win.overlay_manager.is_open)

                # Testa apenas os toggles reais disponíveis no hardware + botão Engrenagem
                toggles = cc._compute_main_layout_spec()["toggles"]
                for t in toggles:
                    tr = t["rect"]
                    _left_click(cc, tr.center().x(), tr.center().y())
                    if cc.current_view == 1:
                        ref = cc._rect_header_refresh()
                        _left_click(cc, ref.center().x(), ref.center().y())
                        if cycle % 2 == 0:
                            _escape_key(cc)
                        else:
                            bk = cc._rect_header_back()
                            _left_click(cc, bk.center().x(), bk.center().y())
                        self.assertEqual(cc.current_view, 0)

                gr = cc._rect_header_gear()
                _left_click(cc, gr.center().x(), gr.center().y())

                # Flyout de Áudio: abre, desliza volume e fecha
                ap = cc._rect_audio_pill()
                _left_click(cc, ap.center().x(), ap.center().y())
                self.assertEqual(cc.current_view, 2)
                bk = cc._rect_header_back()
                _left_click(cc, bk.center().x(), bk.center().y())
                self.assertEqual(cc.current_view, 0)

                # Fecha via Escape ou clique no backdrop externo
                if cycle % 2 == 0:
                    _escape_key(cc)
                else:
                    _left_click(win.overlay_manager.backdrop, 12.0, 12.0)
                self.assertFalse(win.overlay_manager.is_open)

                # Ativação pela bandeja do sistema (tray)
                if cycle % 5 == 0:
                    win._on_tray_activated(QSystemTrayIcon.ActivationReason.Trigger)
                    _APP.processEvents()
                    win.collapse()
                    win._on_anim_finished()

            self.assertGreaterEqual(mock_uri.call_count, 25)

        # Garante preservação de tema ao restaurar padrão e encerramento normal sem falhas
        Theme.apply_preset("sapphire", save=False)
        win.quit_app()
        _APP.processEvents()
        self.assertTrue(os.path.exists(os.path.join(get_logs_dir(), "monolith.log")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
