"""
Módulo 3 — Adaptador de Áudio Nativo (CoreAudio & IPolicyConfig)
Implementa:
- Enumeração de endpoints de reprodução de áudio (IMMDeviceEnumerator)
- Identificação do endpoint de áudio padrão do sistema
- Alteração atômica de saída de áudio via IPolicyConfig com múltiplos GUIDs
- Fallback gracioso para ms-settings:sound
- Controle de volume master e silenciamento (IAudioEndpointVolume)
- Notificação de eventos de hardware e sincronização reativa com PyQt6
- Totalmente isolado fora da thread de renderização com tratamento defensivo de exceções
"""

import os
import sys
import threading
import ctypes
from ctypes import wintypes, POINTER, c_wchar_p, c_int, c_uint, c_float, byref

import comtypes
import comtypes.client
from comtypes import IUnknown, GUID, COMMETHOD, HRESULT

from PyQt6.QtCore import QObject, pyqtSignal

from core.diagnostics import log_exception

ole32 = ctypes.windll.ole32

# ==============================================================================
# DEFINIÇÃO DE INTERFACES COM DO COREAUDIO
# ==============================================================================

CLSID_MMDeviceEnumerator = GUID("{BCDE0395-E52F-467C-8E3D-C4579291692E}")
IID_IMMDeviceEnumerator = GUID("{A95664D2-9614-4F35-A746-DE8DB63617E6}")
IID_IMMDevice = GUID("{D666063F-1587-4E43-8187-E0643771E0FA}")
IID_IPropertyStore = GUID("{886d8eeb-8cf2-4446-8d02-cdba1dbdcf99}")
IID_IAudioEndpointVolume = GUID("{5CDF2C82-841E-4546-9722-0CF74078229A}")

# PROPERTYKEY para PKEY_Device_FriendlyName: {a45c254e-df1c-4efd-8020-67d146a850e0}, 14
class PROPERTYKEY(ctypes.Structure):
    _fields_ = [("fmtid", GUID), ("pid", wintypes.DWORD)]

PKEY_Device_FriendlyName = PROPERTYKEY(GUID("{a45c254e-df1c-4efd-8020-67d146a850e0}"), 14)

class PROPVARIANT(ctypes.Structure):
    _fields_ = [
        ("vt", wintypes.WORD),
        ("wReserved1", wintypes.WORD),
        ("wReserved2", wintypes.WORD),
        ("wReserved3", wintypes.WORD),
        ("pwszVal", c_wchar_p)
    ]

ole32.PropVariantClear.argtypes = [POINTER(PROPVARIANT)]
ole32.PropVariantClear.restype = HRESULT

class IPropertyStore(IUnknown):
    _iid_ = IID_IPropertyStore
    _methods_ = [
        COMMETHOD([], HRESULT, "GetCount", (["out"], POINTER(wintypes.DWORD), "cProps")),
        COMMETHOD([], HRESULT, "GetAt", (["in"], wintypes.DWORD, "iProp"), (["out"], POINTER(PROPERTYKEY), "pkey")),
        COMMETHOD([], HRESULT, "GetValue", (["in"], POINTER(PROPERTYKEY), "key"), (["out"], POINTER(PROPVARIANT), "pv")),
        COMMETHOD([], HRESULT, "SetValue", (["in"], POINTER(PROPERTYKEY), "key"), (["in"], POINTER(PROPVARIANT), "propvar")),
        COMMETHOD([], HRESULT, "Commit"),
    ]

