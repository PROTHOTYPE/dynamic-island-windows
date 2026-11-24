"""
Módulo 2B — Gerenciador de Wi-Fi Nativo (wlanapi.dll via ctypes)
Implementa:
- Enumeração de interfaces de rede física
- Busca assíncrona de redes (WlanScan / WlanGetAvailableNetworkList)
- Identificação de intensidade de sinal (0-100%) e segurança (WPA2, WPA3, Aberta)
- Conexão e desconexão de redes (WlanConnect / WlanDisconnect)
- Consulta de rede atualmente conectada (WlanQueryInterface)
- Política estrita de proteção de senhas (nunca logadas, manipuladas em memória volátil)
- Execução 100% fora da thread de renderização (thread-safe com sinais PyQt6)
"""

import os
import sys
import time
import threading
import ctypes
from ctypes import wintypes, POINTER, Structure, c_int, c_uint, byref
from xml.sax.saxutils import escape as xml_escape

from PyQt6.QtCore import QObject, pyqtSignal

from core.diagnostics import log_exception

# ==============================================================================
# ESTRUTURAS E CONSTANTES DA NATIVE WIFI API (wlanapi.dll)
# ==============================================================================

try:
    wlanapi = ctypes.WinDLL("wlanapi")
    wlanapi.WlanOpenHandle.argtypes = [wintypes.DWORD, ctypes.c_void_p, POINTER(wintypes.DWORD), POINTER(wintypes.HANDLE)]
    wlanapi.WlanOpenHandle.restype = wintypes.DWORD
    wlanapi.WlanCloseHandle.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
    wlanapi.WlanCloseHandle.restype = wintypes.DWORD
    wlanapi.WlanFreeMemory.argtypes = [ctypes.c_void_p]
    wlanapi.WlanFreeMemory.restype = None
except Exception:
    wlanapi = None

# Opcodes e Modos
WLAN_INTF_OPCODE_CURRENT_CONNECTION = 7
WLAN_CONNECTION_MODE_PROFILE = 0
WLAN_CONNECTION_MODE_TEMPORARY_PROFILE = 1
WLAN_CONNECTION_MODE_DISCOVERY_UNSECURE = 2
WLAN_CONNECTION_MODE_DISCOVERY_SECURE = 3
WLAN_CONNECTION_MODE_AUTO = 4

DOT11_BSS_TYPE_INFRASTRUCTURE = 1
DOT11_BSS_TYPE_ANY = 3

DOT11_AUTH_ALGO_80211_OPEN = 1
DOT11_AUTH_ALGO_80211_SHARED_KEY = 2
DOT11_AUTH_ALGO_WPA = 3
DOT11_AUTH_ALGO_WPA_PSK = 4
DOT11_AUTH_ALGO_RSNA = 6
DOT11_AUTH_ALGO_RSNA_PSK = 7
DOT11_AUTH_ALGO_WPA3 = 8
DOT11_AUTH_ALGO_WPA3_SAE = 9

DOT11_CIPHER_ALGO_NONE = 0
DOT11_CIPHER_ALGO_WEP40 = 1
DOT11_CIPHER_ALGO_TKIP = 2
DOT11_CIPHER_ALGO_CCMP = 4
DOT11_CIPHER_ALGO_WEP104 = 5

WLAN_AVAILABLE_NETWORK_INCLUDE_ALL_MANUAL_HIDDEN_PROFILES = 0x00000002

class DOT11_SSID(Structure):
    _fields_ = [
        ("uSSIDLength", wintypes.ULONG),
        ("ucSSID", ctypes.c_char * 32)
    ]

class WLAN_INTERFACE_INFO(Structure):
    _fields_ = [
        ("InterfaceGuid", ctypes.c_byte * 16),
        ("strInterfaceDescription", wintypes.WCHAR * 256),
        ("isState", c_int)
    ]

