import psutil
import datetime
import time

class SystemMonitor:
    """Coleta métricas reais de hardware e rede de forma leve e assíncrona."""

    _last_net = None
    _last_time = None

    @classmethod
    def get_stats(cls) -> dict:
        now = datetime.datetime.now()
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()
        
        # Bateria (None em PCs Desktop)
        battery = psutil.sensors_battery()
        has_battery = battery is not None
        battery_percent = int(battery.percent) if has_battery else None
        is_charging = bool(battery.power_plugged) if has_battery else None

        # Disco rígido principal
        try:
            disk = psutil.disk_usage("C:")
            disk_percent = int(disk.percent)
            disk_free_gb = round(disk.free / (1024 ** 3), 1)
        except Exception:
            disk_percent = 0
            disk_free_gb = 0.0

        # Velocidade de rede em tempo real
        try:
            net = psutil.net_io_counters()
            cur_time = time.time()
            down_speed = 0.0
            up_speed = 0.0
            if cls._last_net and cls._last_time:
                dt = cur_time - cls._last_time
                if dt > 0.1:
                    down_speed = (net.bytes_recv - cls._last_net.bytes_recv) / dt
                    up_speed = (net.bytes_sent - cls._last_net.bytes_sent) / dt
            cls._last_net = net
            cls._last_time = cur_time

            if down_speed > 1024 * 1024:
                net_str = f"↓{down_speed / (1024*1024):.1f} MB/s"
            elif down_speed > 1024:
                net_str = f"↓{down_speed / 1024:.0f} KB/s"
            else:
                net_str = f"{int(down_speed)} B/s"
        except Exception:
            net_str = "0 B/s"

        return {
            "cpu": cpu,
            "ram": int(mem.percent),
            "ram_used_gb": round(mem.used / (1024 ** 3), 1),
            "ram_total_gb": round(mem.total / (1024 ** 3), 1),
            "has_battery": has_battery,
            "battery_percent": battery_percent,
            "is_charging": is_charging,
            "disk_percent": disk_percent,
            "disk_free_gb": disk_free_gb,
            "net_str": net_str,
            "time": now.strftime("%H:%M"),
            "date": now.strftime("%d/%m")
        }

