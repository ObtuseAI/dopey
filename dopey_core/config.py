"""Dopey config loader: minimal flat-YAML reader (stdlib only, no pyyaml).

DOPEY-native. Reads the simple flat `key: value` config YAML files used by DOPEY. Supports
comments (#) and bare scalars (bool/int/float/str). This is intentionally NOT a full YAML
parser — DOPEY configs are flat by design.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


_BOOL = {"true": True, "false": False, "yes": True, "no": False, "null": None, "none": None}


def _coerce(raw: str) -> Any:
    v = raw.strip().strip('"').strip("'")
    if v == "":
        return ""
    low = v.lower()
    if low in _BOOL:
        return _BOOL[low]
    try:
        if "." in v:
            return float(v)
        return int(v)
    except ValueError:
        return v


def load_config(path) -> dict:
    path = Path(path)
    out: dict[str, Any] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        out[key.strip()] = _coerce(val)
    return out


def default_config_path() -> Path:
    return Path(__file__).resolve().parent.parent / "configs" / "dopey.default.yaml"
