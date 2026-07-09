# AGENTS.md — ProyectoPDI

Windows tkinter app that detects USB/integrated cameras **and** connects to
IP / network camera streams (ESP32-CAM, RTSP, MJPEG over HTTP). Shows a live
preview in a single window.

## Quick start

```bat
setup.bat          # creates venv, installs deps
run.bat            # activates venv, launches main.py
build.bat          # (optional) standalone .exe via PyInstaller
```

Manual:
```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Python 3.13.3, Windows only. No tests, no linter, no formatter, no CI.

## Architecture

```
main.py                    ← entrypoint (creates CameraApp, calls mainloop)
├── interfaz/app.py        ← CameraApp: toolbar, combobox, 🌐 Red button, stream lifecycle
├── interfaz/viewer.py     ← VideoPreview: BGR→RGB via numpy, renders on Canvas
├── camara/device.py       ← CameraInfo dataclass, list_cameras(), from_url()
└── camara/stream.py       ← CameraStream: accepts int (local) or str (URL), background thread
```

- `CameraStream.source` is `int | str` — int for local devices, str for URLs (`http://…`, `rtsp://…`).
- `CameraInfo.from_url(url)` creates a network source descriptor. Clicking "🌐 Red" opens a URL dialog.
- Resolution is only forced for local cameras (`cap.set()`) — network streams negotiate their own resolution.
- Warm-up (1s sleep + 5 discards) applies to both local and network sources.
- The app polls the stream every 30 ms via `tkinter.after()`.

## Known bug (mostly fixed): "Cámara detenida" with no image

**Root cause**: double-open on Windows DSHOW — `device.py` opens and releases,
then `stream.py` opens again. DSHOW's `release()` doesn't always free the driver.

**Fixes applied**:
1. `device.py`: 0.5s sleep after `cap.release()` to let DSHOW release
2. `stream.py`: `cap.set(FRAME_WIDTH/HEIGHT/FPS)` **before** first read
3. `stream.py`: 1.0s warm-up sleep + discards 5 initial garbled frames
4. `device.py`: resolution set during probe to negotiate a known profile
5. `viewer.py`: numpy slicing for BGR→RGB (removes hidden cv2 dependency)
6. `max_read_errors` increased from 30 → 50

### If it still fails

- Unsilence OpenCV: comment out `os.environ["OPENCV_LOG_LEVEL"] = "SILENT"` in both modules.
- Check Windows privacy: Settings → Privacy & security → Camera → allow desktop apps.
- Try forcing a different backend in `_BACKEND_PRIORITY`.
- For USB devices: make sure no other app (Zoom, Teams) holds the camera.

## Network / IP cameras (ESP32-CAM, etc.)

ESP32-CAM and similar devices typically stream MJPEG over HTTP:

```
http://192.168.1.100:81/stream
```

**How to connect:**
1. Click "🌐 Red" in the toolbar
2. Enter the stream URL
3. Click "Conectar" — the source appears in the camera dropdown
4. Select it and click "▶ Iniciar"

Also works with RTSP (`rtsp://…`) and RTMP (`rtmp://…`) URLs.
If the ESP32-CAM is flashed as a UVC USB camera, it appears as a normal
local camera and works with "🔍 Detectar" directly.

## Standalone .exe (PyInstaller)

```bat
pip install pyinstaller
build.bat
```

Output: `dist/VisorCamara.exe` — single file, no Python needed.
Embeds Windows manifest for DPI awareness and camera access.

## Dependencies

Runtime (`requirements.txt`):
- `opencv-python==5.0.0.93`
- `Pillow==12.2.0`
- `numpy==2.4.4`

Build-only (not in requirements.txt):
- `pyinstaller`
