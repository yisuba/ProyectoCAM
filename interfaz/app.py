"""Main tkinter application window."""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from typing import List, Optional

from camara.device import CameraInfo, list_cameras
from camara.stream import CameraStream
from interfaz.viewer import VideoPreview

# ── dialog for entering a network stream URL ─────────────


class _UrlDialog(tk.Toplevel):
    """Simple modal dialog to enter a camera stream URL."""

    def __init__(self, parent: tk.Widget):
        super().__init__(parent)
        self.title("Fuente de red")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._result: Optional[str] = None

        f = ttk.Frame(self, padding="12 12 12 12")
        f.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            f,
            text="URL del stream de video:",
            font=("Segoe UI", 10),
        ).pack(anchor=tk.W)

        ttk.Label(
            f,
            text="Ej: http://192.168.1.100:81/stream\n"
                 "    rtsp://cámara.local:554/stream\n"
                 "    rtmp://…",
            foreground="#666666",
            font=("Segoe UI", 9),
        ).pack(anchor=tk.W, pady=(4, 8))

        self._entry = ttk.Entry(f, width=50, font=("Segoe UI", 10))
        self._entry.pack(fill=tk.X)
        self._entry.focus_set()

        btn_frame = ttk.Frame(f)
        btn_frame.pack(fill=tk.X, pady=(12, 0))

        ttk.Button(
            btn_frame, text="Cancelar",
            command=self.destroy,
        ).pack(side=tk.RIGHT, padx=(8, 0))

        ttk.Button(
            btn_frame, text="Conectar",
            command=self._on_ok,
        ).pack(side=tk.RIGHT)

        self.bind("<Return>", lambda _: self._on_ok())
        self.bind("<Escape>", lambda _: self.destroy())

        # Center on parent
        self.update_idletasks()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        w, h = self.winfo_width(), self.winfo_height()
        self.geometry(f"+{px + (pw - w) // 2}+{py + (ph - h) // 2}")

        self.wait_window()

    def _on_ok(self) -> None:
        url = self._entry.get().strip()
        if not url:
            messagebox.showwarning("URL vacía", "Ingresá la URL del stream.", parent=self)
            return
        self._result = url
        self.destroy()

    @property
    def result(self) -> Optional[str]:
        return self._result


# ── main app ────────────────────────────────────────────


