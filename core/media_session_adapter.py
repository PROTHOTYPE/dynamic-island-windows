"""
Adaptador de Sessões de Mídia do Windows (SMTC)
Fonte única de verdade para "há reprodução ativa?" no Monolith.

- Usa Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager via worker
  PowerShell persistente (mesmo padrão do RadioAdapter; sem dependências Python adicionais).
- Considera ativo SOMENTE PlaybackStatus == Playing. Paused / Stopped / Closed / sem sessão = inativo.
- Volume do sistema, dispositivo de áudio ou processo de player aberto NÃO contam como reprodução.
- Tolerância técnica de ~1 s apenas para a transição Playing -> não-Playing (troca de faixa),
  evitando oscilação visual. A entrada em Playing é aplicada imediatamente.
"""

import os
import json
import subprocess
import threading
import atexit

from PyQt6.QtCore import QObject, pyqtSignal, QTimer, pyqtSlot

from core.paths import get_resource_path
from core.diagnostics import log_warning, log_exception


class MediaSessionAdapter(QObject):
    # Emitido na thread da UI somente quando a visibilidade contextual muda
    playback_active_changed = pyqtSignal(bool)
    # Emitido na thread da UI sempre que metadados/estado mudam (dict)
    session_updated = pyqtSignal(dict)
    command_result = pyqtSignal(dict)

    _raw_state = pyqtSignal(dict)   # ponte thread de leitura -> thread da UI
    _raw_cmd = pyqtSignal(dict)

    HIDE_TOLERANCE_MS = 1000

    def __init__(self, parent=None, start_worker: bool = True):
        super().__init__(parent)
        self._proc = None
        self._running = False
        self._lock = threading.Lock()
        self.state = {"playing": False, "status": "Closed", "app": "", "title": "", "artist": ""}
        self.active = False

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(self.HIDE_TOLERANCE_MS)
        self._hide_timer.timeout.connect(self._commit_inactive)

        self._raw_state.connect(self._on_raw_state)
        self._raw_cmd.connect(self.command_result.emit)

        self._script_path = get_resource_path("core", "media_session_worker.ps1")
        if start_worker:
            self._start_worker()
        atexit.register(self.shutdown)

    # ------------------------------------------------------------------ worker
    def _start_worker(self):
        if not os.path.exists(self._script_path):
            log_warning("Worker SMTC não encontrado: %s", self._script_path)
            return
        try:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE
            self._proc = subprocess.Popen(
                ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                 "-File", self._script_path],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace", bufsize=1, startupinfo=si,
            )
            self._running = True
            threading.Thread(target=self._stdout_reader, name="MediaSessionStdout", daemon=True).start()
            threading.Thread(target=self._stderr_reader, name="MediaSessionStderr", daemon=True).start()
        except Exception as e:
            self._running = False
            log_exception("MediaSessionAdapter._start_worker", e)

    def _stderr_reader(self):
        while self._running and self._proc and self._proc.poll() is None:
            try:
                line = self._proc.stderr.readline()
                if not line:
                    break
                if line.strip():
                    log_warning("MediaSessionWorker stderr: %s", line.strip())
            except Exception:
                break

    def _stdout_reader(self):
        while self._running and self._proc and self._proc.poll() is None:
            try:
                line = self._proc.stdout.readline()
                if not line:
                    break
                line = line.strip().lstrip("\ufeff")
                if line.startswith("READY:") or line.startswith("MEDIA:"):
                    payload = json.loads(line.split(":", 1)[1])
                    try:
                        self._raw_state.emit(payload)
                    except RuntimeError:
                        return
                elif line.startswith("CMD_RESULT:"):
                    try:
                        self._raw_cmd.emit(json.loads(line[11:]))
                    except RuntimeError:
                        return
            except Exception as e:
                if self._running:
                    log_exception("MediaSessionAdapter._stdout_reader", e)

    def _send(self, cmd: str) -> bool:
        with self._lock:
            if not (self._proc and self._proc.poll() is None):
                return False
            try:
                self._proc.stdin.write(cmd + "\n")
                self._proc.stdin.flush()
                return True
            except Exception:
                return False

    # ------------------------------------------------------------- state logic
    @pyqtSlot(dict)
    def _on_raw_state(self, payload: dict):
        self.ingest_state(payload)

    def ingest_state(self, payload: dict):
        """Aplica um estado SMTC (também usado pelos testes para injetar transições reais simuladas)."""
        st = {
            "playing": bool(payload.get("playing")) and str(payload.get("status")) == "Playing",
            "status": str(payload.get("status", "Closed")),
            "app": str(payload.get("app", "") or ""),
            "title": str(payload.get("title", "") or ""),
            "artist": str(payload.get("artist", "") or ""),
        }
        self.state = st
        self.session_updated.emit(dict(st))
        if st["playing"]:
            self._hide_timer.stop()
            if not self.active:
                self.active = True
                self.playback_active_changed.emit(True)
        elif self.active and not self._hide_timer.isActive():
            self._hide_timer.start()

    def _commit_inactive(self):
        if not self.state.get("playing") and self.active:
            self.active = False
            self.playback_active_changed.emit(False)

    # ---------------------------------------------------------------- commands
    def play_pause(self) -> bool:
        return self._send("play_pause")

    def next_track(self) -> bool:
        return self._send("next")

    def prev_track(self) -> bool:
        return self._send("prev")

    def refresh(self) -> bool:
        return self._send("refresh")

    @staticmethod
    def friendly_app_name(app_id: str) -> str:
        a = (app_id or "").lower()
        for key, name in (("spotify", "Spotify"), ("chrome", "Chrome"), ("msedge", "Edge"), ("firefox", "Firefox"),
                          ("vlc", "VLC"), ("zunemusic", "Media Player"), ("music", "Música"), ("stremio", "Stremio")):
            if key in a:
                return name
        if not app_id:
            return ""
        base = app_id.split("!")[0].split("\\")[-1]
        return base.replace(".exe", "")[:24]

    def shutdown(self):
        self._running = False
        try:
            self._hide_timer.stop()
        except RuntimeError:
            pass
        if self._proc:
            if self._proc.poll() is None:
                try:
                    self._proc.stdin.write("exit\n")
                    self._proc.stdin.flush()
                    self._proc.wait(timeout=1.5)
                except Exception:
                    try:
                        self._proc.kill()
                    except Exception:
                        pass
            for stream in (self._proc.stdin, self._proc.stdout, self._proc.stderr):
                if stream:
                    try:
                        stream.close()
                    except Exception:
                        pass
        self._proc = None
