import os
import json
from PyQt6.QtGui import QColor, QFont

from core.paths import get_app_data_dir, get_config_file

CONFIG_DIR = get_app_data_dir()
CONFIG_FILE = get_config_file()


class Theme:
    """
    Design System Autoral — Monolith
    Centraliza superfícies Grafite/Safira escuras imutáveis, geometria Monolith,
    motor de recálculo perceptual de contraste/hover/seleção e persistência local em %LOCALAPPDATA%\\Monolith.
    """

    # --- PRESETS OFICIAIS DE DESTAQUE ---
    # "oled" é o padrão: acento neutro (branco suave) usado apenas para estado ativo/seleção.
    PRESETS = {
        "oled":     {"name": "OLED Black",    "hex": "#EDEDED"},
        "sapphire": {"name": "Azul Sapphire", "hex": "#3E91F7"},
        "violet":   {"name": "Violeta",       "hex": "#8B5CF6"},
        "cyan":     {"name": "Ciano",         "hex": "#06B6D4"},
        "emerald":  {"name": "Esmeralda",     "hex": "#10B981"},
        "amber":    {"name": "Âmbar",         "hex": "#F59E0B"},
        "ruby":     {"name": "Rubi",          "hex": "#F43F5E"},
    }
    DEFAULT_PRESET = "oled"
    THEME_SCHEMA_VERSION = 2

    # --- MATERIAIS OLED STEALTH PARA O CORPO DO NOTCH ---
    NOTCH_MATERIALS = {
        "oled_black": {
            "name": "OLED Black",
            "hex": "#000000",
            "bg": QColor(0, 0, 0, 255),
            "border_idle": QColor(0, 0, 0, 255),
            "border_hover": QColor(255, 255, 255, 24),
        },
        "obsidian_graphite": {
            "name": "Obsidian Graphite",
            "hex": "#101116",
            "bg": QColor(16, 17, 22, 250),
            "border_idle": QColor(255, 255, 255, 14),
            "border_hover": QColor(255, 255, 255, 32),
        },
    }

    # --- ESTADO DE PERSONALIZAÇÃO PERSISTIDO ---
    current_preset: str = "oled"
    custom_hex: str = "#EDEDED"
    satellite_enabled: bool = True
    notch_material: str = "oled_black"

    # --- SUPERFÍCIES DO NOTCH (OLED Stealth — Sem Borda ou Halo Permanente) ---
    COLOR_NOTCH_BG = QColor(0, 0, 0, 255)
    COLOR_NOTCH_BORDER_IDLE = QColor(0, 0, 0, 255)
    COLOR_NOTCH_BORDER_HOVER = QColor(255, 255, 255, 24)
    HEX_NOTCH_BG = "#000000"

    # --- SUPERFÍCIES FIXAS OLED (preto absoluto + grafites neutros, sem matiz azul) ---
    COLOR_BG_GRAD_TOP = QColor(0, 0, 0, 255)
    COLOR_BG_GRAD_MID = QColor(0, 0, 0, 255)
    COLOR_BG_GRAD_BOTTOM = QColor(0, 0, 0, 255)

    COLOR_BORDER_SUBTLE = QColor(255, 255, 255, 18)
    COLOR_BORDER_HOVER = QColor(255, 255, 255, 40)

    HEX_BG_CARD = "rgba(255, 255, 255, 0.045)"
    HEX_BG_CARD_HOVER = "rgba(255, 255, 255, 0.075)"
    HEX_BG_INPUT = "rgba(255, 255, 255, 0.055)"
    HEX_BG_INPUT_FOCUS = "rgba(255, 255, 255, 0.085)"
    HEX_BG_ELEVATED = "#121212"

    HEX_TEXT_PRIMARY = "#F2F2F2"
    HEX_TEXT_SECONDARY = "#A3A3A3"
    HEX_TEXT_MUTED = "#6E6E6E"
    HEX_BORDER = "rgba(255, 255, 255, 0.07)"

    HEX_STATUS_IDLE = "#10B981"
    HEX_STATUS_MEDIA = "#06B6D4"
    HEX_STATUS_ALERT = "#F59E0B"
    HEX_STATUS_DANGER = "rgba(244, 63, 94, 0.20)"
    HEX_STATUS_DANGER_TEXT = "#FDA4AF"
    HEX_STATUS_DANGER_BORDER = "rgba(244, 63, 94, 0.38)"

    # --- TOKENS DINÂMICOS DE DESTAQUE (Recalculados por Luminância/HSL) ---
    COLOR_ACCENT = QColor("#3E91F7")
    COLOR_ACCENT_HOVER = QColor("#5CA3FA")
    COLOR_ACCENT_SECONDARY = QColor("#1D4ED8")
    COLOR_ACCENT_LIGHT = QColor("#93C5FD")
    COLOR_ACCENT_GLOW = QColor(62, 145, 247, 90)
    COLOR_BORDER_FOCUS = QColor(62, 145, 247, 150)
    COLOR_TEXT_ON_ACCENT = QColor("#FFFFFF")
    COLOR_ACCENT_SOFT_FILL = QColor(62, 145, 247, 56)

    HEX_ACCENT = "#3E91F7"
    HEX_ACCENT_HOVER_SOLID = "#5CA3FA"
    HEX_ACCENT_SECONDARY = "#1D4ED8"
    HEX_ACCENT_LIGHT = "#93C5FD"
    HEX_TEXT_ON_ACCENT = "#FFFFFF"
    HEX_ACCENT_MUTED = "rgba(62, 145, 247, 0.20)"
    HEX_ACCENT_HOVER = "rgba(62, 145, 247, 0.32)"
    HEX_ACCENT_BORDER = "rgba(62, 145, 247, 0.48)"
    HEX_ACCENT_BORDER_HOVER = "rgba(92, 163, 250, 0.88)"

    # --- GEOMETRIA MONOLITH FUSION (Conceito B Refinado: 190x30) ---
    TOP_MARGIN = 0
    COMPACT_W = 190
    COMPACT_SAT_W = 340      # Expansão horizontal contextual com mídia ativa
    COMPACT_H = 30
    EXPANDED_W = 540
    EXPANDED_H = 396

    RADIUS_PILL = 14.0
    RADIUS_PANEL = 22.0
    RADIUS_CARD = 14.0
    RADIUS_BUTTON = 11.0
    RADIUS_INPUT = 12.0
    RADIUS_TAB = 10.0

    # --- TIPOGRAFIA ---
    FONT_FAMILY = "Segoe UI Variable Text"
    FONT_FAMILY_FALLBACK = "Segoe UI"

    @classmethod
    def get_font(cls, size_pt: float, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
        font = QFont(cls.FONT_FAMILY)
        font.setPointSizeF(float(size_pt))
        font.setWeight(weight)
        font.setStyleHint(QFont.StyleHint.SansSerif)
        return font

    @staticmethod
    def reduced_motion_enabled() -> bool:
        """Respeita a preferência nativa do Windows para redução de animações."""
        try:
            import ctypes
            from ctypes import wintypes
            SPI_GETCLIENTAREAANIMATION = 0x1042
            enabled = wintypes.BOOL(True)
            if ctypes.windll.user32.SystemParametersInfoW(SPI_GETCLIENTAREAANIMATION, 0, ctypes.byref(enabled), 0):
                return not bool(enabled.value)
        except Exception:
            pass
        return False

    @staticmethod
    def _relative_luminance(c: QColor) -> float:
        """Calcula a luminância relativa WCAG 2.1 para garantir contraste adequado."""
        def ch(v: int) -> float:
            s = v / 255.0
            return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4
        return 0.2126 * ch(c.red()) + 0.7152 * ch(c.green()) + 0.0722 * ch(c.blue())

    @classmethod
    def recalculate_tokens(cls, hex_color: str) -> bool:
        """
        Recalcula todos os estados derivados (hover, active, seleção, borda, brilho e contraste de texto)
        a partir de um código hexadecimal, impedindo perda de contraste em cores muito claras ou escuras.
        """
        clean = hex_color.strip()
        if not clean.startswith("#"):
            clean = "#" + clean
        base = QColor(clean)
        if not base.isValid():
            return False

        h, s, l, _ = base.getHslF()

        # Acento acromático (OLED Black): tokens neutros, sem matiz, baixa opacidade de seleção
        if s < 0.08 or h < 0:
            cls.COLOR_ACCENT = QColor("#EDEDED")
            cls.COLOR_ACCENT_HOVER = QColor("#FFFFFF")
            cls.COLOR_ACCENT_SECONDARY = QColor("#8A8A8A")
            cls.COLOR_ACCENT_LIGHT = QColor("#F5F5F5")
            cls.COLOR_ACCENT_GLOW = QColor(255, 255, 255, 40)
            cls.COLOR_BORDER_FOCUS = QColor(255, 255, 255, 90)
            cls.COLOR_TEXT_ON_ACCENT = QColor("#000000")
            cls.COLOR_ACCENT_SOFT_FILL = QColor(255, 255, 255, 26)
            cls.HEX_ACCENT = "#EDEDED"
            cls.HEX_ACCENT_HOVER_SOLID = "#FFFFFF"
            cls.HEX_ACCENT_SECONDARY = "#8A8A8A"
            cls.HEX_ACCENT_LIGHT = "#F5F5F5"
            cls.HEX_TEXT_ON_ACCENT = "#000000"
            cls.HEX_ACCENT_MUTED = "rgba(255, 255, 255, 0.10)"
            cls.HEX_ACCENT_HOVER = "rgba(255, 255, 255, 0.16)"
            cls.HEX_ACCENT_BORDER = "rgba(255, 255, 255, 0.22)"
            cls.HEX_ACCENT_BORDER_HOVER = "rgba(255, 255, 255, 0.40)"
            return True
        # Garante faixa segura de luminosidade em HSL para nunca apagar em fundo grafite
        safe_l = max(0.32, min(0.72, l))
        safe_s = max(0.35, s) if h >= 0 else s
        accent = QColor.fromHslF(h if h >= 0 else 0.6, safe_s, safe_l)

        # Estado Hover: elevação luminosa perceptualmente calibrada
        hover_l = min(0.82, safe_l + 0.10)
        hover_s = min(1.0, safe_s + 0.06)
        hover_col = QColor.fromHslF(h if h >= 0 else 0.6, hover_s, hover_l)

        # Estado Secundário / Pressed (para gradientes esculturais)
        sec_l = max(0.20, safe_l - 0.16)
        sec_col = QColor.fromHslF(h if h >= 0 else 0.6, safe_s, sec_l)

        # Variante Pastel Clara para textos de destaque sobre fundo escuro (alto contraste garantido)
        light_col = QColor.fromHslF(h if h >= 0 else 0.6, min(1.0, safe_s * 0.90), 0.78)

        # Luminância relativa WCAG para decidir cor de texto/ícone sobre preenchimento sólido
        lum = cls._relative_luminance(accent)
        on_accent = QColor("#060911") if lum > 0.44 else QColor("#FFFFFF")

        # Compensação de opacidade por luminância (cores vibrantes como Âmbar usam alpha menor)
        sel_alpha = 0.16 if lum > 0.35 else 0.22
        hov_alpha = 0.26 if lum > 0.35 else 0.34
        brd_alpha = 0.46 if lum > 0.35 else 0.54

        cls.COLOR_ACCENT = accent
        cls.COLOR_ACCENT_HOVER = hover_col
        cls.COLOR_ACCENT_SECONDARY = sec_col
        cls.COLOR_ACCENT_LIGHT = light_col
        cls.COLOR_ACCENT_GLOW = QColor(accent.red(), accent.green(), accent.blue(), 92)
        cls.COLOR_BORDER_FOCUS = QColor(accent.red(), accent.green(), accent.blue(), 155)
        cls.COLOR_TEXT_ON_ACCENT = on_accent
        cls.COLOR_ACCENT_SOFT_FILL = QColor(accent.red(), accent.green(), accent.blue(), int(round(sel_alpha * 255)))

        cls.HEX_ACCENT = accent.name()
        cls.HEX_ACCENT_HOVER_SOLID = hover_col.name()
        cls.HEX_ACCENT_SECONDARY = sec_col.name()
        cls.HEX_ACCENT_LIGHT = light_col.name()
        cls.HEX_TEXT_ON_ACCENT = on_accent.name()

        r, g, b = accent.red(), accent.green(), accent.blue()
        hr, hg, hb = hover_col.red(), hover_col.green(), hover_col.blue()
        cls.HEX_ACCENT_MUTED = f"rgba({r}, {g}, {b}, {sel_alpha:.2f})"
        cls.HEX_ACCENT_HOVER = f"rgba({r}, {g}, {b}, {hov_alpha:.2f})"
        cls.HEX_ACCENT_BORDER = f"rgba({r}, {g}, {b}, {brd_alpha:.2f})"
        cls.HEX_ACCENT_BORDER_HOVER = f"rgba({hr}, {hg}, {hb}, 0.88)"
        return True

    @classmethod
    def apply_preset(cls, preset_key: str, save: bool = True):
        if preset_key in cls.PRESETS:
            cls.current_preset = preset_key
            cls.custom_hex = cls.PRESETS[preset_key]["hex"]
            cls.recalculate_tokens(cls.custom_hex)
            if save:
                cls.save_preferences()

    @classmethod
    def apply_custom_hex(cls, hex_str: str, save: bool = True) -> bool:
        if cls.recalculate_tokens(hex_str):
            cls.current_preset = "custom"
            cls.custom_hex = cls.HEX_ACCENT.upper()
            # Verifica se coincide com algum preset oficial
            for k, v in cls.PRESETS.items():
                if v["hex"].upper() == cls.custom_hex:
                    cls.current_preset = k
                    break
            if save:
                cls.save_preferences()
            return True
        return False

    @classmethod
    def apply_notch_material(cls, material_key: str, save: bool = True):
        if material_key in cls.NOTCH_MATERIALS:
            mat = cls.NOTCH_MATERIALS[material_key]
            cls.notch_material = material_key
            cls.COLOR_NOTCH_BG = QColor(mat["bg"])
            cls.COLOR_NOTCH_BORDER_IDLE = QColor(mat["border_idle"])
            cls.COLOR_NOTCH_BORDER_HOVER = QColor(mat["border_hover"])
            cls.HEX_NOTCH_BG = mat["hex"]
            if save:
                cls.save_preferences()

    @classmethod
    def load_preferences(cls):
        try:
            cfg_file = get_config_file()
            if os.path.exists(cfg_file):
                with open(cfg_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                cls.satellite_enabled = bool(data.get("satellite_enabled", True))
                mat_key = str(data.get("notch_material", "oled_black"))
                cls.apply_notch_material(mat_key if mat_key in cls.NOTCH_MATERIALS else "oled_black", save=False)

                # Migração única para o esquema v2: OLED Black passa a ser o padrão.
                # A configuração anterior é preservada em appearance.backup-v1.json.
                if int(data.get("theme_version", 1)) < cls.THEME_SCHEMA_VERSION:
                    try:
                        backup = os.path.join(os.path.dirname(cfg_file), "appearance.backup-v1.json")
                        if not os.path.exists(backup):
                            with open(backup, "w", encoding="utf-8") as bf:
                                json.dump(data, bf, indent=2, ensure_ascii=False)
                    except Exception:
                        pass
                    cls.apply_preset(cls.DEFAULT_PRESET, save=False)
                    cls.save_preferences()
                    return

                preset = data.get("preset", cls.DEFAULT_PRESET)
                custom = data.get("custom_hex", cls.PRESETS[cls.DEFAULT_PRESET]["hex"])
                if preset in cls.PRESETS:
                    cls.apply_preset(preset, save=False)
                else:
                    cls.apply_custom_hex(custom, save=False)
            else:
                cls.apply_notch_material("oled_black", save=False)
                cls.apply_preset(cls.DEFAULT_PRESET, save=False)
        except Exception:
            cls.apply_notch_material("oled_black", save=False)
            cls.apply_preset(cls.DEFAULT_PRESET, save=False)

    @classmethod
    def save_preferences(cls):
        try:
            cfg_file = get_config_file()
            os.makedirs(os.path.dirname(cfg_file), exist_ok=True)
            data = {
                "theme_version": cls.THEME_SCHEMA_VERSION,
                "preset": cls.current_preset,
                "custom_hex": cls.custom_hex,
                "satellite_enabled": cls.satellite_enabled,
                "notch_material": cls.notch_material,
            }
            with open(cfg_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    # --- GERADORES DE ESTILOS QSS DINÂMICOS ---

    @classmethod
    def style_card(cls) -> str:
        return (
            f"QFrame {{ background-color: {cls.HEX_BG_CARD}; "
            f"border: 1px solid {cls.HEX_BORDER}; border-radius: {cls.RADIUS_CARD}px; }}"
        )

    @classmethod
    def style_stack_container(cls) -> str:
        return "QStackedWidget { background: transparent; border: none; }"

    @classmethod
    def style_scroll_area(cls) -> str:
        return (
            "QScrollArea { border: none; background: transparent; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
            "QScrollBar:vertical {"
            "    border: none;"
            "    background: rgba(255, 255, 255, 0.02);"
            "    width: 5px;"
            "    margin: 0px;"
            "    border-radius: 2px;"
            "}"
            "QScrollBar::handle:vertical {"
            "    background: rgba(255, 255, 255, 0.16);"
            "    min-height: 24px;"
            "    border-radius: 2px;"
            "}"
            f"QScrollBar::handle:vertical:hover {{ background: {cls.HEX_ACCENT}; }}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { border: none; background: none; height: 0px; }"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }"
        )

    @classmethod
    def style_empty_state_card(cls) -> str:
        return (
            f"QFrame#empty_tasks_card {{ "
            f"  background-color: rgba(20, 20, 20, 195); "
            f"  border: 1px dashed rgba(255, 255, 255, 0.12); "
            f"  border-radius: {cls.RADIUS_CARD}px; "
            f"}}"
        )

    @classmethod
    def style_action_button_accent(cls) -> str:
        return (
            f"QPushButton {{ background-color: {cls.HEX_ACCENT_MUTED}; color: {cls.HEX_ACCENT_LIGHT}; "
            f"border: 1px solid {cls.HEX_ACCENT_BORDER}; border-radius: {cls.RADIUS_BUTTON}px; "
            f"padding: 6px 14px; font-size: 10.5px; font-weight: 600; font-family: '{cls.FONT_FAMILY_FALLBACK}'; }}"
            f"QPushButton:hover {{ background-color: {cls.HEX_ACCENT_HOVER}; color: #ffffff; border: 1px solid {cls.HEX_ACCENT_BORDER_HOVER}; }}"
        )

    @classmethod
    def style_search_input(cls) -> str:
        return (
            f"QLineEdit {{ background-color: {cls.HEX_BG_INPUT}; color: {cls.HEX_TEXT_PRIMARY}; "
            f"border: 1px solid {cls.HEX_ACCENT_BORDER}; border-radius: {cls.RADIUS_INPUT}px; "
            f"padding: 7px 12px 7px 34px; font-size: 12px; font-family: '{cls.FONT_FAMILY_FALLBACK}'; }}"
            f"QLineEdit:hover {{ border: 1px solid {cls.HEX_ACCENT_BORDER_HOVER}; }}"
            f"QLineEdit:focus {{ border: 1.5px solid {cls.HEX_ACCENT}; background-color: {cls.HEX_BG_INPUT_FOCUS}; }}"
        )

    @classmethod
    def style_dock_squircle(cls, is_active: bool) -> str:
        if is_active:
            return (
                f"QPushButton {{ background-color: {cls.HEX_ACCENT_MUTED}; color: {cls.HEX_ACCENT_LIGHT}; "
                f"border: 1px solid {cls.HEX_ACCENT}; border-radius: 12px; "
                f"padding: 4px 6px; font-size: 9.5px; font-weight: 600; font-family: '{cls.FONT_FAMILY_FALLBACK}'; }}"
                f"QPushButton:hover {{ background-color: {cls.HEX_ACCENT_HOVER}; color: #ffffff; border: 1px solid {cls.HEX_ACCENT_BORDER_HOVER}; }}"
            )
        return (
            f"QPushButton {{ background-color: rgba(22, 22, 22, 210); color: {cls.HEX_TEXT_SECONDARY}; "
            f"border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 12px; "
            f"padding: 4px 6px; font-size: 9.5px; font-weight: 500; font-family: '{cls.FONT_FAMILY_FALLBACK}'; }}"
            f"QPushButton:hover {{ background-color: rgba(34, 34, 34, 235); color: {cls.HEX_TEXT_PRIMARY}; "
            f"border: 1px solid {cls.HEX_ACCENT_BORDER}; }}"
        )

    @classmethod
    def style_play_circle_button(cls) -> str:
        return (
            f"QPushButton {{ background-color: {cls.HEX_ACCENT}; color: {cls.HEX_TEXT_ON_ACCENT}; "
            f"border: 1px solid rgba(255, 255, 255, 0.32); border-radius: 21px; }}"
            f"QPushButton:hover {{ background-color: {cls.HEX_ACCENT_HOVER_SOLID}; border: 1px solid rgba(255, 255, 255, 0.60); }}"
        )

    @classmethod
    def style_media_transport_subtle(cls) -> str:
        return (
            f"QPushButton {{ background-color: rgba(29, 29, 29, 175); border: 1px solid rgba(255, 255, 255, 0.08); "
            f"border-radius: 15px; }}"
            f"QPushButton:hover {{ background-color: {cls.HEX_ACCENT_MUTED}; border: 1px solid {cls.HEX_ACCENT_BORDER}; }}"
        )

    @classmethod
    def style_filter_pill(cls, is_active: bool) -> str:
        if is_active:
            return (
                f"QPushButton {{ background-color: {cls.HEX_ACCENT_MUTED}; color: {cls.HEX_TEXT_PRIMARY}; "
                f"border: 1px solid {cls.HEX_ACCENT_BORDER}; border-radius: 7px; padding: 3px 10px; "
                f"font-size: 9.5px; font-weight: 600; font-family: '{cls.FONT_FAMILY_FALLBACK}'; }}"
            )
        return (
            f"QPushButton {{ background-color: rgba(22, 22, 22, 165); color: {cls.HEX_TEXT_MUTED}; "
            f"border: 1px solid rgba(255, 255, 255, 0.06); border-radius: 7px; padding: 3px 10px; "
            f"font-size: 9.5px; font-weight: 500; font-family: '{cls.FONT_FAMILY_FALLBACK}'; }}"
            f"QPushButton:hover {{ background-color: rgba(33, 33, 33, 210); color: {cls.HEX_TEXT_SECONDARY}; "
            f"border: 1px solid {cls.HEX_ACCENT_BORDER}; }}"
        )

    @classmethod
    def style_tab_button(cls, is_active: bool) -> str:
        return cls.style_dock_squircle(is_active)

    @classmethod
    def style_quick_action_button(cls) -> str:
        return cls.style_dock_squircle(False)

    @classmethod
    def style_media_control_button(cls) -> str:
        return cls.style_media_transport_subtle()

    @classmethod
    def style_quit_button(cls) -> str:
        return (
            f"QPushButton {{ background-color: {cls.HEX_STATUS_DANGER}; color: {cls.HEX_STATUS_DANGER_TEXT}; "
            f"border: 1px solid {cls.HEX_STATUS_DANGER_BORDER}; border-radius: 8px; "
            f"padding: 4px 10px; font-size: 9.5px; font-weight: 600; font-family: '{cls.FONT_FAMILY_FALLBACK}'; }}"
            f"QPushButton:hover {{ background-color: rgba(225, 29, 72, 0.42); color: #ffffff; }}"
        )

    @classmethod
    def style_collapse_button(cls) -> str:
        return (
            f"QPushButton {{ background-color: rgba(26, 26, 26, 200); color: {cls.HEX_TEXT_SECONDARY}; "
            f"border: 1px solid {cls.HEX_BORDER}; border-radius: 8px; "
            f"padding: 4px 10px; font-size: 9.5px; font-family: '{cls.FONT_FAMILY_FALLBACK}'; }}"
            f"QPushButton:hover {{ background-color: rgba(40, 40, 40, 240); color: #ffffff; }}"
        )

    @classmethod
    def style_taskbar_toggle_button(cls, is_hidden: bool) -> str:
        if is_hidden:
            return cls.style_quit_button()
        return (
            f"QPushButton {{ background-color: {cls.HEX_ACCENT_MUTED}; color: {cls.HEX_ACCENT_LIGHT}; "
            f"border: 1px solid {cls.HEX_ACCENT_BORDER}; border-radius: 8px; "
            f"padding: 4px 10px; font-size: 9.5px; font-weight: 600; font-family: '{cls.FONT_FAMILY_FALLBACK}'; }}"
            f"QPushButton:hover {{ background-color: {cls.HEX_ACCENT_HOVER}; color: #ffffff; }}"
        )


# Inicializa preferências salvas ao importar
Theme.load_preferences()
