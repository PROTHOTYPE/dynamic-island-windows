"""
Adaptador de Controles e Telemetria de Hardware do Sistema (Windows 11)
Fornece fonte única de verdade (sem dados fictícios) para:
- Bateria e Economia de Energia (psutil + Win32 GetSystemPowerStatus)
- Brilho de Tela (DDC/CI via dxva2.dll para monitores externos + WMI para notebooks)
- Luz Noturna (leitura do registro CloudStore do Windows)
Todas as operações lentas executam fora da thread gráfica e notificam via sinais PyQt6.
"""

import ctypes
import subprocess
import threading
import winreg
from ctypes import wintypes, POINTER, byref

import psutil
from PyQt6.QtCore import QObject, pyqtSignal

from core.diagnostics import log_exception


class _SYSTEM_POWER_STATUS(ctypes.Structure):
    _fields_ = [
        ("ACLineStatus", ctypes.c_ubyte),
        ("BatteryFlag", ctypes.c_ubyte),
        ("BatteryLifePercent", ctypes.c_ubyte),
        ("SystemStatusFlag", ctypes.c_ubyte),
        ("BatteryLifeTime", ctypes.c_ulong),
        ("BatteryFullLifeTime", ctypes.c_ulong),
    ]


class _PHYSICAL_MONITOR(ctypes.Structure):
    _fields_ = [
        ("hPhysicalMonitor", wintypes.HANDLE),
        ("szPhysicalMonitorDescription", wintypes.WCHAR * 128),
    ]


_DDC_LOCK = threading.Lock()

# Configura tipos explícitos Win32/DDC para evitar truncamento ou corrupção de stack em 64-bit
try:
    _user32 = ctypes.windll.user32
    _user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
    _user32.MonitorFromPoint.restype = wintypes.HANDLE
except Exception:
    _user32 = None

try:
    _dxva2 = ctypes.windll.dxva2
    _dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR.argtypes = [wintypes.HANDLE, POINTER(wintypes.DWORD)]
    _dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR.restype = wintypes.BOOL
    _dxva2.GetPhysicalMonitorsFromHMONITOR.argtypes = [wintypes.HANDLE, wintypes.DWORD, POINTER(_PHYSICAL_MONITOR)]
    _dxva2.GetPhysicalMonitorsFromHMONITOR.restype = wintypes.BOOL
    _dxva2.GetMonitorBrightness.argtypes = [wintypes.HANDLE, POINTER(wintypes.DWORD), POINTER(wintypes.DWORD), POINTER(wintypes.DWORD)]
    _dxva2.GetMonitorBrightness.restype = wintypes.BOOL
    _dxva2.SetMonitorBrightness.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    _dxva2.SetMonitorBrightness.restype = wintypes.BOOL
    _dxva2.DestroyPhysicalMonitors.argtypes = [wintypes.DWORD, POINTER(_PHYSICAL_MONITOR)]
    _dxva2.DestroyPhysicalMonitors.restype = wintypes.BOOL
except Exception:
    _dxva2 = None