class IAudioEndpointVolume(IUnknown):
    _iid_ = IID_IAudioEndpointVolume
    _methods_ = [
        COMMETHOD([], HRESULT, "RegisterControlChangeNotify", (["in"], ctypes.c_void_p, "pNotify")),
        COMMETHOD([], HRESULT, "UnregisterControlChangeNotify", (["in"], ctypes.c_void_p, "pNotify")),
        COMMETHOD([], HRESULT, "GetChannelCount", (["out"], POINTER(wintypes.UINT), "pnChannelCount")),
        COMMETHOD([], HRESULT, "SetMasterVolumeLevel", (["in"], c_float, "fLevelDB"), (["in"], POINTER(GUID), "pguidEventContext")),
        COMMETHOD([], HRESULT, "SetMasterVolumeLevelScalar", (["in"], c_float, "fLevel"), (["in"], POINTER(GUID), "pguidEventContext")),
        COMMETHOD([], HRESULT, "GetMasterVolumeLevel", (["out"], POINTER(c_float), "pfLevelDB")),
        COMMETHOD([], HRESULT, "GetMasterVolumeLevelScalar", (["out"], POINTER(c_float), "pfLevel")),
        COMMETHOD([], HRESULT, "SetChannelVolumeLevel"),
        COMMETHOD([], HRESULT, "SetChannelVolumeLevelScalar"),
        COMMETHOD([], HRESULT, "GetChannelVolumeLevel"),
        COMMETHOD([], HRESULT, "GetChannelVolumeLevelScalar"),
        COMMETHOD([], HRESULT, "SetMute", (["in"], wintypes.BOOL, "bMute"), (["in"], POINTER(GUID), "pguidEventContext")),
        COMMETHOD([], HRESULT, "GetMute", (["out"], POINTER(wintypes.BOOL), "pbMute")),
    ]

class IMMDevice(IUnknown):
    _iid_ = IID_IMMDevice
    _methods_ = [
        COMMETHOD([], HRESULT, "Activate",
                  (["in"], POINTER(GUID), "iid"),
                  (["in"], wintypes.DWORD, "dwClsCtx"),
                  (["in"], POINTER(c_int), "pActivationParams"),
                  (["out"], POINTER(POINTER(IUnknown)), "ppInterface")),
        COMMETHOD([], HRESULT, "OpenPropertyStore",
                  (["in"], wintypes.DWORD, "stgmAccess"),
                  (["out"], POINTER(POINTER(IPropertyStore)), "ppProperties")),
        COMMETHOD([], HRESULT, "GetId",
                  (["out"], POINTER(c_wchar_p), "ppstrId")),
        COMMETHOD([], HRESULT, "GetState",
                  (["out"], POINTER(wintypes.DWORD), "pdwState")),
    ]

class IMMDeviceCollection(IUnknown):
    _iid_ = GUID("{0BD7A1BE-7A1A-44DB-8397-CC5392387B5E}")
    _methods_ = [
        COMMETHOD([], HRESULT, "GetCount",
                  (["out"], POINTER(c_uint), "pcDevices")),
        COMMETHOD([], HRESULT, "Item",
                  (["in"], c_uint, "nDevice"),
                  (["out"], POINTER(POINTER(IMMDevice)), "ppDevice")),
    ]

class IMMDeviceEnumerator(IUnknown):
    _iid_ = IID_IMMDeviceEnumerator
    _methods_ = [
        COMMETHOD([], HRESULT, "EnumAudioEndpoints",
                  (["in"], c_int, "dataFlow"),
                  (["in"], wintypes.DWORD, "dwStateMask"),
                  (["out"], POINTER(POINTER(IMMDeviceCollection)), "ppDevices")),
        COMMETHOD([], HRESULT, "GetDefaultAudioEndpoint",
                  (["in"], c_int, "dataFlow"),
                  (["in"], c_int, "role"),
                  (["out"], POINTER(POINTER(IMMDevice)), "ppEndpoint")),
    ]

# ==============================================================================
# INTERFACES NÃO DOCUMENTADAS: IPolicyConfig (Isolamento Defensivo)
# ==============================================================================

CLSID_CPolicyConfigClient = GUID("{870af99c-171d-4f9e-af0d-e63df40c2bc9}")

