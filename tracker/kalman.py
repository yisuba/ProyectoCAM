"""2D Kalman filter for smooth object tracking.

State vector:  [x, y, vx, vy]^T
Measurement:   [x, y]^T         (center of detected object)

When YOLO detects the object → update() corrects the state.
When YOLO misses (occlusion) → predict() estimates position from velocity.

Q (process noise):  how fast the filter adapts to changes
R (measurement noise): how much it trusts the detection vs its own prediction
"""

from dataclasses import dataclass, field

import numpy as np


@dataclass
class KalmanFilter:
    """Discrete 2D Kalman filter with adjustable Q and R.

    Parameters
    ----------
    dt : float
        Time step (default 1.0 — works per-frame).
    q_scale : float
        Default process-noise multiplier.
    r_scale : float
        Default measurement-noise multiplier.
    """

    dt: float = 1.0
    q_scale: float = 0.1
    r_scale: float = 1.0

    # ── internal state (initialised lazily) ──────────────
    x: np.ndarray = field(init=False)          # state [x, y, vx, vy]
    P: np.ndarray = field(init=False)          # covariance
    F: np.ndarray = field(init=False)          # transition matrix
    H: np.ndarray = field(init=False)          # measurement matrix
    _initialised: bool = field(default=False, init=False)
    _last_bbox_size: tuple = field(default=(0, 0), init=False)

    def __post_init__(self):
        dt = self.dt
        # State transition: constant-velocity model
        self.F = np.array([
            [1, 0, dt, 0],
            [0, 1, 0, dt],
            [0, 0, 1, 0],
            [0, 0, 0, 1],
        ], dtype=np.float64)

        # We only measure x, y
        self.H = np.array([
            [1, 0, 0, 0],
            [0, 1, 0, 0],
        ], dtype=np.float64)

        # Base process-noise — penalise velocity less than position
        self._Q_base = np.array([
            [1, 0, 0, 0],
            [0, 1, 0, 0],
            [0, 0, 0.1, 0],
            [0, 0, 0, 0.1],
        ], dtype=np.float64)

        # Base measurement-noise
        self._R_base = np.eye(2, dtype=np.float64) * 10.0

        # State will be allocated on first update()
        self.x = np.zeros((4, 1), dtype=np.float64)
        self.P = np.eye(4, dtype=np.float64) * 100.0

    # ── public parameter setters (called from trackbars) ─

    def set_Q(self, value: float) -> None:
        """Set process-noise multiplier (> 0)."""
        self.q_scale = max(1e-6, value)

    def set_R(self, value: float) -> None:
        """Set measurement-noise multiplier (> 0)."""
        self.r_scale = max(1e-6, value)

    # ── core Kalman operations ───────────────────────────

    def _Q(self) -> np.ndarray:
        return self._Q_base * self.q_scale

    def _R(self) -> np.ndarray:
        return self._R_base * self.r_scale

    def initialise(self, x: float, y: float, w: int, h: int) -> None:
        """Initialise state from the first detection."""
        self.x = np.array([[x], [y], [0], [0]], dtype=np.float64)
        self.P = np.eye(4, dtype=np.float64) * 50.0
        self._last_bbox_size = (w, h)
        self._initialised = True

    def predict(self) -> tuple[int, int]:
        """Predict next state without a measurement (occlusion).

        Returns
        -------
        (x, y) : predicted centre coordinates.
        """
        Q = self._Q()
        self.x = self.F @ self.x
        self.P = self.F @ self.P @ self.F.T + Q

        if not self._initialised:
            return 0, 0
        return int(self.x[0, 0]), int(self.x[1, 0])

    def update(self, x: float, y: float, w: int, h: int) -> tuple[int, int]:
        """Update filter with a new detection from YOLO.

        Parameters
        ----------
        x, y : Measured centre coordinates.
        w, h : Bounding-box size (for persistence during occlusion).

        Returns
        -------
        (x, y) : Smoothed centre coordinates.
        """
        self._last_bbox_size = (w, h)

        if not self._initialised:
            self.initialise(x, y, w, h)
            return int(self.x[0, 0]), int(self.x[1, 0])

        R = self._R()
        Q = self._Q()

        # ── predict ──
        self.x = self.F @ self.x
        self.P = self.F @ self.P @ self.F.T + Q

        # ── update ──
        z = np.array([[x], [y]], dtype=np.float64)
        innovation = z - self.H @ self.x
        S = self.H @ self.P @ self.H.T + R
        K = self.P @ self.H.T @ np.linalg.inv(S)      # Kalman gain

        self.x = self.x + K @ innovation
        self.P = (np.eye(4) - K @ self.H) @ self.P

        return int(self.x[0, 0]), int(self.x[1, 0])

    # ── helpers ──────────────────────────────────────────

    @property
    def position(self) -> tuple[int, int]:
        """Current smoothed position (centre)."""
        return int(self.x[0, 0]), int(self.x[1, 0])

    @property
    def bbox_size(self) -> tuple[int, int]:
        """Last known bounding-box size (w, h)."""
        return self._last_bbox_size

    @property
    def is_initialised(self) -> bool:
        return self._initialised
