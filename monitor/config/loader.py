from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from monitor.config.defaults import DEFAULT_CONFIG, PROJECT_ROOT


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(path: str | None = None) -> dict[str, Any]:
    config_path = Path(path) if path else PROJECT_ROOT / "config.json"
    config = copy.deepcopy(DEFAULT_CONFIG)
    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as handle:
            user_config = json.load(handle)
        config = deep_merge(config, user_config)
    return config
