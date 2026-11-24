import ctypes
import win32con


class MediaController:
    """
    Controlador de transporte de mídia do Monolith.
    Encaminha comandos para o MediaSessionAdapter (SMTC real do Windows) quando vinculado
    e utiliza teclas virtuais VK_MEDIA_* como fallback de compatibilidade.
    Nunca infere reprodução ativa apenas pela existência de processos abertos.
    """

    VK_PLAY_PAUSE = win32con.VK_MEDIA_PLAY_PAUSE
    VK_NEXT = win32con.VK_MEDIA_NEXT_TRACK
    VK_PREV = win32con.VK_MEDIA_PREV_TRACK
    VK_MUTE = win32con.VK_VOLUME_MUTE

    _adapter = None

    @classmethod
    def bind_adapter(cls, adapter):
        cls._adapter = adapter

    @classmethod
    def play_pause(cls):
        if cls._adapter is not None and cls._adapter.play_pause():
            return
        cls._send_vk(cls.VK_PLAY_PAUSE)

    @classmethod
    def next_track(cls):
        if cls._adapter is not None and cls._adapter.next_track():
            return
        cls._send_vk(cls.VK_NEXT)

    @classmethod
    def prev_track(cls):
        if cls._adapter is not None and cls._adapter.prev_track():
            return
        cls._send_vk(cls.VK_PREV)

    @classmethod
    def toggle_mute(cls):
        cls._send_vk(cls.VK_MUTE)

    @staticmethod
    def _send_vk(vk_code: int):
        try:
            ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0)
            ctypes.windll.user32.keybd_event(vk_code, 0, 2, 0)  # KEYEVENTF_KEYUP
        except Exception:
            pass

    @classmethod
    def get_active_media(cls) -> dict:
        if cls._adapter is not None:
            st = cls._adapter.state
            is_playing = bool(cls._adapter.active and st.get("playing"))
            if is_playing:
                app_name = cls._adapter.friendly_app_name(st.get("app", "")) or "Mídia"
                title = st.get("title") or f"Reproduzindo em {app_name}"
                artist = st.get("artist") or app_name
                return {
                    "active": True,
                    "playing": True,
                    "status": "Em reprodução ativa",
                    "app": app_name,
                    "title": title,
                    "artist": artist,
                    "icon": "🎵",
                }
        return {
            "active": False,
            "playing": False,
            "app": "Windows Media",
            "title": "Nenhuma mídia em reprodução",
            "artist": "",
            "status": "Inativo",
            "icon": "🎧",
        }
