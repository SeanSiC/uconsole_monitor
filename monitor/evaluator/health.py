from __future__ import annotations

from datetime import datetime
from typing import Any

from monitor.models import DimensionState, Snapshot


STATUS_ORDER = {"ok": 0, "warn": 1, "error": 2, "unknown": 3}


def _worse(left: str, right: str) -> str:
    return left if STATUS_ORDER[left] >= STATUS_ORDER[right] else right


def _fmt_bytes(num: int) -> str:
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    value = float(num)
    for unit in units:
        if value < 1024.0 or unit == units[-1]:
            return f"{value:.1f}{unit}"
        value /= 1024.0
    return f"{num}B"


def evaluate_cpu(raw: dict[str, Any], thresholds: dict[str, Any]) -> tuple[DimensionState, list[str], list[str]]:
    warnings: list[str] = []
    errors: list[str] = []
    status = "ok"
    cpu_count = max(int(raw.get("cpu_count") or 1), 1)
    load5 = float(raw.get("load_5") or 0.0)
    per_core = load5 / cpu_count
    if per_core >= thresholds["load_error_per_core"]:
        status = "error"
        errors.append(f"CPU load per core is high: {per_core:.2f}")
    elif per_core >= thresholds["load_warn_per_core"]:
        status = "warn"
        warnings.append(f"CPU load per core is elevated: {per_core:.2f}")

    temp_c = raw.get("temp_c")
    if temp_c is not None:
        if temp_c >= thresholds["temp_error_c"]:
            status = "error"
            errors.append(f"CPU temperature is high: {temp_c:.1f}C")
        elif temp_c >= thresholds["temp_warn_c"] and status != "error":
            status = _worse(status, "warn")
            warnings.append(f"CPU temperature is elevated: {temp_c:.1f}C")

    summary = f"CPU {raw.get('usage_pct', 0):.1f}%, load {raw.get('load_5', 0):.2f}"
    if temp_c is not None:
        summary += f", {temp_c:.1f}C"
    return DimensionState(status=status, summary=summary, details=raw), warnings, errors


def evaluate_memory(raw: dict[str, Any], thresholds: dict[str, Any]) -> tuple[DimensionState, list[str], list[str]]:
    warnings: list[str] = []
    errors: list[str] = []
    total = int(raw.get("total_bytes") or 0)
    available = int(raw.get("available_bytes") or 0)
    available_pct = (available / total * 100.0) if total else 0.0
    status = "ok"
    if total == 0:
        status = "unknown"
    elif available_pct <= thresholds["available_error_pct"]:
        status = "error"
        errors.append(f"Available memory is low: {available_pct:.1f}%")
    elif available_pct <= thresholds["available_warn_pct"]:
        status = "warn"
        warnings.append(f"Available memory is low: {available_pct:.1f}%")
    summary = f"{_fmt_bytes(int(raw.get('used_bytes') or 0))} used / {_fmt_bytes(total)}"
    return DimensionState(status=status, summary=summary, details=raw), warnings, errors


def evaluate_disk(raw: dict[str, Any], thresholds: dict[str, Any]) -> tuple[DimensionState, list[str], list[str]]:
    warnings: list[str] = []
    errors: list[str] = []
    status = "ok"
    mounts = raw.get("mounts", [])
    if not mounts:
        status = "unknown"
    for mount in mounts:
        usage_pct = float(mount.get("usage_pct") or 0.0)
        if usage_pct >= thresholds["usage_error_pct"]:
            status = "error"
            errors.append(f"{mount['mountpoint']} usage is high: {usage_pct:.1f}%")
        elif usage_pct >= thresholds["usage_warn_pct"] and status != "error":
            status = _worse(status, "warn")
            warnings.append(f"{mount['mountpoint']} usage is elevated: {usage_pct:.1f}%")
    summary = ", ".join(
        f"{mount['mountpoint']} {mount.get('usage_pct', 0):.1f}%"
        for mount in mounts
    ) or "No disk data"
    return DimensionState(status=status, summary=summary, details=raw), warnings, errors


def evaluate_network(raw: dict[str, Any], primary: str) -> tuple[DimensionState, list[str], list[str]]:
    warnings: list[str] = []
    errors: list[str] = []
    status = "ok"
    interfaces = raw.get("interfaces", [])
    if not interfaces:
        return DimensionState(status="unknown", summary="No network data", details=raw), warnings, errors
    primary_iface = next((iface for iface in interfaces if iface.get("name") == primary), interfaces[0])
    primary_state = primary_iface.get("state", "unknown")
    if primary_state != "up":
        status = "error"
        errors.append(f"Primary interface {primary} is {primary_state}")
    elif not primary_iface.get("ipv4"):
        status = "warn"
        warnings.append(f"Primary interface {primary} has no IPv4 address")
    summary = f"{primary} {primary_state}"
    if primary_iface.get("ipv4"):
        summary += f", {primary_iface['ipv4']}"
    return DimensionState(status=status, summary=summary, details=raw), warnings, errors


