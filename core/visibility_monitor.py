"""
Motor orientado a eventos de visibilidade contextual da cápsula Monolith.
Utiliza Win32 SetWinEventHook (EVENT_SYSTEM_FOREGROUND, EVENT_OBJECT_LOCATIONCHANGE,
EVENT_SYSTEM_MINIMIZESTART, EVENT_SYSTEM_MINIMIZEEND) sem polling agressivo.

Estados suportados:
- DESKTOP_IDLE: Área de trabalho visível / em foco -> cápsula visível e centralizada.
- APP_AUTO_HIDE: Aplicação convencional em primeiro plano -> cápsula recolhida para a borda
  superior com zona discreta de revelação.
- EDGE_REVEAL: Cursor na zona central superior durante APP_AUTO_HIDE -> revela cápsula sem
  expandir o painel completo e sem roubar foco da aplicação ativa.
- FULLSCREEN_HIDDEN: Jogo, vídeo ou aplicação em tela cheia real / borderless fullscreen ->
  desaparecimento completo sem revelação por mouse; restaura ao sair da tela cheia.
"""

import ctypes
from ctypes import wintypes, byref, Structure
import win32con
import win32gui

from PyQt6.QtCore import QObject, pyqtSignal, QTimer

from core.diagnostics import log_exception

EVENT_SYSTEM_FOREGROUND = 0x0003
EVENT_SYSTEM_MINIMIZESTART = 0x0016
EVENT_SYSTEM_MINIMIZEEND = 0x0017
EVENT_OBJECT_LOCATIONCHANGE = 0x800B
OBJID_WINDOW = 0
WINEVENT_OUTOFCONTEXT = 0x0000
WINEVENT_SKIPOWNPROCESS = 0x0002

DWMWA_EXTENDED_FRAME_BOUNDS = 9
MONITOR_DEFAULTTONEAREST = 2
WS_CAPTION = 0x00C00000

SHELL_CLASSES = {
    "Progman",
    "WorkerW",
    "Shell_TrayWnd",
    "Shell_SecondaryTrayWnd",
    "NotifyIconOverflowWindow",
    "TaskListThumbnailWnd",
    "Windows.UI.Core.CoreWindow",
    "MultitaskingViewFrame",
    "ForegroundStaging",
}

DESKTOP_CLASSES = {"Progman", "WorkerW"}


class _MONITORINFO(Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


_WINEVENTPROC = ctypes.WINFUNCTYPE(
    None,
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.HWND,
    ctypes.c_long,
    ctypes.c_long,
    wintypes.DWORD,
    wintypes.DWORD,
)

user32 = ctypes.windll.user32
user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
user32.MonitorFromWindow.restype = wintypes.HANDLE
user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_MONITORINFO)]
user32.GetMonitorInfoW.restype = wintypes.BOOL
user32.SetWinEventHook.argtypes = [
    wintypes.DWORD, wintypes.DWORD, wintypes.HMODULE,
    _WINEVENTPROC, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
]
user32.SetWinEventHook.restype = wintypes.HANDLE
user32.UnhookWinEvent.argtypes = [wintypes.HANDLE]
user32.UnhookWinEvent.restype = wintypes.BOOL

try:
    _dwmapi = ctypes.windll.dwmapi
except Exception:
    _dwmapi = None


def get_window_bounds(hwnd: int) -> tuple[int, int, int, int] | None:
    """Obtém limites reais da janela via DWMWA_EXTENDED_FRAME_BOUNDS (fallback GetWindowRect)."""
    if not hwnd or not win32gui.IsWindow(hwnd):
        return None
    if _dwmapi:
        try:
            rect = wintypes.RECT()
            hr = _dwmapi.DwmGetWindowAttribute(
                wintypes.HWND(hwnd),
                wintypes.DWORD(DWMWA_EXTENDED_FRAME_BOUNDS),
                byref(rect),
                ctypes.sizeof(rect),
            )
            if hr == 0 and (rect.right - rect.left) > 0 and (rect.bottom - rect.top) > 0:
                return (rect.left, rect.top, rect.right, rect.bottom)
        except Exception:
            pass
    try:
        return win32gui.GetWindowRect(hwnd)
    except Exception:
        return None


