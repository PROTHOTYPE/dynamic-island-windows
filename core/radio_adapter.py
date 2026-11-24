"""
Módulo 2A — Adaptador de Rádios Nativos (Windows.Devices.Radios)
Gerencia controle real de Wi-Fi, Bluetooth e Tethering/Hotspot em thread isolada (fora do loop de renderização).
Emite eventos via PyQt6 Signals para atualização reativa da interface.
"""

import os
import json
import subprocess
import threading
import atexit

from PyQt6.QtCore import QObject, pyqtSignal

from core.paths import get_resource_path
from core.diagnostics import log_warning, log_exception


class RadioAdapter(QObject):
    """
    Controlador de Rádios Nativos do Windows.
    Executa comandos sobre Windows.Devices.Radios de forma assíncrona,
    confirmando estados reais de hardware e garantindo zero bloqueio da UI.
    """

    radios_updated = pyqtSignal(list)               # Lista completa de rádios e estados
    radio_state_changed = pyqtSignal(str, str)       # kind ("WiFi" | "Bluetooth"), state ("On" | "Off" | "Unavailable")
    access_status_received = pyqtSignal(str)         # "Allowed" | "DeniedByUser" | "DeniedBySystem"
    tethering_updated = pyqtSignal(bool, bool, str)  # (supported, active, state_label)
    radio_error = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._radios_cache = {}
        self._access_status = "Unknown"
        self._tethering_supported = False
        self._tethering_active = False
        self._tethering_state = "Unavailable"
        self._proc = None
        self._lock = threading.Lock()
        self._running = False
        self._ready_event = threading.Event()

        self._script_path = get_resource_path("core", "radio_worker.ps1")

        self._start_worker()
        atexit.register(self.shutdown)

    def _start_worker(self):
        """Inicia o processo worker PowerShell em segundo plano."""
        if not os.path.exists(self._script_path):
            log_warning("Script de worker de rádio não encontrado: %s", self._script_path)
            self.radio_error.emit(f"Script de worker não encontrado: {self._script_path}")
            return

        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

            self._proc = subprocess.Popen(
                [
                    "powershell", "-NoProfile", "-NonInteractive",
                    "-ExecutionPolicy", "Bypass",
                    "-File", self._script_path
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                startupinfo=startupinfo
            )
            self._running = True

            self._reader_thread = threading.Thread(target=self._stdout_reader, name="RadioStdout", daemon=True)
            self._reader_thread.start()
            self._stderr_thread = threading.Thread(target=self._stderr_reader, name="RadioStderr", daemon=True)
            self._stderr_thread.start()

            self._ready_event.wait(timeout=3.0)

        except Exception as e:
            self._running = False
            log_exception("RadioAdapter._start_worker", e)
            self.radio_error.emit(f"Falha ao iniciar worker de rádio: {e}")

    def _stderr_reader(self):
        """Consome stderr do worker PowerShell evitando bloqueio de pipe."""
        while self._running and self._proc and self._proc.poll() is None:
            try:
                err_line = self._proc.stderr.readline()
                if not err_line:
                    break
                err_line = err_line.strip()
                if err_line:
                    log_warning("RadioWorker stderr: %s", err_line)
            except Exception:
                break

    def _stdout_reader(self):
        """Lê mensagens emitidas pelo worker PowerShell e despacha sinais PyQt."""
        while self._running and self._proc and self._proc.poll() is None:
            try:
                line = self._proc.stdout.readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue

                if line.startswith("READY:"):
                    self._parse_radios_update(line[6:])
                    self._ready_event.set()
                elif line.startswith("RADIOS:"):
                    self._parse_radios_update(line[7:])
                elif line.startswith("SET_RESULT:"):
                    self._parse_set_result(line[11:])
                elif line.startswith("ACCESS:"):
                    status = line[7:].strip()
                    self._access_status = status
                    self.access_status_received.emit(status)
                elif line.startswith("TETHERING:"):
                    self._parse_tethering_result(line[10:])

            except Exception as e:
                if self._running:
                    log_exception("RadioAdapter._stdout_reader", e)
                    self.radio_error.emit(f"Erro na leitura de saída do rádio: {e}")

    @staticmethod
    def normalize_radios_payload(raw_json: str) -> list:
        """Normaliza payload JSON de rádios (trata lista vazia, objeto único do PS 5.1 ou lista)."""
        if not raw_json or not raw_json.strip():
            return []
        data = json.loads(raw_json)
        if data is None:
            return []
        if isinstance(data, dict):
            return [data] if ("kind" in data and "state" in data) else []
        if isinstance(data, list):
            return [r for r in data if isinstance(r, dict) and "kind" in r and "state" in r]
        return []

    def _parse_radios_update(self, raw_json: str):
        try:
            data = self.normalize_radios_payload(raw_json)
            seen = {}
            for r in data:
                kind = r.get("kind")
                st = r.get("state")
                if kind and st:
                    seen[kind] = st

            # Remove estados em cache de adaptadores removidos ou inexistentes
            for stale_kind in list(self._radios_cache.keys()):
                if stale_kind not in seen:
                    del self._radios_cache[stale_kind]
                    self.radio_state_changed.emit(stale_kind, "Unavailable")

            for kind, st in seen.items():
                old_st = self._radios_cache.get(kind)
                self._radios_cache[kind] = st
                if old_st != st:
                    self.radio_state_changed.emit(kind, st)

            if "WiFi" not in seen and self._tethering_supported:
                self._tethering_supported = False
                self._tethering_active = False
                self._tethering_state = "Unavailable"
                self.tethering_updated.emit(False, False, "Unavailable")

            self.radios_updated.emit(data)
        except Exception as e:
            log_exception("RadioAdapter._parse_radios_update", e)
            self.radio_error.emit(f"Falha temporária ao ler adaptadores de rádio: {e}")

    def _parse_set_result(self, raw_json: str):
        try:
            res = json.loads(raw_json)
            if "error" in res:
                self.radio_error.emit(f"Falha na troca de rádio: {res['error']}")
                return
            kind = res.get("kind")
            actual = res.get("actualState")
            if kind and actual:
                self._radios_cache[kind] = actual
                self.radio_state_changed.emit(kind, actual)
        except Exception as e:
            self.radio_error.emit(f"Erro no resultado de rádio: {e}")

    def _parse_tethering_result(self, raw_json: str):
        try:
            res = json.loads(raw_json)
            wifi_present = self.has_radio("WiFi")
            supported = bool(res.get("supported", False)) and wifi_present
            active = bool(res.get("active", False)) if supported else False
            state = str(res.get("state", "Unavailable")) if supported else "Unavailable"
            self._tethering_supported = supported
            self._tethering_active = active
            self._tethering_state = state
            self.tethering_updated.emit(supported, active, state)
        except Exception as e:
            self._tethering_supported = False
            self._tethering_active = False
            self._tethering_state = "Unavailable"
            self.tethering_updated.emit(False, False, "Unavailable")
            self.radio_error.emit(f"Erro ao consultar Hotspot: {e}")

    def _send_cmd(self, cmd: str):
        """Envia comando de forma thread-safe para o worker PowerShell."""
        if not self._running or not self._proc or self._proc.poll() is not None:
            return
        with self._lock:
            try:
                self._proc.stdin.write(cmd + "\n")
                self._proc.stdin.flush()
            except Exception as e:
                self.radio_error.emit(f"Erro ao enviar comando para worker: {e}")

    # ==========================================================================
    # API Pública Assíncrona
    # ==========================================================================

    def request_access(self):
        threading.Thread(target=lambda: self._send_cmd("REQUEST_ACCESS"), daemon=True).start()

    def refresh_radios(self):
        threading.Thread(target=lambda: self._send_cmd("GET_RADIOS"), daemon=True).start()

    def refresh_tethering(self):
        threading.Thread(target=lambda: self._send_cmd("GET_TETHERING"), daemon=True).start()

    def toggle_tethering(self):
        if not self._tethering_supported:
            self.tethering_updated.emit(False, False, "Unavailable")
            return
        target = "Off" if self._tethering_active else "On"
        threading.Thread(target=lambda: self._send_cmd(f"SET_TETHERING:{target}"), daemon=True).start()

    def set_radio_state(self, kind: str, state: str):
        if not self.has_radio(kind):
            self.radio_state_changed.emit(kind, "Unavailable")
            self.radio_error.emit(f"Adaptador de rádio '{kind}' ausente neste computador.")
            return
        threading.Thread(target=lambda: self._send_cmd(f"SET:{kind}:{state}"), daemon=True).start()

    def toggle_radio(self, kind: str):
        if not self.has_radio(kind):
            self.radio_state_changed.emit(kind, "Unavailable")
            return
        curr = self._radios_cache.get(kind, "Off")
        target = "Off" if curr == "On" else "On"
        self.set_radio_state(kind, target)

    def has_radio(self, kind: str) -> bool:
        return kind in self._radios_cache

    def is_wifi_on(self) -> bool:
        return self._radios_cache.get("WiFi") == "On"

    def is_bluetooth_on(self) -> bool:
        return self._radios_cache.get("Bluetooth") == "On"

    def get_cached_radios(self) -> dict:
        return dict(self._radios_cache)

    def get_tethering_status(self) -> tuple[bool, bool, str]:
        return (self._tethering_supported, self._tethering_active, self._tethering_state)

    def shutdown(self):
        """Finaliza graciosamente o processo worker e fecha descritores de pipe."""
        self._running = False
        if self._proc:
            try:
                if self._proc.stdin:
                    self._proc.stdin.write("QUIT\n")
                    self._proc.stdin.flush()
                self._proc.wait(timeout=1.0)
            except Exception:
                try:
                    self._proc.kill()
                    self._proc.wait(timeout=0.5)
                except Exception:
                    pass
            finally:
                for stream in (self._proc.stdin, self._proc.stdout, self._proc.stderr):
                    try:
                        if stream:
                            stream.close()
                    except Exception:
                        pass
            self._proc = None
