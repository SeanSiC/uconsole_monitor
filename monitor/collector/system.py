from __future__ import annotations

import json
import os
import platform
import re
import shutil
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now_local() -> datetime:
    return datetime.now().astimezone()


def _read_text(path: str | Path) -> str | None:
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return None


def read_os_release() -> dict[str, str]:
    data: dict[str, str] = {}
    text = _read_text("/etc/os-release")
    if not text:
        return data
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key] = value.strip().strip('"')
    return data


def collect_host_info() -> dict[str, Any]:
    os_release = read_os_release()
    return {
        "hostname": socket.gethostname(),
        "os": os_release.get("PRETTY_NAME", platform.platform()),
        "kernel": platform.release(),
        "uptime_seconds": read_uptime_seconds(),
        "timestamp": now_local().isoformat(),
    }


def read_uptime_seconds() -> int:
    text = _read_text("/proc/uptime")
    if not text:
        return 0
    return int(float(text.split()[0]))


def read_loadavg() -> dict[str, float]:
    text = _read_text("/proc/loadavg")
    if not text:
        return {"load_1": 0.0, "load_5": 0.0, "load_15": 0.0}
    load_1, load_5, load_15, *_ = text.split()
    return {
        "load_1": float(load_1),
        "load_5": float(load_5),
        "load_15": float(load_15),
    }


def read_cpu_times() -> tuple[int, int]:
    text = _read_text("/proc/stat")
    if not text:
        return 0, 0
    fields = text.splitlines()[0].split()[1:]
    values = [int(value) for value in fields]
    idle = values[3] + values[4]
    total = sum(values)
    return idle, total


def read_cpu_usage(sample_seconds: float = 0.2) -> float:
    idle_1, total_1 = read_cpu_times()
    if sample_seconds > 0:
        import time

        time.sleep(sample_seconds)
    idle_2, total_2 = read_cpu_times()
    idle_delta = idle_2 - idle_1
    total_delta = total_2 - total_1
    if total_delta <= 0:
        return 0.0
    return round(100.0 * (1 - idle_delta / total_delta), 1)


def read_cpu_freq_mhz() -> float | None:
    path = "/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq"
    text = _read_text(path)
    if not text:
        return None
    return round(int(text) / 1000.0, 1)


def read_temperature_c() -> float | None:
    thermal_root = Path("/sys/class/thermal")
    for zone in sorted(thermal_root.glob("thermal_zone*")):
        zone_type = _read_text(zone / "type")
        temp = _read_text(zone / "temp")
        if not temp:
            continue
        if zone_type and "cpu" in zone_type.lower():
            return round(int(temp) / 1000.0, 1)
    return None


def read_meminfo() -> dict[str, int]:
    text = _read_text("/proc/meminfo")
    result: dict[str, int] = {}
    if not text:
        return result
    for line in text.splitlines():
        key, value = line.split(":", 1)
        amount = int(value.strip().split()[0]) * 1024
        result[key] = amount
    return result


def collect_memory() -> dict[str, Any]:
    mem = read_meminfo()
    total = mem.get("MemTotal", 0)
    available = mem.get("MemAvailable", 0)
    free = mem.get("MemFree", 0)
    cached = mem.get("Cached", 0) + mem.get("Buffers", 0)
    used = max(total - available, 0)
    swap_total = mem.get("SwapTotal", 0)
    swap_free = mem.get("SwapFree", 0)
    swap_used = max(swap_total - swap_free, 0)
    return {
        "total_bytes": total,
        "used_bytes": used,
        "available_bytes": available,
        "free_bytes": free,
        "cached_bytes": cached,
        "swap_total_bytes": swap_total,
        "swap_used_bytes": swap_used,
    }


def collect_disks() -> dict[str, Any]:
    mounts: list[dict[str, Any]] = []
    for mountpoint in ("/", "/boot/firmware"):
        try:
            stats = shutil.disk_usage(mountpoint)
        except OSError:
            continue
        mounts.append(
            {
                "mountpoint": mountpoint,
                "total_bytes": stats.total,
                "used_bytes": stats.used,
                "free_bytes": stats.free,
                "usage_pct": round(stats.used / stats.total * 100.0, 1) if stats.total else 0.0,
            }
        )
    return {"mounts": mounts}


def _parse_proc_net_dev() -> dict[str, dict[str, int]]:
    text = _read_text("/proc/net/dev")
    if not text:
        return {}
    stats: dict[str, dict[str, int]] = {}
    for line in text.splitlines()[2:]:
        iface, values = line.split(":", 1)
        parts = values.split()
        stats[iface.strip()] = {
            "rx_bytes": int(parts[0]),
            "rx_packets": int(parts[1]),
            "rx_errors": int(parts[2]),
            "tx_bytes": int(parts[8]),
            "tx_packets": int(parts[9]),
            "tx_errors": int(parts[10]),
        }
    return stats


