import ctypes
from ctypes import wintypes
import win32gui
import win32con
import win32process
import win32api
import win32ui
import psutil
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtCore import Qt


class TaskManager:
    """
    Gerencia janelas abertas no Windows para o Carrossel Visual Monolith Fusion.
    Inclui agrupamento por identidade de aplicativo e captura de miniaturas estritamente sob demanda.
    """

    _thumbnail_cache = {}

    @classmethod
    def clear_thumbnail_cache(cls):
        """Libera imediatamente as miniaturas em memória quando o painel é recolhido."""
        cls._thumbnail_cache.clear()

    @staticmethod
    def _is_window_cloaked(hwnd: int) -> bool:
        try:
            cloaked = ctypes.c_int(0)
            DWMWA_CLOAKED = 14
            res = ctypes.windll.dwmapi.DwmGetWindowAttribute(
                wintypes.HWND(hwnd),
                wintypes.DWORD(DWMWA_CLOAKED),
                ctypes.byref(cloaked),
                ctypes.sizeof(cloaked)
            )
            return res == 0 and cloaked.value != 0
        except Exception:
            return False

    @staticmethod
    def _classify_app_kind(exe_lower: str, title_lower: str) -> str:
        if any(k in exe_lower for k in ("code", "pycharm", "idea", "devenv", "cursor", "windsurf")):
            return "vscode"
        if any(k in exe_lower for k in ("msedge", "chrome", "firefox", "brave", "opera")):
            return "edge"
        if "explorer" in exe_lower:
            return "folder"
        if any(k in exe_lower for k in ("spotify", "vlc", "stremio", "wmplayer", "music", "mpv")):
            return "media"
        if any(k in exe_lower for k in ("photo", "paint", "figma", "canva")):
            return "photos"
        if any(k in exe_lower for k in ("windowsterminal", "powershell", "cmd", "wt", "mintty")):
            return "terminal"
        return "windows"

    @classmethod
    def get_open_windows(cls) -> list:
        raw_windows = []
        app_counts = {}
        fg_hwnd = win32gui.GetForegroundWindow()

        def enum_cb(hwnd, _):
            try:
                if not win32gui.IsWindowVisible(hwnd):
                    return True
                title = win32gui.GetWindowText(hwnd).strip()
                if not title:
                    return True

                ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
                if ex_style & win32con.WS_EX_TOOLWINDOW:
                    return True

                style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
                if not (style & win32con.WS_VISIBLE):
                    return True

                if cls._is_window_cloaked(hwnd):
                    return True
            except Exception:
                return True

            w_cls = win32gui.GetClassName(hwnd)
            if w_cls in ("Progman", "Shell_TrayWnd", "Shell_SecondaryTrayWnd", "Windows.UI.Core.CoreWindow"):
                return True
            if title in (
                "Program Manager", "Settings", "Dynamic Island Windows",
                "Windows Input Experience", "Monolith", "Monolith Overlay",
                "Monolith — Centro de Controle"
            ):
                return True

            exe_name = "app.exe"
            clean_name = "Janela"
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                p = psutil.Process(pid)
                exe_name = p.name()
                base = exe_name.replace(".exe", "").replace(".EXE", "")
                friendly_map = {
                    "code": "VS Code",
                    "msedge": "Microsoft Edge",
                    "chrome": "Google Chrome",
                    "explorer": "Explorador",
                    "windowsterminal": "Terminal",
                    "powershell": "PowerShell",
                    "spotify": "Spotify",
                    "vlc": "VLC Player",
                    "stremio": "Stremio",
                }
                clean_name = friendly_map.get(base.lower(), base.capitalize())
            except Exception:
                pass

            app_counts[clean_name] = app_counts.get(clean_name, 0) + 1
            display_title = title if len(title) <= 28 else f"{title[:26]}..."
            kind = cls._classify_app_kind(exe_name.lower(), title.lower())

            raw_windows.append({
                "hwnd": hwnd,
                "title": title,
                "display_title": display_title,
                "app_name": clean_name,
                "exe_name": exe_name,
                "kind": kind,
                "is_active": (hwnd == fg_hwnd),
                "is_minimized": bool(win32gui.IsIconic(hwnd)),
            })
            return True

        try:
            win32gui.EnumWindows(enum_cb, None)
        except Exception:
            pass

        for w in raw_windows:
            w["instance_count"] = app_counts.get(w["app_name"], 1)

        return raw_windows

    @classmethod
    def get_thumbnail_on_demand(cls, hwnd: int, target_w: int = 180, target_h: int = 104):
        """
        Captura miniatura da janela ESTRITAMENTE SOB DEMANDA quando o Carrossel de Janelas está aberto.
        Não executa se a janela estiver minimizada, retornando None para fallback vetorial leve.
        """
        cache_key = (hwnd, target_w, target_h)
        if cache_key in cls._thumbnail_cache:
            return cls._thumbnail_cache[cache_key]

        if not win32gui.IsWindow(hwnd) or win32gui.IsIconic(hwnd):
            return None

        hwnd_dc = None
        mfc_dc = None
        save_dc = None
        save_bmp = None
        old_bmp = None
        try:
            left, top, right, bot = win32gui.GetWindowRect(hwnd)
            w = right - left
            h = bot - top
            if w <= 40 or h <= 40:
                return None

            hwnd_dc = win32gui.GetWindowDC(hwnd)
            mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
            save_dc = mfc_dc.CreateCompatibleDC()
            save_bmp = win32ui.CreateBitmap()
            save_bmp.CreateCompatibleBitmap(mfc_dc, w, h)
            old_bmp = save_dc.SelectObject(save_bmp)

            # PW_RENDERFULLCONTENT = 2
            res = ctypes.windll.user32.PrintWindow(wintypes.HWND(hwnd), save_dc.GetSafeHdc(), 2)
            if res == 0:
                res = ctypes.windll.user32.PrintWindow(wintypes.HWND(hwnd), save_dc.GetSafeHdc(), 0)
            if res == 0:
                return None

            bmp_info = save_bmp.GetInfo()
            bmp_bytes = save_bmp.GetBitmapBits(True)
            img = QImage(
                bmp_bytes,
                bmp_info["bmWidth"],
                bmp_info["bmHeight"],
                bmp_info["bmWidth"] * 4,
                QImage.Format.Format_ARGB32
            ).copy()

            # Verifica se a imagem não é totalmente preta/vazia
            c_mid = img.pixelColor(img.width() // 2, img.height() // 2)
            c_qtr = img.pixelColor(img.width() // 3, img.height() // 3)
            if c_mid.red() == 0 and c_mid.green() == 0 and c_mid.blue() == 0 and c_qtr.red() == 0 and c_qtr.green() == 0 and c_qtr.blue() == 0:
                return None

            scaled = QPixmap.fromImage(img).scaled(
                target_w, target_h,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation
            )
            cls._thumbnail_cache[cache_key] = scaled
            return scaled
        except Exception:
            return None
        finally:
            try:
                if save_dc and old_bmp:
                    save_dc.SelectObject(old_bmp)
                if save_dc:
                    save_dc.DeleteDC()
                if save_bmp:
                    win32gui.DeleteObject(save_bmp.GetHandle())
                if hwnd_dc:
                    win32gui.ReleaseDC(hwnd, hwnd_dc)
            except Exception:
                pass

    @staticmethod
    def focus_window(hwnd: int) -> bool:
        """Restaura (se minimizada) e traz a janela selecionada para o foco principal."""
        try:
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            else:
                win32gui.ShowWindow(hwnd, win32con.SW_SHOW)

            cur_thread = win32api.GetCurrentThreadId()
            fg_thread = win32process.GetWindowThreadProcessId(win32gui.GetForegroundWindow())[0]
            if cur_thread != fg_thread and fg_thread != 0:
                win32process.AttachThreadInput(cur_thread, fg_thread, True)
                win32gui.SetForegroundWindow(hwnd)
                win32process.AttachThreadInput(cur_thread, fg_thread, False)
            else:
                win32gui.SetForegroundWindow(hwnd)
            return True
        except Exception:
            try:
                win32gui.SetForegroundWindow(hwnd)
                return True
            except Exception:
                return False

    @staticmethod
    def close_window(hwnd: int):
        try:
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
        except Exception:
            pass
