# ProyectoPDI

Visor de camara y seguimiento de objetos en tiempo real para Windows.

Aplicacion de escritorio que proporciona vista previa en vivo desde camaras USB, webcams integradas, streams de camaras IP (ESP32-CAM, RTSP, MJPEG sobre HTTP) y archivos de video locales. Incluye un modo de seguimiento de objetos con deteccion YOLO y filtro de Kalman, con parametros ajustables en tiempo real.

---

## Caracteristicas

- Captura multi-fuente: camaras USB, webcams, camaras IP (RTSP, RTMP, MJPEG) y archivos de video (.mp4, .avi, .mov)
- Vista previa en vivo con deteccion automatica de dispositivos
- Seguimiento de objetos en ventana OpenCV dedicada:
  - Deteccion YOLO (Ultralytics, dataset COCO, 80 clases)
  - Filtro de Kalman 2D para suavizado de trayectoria y prediccion ante oclusiones
  - Umbral de confianza, ruido de proceso (Q) y ruido de medicion (R) ajustables
  - Visualizacion de overlays activable/desactivable (Kalman / YOLO independientemente)
  - Longitud de estela configurable para visualizacion de trayectoria
  - Selector desplegable de clases con paginacion por teclado
- Reproduccion de video con bucle automatico y limitacion a la tasa de cuadros real
- Persistencia de tamano y posicion de ventana entre sesiones
- Ejecutable portatil (build con PyInstaller)

---

## Inicio rapido

### Desde el codigo fuente

```bat
setup.bat        # Crea el entorno virtual e instala dependencias
run.bat          # Inicia la aplicacion
```

### Instalacion manual

```bat
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

### Requisitos

- Windows 10 u 11
- Python 3.13 o superior
- Una camara (USB o integrada) o la URL de una camara de red

---

## Uso

### Camaras locales

1. Presione el boton Detectar para enumerar las camaras conectadas.
2. Seleccione un dispositivo en el menu desplegable.
3. Presione Iniciar para comenzar la vista previa.
4. Presione Detener para finalizar.

### Camaras IP / red

1. Presione el boton Red en la barra de herramientas.
2. Introduzca la URL del stream. Formatos compatibles:

| Tipo | Ejemplo |
|------|---------|
| ESP32-CAM (MJPEG) | `http://192.168.1.100:81/stream` |
| RTSP | `rtsp://usuario:contrasena@camara:554/stream` |
| RTMP | `rtmp://...` |
| MJPEG generico | `http://...` |

3. Presione Conectar. La fuente aparece en el menu desplegable.
4. Seleccionela y presione Iniciar.

> Nota: si el ESP32-CAM esta flasheado con firmware UVC, se detecta como camara USB estandar y no requiere URL.

### Archivos de video

1. Presione el boton Video en la barra de herramientas.
2. Seleccione un archivo .mp4, .avi o .mov.
3. El video se reproduce en bucle con reinicio automatico del filtro de Kalman en cada ciclo.

---

## Modo de seguimiento de objetos

Con un stream activo, presione el boton Analizar para abrir la ventana de seguimiento. La interfaz tkinter se oculta y se abre una ventana OpenCV con el siguiente pipeline por fotograma:

1. Deteccion YOLO: detecta la clase objetivo (clase COCO 0 = persona por defecto)
2. Filtro de Kalman: suaviza la deteccion y predice la posicion durante oclusiones
3. Renderizado de overlays: bounding boxes, centros y estela de movimiento

### Controles

| Tecla | Accion |
|-------|--------|
| ESC / Q | Volver a la interfaz principal |
| ESPACIO / P | Pausar / reanudar |
| N / B | Desplazar paginas del menu de clases |
| Click en nombre de clase | Abrir menu desplegable de clases |
| Click en elemento del menu | Seleccionar clase de seguimiento |
| Click en "Kalman" o "YOLO" | Activar/desactivar overlay |

### Parametros del panel

| Control | Rango | Descripcion |
|---------|-------|-------------|
| Confianza | 0.00 - 1.00 | Umbral minimo de confianza de YOLO |
| Q (Proceso) | 0.0 - 10.0 | Ruido de proceso de Kalman (mayor = adaptacion mas rapida) |
| R (Medicion) | 0.0 - 20.0 | Ruido de medicion de Kalman (mayor = confia menos en YOLO) |
| Estela (pts) | 1 - 60 | Longitud de la estela de movimiento en fotogramas |

---

## Estructura del proyecto

```
main.py                       Punto de entrada
|
+-- interfaz/                 Capa de interfaz (tkinter + OpenCV)
|   +-- app.py                Ventana principal y barra de herramientas
|   +-- viewer.py             Renderizado del visor de video
|   +-- analysis_win.py       Ventana de seguimiento YOLO + Kalman
|   +-- config_manager.py     Persistencia de configuracion local
|
+-- camara/                   Capa de abstraccion de camaras
|   +-- device.py             Descubrimiento y descriptores de camaras
|   +-- stream.py             Captura de fotogramas en segundo plano
|   +-- version.py            Version de la aplicacion
|
+-- tracker/                  Modulo de seguimiento de objetos
|   +-- detector.py           Detector YOLO (Ultralytics)
|   +-- kalman.py             Filtro de Kalman 2D (NumPy)
|
+-- _dev/                     Documentacion interna de desarrollo
```

---

## Generacion del ejecutable portatil

```bat
pip install pyinstaller
build.bat
```

El ejecutable se genera en `portable/VisorCamara.exe`. Incluye un manifiesto de Windows para DPI awareness y permisos de camara.

> El binario no se incluye en el repositorio. Cada desarrollador lo genera localmente. Para lanzamientos oficiales, el ejecutable se distribuye como asset de GitHub Releases.

---

## Dependencias

### Tiempo de ejecucion (requirements.txt)

- `opencv-python>=5.0` — Captura de video y procesamiento de imagenes
- `Pillow>=12.0` — Conversion de formatos de imagen
- `numpy>=2.0` — Operaciones con arreglos y datos de imagen
- `ultralytics>=8.0` — Modelo de deteccion de objetos YOLO

### Construccion (no incluido en requirements.txt)

- `pyinstaller` — Empaquetado del ejecutable portatil

---

## Solucion de problemas

### La camara no muestra imagen

- Verifique que ninguna otra aplicacion este usando la camara (Zoom, Teams, navegador)
- Reinicie la aplicacion
- Desconecte y vuelva a conectar la camara USB
- Verifique la configuracion de privacidad de Windows: Configuracion > Privacidad y seguridad > Camara > permitir aplicaciones de escritorio

### La camara no se detecta

- Pruebe con la aplicacion Camara de Windows para descartar problemas de hardware o drivers
- Verifique la conexion del cable USB

---

## Licencia

Proyecto educativo y de investigacion.
