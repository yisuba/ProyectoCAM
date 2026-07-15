"""OpenCV analysis window — single-window layout with custom sliders.

Layout (resizable):
┌─────────────────────────┬──────────────────────┐
│   VIDEO (auto-resize)   │  🎛 PARAMETROS       │
│                         │  ●──●── Confianza    │
│   Overlays:             │  ●──●── Q (Proceso)  │
│    · Bbox Kalman (verde)│  ●──●── R (Medicion) │
│    · Bbox YOLO (azul)   │  ─── ─── ─── ───    │
│    · Trail centro       │  Leyenda + FPS       │
│                         │  Estado deteccion    │
└─────────────────────────┴──────────────────────┘

Controles
---------
ESC / Q             → Salir
SPACE / P           → Pausa / reanudar
Mouse drag en slider → Ajustar parametros
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Optional

import cv2
import numpy as np
import psutil

from tracker.detector import COCO_CLASSES, Detector, Detection
from tracker.kalman import KalmanFilter

if TYPE_CHECKING:
    from camara.stream import CameraStream

logger = logging.getLogger(__name__)


# ── constants ─────────────────────────────────────────────

_WIN_NAME = "Object Tracking - ProyectoPDI"
_PANEL_W = 280          # right panel width (px)
_TRAIL_MAX = 30
_SLIDER_H = 55          # height per slider row


# ═══════════════════════════════════════════════════════════
#  AnalysisWindow
# ═══════════════════════════════════════════════════════════


class AnalysisWindow:
    """OpenCV window with YOLO + Kalman tracking and custom sliders."""

    def __init__(self, stream: CameraStream, target_class: int = 0):
        self._stream = stream
        self._detector = Detector(target_class=target_class)
        self._kf = KalmanFilter()

        # ── class cycling ──
        self._class_list: list[tuple[int, str]] = sorted(
            COCO_CLASSES.items(), key=lambda x: x[1]
        )
        self._class_idx = 0
        for i, (cid, _) in enumerate(self._class_list):
            if cid == target_class:
                self._class_idx = i
                break
        # rect where the class label is drawn (for click detection)
        self._class_rect: tuple[int, int, int, int] = (0, 0, 0, 0)

        # ── slider values ──
        self._conf = 0.25
        self._q_val = 1.0
        self._r_val = 2.0
        self._trail_len = 30.0  # trail length in points

        # ── hybrid tracking state ──
        self._hybrid_mode = True    # True = async, False = continuo
        self._yolo_interval = 10    # YOLO cada N frames (solo async)
        self._kcf: Optional["cv2.TrackerKCF"] = None
        self._kcf_init = False
        self._frame_idx = 0         # contador de frames para modo async
        self._track_source = "YOLO"  # YOLO | KCF | PREDICT — para mostrar
        self._kcf_success = False    # si KCF trackeó bien el último frame
        self._kcf_bbox: Optional[tuple[int, int, int, int]] = None  # (x, y, w, h) último KCF

        # ── resource metrics ──
        self._show_metrics = False
        self._cpu_pct = 0.0
        self._ram_pct = 0.0
        self._frame_time_ms = 0.0    # tiempo del último frame procesado

        # ── visualisation state ──
        self._trail: list[tuple[int, int]] = []
        self._fps = 0.0
        self._frame_count = 0
        self._last_fps_time = time.perf_counter()
        self._fps_interval = 0.5

        # ── toggle flags ──
        self._show_kalman = True
        self._show_yolo = True
        self._show_kcf = True

        # ── drag state ──
        self._drag_idx: Optional[int] = None

        # ── dropdown state ──
        self._dropdown_open = False
        self._dropdown_scroll = 0  # scroll offset in class list
        self._dropdown_highlight = 0  # highlighted item index (absolute)
        self._class_name_rect = (0, 0, 0, 0)
        self._dropdown_up_rect = (0, 0, 0, 0)
        self._dropdown_down_rect = (0, 0, 0, 0)
        self._dropdown_item_rects: list[tuple[int, int, int, int, int]] = []
        self._kalman_toggle_rect = (0, 0, 0, 0)
        self._yolo_toggle_rect = (0, 0, 0, 0)

        # ── layout cache (updated every frame) ──
        self._panel_left = 0   # x-coord of panel left edge in canvas

    # ── main loop ─────────────────────────────────────────

    def run(self) -> None:
        """Blocking loop — returns when user presses ESC."""
        # Clean up any lingering windows from previous runs
        cv2.destroyAllWindows()
        for _ in range(5):
            cv2.waitKey(50)  # give OpenCV time to destroy

        self._create_window()
        logger.info(
            "Analysis started — tracking class %d (%s), mode=%s%s",
            self._detector.target_class,
            self._detector.target_name,
            "async" if self._hybrid_mode else "continuous",
            f" (YOLO cada {self._yolo_interval})" if self._hybrid_mode else "",
        )

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
                    if k == 27:
                        if self._dropdown_open:
                            self._dropdown_open = False
                            continue
                        break
                    continue

                key = cv2.waitKey(1) & 0xFF

                # ESC/Q — close dropdown if open, otherwise exit
                if key in (27, ord("q"), ord("Q")):
                    if self._dropdown_open:
                        self._dropdown_open = False
                    else:
                        break
                elif key in (ord(" "), ord("p"), ord("P")):
                    paused = not paused
                    logger.info("%s", "Paused" if paused else "Resumed")
                elif key in (ord("c"), ord("C")):
                    self._hybrid_mode = not self._hybrid_mode
                    self._frame_idx = 0
                    # KCF se crea una sola vez por sesion async
                    self._kcf = None
                    self._kcf_init = False
                    logger.info("Mode: %s", f"Async (YOLO cada {self._yolo_interval})" if self._hybrid_mode else "Continuo")
                elif key in (ord("m"), ord("M")):
                    self._show_metrics = not self._show_metrics
                    logger.info("Metrics: %s", "ON" if self._show_metrics else "OFF")

                # ── dropdown open: N/B to page through classes ──
                elif self._dropdown_open:
                    n_total = len(self._class_list)
                    if key in (ord("n"), ord("N")):
                        step = min(10, n_total - self._dropdown_highlight - 1)
                        if step > 0:
                            self._dropdown_highlight += step
                    elif key in (ord("b"), ord("B")):
                        step = min(10, self._dropdown_highlight)
                        if step > 0:
                            self._dropdown_highlight -= step

                # ── N/B when closed → open dropdown ──
                elif key in (ord("n"), ord("N"), ord("b"), ord("B")):
                    self._dropdown_open = True
                    self._dropdown_highlight = self._class_idx
                    self._dropdown_scroll = max(0, self._class_idx - 5)
        finally:
            cv2.destroyAllWindows()
            logger.info("Analysis window closed")

    # ── per-frame ─────────────────────────────────────────

    def _process_frame(self, frame: np.ndarray) -> None:
        """Hybrid pipeline: decide every frame whether to run YOLO or KCF.

        - Async mode (_hybrid_mode=True): YOLO cada 10 frames, KCF los 9 intermedios.
        - Continuous mode (_hybrid_mode=False): YOLO en todos los frames (comportamiento clasico).
        - Kalman se actualiza con la fuente disponible (YOLO, KCF o prediccion autonoma).
        """
        t_start = time.perf_counter()

        # Reset Kalman + KCF on video loop
        if self._stream.looped:
            logger.debug("Video loop detected — resetting Kalman + trail + KCF")
            self._kf = KalmanFilter()
            self._trail.clear()
            self._kcf_init = False
            self._kcf = None

        self._kf.set_Q(self._q_val)
        self._kf.set_R(self._r_val)

        self._frame_idx += 1
        run_yolo = (not self._hybrid_mode) or (self._frame_idx % self._yolo_interval == 0)

        kalman_cx, kalman_cy = 0, 0
        best_det: Optional[Detection] = None
        self._kcf_success = False

        if run_yolo:
            # ── YOLO detect ──
            detections = self._detector.detect(frame, conf_threshold=self._conf)
            if detections:
                best_det = detections[0]
                cx, cy = best_det.center
                x1, y1, x2, y2 = best_det.bbox
                kw, kh = x2 - x1, y2 - y1

                # Re-init KCF solo en async (en continuo no se usa KCF)
                if self._hybrid_mode:
                    self._init_kcf(frame, (x1, y1, kw, kh))

                # Kalman update con YOLO
                kalman_cx, kalman_cy = self._kf.update(cx, cy, kw, kh)
                self._track_source = "YOLO"
            elif self._kf.is_initialised:
                kalman_cx, kalman_cy = self._kf.predict()
                self._track_source = "PREDICT"
        elif self._hybrid_mode:
            # ── KCF track (frames intermedios en modo async) ──
            if self._kcf_init:
                success, bbox = self._kcf.update(frame)
                self._kcf_success = success
                if success:
                    x, y, w, h = [int(v) for v in bbox]
                    cx, cy = x + w // 2, y + h // 2
                    kalman_cx, kalman_cy = self._kf.update(cx, cy, w, h)
                    self._track_source = "KCF"
                    self._kcf_bbox = (x, y, w, h)
                elif self._kf.is_initialised:
                    kalman_cx, kalman_cy = self._kf.predict()
                    self._track_source = "PREDICT"
            elif self._kf.is_initialised:
                kalman_cx, kalman_cy = self._kf.predict()
                self._track_source = "PREDICT"

        # FPS
        self._update_fps()

        # Resource metrics (cada ~10 frames ≈ 3×/seg a 30fps)
        if self._frame_idx % 10 == 0:
            self._cpu_pct = psutil.cpu_percent(interval=None)
            self._ram_pct = psutil.virtual_memory().percent

        # Per-frame processing time
        self._frame_time_ms = (time.perf_counter() - t_start) * 1000

        # draw overlay
        display = frame.copy()
        self._draw_overlay(display, best_det, (kalman_cx, kalman_cy))

        # compose + show
        canvas = self._build_canvas(display, best_det, (kalman_cx, kalman_cy))
        cv2.imshow(_WIN_NAME, canvas)

    def _init_kcf(self, frame: np.ndarray, bbox_wh: tuple[int, int, int, int]) -> None:
        """Inicializa KCF UNA SOLA VEZ. Si ya existe, no lo recrea (evita acumulación)."""
        if self._kcf is not None:
            return  # ya inicializado — YOLO corrige via Kalman, KCF sigue vivo
        self._kcf = cv2.TrackerKCF_create()
        self._kcf.init(frame, bbox_wh)
        self._kcf_init = True
        self._kcf_bbox = bbox_wh
        logger.debug("KCF initialised with bbox %s", bbox_wh)

    def _show_static(self, frame: np.ndarray) -> None:
        """When paused, keep showing last canvas."""
        canvas = self._build_canvas(frame, None, (0, 0))
        cv2.imshow(_WIN_NAME, canvas)

    # ── canvas composition ───────────────────────────────

    def _build_canvas(
        self,
        frame: np.ndarray,
        detection: Optional[Detection],
        kalman_pos: tuple[int, int],
    ) -> np.ndarray:
        """Build [scaled video | control panel] matching current window size."""
        # Get current window size
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
        self._panel_left = video_w  # ← cache for mouse callback

        fh, fw = frame.shape[:2]
        scale = min(video_w / fw, video_h / fh)
        new_w = max(int(fw * scale), 1)
        new_h = max(int(fh * scale), 1)

        # Dark canvas
        canvas = np.zeros((video_h, win_w, 3), dtype=np.uint8)
        canvas[:] = (20, 20, 20)

        # Place scaled video (centred)
        resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
        x_off = (video_w - new_w) // 2
        y_off = (video_h - new_h) // 2
        canvas[y_off:y_off + new_h, x_off:x_off + new_w] = resized

        # Control panel
        self._draw_panel(canvas, video_w, detection, kalman_pos)

        return canvas

    @staticmethod
    def _initial_size(frame: np.ndarray) -> tuple[int, int]:
        h, w = frame.shape[:2]
        return (w + _PANEL_W, h)

    # ── control panel ─────────────────────────────────────

    def _draw_panel(
        self,
        canvas: np.ndarray,
        px: int,
        detection: Optional[Detection],
        kalman_pos: tuple[int, int],
    ) -> None:
        """Draw the right-side control panel."""
        ch = canvas.shape[0]

        # Background
        cv2.rectangle(canvas, (px, 0), (px + _PANEL_W, ch), (30, 30, 30), -1)

        # ── title ──
        cv2.putText(canvas, "PARAMETROS", (px + 20, 28),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (220, 220, 220), 1)

        # ── sliders ──
        sl = px + 25          # slider left edge
        sw = 165              # slider track width
        sy0 = 50              # first slider top

        self._draw_one_slider(canvas, sl, sy0, sw, "Confianza",
                              self._conf, 0.0, 1.0, "%.2f", (0, 200, 0))
        self._draw_one_slider(canvas, sl, sy0 + _SLIDER_H, sw, "Q (Proceso)",
                              self._q_val, 0.0, 10.0, "%.1f", (0, 160, 255))
        self._draw_one_slider(canvas, sl, sy0 + 2 * _SLIDER_H, sw, "R (Medicion)",
                              self._r_val, 0.0, 20.0, "%.1f", (255, 120, 0))
        self._draw_one_slider(canvas, sl, sy0 + 3 * _SLIDER_H, sw, "Estela (pts)",
                              self._trail_len, 1.0, 60.0, "%.0f", (200, 0, 200))

        # 5th slider: YOLO interval (solo en async mode)
        if self._hybrid_mode:
            self._draw_one_slider(canvas, sl, sy0 + 4 * _SLIDER_H, sw, "YOLO cada N",
                                  self._yolo_interval, 3.0, 20.0, "%.0f", (0, 200, 200))

        # ── separator ──
        n_sliders = 5 if self._hybrid_mode else 4
        sep_y = sy0 + n_sliders * _SLIDER_H + 8
        cv2.line(canvas, (px + 15, sep_y), (px + _PANEL_W - 15, sep_y),
                 (60, 60, 60), 1)

        # ── legend (clickeable — toggle overlay on/off) ──
        ly = sep_y + 18
        # Kalman
        km_col = (0, 220, 0) if self._show_kalman else (50, 50, 50)
        km_label = (180, 180, 180) if self._show_kalman else (80, 80, 80)
        cv2.circle(canvas, (px + 22, ly), 5, km_col, -1)
        cv2.putText(canvas, "Kalman", (px + 34, ly + 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, km_label, 1)
        self._kalman_toggle_rect = (px + 18, ly - 12, px + 100, ly + 12)
        # YOLO (azul para coincidir con el overlay)
        yl_col = (255, 120, 0) if self._show_yolo else (50, 50, 50)
        yl_label = (180, 180, 180) if self._show_yolo else (80, 80, 80)
        cv2.circle(canvas, (px + 22, ly + 22), 5, yl_col, -1)
        cv2.putText(canvas, "YOLO", (px + 34, ly + 27),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, yl_label, 1)
        self._yolo_toggle_rect = (px + 18, ly + 10, px + 100, ly + 34)
        # KCF (amarillo)
        kcf_col = (0, 255, 255) if self._show_kcf else (50, 50, 50)
        kcf_label = (180, 180, 180) if self._show_kcf else (80, 80, 80)
        cv2.circle(canvas, (px + 22, ly + 44), 5, kcf_col, -1)
        cv2.putText(canvas, "KCF", (px + 34, ly + 49),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, kcf_label, 1)
        self._kcf_toggle_rect = (px + 18, ly + 32, px + 100, ly + 56)

        # ── detection status ──
        dy = ly + 72
        if detection:
            txt = f"{self._detector.target_name}  {detection.confidence:.2f}"
            col = (0, 200, 0)
        elif self._kf.is_initialised:
            txt = f"{self._detector.target_name}  [prediciendo]"
            col = (200, 200, 0)
        else:
            txt = "Sin deteccion"
            col = (120, 120, 120)
        cv2.putText(canvas, txt, (px + 20, dy),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, col, 1)

        # ── mode indicator ──
        my = dy + 22
        mode_txt = f"Async (c/{self._yolo_interval})" if self._hybrid_mode else "Continuo"
        src_txt = f"Src: {self._track_source}"
        cv2.putText(canvas, f"Modo: {mode_txt}", (px + 20, my),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1)
        cv2.putText(canvas, src_txt, (px + 20, my + 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (140, 140, 140), 1)

        # ── resource metrics (toggleable with M, una linea compacta) ──
        if self._show_metrics:
            met_y = my + 36
            cv2.putText(canvas, f"CPU:{self._cpu_pct:.0f}% RAM:{self._ram_pct:.0f}% {self._frame_time_ms:.0f}ms",
                        (px + 20, met_y), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (100, 200, 255), 1)

        # ── class selector (click name + ▼ to open dropdown) ──
        cy = (my + 52) if self._show_metrics else (my + 36)
        cid, cname = self._class_list[self._class_idx]
        name_x = px + 20
        cv2.putText(canvas, cname, (name_x, cy),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 0), 1)
        txt_size = cv2.getTextSize(cname, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)[0]
        drop_x = name_x + txt_size[0] + 6
        indicator = "v" if not self._dropdown_open else "^"
        cv2.putText(canvas, indicator, (drop_x, cy),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 200), 1)
        self._class_name_rect = (name_x - 4, cy - 18, drop_x + 12, cy + 6)

        # ── dropdown ──
        if self._dropdown_open:
            self._draw_dropdown(canvas, px, ch, cy + 20)

        # ── controls hint ──
        hy = ch - 55
        for i, line in enumerate(["ESC: salir", "SPACE: pausa", "C: modo continuo/async", "M: recursos", "N/B: paginar menu"]):
            cv2.putText(canvas, line, (px + 20, hy + i * 18),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (90, 90, 90), 1)

    # ── dropdown list ────────────────────────────────────

    def _draw_dropdown(self, canvas: np.ndarray, px: int, ch: int, y0: int) -> None:
        """Draw scrollable class dropdown within the panel."""
        n_total = len(self._class_list)
        max_visible = max(4, (ch - y0 - 60) // 16)  # fit to available height
        max_visible = min(max_visible, 15)

        # Background
        dh = min(y0 + max_visible * 16 + 32, ch - 10)
        cv2.rectangle(canvas, (px + 5, y0 - 4), (px + _PANEL_W - 5, dh), (40, 40, 40), -1)
        cv2.rectangle(canvas, (px + 5, y0 - 4), (px + _PANEL_W - 5, dh), (70, 70, 70), 1)

        # Pin highlight to visible area
        if self._dropdown_highlight < self._dropdown_scroll:
            self._dropdown_scroll = self._dropdown_highlight
        elif self._dropdown_highlight >= self._dropdown_scroll + max_visible:
            self._dropdown_scroll = self._dropdown_highlight - max_visible + 1

        # Up arrow (scroll back)
        arrow_y = y0 + 2
        self._dropdown_up_rect = (px + _PANEL_W - 30, arrow_y - 8, px + _PANEL_W - 10, arrow_y + 6)
        if self._dropdown_scroll > 0:
            cv2.putText(canvas, "^", (px + _PANEL_W - 28, arrow_y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 200), 1)
        else:
            cv2.putText(canvas, "^", (px + _PANEL_W - 28, arrow_y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (50, 50, 50), 1)

        # Items
        self._dropdown_item_rects: list[tuple[int, int, int, int, int]] = []
        for i in range(max_visible):
            idx = self._dropdown_scroll + i
            if idx >= n_total:
                break
            cid, cname = self._class_list[idx]
            iy = y0 + 18 + i * 16
            # Background: highlight takes priority
            if idx == self._dropdown_highlight:
                bg = (70, 100, 70)  # greenish highlight
                border_color = (0, 200, 0)
            elif idx == self._class_idx:
                bg = (60, 60, 60)
            elif i % 2 == 0:
                bg = (48, 48, 48)
            else:
                bg = (44, 44, 44)
            cv2.rectangle(canvas, (px + 8, iy - 11), (px + _PANEL_W - 8, iy + 3), bg, -1)
            if idx == self._dropdown_highlight:
                cv2.rectangle(canvas, (px + 8, iy - 11), (px + _PANEL_W - 8, iy + 3), border_color, 1)
            color = (200, 200, 0) if idx == self._class_idx else (220, 220, 220)
            cv2.putText(canvas, cname, (px + 12, iy),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35, color, 1)
            self._dropdown_item_rects.append((px + 8, iy - 11, px + _PANEL_W - 8, iy + 3, idx))

        # Down arrow (scroll forward)
        down_y = y0 + 18 + max_visible * 16 + 4
        self._dropdown_down_rect = (px + _PANEL_W - 30, down_y - 8, px + _PANEL_W - 10, down_y + 6)
        if self._dropdown_scroll + max_visible < n_total:
            cv2.putText(canvas, "v", (px + _PANEL_W - 28, down_y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 200), 1)
        else:
            cv2.putText(canvas, "v", (px + _PANEL_W - 28, down_y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (50, 50, 50), 1)

    # ── single slider ─────────────────────────────────────

    def _draw_one_slider(
        self, canvas: np.ndarray,
        x: int, y: int, width: int,
        label: str, value: float, vmin: float, vmax: float,
        fmt: str, color: tuple,
    ) -> None:
        """Draw one slider (label + track + thumb + value)."""
        # Label
        cv2.putText(canvas, label, (x, y + 14),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)
        # Track
        ty = y + 30
        cv2.line(canvas, (x, ty), (x + width, ty), (70, 70, 70), 4)
        # Active
        ratio = (value - vmin) / (vmax - vmin) if vmax > vmin else 0
        tx = x + int(ratio * width)
        cv2.line(canvas, (x, ty), (tx, ty), color, 4)
        # Thumb
        cv2.circle(canvas, (tx, ty), 8, color, -1)
        cv2.circle(canvas, (tx, ty), 8, (255, 255, 255), 1)
        # Value
        cv2.putText(canvas, fmt % value, (x + width + 10, ty + 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (180, 180, 180), 1)

    # ── mouse callback ────────────────────────────────────

    def _create_window(self) -> None:
        # We use WINDOW_GUI_NORMAL to prevent the Qt backend from
        # creating a separate empty controls panel on some OpenCV builds.
        # WINDOW_NORMAL allows the user to resize the window.
        cv2.namedWindow(
            _WIN_NAME,
            cv2.WINDOW_NORMAL | cv2.WINDOW_GUI_NORMAL,
        )
        cv2.resizeWindow(_WIN_NAME, 960, 540)  # sensible default size
        cv2.setMouseCallback(_WIN_NAME, self._on_mouse)

    def _on_mouse(self, event: int, mx: int, my: int, _flags: int, _userdata: object = None) -> None:
        """Handle slider interaction via mouse drag."""
        pl = self._panel_left  # panel left edge
        pr = pl + _PANEL_W     # panel right edge

        if event == cv2.EVENT_LBUTTONDOWN:
            logger.debug("Mouse click at (%d, %d) panel_x=[%d,%d]",
                         mx, my, pl, pr)

            # ── if dropdown open, check its items first ──
            if self._dropdown_open:
                # Check up arrow
                l, t, r, b = self._dropdown_up_rect
                if l <= mx <= r and t <= my <= b and self._dropdown_scroll > 0:
                    self._dropdown_scroll = max(0, self._dropdown_scroll - 5)
                    return
                # Check down arrow
                l, t, r, b = self._dropdown_down_rect
                if l <= mx <= r and t <= my <= b:
                    max_visible = 15
                    if self._dropdown_scroll + max_visible < len(self._class_list):
                        self._dropdown_scroll += 5
                    return
                # Check item clicks
                for l, t, r, b, idx in self._dropdown_item_rects:
                    if l <= mx <= r and t <= my <= b:
                        self._jump_to_class(idx)
                        self._dropdown_open = False
                        return
                # Click anywhere else in panel → close dropdown
                if pl <= mx <= pr:
                    self._dropdown_open = False
                    return
                # Click outside panel → close dropdown
                self._dropdown_open = False

            # ── check slider thumbs ──
            if pl <= mx <= pr:
                for idx in range(self._n_sliders):
                    sx = pl + 25                        # slider left edge
                    sw = 165                             # slider track width
                    # track_y = sy0 + 30 + idx * _SLIDER_H
                    # sy0=50, so track_y = 80 + idx * _SLIDER_H
                    track_y = 80 + idx * _SLIDER_H
                    val = self._get_val(idx)
                    lo, hi = self._bounds(idx)
                    ratio = (val - lo) / (hi - lo) if hi > lo else 0
                    tx = sx + int(ratio * sw)            # thumb x
                    dx = mx - tx
                    dy = my - track_y
                    if dx * dx + dy * dy < 14 * 14:
                        self._drag_idx = idx
                        break
                else:
                    # ── check legend toggles ──
                    l, t, r, b = self._kalman_toggle_rect
                    if l <= mx <= r and t <= my <= b:
                        self._show_kalman = not self._show_kalman
                        logger.info("Kalman overlay %s", "ON" if self._show_kalman else "OFF")
                        return
                    l, t, r, b = self._yolo_toggle_rect
                    if l <= mx <= r and t <= my <= b:
                        self._show_yolo = not self._show_yolo
                        logger.info("YOLO overlay %s", "ON" if self._show_yolo else "OFF")
                        return
                    l, t, r, b = self._kcf_toggle_rect
                    if l <= mx <= r and t <= my <= b:
                        self._show_kcf = not self._show_kcf
                        logger.info("KCF overlay %s", "ON" if self._show_kcf else "OFF")
                        return
                    # ── check class name → toggle dropdown ──
                    l, t, r, b = self._class_name_rect
                    if l <= mx <= r and t <= my <= b:
                        self._dropdown_open = not self._dropdown_open
                        if self._dropdown_open:
                            self._dropdown_highlight = self._class_idx
                            self._dropdown_scroll = max(0, self._class_idx - 5)
                        return

        elif event == cv2.EVENT_MOUSEMOVE and self._drag_idx is not None:
            idx = self._drag_idx
            sx = pl + 25
            sw = 165
            lo, hi = self._bounds(idx)
            tx = max(sx, min(mx, sx + sw))
            ratio = (tx - sx) / sw
            val = lo + ratio * (hi - lo)
            self._set_val(idx, val)
            logger.debug("Drag slider %d → %.2f", idx, val)

        elif event == cv2.EVENT_LBUTTONUP:
            self._drag_idx = None

    def _get_val(self, idx: int) -> float:
        return [self._conf, self._q_val, self._r_val, self._trail_len, self._yolo_interval][idx]

    def _set_val(self, idx: int, v: float) -> None:
        v = max(0.0, v)
        if idx == 0:
            self._conf = min(v, 1.0)
        elif idx == 1:
            self._q_val = v
        elif idx == 2:
            self._r_val = v
        elif idx == 3:
            self._trail_len = min(v, 60.0)
        else:
            self._yolo_interval = max(3, min(round(v), 20))

    @staticmethod
    def _bounds(idx: int) -> tuple[float, float]:
        return [(0.0, 1.0), (0.0, 10.0), (0.0, 20.0), (1.0, 60.0), (3.0, 20.0)][idx]

    @property
    def _n_sliders(self) -> int:
        """5 sliders en async, 4 en continuo."""
        return 5 if self._hybrid_mode else 4

    # ── class cycling ─────────────────────────────────────

    def _cycle_class(self, direction: int = 1) -> None:
        """Switch to next (1) or previous (-1) class in the list and reset tracking."""
        n = len(self._class_list)
        self._class_idx = (self._class_idx + direction) % n
        cid, cname = self._class_list[self._class_idx]
        self._detector.target_class = cid

        # Reset Kalman + trail for new object
        self._kf = KalmanFilter()
        self._trail.clear()
        self._drag_idx = None

        logger.info("Switched to class %d (%s)", cid, cname)

    def _jump_to_class(self, idx: int) -> None:
        """Jump directly to a class by its index in the list."""
        cid, cname = self._class_list[idx]
        self._class_idx = idx
        self._detector.target_class = cid
        self._kf = KalmanFilter()
        self._trail.clear()
        self._drag_idx = None
        logger.info("Jumped to class %d (%s)", cid, cname)

    # ── overlay drawing ───────────────────────────────────

    def _draw_overlay(
        self,
        frame: np.ndarray,
        detection: Optional[Detection],
        kalman_pos: tuple[int, int],
    ) -> None:
        """Draw bbox, centre, trail, status over the frame."""
        h, w = frame.shape[:2]
        kx, ky = kalman_pos

        # Kalman bounding box (centred on smoothed pos)
        if self._show_kalman and self._kf.is_initialised:
            bw, bh = self._kf.bbox_size
            if bw > 0 and bh > 0:
                x1 = int(kx - bw / 2)
                y1 = int(ky - bh / 2)
                x2 = int(kx + bw / 2)
                y2 = int(ky + bh / 2)
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 220, 0), 2)
                overlay = frame.copy()
                cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 220, 0), -1)
                cv2.addWeighted(overlay, 0.08, frame, 0.92, 0, frame)

        # YOLO bbox (cyan intenso + grosor 2 para mejor contraste)
        if self._show_yolo and detection:
            x1, y1, x2, y2 = detection.bbox
            cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 180, 0), 2)
            cv2.putText(frame, f"YOLO {detection.confidence:.2f}",
                        (x1, y1 - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 180, 0), 2)

        # KCF bbox (amarillo, solo en modo async cuando hay bbox)
        if self._show_kcf and self._kcf_bbox and self._hybrid_mode:
            kx1, ky1, kw, kh = self._kcf_bbox
            kx2, ky2 = kx1 + kw, ky1 + kh
            cv2.rectangle(frame, (kx1, ky1), (kx2, ky2), (0, 255, 255), 2)
            cv2.putText(frame, "KCF", (kx1, ky2 + 16),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)

        # Centres
        if self._show_kalman and self._kf.is_initialised:
            cv2.circle(frame, (kx, ky), 5, (0, 220, 0), -1)
        if self._show_yolo and detection:
            mx, my = detection.center
            cv2.circle(frame, (mx, my), 3, (0, 0, 255), -1)

        # Trail (length ajustable con slider "Estela")
        if self._show_kalman and self._kf.is_initialised:
            self._trail.append((kx, ky))
            max_len = max(1, int(self._trail_len))
            while len(self._trail) > max_len:
                self._trail.pop(0)
            for i in range(1, len(self._trail)):
                alpha = i / len(self._trail)
                cv2.line(frame, self._trail[i - 1], self._trail[i],
                         (0, int(180 * alpha), 0), 2)

        # FPS + debug info on video (siempre visible)
        fps_line = f"FPS: {self._fps:.1f}"
        if self._hybrid_mode and self._track_source == "KCF":
            fps_line += " [KCF]" if self._kcf_success else " [KCF?]"
        cv2.putText(frame, fps_line, (10, 28),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 2)
        # Debug: tiempo del frame + fuente
        dbg = f"{self._frame_time_ms:.0f}ms src={self._track_source}"
        if self._hybrid_mode:
            dbg += f" KCFinit={int(self._kcf_init)}"
        cv2.putText(frame, dbg, (10, 52),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (180, 180, 180), 1)

    # ── FPS ───────────────────────────────────────────────

    def _update_fps(self) -> None:
        self._frame_count += 1
        now = time.perf_counter()
        if now - self._last_fps_time >= self._fps_interval:
            self._fps = self._frame_count / (now - self._last_fps_time)
            self._frame_count = 0
            self._last_fps_time = now
