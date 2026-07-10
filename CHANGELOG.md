# Changelog — ProyectoPDI

## 0.3.0 (2026-07-10)

- Ventana de análisis con detección YOLO + filtro de Kalman (2D)
- Sliders custom en panel: confianza, Q (proceso), R (medición) con drag
- Selector de clases COCO desplegable con paginación (N/B + click)
- Toggle de overlays Kalman/YOLO por click en leyenda del panel
- Reproducción de archivos de video (.mp4, .avi, .mov) con loop automático
- FPS real del video respetado (throttle por CAP_PROP_FPS)
- Reseteo de Kalman al reiniciar el video loop
- Persistencia de tamaño/posición de ventana tkinter en config.json
- Bbox YOLO con color cian intenso y grosor 2 para mejor contraste
- Consola se cierra automáticamente al cerrar la app (run.bat)

## 0.2.0 (2026-07-09)

- Conexión a cámaras IP / ESP32-CAM por URL (HTTP MJPEG, RTSP, RTMP)
- Redimensionamiento automático de la imagen al tamaño de la ventana
- Corrección del bug de doble apertura DSHOW ("Cámara detenida")
- Build standalone con PyInstaller (.exe portable)
- Windows manifest con DPI awareness y permisos de cámara

## 0.1.0 (2026-07-09)

- Detección de cámaras USB e integradas
- Vista previa en vivo con tkinter
- Estructura de proyecto separada: camara/, interfaz/, _asistente-ia/
- Sistema de versiones (VERSION + version.py)
