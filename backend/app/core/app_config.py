"""Loader for config/app.yaml (pipeline parameters).

WHY: preprocessing, quality and identification parameters are data, not code, so they can
be tuned in the Pipeline Lab and documented in one place. `section()` returns a deep copy
with optional per-call overrides merged in, so a request can change one slider value
without mutating the shared configuration.
"""
from __future__ import annotations

import copy
from functools import lru_cache
from typing import Any

import yaml

from app.core.config import get_settings


@lru_cache
def load_app_config() -> dict[str, Any]:
    path = get_settings().config_dir / "app.yaml"
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def deep_merge(base: dict[str, Any], override: dict[str, Any] | None) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def section(name: str, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = load_app_config()
    if name not in cfg:
        raise KeyError(f"config/app.yaml has no '{name}' section")
    return deep_merge(cfg[name], overrides)
