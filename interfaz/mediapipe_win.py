"""OpenCV analysis window — MediaPipe Pose + Hands with Kalman smoothing.

Layout (resizable):
┌─────────────────────────┬──────────────────────────────┐
│   VIDEO (auto-resize)   │  🎛 POSE / MANOS             │
│                         │  ─────────────────           │
│   Overlays:             │  Modo: Cuerpo Simple (12)    │
│    · Esqueleto (verde)  │  ●──●── Confianza           │
│    · Predicción (amar.) │  ●──●── Q (Proceso)         │
│    · Landmarks          │  ●──●── R (Medición)        │
│                         │  ─────────────────           │
│                         │  Detectados: 8/12           │
│                         │  Prediciendo: 4             │
│                         │  FPS: 30.2                  │
│                         │  ─────────────────           │
│                         │  1-4: modo  ESC:salir        │
│                         │  SPACE: pausa                │
└─────────────────────────┴──────────────────────────────┘

Controles
---------
ESC / Q          → Salir (vuelve a tkinter)
SPACE / P        → Pausa / reanudar
1 / 2 / 3 / 4    → Cambiar modo de operación
Mouse en slider  → Ajustar parámetros en vivo
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Optional

import cv2
import numpy as np

from tracker.detector_pose_manos import PoseHandTracker

if TYPE_CHECKING:
    from camara.stream import CameraStream

logger = logging.getLogger(__name__)


# ── constants ─────────────────────────────────────────────

_WIN_NAME = "Pose / Manos - ProyectoPDI"
_PANEL_W = 280
_SLIDER_H = 70


# ═══════════════════════════════════════════════════════════
#  MediaPipeWindow
# ═══════════════════════════════════════════════════════════


class MediaPipeWindow:
    """OpenCV window for MediaPipe pose/hand tracking with Kalman smoothing.

    Features:
    - 4 modes (1-4 keys) with dynamic Kalman array management
    - Custom sliders for confidence, process noise (Q), measurement noise (R)
    - Visual distinction: green = detected, yellow = predicting (occlusion)
    - Auto-cleanup on exit
    """

    def __init__(self, stream: CameraStream):
        self._stream = stream

        # ── tracker ──
        self._tracker = PoseHandTracker(mode=PoseHandTracker.MODE_CUERPO_SIMPLE)

        # ── slider values ──
        self._conf = 0.5
        self._q_val = 1.0
        self._r_val = 2.0

        # ── FPS ──
        self._fps_display = 0.0

        # ── drag state for sliders ──
        self._drag_idx: Optional[int] = None

        # ── layout cache ──
        self._panel_left = 0

    # ── main loop ─────────────────────────────────────────

    def run(self) -> None:
        """Blocking loop — returns when user presses ESC."""
        cv2.destroyAllWindows()
        for _ in range(5):
            cv2.waitKey(50)

        self._create_window()
        logger.info("MediaPipe analysis started — mode: %s", self._tracker.mode)

        paused = False
        last_frame: Optional[np.ndarray] = None

        try:
            while True:
                frame = self._stream.read()
                if frame is not None:
                    last_frame = frame
                    if not paused:
                        self._process_frame(frame)
                    elif last_frame is not None:
                        self._show_static(last_frame)
                else:
                    k = cv2.waitKey(30) & 0xFF
                    if k in (27, ord("q"), ord("Q")):
                        break
                    continue

                key = cv2.waitKey(1) & 0xFF

                # ESC / Q → exit
                if key in (27, ord("q"), ord("Q")):
                    break

                # SPACE / P → pause toggle
                elif key in (ord(" "), ord("p"), ord("P")):
                    paused = not paused
                    logger.info("%s", "Paused" if paused else "Resumed")

                # 1-4 → mode switch
                elif key in (ord("1"), ord("2"), ord("3"), ord("4")):
                    idx = int(chr(key)) - 1
                    new_mode = PoseHandTracker.MODES[idx]
                    old_mode = self._tracker.mode
                    self._tracker.set_mode(new_mode)
                    logger.info("Modo: %s → %s", old_mode, new_mode)

        finally:
            self._tracker.close()
            cv2.destroyAllWindows()
            logger.info("MediaPipe window closed")

    # ── per-frame ─────────────────────────────────────────

    def _process_frame(self, frame: np.ndarray) -> None:
        """Tracker → draw → compose canvas → imshow."""
        # Sincronizar parámetros de trackbars al tracker
        self._tracker.conf_threshold = self._conf
        self._tracker.q_scale = self._q_val
        self._tracker.r_scale = self._r_val

        # Procesar: MediaPipe + Kalman por landmark
        self._tracker.process(frame)

        # Dibujar overlay sobre el frame (in-place)
        self._tracker.draw(frame)

        # FPS display
        self._fps_display = self._tracker.fps

        # Componer canvas + panel lateral
        canvas = self._build_canvas(frame)
        cv2.imshow(_WIN_NAME, canvas)

    def _show_static(self, frame: np.ndarray) -> None:
        """When paused, show the last canvas."""
        canvas = self._build_canvas(frame)
        cv2.imshow(_WIN_NAME, canvas)

    # ── canvas composition ───────────────────────────────

    def _build_canvas(self, frame: np.ndarray) -> np.ndarray:
        """Build [scaled video | control panel] matching current window size."""
        try:
            r = cv2.getWindowImageRect(_WIN_NAME)
            if r[2] > 10 and r[3] > 10:
                win_w, win_h = r[2], r[3]
            else:
                win_w, win_h = self._initial_size(frame)
        except cv2.error:
            win_w, win_h = self._initial_size(frame)

        video_w = max(win_w - _PANEL_W, 200)
        video_h = max(win_h, 200)
        self._panel_left = video_w

        fh, fw = frame.shape[:2]
        scale = min(video_w / fw, video_h / fh)
        new_w = max(int(fw * scale), 1)
        new_h = max(int(fh * scale), 1)

        canvas = np.zeros((video_h, win_w, 3), dtype=np.uint8)
        canvas[:] = (20, 20, 20)

        resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
        x_off = (video_w - new_w) // 2
        y_off = (video_h - new_h) // 2
        canvas[y_off:y_off + new_h, x_off:x_off + new_w] = resized

        self._draw_panel(canvas, video_w)

        return canvas

    @staticmethod
    def _initial_size(frame: np.ndarray) -> tuple[int, int]:
        h, w = frame.shape[:2]
        return (w + _PANEL_W, h)

    # ── control panel ─────────────────────────────────────

    def _draw_panel(self, canvas: np.ndarray, px: int) -> None:
        """Draw the right-side control panel."""
        ch = canvas.shape[0]

        # Background
        cv2.rectangle(canvas, (px, 0), (px + _PANEL_W, ch), (30, 30, 30), -1)

        # ── title ──
        cv2.putText(canvas, "POSE / MANOS", (px + 20, 28),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (220, 220, 220), 1)

        # ── mode display ──
        mode_name = self._tracker.mode_label
        cv2.putText(canvas, f"Modo:", (px + 20, 52),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1)
        cv2.putText(canvas, mode_name, (px + 20, 70),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 220, 220), 1)

        # ── sliders ──
        sl = px + 25
        sw = 165
        sy0 = 90

        self._draw_one_slider(canvas, sl, sy0, sw, "Confianza",
                              self._conf, 0.01, 1.0, "%.2f", (0, 200, 0))
        self._draw_one_slider(canvas, sl, sy0 + _SLIDER_H, sw, "Q (Proceso)",
                              self._q_val, 0.0, 10.0, "%.1f", (0, 160, 255))
        self._draw_one_slider(canvas, sl, sy0 + 2 * _SLIDER_H, sw, "R (Medicion)",
                              self._r_val, 0.0, 20.0, "%.1f", (255, 120, 0))

        # ── separator ──
        sep_y = sy0 + 3 * _SLIDER_H + 12
        cv2.line(canvas, (px + 15, sep_y), (px + _PANEL_W - 15, sep_y),
                 (60, 60, 60), 1)

        # ── detection status ──
        dy = sep_y + 18
        nd = self._tracker.num_detected
        np_ = self._tracker.num_predicting
        total = self._tracker.num_landmarks

        cv2.putText(canvas, f"Detectados: {nd}/{total}",
                    (px + 20, dy), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                    (0, 220, 0) if nd > 0 else (120, 120, 120), 1)
        cv2.putText(canvas, f"Prediciendo: {np_}",
                    (px + 20, dy + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                    (0, 220, 220) if np_ > 0 else (120, 120, 120), 1)

        # ── FPS ──
        cv2.putText(canvas, f"FPS: {self._fps_display:.1f}",
                    (px + 20, dy + 50), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                    (0, 255, 255), 1)

        # ── controls hint ──
        hy = ch - 90
        hints = [
            "1-4: Cambiar modo",
            "ESC: Salir",
            "SPACE: Pausa",
        ]
        for i, line in enumerate(hints):
            cv2.putText(canvas, line, (px + 20, hy + i * 18),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (90, 90, 90), 1)

        # ── mode indicators (mini legend) ──
        mode_lines = [
            ("[1] Cpo.Simple", 0, 200, 0),
            ("[2] Cpo.Comp.", 0, 180, 100),
            ("[3] Mano Simp.", 100, 180, 0),
            ("[4] Mano Comp.", 0, 100, 200),
        ]
        ly = hy - 85
        for i, (text, r, g, b) in enumerate(mode_lines):
            color = (b, g, r)
            # Highlight current mode
            if i == PoseHandTracker.MODES.index(self._tracker.mode):
                cv2.putText(canvas, text, (px + 20, ly + i * 18),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
            else:
                cv2.putText(canvas, text, (px + 20, ly + i * 18),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (80, 80, 80), 1)

    # ── single slider ─────────────────────────────────────

    def _draw_one_slider(
        self, canvas: np.ndarray,
        x: int, y: int, width: int,
        label: str, value: float, vmin: float, vmax: float,
        fmt: str, color: tuple,
    ) -> None:
        """Draw one custom slider (label + track + thumb + value)."""
        # Label
        cv2.putText(canvas, label, (x, y + 14),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)
        # Track
        ty = y + 30
        cv2.line(canvas, (x, ty), (x + width, ty), (70, 70, 70), 4)
        # Active portion
        ratio = (value - vmin) / (vmax - vmin) if vmax > vmin else 0
        tx = x + int(ratio * width)
        cv2.line(canvas, (x, ty), (tx, ty), color, 4)
        # Thumb
        cv2.circle(canvas, (tx, ty), 8, color, -1)
        cv2.circle(canvas, (tx, ty), 8, (255, 255, 255), 1)
        # Value text
        cv2.putText(canvas, fmt % value, (x + width + 10, ty + 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (180, 180, 180), 1)

    # ── mouse callback ────────────────────────────────────

    def _create_window(self) -> None:
        cv2.namedWindow(
            _WIN_NAME,
            cv2.WINDOW_NORMAL | cv2.WINDOW_GUI_NORMAL,
        )
        cv2.resizeWindow(_WIN_NAME, 960, 540)
        cv2.setMouseCallback(_WIN_NAME, self._on_mouse)

    def _on_mouse(self, event: int, mx: int, my: int,
                  _flags: int, _userdata: object = None) -> None:
        """Handle slider thumb drag."""
        pl = self._panel_left

        if event == cv2.EVENT_LBUTTONDOWN:
            if pl <= mx <= pl + _PANEL_W:
                for idx in range(3):  # 3 sliders: conf, Q, R
                    sx = pl + 25
                    sw = 165
                    # sy0=90, track_y = 90 + 30 + idx * 70 = 120 + idx * 70
                    track_y = 120 + idx * _SLIDER_H
                    val = [self._conf, self._q_val, self._r_val][idx]
                    lo, hi = [(0.01, 1.0), (0.0, 10.0), (0.0, 20.0)][idx]
                    ratio = (val - lo) / (hi - lo) if hi > lo else 0
                    tx = sx + int(ratio * sw)
                    dx = mx - tx
                    dy = my - track_y
                    if dx * dx + dy * dy < 14 * 14:
                        self._drag_idx = idx
                        break

        elif event == cv2.EVENT_MOUSEMOVE and self._drag_idx is not None:
            idx = self._drag_idx
            sx = pl + 25
            sw = 165
            lo, hi = [(0.01, 1.0), (0.0, 10.0), (0.0, 20.0)][idx]
            tx = max(sx, min(mx, sx + sw))
            ratio = (tx - sx) / sw
            val = lo + ratio * (hi - lo)
            val = max(lo, min(hi, val))
            if idx == 0:
                self._conf = val
            elif idx == 1:
                self._q_val = val
            else:
                self._r_val = val

        elif event == cv2.EVENT_LBUTTONUP:
            self._drag_idx = None
