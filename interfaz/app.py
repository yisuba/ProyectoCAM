"""Main tkinter application window."""

import logging
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from typing import List, Optional

from camara.device import CameraInfo, list_cameras
from camara.stream import CameraStream
from camara.version import __version__
from interfaz import config_manager as cfg
from interfaz.viewer import VideoPreview
from tracker.detector import COCO_CLASSES

logger = logging.getLogger(__name__)

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

        self.title(f"Visor de Cámara — ProyectoPDI v{__version__}")
        self.minsize(self.MIN_WIDTH, self.MIN_HEIGHT)

        # ── state ───────────────────────────────────────
        self._cameras: List[CameraInfo] = []
        self._stream: Optional[CameraStream] = None
        self._poll_id: Optional[str] = None
        self._config: dict = cfg.load()

        self._restore_geometry()

        self._build_ui()
        self._refresh_cameras()
        self._restore_last_source()

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
        self._btn_network.pack(side=tk.LEFT, padx=(0, 8))

        self._btn_video = ttk.Button(
            toolbar,
            text="📁 Video",
            command=self._load_video_file,
        )
        self._btn_video.pack(side=tk.LEFT, padx=(0, 16))

        self._btn_toggle = ttk.Button(
            toolbar,
            text="▶ Iniciar",
            command=self._toggle_stream,
            width=12,
        )
        self._btn_toggle.pack(side=tk.LEFT, padx=(0, 16))

        self._btn_analyze = ttk.Button(
            toolbar,
            text="🔬 Analizar",
            command=self._start_analysis,
            width=14,
            state="disabled",
        )
        self._btn_analyze.pack(side=tk.LEFT, padx=(0, 12))

        # ── target class selector ──
        ttk.Label(toolbar, text="Objeto:").pack(side=tk.LEFT, padx=(0, 4))
        self._class_combo = ttk.Combobox(
            toolbar,
            state="readonly",
            width=16,
        )
        # Build sorted list of (class_id, name) for common classes
        self._class_list: list[tuple[int, str]] = sorted(
            COCO_CLASSES.items(), key=lambda x: x[1]
        )
        self._class_combo["values"] = [name for _, name in self._class_list]
        # Select default from config or fallback to "person" (class 0)
        default_class = self._config.get("detection", {}).get("target_class", 0)
        for i, (cid, _) in enumerate(self._class_list):
            if cid == default_class:
                self._class_combo.current(i)
                break
        else:
            # Default to "person" (first item that matches class 0)
            for i, (cid, _) in enumerate(self._class_list):
                if cid == 0:
                    self._class_combo.current(i)
                    break
        self._class_combo.pack(side=tk.LEFT)

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
        self._config = cfg.add_network_url(self._config, url)
        cfg.save(self._config)
        self._set_status(f"Agregada fuente de red: {url}")

    def _load_video_file(self) -> None:
        """Open a file dialog to load a local video file for testing."""
        path = filedialog.askopenfilename(
            title="Seleccionar archivo de video",
            filetypes=[
                ("Video files", "*.mp4 *.avi *.mov *.mkv *.webm"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return

        # Check if this file is already in the list
        for cam in self._cameras:
            if cam.url == path:
                idx = self._cameras.index(cam)
                self._cam_combo.current(idx)
                self._set_status(f"Seleccionado: {Path(path).name}")
                return

        cam = CameraInfo(
            index=-1,
            url=path,
            name=Path(path).name,
        )
        self._cameras.append(cam)
        self._cam_combo["values"] = [c.label for c in self._cameras]
        self._cam_combo.current(len(self._cameras) - 1)
        self._set_status(f"Cargado video: {Path(path).name}")

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
        self._btn_analyze.configure(state="normal")
        self._cam_combo.configure(state="disabled")
        self._btn_refresh.configure(state="disabled")
        self._btn_network.configure(state="disabled")
        self._btn_video.configure(state="disabled")
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
        self._btn_analyze.configure(state="disabled")
        self._cam_combo.configure(state="readonly")
        self._btn_refresh.configure(state="normal")
        self._btn_network.configure(state="normal")
        self._btn_video.configure(state="normal")
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
            label = "Red" if stream.is_network else "Video" if isinstance(stream.source, str) else "Cámara"
            self._set_status(
                f"✅ {label} activa — {w}x{h} @ ~30 fps — {total} frames"
            )
        else:
            self._set_status("⏳ Esperando primer frame...")

        self._poll_id = self.after(30, self._poll_frame)

    # ── helpers ─────────────────────────────────────────

    def _set_status(self, text: str) -> None:
        self._status_var.set(text)

    # ── config persistence ──────────────────────────────

    def _restore_last_source(self) -> None:
        """Select the last-used camera in the combobox, if found."""
        last = self._config.get("last_source")
        if last is None:
            return
        for i, cam in enumerate(self._cameras):
            if cam.source == last:
                self._cam_combo.current(i)
                self._set_status(f"Restaurada: {cam.label}")
                return

    def _save_last_source(self) -> None:
        cam = self._selected_camera()
        if cam is not None:
            self._config = cfg.update_last_source(self._config, cam.source)
            cfg.save(self._config)

    # ── analysis mode (YOLO + Kalman) ───────────────────

    def _start_analysis(self) -> None:
        """Open OpenCV analysis window with object tracking.

        The tkinter window is hidden while analysis runs and restored
        when the user presses ESC.
        """
        if self._stream is None:
            messagebox.showwarning(
                "Sin stream",
                "Iniciá la cámara primero con ▶ Iniciar.",
            )
            return

        # Stop tkinter poll loop — analysis has its own loop
        if self._poll_id:
            self.after_cancel(self._poll_id)
            self._poll_id = None

        # Hide tkinter window
        self.withdraw()
        self.update()  # force redraw so it actually hides

        try:
            from interfaz.analysis_win import AnalysisWindow

            # Get selected target class from combobox
            idx = self._class_combo.current()
            target = self._class_list[idx][0] if 0 <= idx < len(self._class_list) else 0
            win = AnalysisWindow(stream=self._stream, target_class=target)
            win.run()
            logger.info("Analysis finished normally (class %d)", target)
            # Save selected class to config
            self._config.setdefault("detection", {})["target_class"] = target
            cfg.save(self._config)
        except ImportError:
            messagebox.showerror(
                "Falta dependencia",
                "Ultralytics no está instalado.\n\n"
                "Ejecutá en la terminal:\n"
                "  pip install ultralytics\n"
                "o corré setup.bat de nuevo.",
            )
        except Exception:
            logger.exception("Error durante el análisis")
            messagebox.showerror("Error", "Ocurrió un error durante el análisis.\n"
                                          "Revisá logs/tracker.log para más detalle.")
        finally:
            # Stop stream and restore full UI state
            self._stop_stream()
            self._save_last_source()
            self.deiconify()

    # ── window close ────────────────────────────────────

    # ── window geometry ───────────────────────────────────

    def _restore_geometry(self) -> None:
        """Restore window geometry from config."""
        geom = self._config.get("window", {}).get("geometry")
        if geom:
            logger.debug("Restoring window geometry: %s", geom)
            self.geometry(geom)

    def _save_geometry(self) -> None:
        """Persist current window geometry to config."""
        geom = self.geometry()  # returns "WxH+X+Y"
        self._config.setdefault("window", {})["geometry"] = geom
        logger.debug("Saved window geometry: %s", geom)

    def _on_close(self) -> None:
        self._save_geometry()
        self._save_last_source()
        self._stop_stream()
        self.destroy()
