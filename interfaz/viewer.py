"""Video preview widget that renders OpenCV frames on a tkinter Canvas."""

import tkinter as tk
from typing import Optional

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageTk


class VideoPreview(tk.Frame):
    """A frame that displays camera frames, auto-scaling to fit the window.

    The image is resized at the PIL level (not via ``canvas.scale()``) so
    there is no cumulative distortion when the window is resized.
    """

    def __init__(
        self,
        parent: tk.Widget,
        bg: str = "#1e1e1e",
        **kwargs,
    ):
        super().__init__(parent, **kwargs)
        self._image_id: Optional[str] = None
        self._photo: Optional[ImageTk.PhotoImage] = None
        self._last_pil: Optional[Image.Image] = None

        self.configure(bg=bg, highlightthickness=0)
        self._canvas = tk.Canvas(self, bg=bg, highlightthickness=0)
        self._canvas.pack(fill=tk.BOTH, expand=True)
        self._canvas.bind("<Configure>", self._on_resize)

        self._draw_placeholder("Cámara detenida")

    # ── public API ──────────────────────────────────────

    def show_frame(self, frame: NDArray) -> None:
        """Convert an OpenCV BGR frame to RGB and display it, resized to fit."""
        rgb = cv2_to_rgb(frame)
        self._last_pil = rgb
        self._display_pil(rgb)

    def clear(self) -> None:
        """Remove the displayed frame and show placeholder."""
        if self._image_id:
            self._canvas.delete(self._image_id)
            self._image_id = None
        self._photo = None
        self._last_pil = None
        self._draw_placeholder("Cámara detenida")

    # ── internals ───────────────────────────────────────

    def _display_pil(self, pil: Image.Image) -> None:
        """Resize *pil* to fit the canvas and render it centred."""
        cw = self._canvas.winfo_width()
        ch = self._canvas.winfo_height()

        if cw > 10 and ch > 10:
            iw, ih = pil.size
            scale = min(cw / iw, ch / ih)
            if abs(scale - 1.0) > 0.01:  # avoid pointless no-op resizes
                new_w = max(int(iw * scale), 1)
                new_h = max(int(ih * scale), 1)
                pil = pil.resize((new_w, new_h), Image.Resampling.BILINEAR)

        self._photo = ImageTk.PhotoImage(pil)

        # Centre inside canvas
        cw = self._canvas.winfo_width()
        ch = self._canvas.winfo_height()
        x_off = max((cw - pil.width) // 2, 0)
        y_off = max((ch - pil.height) // 2, 0)

        if self._image_id is None:
            self._image_id = self._canvas.create_image(
                x_off, y_off, anchor=tk.NW, image=self._photo,
            )
        else:
            self._canvas.coords(self._image_id, x_off, y_off)
            self._canvas.itemconfig(self._image_id, image=self._photo)

    def _draw_placeholder(self, text: str) -> None:
        self._canvas.delete("placeholder")
        self._canvas.create_text(
            max(self._canvas.winfo_width() // 2, 100),
            max(self._canvas.winfo_height() // 2, 100),
            text=text,
            fill="#888888",
            font=("Segoe UI", 14),
            tags="placeholder",
        )

    def _on_resize(self, _event: Optional[tk.Event] = None) -> None:
        if self._last_pil is not None:
            self._display_pil(self._last_pil)
        else:
            self._draw_placeholder("Cámara detenida")


# ── helpers ─────────────────────────────────────────────

def cv2_to_rgb(frame: NDArray) -> Image.Image:
    """Convert an OpenCV BGR ``numpy.ndarray`` to a Pillow ``RGB`` image.

    Uses numpy channel-reversal (``frame[:, :, ::-1]``) instead of
    ``cv2.cvtColor`` so this module does not need to import OpenCV.
    """
    return Image.fromarray(frame[:, :, ::-1], mode="RGB")