def _read_interface_operstate(name: str) -> str:
    return _read_text(f"/sys/class/net/{name}/operstate") or "unknown"


def _read_interface_mac(name: str) -> str | None:
    return _read_text(f"/sys/class/net/{name}/address")


def _run_json_ip() -> list[dict[str, Any]]:
    try:
        output = subprocess.run(
            ["ip", "-json", "address", "show"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return []
    try:
        return json.loads(output.stdout)
    except json.JSONDecodeError:
        return []


def collect_network(primary: str, secondary: list[str]) -> dict[str, Any]:
    wanted = [primary, *secondary]
    counters = _parse_proc_net_dev()
    addresses = {item.get("ifname"): item for item in _run_json_ip()}
    interfaces: list[dict[str, Any]] = []
    for name in wanted:
        details = {
            "name": name,
            "state": _read_interface_operstate(name),
            "mac": _read_interface_mac(name),
        }
        stats = counters.get(name, {})
        details.update(stats)
        ip_info = addresses.get(name, {})
        addr_info = ip_info.get("addr_info", [])
        ipv4 = next(
            (
                f"{item['local']}/{item['prefixlen']}"
                for item in addr_info
                if item.get("family") == "inet"
            ),
            None,
        )
        ipv6 = next(
            (
                f"{item['local']}/{item['prefixlen']}"
                for item in addr_info
                if item.get("family") == "inet6" and not item.get("local", "").startswith("fe80")
            ),
            None,
        )
        details["ipv4"] = ipv4
        details["ipv6"] = ipv6
        interfaces.append(details)
    return {"interfaces": interfaces}


def _systemctl_show(unit: str) -> dict[str, str]:
    try:
        output = subprocess.run(
            ["systemctl", "show", unit, "--no-pager", "--property=Id,LoadState,ActiveState,SubState,UnitFileState,StateChangeTimestamp"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return {
            "Id": unit,
            "LoadState": "unknown",
            "ActiveState": "unknown",
            "SubState": "unknown",
            "UnitFileState": "unknown",
            "StateChangeTimestamp": "",
        }
    result: dict[str, str] = {}
    for line in output.stdout.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key] = value
    return result


def _run_command(command: list[str]) -> dict[str, Any]:
    try:
        output = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        return {
            "ok": False,
            "returncode": None,
            "stdout": "",
            "stderr": str(exc),
        }
    return {
        "ok": output.returncode == 0,
        "returncode": output.returncode,
        "stdout": output.stdout.strip(),
        "stderr": output.stderr.strip(),
    }


def _run_json_http(url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
    import urllib.error
    import urllib.request

    request = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return {"ok": True, "status": response.status, "json": json.loads(response.read().decode("utf-8"))}
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": str(exc)}


def collect_mihomo_status(config: dict[str, Any]) -> dict[str, Any]:
    unit = config["unit"]
    controller = config["controller"].rstrip("/")
    secret = config.get("secret", "")
    group_name = config.get("group", "Proxy")
    headers = {"Authorization": f"Bearer {secret}"} if secret else {}

    service = _systemctl_show(unit)
    version = _run_json_http(f"{controller}/version", headers=headers)
    runtime = _run_json_http(f"{controller}/configs", headers=headers)
    providers = _run_json_http(f"{controller}/providers/proxies", headers=headers)
    group_state = _run_json_http(f"{controller}/proxies/{group_name}", headers=headers)

    group = group_state.get("json", {}) if group_state.get("ok") else {}
    provider_summary = {}
    if providers.get("ok"):
        providers_json = providers["json"].get("providers", {})
        for name, provider in providers_json.items():
            if provider.get("vehicleType") != "HTTP":
                continue
            proxies = provider.get("proxies", [])
            counted = [item for item in proxies if item.get("type") not in {"Direct", "Reject"}]
            alive = sum(1 for item in counted if item.get("alive"))
            provider_summary[name] = {"alive": alive, "total": len(counted)}

    return {
        "service": {
            "unit": unit,
            "load_state": service.get("LoadState", "unknown"),
            "active_state": service.get("ActiveState", "unknown"),
            "sub_state": service.get("SubState", "unknown"),
            "unit_file_state": service.get("UnitFileState", "unknown"),
        },
        "controller": controller,
        "version": version,
        "runtime": runtime,
        "group_name": group_name,
        "group_state": group_state,
        "group": {
            "name": group.get("name"),
            "type": group.get("type"),
            "current": group.get("now"),
            "alive": group.get("alive"),
        },
        "providers": provider_summary,
    }


def collect_services(required: list[str], mihomo_config: dict[str, Any]) -> dict[str, Any]:
    units = []
    for name in required:
        unit_name = name if name.endswith(".service") else f"{name}.service"
        info = _systemctl_show(unit_name)
        units.append(
            {
                "name": unit_name,
                "load_state": info.get("LoadState", "unknown"),
                "active_state": info.get("ActiveState", "unknown"),
                "sub_state": info.get("SubState", "unknown"),
                "unit_file_state": info.get("UnitFileState", "unknown"),
                "state_change_timestamp": info.get("StateChangeTimestamp", ""),
            }
        )
    return {
        "units": units,
        "mihomo": collect_mihomo_status(mihomo_config),
    }


def collect_battery() -> dict[str, Any]:
    upower_battery = _collect_battery_upower()
    if upower_battery:
        return upower_battery

    power_root = Path("/sys/class/power_supply")
    batteries = sorted(power_root.glob("BAT*"))
    mains = sorted(power_root.glob("AC*")) + sorted(power_root.glob("ADP*")) + sorted(power_root.glob("USB*"))
    online_power = any((_read_text(item / "online") == "1") for item in mains)
    if not batteries:
        return {"present": False, "online_power": online_power}

    battery = batteries[0]
    status = _read_text(battery / "status") or "Unknown"
    capacity = _read_text(battery / "capacity")
    energy_full = _read_text(battery / "energy_full")
    energy_full_design = _read_text(battery / "energy_full_design")
    charge_full = _read_text(battery / "charge_full")
    charge_full_design = _read_text(battery / "charge_full_design")

    health_pct = None
    actual = energy_full or charge_full
    design = energy_full_design or charge_full_design
    if actual and design:
        try:
            health_pct = round(int(actual) / int(design) * 100.0, 1)
        except (ValueError, ZeroDivisionError):
            health_pct = None

    return {
        "present": True,
        "name": battery.name,
        "state": status,
        "capacity_pct": float(capacity) if capacity else None,
        "online_power": online_power,
        "health_pct": health_pct,
    }


def _collect_battery_upower() -> dict[str, Any] | None:
    try:
        devices = subprocess.run(
            ["upower", "-e"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None

    battery_path = None
    display_path = None
    for line in devices.stdout.splitlines():
        item = line.strip()
        if "battery_" in item and battery_path is None:
            battery_path = item
        if item.endswith("/DisplayDevice"):
            display_path = item
    target = battery_path or display_path
    if not target:
        return None

    try:
        details = subprocess.run(
            ["upower", "-i", target],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None

    parsed: dict[str, str] = {}
    section = ""
    for raw_line in details.stdout.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue
        stripped = line.strip()
        if stripped in {"battery", "line-power"}:
            section = stripped
            continue
        if not raw_line.startswith(" "):
            continue
        if stripped.endswith(":"):
            section = stripped[:-1]
            continue
        if ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        parsed_key = f"{section}.{key.strip()}" if section else key.strip()
        parsed[parsed_key] = value.strip()

    present = parsed.get("battery.present", "").lower() == "yes"
    if not present:
        return {"present": False, "online_power": parsed.get("line-power.online", "").lower() == "yes"}

    percentage = parsed.get("battery.percentage") or parsed.get("percentage")
    capacity = parsed.get("battery.capacity") or parsed.get("capacity")
    state = parsed.get("battery.state", "Unknown")
    line_online = parsed.get("line-power.online", "").lower() == "yes"
    return {
        "present": True,
        "name": parsed.get("native-path", target.rsplit("/", 1)[-1]),
        "state": state,
        "capacity_pct": float(percentage.rstrip("%")) if percentage else None,
        "health_pct": float(capacity.rstrip("%")) if capacity else None,
        "online_power": line_online or state.lower() in {"charging", "fully-charged", "pending-charge"},
        "energy_wh": _parse_number_prefix(parsed.get("battery.energy")),
        "energy_full_wh": _parse_number_prefix(parsed.get("battery.energy-full")),
        "energy_rate_w": _parse_number_prefix(parsed.get("battery.energy-rate")),
        "voltage_v": _parse_number_prefix(parsed.get("battery.voltage")),
        "warning_level": parsed.get("battery.warning-level"),
        "technology": parsed.get("battery.technology"),
        "icon_name": parsed.get("battery.icon-name"),
    }


def _parse_number_prefix(value: str | None) -> float | None:
    if not value:
        return None
    token = value.split()[0]
    try:
        return float(token)
    except ValueError:
        return None


def collect_all(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "host": collect_host_info(),
        "cpu": {
            **read_loadavg(),
            "usage_pct": read_cpu_usage(),
            "temp_c": read_temperature_c(),
            "freq_mhz": read_cpu_freq_mhz(),
            "cpu_count": os.cpu_count() or 1,
        },
        "memory": collect_memory(),
        "disk": collect_disks(),
        "network": collect_network(
            config["network"]["primary_interface"],
            config["network"].get("secondary_interfaces", []),
        ),
        "services": collect_services(
            config["services"]["required"],
            config["services"]["mihomo"],
        ),
        "battery": collect_battery(),
    }
