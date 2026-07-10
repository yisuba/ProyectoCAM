# 📁 Guía de estructura del proyecto — ProyectoPDI

> ⚠️ **Guía viva** — actualizala cada vez que se agregue, mueva o elimine
> un archivo para que el árbol refleje siempre el estado real.

```
ProyectoPDI/
│
├── _asistente-ia/                ← 🧠 Guías y configuración para el agente IA
│   ├── AGENTS.md                 ←    Instrucciones detalladas para OpenCode
│   ├── guia-estructura.md        ←    ⬅️ Este archivo
│   └── opencode.json             ←    (referencia desde la raíz)
│
├── camara/                       ← 📷 Capa de abstracción de hardware
│   ├── __init__.py
│   ├── device.py                 ←    CameraInfo, list_cameras(), from_url() p/ IP cams
│   ├── stream.py                 ←    CameraStream: source=int|str, hilo separado con buffer
│   └── version.py                ←    __version__ leído desde VERSION
│
├── interfaz/                     ← 🖥️ Capa de presentación (tkinter)
│   ├── __init__.py
│   ├── app.py                    ←    CameraApp + _UrlDialog para fuentes de red
│   └── viewer.py                 ←    VideoPreview: redimensiona PIL, sin canvas.scale()
│
├── main.py                       ← 🚪 Punto de entrada (crea CameraApp, llama mainloop)
├── VERSION                       ← 🏷️ Versión actual del proyecto (0.2.0)
├── CHANGELOG.md                  ← 📋 Historial de cambios por versión
├── requirements.txt              ← 📦 Dependencias exactas (pip install -r)
├── run.bat                       ← ▶️ Inicia la aplicación (activa venv + python main.py)
├── setup.bat                     ← ⚙️  Crea el entorno virtual e instala dependencias
├── build.bat                     ← 🏗️ Compila .exe con PyInstaller (usa VERSION)
├── visor-camara.manifest         ← 🪟 Windows manifest (DPI awareness, permisos cámara)
├── README.md                     ← 📖 Documentación del proyecto
├── opencode.json                 ← 🔧 OpenCode descubre las instrucciones acá
└── .gitignore                    ← 🙈 Exclusiones para git (incluye dist/, build/)
```

## Convenciones

| Carpeta / archivo | Propósito | ¿Depende de otra capa? |
|-------------------|-----------|------------------------|
| `_asistente-ia/` | Configuración del agente IA | No — es metadata del proyecto |
| `camara/` | Detección y captura de video | No — solo OpenCV + numpy |
| `interfaz/` | Interfaz gráfica | Sí — importa de `camara/` |
| `build.bat` + `visor-camara.manifest` | Build system | No — solo herramientas |
| Raíz | Entrypoint, scripts, configuración | Sí — importa de `interfaz/` |

## Notas

- `_asistente-ia/` tiene prefijo `_` para ordenarse primero en el explorador
  y señalar visualmente que no es código de la aplicación
- `camara/` y `interfaz/` están separadas para que la capa de hardware sea
  intercambiable sin tocar la UI
- `CameraStream.source` acepta `int` (cámara local) o `str` (URL de red),
  lo que permite conectar ESP32-CAM y otras IP cámaras sin cambiar el flujo
- `opencode.json` está en la raíz porque OpenCode lo busca ahí, pero su
  contenido apunta a `_asistente-ia/AGENTS.md`
- `build.bat` genera un .exe portable en `dist/` (no requiere Python instalado)