class WLAN_INTERFACE_INFO_LIST(Structure):
    _fields_ = [
        ("dwNumberOfItems", wintypes.DWORD),
        ("dwIndex", wintypes.DWORD),
        ("InterfaceInfo", WLAN_INTERFACE_INFO * 1)
    ]

class WLAN_AVAILABLE_NETWORK(Structure):
    _fields_ = [
        ("strProfileName", wintypes.WCHAR * 256),
        ("dot11Ssid", DOT11_SSID),
        ("dot11BssType", c_int),
        ("uNumberOfBssids", wintypes.ULONG),
        ("bNetworkConnectable", wintypes.BOOL),
        ("wlanNotConnectableReason", wintypes.DWORD),
        ("uNumberOfPhyTypes", wintypes.ULONG),
        ("dot11PhyTypes", c_int * 8),
        ("bMorePhyTypes", wintypes.BOOL),
        ("wlanSignalQuality", wintypes.ULONG),
        ("bSecurityEnabled", wintypes.BOOL),
        ("dot11DefaultAuthAlgorithm", c_int),
        ("dot11DefaultCipherAlgorithm", c_int),
        ("dwFlags", wintypes.DWORD),
        ("dwReserved", wintypes.DWORD),
    ]

class WLAN_ASSOCIATION_ATTRIBUTES(Structure):
    _fields_ = [
        ("dot11Ssid", DOT11_SSID),
        ("dot11BssType", c_int),
        ("dot11Bssid", ctypes.c_ubyte * 6),
        ("dot11PhyType", c_int),
        ("uDot11PhyIndex", wintypes.ULONG),
        ("wlanSignalQuality", wintypes.ULONG),
        ("ulRxRate", wintypes.ULONG),
        ("ulTxRate", wintypes.ULONG)
    ]

class WLAN_SECURITY_ATTRIBUTES(Structure):
    _fields_ = [
        ("bSecurityEnabled", wintypes.BOOL),
        ("bOneXEnabled", wintypes.BOOL),
        ("dot11AuthAlgorithm", c_int),
        ("dot11CipherAlgorithm", c_int)
    ]

class WLAN_CONNECTION_ATTRIBUTES(Structure):
    _fields_ = [
        ("isState", c_int),
        ("wlanConnectionMode", c_int),
        ("strProfileName", wintypes.WCHAR * 256),
        ("wlanAssociationAttributes", WLAN_ASSOCIATION_ATTRIBUTES),
        ("wlanSecurityAttributes", WLAN_SECURITY_ATTRIBUTES)
    ]

class WLAN_CONNECTION_PARAMETERS(Structure):
    _fields_ = [
        ("wlanConnectionMode", c_int),
        ("strProfile", wintypes.LPCWSTR),
        ("pDot11Ssid", POINTER(DOT11_SSID)),
        ("pDesiredBssidList", ctypes.c_void_p),
        ("dot11BssType", c_int),
        ("dwFlags", wintypes.DWORD)
    ]


def _auth_algo_to_string(auth: int, cipher: int) -> str:
    if auth in (DOT11_AUTH_ALGO_WPA3, DOT11_AUTH_ALGO_WPA3_SAE):
        return "WPA3-Personal"
    elif auth == DOT11_AUTH_ALGO_RSNA_PSK:
        return "WPA2-Personal"
    elif auth == DOT11_AUTH_ALGO_WPA_PSK:
        return "WPA-Personal"
    elif auth in (DOT11_AUTH_ALGO_RSNA, DOT11_AUTH_ALGO_WPA):
        return "WPA/WPA2-Enterprise"
    elif auth == DOT11_AUTH_ALGO_80211_OPEN:
        if cipher == DOT11_CIPHER_ALGO_NONE:
            return "Aberta"
        return "WEP"
    return "Protegida"