class CameraApp(tk.Tk):
    """Main application window.

    Features:
    - Detect available cameras
    - Select camera from dropdown
    - Start/Stop live preview
    - Connect to network / IP camera streams (ESP32-CAM, etc.)
    """

    MIN_WIDTH = 800
    MIN_HEIGHT = 600

    def __init__(self):
        super().__init__()

        self.title("Visor de Cámara — ProyectoPDI")
        self.geometry(f"{self.MIN_WIDTH}x{self.MIN_HEIGHT}")
        self.minsize(self.MIN_WIDTH, self.MIN_HEIGHT)

        # ── state ───────────────────────────────────────
        self._cameras: List[CameraInfo] = []
        self._stream: Optional[CameraStream] = None
        self._poll_id: Optional[str] = None

        self._build_ui()
        self._refresh_cameras()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── UI construction ─────────────────────────────────

    def _build_ui(self) -> None:
        """Create all widgets."""
        # ──────── toolbar ────────
        toolbar = ttk.Frame(self, padding="8 8 8 8")
        toolbar.pack(fill=tk.X)

        ttk.Label(toolbar, text="Cámara:").pack(side=tk.LEFT, padx=(0, 8))

        self._cam_combo = ttk.Combobox(
            toolbar,
            state="readonly",
            width=55,
        )
        self._cam_combo.pack(side=tk.LEFT, padx=(0, 8))

        self._btn_refresh = ttk.Button(
            toolbar,
            text="🔍 Detectar",
            command=self._refresh_cameras,
        )
        self._btn_refresh.pack(side=tk.LEFT, padx=(0, 8))

        self._btn_network = ttk.Button(
            toolbar,
            text="🌐 Red",
            command=self._add_network_source,
        )
        self._btn_network.pack(side=tk.LEFT, padx=(0, 16))

        self._btn_toggle = ttk.Button(
            toolbar,
            text="▶ Iniciar",
            command=self._toggle_stream,
            width=12,
        )
        self._btn_toggle.pack(side=tk.LEFT)

        # ──────── status bar ────────
        self._status_var = tk.StringVar(value="Listo — seleccioná una cámara")
        status_bar = ttk.Label(
            self,
            textvariable=self._status_var,
            relief=tk.SUNKEN,
            anchor=tk.W,
            padding="4 2 4 2",
        )
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)

        # ──────── video preview ────────
        self._viewer = VideoPreview(self)
        self._viewer.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

    # ── camera detection ────────────────────────────────

    def _add_network_source(self) -> None:
        """Open a dialog to enter a network stream URL."""
        dialog = _UrlDialog(self)
        url = dialog.result
        if not url:
            return

        # Check if this URL is already in the list
        for cam in self._cameras:
            if cam.url == url:
                idx = self._cameras.index(cam)
                self._cam_combo.current(idx)
                self._set_status(f"Seleccionada: {url}")
                return

        cam = CameraInfo.from_url(url)
        self._cameras.append(cam)
        self._cam_combo["values"] = [c.label for c in self._cameras]
        self._cam_combo.current(len(self._cameras) - 1)
        self._set_status(f"Agregada fuente de red: {url}")

    def _refresh_cameras(self) -> None:
        """Re-scan for available cameras and fill the dropdown."""
        if self._stream:
            self._stop_stream()

        self._cameras = list_cameras()
        self._cam_combo["values"] = [c.label for c in self._cameras]

        if self._cameras:
            self._cam_combo.current(0)
            self._set_status(f"Detectadas {len(self._cameras)} cámara(s)")
        else:
            self._cam_combo.set("")
            self._set_status(
                "No se detectaron cámaras — conectá una y presioná Detectar"
            )

    def _selected_camera(self) -> Optional[CameraInfo]:
        """Return the currently selected :class:`CameraInfo` or ``None``."""
        idx = self._cam_combo.current()
        if 0 <= idx < len(self._cameras):
            return self._cameras[idx]
        return None

    # ── stream control ──────────────────────────────────

    def _toggle_stream(self) -> None:
        if self._stream:
            self._stop_stream()
        else:
            self._start_stream()

    def _start_stream(self) -> None:
        cam = self._selected_camera()
        if cam is None:
            messagebox.showwarning(
                "Sin cámara",
                "No hay ninguna cámara seleccionada.\n"
                "Presioná 'Detectar' para buscar dispositivos.",
            )
            return

        try:
            stream = CameraStream(
                source=cam.source,
                backend=cam.backend_int,
            )
            stream.start()
        except RuntimeError as exc:
            messagebox.showerror("Error al iniciar", str(exc))
            return

        self._stream = stream
        self._btn_toggle.configure(text="⏹ Detener")
        self._cam_combo.configure(state="disabled")
        self._btn_refresh.configure(state="disabled")
        self._set_status("Conectando...")
        # Give the capture thread time for warm-up before first poll
        self.after(500, self._poll_frame)

    def _stop_stream(self) -> None:
        if self._poll_id:
            self.after_cancel(self._poll_id)
            self._poll_id = None

        if self._stream:
            self._stream.stop()
            self._stream = None

        self._viewer.clear()
        self._btn_toggle.configure(text="▶ Iniciar")
        self._cam_combo.configure(state="readonly")
        self._btn_refresh.configure(state="normal")
        self._set_status("Cámara detenida")

    def _poll_frame(self) -> None:
        """Called every ~30 ms to fetch the latest frame from the stream."""
        stream = self._stream
        if stream is None:
            return

        if not stream.running:
            error = stream.error
            self._stop_stream()
            if error:
                messagebox.showerror("Error de cámara", error)
            return

        frame = stream.read()
        if frame is not None:
            self._viewer.show_frame(frame)
            total = stream.frame_count
            h, w = frame.shape[:2]
            label = "Red" if stream.is_network else "Cámara"
            self._set_status(
                f"✅ {label} activa — {w}x{h} @ ~30 fps — {total} frames"
            )
        else:
            self._set_status("⏳ Esperando primer frame...")

        self._poll_id = self.after(30, self._poll_frame)

    # ── helpers ─────────────────────────────────────────

    def _set_status(self, text: str) -> None:
        self._status_var.set(text)

    def _on_close(self) -> None:
        self._stop_stream()
        self.destroy()
