"""
Resolvedor centralizado de caminhos e recursos do Monolith.
Compatível com execução via código-fonte e via bundle PyInstaller (--onedir).
Nunca grava configurações ou logs dentro do diretório interno do executável.
"""

import os
import sys
import shutil

APP_NAME = "Monolith"
APP_VERSION = "0.2.0-rc2"


def is_frozen() -> bool:
    """Retorna True quando executado a partir do executável empacotado PyInstaller."""
    return bool(getattr(sys, "frozen", False))


def get_bundle_dir() -> str:
    """Diretório raiz de leitura dos recursos embutidos (somente leitura em produção)."""
    if is_frozen():
        if hasattr(sys, "_MEIPASS"):
            return sys._MEIPASS
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_executable_dir() -> str:
    """Diretório onde está localizado o Monolith.exe (ou raiz do repositório em desenvolvimento)."""
    if is_frozen():
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_resource_path(*parts: str) -> str:
    """Resolve o caminho absoluto de um recurso embutido (worker PS1, config padrão, ícones, etc.)."""
    candidate = os.path.join(get_bundle_dir(), *parts)
    if os.path.exists(candidate):
        return candidate
    fallback = os.path.join(get_executable_dir(), *parts)
    if os.path.exists(fallback):
        return fallback
    return candidate


def get_app_data_dir() -> str:
    """Retorna %LOCALAPPDATA%\\Monolith para preferências e dados graváveis do usuário."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        local_app_data = os.path.join(os.path.expanduser("~"), "AppData", "Local")
    path = os.path.join(local_app_data, APP_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def get_logs_dir() -> str:
    """Retorna %LOCALAPPDATA%\\Monolith\\Logs."""
    path = os.path.join(get_app_data_dir(), "Logs")
    os.makedirs(path, exist_ok=True)
    return path


def get_config_file() -> str:
    """
    Retorna %LOCALAPPDATA%\\Monolith\\appearance.json.
    Se ainda não existir, inicializa a partir da configuração padrão do bundle (somente leitura).
    """
    target = os.path.join(get_app_data_dir(), "appearance.json")
    if not os.path.exists(target):
        default_cfg = get_resource_path("config", "appearance.json")
        if os.path.exists(default_cfg):
            try:
                shutil.copyfile(default_cfg, target)
            except Exception:
                pass
    return target