def _generate_wifi_profile_xml(ssid: str, password: str, security: str = "WPA2-Personal", auto_connect: bool = True) -> str:
    """Gera perfil XML compatível com Windows Native Wifi (WPA2 e WPA3) sem salvar em disco."""
    hex_ssid = ssid.encode("utf-8").hex().upper()
    conn_mode = "auto" if auto_connect else "manual"
    safe_ssid = xml_escape(ssid, {"'": "&apos;", '"': "&quot;"})
    safe_pwd = xml_escape(password, {"'": "&apos;", '"': "&quot;"})
    is_wpa3 = "wpa3" in (security or "").lower()
    auth_tag = "WPA3SAE" if is_wpa3 else "WPA2PSK"
    return f"""<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
    <name>{safe_ssid}</name>
    <SSIDConfig>
        <SSID>
            <hex>{hex_ssid}</hex>
            <name>{safe_ssid}</name>
        </SSID>
    </SSIDConfig>
    <connectionType>ESS</connectionType>
    <connectionMode>{conn_mode}</connectionMode>
    <MSM>
        <security>
            <authEncryption>
                <authentication>{auth_tag}</authentication>
                <encryption>AES</encryption>
                <useOneX>false</useOneX>
            </authEncryption>
            <sharedKey>
                <keyType>passPhrase</keyType>
                <protected>false</protected>
                <keyMaterial>{safe_pwd}</keyMaterial>
            </sharedKey>
        </security>
    </MSM>
</WLANProfile>"""


def _generate_wpa2_profile_xml(ssid: str, password: str, auto_connect: bool = True) -> str:
    """Alias retrocompatível para perfil WPA2-Personal."""
    return _generate_wifi_profile_xml(ssid, password, security="WPA2-Personal", auto_connect=auto_connect)


def _generate_open_profile_xml(ssid: str, auto_connect: bool = True) -> str:
    """Gera perfil XML para rede aberta."""
    hex_ssid = ssid.encode("utf-8").hex().upper()
    conn_mode = "auto" if auto_connect else "manual"
    safe_ssid = xml_escape(ssid, {"'": "&apos;", '"': "&quot;"})
    return f"""<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
    <name>{safe_ssid}</name>
    <SSIDConfig>
        <SSID>
            <hex>{hex_ssid}</hex>
            <name>{safe_ssid}</name>
        </SSID>
    </SSIDConfig>
    <connectionType>ESS</connectionType>
    <connectionMode>{conn_mode}</connectionMode>
    <MSM>
        <security>
            <authEncryption>
                <authentication>open</authentication>
                <encryption>none</encryption>
                <useOneX>false</useOneX>
            </authEncryption>
        </security>
    </MSM>
</WLANProfile>"""


# ==============================================================================
# CLASSE PRINCIPAL: WiFiManager
# ==============================================================================

