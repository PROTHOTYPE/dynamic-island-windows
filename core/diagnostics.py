"""
Sistema centralizado de diagnóstico, captura de exceções e telemetria de falhas do Monolith.
- Grava logs em %LOCALAPPDATA%\\Monolith\\Logs\\monolith.log (rotativo)
- Captura falhas nativas via faulthandler em %LOCALAPPDATA%\\Monolith\\Logs\\native_fault.log
- Instala sys.excepthook, threading.excepthook e qInstallMessageHandler
- Nunca grava senhas de Wi-Fi, credenciais ou keyMaterial nos logs
"""

import ctypes
import faulthandler
import logging
from logging.handlers import RotatingFileHandler
import os
import re
import sys
import threading

from PyQt6.QtCore import QtMsgType, qInstallMessageHandler

from core.paths import get_logs_dir

_LOGGER = None
_FAULT_FILE = None
_INITIALIZED = False

_SENSITIVE_PATTERNS = [
    (re.compile(r"(<keyMaterial>)(.*?)(</keyMaterial>)", re.IGNORECASE | re.DOTALL), r"\1[REDACTED]\3"),
    (re.compile(r"(password\s*[=:]\s*)(\S+)", re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"(passphrase\s*[=:]\s*)(\S+)", re.IGNORECASE), r"\1[REDACTED]"),
]


def sanitize_message(text: str) -> str:
    """Remove possíveis senhas ou segredos antes de registrar qualquer entrada de log."""
    if not text:
        return ""
    clean = str(text)
    for pattern, repl in _SENSITIVE_PATTERNS:
        clean = pattern.sub(repl, clean)
    return clean


class _SanitizingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
            clean = sanitize_message(msg)
            if clean != msg:
                record.msg = clean
                record.args = ()
        except Exception:
            pass
        return True


def _enable_debug_console():
    """Aloca/anexa console sob demanda quando iniciado com --console ou MONOLITH_CONSOLE=1."""
    try:
        kernel32 = ctypes.windll.kernel32
        ATTACH_PARENT_PROCESS = -1
        if not kernel32.AttachConsole(ATTACH_PARENT_PROCESS):
            kernel32.AllocConsole()
        sys.stdout = open("CONOUT$", "w", encoding="utf-8", buffering=1)
        sys.stderr = open("CONOUT$", "w", encoding="utf-8", buffering=1)
    except Exception:
        pass


def get_logger() -> logging.Logger:
    global _LOGGER
    if _LOGGER is None:
        _LOGGER = logging.getLogger("Monolith")
        _LOGGER.setLevel(logging.INFO)
    return _LOGGER


def setup_diagnostics(console_mode: bool = False) -> logging.Logger:
    """Inicializa logs rotativos, faulthandler e ganchos globais de exceção."""
    global _INITIALIZED, _FAULT_FILE
    logger = get_logger()
    if _INITIALIZED:
        return logger

    if console_mode or os.environ.get("MONOLITH_CONSOLE") == "1":
        if sys.stdout is None or sys.stderr is None:
            _enable_debug_console()

    logs_dir = get_logs_dir()
    log_path = os.path.join(logs_dir, "monolith.log")
    fault_path = os.path.join(logs_dir, "native_fault.log")

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] [%(threadName)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    san_filter = _SanitizingFilter()

    try:
        file_handler = RotatingFileHandler(
            log_path, maxBytes=2 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        file_handler.addFilter(san_filter)
        logger.addHandler(file_handler)
    except Exception:
        pass

    if console_mode or os.environ.get("MONOLITH_CONSOLE") == "1":
        try:
            stream = sys.stderr or sys.stdout
            if stream is not None:
                console_handler = logging.StreamHandler(stream)
                console_handler.setFormatter(formatter)
                console_handler.addFilter(san_filter)
                logger.addHandler(console_handler)
        except Exception:
            pass

    try:
        _FAULT_FILE = open(fault_path, "a", encoding="utf-8")
        faulthandler.enable(file=_FAULT_FILE, all_threads=True)
    except Exception:
        pass

    def _sys_excepthook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            return
        logger.critical(
            "Exceção não tratada na thread principal",
            exc_info=(exc_type, exc_value, exc_tb),
        )

    def _thread_excepthook(args):
        if issubclass(args.exc_type, SystemExit):
            return
        tname = getattr(args.thread, "name", "WorkerThread")
        logger.error(
            "Exceção não tratada em thread secundária (%s)",
            tname,
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    def _qt_message_handler(mode, context, message):
        msg = sanitize_message(message)
        if mode == QtMsgType.QtFatalMsg:
            logger.critical("QtFatal: %s", msg)
        elif mode == QtMsgType.QtCriticalMsg:
            logger.error("QtCritical: %s", msg)
        elif mode == QtMsgType.QtWarningMsg:
            # Ignora avisos benignos de QFont/QSS se repetitivos, mas registra para diagnóstico
            logger.warning("QtWarning: %s", msg)

    sys.excepthook = _sys_excepthook
    threading.excepthook = _thread_excepthook
    try:
        qInstallMessageHandler(_qt_message_handler)
    except Exception:
        pass

    _INITIALIZED = True
    logger.info("Diagnóstico inicializado (logs=%s)", logs_dir)
    return logger


def log_info(message: str, *args):
    try:
        get_logger().info(sanitize_message(message), *args)
    except Exception:
        pass


def log_warning(message: str, *args):
    try:
        get_logger().warning(sanitize_message(message), *args)
    except Exception:
        pass


def log_exception(context: str, exc: BaseException = None):
    try:
        logger = get_logger()
        clean_ctx = sanitize_message(context)
        if exc is not None:
            logger.exception("Falha em %s: %s", clean_ctx, sanitize_message(str(exc)))
        else:
            logger.exception("Falha em %s", clean_ctx)
    except Exception:
        pass


def shutdown_diagnostics():
    """Encerra handlers e descarrega arquivos de diagnóstico com segurança."""
    global _FAULT_FILE
    try:
        if faulthandler.is_enabled():
            faulthandler.disable()
    except Exception:
        pass
    try:
        if _FAULT_FILE:
            _FAULT_FILE.flush()
            _FAULT_FILE.close()
            _FAULT_FILE = None
    except Exception:
        pass
    try:
        logging.shutdown()
    except Exception:
        pass
