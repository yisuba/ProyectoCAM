"""Entry point — launch the camera application.

Environment variables for OpenCV are set **before** any imports to
silence the noisy DSHOW backend on Windows.
"""

import os
import sys
from pathlib import Path

# ── silence OpenCV (must happen before any import of cv2) ──
os.environ["OPENCV_LOG_LEVEL"] = "SILENT"
os.environ.setdefault("OPENCV_LOGGING_LEVEL", "SILENT")


def _setup_logging() -> None:
    """Basic logging to both file and console."""
    logs_dir = Path(__file__).parent / "logs"
    logs_dir.mkdir(exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)-7s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(logs_dir / "tracker.log", encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )

    # Silence noisy libraries
    for lib in ("ultralytics", "PIL", "matplotlib", "huggingface"):
        logging.getLogger(lib).setLevel(logging.WARNING)


# ── app import (after env setup) ──────────────────────────

import logging  # noqa: E402

from interfaz.app import CameraApp  # noqa: E402


def main() -> None:
    _setup_logging()
    app = CameraApp()
    app.mainloop()


if __name__ == "__main__":
    main()