# Layout para GUID {f8679f50-850a-41cf-9c72-430f290290c8} (Validado no Win11 Build 26300)
class IPolicyConfigVista(IUnknown):
    _iid_ = GUID("{f8679f50-850a-41cf-9c72-430f290290c8}")
    _methods_ = [
        COMMETHOD([], HRESULT, "GetMixFormat"),
        COMMETHOD([], HRESULT, "GetDeviceFormat"),
        COMMETHOD([], HRESULT, "ResetDeviceFormat"),
        COMMETHOD([], HRESULT, "SetDeviceFormat"),
        COMMETHOD([], HRESULT, "GetProcessingPeriod"),
        COMMETHOD([], HRESULT, "SetProcessingPeriod"),
        COMMETHOD([], HRESULT, "GetShareMode"),
        COMMETHOD([], HRESULT, "SetShareMode"),
        COMMETHOD([], HRESULT, "GetPropertyValue"),
        COMMETHOD([], HRESULT, "SetPropertyValue"),
        COMMETHOD([], HRESULT, "SetDefaultEndpoint",
                  (["in"], c_wchar_p, "wszDeviceId"),
                  (["in"], c_int, "role")),
        COMMETHOD([], HRESULT, "SetEndpointVisibility"),
    ]

# Layout para GUID {870af99c-171d-4f9e-af0d-e63df40c2bc9} (Win10 Original)
class IPolicyConfigWin10(IUnknown):
    _iid_ = GUID("{870af99c-171d-4f9e-af0d-e63df40c2bc9}")
    _methods_ = [
        COMMETHOD([], HRESULT, "GetMixFormat"),
        COMMETHOD([], HRESULT, "GetDeviceFormat"),
        COMMETHOD([], HRESULT, "ResetDeviceFormat"),
        COMMETHOD([], HRESULT, "SetDeviceFormat"),
        COMMETHOD([], HRESULT, "GetProcessingPeriod"),
        COMMETHOD([], HRESULT, "SetProcessingPeriod"),
        COMMETHOD([], HRESULT, "GetShareMode"),
        COMMETHOD([], HRESULT, "SetShareMode"),
        COMMETHOD([], HRESULT, "GetPropertyValue"),
        COMMETHOD([], HRESULT, "SetPropertyValue"),
        COMMETHOD([], HRESULT, "SetDefaultEndpoint",
                  (["in"], c_wchar_p, "wszDeviceId"),
                  (["in"], c_int, "role")),
        COMMETHOD([], HRESULT, "SetEndpointVisibility"),
    ]

# ==============================================================================
# CLASSE PRINCIPAL: AudioEndpointAdapter
# ==============================================================================

