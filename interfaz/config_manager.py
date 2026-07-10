"""Persistent local configuration (config.json).

Stores user preferences that are machine-specific (not committed to git):
- Last selected camera index / URL
- History of network camera URLs
- Detection preferences (target class, default confidence, Q, R)

File is saved to ``config.json`` in the project root.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"

_DEFAULT: dict[str, Any] = {
    "last_source": None,                 # int index or str URL; None = none
    "network_urls": [],                  # list[str] — history of IP cam URLs
    "detection": {
        "target_class": 0,               # COCO class id (0 = person)
        "default_confidence": 0.5,
        "default_q": 1.0,
        "default_r": 2.0,
    },
    "window": {
        "geometry": None,                # "WxH+X+Y" — tkinter geometry string
    },
}


# ═══════════════════════════════════════════════════════════
#  Public API
# ═══════════════════════════════════════════════════════════


def load() -> dict[str, Any]:
    """Load config from disk, merging with defaults.

    Missing keys are filled from ``_DEFAULT`` so adding new fields
    never breaks old config files.
    """
    if not _CONFIG_PATH.exists():
        logger.info("No config.json found — using defaults")
        return dict(_DEFAULT)

    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            raw: dict[str, Any] = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Corrupt config.json — using defaults (%s)", exc)
        return dict(_DEFAULT)

    # Deep-merge with defaults
    merged = _deep_merge(dict(_DEFAULT), raw)
    logger.debug("Config loaded: %s", merged)
    return merged


def save(cfg: dict[str, Any]) -> None:
    """Write config to disk."""
    try:
        with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        logger.info("Config saved to %s", _CONFIG_PATH)
    except OSError as exc:
        logger.error("Cannot save config.json: %s", exc)


def add_network_url(cfg: dict[str, Any], url: str) -> dict[str, Any]:
    """Append a URL to the network history (deduped, max 20 entries)."""
    history: list[str] = cfg.setdefault("network_urls", [])
    if url in history:
        history.remove(url)
    history.insert(0, url)
    cfg["network_urls"] = history[:20]
    return cfg


def update_last_source(cfg: dict[str, Any], source: int | str) -> dict[str, Any]:
    """Update the last used camera source."""
    cfg["last_source"] = source
    return cfg


# ── helpers ───────────────────────────────────────────────


def _deep_merge(base: dict, overrides: dict) -> dict:
    """Recursively merge *overrides* into *base*."""
    for key, val in overrides.items():
        if key in base and isinstance(base[key], dict) and isinstance(val, dict):
            base[key] = _deep_merge(base[key], val)
        else:
            base[key] = val
    return base