def evaluate_services(raw: dict[str, Any]) -> tuple[DimensionState, list[str], list[str]]:
    warnings: list[str] = []
    errors: list[str] = []
    status = "ok"
    for unit in raw.get("units", []):
        if unit.get("active_state") != "active":
            status = "error"
            errors.append(f"{unit['name']} is {unit.get('active_state')}/{unit.get('sub_state')}")
    summary = "All required services active" if status == "ok" else "One or more required services are not active"
    return DimensionState(status=status, summary=summary, details=raw), warnings, errors


def evaluate_mihomo(raw: dict[str, Any]) -> tuple[DimensionState, list[str], list[str]]:
    warnings: list[str] = []
    errors: list[str] = []
    service = raw.get("service", {})
    version = raw.get("version", {})
    runtime = raw.get("runtime", {})
    group = raw.get("group", {})
    providers = raw.get("providers", {})

    if service.get("active_state") != "active":
        status = "error"
        errors.append(f"{service.get('unit')} is {service.get('active_state')}/{service.get('sub_state')}")
    elif not version.get("ok") or not runtime.get("ok"):
        status = "error"
        errors.append("Mihomo controller API is unavailable")
    else:
        alive_total = sum(item.get("alive", 0) for item in providers.values())
        node_total = sum(item.get("total", 0) for item in providers.values())
        if node_total > 0 and alive_total == 0:
            status = "error"
            errors.append("Mihomo providers have no alive proxy nodes")
        elif group.get("current"):
            status = "ok"
        else:
            status = "warn"
            warnings.append("Mihomo proxy group has no active selection")

    version_text = version.get("json", {}).get("version") if version.get("ok") else "api-down"
    current = group.get("current") or raw.get("group_name") or "unknown"
    summary = f"{current}, {version_text}"
    return DimensionState(status=status, summary=summary, details=raw), warnings, errors


def evaluate_battery(raw: dict[str, Any], thresholds: dict[str, Any]) -> tuple[DimensionState, list[str], list[str]]:
    warnings: list[str] = []
    errors: list[str] = []
    if not raw.get("present"):
        return (
            DimensionState(status="unknown", summary="Battery not present", details=raw),
            warnings,
            errors,
        )
    capacity = raw.get("capacity_pct")
    state = raw.get("state", "Unknown")
    discharging = state.lower() == "discharging"
    status = "ok"
    if capacity is None:
        status = "warn"
        warnings.append("Battery capacity unavailable")
    else:
        if capacity <= thresholds["error_pct"] and (discharging or not thresholds["error_when_discharging_only"]):
            status = "error"
            errors.append(f"Battery is low: {capacity:.0f}%")
        elif capacity <= thresholds["warn_pct"]:
            status = "warn"
            warnings.append(f"Battery is low: {capacity:.0f}%")
    parts = []
    if capacity is not None:
        parts.append(f"{capacity:.0f}%")
    parts.append(state)
    if raw.get("online_power"):
        parts.append("AC")
    summary = ", ".join(parts)
    return DimensionState(status=status, summary=summary, details=raw), warnings, errors


def build_snapshot(raw: dict[str, Any], config: dict[str, Any]) -> Snapshot:
    warnings: list[str] = []
    errors: list[str] = []

    cpu_state, cpu_warn, cpu_err = evaluate_cpu(raw["cpu"], config["thresholds"]["cpu"])
    mem_state, mem_warn, mem_err = evaluate_memory(raw["memory"], config["thresholds"]["memory"])
    disk_state, disk_warn, disk_err = evaluate_disk(raw["disk"], config["thresholds"]["disk"])
    net_state, net_warn, net_err = evaluate_network(raw["network"], config["network"]["primary_interface"])
    svc_state, svc_warn, svc_err = evaluate_services(raw["services"])
    mihomo_state, mihomo_warn, mihomo_err = evaluate_mihomo(raw["services"]["mihomo"])
    battery_state, battery_warn, battery_err = evaluate_battery(raw["battery"], config["thresholds"]["battery"])

    dimensions = {
        "cpu": cpu_state,
        "memory": mem_state,
        "disk": disk_state,
        "network": net_state,
        "services": svc_state,
        "mihomo": mihomo_state,
        "battery": battery_state,
    }

    for group in (cpu_warn, mem_warn, disk_warn, net_warn, svc_warn, mihomo_warn, battery_warn):
        warnings.extend(group)
    for group in (cpu_err, mem_err, disk_err, net_err, svc_err, mihomo_err, battery_err):
        errors.extend(group)

    critical = ["cpu", "memory", "disk", "network", "mihomo"]
    critical_statuses = [dimensions[name].status for name in critical]
    if raw["battery"].get("present"):
        critical_statuses.append(dimensions["battery"].status)
    if any(status == "error" for status in critical_statuses):
        overall_status = "error"
    elif any(status == "warn" for status in critical_statuses):
        overall_status = "warn"
    elif all(status == "ok" for status in critical_statuses if status != "unknown"):
        overall_status = "ok"
    else:
        overall_status = "unknown"

    summary_parts = []
    for name in ("cpu", "memory", "disk", "network", "mihomo", "battery"):
        summary_parts.append(f"{name}: {dimensions[name].summary}")

    return Snapshot(
        updated_at=datetime.now().astimezone(),
        host=raw["host"],
        dimensions=dimensions,
        overall_status=overall_status,
        overall_summary=" | ".join(summary_parts),
        warnings=warnings,
        errors=errors,
    )