class AudioEndpointAdapter(QObject):
    """
    Adaptador defensivo e thread-safe de controle de áudio CoreAudio.
    Gerencia enumeração de dispositivos, volume master e troca de saída padrão.
    """
    
    devices_updated = pyqtSignal(list)            # Lista de dispositivos de reprodução ativos
    default_device_changed = pyqtSignal(str, str) # (dev_id, dev_name)
    volume_changed = pyqtSignal(int)              # Percentual de volume (0 a 100)
    mute_changed = pyqtSignal(bool)               # True = Mudo, False = Normal
    open_settings_requested = pyqtSignal(str)     # URI para abrir na thread gráfica
    audio_error = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._lock = threading.Lock()
        self._vol_write_lock = threading.Lock()
        self._pending_volume = None
        self._volume_worker_active = False
        self._cached_devices = []
        self._current_default = None
        self._current_volume = 100
        self._is_muted = False
        
        # Faz uma leitura inicial
        self.refresh()

    def refresh(self):
        """Dispara atualização assíncrona dos endpoints de áudio."""
        threading.Thread(target=self._refresh_worker, daemon=True).start()

    def _refresh_worker(self):
        with self._lock:
            comtypes.CoInitialize()
            try:
                enumerator = comtypes.client.CreateObject(
                    CLSID_MMDeviceEnumerator,
                    interface=IMMDeviceEnumerator
                )
                
                # 1. Obtém endpoint padrão atual (eRender = 0, eConsole = 0)
                def_id = ""
                def_name = ""
                try:
                    def_dev = enumerator.GetDefaultAudioEndpoint(0, 0)
                    def_id = def_dev.GetId()
                    props = def_dev.OpenPropertyStore(0)
                    pv = props.GetValue(byref(PKEY_Device_FriendlyName))
                    try:
                        def_name = pv.pwszVal if pv.pwszVal else "Dispositivo Padrão"
                    finally:
                        ole32.PropVariantClear(byref(pv))
                    
                    # Lê volume e mute do endpoint padrão
                    CLSCTX_INPROC_SERVER = 0x1
                    vol_ctl = def_dev.Activate(byref(IID_IAudioEndpointVolume), CLSCTX_INPROC_SERVER, None)
                    vol_ctl = vol_ctl.QueryInterface(IAudioEndpointVolume)
                    v_scalar = vol_ctl.GetMasterVolumeLevelScalar()
                    m_val = vol_ctl.GetMute()
                    self._current_volume = int(round(v_scalar * 100))
                    self._is_muted = bool(m_val)
                    self.volume_changed.emit(self._current_volume)
                    self.mute_changed.emit(self._is_muted)
                except Exception as e:
                    self.audio_error.emit(f"Erro ao ler endpoint padrão: {e}")

                # 2. Enumera todos os dispositivos ativos (eRender = 0, DEVICE_STATE_ACTIVE = 1)
                col = enumerator.EnumAudioEndpoints(0, 1)
                count = col.GetCount()
                dev_list = []
                
                for i in range(count):
                    try:
                        dev = col.Item(i)
                        did = dev.GetId()
                        props = dev.OpenPropertyStore(0)
                        pv = props.GetValue(byref(PKEY_Device_FriendlyName))
                        try:
                            name = pv.pwszVal if pv.pwszVal else f"Saída {i+1}"
                        finally:
                            ole32.PropVariantClear(byref(pv))
                        is_def = (did == def_id)
                        
                        # Determina tipo de ícone visual
                        icon_type = "headphones" if any(k in name.lower() for k in ["fone", "headphone", "headset", "tune", "wh-"]) else (
                            "screen" if any(k in name.lower() for k in ["displayport", "hdmi", "monitor", "tv", "ultragear"]) else "speaker"
                        )
                        
                        dev_list.append({
                            "id": did,
                            "name": name,
                            "is_default": is_def,
                            "icon_type": icon_type
                        })
                    except Exception:
                        continue
                        
                self._cached_devices = dev_list
                self._current_default = {"id": def_id, "name": def_name}
                self.devices_updated.emit(dev_list)
                if def_id:
                    self.default_device_changed.emit(def_id, def_name)

            except Exception as e:
                self.audio_error.emit(f"Erro ao enumerar dispositivos de áudio: {e}")
            finally:
                comtypes.CoUninitialize()

    # ==========================================================================
    # CONTROLE DE DISPOSITIVO PADRÃO (IPolicyConfig com Fallback)
    # ==========================================================================

    def set_default_device(self, dev_id: str):
        """Altera a saída de áudio padrão de forma defensiva e assíncrona."""
        threading.Thread(target=self._set_default_worker, args=(dev_id,), daemon=True).start()

    def _set_default_worker(self, dev_id: str):
        with self._lock:
            comtypes.CoInitialize()
            success = False
            try:
                # 1. Tenta instanciar IPolicyConfig com GUID Vista/7/8/Win11 Build 26300
                try:
                    policy = comtypes.client.CreateObject(CLSID_CPolicyConfigClient, interface=IPolicyConfigVista)
                    hr0 = policy.SetDefaultEndpoint(dev_id, 0) # eConsole
                    hr1 = policy.SetDefaultEndpoint(dev_id, 1) # eMultimedia
                    if hr0 == 0 and hr1 == 0:
                        success = True
                except Exception:
                    pass

                # 2. Se falhou, tenta GUID Win10 original
                if not success:
                    try:
                        policy10 = comtypes.client.CreateObject(CLSID_CPolicyConfigClient, interface=IPolicyConfigWin10)
                        hr0 = policy10.SetDefaultEndpoint(dev_id, 0)
                        hr1 = policy10.SetDefaultEndpoint(dev_id, 1)
                        if hr0 == 0 and hr1 == 0:
                            success = True
                    except Exception:
                        pass

                # 3. Se nenhuma interface COM funcionou -> Fallback seguro na thread gráfica
                if not success:
                    self.audio_error.emit("Troca automática não suportada pela versão do Windows. Abrindo configurações de som.")
                    self.open_settings_requested.emit("ms-settings:sound")
                else:
                    # Sucesso! Atualiza cache e emite sinal
                    target_name = next((d["name"] for d in self._cached_devices if d["id"] == dev_id), "Saída Selecionada")
                    for d in self._cached_devices:
                        d["is_default"] = (d["id"] == dev_id)
                    self._current_default = {"id": dev_id, "name": target_name}
                    self.devices_updated.emit(self._cached_devices)
                    self.default_device_changed.emit(dev_id, target_name)

            except Exception as e:
                self.audio_error.emit(f"Falha ao trocar saída de áudio: {e}")
                self.open_settings_requested.emit("ms-settings:sound")
            finally:
                comtypes.CoUninitialize()

    # ==========================================================================
    # CONTROLE DE VOLUME MASTER E MUTE
    # ==========================================================================

    def set_volume(self, percent: int):
        """Define o volume master do endpoint padrão (0 a 100) com coalescência de arraste."""
        clamped = max(0, min(100, int(percent)))
        self._current_volume = clamped
        self.volume_changed.emit(clamped)
        with self._vol_write_lock:
            self._pending_volume = clamped
            if not self._volume_worker_active:
                self._volume_worker_active = True
                threading.Thread(target=self._set_volume_loop, daemon=True).start()

    def _set_volume_loop(self):
        while True:
            with self._vol_write_lock:
                target = self._pending_volume
                self._pending_volume = None
                if target is None:
                    self._volume_worker_active = False
                    return
            self._set_volume_worker(target)

    def _set_volume_worker(self, percent: int):
        with self._lock:
            comtypes.CoInitialize()
            enumerator = def_dev = vol_ctl = None
            try:
                enumerator = comtypes.client.CreateObject(
                    CLSID_MMDeviceEnumerator,
                    interface=IMMDeviceEnumerator
                )
                def_dev = enumerator.GetDefaultAudioEndpoint(0, 0)
                CLSCTX_INPROC_SERVER = 0x1
                vol_ctl = def_dev.Activate(byref(IID_IAudioEndpointVolume), CLSCTX_INPROC_SERVER, None)
                vol_ctl = vol_ctl.QueryInterface(IAudioEndpointVolume)
                scalar = float(percent) / 100.0
                vol_ctl.SetMasterVolumeLevelScalar(scalar, None)
            except Exception as e:
                log_exception("AudioEndpointAdapter._set_volume_worker", e)
                self.audio_error.emit(f"Erro ao definir volume: {e}")
            finally:
                vol_ctl = None
                def_dev = None
                enumerator = None
                comtypes.CoUninitialize()

    def set_mute(self, is_muted: bool):
        """Ativa ou desativa o mudo da saída de áudio padrão."""
        self._is_muted = is_muted
        self.mute_changed.emit(is_muted)
        threading.Thread(target=self._set_mute_worker, args=(is_muted,), daemon=True).start()

    def _set_mute_worker(self, is_muted: bool):
        with self._lock:
            comtypes.CoInitialize()
            enumerator = def_dev = vol_ctl = None
            try:
                enumerator = comtypes.client.CreateObject(
                    CLSID_MMDeviceEnumerator,
                    interface=IMMDeviceEnumerator
                )
                def_dev = enumerator.GetDefaultAudioEndpoint(0, 0)
                CLSCTX_INPROC_SERVER = 0x1
                vol_ctl = def_dev.Activate(byref(IID_IAudioEndpointVolume), CLSCTX_INPROC_SERVER, None)
                vol_ctl = vol_ctl.QueryInterface(IAudioEndpointVolume)
                vol_ctl.SetMute(wintypes.BOOL(is_muted), None)
            except Exception as e:
                log_exception("AudioEndpointAdapter._set_mute_worker", e)
                self.audio_error.emit(f"Erro ao alternar mudo: {e}")
            finally:
                vol_ctl = None
                def_dev = None
                enumerator = None
                comtypes.CoUninitialize()

    def toggle_mute(self):
        """Alterna estado de mudo."""
        self.set_mute(not self._is_muted)

    def get_cached_devices(self) -> list:
        return list(self._cached_devices)

    def get_cached_default(self) -> dict:
        return dict(self._current_default) if self._current_default else None

    def get_cached_volume(self) -> int:
        return self._current_volume

    def is_muted(self) -> bool:
        return self._is_muted
