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
main.py                    ← entrypoint (env setup + logging)
│
├── interfaz/              ← UI layer (tkinter + OpenCV)
│   ├── app.py             ← CameraApp: toolbar, combobox, botones, stream lifecycle
│   ├── viewer.py          ← VideoPreview: BGR→RGB via numpy, render en Canvas
│   ├── analysis_win.py    ← OpenCV window: YOLO + Kalman + trackbars
│   ├── mediapipe_win.py   ← OpenCV window: MediaPipe Pose/Hands + Kalman + trackbars
│   └── config_manager.py  ← config.json persistencia local
│
├── camara/                ← Camera layer
│   ├── device.py          ← CameraInfo, list_cameras(), from_url()
│   ├── stream.py          ← CameraStream: int (local) o str (URL), background thread
│   └── version.py         ← lee VERSION
│
├── tracker/               ← Object tracking
│   ├── detector.py        ← YOLO detector (ultralytics)
│   ├── kalman.py          ← Filtro de Kalman 2D (numpy puro)
│   └── detector_pose_manos.py ← PoseHandTracker (MediaPipe Tasks API + Kalman)
│
└── models/mediapipe/      ← Modelos .task de MediaPipe (descarga automática)
```

- `CameraStream.source` es `int | str` — int para local, str para URLs (`http://…`, `rtsp://…`).
- `CameraInfo.from_url(url)` crea un descriptor de red. El botón "🌐 Red" abre un diálogo de URL.
- Resolución sólo se fuerza para cámaras locales — las de red negocian solas.
- Warm-up (1s sleep + 5 descartes) aplica a ambos tipos de fuente.
- El preview de tkinter polea el stream cada 30 ms con `after()`.
- **Modo análisis** (`"🔬 Analizar"`) abre una ventana OpenCV separada con su propio loop (cv2.waitKey).
- **Modo pose/manos** (`"🖐️ Pose/Mano"`) abre otra ventana OpenCV separada para MediaPipe.
- `CameraStream.source` es `int | str` — int para local, str para URLs.
- `detector_pose_manos.py` usa la **Tasks API** de MediaPipe 0.10.35 (NO la obsoleta `mp.solutions`).
- Los modelos .task se descargan automáticamente a `models/mediapipe/` en la primera ejecución.

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

## Object Tracking (modo análisis)

Al hacer clic en **"🔬 Analizar"** (con un stream activo), la ventana tkinter se oculta y se abre una ventana OpenCV con:

### Pipeline por frame

1. **Detección (YOLO)**: `tracker/detector.py` usa ultralytics (modelo `yolo11n.pt`) para detectar la clase objetivo (COCO class 0 = persona por defecto).
   - Devuelve centro [x, y] + bounding box.
   - Filtrable por **umbral de confianza** (trackbar).

2. **Filtro de Kalman**: `tracker/kalman.py` implementa un filtro 2D con velocidad constante.
   - **Estado**: [x, y, vx, vy]
   - **Con detección**: `update()` — corrige la posición con la medición de YOLO.
   - **Sin detección** (oclusión): `predict()` — estima la posición usando el modelo de velocidad.
   - Trackbars para ajustar **Q** (ruido de proceso) y **R** (ruido de medición) en vivo.

3. **Visualización**: Bounding box suavizado (verde) + bbox crudo de YOLO (azul) + trail del centro + FPS real.

### Trackbars

| Trackbar | Rango | Efecto |
|----------|-------|--------|
| Confianza | 0–100 → 0.00–1.00 | Mínima confianza YOLO para aceptar detección |
| Q (Proceso) | 0–100 → 0.0–10.0 | Mayor Q = se adapta más rápido a cambios bruscos |
| R (Medición) | 0–100 → 0.0–20.0 | Mayor R = confía menos en YOLO, más en la predicción |

### Controles

- **ESC / Q**: Cerrar análisis y volver a tkinter.
- **SPACE / P**: Pausar/reanudar.

### Logger

Todo se registra en `logs/tracker.log` (rotación manual). Si algo falla, revisá ahí
antes de silenciar/desilenciar OpenCV.

