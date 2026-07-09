"""Camera device enumeration and info."""
import os
import sys
import time
import contextlib
from dataclasses import dataclass
from typing import List

# ── silence OpenCV noise ─────────────────────────────
os.environ["OPENCV_LOG_LEVEL"] = "SILENT"
os.environ.setdefault("OPENCV_LOGGING_LEVEL", "SILENT")

import cv2

try:
    cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_SILENT)
except Exception:
    pass


@contextlib.contextmanager
def _silence_stderr():
    """Temporarily redirect stderr to nul (for noisy OpenCV probes)."""
    old_stderr = sys.stderr
    try:
        with open(os.devnull, "w") as devnull:
            sys.stderr = devnull
            yield
    finally:
        sys.stderr = old_stderr


# ── backend resolution helpers ────────────────────────

# Ordered list: try backends that are most likely to work first
_BACKEND_PRIORITY: List[int] = []

if hasattr(cv2, "CAP_DSHOW"):
    _BACKEND_PRIORITY.append(cv2.CAP_DSHOW)
_BACKEND_PRIORITY.append(cv2.CAP_ANY)


def _backend_name(backend: int) -> str:
    """Human-readable backend name."""
    name_map = {
        getattr(cv2, a): a.removeprefix("CAP_")
        for a in dir(cv2) if a.startswith("CAP_")
    }
    return name_map.get(backend, "DEFAULT")


@dataclass
class CameraInfo:
    """Information about a camera source (local USB or network stream).

    For local cameras use the default constructor with ``index`` and
    ``backend_int``.  For network/IP cameras use ``from_url()``.

    ``source`` is the preferred way to pass this info to
    :class:`CameraStream` — it returns the local index or the URL
    string automatically.
    """

    index: int = -1        # local camera device index (-1 for network)
    width: int = 640
    height: int = 480
    fps: float = 30.0
    backend_str: str = "DEFAULT"
    backend_int: int = cv2.CAP_ANY
    name: str = ""
    url: str = ""          # stream URL for network / ESP32-CAM cameras

    def __post_init__(self):
        if not self.name:
            if self.url:
                self.name = self.url
            else:
                self.name = f"Cámara {self.index}"

    @property
    def source(self) -> int | str:
        """Return the value to pass to ``CameraStream(source=...)``."""
        return self.url if self.url else self.index

    @property
    def is_network(self) -> bool:
        return bool(self.url)

    @property
    def label(self) -> str:
        """Human-readable label for UI dropdowns."""
        if self.url:
            return f"🌐 {self.name}"
        return f"{self.name} — {self.width}x{self.height} @ {self.fps:.0f} fps"

    @staticmethod
    def from_url(url: str) -> "CameraInfo":
        """Create a ``CameraInfo`` for a network / IP camera stream.

        Accepted URL schemes:
        - ``http://…``  → MJPEG over HTTP (ESP32-CAM, generic IP cams)
        - ``rtsp://…``  → RTSP streams
        - ``rtmp://…``  → RTMP streams
        """
        return CameraInfo(
            index=-1,
            url=url,
            name=url,
            width=640,
            height=480,
            fps=30.0,
            backend_str="NETWORK",
            backend_int=cv2.CAP_ANY,
        )


def _probe_camera(index: int, backend: int) -> CameraInfo | None:
    """Try to open a camera without fully consuming the device.

    Sets a baseline resolution so the camera negotiates a known profile,
    reads properties, then releases quickly. A small delay after release
    ensures DSHOW frees the driver resource for later use by the stream.
    """
    with _silence_stderr():
        cap = cv2.VideoCapture(index, backend)
    if not cap.isOpened():
        return None

    # Set a known resolution upfront — some USB cameras require this
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 30)

    # One warm-up frame to confirm the camera delivers
    for _ in range(3):
        ret, _ = cap.read()
        if ret:
            break
        time.sleep(0.1)

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)

    # Sanitise — some drivers report 0 or -1
    width = max(width, 320) if width > 0 else 640
    height = max(height, 240) if height > 0 else 480
    fps = max(fps, 15.0) if fps > 0 else 30.0

    info = CameraInfo(
        index=index,
        width=width,
        height=height,
        fps=fps,
        backend_str=_backend_name(backend),
        backend_int=backend,
    )

    cap.release()
    # CRITICAL: give DSHOW time to free the driver before stream opens
    time.sleep(0.5)
    return info


def list_cameras(max_index: int = 5) -> List[CameraInfo]:
    """Enumerate available camera devices.

    Tries backends in priority order (DSHOW → ANY on Windows).
    Returns a (possibly empty) list of :class:`CameraInfo`.
    """
    cameras: List[CameraInfo] = []

    for idx in range(max_index):
        for backend in _BACKEND_PRIORITY:
            info = _probe_camera(idx, backend)
            if info is not None:
                cameras.append(info)
                break  # first backend that works wins

    return cameras


def find_camera_by_index(index: int) -> CameraInfo | None:
    """Probe a single camera index and return its info (or ``None``)."""
    for backend in _BACKEND_PRIORITY:
        info = _probe_camera(index, backend)
        if info is not None:
            return info
    return None
