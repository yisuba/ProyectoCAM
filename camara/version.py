"""Project version — single source of truth."""

from pathlib import Path


def _read_version() -> str:
    """Read version from the ``VERSION`` file at the project root."""
    try:
        return Path(__file__).resolve().parent.parent.joinpath("VERSION").read_text().strip()
    except Exception:
        return "0.0.0"


__version__: str = _read_version()
