from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_DB_PATH = DATA_DIR / "monitor.db"
DEFAULT_STATE_PATH = DATA_DIR / "latest.json"
DEFAULT_LOG_DIR = DATA_DIR / "logs"
DEFAULT_ICON_DIR = PROJECT_ROOT / "assets" / "icons"

DEFAULT_CONFIG = {
    "interval_seconds": 300,
    "paths": {
        "db": str(DEFAULT_DB_PATH),
        "latest_state": str(DEFAULT_STATE_PATH),
        "log_dir": str(DEFAULT_LOG_DIR),
        "icon_dir": str(DEFAULT_ICON_DIR),
    },
    "network": {
        "primary_interface": "wlan0",
        "secondary_interfaces": ["eth0"],
    },
    "services": {
        "required": ["ssh", "NetworkManager", "wpa_supplicant"],
        "mihomo": {
            "unit": "mihomo.service",
            "controller": "http://127.0.0.1:9090",
            "secret": "KKNtb1ZJRPzUFBddcYAWUQ==",
            "group": "Proxy",
        },
    },
    "thresholds": {
        "cpu": {
            "load_warn_per_core": 0.8,
            "load_error_per_core": 1.2,
            "temp_warn_c": 70.0,
            "temp_error_c": 80.0,
        },
        "memory": {
            "available_warn_pct": 20.0,
            "available_error_pct": 10.0,
        },
        "disk": {
            "usage_warn_pct": 80.0,
            "usage_error_pct": 90.0,
        },
        "battery": {
            "warn_pct": 25.0,
            "error_pct": 10.0,
            "error_when_discharging_only": True,
        },
    },
    "ui": {
        "stale_after_seconds": 900,
        "show_details_window": True,
    },
}
