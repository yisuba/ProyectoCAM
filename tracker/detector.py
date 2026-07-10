"""YOLO object detector using Ultralytics.

Wraps a pre-trained YOLO model (yolo11n.pt by default — fastest variant)
and returns the *best* detection for a given target class.

COCO class examples:
    0  → person
    67 → cell phone
    1  → bicycle
    2  → car
"""

from dataclasses import dataclass, field
from typing import Optional

import numpy as np


# ═══════════════════════════════════════════════════════════
# COCO class lookup
# ═══════════════════════════════════════════════════════════

COCO_CLASSES: dict[int, str] = {
    0: "person", 1: "bicycle", 2: "car", 3: "motorcycle",
    4: "airplane", 5: "bus", 6: "train", 7: "truck",
    8: "boat", 9: "traffic light", 10: "fire hydrant",
    11: "stop sign", 12: "parking meter", 13: "bench",
    14: "bird", 15: "cat", 16: "dog", 17: "horse",
    18: "sheep", 19: "cow", 20: "elephant", 21: "bear",
    22: "zebra", 23: "giraffe", 24: "backpack", 25: "umbrella",
    26: "handbag", 27: "tie", 28: "suitcase", 29: "frisbee",
    30: "skis", 31: "snowboard", 32: "sports ball",
    33: "kite", 34: "baseball bat", 35: "baseball glove",
    36: "skateboard", 37: "surfboard", 38: "tennis racket",
    39: "bottle", 40: "wine glass", 41: "cup", 42: "fork",
    43: "knife", 44: "spoon", 45: "bowl", 46: "banana",
    47: "apple", 48: "sandwich", 49: "orange", 50: "broccoli",
    51: "carrot", 52: "hot dog", 53: "pizza", 54: "donut",
    55: "cake", 56: "chair", 57: "couch", 58: "potted plant",
    59: "bed", 60: "dining table", 61: "toilet", 62: "tv",
    63: "laptop", 64: "mouse", 65: "remote", 66: "keyboard",
    67: "cell phone", 68: "microwave", 69: "oven", 70: "toaster",
    71: "sink", 72: "refrigerator", 73: "book", 74: "clock",
    75: "vase", 76: "scissors", 77: "teddy bear",
    78: "hair drier", 79: "toothbrush",
}


# ═══════════════════════════════════════════════════════════
# Public types
# ═══════════════════════════════════════════════════════════

@dataclass
class Detection:
    """A single object detection from YOLO."""

    bbox: tuple[int, int, int, int]      # (x1, y1, x2, y2)
    center: tuple[int, int]              # (cx, cy)
    confidence: float
    class_id: int
    class_name: str = ""

    def __post_init__(self):
        self.class_name = COCO_CLASSES.get(self.class_id, f"class_{self.class_id}")


# ═══════════════════════════════════════════════════════════
# Detector
# ═══════════════════════════════════════════════════════════


class Detector:
    """Object detector wrapping an Ultralytics YOLO model.

    Parameters
    ----------
    model_name : str
        Path or name of the YOLO model (e.g. ``"yolo11n.pt"``).
        The first run downloads the weights automatically.
    target_class : int
        COCO class ID to track (default 0 = person).
    """

    def __init__(
        self,
        model_name: str = "yolo11n.pt",
        target_class: int = 0,
    ):
        self._target_class = target_class

        # Lazy import so the app can start even without ultralytics
        try:
            from ultralytics import YOLO as _YOLO
        except ImportError:
            raise ImportError(
                "Ultralytics no está instalado. Ejecutá:\n"
                "  pip install ultralytics\n"
                "o corré setup.bat de nuevo."
            ) from None

        # verbose=False silences the per-epoch download spam
        self._model = _YOLO(model_name, verbose=False)

    @property
    def target_class(self) -> int:
        return self._target_class

    @target_class.setter
    def target_class(self, value: int) -> None:
        self._target_class = value

    @property
    def target_name(self) -> str:
        return COCO_CLASSES.get(self._target_class, f"class_{self._target_class}")

    # ── core ─────────────────────────────────────────────

    def detect(
        self,
        frame: np.ndarray,
        conf_threshold: float = 0.5,
    ) -> list[Detection]:
        """Run inference and return *all* detections matching the target class.

        Parameters
        ----------
        frame :
            BGR image from OpenCV.
        conf_threshold :
            Minimum confidence (0–1) to accept a detection.

        Returns
        -------
        List of :class:`Detection` objects, sorted by confidence descending.
        Empty list if nothing found.
        """
        results = self._model(frame, verbose=False, device="cpu")[0]

        detections: list[Detection] = []

        for box in results.boxes:
            cls_id = int(box.cls[0])
            if cls_id != self._target_class:
                continue

            conf = float(box.conf[0])
            if conf < conf_threshold:
                continue

            x1, y1, x2, y2 = map(int, box.xyxy[0])
            cx = int((x1 + x2) / 2)
            cy = int((y1 + y2) / 2)

            detections.append(Detection(
                bbox=(x1, y1, x2, y2),
                center=(cx, cy),
                confidence=conf,
                class_id=cls_id,
            ))

        detections.sort(key=lambda d: d.confidence, reverse=True)
        return detections

    def detect_best(
        self,
        frame: np.ndarray,
        conf_threshold: float = 0.5,
    ) -> Optional[Detection]:
        """Return the **single best** detection or ``None``."""
        dets = self.detect(frame, conf_threshold)
        return dets[0] if dets else None