def get_monitor_rects(hwnd: int) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int]] | None:
    """Retorna (rcMonitor, rcWork) do monitor onde a janela está localizada."""
    try:
        hmon = user32.MonitorFromWindow(wintypes.HWND(hwnd), MONITOR_DEFAULTTONEAREST)
        if not hmon:
            return None
        mi = _MONITORINFO()
        mi.cbSize = ctypes.sizeof(_MONITORINFO)
        if not user32.GetMonitorInfoW(hmon, byref(mi)):
            return None
        mon = (mi.rcMonitor.left, mi.rcMonitor.top, mi.rcMonitor.right, mi.rcMonitor.bottom)
        work = (mi.rcWork.left, mi.rcWork.top, mi.rcWork.right, mi.rcWork.bottom)
        return mon, work
    except Exception:
        return None


def classify_foreground_state(
    fg_hwnd: int,
    monolith_hwnds: set[int],
    is_expanded: bool = False,
    overlay_open: bool = False,
    edge_hovered: bool = False,
    prev_non_monolith_state: str = "DESKTOP_IDLE",
) -> tuple[str, bool]:
    """
    Classifica o estado contextual de visibilidade a partir do foreground window real.
    Retorna (estado, deve_atualizar_prev_state).
    """
    if is_expanded or overlay_open:
        return ("DESKTOP_IDLE", False)

    if not fg_hwnd or not win32gui.IsWindow(fg_hwnd):
        return ("DESKTOP_IDLE", True)

    if int(fg_hwnd) in monolith_hwnds:
        return (prev_non_monolith_state, False)

    try:
        cls_name = win32gui.GetClassName(fg_hwnd)
    except Exception:
        cls_name = ""

    if cls_name in DESKTOP_CLASSES:
        return ("DESKTOP_IDLE", True)

    # Ignora menus temporários da bandeja / taskbar sem alterar o estado anterior
    if cls_name in SHELL_CLASSES:
        return (prev_non_monolith_state, False)

    try:
        if not win32gui.IsWindowVisible(fg_hwnd) or win32gui.IsIconic(fg_hwnd):
            return ("DESKTOP_IDLE", True)
        title = win32gui.GetWindowText(fg_hwnd).strip()
        if not title and (win32gui.GetWindowLong(fg_hwnd, win32con.GWL_EXSTYLE) & win32con.WS_EX_TOOLWINDOW):
            return (prev_non_monolith_state, False)
    except Exception:
        return ("DESKTOP_IDLE", True)

    bounds = get_window_bounds(fg_hwnd)
    mon_rects = get_monitor_rects(fg_hwnd)
    if not bounds or not mon_rects:
        return ("APP_AUTO_HIDE", True)

    left, top, right, bottom = bounds
    mon, work = mon_rects
    m_l, m_t, m_r, m_b = mon
    w_l, w_t, w_r, w_b = work

    # Distingue janela maximizada (respeita área útil rcWork) de tela cheia real (cobre todo rcMonitor)
    covers_full_monitor = (
        left <= m_l + 1
        and top <= m_t + 1
        and right >= m_r - 1
        and bottom >= m_b - 1
    )

    if covers_full_monitor:
        taskbar_visible = (work != mon)
        try:
            style = win32gui.GetWindowLong(fg_hwnd, win32con.GWL_STYLE)
        except Exception:
            style = 0
        has_caption = (style & WS_CAPTION) == WS_CAPTION

        # Se a barra de tarefas está visível e a janela cobre até a área da barra de tarefas,
        # OU se não possui barra de título (borderless fullscreen / jogo / vídeo F11), é FULLSCREEN_HIDDEN.
        if taskbar_visible or not has_caption:
            return ("FULLSCREEN_HIDDEN", True)

    # Aplicação convencional (normal ou maximizada) -> oculta cápsula para a borda com zona de revelação
    if edge_hovered:
        return ("EDGE_REVEAL", True)
    return ("APP_AUTO_HIDE", True)


