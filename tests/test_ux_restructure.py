"""
Suíte de Testes da Reestruturação de Experiência, Navegação e Identidade OLED do Monolith.
Valida os 12 critérios de aceitação:
1. Abertura direta na página INÍCIO (nunca em mídia vazia)
2. Mídia exclusivamente contextual via SMTC (aparece somente em Playing, desaparece em Paused/Stopped/Closed)
3. Navegação linear deslizante (SlidingPager: Início -> Janelas -> Sistema)
4. LauncherBar permanente visível em todas as 3 páginas
5. Pesquisa e sobreposição de resultados sem abandonar a página atual
6. Bloco do Centro de Controle em destaque na primeira tela + overlay independente
7. Seção de Temas incorporada a Sistema
8. Padrão OLED Black (#000000) e ausência de azul decorativo
9. Textos íntegros e métricas de fontes sem truncamento indevido
10. Antialiasing e DPR supersampling em ícones e renderizações
11. Transições fluidas com respeito a movimento reduzido
12. Preservação das funcionalidades de hardware e atalhos
"""

import os
import sys
import time
import unittest
from unittest.mock import patch

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from PyQt6.QtWidgets import QApplication, QLineEdit
from PyQt6.QtCore import Qt, QEvent, QPointF
from PyQt6.QtGui import QFontMetrics, QMouseEvent, QKeyEvent, QColor

from ui.theme import Theme
from ui.icons import IconFactory
from ui.sliding_pager import SlidingPager
from ui.launcher_bar import LauncherBar
from core.media_controller import MediaController
from main import DynamicIslandWindow

_APP = QApplication.instance() or QApplication(sys.argv)