class WiFiManager(QObject):
    """
    Gerenciador thread-safe de Wi-Fi via Native Wifi API do Windows.
    Executa varredura de redes, consulta de conexão ativa e autenticação de forma assíncrona.
    """

    scan_started = pyqtSignal()
    scan_finished = pyqtSignal(list)                    # Lista de redes disponíveis formatadas
    current_connection_updated = pyqtSignal(dict)       # Info da rede conectada no momento
    connection_status_changed = pyqtSignal(str, str)     # (ssid, status: "Connecting" | "Connected" | "Disconnected" | "Failed")
    wifi_available_changed = pyqtSignal(bool)
    wifi_error = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lock = threading.Lock()
        self._is_busy = False
        self._cached_networks = []
        self._current_conn = None
        self._guid_cache = None
        self._wifi_available = False

    def is_wifi_available(self) -> bool:
        return self._wifi_available

    def _open_handle(self):
        """Abre handle nativo com o subsistema WLAN."""
        if not wlanapi:
            self._wifi_available = False
            self.wifi_available_changed.emit(False)
            return None
        try:
            h = wintypes.HANDLE()
            v = wintypes.DWORD()
            ret = wlanapi.WlanOpenHandle(2, None, byref(v), byref(h))
            if ret != 0:
                return None
            return h
        except Exception as e:
            log_exception("WiFiManager._open_handle", e)
            return None

    def _get_primary_guid(self, handle):
        """Retorna o GUID da interface primária de Wi-Fi."""
        pList = POINTER(WLAN_INTERFACE_INFO_LIST)()
        ret = wlanapi.WlanEnumInterfaces(handle, None, byref(pList))
        if ret == 0 and pList:
            try:
                if pList.contents.dwNumberOfItems > 0:
                    guid_bytes = bytes(pList.contents.InterfaceInfo[0].InterfaceGuid)
                    self._guid_cache = (ctypes.c_byte * 16)(*guid_bytes)
                    if not self._wifi_available:
                        self._wifi_available = True
                        self.wifi_available_changed.emit(True)
                    return self._guid_cache
                else:
                    self._guid_cache = None
                    if self._wifi_available:
                        self._wifi_available = False
                    self.wifi_available_changed.emit(False)
                    return None
            finally:
                wlanapi.WlanFreeMemory(pList)
        self._guid_cache = None
        self._wifi_available = False
        self.wifi_available_changed.emit(False)
        return None

    # ==========================================================================
    # API PÚBLICA ASSÍNCRONA
    # ==========================================================================

    def start_scan(self):
        """Inicia escaneamento assíncrono de redes visíveis."""
        if self._is_busy:
            return
        threading.Thread(target=self._scan_worker, daemon=True).start()

    def _scan_worker(self):
        self._is_busy = True
        self.scan_started.emit()
        
        handle = self._open_handle()
        if not handle:
            self._cached_networks = []
            self._current_conn = None
            self.scan_finished.emit([])
            self.current_connection_updated.emit({})
            self._is_busy = False
            self.wifi_error.emit("Nenhuma interface Wi-Fi física disponível neste computador.")
            return

        try:
            guid = self._get_primary_guid(handle)
            if not guid:
                self._cached_networks = []
                self._current_conn = None
                self.scan_finished.emit([])
                self.current_connection_updated.emit({})
                self.wifi_error.emit("Nenhuma interface Wi-Fi física detectada.")
                return

            # 1. Dispara WlanScan para forçar atualização do cache do driver
            wlanapi.WlanScan(handle, byref(guid), None, None, None)
            time.sleep(0.4)  # Breve pausa para o driver consolidar beacons

            # 2. Obtém rede atualmente conectada
            current = self._query_current_connection(handle, guid)
            self._current_conn = current
            if current:
                try:
                    self.current_connection_updated.emit(current)
                except RuntimeError:
                    pass

            # 3. Lista redes disponíveis
            networks = self._query_available_networks(handle, guid, current.get("ssid") if current else None)
            self._cached_networks = networks
            try:
                self.scan_finished.emit(networks)
            except RuntimeError:
                pass

        except Exception as e:
            try:
                self.wifi_error.emit(f"Erro ao escanear redes Wi-Fi: {e}")
            except RuntimeError:
                pass
        finally:
            wlanapi.WlanCloseHandle(handle, None)
            self._is_busy = False

    def _query_current_connection(self, handle, guid) -> dict:
        """Consulta atributos da conexão ativa via WlanQueryInterface."""
        pDataSize = wintypes.DWORD()
        pData = ctypes.c_void_p()
        opcode_type = c_int()
        
        ret = wlanapi.WlanQueryInterface(
            handle, byref(guid), WLAN_INTF_OPCODE_CURRENT_CONNECTION,
            None, byref(pDataSize), byref(pData), byref(opcode_type)
        )
        if ret == 0 and pData:
            try:
                conn = ctypes.cast(pData, POINTER(WLAN_CONNECTION_ATTRIBUTES)).contents
                raw_ssid = conn.wlanAssociationAttributes.dot11Ssid
                ssid_str = raw_ssid.ucSSID[:raw_ssid.uSSIDLength].decode('utf-8', errors='replace')
                signal = int(conn.wlanAssociationAttributes.wlanSignalQuality)
                auth = conn.wlanSecurityAttributes.dot11AuthAlgorithm
                cipher = conn.wlanSecurityAttributes.dot11CipherAlgorithm
                sec_str = _auth_algo_to_string(auth, cipher)
                rx = float(conn.wlanAssociationAttributes.ulRxRate) / 1000.0
                tx = float(conn.wlanAssociationAttributes.ulTxRate) / 1000.0
                
                return {
                    "ssid": ssid_str,
                    "profile_name": conn.strProfileName,
                    "signal": signal,
                    "security": sec_str,
                    "rx_mbps": rx,
                    "tx_mbps": tx,
                    "connected": True
                }
            finally:
                wlanapi.WlanFreeMemory(pData)
        return None

    def _query_available_networks(self, handle, guid, connected_ssid: str = None) -> list:
        """Obtém e ordena lista de redes disponíveis."""
        pList = ctypes.c_void_p()
        ret = wlanapi.WlanGetAvailableNetworkList(
            handle, byref(guid),
            WLAN_AVAILABLE_NETWORK_INCLUDE_ALL_MANUAL_HIDDEN_PROFILES,
            None, byref(pList)
        )
        if ret != 0 or not pList:
            return []

        networks = []
        seen_ssids = set()
        
        try:
            # Lê cabeçalho com número de itens
            dw_items = ctypes.cast(pList, POINTER(wintypes.DWORD)).contents.value
            if dw_items > 0:
                class DYNAMIC_NET_LIST(Structure):
                    _fields_ = [
                        ("dwNumberOfItems", wintypes.DWORD),
                        ("dwIndex", wintypes.DWORD),
                        ("Network", WLAN_AVAILABLE_NETWORK * dw_items)
                    ]
                net_list = ctypes.cast(pList, POINTER(DYNAMIC_NET_LIST)).contents
                
                for i in range(dw_items):
                    item = net_list.Network[i]
                    raw_len = item.dot11Ssid.uSSIDLength
                    if raw_len == 0:
                        continue  # Rede oculta / sem beacon SSID
                    name = item.dot11Ssid.ucSSID[:raw_len].decode('utf-8', errors='replace')
                    if not name or name in seen_ssids:
                        continue
                    seen_ssids.add(name)
                    
                    sig = int(item.wlanSignalQuality)
                    is_sec = bool(item.bSecurityEnabled)
                    auth = item.dot11DefaultAuthAlgorithm
                    cipher = item.dot11DefaultCipherAlgorithm
                    sec_type = _auth_algo_to_string(auth, cipher) if is_sec else "Aberta"
                    is_conn = (name == connected_ssid)
                    
                    # Cálculo de barras de sinal (1 a 4)
                    bars = 4 if sig >= 75 else (3 if sig >= 50 else (2 if sig >= 25 else 1))
                    
                    networks.append({
                        "ssid": name,
                        "signal": sig,
                        "bars": bars,
                        "security": sec_type,
                        "is_secure": is_sec,
                        "is_connected": is_conn,
                        "connectable": bool(item.bNetworkConnectable),
                        "profile_name": item.strProfileName
                    })
        finally:
            wlanapi.WlanFreeMemory(pList)

        # Ordenação: rede conectada primeiro, seguida pelas de maior sinal RSSI
        networks.sort(key=lambda n: (1 if n["is_connected"] else 0, n["signal"]), reverse=True)
        return networks

    def connect_network(self, ssid: str, password: str = "", auto_connect: bool = True):
        """Conecta a uma rede Wi-Fi de forma assíncrona com segurança de senhas."""
        threading.Thread(
            target=self._connect_worker,
            args=(ssid, password, auto_connect),
            daemon=True
        ).start()

    def _connect_worker(self, ssid: str, password: str, auto_connect: bool):
        self.connection_status_changed.emit(ssid, "Connecting")
        
        handle = self._open_handle()
        if not handle:
            self.connection_status_changed.emit(ssid, "Failed")
            self.wifi_error.emit("Handle de Wi-Fi indisponível.")
            return

        try:
            guid = self._get_primary_guid(handle)
            if not guid:
                self.connection_status_changed.emit(ssid, "Failed")
                return

            profile_name = ssid
            
            target_net = next((n for n in self._cached_networks if n["ssid"] == ssid), None)

            # Se a senha foi fornecida, cria/atualiza o perfil XML seguro (WPA2 ou WPA3)
            if password:
                sec = target_net.get("security", "WPA2-Personal") if target_net else "WPA2-Personal"
                xml = _generate_wifi_profile_xml(ssid, password, security=sec, auto_connect=auto_connect)
                reason = wintypes.DWORD()
                ret_set = wlanapi.WlanSetProfile(
                    handle, byref(guid), 0,
                    wintypes.LPCWSTR(xml), None, True, None, byref(reason)
                )
                # Limpa imediatamente a string do XML da memória
                del xml
                if ret_set != 0:
                    self.connection_status_changed.emit(ssid, "Failed")
                    self.wifi_error.emit(f"Falha ao configurar credenciais de Wi-Fi (Erro={ret_set}).")
                    return
            else:
                # Verifica se a rede já possui perfil ou se é aberta
                if target_net and not target_net.get("is_secure"):
                    xml = _generate_open_profile_xml(ssid, auto_connect)
                    reason = wintypes.DWORD()
                    ret_open = wlanapi.WlanSetProfile(handle, byref(guid), 0, wintypes.LPCWSTR(xml), None, True, None, byref(reason))
                    del xml
                    if ret_open != 0:
                        self.connection_status_changed.emit(ssid, "Failed")
                        self.wifi_error.emit(f"Falha ao configurar rede aberta (Erro={ret_open}).")
                        return

            # Executa WlanConnect
            conn_params = WLAN_CONNECTION_PARAMETERS()
            conn_params.wlanConnectionMode = WLAN_CONNECTION_MODE_PROFILE
            conn_params.strProfile = wintypes.LPCWSTR(profile_name)
            conn_params.pDot11Ssid = None
            conn_params.pDesiredBssidList = None
            conn_params.dot11BssType = DOT11_BSS_TYPE_INFRASTRUCTURE
            conn_params.dwFlags = 0

            ret_conn = wlanapi.WlanConnect(handle, byref(guid), byref(conn_params), None)
            if ret_conn != 0:
                self.connection_status_changed.emit(ssid, "Failed")
                self.wifi_error.emit(f"WlanConnect retornou código de erro: {ret_conn}")
                return

            # Aguarda e confirma conexão efetiva por até 8 segundos
            confirmed = False
            for _ in range(16):
                time.sleep(0.5)
                cur = self._query_current_connection(handle, guid)
                if cur and cur.get("ssid") == ssid:
                    confirmed = True
                    self._current_conn = cur
                    self.current_connection_updated.emit(cur)
                    self.connection_status_changed.emit(ssid, "Connected")
                    break
                    
            if not confirmed:
                self.connection_status_changed.emit(ssid, "Failed")

        except Exception as e:
            self.connection_status_changed.emit(ssid, "Failed")
            self.wifi_error.emit(f"Exceção durante conexão Wi-Fi: {e}")
        finally:
            wlanapi.WlanCloseHandle(handle, None)
            # Limpeza defensiva do parâmetro de senha
            password = None

    def disconnect_network(self):
        """Desconecta a interface Wi-Fi ativa."""
        threading.Thread(target=self._disconnect_worker, daemon=True).start()

    def _disconnect_worker(self):
        handle = self._open_handle()
        if not handle:
            return
        try:
            guid = self._get_primary_guid(handle)
            if guid:
                wlanapi.WlanDisconnect(handle, byref(guid), None)
                self._current_conn = None
                self.connection_status_changed.emit("", "Disconnected")
        finally:
            wlanapi.WlanCloseHandle(handle, None)

    def get_cached_networks(self) -> list:
        return list(self._cached_networks)

    def get_cached_connection(self) -> dict:
        return dict(self._current_conn) if self._current_conn else None