class VisibilityMonitor(QObject):
    """
    Gerencia hooks Win32 orientados a eventos e emite o estado contextual na thread gráfica.
    """

    DESKTOP_IDLE = "DESKTOP_IDLE"
    APP_AUTO_HIDE = "APP_AUTO_HIDE"
    EDGE_REVEAL = "EDGE_REVEAL"
    FULLSCREEN_HIDDEN = "FULLSCREEN_HIDDEN"

    state_changed = pyqtSignal(str)
    _win_event_signal = pyqtSignal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._monolith_hwnds: set[int] = set()
        self._is_expanded = False
        self._overlay_open = False
        self._edge_hovered = False
        self._current_state = self.DESKTOP_IDLE
        self._prev_app_state = self.DESKTOP_IDLE
        self._in_hook = False
        self._hooks: list[int] = []

        self._win_event_signal.connect(self._on_win_event_qt)

        # Debounce leve apenas para coalescer rajadas de EVENT_OBJECT_LOCATIONCHANGE
        self._eval_timer = QTimer(self)
        self._eval_timer.setSingleShot(True)
        self._eval_timer.setInterval(45)
        self._eval_timer.timeout.connect(self.evaluate_now)

        # Mantém referência forte do callback C para evitar coleta de lixo
        self._hook_cb = _WINEVENTPROC(self._native_win_event_cb)

    def register_monolith_hwnd(self, hwnd: int):
        if hwnd:
            self._monolith_hwnds.add(int(hwnd))

    def set_interaction_flags(self, is_expanded: bool = None, overlay_open: bool = None, edge_hovered: bool = None):
        changed = False
        if is_expanded is not None and self._is_expanded != bool(is_expanded):
            self._is_expanded = bool(is_expanded)
            changed = True
        if overlay_open is not None and self._overlay_open != bool(overlay_open):
            self._overlay_open = bool(overlay_open)
            changed = True
        if edge_hovered is not None and self._edge_hovered != bool(edge_hovered):
            self._edge_hovered = bool(edge_hovered)
            changed = True
        if changed:
            self.evaluate_now()

    def current_state(self) -> str:
        return self._current_state

    def start(self):
        """Instala os hooks SetWinEventHook orientados a eventos e avalia o estado inicial."""
        if self._hooks:
            return
        flags = WINEVENT_OUTOFCONTEXT | WINEVENT_SKIPOWNPROCESS
        ranges = [
            (EVENT_SYSTEM_FOREGROUND, EVENT_SYSTEM_FOREGROUND),
            (EVENT_SYSTEM_MINIMIZESTART, EVENT_SYSTEM_MINIMIZEEND),
            (EVENT_OBJECT_LOCATIONCHANGE, EVENT_OBJECT_LOCATIONCHANGE),
        ]
        for ev_min, ev_max in ranges:
            try:
                h = user32.SetWinEventHook(ev_min, ev_max, 0, self._hook_cb, 0, 0, flags)
                if h:
                    self._hooks.append(int(h))
            except Exception as e:
                log_exception("VisibilityMonitor.SetWinEventHook", e)

        self.evaluate_now()

    def stop(self):
        self._eval_timer.stop()
        for h in self._hooks:
            try:
                user32.UnhookWinEvent(wintypes.HANDLE(h))
            except Exception:
                pass
        self._hooks.clear()

    def _native_win_event_cb(self, hWinEventHook, event, hwnd, idObject, idChild, dwEventThread, dwmsEventTime):
        """Callback Win32 ultraleve protegida contra reentrância."""
        if self._in_hook:
            return
        self._in_hook = True
        try:
            if event == EVENT_OBJECT_LOCATIONCHANGE:
                if idObject != OBJID_WINDOW or not hwnd:
                    return
                fg = user32.GetForegroundWindow()
                if int(hwnd) != int(fg):
                    return
            elif hwnd and int(hwnd) in self._monolith_hwnds:
                return
            self._win_event_signal.emit(int(event), int(hwnd or 0))
        except Exception:
            pass
        finally:
            self._in_hook = False

    def _on_win_event_qt(self, event_id: int, hwnd: int):
        if event_id == EVENT_OBJECT_LOCATIONCHANGE:
            if not self._eval_timer.isActive():
                self._eval_timer.start()
        else:
            self._eval_timer.stop()
            self.evaluate_now()

    def evaluate_now(self):
        try:
            fg = win32gui.GetForegroundWindow()
            new_state, remember = classify_foreground_state(
                fg_hwnd=fg,
                monolith_hwnds=self._monolith_hwnds,
                is_expanded=self._is_expanded,
                overlay_open=self._overlay_open,
                edge_hovered=self._edge_hovered,
                prev_non_monolith_state=self._prev_app_state,
            )
            if remember:
                self._prev_app_state = self.APP_AUTO_HIDE if new_state == self.EDGE_REVEAL else new_state
            if new_state != self._current_state:
                self._current_state = new_state
                self.state_changed.emit(new_state)
        except Exception as e:
            log_exception("VisibilityMonitor.evaluate_now", e)
