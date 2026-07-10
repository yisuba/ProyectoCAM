# ProyectoPDI

**Visor de cámara y seguimiento de objetos en tiempo real para Windows.**

ProyectoPDI es una aplicación de escritorio que proporciona una vista previa en vivo desde cámaras USB locales, webcams integradas y streams de cámaras IP (ESP32-CAM, RTSP, MJPEG sobre HTTP). Incluye un modo de seguimiento de objetos integrado impulsado por detección YOLO y filtrado de Kalman para seguimiento visual en tiempo real con parámetros ajustables.

---

## Características

- **Captura multi-fuente**: cámaras USB, webcams integradas, cámaras IP (RTSP, RTMP, MJPEG sobre HTTP) y archivos de video locales (.mp4, .avi, .mov)
- **Vista previa en vivo**: interfaz basada en tkinter con detección de dispositivos, selección desplegable y controles de inicio/parada
- **Seguimiento de objetos**: ventana de análisis OpenCV dedicada con:
  - Detección YOLO (Ultralytics, dataset COCO, 80 clases)
  - Filtro de Kalman para suavizado de trayectoria y manejo de oclusiones
  - Umbral de confianza, ruido de proceso (Q) y ruido de medición (R) ajustables
  - Visualización de overlays activable/desactivable (Kalman / YOLO de forma independiente)
  - Longitud de estela configurable para visualización de movimiento
  - Selector de clases con paginación por teclado
- **Reproducción de archivos de video**: con bucle automático y limitación a la tasa de cuadros real
- **Persistencia de ventana**: el tamaño y la posición de la ventana se guardan entre sesiones
- **Ejecutable portátil**: se puede empaquetar en un único archivo ejecutable

---

## Inicio rápido

### Desde el código fuente (desarrollo)

```bat
setup.bat        # Crea el entorno virtual e instala las dependencias
run.bat          # Inicia la aplicación
```

### Instalación manual

```bat
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

### Requisitos

- Windows 10 u 11
- Python 3.13 o superior
- Una cámara (USB o integrada) **o** la URL de una cámara de red

---

## Uso

### Cámaras locales

1. Haga clic en **🔍 Detectar** para enumerar las cámaras conectadas.
2. Seleccione un dispositivo en el menú desplegable.
3. Haga clic en **▶ Iniciar** para comenzar la vista previa.
4. Haga clic en **⏹ Detener** para finalizar.

### Cámaras IP / red

1. Haga clic en **🌐 Red** en la barra de herramientas.
2. Introduzca la URL del stream. Formatos compatibles:

| Tipo | Ejemplo |
|------|---------|
| ESP32-CAM (MJPEG) | `http://192.168.1.100:81/stream` |
| RTSP | `rtsp://usuario:contraseña@cámara:554/stream` |
| RTMP | `rtmp://…` |
| MJPEG genérico | `http://…` |

3. Haga clic en **Conectar**. La fuente aparece en el menú desplegable.
4. Selecciónela y haga clic en **▶ Iniciar**.

> **Nota:** Si el ESP32-CAM está flasheado con firmware UVC, se detecta como una cámara USB estándar y no requiere URL.

### Archivos de video

1. Haga clic en **📁 Video** en la barra de herramientas.
2. Seleccione un archivo `.mp4`, `.avi` o `.mov`.
3. El video se reproduce en bucle con reinicio automático del filtro de Kalman en cada ciclo.

---

## Modo de seguimiento de objetos

Con un stream activo, haga clic en **🔬 Analizar** para abrir la ventana de seguimiento. La interfaz tkinter se oculta y se abre una ventana OpenCV con:

### Pipeline (por fotograma)

1. **Detección YOLO**: detecta la clase objetivo (clase COCO 0 = `person` por defecto)
2. **Filtro de Kalman**: suaviza la detección, predice la posición durante oclusiones
3. **Renderizado de overlays**: bounding boxes, puntos centrales y estela de movimiento

### Controles

| Tecla | Acción |
|-------|--------|
| `ESC` / `Q` | Volver a la interfaz tkinter |
| `ESPACIO` / `P` | Pausar / reanudar |
| `N` / `B` | Desplazar páginas del menú de clases |
| Clic en el nombre de la clase | Abrir menú desplegable de clases |
| Clic en un elemento del menú | Seleccionar clase de seguimiento |
| Clic en **Kalman** / **YOLO** del panel | Activar/desactivar overlay |

### Parámetros del panel

| Control deslizante | Rango | Descripción |
|--------------------|-------|-------------|
| Confianza | 0.00 – 1.00 | Umbral mínimo de confianza de YOLO |
| Q (Proceso) | 0.0 – 10.0 | Ruido de proceso de Kalman (valor alto = adaptación más rápida) |
| R (Medición) | 0.0 – 20.0 | Ruido de medición de Kalman (valor alto = confía menos en YOLO) |
| Estela (pts) | 1 – 60 | Longitud de la estela de movimiento en fotogramas |

---

## Estructura del proyecto

```
main.py                       Punto de entrada de la aplicación
│
├── interfaz/                 Capa de interfaz (tkinter + OpenCV)
│   ├── app.py                Ventana principal tkinter y barra de herramientas
│   ├── viewer.py             Renderizado del visor de video
│   ├── analysis_win.py       Ventana de seguimiento YOLO + Kalman
│   └── config_manager.py     Persistencia de configuración local
│
├── camara/                   Capa de abstracción de cámaras
│   ├── device.py             Descubrimiento y descriptores de cámaras
│   ├── stream.py             Captura de fotogramas en segundo plano
│   └── version.py            Versión de la aplicación
│
├── tracker/                  Módulo de seguimiento de objetos
│   ├── detector.py           Detector YOLO (Ultralytics)
│   └── kalman.py             Filtro de Kalman 2D (NumPy puro)
│
└── _asistente-ia/            Documentación interna del proyecto
```

---

## Generación del ejecutable portátil

```bat
pip install pyinstaller
build.bat
```

El ejecutable se genera en `portable/VisorCamara.exe`. Incluye un manifiesto de Windows para la conciencia de DPI y los permisos de acceso a la cámara.

> **Nota:** El binario no se incluye en el repositorio. Cada desarrollador lo genera localmente. Para lanzamientos oficiales, el ejecutable se distribuye como un asset de GitHub Releases.

---

## Dependencias

### Tiempo de ejecución (`requirements.txt`)

- `opencv-python>=5.0` — Captura de video y procesamiento de imágenes
- `Pillow>=12.0` — Conversión de formatos de imagen
- `numpy>=2.0` — Operaciones con arreglos y datos de imagen
- `ultralytics>=8.0` — Modelo de detección de objetos YOLO

### Construcción (no incluido en requirements.txt)

- `pyinstaller` — Empaquetado del ejecutable portátil

---

## Solución de problemas

### "Cámara detenida" sin imagen

- Asegúrese de que ninguna otra aplicación esté usando la cámara (Zoom, Teams, navegador, etc.)
- Reinicie la aplicación
- Desconecte y vuelva a conectar la cámara USB
- Verifique la configuración de privacidad de Windows:  
  Configuración → Privacidad y seguridad → Cámara → permitir aplicaciones de escritorio

### La cámara no se detecta

- Pruebe con la aplicación Cámara de Windows para descartar problemas de hardware o controladores
- Verifique la conexión del cable USB

---

## Licencia

Este proyecto se proporciona con fines educativos y de investigación.