## Pose / Hand Tracking (modo pose/manos)

Al hacer clic en **"🖐️ Pose/Mano"** (con un stream activo), la ventana tkinter se oculta y se abre una ventana OpenCV con:

### Modos de operación

| Tecla | Modo | Landmarks | Kalman | Descripción |
|-------|------|-----------|--------|-------------|
| 1 | CUERPO_SIMPLE | 12 | 12 | Hombros, codos, muñecas, caderas, rodillas, tobillos |
| 2 | CUERPO_COMPLETO | 17 | 17 | COCO 17 estándar sobre MediaPipe |
| 3 | MANO_SIMPLE | 6 | 6 | Muñeca + 5 puntas de dedos |
| 4 | MANO_COMPLETA | 21 | 21 | Mano completa (21 landmarks) |

### Pipeline por frame

1. **MediaPipe Tasks API**: `PoseLandmarker` o `HandLandmarker` según el modo.
2. **Extracción selectiva**: solo los landmarks del modo activo (sub-muestreo para modos simples).
3. **Kalman por landmark**: cada landmark tiene su propio `KalmanFilter` (2D, velocidad constante).
   - Con detección → `update()` corrige la posición
   - Sin detección (oclusión) → `predict()` estima por velocidad previa
4. **Dibujo**: líneas verdes (detectado) o amarillas (predicción).

### State machine

`PoseHandTracker.set_mode(mode)`:
1. Destruye el arreglo anterior de Kalman (`self._kfs.clear()`).
2. Crea nuevos Kalman según la cantidad de landmarks del modo.
3. Recrea el modelo MediaPipe correspondiente (libera el anterior).
4. Resetea flags de detección y posiciones suavizadas.

### Parámetros (trackbars)

| Trackbar | Rango | Efecto |
|----------|-------|--------|
| Confianza | 0.01–1.00 | `min_detection_confidence` de MediaPipe |
| Q (Proceso) | 0.0–10.0 | Mayor Q = Kalman se adapta más rápido |
| R (Medición) | 0.0–20.0 | Mayor R = Kalman confía menos en MediaPipe |

### Controles

- **1 / 2 / 3 / 4**: Cambiar modo en vivo (recrea Kalman automáticamente).
- **ESC / Q**: Cerrar y volver a tkinter.
- **SPACE / P**: Pausar/reanudar.

### Modelos

Se descargan automáticamente desde Google Storage a `models/mediapipe/`:
- `pose_landmarker_lite.task` (~5.6 MB)
- `hand_landmarker.task` (~7.6 MB)

Usan la Tasks API de MediaPipe (NO la vieja `mp.solutions` que ya no existe en 0.10.35+).

## Configuración local (no se sube a GitHub)

El archivo `config.json` (en la raíz) persiste:
- Última fuente de cámara usada.
- Historial de URLs de red.
- Preferencias de detección (clase objetivo, confianza por defecto).

Está en `.gitignore` porque es específico de cada máquina.

## Standalone .exe (PyInstaller)

```bat
pip install pyinstaller
build.bat
```

Output: `dist/VisorCamara.exe` → también copiado a `portable/`.
Embeds Windows manifest for DPI awareness and camera access.

**El .exe no se sube a GitHub** (binario muy grande). Cada uno lo builda
localmente. Si se necesita una release oficial, se sube a GitHub Releases
como asset separado, no en el repo.

**Current version**: `0.x.x`. Not yet 1.0. Versions track functional milestones,
not just commits.

## Standalone .exe (PyInstaller)

```bat
pip install pyinstaller
build.bat
```

Output: `dist/VisorCamara.exe` → also copied to `portable/`.
Embeds Windows manifest for DPI awareness and camera access.
Built **only** on explicit request.

## Dependencies

Runtime (`requirements.txt`):
- `opencv-python==5.0.0.93`
- `Pillow==12.2.0`
- `numpy==2.4.4`
- `ultralytics>=8.0.0`   ← YOLO object detector (~150 MB con pesos)

Build-only (not in requirements.txt):
- `pyinstaller`
