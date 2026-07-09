"""Background-thread camera frame capture.

Usage::

    with CameraStream(index=0) as stream:
        frame = stream.read()       # latest frame (or None)
        # … do something with frame …
        # stream.running tells you if it's still alive
"""

import os
import sys
import time
import contextlib
from collections import deque
from threading import Event, Lock, Thread
from typing import Optional

# ── silence OpenCV noise ────────────────────────────────
os.environ["OPENCV_LOG_LEVEL"] = "SILENT"
os.environ.setdefault("OPENCV_LOGGING_LEVEL", "SILENT")

import cv2

try:
    cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_SILENT)
except Exception:
    pass

import numpy as np
from numpy.typing import NDArray


@contextlib.contextmanager
def _silence_stderr():
    old_stderr = sys.stderr
    try:
        with open(os.devnull, "w") as devnull:
            sys.stderr = devnull
            yield
    finally:
        sys.stderr = old_stderr


Source = int | str


class CameraStream:
    """Capture frames from a camera in a **background thread**.

    The latest frame is always available via ``.read()`` – this is
    **non-blocking** and returns ``None`` if no frame has been captured
    yet or the camera was lost.

    Parameters
    ----------
    source:
        Local camera device index (``int``, usually 0, 1, …) **or**
        a stream URL (``str``) such as ``http://…`` for an IP camera
        or ESP32-CAM, ``rtsp://…``, or ``rtmp://…``.
    backend:
        OpenCV backend hint (``cv2.CAP_DSHOW``, ``cv2.CAP_ANY``, …).
        Only used when ``source`` is an ``int``.
    """

    def __init__(
        self,
        source: Source,
        backend: int = cv2.CAP_ANY,
        max_read_errors: int = 50,
    ):
        self._source = source
        self._backend = backend if isinstance(source, int) else cv2.CAP_ANY
        self._max_read_errors = max_read_errors
        self._cap: cv2.VideoCapture | None = None
        self._thread: Thread | None = None
        self._stop_event = Event()
        self._lock = Lock()
        # Deque with maxlen=1 keeps ONLY the latest frame
        self._queue: deque = deque(maxlen=1)
        self._error: Optional[str] = None
        self._running = False
        self._frame_count = 0

    # ── public helpers ─────────────────────────────────

    @property
    def running(self) -> bool:
        """Whether the capture loop is active."""
        return self._running

    @property
    def error(self) -> Optional[str]:
        """Last error message (resets on read)."""
        return self._error

    @property
    def index(self) -> int:
        """Local camera index, or -1 for network streams."""
        return self._source if isinstance(self._source, int) else -1

    @property
    def source(self) -> Source:
        """The source identifier — int index or stream URL."""
        return self._source

    @property
    def is_network(self) -> bool:
        return isinstance(self._source, str)

    @property
    def frame_count(self) -> int:
        """How many frames have been captured so far."""
        return self._frame_count

    def read(self) -> Optional[NDArray]:
        """Return the **latest** frame (BGR numpy array) or ``None``."""
        with self._lock:
            return self._queue[0] if self._queue else None

    def start(self) -> None:
        """Open the camera and spawn the capture thread."""
        with _silence_stderr():
            if isinstance(self._source, int):
                self._cap = cv2.VideoCapture(self._source, self._backend)
            else:
                self._cap = cv2.VideoCapture(self._source)
        if not self._cap.isOpened():
            raise RuntimeError(
                f"No se pudo abrir: {self._source}"
            )

        self._stop_event.clear()
        self._thread = Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        self._running = True

    def stop(self) -> None:
        """Signal the thread to stop and release the camera."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        if self._cap:
            self._cap.release()
            self._cap = None
        self._running = False

    # ── context manager ────────────────────────────────

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.stop()

    # ── internal ───────────────────────────────────────

    def _capture_loop(self) -> None:
        """Continuously read frames and keep only the latest.

        Resolution is set explicitly before the first read since some
        cameras need it before they deliver usable frames.  A warm-up
        delay lets the sensor stabilise, and early garbled frames are
        discarded.
        """
        cap = self._cap
        if cap is None:
            self._error = "Camera not opened"
            self._running = False
            return

        # ── configure camera upfront (local only) ─────────
        if isinstance(self._source, int):
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cap.set(cv2.CAP_PROP_FPS, 30)

        # ── warm-up: let the camera stabilise ─────────────
        time.sleep(1.0)

        # Discard any early garbled frames
        for _ in range(5):
            with _silence_stderr():
                ret, _ = cap.read()
            if not ret:
                time.sleep(0.05)
            else:
                break

        # ── capture loop ──────────────────────────────────
        consecutive_errors = 0

        while not self._stop_event.is_set():
            try:
                with _silence_stderr():
                    ret, frame = cap.read()
                if not ret:
                    consecutive_errors += 1
                    if consecutive_errors >= self._max_read_errors:
                        self._error = (
                            f"La cámara no entrega frames después de "
                            f"{consecutive_errors} intentos"
                        )
                        break
                    time.sleep(0.05)
                    continue

                # Successful read → reset error count
                consecutive_errors = 0
                self._frame_count += 1
                self._error = None

                with self._lock:
                    self._queue.append(frame)
            except Exception as exc:
                self._error = str(exc)
                break

        self._running = False