class SystemControlsAdapter(QObject):
    """Fonte única de verdade para Bateria, Economia de Energia, Brilho e Luz Noturna."""

    state_updated = pyqtSignal(dict)
    open_settings_requested = pyqtSignal(str)

    _NIGHT_LIGHT_KEY = (
        r"Software\Microsoft\Windows\CurrentVersion\CloudStore\Store\DefaultAccount\Current"
        r"\default$windows.data.bluelightreduction.bluelightreductionstate"
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lock = threading.Lock()
        self._brightness_method = None  # "ddc" | "wmi" | "none" | None
        self._brightness_write_lock = threading.Lock()
        self._pending_brightness = None
        self._brightness_worker_active = False

        self._state = {
            "has_battery": False,
            "battery_percent": None,
            "is_charging": None,
            "battery_saver_supported": False,
            "battery_saver_active": False,
            "night_light_supported": False,
            "night_light_active": False,
            "brightness_supported": False,
            "brightness_val": None,
            "brightness_backend": "none",
        }
        self.refresh()

    def get_state(self) -> dict:
        with self._lock:
            return dict(self._state)

    def refresh(self):
        """Atualiza telemetria real de hardware em thread isolada."""
        threading.Thread(target=self._refresh_worker, daemon=True).start()

    def _refresh_worker(self):
        new_state = {}
        new_state.update(self._query_power_state())
        new_state.update(self._query_night_light_state())
        new_state.update(self._query_brightness_state())

        with self._lock:
            self._state.update(new_state)
            snapshot = dict(self._state)
        try:
            self.state_updated.emit(snapshot)
        except RuntimeError:
            pass

    @staticmethod
    def _query_power_state() -> dict:
        bat = psutil.sensors_battery()
        has_bat = bat is not None
        pct = int(bat.percent) if has_bat else None
        charging = bool(bat.power_plugged) if has_bat else None

        saver_active = False
        if has_bat:
            try:
                sps = _SYSTEM_POWER_STATUS()
                if ctypes.windll.kernel32.GetSystemPowerStatus(byref(sps)):
                    saver_active = bool(sps.SystemStatusFlag & 1)
            except Exception:
                saver_active = False

        return {
            "has_battery": has_bat,
            "battery_percent": pct,
            "is_charging": charging,
            "battery_saver_supported": has_bat,
            "battery_saver_active": saver_active,
        }

    @classmethod
    def _query_night_light_state(cls) -> dict:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, cls._NIGHT_LIGHT_KEY) as k:
                sub = winreg.EnumKey(k, 0)
                with winreg.OpenKey(k, sub) as sk:
                    data, _ = winreg.QueryValueEx(sk, "Data")
                    # Formato CloudStore Win10/11: byte 18 == 0x15 ou sequência [0x10, 0x00] em 23..24
                    active = False
                    if len(data) > 24 and data[23] == 0x10 and data[24] == 0x00:
                        active = True
                    elif len(data) > 18 and data[18] == 0x15:
                        active = True
                    return {"night_light_supported": True, "night_light_active": active}
        except OSError:
            return {"night_light_supported": False, "night_light_active": False}
        except Exception:
            return {"night_light_supported": False, "night_light_active": False}

    def _query_ddc_brightness(self) -> int | None:
        if not _user32 or not _dxva2:
            return None
        with _DDC_LOCK:
            try:
                hmon = _user32.MonitorFromPoint(wintypes.POINT(0, 0), 1)
                if not hmon:
                    return None
                cnt = wintypes.DWORD()
                if not _dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR(hmon, byref(cnt)) or cnt.value == 0:
                    return None
                arr = (_PHYSICAL_MONITOR * cnt.value)()
                if not _dxva2.GetPhysicalMonitorsFromHMONITOR(hmon, cnt.value, arr):
                    return None
                try:
                    mn, cur, mx = wintypes.DWORD(), wintypes.DWORD(), wintypes.DWORD()
                    if _dxva2.GetMonitorBrightness(arr[0].hPhysicalMonitor, byref(mn), byref(cur), byref(mx)):
                        span = max(1, mx.value - mn.value)
                        return int(round(((cur.value - mn.value) / span) * 100.0))
                finally:
                    _dxva2.DestroyPhysicalMonitors(cnt.value, arr)
            except Exception as e:
                log_exception("SystemControlsAdapter._query_ddc_brightness", e)
        return None

    def _set_ddc_brightness(self, pct: int) -> bool:
        if not _user32 or not _dxva2:
            return False
        with _DDC_LOCK:
            try:
                hmon = _user32.MonitorFromPoint(wintypes.POINT(0, 0), 1)
                if not hmon:
                    return False
                cnt = wintypes.DWORD()
                if not _dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR(hmon, byref(cnt)) or cnt.value == 0:
                    return False
                arr = (_PHYSICAL_MONITOR * cnt.value)()
                if not _dxva2.GetPhysicalMonitorsFromHMONITOR(hmon, cnt.value, arr):
                    return False
                try:
                    mn, cur, mx = wintypes.DWORD(), wintypes.DWORD(), wintypes.DWORD()
                    if _dxva2.GetMonitorBrightness(arr[0].hPhysicalMonitor, byref(mn), byref(cur), byref(mx)):
                        target = int(round(mn.value + (max(0, min(100, pct)) / 100.0) * max(0, mx.value - mn.value)))
                        return bool(_dxva2.SetMonitorBrightness(arr[0].hPhysicalMonitor, wintypes.DWORD(target)))
                finally:
                    _dxva2.DestroyPhysicalMonitors(cnt.value, arr)
            except Exception as e:
                log_exception("SystemControlsAdapter._set_ddc_brightness", e)
        return False

    @staticmethod
    def _query_wmi_brightness() -> int | None:
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            res = subprocess.run(
                [
                    "powershell", "-NoProfile", "-NonInteractive", "-Command",
                    "(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty CurrentBrightness)"
                ],
                capture_output=True, text=True, timeout=2.0, startupinfo=startupinfo
            )
            val = res.stdout.strip()
            if val.isdigit():
                return max(0, min(100, int(val)))
        except Exception:
            pass
        return None

    @staticmethod
    def _set_wmi_brightness(pct: int) -> bool:
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            clamped = max(0, min(100, int(pct)))
            res = subprocess.run(
                [
                    "powershell", "-NoProfile", "-NonInteractive", "-Command",
                    f"$m = Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods -ErrorAction SilentlyContinue | Select-Object -First 1; if ($m) {{ Invoke-CimMethod -InputObject $m -MethodName WmiSetBrightness -Arguments @{{ Timeout = 1; Brightness = {clamped} }} | Out-Null; 'OK' }}"
                ],
                capture_output=True, text=True, timeout=2.5, startupinfo=startupinfo
            )
            return "OK" in res.stdout
        except Exception:
            return False

    def _query_brightness_state(self) -> dict:
        if self._brightness_method in (None, "ddc"):
            ddc_val = self._query_ddc_brightness()
            if ddc_val is not None:
                self._brightness_method = "ddc"
                return {"brightness_supported": True, "brightness_val": ddc_val, "brightness_backend": "ddc"}

        if self._brightness_method in (None, "wmi"):
            wmi_val = self._query_wmi_brightness()
            if wmi_val is not None:
                self._brightness_method = "wmi"
                return {"brightness_supported": True, "brightness_val": wmi_val, "brightness_backend": "wmi"}

        self._brightness_method = "none"
        return {"brightness_supported": False, "brightness_val": None, "brightness_backend": "none"}

    def set_brightness(self, pct: int):
        """Aplica brilho real no monitor quando suportado (coalesce de arraste rápido)."""
        with self._lock:
            if not self._state["brightness_supported"]:
                return
            clamped = max(0, min(100, int(pct)))
            self._state["brightness_val"] = clamped
            snapshot = dict(self._state)

        try:
            self.state_updated.emit(snapshot)
        except RuntimeError:
            pass

        with self._brightness_write_lock:
            self._pending_brightness = clamped
            if not self._brightness_worker_active:
                self._brightness_worker_active = True
                threading.Thread(target=self._brightness_write_loop, daemon=True).start()

    def _brightness_write_loop(self):
        while True:
            with self._brightness_write_lock:
                target = self._pending_brightness
                self._pending_brightness = None
                if target is None:
                    self._brightness_worker_active = False
                    return
            if self._brightness_method == "ddc":
                self._set_ddc_brightness(target)
            elif self._brightness_method == "wmi":
                self._set_wmi_brightness(target)

    def open_night_light_settings(self):
        self.open_settings_requested.emit("ms-settings:nightlight")

    def open_battery_saver_settings(self):
        if self._state.get("has_battery"):
            self.open_settings_requested.emit("ms-settings:batterysaver")
