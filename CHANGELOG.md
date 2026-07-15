# Changelog — ProyectoPDI

## 0.5.0 (2026-07-14)

- Tracking híbrido async en ventana de análisis: YOLO cada N frames + KCF en intermedios + Kalman siempre
- Modo Async (YOLO cada N configurable, default 10) y modo Continuo (YOLO siempre) toggleable con tecla C
- Slider "YOLO cada N" (3-20) para ajustar frecuencia de detección en modo async
- KCF se inicializa una sola vez por sesión async, sin recreación (evita degradación de FPS)
- KCF con bbox propio (amarillo) toggleable por click en leyenda del panel
- Bboxes Kalman (verde), YOLO (azul), KCF (amarillo) con toggle individual
- Medición de recursos toggleable con M: CPU, RAM y tiempo por frame (ms)
- Indicador de fuente (YOLO/KCF/PREDICT) en overlay y panel
- psutil agregado para monitoreo de recursos

## 0.4.0 (2026-07-14)

- Nuevo modulo `tracker/detector_pose_manos.py`: clase PoseHandTracker con 4 modos de operacion
- State machine con destruccion/recreacion dinamica de arreglos de Kalman al cambiar de modo
- Modo Cuerpo Simple (12 landmarks, 12 Kalman): hombros, codos, munecas, caderas, rodillas, tobillos
- Modo Cuerpo Completo (17 landmarks, 17 Kalman): esqueleto COCO completo sobre MediaPipe
- Modo Mano Simple (6 landmarks, 6 Kalman): muneca + 5 puntas de dedos
- Modo Mano Completa (21 landmarks, 21 Kalman): mano anatomica completa
- Prediccion por oclusion: Kalman estima posicion por velocidad cuando MediaPipe pierde deteccion
- Parametros ajustables en vivo: confianza, Q (proceso), R (medicion)
- Ventana OpenCV dedicada (`interfaz/mediapipe_win.py`) con sliders custom y cambio de modo por teclas 1-4
- Boton "Pose/Mano" en la toolbar de tkinter, al lado de "Analizar"
- Descarga automatica de modelos .task de MediaPipe en `models/mediapipe/`
- MediaPipe 0.10.35 (Tasks API, no la obsoleta solutions API)
- Seccion "mediapipe" en config.json con persistencia de parametros

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
