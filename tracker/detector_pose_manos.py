"""PoseHandTracker — MediaPipe Pose + Hands tracking with dynamic Kalman filtering.

Modos de operación (4):
  CUERPO_SIMPLE    → 12 landmarks (6 pares bilaterales) + 12 Filtros Kalman
  CUERPO_COMPLETO  → 17 landmarks (COCO estándar sobre MediaPipe) + 17 Kalman
  MANO_SIMPLE      →  6 landmarks (muñeca + 5 puntas de dedos) + 6 Kalman
  MANO_COMPLETA    → 21 landmarks (mano completa) + 21 Kalman

Arquitectura:
  - State machine: set_mode() destruye el arreglo anterior de Kalman y reconfigura
  - Cada landmark tiene su propio KalmanFilter independiente
  - Oclusión: si un landmark no se detecta, su Kalman predice por velocidad previa
  - Parámetros conf_threshold / q_scale / r_scale expuestos para trackbars

Modelos:
  Los modelos .task se descargan automáticamente desde Google Storage
  a models/mediapipe/ en la primera ejecución (~5 MB cada uno).

Referencia de índices MediaPipe
------------------------------
Pose (33 landmarks total):
  0:nose  1:left_eye_inner  2:left_eye  3:left_eye_outer
  4:right_eye_inner  5:right_eye  6:right_eye_outer
  7:left_ear  8:right_ear  9:mouth_left  10:mouth_right
  11:l_shoulder  12:r_shoulder  13:l_elbow  14:r_elbow
  15:l_wrist  16:r_wrist  17:l_pinky  18:r_pinky
  19:l_index  20:r_index  21:l_thumb  22:r_thumb
  23:l_hip  24:r_hip  25:l_knee  26:r_knee
  27:l_ankle  28:r_ankle  29:l_heel  30:r_heel
  31:l_foot_index  32:r_foot_index

Hands (21 landmarks por mano):
  0:WRIST  1:THUMB_CMC  2:THUMB_MCP  3:THUMB_IP  4:THUMB_TIP
  5:INDEX_MCP  6:INDEX_PIP  7:INDEX_DIP  8:INDEX_TIP
  9:MIDDLE_MCP  10:MIDDLE_PIP  11:MIDDLE_DIP  12:MIDDLE_TIP
  13:RING_MCP  14:RING_PIP  15:RING_DIP  16:RING_TIP
  17:PINKY_MCP  18:PINKY_PIP  19:PINKY_DIP  20:PINKY_TIP
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional
from urllib.request import urlretrieve

import cv2
import numpy as np

from tracker.kalman import KalmanFilter

# ═══════════════════════════════════════════════════════════
#  MediaPipe lazy import + model management
# ═══════════════════════════════════════════════════════════

try:
    import mediapipe as mp
    from mediapipe import tasks

    _MP_AVAILABLE = True
except ImportError:
    mp = None  # type: ignore[assignment]
    tasks = None  # type: ignore[assignment]
    _MP_AVAILABLE = False

logger = logging.getLogger(__name__)

# ── model auto-download ───────────────────────────────

_MODELS_DIR = Path(__file__).resolve().parent.parent / "models" / "mediapipe"

_POSE_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task"
)
_HAND_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
)

_POSE_MODEL_PATH = _MODELS_DIR / "pose_landmarker_lite.task"
_HAND_MODEL_PATH = _MODELS_DIR / "hand_landmarker_lite.task"


def _download_model(url: str, dest: Path, label: str) -> None:
    """Download a MediaPipe task model if not already present."""
    if dest.exists():
        logger.debug("Model %s ya existe: %s", label, dest)
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Descargando modelo %s desde %s ...", label, url)
    try:
        urlretrieve(url, str(dest))
        logger.info("Modelo %s descargado a %s (%d KB)", label, dest, dest.stat().st_size // 1024)
    except Exception as exc:
        raise RuntimeError(
            f"No se pudo descargar el modelo {label}.\n"
            f"Verificá tu conexión a internet.\n"
            f"URL: {url}\nError: {exc}"
        ) from exc


def _ensure_pose_model() -> Path:
    _download_model(_POSE_MODEL_URL, _POSE_MODEL_PATH, "pose_landmarker")
    return _POSE_MODEL_PATH


def _ensure_hand_model() -> Path:
    _download_model(_HAND_MODEL_URL, _HAND_MODEL_PATH, "hand_landmarker")
    return _HAND_MODEL_PATH


# ═══════════════════════════════════════════════════════════
#  CONSTANTES — índices de landmarks y conexiones por modo
# ═══════════════════════════════════════════════════════════

# ── CUERPO_SIMPLE ────────────────────────────────────────
# 12 landmarks: 6 pares bilaterales de articulaciones principales
# [hombros, codos, muñecas, caderas, rodillas, tobillos]
CUERPO_SIMPLE_INDICES: list[int] = [
    11, 12,  # hombros   (left/right_shoulder)
    13, 14,  # codos     (left/right_elbow)
    15, 16,  # muñecas   (left/right_wrist)
    23, 24,  # caderas   (left/right_hip)
    25, 26,  # rodillas  (left/right_knee)
    27, 28,  # tobillos  (left/right_ankle)
]

CUERPO_SIMPLE_CONNECTIONS: list[tuple[int, int]] = [
    (11, 13), (13, 15),  # izquierdo: hombro → codo → muñeca
    (12, 14), (14, 16),  # derecho:   hombro → codo → muñeca
    (11, 12),            # línea de hombros
    (23, 24),            # línea de caderas
    (11, 23), (12, 24),  # hombro → cadera (torso lateral)
    (23, 25), (25, 27),  # izquierda: cadera → rodilla → tobillo
    (24, 26), (26, 28),  # derecha:   cadera → rodilla → tobillo
]

# ── CUERPO_COMPLETO ──────────────────────────────────────
# 17 landmarks: mapeo COCO 17 → MediaPipe Pose
CUERPO_COMPLETO_INDICES: list[int] = [
    0,   # nose               → MP 0
    2,   # left_eye           → MP 2
    5,   # right_eye          → MP 5
    7,   # left_ear           → MP 7
    8,   # right_ear          → MP 8
    11,  # left_shoulder      → MP 11
    12,  # right_shoulder     → MP 12
    13,  # left_elbow         → MP 13
    14,  # right_elbow        → MP 14
    15,  # left_wrist         → MP 15
    16,  # right_wrist        → MP 16
    23,  # left_hip           → MP 23
    24,  # right_hip          → MP 24
    25,  # left_knee          → MP 25
    26,  # right_knee         → MP 26
    27,  # left_ankle         → MP 27
    28,  # right_ankle        → MP 28
]

CUERPO_COMPLETO_CONNECTIONS: list[tuple[int, int]] = [
    (0, 2), (0, 5),          # nariz → ojos
    (2, 7), (5, 8),          # ojos → oídos
    (11, 13), (13, 15),      # brazo izquierdo
    (12, 14), (14, 16),      # brazo derecho
    (11, 12), (23, 24),      # hombros y caderas
    (11, 23), (12, 24),      # torso lateral
    (23, 25), (25, 27),      # pierna izquierda
    (24, 26), (26, 28),      # pierna derecha
]

# ── MANO_SIMPLE ──────────────────────────────────────────
# 6 landmarks: muñeca (0) + puntas de los 5 dedos
MANO_SIMPLE_INDICES: list[int] = [
    0,   # WRIST
    4,   # THUMB_TIP
    8,   # INDEX_FINGER_TIP
    12,  # MIDDLE_FINGER_TIP
    16,  # RING_FINGER_TIP
    20,  # PINKY_TIP
]

# Índices POSICIONALES dentro de MANO_SIMPLE_INDICES, NO de MediaPipe
MANO_SIMPLE_CONNECTIONS: list[tuple[int, int]] = [
    (0, 1),  # muñeca → pulgar
    (0, 2),  # muñeca → índice
    (0, 3),  # muñeca → medio
    (0, 4),  # muñeca → anular
    (0, 5),  # muñeca → meñique
]

# ── MANO_COMPLETA ────────────────────────────────────────
MANO_COMPLETA_INDICES: list[int] = list(range(21))

MANO_COMPLETA_CONNECTIONS: list[tuple[int, int]] = [
    (0, 1), (1, 2), (2, 3), (3, 4),        # pulgar
    (0, 5), (5, 6), (6, 7), (7, 8),        # índice
    (0, 9), (9, 10), (10, 11), (11, 12),   # medio
    (0, 13), (13, 14), (14, 15), (15, 16), # anular
    (0, 17), (17, 18), (18, 19), (19, 20), # meñique
    (5, 9), (9, 13), (13, 17),             # puentes interdigitales
]


# ═══════════════════════════════════════════════════════════
#  Mode registry
# ═══════════════════════════════════════════════════════════

def _build_mode_registry() -> dict[str, dict]:
    return {
        "CUERPO_SIMPLE": {
            "indices": CUERPO_SIMPLE_INDICES,
            "connections": CUERPO_SIMPLE_CONNECTIONS,
            "is_hand": False,
            "label": "Cuerpo Simple (12 pts)",
            "short": "[1] Cpo.Simple",
        },
        "CUERPO_COMPLETO": {
            "indices": CUERPO_COMPLETO_INDICES,
            "connections": CUERPO_COMPLETO_CONNECTIONS,
            "is_hand": False,
            "label": "Cuerpo Completo (17 pts)",
            "short": "[2] Cpo.Comp.",
        },
        "MANO_SIMPLE": {
            "indices": MANO_SIMPLE_INDICES,
            "connections": MANO_SIMPLE_CONNECTIONS,
            "is_hand": True,
            "label": "Mano Simple (6 pts)",
            "short": "[3] Mano Simp.",
        },
        "MANO_COMPLETA": {
            "indices": MANO_COMPLETA_INDICES,
            "connections": MANO_COMPLETA_CONNECTIONS,
            "is_hand": True,
            "label": "Mano Completa (21 pts)",
            "short": "[4] Mano Comp.",
        },
    }


# ═══════════════════════════════════════════════════════════
#  PoseHandTracker
# ═══════════════════════════════════════════════════════════

class PoseHandTracker:
    """State-machine tracker: 4 modos MediaPipe Tasks API + Kalman dinámico.

    Al cambiar de modo, el arreglo anterior de Kalman se destruye y se
    crea uno nuevo con el tamaño exacto del nuevo modo.

    Parámetros ajustables en tiempo real (para conectar trackbars):
      - ``conf_threshold`` → min_detection_confidence de MediaPipe
      - ``q_scale``        → multiplicador de ruido de proceso (Kalman Q)
      - ``r_scale``        → multiplicador de ruido de medición (Kalman R)
    """

    MODE_CUERPO_SIMPLE = "CUERPO_SIMPLE"
    MODE_CUERPO_COMPLETO = "CUERPO_COMPLETO"
    MODE_MANO_SIMPLE = "MANO_SIMPLE"
    MODE_MANO_COMPLETA = "MANO_COMPLETA"

    MODES: list[str] = [
        MODE_CUERPO_SIMPLE,
        MODE_CUERPO_COMPLETO,
        MODE_MANO_SIMPLE,
        MODE_MANO_COMPLETA,
    ]

    def __init__(self, mode: str = MODE_CUERPO_SIMPLE):
        if not _MP_AVAILABLE:
            raise ImportError(
                "MediaPipe no está instalado.\n"
                "Ejecutá:  pip install mediapipe\n"
                "o corré setup.bat de nuevo."
            )

        vision = tasks.vision

        # ── descargar modelos si es necesario ──
        self._pose_model_path = _ensure_pose_model()
        self._hand_model_path = _ensure_hand_model()

        # Instancias de landmarkers (se crean bajo demanda por modo)
        self._pose_landmarker: Optional[vision.PoseLandmarker] = None
        self._hand_landmarker: Optional[vision.HandLandmarker] = None

        # Registry
        self._registry = _build_mode_registry()

        # ── estado interno ──
        self._mode: str = ""
        self._landmark_indices: list[int] = []
        self._connections: list[tuple[int, int]] = []
        self._is_hand: bool = False
        self._num_landmarks: int = 0

        # Arreglo dinámico de Kalman
        self._kfs: list[KalmanFilter] = []

        # Flags de detección del último frame
        self._detected_flags: list[bool] = []

        # Posiciones suavizadas del último process()
        self._smoothed: list[tuple[int, int]] = []

        # ── parámetros ajustables por trackbar ──
        self.conf_threshold: float = 0.5
        self.q_scale: float = 1.0
        self.r_scale: float = 2.0

        # ── FPS ──
        self.fps: float = 0.0
        self._frame_count: int = 0
        self._fps_start: float = time.perf_counter()
        self._fps_interval: float = 0.5

        self.set_mode(mode)

    # ──────────────────────────────────────────────────────
    #  Propiedades
    # ──────────────────────────────────────────────────────

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def mode_label(self) -> str:
        return self._registry.get(self._mode, {}).get("label", self._mode)

    @property
    def num_landmarks(self) -> int:
        return self._num_landmarks

    @property
    def num_detected(self) -> int:
        return sum(self._detected_flags)

    @property
    def num_predicting(self) -> int:
        return self._num_landmarks - self.num_detected

    @property
    def connections(self) -> list[tuple[int, int]]:
        return list(self._connections)

    @property
    def is_hand_mode(self) -> bool:
        return self._is_hand

    # ──────────────────────────────────────────────────────
    #  State machine — cambio de modo
    # ──────────────────────────────────────────────────────

    def set_mode(self, mode: str) -> None:
        """Cambiar a *mode* — destruye Kalman anteriores y recrea."""
        if mode not in self._registry:
            raise ValueError(
                f"Modo inválido '{mode}'. Válidos: {', '.join(self.MODES)}"
            )

        if mode == self._mode:
            return

        old_mode = self._mode
        info = self._registry[mode]
        self._mode = mode
        self._landmark_indices = list(info["indices"])
        self._connections = list(info["connections"])
        self._is_hand = info["is_hand"]
        self._num_landmarks = len(self._landmark_indices)

        # ── destruir Kalman anteriores ──
        self._kfs.clear()

        # ── crear nuevos Kalman ──
        for _ in range(self._num_landmarks):
            kf = KalmanFilter()
            kf.set_Q(self.q_scale)
            kf.set_R(self.r_scale)
            self._kfs.append(kf)

        # ── resetear estado ──
        self._detected_flags = [False] * self._num_landmarks
        self._smoothed = [(0, 0)] * self._num_landmarks

        # ── recrear landmarker ──
        self._recreate_landmarker()

        logger.info(
            "Modo: %s → %s  |  Kalman: %d filtros",
            old_mode or "(init)", mode, self._num_landmarks,
        )

    def _recreate_landmarker(self) -> None:
        """Crear/recrear el MediaPipe Landmarker para el modo actual."""
        vision = tasks.vision

        # Liberar instancia anterior
        self._close_landmarker()

        conf = max(0.01, min(1.0, self.conf_threshold))

        if self._is_hand:
            options = vision.HandLandmarkerOptions(
                base_options=tasks.BaseOptions(
                    model_asset_path=str(self._hand_model_path),
                ),
                running_mode=vision.RunningMode.IMAGE,
                num_hands=2,
                min_hand_detection_confidence=conf,
                min_hand_presence_confidence=conf,
                min_tracking_confidence=conf * 0.8,
            )
            self._hand_landmarker = vision.HandLandmarker.create_from_options(options)
        else:
            options = vision.PoseLandmarkerOptions(
                base_options=tasks.BaseOptions(
                    model_asset_path=str(self._pose_model_path),
                ),
                running_mode=vision.RunningMode.IMAGE,
                num_poses=1,
                min_pose_detection_confidence=conf,
                min_pose_presence_confidence=conf,
                min_tracking_confidence=conf * 0.8,
                output_segmentation_masks=False,
            )
            self._pose_landmarker = vision.PoseLandmarker.create_from_options(options)

    # ──────────────────────────────────────────────────────
    #  Procesamiento por frame
    # ──────────────────────────────────────────────────────

    def process(self, frame: np.ndarray) -> list[tuple[int, int]]:
        """Ejecutar MediaPipe → Kalman por landmark.

        Returns
        -------
        list[tuple[int, int]]
            Posiciones suavizadas (x, y). Tamaño = num_landmarks.
            Landmarks no inicializados retornan (0, 0).
        """
        h, w = frame.shape[:2]

        # Sincronizar Q/R en todos los filtros
        for kf in self._kfs:
            kf.set_Q(self.q_scale)
            kf.set_R(self.r_scale)

        # ── MediaPipe ──
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        raw = self._extract_landmarks(mp_image, w, h)

        # ── Kalman: update si hay detección, predict si no ──
        self._detected_flags = [False] * self._num_landmarks
        smoothed: list[tuple[int, int]] = [(0, 0)] * self._num_landmarks

        vision = tasks.vision

        for i, landmark_data in enumerate(raw):
            kf = self._kfs[i]

            if landmark_data is not None:
                rx, ry, visibility = landmark_data

                # Para pose: visibility >= 0.5 es detectable
                # Para manos: visibility es siempre 1.0 si el landmark existe
                if visibility is None or visibility >= 0.5:
                    sx, sy = kf.update(rx, ry, 1, 1)
                    self._detected_flags[i] = True
                else:
                    sx, sy = kf.predict()
            else:
                sx, sy = kf.predict()

            smoothed[i] = (int(sx), int(sy))

        self._smoothed = smoothed
        self._update_fps()

        return smoothed

    def _extract_landmarks(
        self, mp_image, frame_w: int, frame_h: int
    ) -> list[Optional[tuple[float, float, Optional[float]]]]:
        """Ejecutar MediaPipe y extraer (x, y, visibility) por landmark."""
        vision = tasks.vision

        if self._is_hand:
            if self._hand_landmarker is None:
                return [None] * self._num_landmarks
            result = self._hand_landmarker.detect(mp_image)
            if not result.hand_landmarks:
                return [None] * self._num_landmarks
            # Tomar la primera mano detectada
            landmarks = result.hand_landmarks[0]
            out: list[Optional[tuple[float, float, Optional[float]]]] = []
            for idx in self._landmark_indices:
                lm = landmarks[idx]
                out.append((lm.x * frame_w, lm.y * frame_h, 1.0))
            return out
        else:
            if self._pose_landmarker is None:
                return [None] * self._num_landmarks
            result = self._pose_landmarker.detect(mp_image)
            if not result.pose_landmarks:
                return [None] * self._num_landmarks
            landmarks = result.pose_landmarks[0]
            out = []
            for idx in self._landmark_indices:
                lm = landmarks[idx]
                out.append((lm.x * frame_w, lm.y * frame_h, lm.visibility))
            return out

    # ──────────────────────────────────────────────────────
    #  Dibujo
    # ──────────────────────────────────────────────────────

    def draw(self, frame: np.ndarray) -> None:
        """Dibujar esqueleto/mano + landmarks (verde=detectado, amarillo=predicción)."""
        pts = self._smoothed
        detected = self._detected_flags

        # Conexiones
        for a, b in self._connections:
            if a >= len(pts) or b >= len(pts):
                continue
            ax, ay = pts[a]
            bx, by = pts[b]
            if (ax, ay) == (0, 0) or (bx, by) == (0, 0):
                continue

            color = (0, 220, 0) if (detected[a] and detected[b]) else (0, 220, 220)
            cv2.line(frame, (ax, ay), (bx, by), color, 2, cv2.LINE_AA)

        # Puntos
        for i, (x, y) in enumerate(pts):
            if (x, y) == (0, 0):
                continue
            color = (0, 255, 0) if detected[i] else (0, 255, 255)
            cv2.circle(frame, (x, y), 5, color, -1, cv2.LINE_AA)
            cv2.circle(frame, (x, y), 5, (255, 255, 255), 1, cv2.LINE_AA)

    # ──────────────────────────────────────────────────────
    #  FPS
    # ──────────────────────────────────────────────────────

    def _update_fps(self) -> None:
        self._frame_count += 1
        elapsed = time.perf_counter() - self._fps_start
        if elapsed >= self._fps_interval:
            self.fps = self._frame_count / elapsed
            self._frame_count = 0
            self._fps_start = time.perf_counter()

    # ──────────────────────────────────────────────────────
    #  Recursos
    # ──────────────────────────────────────────────────────

    def _close_landmarker(self) -> None:
        if self._pose_landmarker is not None:
            self._pose_landmarker.close()
            self._pose_landmarker = None
        if self._hand_landmarker is not None:
            self._hand_landmarker.close()
            self._hand_landmarker = None

    def close(self) -> None:
        """Liberar recursos de MediaPipe y Kalman."""
        self._close_landmarker()
        self._kfs.clear()
        logger.info("PoseHandTracker: recursos liberados")