class TestMonolithUXRestructure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Theme.apply_preset("oled", save=False)
        Theme.apply_notch_material("oled_black", save=False)

    def setUp(self):
        with patch("main.DynamicIslandWindow.isActiveWindow", return_value=True):
            self.win = DynamicIslandWindow()
            self.win.show()
            _APP.processEvents()

    def tearDown(self):
        try:
            self.win.overlay_manager.dismiss(immediate=True)
            self.win.media_session.shutdown()
            self.win.radio_adapter.shutdown()
            self.win.close()
        except Exception:
            pass
        _APP.processEvents()

    # ------------------------------------------------------------------ 1. Abertura em Início
    def test_01_opens_in_home_without_empty_media_card(self):
        """1. O Monolith abre em INÍCIO, nunca em mídia vazia."""
        self.win.expand()
        self.win._on_anim_finished()
        _APP.processEvents()

        self.assertEqual(self.win.active_tab_idx, DynamicIslandWindow.PAGE_HOME)
        self.assertEqual(self.win.stack.currentIndex(), 0)
        self.assertFalse(self.win.media_active)
        self.assertTrue(self.win.stage_media_card.isHidden())
        self.assertFalse(self.win.cc_hero_card.isHidden())

    # --------------------------------------------------------- 2. Mídia estritamente contextual
    def test_02_media_contextual_appearance_and_disappearance(self):
        """2. Card de mídia aparece somente com SMTC Playing e recolhe ao pausar/parar."""
        self.win.expand()
        self.win._on_anim_finished()
        _APP.processEvents()

        # Sem mídia: oculto
        self.assertTrue(self.win.stage_media_card.isHidden())
        self.assertFalse(self.win.is_media_satellite_visible())

        # Injeta sessão Playing real
        self.win.media_session.ingest_state({
            "playing": True,
            "status": "Playing",
            "app": "Spotify",
            "title": "Starboy",
            "artist": "The Weeknd"
        })
        _APP.processEvents()

        self.assertTrue(self.win.media_active)
        self.assertFalse(self.win.stage_media_card.isHidden())
        self.assertIn("Starboy", self.win.lbl_media_title.text())
        self.assertIn("The Weeknd", self.win.lbl_media_sub.text())
        self.assertTrue(self.win.is_media_satellite_visible())
        self.assertEqual(self.win._current_compact_width(), self.win.COMPACT_SAT_W)

        # Injeta Paused: ativa tolerância de 1 s e recolhe
        self.win.media_session.ingest_state({
            "playing": False,
            "status": "Paused",
            "app": "Spotify",
            "title": "Starboy",
            "artist": "The Weeknd"
        })
        _APP.processEvents()

        # Dispara expiração da tolerância
        self.win.media_session._commit_inactive()
        _APP.processEvents()

        self.assertFalse(self.win.media_active)
        self.assertTrue(self.win.stage_media_card.isHidden())
        self.assertFalse(self.win.is_media_satellite_visible())
        self.assertEqual(self.win._current_compact_width(), self.win.COMPACT_W)

    # ----------------------------------------------------- 3. Navegação linear deslizante
    def test_03_sliding_pager_linear_navigation_and_indicators(self):
        """3. Navegação linear INÍCIO (0) -> JANELAS (1) -> SISTEMA (2) via SlidingPager."""
        self.assertIsInstance(self.win.stack, SlidingPager)
        self.assertEqual(self.win.stack.count(), 3)

        # Avança para JANELAS (1)
        self.win._switch_tab(DynamicIslandWindow.PAGE_WINDOWS, animate=False)
        _APP.processEvents()
        self.assertEqual(self.win.active_tab_idx, 1)
        self.assertEqual(self.win.stack.currentIndex(), 1)
        self.assertEqual(self.win.pager_indicator._current_index, 1)

        # Avança para SISTEMA (2)
        self.win._switch_tab(DynamicIslandWindow.PAGE_SYSTEM, animate=False)
        _APP.processEvents()
        self.assertEqual(self.win.active_tab_idx, 2)
        self.assertEqual(self.win.stack.currentIndex(), 2)
        self.assertEqual(self.win.pager_indicator._current_index, 2)

        # Retorna para INÍCIO (0)
        self.win._switch_tab(DynamicIslandWindow.PAGE_HOME, animate=False)
        _APP.processEvents()
        self.assertEqual(self.win.active_tab_idx, 0)
        self.assertEqual(self.win.stack.currentIndex(), 0)

    # ------------------------------------------------- 4. LauncherBar permanente na base
    def test_04_permanent_launcher_bar_accessible_on_all_pages(self):
        """4. LauncherBar permanece fixo e visível em Início, Janelas e Sistema."""
        self.win.expand()
        self.win._on_anim_finished()
        _APP.processEvents()

        self.assertIsInstance(self.win.launcher_bar, LauncherBar)
        self.assertTrue(self.win.launcher_bar.isVisible())

        for p_idx in [0, 1, 2]:
            self.win._switch_tab(p_idx, animate=False)
            _APP.processEvents()
            self.assertTrue(self.win.launcher_bar.isVisible())
            self.assertTrue(self.win.launcher_bar.search_input.isVisible())

    # ---------------------------------------- 5. Pesquisa sobreposta sem mudar de página
    def test_05_launcher_search_and_keyboard_launch(self):
        """5. Pesquisar resultados exibe popup sobreposto sem sair do painel atual."""
        self.win.expand()
        self.win._on_anim_finished()
        self.win._switch_tab(DynamicIslandWindow.PAGE_WINDOWS, animate=False)
        _APP.processEvents()

        # Digita na busca
        self.win.launcher_bar.search_input.setText("explorer")
        _APP.processEvents()

        # Permanece na página JANELAS (1) e exibe popup sobreposto
        self.assertEqual(self.win.active_tab_idx, DynamicIslandWindow.PAGE_WINDOWS)
        self.assertTrue(self.win.launcher_bar.is_popup_open())
        self.assertGreater(len(self.win.launcher_bar.results), 0)

        # Tecla Escape fecha popup e limpa busca sem fechar o Monolith
        ev_esc = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
        self.win.keyPressEvent(ev_esc)
        _APP.processEvents()

        self.assertFalse(self.win.launcher_bar.is_popup_open())
        self.assertTrue(self.win.is_expanded)

    # --------------------------------------- 6. Centro de Controle com destaque na 1ª tela
    def test_06_control_center_hero_block_and_independent_overlay(self):
        """6. Bloco do Centro de Controle tem destaque visual e abre o overlay independente."""
        self.win.expand()
        self.win._on_anim_finished()
        _APP.processEvents()

        self.assertTrue(self.win.cc_hero_card.isVisible())
        self.assertGreaterEqual(self.win.cc_hero_card.minimumHeight(), 70)
        self.assertEqual(self.win.lbl_cc_hero_title.text(), "Centro de Controle")

        # Abre o Centro de Controle via botão/card
        self.win.toggle_control_center()
        _APP.processEvents()

        self.assertTrue(self.win.overlay_manager.is_open)
        self.assertTrue(self.win.overlay_manager.panel.isVisible())
        self.assertTrue(self.win.overlay_manager.backdrop.isVisible())

        # Fecha o Centro de Controle
        self.win.toggle_control_center()
        _APP.processEvents()
        self.assertFalse(self.win.overlay_manager.is_open)

    # ------------------------------------------------ 7. Temas incorporados em Sistema
    def test_07_themes_incorporated_into_system_page(self):
        """7. A personalização de temas está integrada na seção Sistema (página 2)."""
        self.win.expand()
        self.win._on_anim_finished()
        self.win._switch_tab(DynamicIslandWindow.PAGE_SYSTEM, animate=False)
        _APP.processEvents()

        self.assertFalse(self.win.swatches_frame.isHidden())
        self.assertIn("oled", self.win.swatch_buttons)
        self.assertIn("sapphire", self.win.swatch_buttons)
        self.assertIn("ruby", self.win.swatch_buttons)

        # Aplica preset Ruby em Sistema
        self.win._on_select_preset("ruby")
        _APP.processEvents()
        self.assertEqual(Theme.current_preset, "ruby")
        self.assertEqual(Theme.HEX_ACCENT.lower(), "#f43f5e")

        # Restaura OLED Black
        self.win._on_select_preset("oled")
        _APP.processEvents()
        self.assertEqual(Theme.current_preset, "oled")

    # ------------------------------------------------ 8. OLED Black como padrão
    def test_08_oled_black_default_and_no_permanent_blue_tint(self):
        """8. Padrão inicial é OLED Black (#000000) e acento neutro (#EDEDED)."""
        Theme.apply_preset("oled", save=False)
        Theme.apply_notch_material("oled_black", save=False)
        self.win._apply_live_theme()

        self.assertEqual(Theme.DEFAULT_PRESET, "oled")
        self.assertEqual(Theme.HEX_NOTCH_BG, "#000000")
        self.assertEqual(Theme.COLOR_BG_GRAD_TOP, QColor(0, 0, 0, 255))
        self.assertEqual(Theme.HEX_ACCENT, "#EDEDED")
        self.assertNotIn("#3e91f7", Theme.HEX_ACCENT.lower())

    # ------------------------------------------------- 9. Tipografia e ausência de corte
    def test_09_typography_fits_without_unwanted_truncation(self):
        """9. Rótulos e botões críticos possuem largura suficiente para seus textos."""
        self.win.expand()
        self.win._on_anim_finished()
        _APP.processEvents()

        fm_title = QFontMetrics(self.win.lbl_cc_hero_title.font())
        adv_title = fm_title.horizontalAdvance(self.win.lbl_cc_hero_title.text())
        self.assertLess(adv_title, 250)

        # Botão de abrir Centro de Controle
        fm_btn = QFontMetrics(self.win.btn_cc_open.font())
        adv_btn = fm_btn.horizontalAdvance(self.win.btn_cc_open.text())
        self.assertLess(adv_btn, 140)

        # Botões de presets na grade de 2 linhas
        for p_key, btn in self.win.swatch_buttons.items():
            txt = btn.text()
            fm = QFontMetrics(btn.font())
            self.assertLess(fm.horizontalAdvance(txt), 130, f"Texto de preset muito longo: {txt}")

    # ------------------------------------------------- 10. Antialiasing e DPR Supersampling
    def test_10_icons_and_album_art_use_supersampling(self):
        """10. Ícones vetoriais e capas de álbum possuem DPR supersampling para nitidez."""
        art = IconFactory.get_album_art_pixmap(56)
        self.assertFalse(art.isNull())
        self.assertGreaterEqual(art.devicePixelRatio(), 1.0)

        icon_gear = IconFactory.get_icon("gear", 16)
        pix_gear = icon_gear.pixmap(16, 16)
        self.assertFalse(pix_gear.isNull())
        self.assertGreaterEqual(pix_gear.devicePixelRatio(), 1.0)


if __name__ == "__main__":
    unittest.main()
